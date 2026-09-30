"""Kernlogik: Pumpe nach Zeitplan schalten und Laufzeit erfassen."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DRY_AUTO_OFF,
    CONF_DRY_DURATION,
    CONF_DRY_MAX_POWER,
    CONF_DRY_MIN_POWER,
    CONF_POWER_ENTITY,
    CONF_PUMP_ENTITY,
    CONF_WINDOWS,
    DEFAULT_DRY_DURATION,
    DEFAULT_DRY_MAX_POWER,
    DEFAULT_DRY_MIN_POWER,
    DOMAIN,
    SIGNAL_UPDATE,
    STORAGE_VERSION,
)
from .dry_run import DryRunDetector
from .schedule import Window, is_active, next_start, parse_windows

_LOGGER = logging.getLogger(__name__)


class PoolManager:
    """Verwaltet Zeitplan, manuellen Lauf und Laufzeitzähler eines Pools."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.pump_entity: str = entry.options.get(
            CONF_PUMP_ENTITY, entry.data[CONF_PUMP_ENTITY]
        )
        self.windows: list[Window] = parse_windows(entry.options.get(CONF_WINDOWS))
        self.enabled = True
        self.manual_until: datetime | None = None

        opts = entry.options
        self.power_entity: str | None = opts.get(CONF_POWER_ENTITY) or None
        self.dry_auto_off: bool = bool(opts.get(CONF_DRY_AUTO_OFF, False))
        self._detector = DryRunDetector(
            float(opts.get(CONF_DRY_MIN_POWER, DEFAULT_DRY_MIN_POWER)),
            float(opts.get(CONF_DRY_MAX_POWER, DEFAULT_DRY_MAX_POWER)),
            timedelta(minutes=float(opts.get(CONF_DRY_DURATION, DEFAULT_DRY_DURATION))),
        )
        # Trockenlauf-Alarm bleibt gehalten, bis quittiert oder die Pumpe neu startet
        self.dry_run_detected = False
        self.dry_run_since: datetime | None = None
        self._paused_by_dry_run = False

        self._last_desired: bool | None = None
        self._pending: bool | None = None
        self._manual_on = False
        self._unsubs: list[CALLBACK_TYPE] = []
        self._manual_unsub: CALLBACK_TYPE | None = None

        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._runtime_date = dt_util.now().date()
        self._runtime_seconds = 0.0
        self._on_since: datetime | None = None

    # ------------------------------------------------------------------ Lebenszyklus

    async def async_start(self) -> None:
        """Zustand laden, Listener registrieren, erste Bewertung durchführen."""
        stored = await self._store.async_load()
        now = dt_util.now()
        if stored and stored.get("date") == now.date().isoformat():
            self._runtime_seconds = float(stored.get("seconds", 0))
        state = self.hass.states.get(self.pump_entity)
        if state is not None and state.state == STATE_ON:
            self._on_since = now

        self._unsubs.append(async_track_time_change(self.hass, self._tick, second=0))
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [self.pump_entity], self._pump_changed
            )
        )
        if self.power_entity:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [self.power_entity], self._power_changed
                )
            )
        await self._async_evaluate(now)

    async def async_stop(self) -> None:
        """Listener entfernen und Laufzeit sichern."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._manual_unsub:
            self._manual_unsub()
            self._manual_unsub = None
        await self._store.async_save(self._store_data(dt_util.now()))

    # ------------------------------------------------------------------ Zustand

    @property
    def schedule_active(self) -> bool:
        return is_active(self.windows, dt_util.now())

    @property
    def manual_active(self) -> bool:
        return self.manual_until is not None and dt_util.now() < self.manual_until

    @property
    def should_run(self) -> bool:
        """Soll die Pumpe laut Zeitplan bzw. manuellem Lauf gerade laufen?"""
        return self.manual_active or (self.enabled and self.schedule_active)

    @property
    def next_start(self) -> datetime | None:
        return next_start(self.windows, dt_util.now())

    def runtime_today_minutes(self) -> float:
        now = dt_util.now()
        seconds = self._runtime_seconds
        if self._on_since is not None:
            seconds += max((now - self._on_since).total_seconds(), 0)
        return round(seconds / 60, 1)

    # ------------------------------------------------------------------ Steuerung

    async def async_set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            # Bewusst wieder eingeschaltet: keine ausstehende Trockenlauf-Pause mehr
            self._paused_by_dry_run = False
        await self._async_evaluate(dt_util.now())

    async def async_run_pump(self, minutes: float) -> None:
        """Pumpe unabhängig vom Zeitplan für `minutes` Minuten laufen lassen."""
        now = dt_util.now()
        self.manual_until = now + timedelta(minutes=minutes)
        if self._manual_unsub:
            self._manual_unsub()
        self._manual_unsub = async_track_point_in_time(
            self.hass, self._manual_expired, self.manual_until
        )
        await self._async_evaluate(now)

    # ------------------------------------------------------------------ intern

    @property
    def dry_run_configured(self) -> bool:
        return self.power_entity is not None

    @property
    def dry_run_paused_schedule(self) -> bool:
        return self._paused_by_dry_run

    def current_power(self) -> float | None:
        """Aktuelle Leistung in Watt (None, wenn nicht verfügbar)."""
        if not self.power_entity:
            return None
        state = self.hass.states.get(self.power_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        if str(state.attributes.get("unit_of_measurement", "")).lower() == "kw":
            value *= 1000
        return value

    async def async_acknowledge_dry_run(self) -> None:
        """Alarm quittieren; ein durch den Trockenlauf pausierter Zeitplan läuft weiter."""
        self.dry_run_detected = False
        self.dry_run_since = None
        self._detector.reset()
        persistent_notification.async_dismiss(self.hass, self._notification_id)
        if self._paused_by_dry_run:
            self._paused_by_dry_run = False
            self.enabled = True
            self._last_desired = None  # Pumpe wieder an den Zeitplan angleichen
        await self._async_evaluate(dt_util.now())

    @property
    def _notification_id(self) -> str:
        return f"{DOMAIN}_dry_run_{self.entry.entry_id}"

    async def _async_check_dry_run(self, now: datetime) -> None:
        if not self.power_entity:
            return
        pump = self.hass.states.get(self.pump_entity)
        pump_on = pump is not None and pump.state == STATE_ON
        due = self._detector.update(now, pump_on, self.current_power())
        if not due or self.dry_run_detected:
            return

        self.dry_run_detected = True
        self.dry_run_since = self._detector.since
        _LOGGER.warning("Trockenlauf erkannt an %s", self.pump_entity)
        if self.dry_auto_off:
            # Zeitplan pausieren, manuellen Lauf beenden, Pumpe ausschalten
            self.enabled = False
            self._paused_by_dry_run = True
            self.manual_until = None
            self._manual_on = False
            self._pending = None
            if self._manual_unsub:
                self._manual_unsub()
                self._manual_unsub = None
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {ATTR_ENTITY_ID: self.pump_entity},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Abschalten der Pumpe %s fehlgeschlagen", self.pump_entity)
        self._notify_dry_run()

    def _notify_dry_run(self) -> None:
        de = self.hass.config.language.startswith("de")
        power = self.current_power()
        watt = f"{power:.0f} W" if power is not None else "?"
        minutes = self._detector.duration.total_seconds() / 60
        if de:
            title = f"Pool: Pumpe läuft trocken ({self.entry.title})"
            message = (
                f"Die Leistung von {self.pump_entity} lag {minutes:g} Minuten lang "
                f"im Trockenlauf-Bereich ({self._detector.minimum:g}–"
                f"{self._detector.maximum:g} W, zuletzt {watt})."
            )
            if self.dry_auto_off:
                message += " Die Pumpe wurde ausgeschaltet und der Zeitplan pausiert."
        else:
            title = f"Pool: pump running dry ({self.entry.title})"
            message = (
                f"The power of {self.pump_entity} stayed in the dry-run range for "
                f"{minutes:g} minutes ({self._detector.minimum:g}-"
                f"{self._detector.maximum:g} W, last {watt})."
            )
            if self.dry_auto_off:
                message += " The pump was switched off and the schedule paused."
        persistent_notification.async_create(
            self.hass, message, title=title, notification_id=self._notification_id
        )

    async def _manual_expired(self, _now: datetime) -> None:
        self._manual_unsub = None
        await self._async_evaluate(dt_util.now())

    async def _tick(self, now: datetime) -> None:
        await self._async_evaluate(dt_util.as_local(now))

    def _roll_day(self, now: datetime) -> None:
        """Tageszähler bei Datumswechsel zurücksetzen."""
        if now.date() == self._runtime_date:
            return
        self._runtime_date = now.date()
        self._runtime_seconds = 0.0
        if self._on_since is not None:
            self._on_since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _store_data(self, now: datetime) -> dict:
        seconds = self._runtime_seconds
        if self._on_since is not None:
            seconds += max((now - self._on_since).total_seconds(), 0)
        return {"date": self._runtime_date.isoformat(), "seconds": seconds}

    async def _async_evaluate(self, now: datetime) -> None:
        """Soll-Zustand bestimmen und bei Wechsel auf die Pumpe anwenden.

        Es wird nur bei einem *Wechsel* des Soll-Zustands geschaltet - manuelle
        Eingriffe an der Pumpe bleiben daher bis zum nächsten Fensterwechsel
        bestehen. Ist die Pumpe gerade `unavailable`, bleibt der Wechsel
        vorgemerkt und wird beim nächsten Durchlauf erneut versucht.
        """
        self._roll_day(now)
        await self._async_check_dry_run(now)
        if self.manual_until is not None and now >= self.manual_until:
            self.manual_until = None

        scheduled = is_active(self.windows, now)
        desired: bool | None
        if self.manual_until is not None:
            desired = True
            self._manual_on = True
        elif self._manual_on:
            # Manueller Lauf ist gerade zu Ende gegangen
            desired = scheduled if self.enabled else False
            self._manual_on = False
        elif self.enabled and self.windows:
            desired = scheduled
        else:
            desired = None

        if desired is not None and desired != self._last_desired:
            self._last_desired = desired
            self._pending = desired

        if self._pending is not None:
            await self._async_apply(self._pending)

        self._notify()

    async def _async_apply(self, desired: bool) -> None:
        state = self.hass.states.get(self.pump_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("Pumpe %s nicht verfügbar, versuche es erneut", self.pump_entity)
            return
        if state.state == (STATE_ON if desired else STATE_OFF):
            self._pending = None
            return
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on" if desired else "turn_off",
                {ATTR_ENTITY_ID: self.pump_entity},
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - beim nächsten Durchlauf erneut versuchen
            _LOGGER.exception("Schalten der Pumpe %s fehlgeschlagen", self.pump_entity)
            return
        self._pending = None

    @callback
    def _pump_changed(self, event: Event) -> None:
        """Laufzeit mitführen, wenn sich der Pumpenzustand ändert."""
        now = dt_util.now()
        self._roll_day(now)
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        is_on = new is not None and new.state == STATE_ON
        if is_on and (old is None or old.state != STATE_ON) and self.dry_run_detected:
            # Pumpe wurde neu gestartet: Alarm zurücknehmen, die Erkennung beginnt neu
            self.dry_run_detected = False
            self.dry_run_since = None
            self._detector.reset()
        if is_on and self._on_since is None:
            self._on_since = now
        elif not is_on and self._on_since is not None:
            self._runtime_seconds += max((now - self._on_since).total_seconds(), 0)
            self._on_since = None
            self._store.async_delay_save(lambda: self._store_data(dt_util.now()), 60)
        if new is not None and new.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            if self._pending is not None:
                self.hass.async_create_task(self._async_apply(self._pending))
        self._notify()

    @callback
    def _power_changed(self, event: Event) -> None:
        self.hass.async_create_task(self._async_dry_run_and_notify())

    async def _async_dry_run_and_notify(self) -> None:
        await self._async_check_dry_run(dt_util.now())
        self._notify()

    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))
