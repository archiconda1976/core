"""Constants used for Russound RIO."""

import asyncio

from aiorussound import CommandError
from aiorussound.const import FeatureFlag

from homeassistant.components.media_player import MediaPlayerEntityFeature

DOMAIN = "russound_rio"

RUSSOUND_RIO_EXCEPTIONS = (
    CommandError,
    ConnectionRefusedError,
    TimeoutError,
    asyncio.CancelledError,
)


CONNECT_TIMEOUT = 5

MP_FEATURES_BY_FLAG = {
    FeatureFlag.COMMANDS_ZONE_MUTE_OFF_ON: MediaPlayerEntityFeature.VOLUME_MUTE
}

MENU_SYSTEM_FAVORITE_TITLE = "System Favorites"
MENU_SYSTEM_FAVORITE = "system"
MENU_PLAY_SYSTEM_FAVORITE = "PlaySysFav"
MENU_ZONE_FAVORITE_TITLE = "Zone Favorites"
MENU_ZONE_FAVORITE = "zone"
MENU_PLAY_ZONE_FAVORITE = "PlayZoneFav"
RUSSOUND_MEDIA_TITLE = "Russound Media Source Options"

SERVICE_CALL_ATTR_FAVORITE_ID = "favorite_id"
SERVICE_CALL_ATTR_ENTITY_ID = "entity_id"
SERVICE_CALL_ATTR_FAVORITE_NAME = "name"
SERVICE_SAVE_SYSTEM_FAVORITE = "save_system_favorite"
SERVICE_SAVE_ZONE_FAVORITE = "save_zone_favorite"
SERVICE_DELETE_SYSTEM_FAVORITE = "delete_system_favorite"
SERVICE_DELETE_ZONE_FAVORITE = "delete_zone_favorite"
SERVICE_CHANGE_TO_SYSTEM_FAVORITE = "restore_system_favorite"
SERVICE_CHANGE_TO_ZONE_FAVORITE = "restore_zone_favorite"
