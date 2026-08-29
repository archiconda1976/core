"""Tests for the Russound RIO media browser."""

from unittest.mock import AsyncMock, Mock, call

from aiorussound.rio import MediaManagementMenuItem, MediaManagementMenuPage
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.russound_rio import media_browser
from homeassistant.components.russound_rio.const import (
    RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
)
from homeassistant.core import HomeAssistant

from . import setup_integration
from .const import ENTITY_ID_ZONE_1

from tests.common import MockConfigEntry
from tests.typing import WebSocketGenerator


async def test_browse_media_root(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_russound_client: AsyncMock,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the root browse page."""
    await setup_integration(hass, mock_config_entry)

    client = await hass_ws_client()
    await client.send_json(
        {
            "id": 1,
            "type": "media_player/browse_media",
            "entity_id": ENTITY_ID_ZONE_1,
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["children"] == snapshot


async def test_browse_media_management(
    hass: HomeAssistant, mock_russound_client: AsyncMock
) -> None:
    """Test browsing a controller-routed Media Management page."""
    zone = mock_russound_client.controllers[1].zones[1]
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.initialize.return_value = MediaManagementMenuPage(
        total_items=2,
        num_items=2,
        menu_items=(
            MediaManagementMenuItem(item_id=1, text="Albums", is_menu=True),
            MediaManagementMenuItem(
                item_id=2,
                text="Song",
                is_menu=False,
                image_url="https://example.com/song.jpg",
            ),
        ),
    )
    zone.create_media_management_session = Mock(return_value=session)

    result = await media_browser.async_browse_media(
        hass,
        mock_russound_client,
        "",
        RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT,
        zone,
    )

    assert result.title == "Browse Music"
    assert [(child.title, child.media_content_id) for child in result.children] == [
        ("Albums", "1"),
        ("Song", "2"),
    ]
    assert result.children[0].can_expand
    assert result.children[1].can_play
    assert result.children[1].thumbnail == "https://example.com/song.jpg"
    session.initialize.assert_awaited_once()


async def test_play_media_management_replays_menu_path(
    mock_russound_client: AsyncMock,
) -> None:
    """Test selecting a Media Management item from a stateless browse path."""
    zone = mock_russound_client.controllers[1].zones[1]
    session = AsyncMock()
    session.__aenter__.return_value = session
    zone.create_media_management_session = Mock(return_value=session)

    await media_browser.async_play_media_management(zone, "3/7")

    session.initialize.assert_awaited_once()
    assert session.select_item.await_args_list == [
        call(3),
        call(7, expect_page=False),
    ]


async def test_browse_presets(
    hass: HomeAssistant,
    mock_russound_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the presets browse page."""
    await setup_integration(hass, mock_config_entry)

    client = await hass_ws_client()
    await client.send_json(
        {
            "id": 1,
            "type": "media_player/browse_media",
            "entity_id": ENTITY_ID_ZONE_1,
            "media_content_type": "presets",
            "media_content_id": "",
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["children"] == snapshot
