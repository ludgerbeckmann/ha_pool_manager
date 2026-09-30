"""Binärsensor: Soll die Pumpe laut Zeitplan laufen?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PoolEntity, remove_unconfigured


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    entities: list[PoolEntity] = [PumpShouldRunSensor(manager)]
    if manager.dry_run_configured:
        entities.append(DryRunSensor(manager))
    else:
        remove_unconfigured(hass, "binary_sensor", manager, "dry_run_detected")
    async_add_entities(entities)


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


class DryRunSensor(PoolEntity, BinarySensorEntity):
    """on = Trockenlauf erkannt (bleibt gehalten, bis quittiert oder Pumpe neu gestartet)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager) -> None:
        super().__init__(manager, "dry_run_detected")

    @property
    def is_on(self) -> bool:
        return self.manager.dry_run_detected

    @property
    def icon(self) -> str:
        return "mdi:water-alert" if self.is_on else "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict:
        since = self.manager.dry_run_since
        return {
            "leistung": self.manager.current_power(),
            "seit": since.isoformat() if since else None,
            "zeitplan_pausiert": self.manager.dry_run_paused_schedule,
            "automatisch_ausschalten": self.manager.dry_auto_off,
            "leistungssensor": self.manager.power_entity,
        }
