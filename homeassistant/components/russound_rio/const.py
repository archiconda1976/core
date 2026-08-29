"""Constants used for Russound RIO."""

import asyncio

from aiorussound import CommandError

DOMAIN = "russound_rio"

RUSSOUND_MEDIA_TYPE_PRESET = "preset"
RUSSOUND_MEDIA_TYPE_MEDIA_MANAGEMENT = "rio_media_management"

ATTR_FAVORITE_ID = "favorite_id"
ATTR_FAVORITE_NAME = "favorite_name"
ATTR_FAVORITE_SCOPE = "scope"
FAVORITE_SCOPE_SYSTEM = "system"
FAVORITE_SCOPE_ZONE = "zone"
SERVICE_RUSSOUND_DELETE_FAVORITE = "russound_delete_favorite"
SERVICE_RUSSOUND_RENAME_SYSTEM_FAVORITE = "russound_rename_system_favorite"
SERVICE_RUSSOUND_RESTORE_FAVORITE = "russound_restore_favorite"
SERVICE_RUSSOUND_SAVE_FAVORITE = "russound_save_favorite"

SELECT_SOURCE_DELAY = 0.5

RUSSOUND_RIO_EXCEPTIONS = (
    CommandError,
    ConnectionRefusedError,
    TimeoutError,
    asyncio.CancelledError,
)

CONF_BAUDRATE = "baudrate"
CONF_ZONE_SOURCE_EXCLUSION = "zone_source_exclusion"
TYPE_TCP = "tcp"
TYPE_SERIAL = "serial"
DEFAULT_BAUDRATE = 19200
DEFAULT_PORT = 9621
