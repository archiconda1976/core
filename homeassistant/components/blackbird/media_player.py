"""Support for interfacing with Monoprice Blackbird 4k 8x8 HDBaseT Matrix."""

import logging
from typing import override

from pyblackbird.profiles import BLACKBIRD_4X4, BLACKBIRD_8X8
from pyblackbird.profiles import BLACKBIRD_4X4_LEGACY
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    CONF_MODEL,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
    MODEL_4X4_LEGACY,
    SERVICE_SETALLZONES,
)

_LOGGER = logging.getLogger(__name__)

ZONE_SCHEMA = vol.Schema({vol.Required(CONF_NAME): cv.string})

SOURCE_SCHEMA = vol.Schema({vol.Required(CONF_NAME): cv.string})

ATTR_SOURCE = "source"

# Valid zone ids: 1-8
ZONE_IDS = vol.All(vol.Coerce(int), vol.Range(min=1, max=8))

# Valid source ids: 1-8
SOURCE_IDS = vol.All(vol.Coerce(int), vol.Range(min=1, max=8))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Blackbird zones from a config entry."""
    data = entry.data
    profile = (
        BLACKBIRD_4X4_LEGACY
        if data[CONF_MODEL] == MODEL_4X4_LEGACY
        else BLACKBIRD_4X4 if data[CONF_MODEL] == "4x4" else BLACKBIRD_8X8
    )
    blackbird = entry.runtime_data

    sources = {
        source_id: _item_name(
            data.get(CONF_SOURCES, {}), source_id, f"Input {source_id}"
        )
        for source_id in range(1, profile.sources + 1)
    }
    async_add_entities(
        [
            BlackbirdZone(
                blackbird,
                sources,
                zone_id,
                _item_name(data.get(CONF_ZONES, {}), zone_id, f"Zone {zone_id}"),
                f"{entry.entry_id}-{zone_id}",
            )
            for zone_id in range(1, profile.zones + 1)
        ],
        update_before_add=True,
    )

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SETALLZONES,
        {vol.Required(ATTR_SOURCE): cv.string},
        "set_all_zones",
    )


def _item_name(items: dict[str, dict[str, str]], item_id: int, default: str) -> str:
    """Return a named item from config-entry or unconverted YAML data."""
    return items.get(str(item_id), items.get(item_id, {})).get(CONF_NAME, default)


PLATFORM_SCHEMA = vol.All(
    cv.has_at_least_one_key(CONF_PORT, CONF_HOST),
    MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
        {
            vol.Exclusive(CONF_PORT, "connection"): cv.string,
            vol.Exclusive(CONF_HOST, "connection"): cv.string,
            vol.Optional(CONF_TYPE): vol.In((0, 1)),
            vol.Required(CONF_ZONES): vol.Schema({ZONE_IDS: ZONE_SCHEMA}),
            vol.Required(CONF_SOURCES): vol.Schema({SOURCE_IDS: SOURCE_SCHEMA}),
        }
    ),
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import the legacy YAML platform into a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=config
    )
    if (
        result.get("type") is FlowResultType.ABORT
        and result.get("reason") != "already_configured"
    ):
        _LOGGER.error(
            "Unable to import Blackbird YAML configuration: %s", result.get("reason")
        )


class BlackbirdZone(MediaPlayerEntity):
    """Representation of a Blackbird matrix zone."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, blackbird, sources, zone_id, zone_name, unique_id):
        """Initialize new zone."""
        self._blackbird = blackbird
        # dict source_id -> source name
        self._source_id_name = sources
        # dict source name -> source_id
        self._source_name_id = {v: k for k, v in sources.items()}
        # ordered list of all source names
        self._attr_source_list = sorted(
            self._source_name_id.keys(), key=lambda v: self._source_name_id[v]
        )
        self._zone_id = zone_id
        self._attr_name = zone_name
        self._attr_unique_id = unique_id

    def update(self) -> None:
        """Retrieve latest state."""
        state = self._blackbird.zone_status(self._zone_id)
        if not state:
            return
        self._attr_state = MediaPlayerState.ON if state.power else MediaPlayerState.OFF
        idx = state.av
        self._attr_source = self._source_id_name.get(idx)

    @property
    @override
    def media_title(self):
        """Return the current source as media title."""
        return self.source

    def set_all_zones(self, source):
        """Set all zones to one source."""
        if source not in self._source_name_id:
            return
        idx = self._source_name_id[source]
        _LOGGER.debug("Setting all zones source to %s", idx)
        self._blackbird.set_all_zone_source(idx)

    @override
    def select_source(self, source: str) -> None:
        """Set input source."""
        if source not in self._source_name_id:
            return
        idx = self._source_name_id[source]
        _LOGGER.debug("Setting zone %d source to %s", self._zone_id, idx)
        self._blackbird.set_zone_source(self._zone_id, idx)

    @override
    def turn_on(self) -> None:
        """Turn the media player on."""
        _LOGGER.debug("Turning zone %d on", self._zone_id)
        self._blackbird.set_zone_power(self._zone_id, True)

    @override
    def turn_off(self) -> None:
        """Turn the media player off."""
        _LOGGER.debug("Turning zone %d off", self._zone_id)
        self._blackbird.set_zone_power(self._zone_id, False)
