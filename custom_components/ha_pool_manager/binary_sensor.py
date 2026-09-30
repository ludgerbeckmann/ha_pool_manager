"""Binärsensor: Soll die Pumpe laut Zeitplan laufen?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PoolEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PumpShouldRunSensor(hass.data[DOMAIN][entry.entry_id])])


class PumpShouldRunSensor(PoolEntity, BinarySensorEntity):
    """on = die Pumpe soll laut Zeitplan bzw. manuellem Lauf laufen."""

    def __init__(self, manager) -> None:
        super().__init__(manager, "pump_should_run")

    @property
    def is_on(self) -> bool:
        return self.manager.should_run

    @property
    def icon(self) -> str:
        return "mdi:pump" if self.is_on else "mdi:pump-off"

    @property
    def extra_state_attributes(self) -> dict:
        manual = self.manager.manual_until
        return {
            "zeitplan_aktiv": self.manager.enabled,
            "im_zeitfenster": self.manager.schedule_active,
            "manueller_lauf_bis": manual.isoformat() if self.manager.manual_active else None,
            "pumpe": self.manager.pump_entity,
        }
