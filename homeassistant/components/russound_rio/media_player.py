"""Support for Russound multizone controllers using RIO Protocol."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

import logging

from . import RussoundConfigEntry
from aiorussound import Controller
from aiorussound.models import Source, Favorite
from aiorussound.rio import ZoneControlSurface

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    Event,
    HomeAssistant,
    ServiceCall,
)
from homeassistant.helpers.entity import Entity
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    MENU_PLAY_SYSTEM_FAVORITE,
    MENU_PLAY_ZONE_FAVORITE,
    MENU_SOURCE,
    MENU_SOURCE_TITLE,
    MENU_SYSTEM_FAVORITE,
    MENU_SYSTEM_FAVORITE_TITLE,
    MENU_ZONE_FAVORITE,
    MENU_ZONE_FAVORITE_TITLE,
    MP_FEATURES_BY_FLAG,
    RUSSOUND_MEDIA_TITLE,
    RUSSOUND_STREAMER_SOURCE,
    SERVICE_CALL_ATTR_FAVORITE_ID,
    SERVICE_SAVE_SYSTEM_FAVORITE,
    SERVICE_SAVE_ZONE_FAVORITE,
    SERVICE_DELETE_SYSTEM_FAVORITE,
    SERVICE_DELETE_ZONE_FAVORITE,
    SERVICE_CALL_ATTR_ENTITY_ID,
    SERVICE_CALL_ATTR_FAVORITE_NAME,
)

MEDIA_PLAYER_SCHEMA = vol.Schema({SERVICE_CALL_ATTR_ENTITY_ID: cv.comp_entity_ids})
RUSSOUND_SYSTEM_CALL_SCHEMA = MEDIA_PLAYER_SCHEMA.extend(
    {vol.Required(SERVICE_CALL_ATTR_FAVORITE_ID): cv.string}
)

from .entity import RussoundBaseEntity, command

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Russound RIO platform."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=config,
    )
    if (
        result["type"] is FlowResultType.CREATE_ENTRY
        or result["reason"] == "single_instance_allowed"
    ):
        async_create_issue(
            hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version="2025.2.0",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": "Russound RIO",
            },
        )
        return
    async_create_issue(
        hass,
        DOMAIN,
        f"deprecated_yaml_import_issue_{result['reason']}",
        breaks_in_ha_version="2025.2.0",
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=IssueSeverity.WARNING,
        translation_key=f"deprecated_yaml_import_issue_{result['reason']}",
        translation_placeholders={
            "domain": DOMAIN,
            "integration_title": "Russound RIO",
        },
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RussoundConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Russound RIO platform."""
    client = entry.runtime_data
    sources = client.sources

    async_add_entities(
        RussoundZoneDevice(controller, zone_id, sources)
        for controller in client.controllers.values()
        for zone_id in controller.zones
    )

    async def service_handle(service: ServiceCall) -> None:
        """Handle for services."""
        favorite_id = service.data.get(SERVICE_CALL_ATTR_FAVORITE_ID)
        favorite_name = service.data.get(SERVICE_CALL_ATTR_FAVORITE_NAME)
        entity_ids = service.data.get(SERVICE_CALL_ATTR_ENTITY_ID)

        if favorite_id and entity_ids:
            for entity in entities:
                for entity_in in entity_ids:
                    if entity.entity_id == entity_in:
                        _LOGGER.debug("Found requested entity %s", entity_in)
                        if service.service == SERVICE_SAVE_SYSTEM_FAVORITE:
                            await entity.save_system_favorite(
                                int(favorite_id), favorite_name
                            )
                        elif service.service == SERVICE_SAVE_ZONE_FAVORITE:
                            await entity.save_zone_favorite(
                                int(favorite_id), favorite_name
                            )
                        elif service.service == SERVICE_DELETE_SYSTEM_FAVORITE:
                            await entity.delete_system_favorite(int(favorite_id))
                        elif service.service == SERVICE_DELETE_ZONE_FAVORITE:
                            await entity.delete_zone_favorite(int(favorite_id))

    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_SYSTEM_FAVORITE,
        service_handle,
        schema=RUSSOUND_SYSTEM_CALL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_ZONE_FAVORITE,
        service_handle,
        schema=RUSSOUND_SYSTEM_CALL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SYSTEM_FAVORITE,
        service_handle,
        schema=RUSSOUND_SYSTEM_CALL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_ZONE_FAVORITE,
        service_handle,
        schema=RUSSOUND_SYSTEM_CALL_SCHEMA,
    )


class RussoundZoneDevice(RussoundBaseEntity, MediaPlayerEntity):
    """Representation of a Russound Zone."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PLAY_MEDIA
    )

    def __init__(
        self, controller: Controller, zone_id: int, sources: dict[int, Source]
    ) -> None:
        """Initialize the zone device."""
        super().__init__(controller)
        self._zone_id = zone_id
        _zone = self._zone
        self._sources = sources
        self._attr_name = _zone.name
        self._attr_unique_id = f"{self._primary_mac_address}-{_zone.device_str}"
        for flag, feature in MP_FEATURES_BY_FLAG.items():
            if flag in self._client.supported_features:
                self._attr_supported_features |= feature

    async def save_system_favorite(self, favorite_id: int, favorite_name=None) -> None:
        """Save system favorite to controller."""

        if favorite_name is None:
            # default to channel name if no name is provided
            favorite_name = self._current_source().properties.channel_name

        if favorite_name is None:
            # if no channel name, set a default name
            favorite_name = f"F{favorite_id}"

        if favorite_id >= 1 and favorite_id <= 32:
            _LOGGER.debug("Saving system favorite %d", favorite_id)
            await self._zone.send_event(
                "saveSystemFavorite", f'"{favorite_name}"', favorite_id
            )

    async def save_zone_favorite(self, favorite_id: int, favorite_name=None) -> None:
        """Save zone favorite to contoller."""

        if favorite_name is None:
            # default to channel name if no name is provided
            favorite_name = self._current_source().properties.channel_name

        if favorite_name is None:
            # if no channel name, set a default name
            favorite_name = f"F{favorite_id}"

        if favorite_id >= 1 and favorite_id <= 32:
            _LOGGER.debug("Saving zone favorite %d", favorite_id)
            await self._zone.send_event(
                "saveZoneFavorite", f'"{favorite_name}"', favorite_id
            )

    async def delete_system_favorite(self, favorite_id: int) -> None:
        """Delete system favorite from contoller."""

        if favorite_id >= 1 and favorite_id <= 32:
            _LOGGER.debug("Removing system favorite %d", favorite_id)
            await self._zone.send_event(
                "KeyRelease", "deleteSystemFavorite", favorite_id
            )

    async def delete_zone_favorite(self, favorite_id: int) -> None:
        """Delete zone favorite from contoller."""

        if favorite_id >= 1 and favorite_id <= 2:
            _LOGGER.debug("Removing system favorite %d", favorite_id)
            await self._zone.send_event("KeyRelease", "deleteZoneFavorite", favorite_id)

    @property
    def _zone(self) -> ZoneControlSurface:
        return self._controller.zones[self._zone_id]

    @property
    def _source(self) -> Source:
        return self._zone.fetch_current_source()

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        status = self._zone.status
        if status == "ON":
            return MediaPlayerState.ON
        if status == "OFF":
            return MediaPlayerState.OFF
        return None

    @property
    def source(self):
        """Get the currently selected source."""
        return self._source.name

    @property
    def source_list(self):
        """Return a list of available input sources."""
        return [x.name for x in self._sources.values()]

    @property
    def media_title(self):
        """Title of current playing media."""
        if self._source.song_name != None:
            return self._source.song_name
        elif self._source.program_service_name != None:
            return self._source.program_service_name
        else:
            return self._source.name

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        if self._source.artist_name != None:
            return self._source.artist_name
        elif self._source.radio_text != None:
            return self._source.radio_text
        else:
            return None

    @property
    def media_album_name(self):
        """Album name of current playing media, music track only."""
        if self._source.album_name != None:
            return self._source.album_name
        elif self._source.channel_name != None:
            return self._source.channel_name
        else:
            return None

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        return self._source.cover_art_url

    @property
    def volume_level(self):
        """Volume level of the media player (0..1).

        Value is returned based on a range (0..50).
        Therefore float divide by 50 to get to the required range.
        """
        return float(self._zone.volume or "0") / 50.0

    @command
    async def async_turn_off(self) -> None:
        """Turn off the zone."""
        await self._zone.zone_off()

    @command
    async def async_turn_on(self) -> None:
        """Turn on the zone."""
        await self._zone.zone_on()

    @command
    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level."""
        rvol = int(volume * 50.0)
        await self._zone.set_volume(str(rvol))

    @command
    async def async_select_source(self, source: str) -> None:
        """Select the source input for this zone."""
        for source_id, src in self._sources.items():
            if src.name.lower() != source.lower():
                continue
            await self._zone.select_source(source_id)
            break

    @command
    async def async_volume_up(self) -> None:
        """Step the volume up."""
        await self._zone.volume_up()

    @command
    async def async_volume_down(self) -> None:
        """Step the volume down."""
        await self._zone.volume_down()

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse system favorites and zone favorites and MMMenus if supported by source."""

        if not media_content_id:
            return await self.async_browse_media_root()

        path = media_content_id.partition("/")
        if path[0] == MENU_SYSTEM_FAVORITE:
            return await self.async_browse_media_system_favorites(True)
        elif path[0] == MENU_ZONE_FAVORITE:
            return await self.async_browse_media_zone_favorites(True)
        elif MENU_PLAY_SYSTEM_FAVORITE in path[0]:
            await self._zone.send_event("restoreSystemFavorite", media_content_id[11:])
            return
        elif MENU_PLAY_ZONE_FAVORITE in path[0]:
            await self._zone.send_event("restoreZoneFavorite", media_content_id[13:])
            return

        raise BrowseError(f"Media not found: {media_content_type} / {media_content_id}")

    async def async_browse_media_root(self) -> BrowseMedia:
        """Return root media objects."""

        return BrowseMedia(
            title=RUSSOUND_MEDIA_TITLE,
            media_class=MediaClass.DIRECTORY,
            media_content_id="",
            media_content_type="",
            can_play=False,
            can_expand=True,
            children=[
                await self.async_browse_media_zone_favorites(),
                await self.async_browse_media_system_favorites(),
            ],
        )

    def _get_source_from_id(self, source_id_in) -> str:
        for source_id in self._sources:
            if source_id == int(source_id_in):
                return str(self._sources[source_id].name)
        return "unknown"

    def _get_menu_title(self, favorite: Favorite) -> str:
        return (
            "["
            + self._get_source_from_id(favorite.source_id)
            + "] \r\n"
            + favorite.name
        )

    async def async_browse_media_zone_favorites(
        self, expanded: bool = False
    ) -> BrowseMedia:
        """Return zone favorite objects."""

        if expanded:
            zone_favorites = await self._zone.enumerate_favorites()
            children = [
                BrowseMedia(
                    title=self._get_menu_title(fav),
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"{MENU_PLAY_ZONE_FAVORITE}:{fav.favorite_id}",
                    media_content_type=MediaType.MUSIC,
                    can_play=True,
                    can_expand=False,
                    thumbnail=fav.album_cover_url,
                )
                # for uri, item in self.coordinator.source_map.items()
                for fav in zone_favorites
                if fav.favorite_id > 0
            ]
        else:
            children = None

        return BrowseMedia(
            title=MENU_ZONE_FAVORITE_TITLE,
            media_class=MediaClass.DIRECTORY,
            media_content_id=MENU_ZONE_FAVORITE,
            media_content_type=MediaType.MUSIC,
            children_media_class=MediaClass.MUSIC,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def async_browse_media_system_favorites(
        self, expanded: bool = False
    ) -> BrowseMedia:
        """Return system favorite objects."""

        if expanded:
            system_favorites = await self._zone.client.enumerate_system_favorites()
            children = [
                BrowseMedia(
                    title=self._get_menu_title(favorite),
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"{MENU_PLAY_SYSTEM_FAVORITE}:{favorite.favorite_id}",
                    media_content_type=MediaType.MUSIC,
                    can_play=True,
                    can_expand=False,
                    thumbnail=favorite.album_cover_url,
                )
                for favorite in system_favorites
                if favorite.favorite_id > 0
            ]
        else:
            children = None

        return BrowseMedia(
            title=MENU_SYSTEM_FAVORITE_TITLE,
            media_class=MediaClass.DIRECTORY,
            media_content_id=MENU_SYSTEM_FAVORITE,
            media_content_type=MediaType.MUSIC,
            children_media_class=MediaClass.MUSIC,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        if media_type == MediaType.MUSIC:
            if MENU_PLAY_SYSTEM_FAVORITE in media_id:
                await self._zone.send_event("restoreSystemFavorite", media_id[11:])
            elif MENU_PLAY_ZONE_FAVORITE in media_id:
                await self._zone.send_event("restoreZoneFavorite", media_id[12:])
            else:
                _LOGGER.error(f"****** media_id: '{media_id}'")
        else:
            _LOGGER.error(f"****** media_type: '{media_type}'")

    async def async_media_next_track(self):
        """Next Track."""
        await self._zone.send_event("KeyRelease", "Next")

    async def async_media_previous_track(self):
        """Previous Track."""
        await self._zone.send_event("KeyRelease", "Previous")