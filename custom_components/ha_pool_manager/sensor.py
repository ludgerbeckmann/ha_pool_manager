"""Sensoren: nächster Start und Laufzeit heute."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PoolEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NextStartSensor(manager), RuntimeTodaySensor(manager)])


class NextStartSensor(PoolEntity, SensorEntity):
    """Nächster geplanter Pumpenstart."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"

    def __init__(self, manager) -> None:
        super().__init__(manager, "next_start")

    @property
    def native_value(self) -> datetime | None:
        return self.manager.next_start


class RuntimeTodaySensor(PoolEntity, SensorEntity):
    """Bisherige Pumpenlaufzeit des heutigen Tages."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    def __init__(self, manager) -> None:
        super().__init__(manager, "runtime_today")

    @property
    def native_value(self) -> float:
        return self.manager.runtime_today_minutes()
