from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_pool_manager.const import DOMAIN


async def test_user_flow_and_duplicate(hass):
    hass.states.async_set("switch.pump", "off")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Garten", "pump_entity": "switch.pump"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"pump_entity": "switch.pump"}
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Zweiter", "pump_entity": "switch.pump"}
    )
    assert result["type"] is FlowResultType.ABORT


async def test_options_add_and_remove_window(hass):
    hass.states.async_set("switch.pump", "off")
    entry = MockConfigEntry(domain=DOMAIN, title="P", data={"pump_entity": "switch.pump"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["pump", "add_window"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_window"}
    )
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], {"start": "08:00:00", "end": "08:00:00", "days": ["mon"]}
    )
    assert bad["errors"] == {"base": "start_equals_end"}
    ok = await hass.config_entries.options.async_configure(
        result["flow_id"], {"start": "08:00:00", "end": "10:00:00", "days": ["mon"]}
    )
    assert ok["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["windows"] == [
        {"start": "08:00:00", "end": "10:00:00", "days": ["mon"]}
    ]
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "remove_window" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_window"}
    )
    done = await hass.config_entries.options.async_configure(result["flow_id"], {"remove": ["0"]})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["windows"] == []
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
