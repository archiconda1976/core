"""Config flow for Monoprice Blackbird matrices."""

from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TYPE

from .const import (
    CONF_MODEL,
    CONF_SERIAL,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
    TYPE_SERIAL,
    TYPE_TCP,
)

MODELS = ("4x4", "8x8")

STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_TYPE, default=TYPE_TCP): vol.In((TYPE_TCP, TYPE_SERIAL))}
)

STEP_TCP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=4001): int,
        vol.Required(CONF_MODEL, default="8x8"): vol.In(MODELS),
    }
)

STEP_SERIAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_MODEL, default="8x8"): vol.In(MODELS),
    }
)


class BlackbirdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Monoprice Blackbird matrix."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial connection selection."""
        if user_input is not None:
            if user_input[CONF_TYPE] == TYPE_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a TCP-connected matrix."""
        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_TYPE: TYPE_TCP,
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                }
            )
            return self.async_create_entry(
                title=f"Monoprice Blackbird {user_input[CONF_MODEL]}",
                data={CONF_TYPE: TYPE_TCP, **user_input},
            )

        return self.async_show_form(step_id="tcp", data_schema=STEP_TCP_DATA_SCHEMA)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a serial-connected matrix."""
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_TYPE: TYPE_SERIAL, CONF_SERIAL: user_input[CONF_SERIAL]}
            )
            return self.async_create_entry(
                title=f"Monoprice Blackbird {user_input[CONF_MODEL]}",
                data={CONF_TYPE: TYPE_SERIAL, **user_input},
            )

        return self.async_show_form(
            step_id="serial", data_schema=STEP_SERIAL_DATA_SCHEMA
        )

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Import the legacy YAML configuration."""
        zones = _serialize_named_items(import_config.get(CONF_ZONES, {}))
        sources = _serialize_named_items(import_config.get(CONF_SOURCES, {}))
        highest_id = max(
            (int(item_id) for item_id in (*zones, *sources)),
            default=1,
        )
        model = "4x4" if highest_id <= 4 else "8x8"

        if CONF_PORT in import_config:
            data = {
                CONF_TYPE: TYPE_SERIAL,
                CONF_MODEL: model,
                CONF_SERIAL: import_config[CONF_PORT],
                CONF_ZONES: zones,
                CONF_SOURCES: sources,
            }
            self._async_abort_entries_match(
                {CONF_TYPE: TYPE_SERIAL, CONF_SERIAL: data[CONF_SERIAL]}
            )
        else:
            data = {
                CONF_TYPE: TYPE_TCP,
                CONF_MODEL: model,
                CONF_HOST: import_config[CONF_HOST],
                CONF_PORT: import_config.get(CONF_PORT, 4001),
                CONF_ZONES: zones,
                CONF_SOURCES: sources,
            }
            self._async_abort_entries_match(
                {
                    CONF_TYPE: TYPE_TCP,
                    CONF_HOST: data[CONF_HOST],
                    CONF_PORT: data[CONF_PORT],
                }
            )

        return self.async_create_entry(title=f"Monoprice Blackbird {model}", data=data)


def _serialize_named_items(
    items: dict[int | str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Serialize legacy YAML item identifiers for config-entry storage."""
    return {
        str(item_id): {CONF_NAME: item[CONF_NAME]} for item_id, item in items.items()
    }
