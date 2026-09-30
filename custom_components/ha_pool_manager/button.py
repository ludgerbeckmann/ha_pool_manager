"""Button: Trockenlauf-Alarm quittieren."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PoolEntity, remove_unconfigured


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    if manager.dry_run_configured:
        async_add_entities([DryRunAcknowledgeButton(manager)])
    else:
        remove_unconfigured(hass, "button", manager, "dry_run_acknowledge")


class DryRunAcknowledgeButton(PoolEntity, ButtonEntity):
    """Quittiert den Alarm und gibt einen pausierten Zeitplan wieder frei."""

    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, manager) -> None:
        super().__init__(manager, "dry_run_acknowledge")

    async def async_press(self) -> None:
        await self.manager.async_acknowledge_dry_run()
