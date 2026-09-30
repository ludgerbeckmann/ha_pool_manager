from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.ha_pool_manager.const import DOMAIN

PUMP = "switch.pool_pump"
ALL = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


async def _setup(hass, windows, pump_state=STATE_OFF):
    hass.states.async_set(PUMP, pump_state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        data={"pump_entity": PUMP},
        options={"pump_entity": PUMP, "windows": windows},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _tick(hass, freezer, minutes):
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _calls(hass):
    on = async_mock_service(hass, "homeassistant", "turn_on")
    off = async_mock_service(hass, "homeassistant", "turn_off")
    return on, off


async def test_switches_at_window_boundaries(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 07:59:30+00:00")
    on, off = _calls(hass)
    hass.config.set_time_zone("UTC")
    await _setup(hass, [{"start": "08:00:00", "end": "09:00:00", "days": ALL}])
    on.clear(); off.clear()

    await _tick(hass, freezer, 1)  # 08:00:30 -> Fensterbeginn
    assert len(on) == 1 and on[0].data["entity_id"] == PUMP
    hass.states.async_set(PUMP, STATE_ON)

    await _tick(hass, freezer, 30)  # innerhalb, keine weiteren Aufrufe
    assert len(on) == 1 and not off

    await _tick(hass, freezer, 30)  # 09:00:30 -> Ende
    assert len(off) == 1


async def test_startup_syncs_inside_window(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 08:30:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(hass, [{"start": "08:00:00", "end": "09:00:00", "days": ALL}])
    assert len(on) == 1


async def test_manual_intervention_not_overridden(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 08:30:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(hass, [{"start": "08:00:00", "end": "09:00:00", "days": ALL}], STATE_ON)
    on.clear(); off.clear()
    hass.states.async_set(PUMP, STATE_OFF)  # Nutzer schaltet manuell aus
    await _tick(hass, freezer, 5)
    assert not on and not off


async def test_unavailable_pump_retried(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 08:30:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(
        hass,
        [{"start": "08:00:00", "end": "09:00:00", "days": ALL}],
        STATE_UNAVAILABLE,
    )
    assert not on
    hass.states.async_set(PUMP, STATE_OFF)
    await hass.async_block_till_done()
    assert len(on) == 1


async def test_disabled_schedule_does_nothing(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 07:59:30+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(hass, [{"start": "08:00:00", "end": "09:00:00", "days": ALL}])
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.pool_schedule_active"}, blocking=True
    )
    on.clear(); off.clear()
    await _tick(hass, freezer, 1)
    assert not on


async def test_run_pump_service_and_expiry(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(hass, [{"start": "08:00:00", "end": "09:00:00", "days": ALL}])
    on.clear(); off.clear()
    await hass.services.async_call(DOMAIN, "run_pump", {"duration": 10}, blocking=True)
    assert len(on) == 1
    hass.states.async_set(PUMP, STATE_ON)
    await _tick(hass, freezer, 11)
    assert len(off) == 1


async def test_runtime_and_entities(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    await _setup(hass, [{"start": "18:00:00", "end": "19:00:00", "days": ALL}])
    hass.states.async_set(PUMP, STATE_ON)
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=15))
    hass.states.async_set(PUMP, STATE_OFF)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.pool_laufzeit_heute") or hass.states.get(
        "sensor.pool_runtime_today"
    )
    assert state is not None and float(state.state) == 15.0
    nxt = hass.states.get("sensor.pool_naechster_start") or hass.states.get(
        "sensor.pool_next_start"
    )
    assert nxt.state.startswith("2026-09-28T18:00:00")
    assert hass.states.get("binary_sensor.pool_pump_should_run").state == STATE_OFF


async def test_unload(hass: HomeAssistant):
    entry = await _setup(hass, [])
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


POWER = "sensor.pump_power"


async def _setup_dry(hass, auto_off=False, pump_state=STATE_ON, power="90", windows=None):
    hass.states.async_set(PUMP, pump_state)
    hass.states.async_set(POWER, power, {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        data={"pump_entity": PUMP},
        options={
            "pump_entity": PUMP,
            "windows": windows or [],
            "power_entity": POWER,
            "dry_min_power": 75,
            "dry_max_power": 100,
            "dry_duration": 5,
            "dry_auto_off": auto_off,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _dry_state(hass):
    return hass.states.get("binary_sensor.pool_dry_run_detected").state


async def test_dry_run_detected_after_duration_and_latched(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup_dry(hass)
    assert _dry_state(hass) == STATE_OFF
    await _tick(hass, freezer, 4)
    assert _dry_state(hass) == STATE_OFF
    await _tick(hass, freezer, 1)
    assert _dry_state(hass) == STATE_ON
    assert not off  # ohne Auto-Aus wird nicht geschaltet

    # Pumpe aus -> Alarm bleibt gehalten; Neustart der Pumpe nimmt ihn zurück
    hass.states.async_set(PUMP, STATE_OFF)
    await _tick(hass, freezer, 1)
    assert _dry_state(hass) == STATE_ON
    hass.states.async_set(PUMP, STATE_ON)
    await hass.async_block_till_done()
    assert _dry_state(hass) == STATE_OFF


async def test_normal_load_never_triggers(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    _calls(hass)
    await _setup_dry(hass, power="250")
    await _tick(hass, freezer, 30)
    assert _dry_state(hass) == STATE_OFF


async def test_unavailable_power_is_not_dry_run(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    _calls(hass)
    await _setup_dry(hass, power=STATE_UNAVAILABLE)
    await _tick(hass, freezer, 30)
    assert _dry_state(hass) == STATE_OFF


async def test_kw_sensor_is_converted(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    _calls(hass)
    await _setup_dry(hass, power="0.09")
    hass.states.async_set(POWER, "0.09", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    await _tick(hass, freezer, 5)
    assert _dry_state(hass) == STATE_ON


async def test_auto_off_pauses_schedule_until_acknowledged(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup_dry(
        hass,
        auto_off=True,
        windows=[{"start": "11:00:00", "end": "23:00:00", "days": ALL}],
    )
    on.clear(); off.clear()
    await _tick(hass, freezer, 5)
    assert _dry_state(hass) == STATE_ON
    assert len(off) == 1 and off[0].data["entity_id"] == PUMP
    assert hass.states.get("switch.pool_schedule_active").state == STATE_OFF
    hass.states.async_set(PUMP, STATE_OFF)

    await _tick(hass, freezer, 5)  # Zeitplan ist pausiert: Pumpe bleibt aus
    assert not on

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pool_acknowledge_dry_run"}, blocking=True
    )
    await hass.async_block_till_done()
    assert _dry_state(hass) == STATE_OFF
    assert hass.states.get("switch.pool_schedule_active").state == STATE_ON
    assert len(on) == 1  # Zeitplan gleicht die Pumpe wieder an (im Fenster)


async def test_dry_run_entities_removed_when_not_configured(hass: HomeAssistant):
    entry = await _setup_dry(hass)
    assert hass.states.get("button.pool_acknowledge_dry_run") is not None
    hass.config_entries.async_update_entry(
        entry, options={"pump_entity": PUMP, "windows": []}
    )
    await hass.async_block_till_done()
    assert hass.states.get("button.pool_acknowledge_dry_run") is None
    assert hass.states.get("binary_sensor.pool_dry_run_detected") is None


async def test_no_windows_leaves_pump_alone(hass: HomeAssistant, freezer):
    freezer.move_to("2026-09-28 12:00:00+00:00")
    hass.config.set_time_zone("UTC")
    on, off = _calls(hass)
    await _setup(hass, [], STATE_ON)
    await _tick(hass, freezer, 5)
    assert not on and not off
