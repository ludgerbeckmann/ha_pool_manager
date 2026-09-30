"""Konstanten für den Pool Manager."""

from __future__ import annotations

DOMAIN = "ha_pool_manager"

CONF_PUMP_ENTITY = "pump_entity"
CONF_WINDOWS = "windows"
CONF_START = "start"
CONF_END = "end"
CONF_DAYS = "days"

# Wochentage in der Reihenfolge von datetime.weekday() (Montag = 0)
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

MAX_WINDOWS = 8

SERVICE_RUN_PUMP = "run_pump"
ATTR_DURATION = "duration"
ATTR_ENTRY_ID = "entry_id"

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"

STORAGE_VERSION = 1
