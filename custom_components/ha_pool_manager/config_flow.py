"""Config- und Options-Flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DAYS,
    CONF_DRY_AUTO_OFF,
    CONF_DRY_DURATION,
    CONF_DRY_MAX_POWER,
    CONF_DRY_MIN_POWER,
    CONF_END,
    CONF_POWER_ENTITY,
    CONF_PUMP_ENTITY,
    CONF_START,
    CONF_WINDOWS,
    DEFAULT_DRY_DURATION,
    DEFAULT_DRY_MAX_POWER,
    DEFAULT_DRY_MIN_POWER,
    DOMAIN,
    MAX_WINDOWS,
    WEEKDAYS,
)
from .schedule import describe_window, parse_time, parse_windows

_PUMP_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)


_DRY_KEYS = (
    CONF_POWER_ENTITY,
    CONF_DRY_MIN_POWER,
    CONF_DRY_MAX_POWER,
    CONF_DRY_DURATION,
    CONF_DRY_AUTO_OFF,
)


def _number(minimum: float, maximum: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step="any",
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
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

    def _save(self, **changes: Any):
        """Optionen speichern; nicht genannte Werte bleiben erhalten."""
        data = dict(self._entry.options)
        data.setdefault(CONF_PUMP_ENTITY, self._pump())
        data.setdefault(CONF_WINDOWS, [])
        data.update(changes)
        return self.async_create_entry(data=data)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        menu = ["pump", "add_window"]
        if self._windows():
            menu.append("remove_window")
        menu.append("dry_run")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_pump(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self._save(**{CONF_PUMP_ENTITY: user_input[CONF_PUMP_ENTITY]})
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
                return self._save(**{CONF_WINDOWS: windows})

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
                **{CONF_WINDOWS: [w for i, w in enumerate(windows) if i not in drop]}
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

    async def async_step_dry_run(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current = self._entry.options
        if user_input is not None:
            changes = {k: v for k, v in user_input.items() if k in _DRY_KEYS}
            if not user_input.get(CONF_POWER_ENTITY):
                # Kein Leistungssensor: Trockenlauferkennung aus
                data = {k: v for k, v in self._entry.options.items() if k not in _DRY_KEYS}
                return self._save_replace(data)
            if user_input[CONF_DRY_MIN_POWER] >= user_input[CONF_DRY_MAX_POWER]:
                errors["base"] = "min_ge_max"
            else:
                return self._save(**changes)

        power = user_input.get(CONF_POWER_ENTITY) if user_input else current.get(CONF_POWER_ENTITY)
        power_key = (
            vol.Optional(CONF_POWER_ENTITY, description={"suggested_value": power})
            if power
            else vol.Optional(CONF_POWER_ENTITY)
        )
        return self.async_show_form(
            step_id="dry_run",
            errors=errors,
            data_schema=vol.Schema(
                {
                    power_key: selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor", device_class="power"
                        )
                    ),
                    vol.Required(
                        CONF_DRY_MIN_POWER,
                        default=current.get(CONF_DRY_MIN_POWER, DEFAULT_DRY_MIN_POWER),
                    ): _number(0, 100000, "W"),
                    vol.Required(
                        CONF_DRY_MAX_POWER,
                        default=current.get(CONF_DRY_MAX_POWER, DEFAULT_DRY_MAX_POWER),
                    ): _number(0, 100000, "W"),
                    vol.Required(
                        CONF_DRY_DURATION,
                        default=current.get(CONF_DRY_DURATION, DEFAULT_DRY_DURATION),
                    ): _number(1, 120, "min"),
                    vol.Required(
                        CONF_DRY_AUTO_OFF,
                        default=current.get(CONF_DRY_AUTO_OFF, False),
                    ): selector.BooleanSelector(),
                }
            ),
        )

    def _save_replace(self, data: dict[str, Any]):
        """Optionen exakt durch `data` ersetzen (zum Entfernen von Werten)."""
        return self.async_create_entry(data=data)
