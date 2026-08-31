"""Support for Russound multizone controllers using RIO Protocol."""

import asyncio
import datetime as dt
import logging
from typing import TYPE_CHECKING, Any, override

from aiorussound.const import FeatureFlag
from aiorussound.rio import Controller, Source
from aiorussound.rio.models import PlayStatus
from aiorussound.util import is_feature_supported
import voluptuous as vol

from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RussoundConfigEntry, media_browser
from .const import (
    ATTR_FAVORITE_ID,
    ATTR_FAVORITE_NAME,
    ATTR_FAVORITE_SCOPE,
    CONF_ZONE_SOURCE_EXCLUSION,
    DOMAIN,
    FAVORITE_SCOPE_SYSTEM,
    FAVORITE_SCOPE_ZONE,
    RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
    RUSSOUND_MEDIA_TYPE_PRESET,
    SELECT_SOURCE_DELAY,
    SERVICE_RUSSOUND_DELETE_FAVORITE,
    SERVICE_RUSSOUND_RENAME_SYSTEM_FAVORITE,
    SERVICE_RUSSOUND_RESTORE_FAVORITE,
    SERVICE_RUSSOUND_SAVE_FAVORITE,
)
from .entity import RussoundBaseEntity, command

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

FAVORITE_SCOPE_SCHEMA = vol.In((FAVORITE_SCOPE_SYSTEM, FAVORITE_SCOPE_ZONE))
FAVORITE_ID_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=32))
FAVORITE_NAME_SCHEMA = vol.All(cv.string, vol.Length(min=1, max=50))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RussoundConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Russound RIO platform."""
    client = entry.runtime_data
    sources = client.sources

    zone_source_exclusion = entry.options.get(
        CONF_ZONE_SOURCE_EXCLUSION,
        True,
    )

    async_add_entities(
        RussoundZoneDevice(
            hass, controller, entry, zone_id, sources, zone_source_exclusion
        )
        for controller in client.controllers.values()
        for zone_id in controller.zones
    )

    if hass.services.has_service(MEDIA_PLAYER_DOMAIN, SERVICE_RUSSOUND_SAVE_FAVORITE):
        return

    platform = entity_platform.async_get_current_platform()
    favorite_schema = {
        vol.Required(ATTR_FAVORITE_ID): FAVORITE_ID_SCHEMA,
        vol.Required(ATTR_FAVORITE_SCOPE): FAVORITE_SCOPE_SCHEMA,
    }
    platform.async_register_entity_service(
        SERVICE_RUSSOUND_SAVE_FAVORITE,
        {**favorite_schema, vol.Required(ATTR_FAVORITE_NAME): FAVORITE_NAME_SCHEMA},
        "async_save_favorite",
    )
    platform.async_register_entity_service(
        SERVICE_RUSSOUND_RESTORE_FAVORITE,
        favorite_schema,
        "async_restore_favorite",
    )
    platform.async_register_entity_service(
        SERVICE_RUSSOUND_DELETE_FAVORITE,
        favorite_schema,
        "async_delete_favorite",
    )
    platform.async_register_entity_service(
        SERVICE_RUSSOUND_RENAME_SYSTEM_FAVORITE,
        {
            vol.Required(ATTR_FAVORITE_ID): FAVORITE_ID_SCHEMA,
            vol.Required(ATTR_FAVORITE_NAME): FAVORITE_NAME_SCHEMA,
        },
        "async_rename_system_favorite",
    )


def _parse_preset_source_id(media_id: str) -> tuple[int | None, int]:
    source_id = None
    if "," in media_id:
        source_id_str, preset_id_str = media_id.split(",", maxsplit=1)
        source_id = int(source_id_str.strip())
        preset_id = int(preset_id_str.strip())
    else:
        preset_id = int(media_id)
    return source_id, preset_id


class RussoundZoneDevice(RussoundBaseEntity, MediaPlayerEntity):
    """Representation of a Russound Zone."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _BASE_SUPPORTED_FEATURES = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        controller: Controller,
        entry: RussoundConfigEntry,
        zone_id: int,
        sources: dict[int, Source],
        zone_source_exclusion: bool,
    ) -> None:
        """Initialize the zone device."""
        super().__init__(hass, controller, entry, zone_id)
        _zone = self._zone
        self._sources = sources
        self._attr_unique_id = f"{self._primary_mac_address}-{_zone.device_str}"
        self._zone_source_exclusion = zone_source_exclusion

    @property
    def _source(self) -> Source:
        return self._zone.fetch_current_source()

    @property
    @override
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        status = self._zone.status
        play_status = self._source.play_status
        if not status:
            return MediaPlayerState.OFF
        if play_status == PlayStatus.PLAYING:
            return MediaPlayerState.PLAYING
        if play_status == PlayStatus.PAUSED:
            return MediaPlayerState.PAUSED
        if play_status == PlayStatus.TRANSITIONING:
            return MediaPlayerState.BUFFERING
        if play_status == PlayStatus.STOPPED:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    @override
    def source(self) -> str:
        """Get the currently selected source."""
        return self._source.name

    @property
    @override
    def source_list(self) -> list[str]:
        """Return a list of available input sources."""
        if TYPE_CHECKING:
            assert self._client.rio_version
        available_sources = (
            [
                source
                for source_id, source in self._sources.items()
                if source_id in self._zone.enabled_sources
            ]
            if (
                is_feature_supported(
                    self._client.rio_version, FeatureFlag.SUPPORT_ZONE_SOURCE_EXCLUSION
                )
                and self._zone_source_exclusion
            )
            else self._sources.values()
        )
        return [x.name for x in available_sources]

    @property
    @override
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self._source.song_name or self._source.channel

    @property
    @override
    def media_artist(self) -> str | None:
        """Artist of current playing media, music track only."""
        return self._source.artist_name

    @property
    @override
    def media_album_name(self) -> str | None:
        """Album name of current playing media."""
        return self._source.album_name

    @property
    @override
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        return self._source.cover_art_url

    @property
    @override
    def media_duration(self) -> int | None:
        """Duration of the current media."""
        return self._source.track_time

    @property
    @override
    def media_position(self) -> int | None:
        """Position of the current media."""
        return self._source.play_time

    @property
    @override
    def media_position_updated_at(self) -> dt.datetime:
        """Last time the media position was updated."""
        return self._source.position_last_updated

    @property
    @override
    def volume_level(self) -> float:
        """Return the volume level."""
        return self._zone.volume / 50.0

    @property
    @override
    def is_volume_muted(self) -> bool:
        """Return whether zone is muted."""
        return self._zone.is_mute

    @command
    @override
    async def async_turn_off(self) -> None:
        """Turn off the zone."""
        await self._zone.zone_off()

    @command
    @override
    async def async_turn_on(self) -> None:
        """Turn on the zone."""
        await self._zone.zone_on()

    @command
    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level."""
        rvol = int(volume * 50.0)
        await self._zone.set_volume(str(rvol))

    @command
    @override
    async def async_select_source(self, source: str) -> None:
        """Select the source input for this zone."""
        for source_id, src in self._sources.items():
            if src.name.lower() != source.lower():
                continue
            await self._zone.select_source(source_id)
            break

    @command
    @override
    async def async_volume_up(self) -> None:
        """Step the volume up."""
        await self._zone.volume_up()

    @command
    @override
    async def async_volume_down(self) -> None:
        """Step the volume down."""
        await self._zone.volume_down()

    @command
    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if FeatureFlag.COMMANDS_ZONE_MUTE_OFF_ON in self._client.supported_features:
            if mute:
                await self._zone.mute()
            else:
                await self._zone.unmute()
            return

        if mute != self.is_volume_muted:
            await self._zone.toggle_mute()

    @command
    @override
    async def async_media_seek(self, position: float) -> None:
        """Seek to a position in the current media."""
        await self._zone.set_seek_time(int(position))

    @command
    @override
    async def async_media_play(self) -> None:
        """Resume playback on a Russound media streamer."""
        await self._zone.play()

    @command
    @override
    async def async_media_pause(self) -> None:
        """Pause playback on a Russound media streamer."""
        await self._zone.pause()

    @command
    @override
    async def async_media_stop(self) -> None:
        """Stop playback on a Russound media streamer."""
        await self._zone.stop()

    @command
    @override
    async def async_media_previous_track(self) -> None:
        """Skip to the previous item on a Russound media streamer."""
        await self._zone.previous()

    @command
    @override
    async def async_media_next_track(self) -> None:
        """Skip to the next item on a Russound media streamer."""
        await self._zone.next()

    @command
    async def async_save_favorite(
        self, favorite_id: int, scope: str, favorite_name: str
    ) -> None:
        """Save the current source as a named Russound favorite."""
        if scope == FAVORITE_SCOPE_SYSTEM:
            await self._zone.save_system_favorite(favorite_id, favorite_name)
        else:
            await self._zone.save_zone_favorite(favorite_id, favorite_name)

    @command
    async def async_restore_favorite(self, favorite_id: int, scope: str) -> None:
        """Restore a Russound favorite in this zone."""
        if scope == FAVORITE_SCOPE_SYSTEM:
            await self._zone.restore_system_favorite(favorite_id)
        else:
            await self._zone.restore_zone_favorite(favorite_id)

    @command
    async def async_delete_favorite(self, favorite_id: int, scope: str) -> None:
        """Delete a Russound favorite."""
        if scope == FAVORITE_SCOPE_SYSTEM:
            await self._zone.delete_system_favorite(favorite_id)
        else:
            await self._zone.delete_zone_favorite(favorite_id)

    @command
    async def async_rename_system_favorite(
        self, favorite_id: int, favorite_name: str
    ) -> None:
        """Rename a system-wide Russound favorite."""
        await self._client.rename_system_favorite(favorite_id, favorite_name)

    @command
    @override
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media on the Russound zone."""

        if media_type == RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT:
            try:
                await media_browser.async_play_media_management(self._zone, media_id)
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_media_management_path",
                    translation_placeholders={"media_id": media_id},
                ) from err
            return

        if media_type != RUSSOUND_MEDIA_TYPE_PRESET:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsupported_media_type",
                translation_placeholders={
                    "media_type": media_type,
                },
            )

        try:
            source_id, preset_id = _parse_preset_source_id(media_id)
        except ValueError as ve:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="preset_non_integer",
                translation_placeholders={"preset_id": media_id},
            ) from ve
        if source_id:
            await self._zone.select_source(source_id)
            await asyncio.sleep(SELECT_SOURCE_DELAY)
        if not self._source.presets or preset_id not in self._source.presets:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_preset",
                translation_placeholders={"preset_id": media_id},
            )
        await self._zone.restore_preset(preset_id)

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement the media browsing helper."""
        return await media_browser.async_browse_media(
            self.hass, self._client, media_content_id, media_content_type, self._zone
        )
