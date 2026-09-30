"""Pool Manager - Funktionen zur Nutzung eines Pools in Home Assistant."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_DURATION, ATTR_ENTRY_ID, DOMAIN, SERVICE_RUN_PUMP
from .manager import PoolManager

PLATFORMS = ["binary_sensor", "sensor", "switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RUN_PUMP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=1, max=1440)),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienste registrieren."""
    hass.data.setdefault(DOMAIN, {})

    async def _run_pump(call: ServiceCall) -> None:
        managers: dict[str, PoolManager] = hass.data[DOMAIN]
        entry_id = call.data.get(ATTR_ENTRY_ID)
        if entry_id is not None:
            if entry_id not in managers:
                raise ServiceValidationError(f"Unbekannter Pool: {entry_id}")
            targets = [managers[entry_id]]
        else:
            targets = list(managers.values())
        for manager in targets:
            await manager.async_run_pump(call.data[ATTR_DURATION])

    hass.services.async_register(DOMAIN, SERVICE_RUN_PUMP, _run_pump, schema=RUN_PUMP_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Pool einrichten."""
    manager = PoolManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Erst nach den Plattformen starten: der Schalter stellt vorher seinen
    # gespeicherten Zustand (Automatik an/aus) wieder her.
    await manager.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Pool entladen."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        manager: PoolManager = hass.data[DOMAIN].pop(entry.entry_id)
        await manager.async_stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bei geänderten Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
