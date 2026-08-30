"""The Blackbird integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from pyblackbird import get_blackbird
from pyblackbird.profiles import BLACKBIRD_4X4, BLACKBIRD_8X8
from pyblackbird.profiles import BLACKBIRD_4X4_LEGACY
from serial import SerialException

from .const import CONF_MODEL, CONF_SERIAL, MODEL_4X4_LEGACY, TYPE_SERIAL

PLATFORMS = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Blackbird from a config entry."""
    data = entry.data
    profile = (
        BLACKBIRD_4X4_LEGACY
        if data[CONF_MODEL] == MODEL_4X4_LEGACY
        else BLACKBIRD_4X4 if data[CONF_MODEL] == "4x4" else BLACKBIRD_8X8
    )
    use_serial = data["type"] == TYPE_SERIAL
    address = data[CONF_SERIAL] if use_serial else data["host"]
    try:
        entry.runtime_data = await hass.async_add_executor_job(
            get_blackbird, address, use_serial, profile, data.get("port", 4001)
        )
    except (OSError, SerialException, TimeoutError) as err:
        raise ConfigEntryNotReady from err
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Blackbird config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
