"""Tests for the Monoprice Blackbird media player integration."""

from collections import defaultdict
from collections.abc import Generator
from unittest.mock import ANY, AsyncMock, patch

import pytest
import voluptuous as vol

from homeassistant.components.blackbird.const import (
    CONF_MODEL,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
    MODEL_4X4,
    MODEL_4X4_LEGACY,
    SERVICE_SETALLZONES,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.components.blackbird.media_player import PLATFORM_SCHEMA
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TYPE, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry


class AttrDict(dict):
    """Helper class for mocking attributes."""

    def __getattr__(self, item):
        """Return dictionary items as attributes."""
        return self[item]


class MockBlackbird:
    """Mock for the pyblackbird client."""

    def __init__(self) -> None:
        """Initialize matrix state."""
        self.zones = defaultdict(lambda: AttrDict(power=True, av=1))

    def zone_status(self, zone_id):
        """Return a zone's state."""
        status = self.zones[zone_id]
        status.zone = zone_id
        return AttrDict(status)

    def set_zone_source(self, zone_id, source_idx):
        """Set a zone's source."""
        self.zones[zone_id].av = source_idx

    def set_zone_power(self, zone_id, power):
        """Set a zone's power."""
        self.zones[zone_id].power = power

    def set_all_zone_source(self, source_idx):
        """Set all zones' source."""
        for zone in self.zones.values():
            zone.av = source_idx


CONFIG_ENTRY_DATA = {
    CONF_TYPE: TYPE_TCP,
    CONF_HOST: "192.0.2.1",
    CONF_PORT: 4001,
    CONF_MODEL: MODEL_4X4,
    CONF_ZONES: {"1": {"name": "Kitchen"}},
    CONF_SOURCES: {"1": {"name": "Streaming"}, "2": {"name": "TV"}},
}


@pytest.fixture
def mock_blackbird() -> MockBlackbird:
    """Return a mock Blackbird client."""
    return MockBlackbird()


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent config-flow tests from setting up a live matrix."""
    with patch(
        "homeassistant.components.blackbird.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a Blackbird config entry."""
    return MockConfigEntry(domain=DOMAIN, data=CONFIG_ENTRY_DATA)


def test_valid_serial_schema() -> None:
    """Test valid serial YAML schema."""
    PLATFORM_SCHEMA(
        {
            "platform": DOMAIN,
            "port": "/dev/ttyUSB0",
            "zones": {1: {"name": "Kitchen"}},
            "sources": {1: {"name": "Streaming"}},
        }
    )


def test_valid_socket_schema() -> None:
    """Test valid socket YAML schema."""
    PLATFORM_SCHEMA(
        {
            "platform": DOMAIN,
            "host": "192.0.2.1",
            "zones": {1: {"name": "Kitchen"}},
            "sources": {1: {"name": "Streaming"}},
        }
    )


def test_valid_legacy_socket_schema() -> None:
    """Test valid legacy 4x4 socket YAML schema."""
    PLATFORM_SCHEMA(
        {
            "platform": DOMAIN,
            "host": "192.0.2.1",
            "type": 1,
            "zones": {1: {"name": "Kitchen"}},
            "sources": {1: {"name": "Streaming"}},
        }
    )


def test_invalid_schema() -> None:
    """Test invalid YAML schema."""
    with pytest.raises(vol.MultipleInvalid):
        PLATFORM_SCHEMA({"platform": DOMAIN})


async def test_setup_entry(
    hass: HomeAssistant,
    mock_blackbird: MockBlackbird,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test config-entry setup creates the profile's zones."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.blackbird.get_blackbird",
        return_value=mock_blackbird,
    ) as get_blackbird:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    get_blackbird.assert_called_once_with("192.0.2.1", False, ANY, 4001)
    assert hass.states.get("media_player.kitchen").state == STATE_ON
    assert hass.states.get("media_player.zone_2").state == STATE_ON
    assert hass.states.get("media_player.kitchen").attributes["source"] == "Streaming"


async def test_set_all_zones_service(
    hass: HomeAssistant,
    mock_blackbird: MockBlackbird,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test set_all_zones is registered for config-entry entities."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.blackbird.get_blackbird",
        return_value=mock_blackbird,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SETALLZONES)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SETALLZONES,
        {"entity_id": "media_player.kitchen", "source": "TV"},
        blocking=True,
    )
    assert mock_blackbird.zones[1].av == 2


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_tcp(hass: HomeAssistant) -> None:
    """Test a TCP configuration flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_TYPE: TYPE_TCP}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tcp"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 4001,
            CONF_MODEL: MODEL_4X4,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_TYPE: TYPE_TCP,
        CONF_HOST: "192.0.2.1",
        CONF_PORT: 4001,
        CONF_MODEL: MODEL_4X4,
    }


@pytest.mark.usefixtures("mock_setup_entry")
async def test_import_flow_serial_preserves_names(hass: HomeAssistant) -> None:
    """Test the YAML import creates a serial config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_PORT: "/dev/ttyUSB0",
            CONF_ZONES: {1: {"name": "Kitchen"}},
            CONF_SOURCES: {1: {"name": "Streaming"}},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_TYPE: TYPE_SERIAL,
        CONF_MODEL: MODEL_4X4,
        "serial": "/dev/ttyUSB0",
        CONF_ZONES: {"1": {"name": "Kitchen"}},
        CONF_SOURCES: {"1": {"name": "Streaming"}},
    }


async def test_import_flow_duplicate(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the YAML import detects an existing matrix."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=CONFIG_ENTRY_DATA
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_import_flow_legacy_4x4_uses_legacy_tcp_port(
    hass: HomeAssistant,
) -> None:
    """Test legacy YAML type 1 selects the PID 15779 transport."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_HOST: "192.0.2.1",
            CONF_TYPE: 1,
            CONF_ZONES: {1: {"name": "Kitchen"}},
            CONF_SOURCES: {1: {"name": "Streaming"}},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_TYPE: TYPE_TCP,
        CONF_MODEL: MODEL_4X4_LEGACY,
        CONF_HOST: "192.0.2.1",
        CONF_PORT: 23,
        CONF_ZONES: {"1": {"name": "Kitchen"}},
        CONF_SOURCES: {"1": {"name": "Streaming"}},
    }


async def test_entry_offline_is_retried(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a connection failure marks the entry for setup retry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.blackbird.get_blackbird",
        side_effect=OSError,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state.value == "setup_retry"


async def test_zone_state_updates(
    hass: HomeAssistant,
    mock_blackbird: MockBlackbird,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test entity state changes reflect the matrix state."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.blackbird.get_blackbird",
        return_value=mock_blackbird,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    mock_blackbird.zones[1].power = False
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": "media_player.kitchen"},
        blocking=True,
    )
    assert hass.states.get("media_player.kitchen").state == STATE_OFF
