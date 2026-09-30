"""Gemeinsame Basisklasse der Entitäten."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .manager import PoolManager


class PoolEntity(Entity):
    """Entität, die bei jeder Änderung des Managers neu gerendert wird."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: PoolManager, key: str) -> None:
        self.manager = manager
        self._attr_translation_key = key
        self._attr_unique_id = f"{manager.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name=manager.entry.title,
            manufacturer="Pool Manager",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(self.manager.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


def remove_unconfigured(hass: HomeAssistant, platform: str, manager: PoolManager, key: str) -> None:
    """Entität aus der Registry entfernen, wenn ihre Funktion nicht (mehr) konfiguriert ist."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        platform, DOMAIN, f"{manager.entry.entry_id}_{key}"
    )
    if entity_id:
        registry.async_remove(entity_id)
