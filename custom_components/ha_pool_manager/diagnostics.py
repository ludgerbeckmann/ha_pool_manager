"""Diagnose-Download."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    manager = hass.data[DOMAIN][entry.entry_id]
    pump = hass.states.get(manager.pump_entity)
    next_start = manager.next_start
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "live": {
            "enabled": manager.enabled,
            "schedule_active": manager.schedule_active,
            "should_run": manager.should_run,
            "manual_until": manager.manual_until.isoformat() if manager.manual_until else None,
            "next_start": next_start.isoformat() if next_start else None,
            "runtime_today_minutes": manager.runtime_today_minutes(),
            "pump_state": pump.state if pump else None,
            "dry_run": {
                "configured": manager.dry_run_configured,
                "detected": manager.dry_run_detected,
                "schedule_paused": manager.dry_run_paused_schedule,
                "power": manager.current_power(),
            },
        },
    }
