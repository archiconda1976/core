"""Support for Russound media browsing."""

from aiorussound.const import FeatureFlag
from aiorussound.rio import MediaManagementMenuPage, RussoundRIOClient, Zone
from aiorussound.rio.models import SourceType
from aiorussound.util import is_feature_supported

from homeassistant.components.media_player import BrowseError, BrowseMedia, MediaClass
from homeassistant.core import HomeAssistant

from .const import RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT


async def async_browse_media(
    hass: HomeAssistant,
    client: RussoundRIOClient,
    media_content_id: str | None,
    media_content_type: str | None,
    zone: Zone,
) -> BrowseMedia:
    """Browse media."""
    if media_content_type == RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT:
        return await _media_management_payload(zone, media_content_id)

    if media_content_type == "presets":
        return await _presets_payload(_find_presets_by_zone(client, zone))

    return await _root_payload(
        hass,
        _find_presets_by_zone(client, zone),
        _supports_media_management(zone),
    )


async def _root_payload(
    hass: HomeAssistant,
    presets_by_zone: dict[int, dict[int, str]],
    supports_media_management: bool,
) -> BrowseMedia:
    """Return root payload for Russound RIO."""
    children: list[BrowseMedia] = []

    if presets_by_zone:
        children.append(
            BrowseMedia(
                title="Presets",
                media_class=MediaClass.DIRECTORY,
                media_content_id="",
                media_content_type="presets",
                thumbnail="/api/brands/integration/russound_rio/logo.png",
                can_play=False,
                can_expand=True,
            )
        )

    if supports_media_management:
        children.append(
            BrowseMedia(
                title="Browse Music",
                media_class=MediaClass.DIRECTORY,
                media_content_id="",
                media_content_type=RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
                thumbnail="/api/brands/integration/russound_rio/logo.png",
                can_play=False,
                can_expand=True,
            )
        )

    return BrowseMedia(
        title="Russound",
        media_class=MediaClass.DIRECTORY,
        media_content_id="",
        media_content_type="root",
        can_play=False,
        can_expand=True,
        children=children,
    )


async def async_play_media_management(zone: Zone, media_id: str) -> None:
    """Play a media-management item addressed by its opaque menu path."""
    menu_path = _decode_media_management_path(media_id)
    if not menu_path:
        raise ValueError("A Media Management item path is required")

    async with zone.create_media_management_session() as session:
        await session.initialize()
        for item_id in menu_path[:-1]:
            await session.select_item(item_id)
        await session.select_item(menu_path[-1], expect_page=False)


async def _media_management_payload(
    zone: Zone, media_content_id: str | None
) -> BrowseMedia:
    """Return one controller-routed Media Management menu page."""
    menu_path = _decode_media_management_path(media_content_id)

    async with zone.create_media_management_session() as session:
        page = await session.initialize()
        for item_id in menu_path:
            selected_page = await session.select_item(item_id)
            if selected_page is None:
                raise BrowseError("The selected Russound item does not contain a menu")
            page = selected_page

    return _media_management_page_payload(page, menu_path)


def _media_management_page_payload(
    page: MediaManagementMenuPage, menu_path: tuple[int, ...]
) -> BrowseMedia:
    """Translate a RIO Media Management page into Home Assistant browse media."""
    children = [
        BrowseMedia(
            title=item.text,
            media_class=(
                MediaClass.DIRECTORY if item.is_menu is not False else MediaClass.TRACK
            ),
            media_content_id=_encode_media_management_path((*menu_path, item.item_id)),
            media_content_type=RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
            thumbnail=item.image_url,
            can_play=item.is_menu is False,
            can_expand=item.is_menu is not False,
        )
        for item in page.menu_items
    ]

    return BrowseMedia(
        title="Browse Music",
        media_class=MediaClass.DIRECTORY,
        media_content_id=_encode_media_management_path(menu_path),
        media_content_type=RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
        can_play=False,
        can_expand=True,
        children=children,
    )


def _supports_media_management(zone: Zone) -> bool:
    """Return whether the selected source is a Russound media streamer."""
    source = zone.fetch_current_source()
    return source is not None and source.type == SourceType.RUSSOUND_MEDIA_STREAMER


def _decode_media_management_path(media_content_id: str | None) -> tuple[int, ...]:
    """Decode a slash-delimited Media Management menu path."""
    if not media_content_id:
        return ()

    try:
        menu_path = tuple(int(item_id) for item_id in media_content_id.split("/"))
    except ValueError as err:
        raise ValueError("Invalid Media Management item path") from err

    if not all(1 <= item_id <= 2**32 for item_id in menu_path):
        raise ValueError("Invalid Media Management item path")
    return menu_path


def _encode_media_management_path(menu_path: tuple[int, ...]) -> str:
    """Encode a Media Management menu path for Home Assistant's browse API."""
    return "/".join(str(item_id) for item_id in menu_path)


async def _presets_payload(presets_by_zone: dict[int, dict[int, str]]) -> BrowseMedia:
    """Create payload to list presets."""
    children: list[BrowseMedia] = []
    for source_id, presets in presets_by_zone.items():
        for preset_id, preset_name in presets.items():
            children.append(
                BrowseMedia(
                    title=preset_name,
                    media_class=MediaClass.CHANNEL,
                    media_content_id=f"{source_id},{preset_id}",
                    media_content_type="preset",
                    can_play=True,
                    can_expand=False,
                )
            )

    return BrowseMedia(
        title="Presets",
        media_class=MediaClass.DIRECTORY,
        media_content_id="",
        media_content_type="presets",
        can_play=False,
        can_expand=True,
        children=children,
    )


def _find_presets_by_zone(
    client: RussoundRIOClient, zone: Zone
) -> dict[int, dict[int, str]]:
    """Returns a dict by {source_id: {preset_id: preset_name}}."""
    assert client.rio_version
    return {
        source_id: source.presets
        for source_id, source in client.sources.items()
        if source.presets
        and (
            not is_feature_supported(
                client.rio_version, FeatureFlag.SUPPORT_ZONE_SOURCE_EXCLUSION
            )
            or source_id in zone.enabled_sources
        )
    }
