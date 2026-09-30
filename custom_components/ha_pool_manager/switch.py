"""Schalter: Zeitplan-Automatik an/aus."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import PoolEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ScheduleEnabledSwitch(hass.data[DOMAIN][entry.entry_id])])


class ScheduleEnabledSwitch(PoolEntity, SwitchEntity, RestoreEntity):
    """Aktiviert bzw. deaktiviert die Zeitplan-Automatik der Pumpe."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, manager) -> None:
        super().__init__(manager, "schedule_enabled")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_OFF:
            self.manager.enabled = False

    @property
    def is_on(self) -> bool:
        return self.manager.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.manager.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.manager.async_set_enabled(False)
