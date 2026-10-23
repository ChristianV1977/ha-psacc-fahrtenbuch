"""Config-Flow und Options-Flow gegen echtes Home Assistant (psacc per aioclient_mock)."""
from datetime import timedelta

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.psacc_fahrtenbuch.const import DOMAIN

from .conftest import BASE, VIN


async def _start(hass, url=BASE):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"url": url})


async def test_full_flow(hass, psacc):
    result = await _start(hass, BASE + "/")  # abschliessender Slash wird entfernt
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "vehicle"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vin": VIN})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "settings"
    # Vorschlag fuer den Titel kommt aus dem psacc-Label
    assert [k for k in result["data_schema"].schema if k == "titel"][0].default() == "Mokka-e"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "titel": "Mokka", "kapazitaet_kwh": 50.0, "scan_interval": 25, "wakeup_stuendlich": False,
        "geocoding": False, "user_agent": "test-agent/1.0",
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mokka"
    assert result["data"] == {"url": BASE, "vin": VIN}
    assert result["options"] == {
        "scan_interval": 25, "wakeup_stuendlich": False, "geocoding": False,
        "user_agent": "test-agent/1.0", "kapazitaet_kwh": 50.0,
    }
    assert isinstance(result["options"]["scan_interval"], int)  # NumberSelector liefert float
    entry = result["result"]
    assert entry.unique_id == VIN
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.mokka_batterie_soc").state == "53"


async def test_flow_with_charge_entity(hass, psacc):
    hass.states.async_set("binary_sensor.wallbox_laedt", "off")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vin": VIN})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "titel": "Mokka", "kapazitaet_kwh": 50, "scan_interval": 20, "wakeup_stuendlich": True,
        "wakeup_bei_ladeende_entity": "binary_sensor.wallbox_laedt", "geocoding": True, "user_agent": "ua",
    })
    assert result["options"]["wakeup_bei_ladeende_entity"] == "binary_sensor.wallbox_laedt"


async def test_cannot_connect(hass, psacc):
    psacc.down = True
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user" and result["errors"] == {"base": "cannot_connect"}
    # Wiederholung nach Behebung funktioniert
    psacc.down = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": BASE})
    assert result["step_id"] == "vehicle"


async def test_no_vehicles(hass, psacc):
    psacc.vehicles = []
    result = await _start(hass)
    assert result["step_id"] == "user" and result["errors"] == {"base": "no_vehicles"}
    psacc.vehicles = [{"label": "ohne vin"}]  # Eintrag ohne VIN zaehlt nicht
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": BASE})
    assert result["errors"] == {"base": "no_vehicles"}


async def test_single_config_entry(hass, psacc, entry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_reloads(hass, setup, psacc):
    entry = setup
    coord = entry.runtime_data.coordinator
    assert coord.update_interval == timedelta(seconds=20)
    first_manager = entry.runtime_data.manager
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "scan_interval": 45, "wakeup_stuendlich": False, "geocoding": False, "user_agent": "neu/2",
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    # bestehende Optionen (Kapazitaet) bleiben, neue gelten, Entry wurde neu geladen
    assert entry.options["kapazitaet_kwh"] == 50.0
    assert entry.options["scan_interval"] == 45 and isinstance(entry.options["scan_interval"], int)
    assert entry.options["user_agent"] == "neu/2" and entry.options["wakeup_stuendlich"] is False
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.manager is not first_manager
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=45)


async def test_options_flow_form_prefilled(hass, setup):
    result = await hass.config_entries.options.async_init(setup.entry_id)
    defaults = {str(k): k.default() for k in result["data_schema"].schema if k.default is not vol.UNDEFINED}
    assert defaults["scan_interval"] == 20 and defaults["user_agent"] == "test-agent/1.0"
