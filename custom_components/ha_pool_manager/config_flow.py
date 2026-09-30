"""Config- und Options-Flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DAYS,
    CONF_END,
    CONF_PUMP_ENTITY,
    CONF_START,
    CONF_WINDOWS,
    DOMAIN,
    MAX_WINDOWS,
    WEEKDAYS,
)
from .schedule import describe_window, parse_time, parse_windows

_PUMP_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)


class PoolManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pool anlegen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PUMP_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input["name"],
                data={CONF_PUMP_ENTITY: user_input[CONF_PUMP_ENTITY]},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Pool"): str,
                    vol.Required(CONF_PUMP_ENTITY): _PUMP_SELECTOR,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PoolManagerOptionsFlow(config_entry)


class PoolManagerOptionsFlow(OptionsFlow):
    """Pumpe und Zeitfenster verwalten."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # Explizit speichern: `self._entry` wird von HA erst ab 2024.11 gesetzt
        self._entry = config_entry

    def _windows(self) -> list[dict[str, Any]]:
        return list(self._entry.options.get(CONF_WINDOWS, []))

    def _pump(self) -> str:
        return self._entry.options.get(
            CONF_PUMP_ENTITY, self._entry.data[CONF_PUMP_ENTITY]
        )

    def _save(self, *, pump: str | None = None, windows: list | None = None):
        return self.async_create_entry(
            data={
                CONF_PUMP_ENTITY: pump or self._pump(),
                CONF_WINDOWS: self._windows() if windows is None else windows,
            }
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        menu = ["pump", "add_window"]
        if self._windows():
            menu.append("remove_window")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_pump(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self._save(pump=user_input[CONF_PUMP_ENTITY])
        return self.async_show_form(
            step_id="pump",
            data_schema=vol.Schema(
                {vol.Required(CONF_PUMP_ENTITY, default=self._pump()): _PUMP_SELECTOR}
            ),
        )

    async def async_step_add_window(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        windows = self._windows()
        if user_input is not None:
            if len(windows) >= MAX_WINDOWS:
                errors["base"] = "too_many_windows"
            elif parse_time(user_input[CONF_START]) == parse_time(user_input[CONF_END]):
                errors["base"] = "start_equals_end"
            elif not user_input[CONF_DAYS]:
                errors[CONF_DAYS] = "no_days"
            else:
                windows.append(
                    {
                        CONF_START: user_input[CONF_START],
                        CONF_END: user_input[CONF_END],
                        CONF_DAYS: user_input[CONF_DAYS],
                    }
                )
                return self._save(windows=windows)

        return self.async_show_form(
            step_id="add_window",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_START, default="08:00:00"): selector.TimeSelector(),
                    vol.Required(CONF_END, default="10:00:00"): selector.TimeSelector(),
                    vol.Required(CONF_DAYS, default=list(WEEKDAYS)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(WEEKDAYS),
                            multiple=True,
                            translation_key="weekdays",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_remove_window(self, user_input: dict[str, Any] | None = None):
        windows = self._windows()
        if user_input is not None:
            drop = {int(i) for i in user_input["remove"]}
            return self._save(
                windows=[w for i, w in enumerate(windows) if i not in drop]
            )

        options = []
        for index, raw in enumerate(windows):
            window = next(iter(parse_windows([raw])), None)
            label = describe_window(window, self.hass.config.language) if window else str(raw)
            options.append(selector.SelectOptionDict(value=str(index), label=label))
        return self.async_show_form(
            step_id="remove_window",
            data_schema=vol.Schema(
                {
                    vol.Required("remove"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
        )
