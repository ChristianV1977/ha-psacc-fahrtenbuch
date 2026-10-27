"""Alle Plattformen: Entities werden angelegt, Werte stimmen mit tests/fixtures ueberein."""
import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.psacc_fahrtenbuch.const import DOMAIN

from .conftest import VIN

EXPECTED = {
    # Fahrzeug-Sensoren
    "sensor.mokka_batterie_soc": "53",
    "sensor.mokka_reichweite": "118",
    "sensor.mokka_kilometerstand": "38061.2",
    "sensor.mokka_batteriespannung": "242.0",  # 60.5 V x 4
    "sensor.mokka_batterie_soh": "90",
    "sensor.mokka_umgebungstemperatur": "19.5",
    "sensor.mokka_umgebungslicht": "day",
    "sensor.mokka_zundung": "Stop",
    "sensor.mokka_geschwindigkeit": "0.0",
    "sensor.mokka_turen": STATE_UNKNOWN,
    "sensor.mokka_lademodus": "none",
    "sensor.mokka_laderate": "0",
    "sensor.mokka_ladestatus": "disconnected",
    "sensor.mokka_verbleibende_ladezeit": "0.0",
    "sensor.mokka_vorklimatisierung_status": "Disabled",
    "sensor.mokka_vorklimatisierung_fehler": STATE_UNKNOWN,
    "sensor.mokka_vorklimatisierung_zustand": "aus",
    "sensor.mokka_vorklimatisierung_restlaufzeit": STATE_UNKNOWN,
    "sensor.mokka_vorklimatisierung_antwort": STATE_UNKNOWN,
    "sensor.mokka_letztes_update": "2026-01-01T12:00:00+00:00",
    "sensor.mokka_nachste_stoppzeit": STATE_UNKNOWN,
    # Fahrtenbuch-Sensoren (leere DB)
    "sensor.mokka_fahrtenbuch_monat_fahrten": "0",
    "sensor.mokka_fahrtenbuch_monat_km": "0",
    "sensor.mokka_fahrtenbuch_monat_kwh": "0",
    "sensor.mokka_fahrtenbuch_monat_kwh_pro_100_km": "0",
    "sensor.mokka_fahrtenbuch_monat_kwh_pro_fahrt": "0",
    "sensor.mokka_fahrtenbuch_gesamt_fahrten": "0",
    "sensor.mokka_fahrtenbuch_gesamt_km": "0",
    "sensor.mokka_fahrtenbuch_gesamt_kwh": "0",
    "sensor.mokka_fahrtenbuch_gesamt_kwh_pro_100_km": "0",
    "sensor.mokka_fahrtenbuch_gesamt_kwh_pro_fahrt": "0",
    # Binary-Sensoren
    "binary_sensor.mokka_angesteckt": STATE_ON,
    "binary_sensor.mokka_in_bewegung": STATE_OFF,
    "binary_sensor.mokka_cloud_daten_aktuell": STATE_ON,
    "binary_sensor.mokka_fahrt_aktiv": STATE_OFF,
    # Steuerung
    "switch.mokka_vorklimatisierung": STATE_OFF,
    "number.mokka_ladelimit": "100",
    "number.mokka_akkukapazitat": "50.0",
    "number.mokka_fahrtenbuch_jahr": "2026",
    "number.mokka_fahrtenbuch_bearbeiten_id": "0",
    "select.mokka_fahrtenbuch_monat": "01",
    "text.mokka_fahrtenbuch_hinweis": "",
    "time.mokka_ladezeit": STATE_UNKNOWN,
}
ENABLED_BUTTONS = ["button.mokka_wakeup", "button.mokka_fahrtenbuch_aktueller_monat",
                   "button.mokka_fahrtenbuch_hinweis_speichern"]
DISABLED_BUTTONS = ["button.mokka_hupe", "button.mokka_lichter",
                    "button.mokka_turen_verriegeln", "button.mokka_turen_entriegeln"]


@pytest.mark.parametrize("entity_id,expected", sorted(EXPECTED.items()))
async def test_state(hass, setup, entity_id, expected):
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    assert state.state == expected


async def test_device_tracker(hass, setup):
    state = hass.states.get("device_tracker.mokka_standort")
    assert state.attributes["latitude"] == 50.0 and state.attributes["longitude"] == 8.0
    assert state.attributes["source_type"] == "gps"


async def test_enum_options_and_device_classes(hass, setup):
    assert hass.states.get("sensor.mokka_ladestatus").attributes["options"] == [
        "failure", "in_progress", "stopped", "finished", "disconnected", "unknown"]
    assert hass.states.get("sensor.mokka_lademodus").attributes["device_class"] == "enum"
    assert hass.states.get("sensor.mokka_letztes_update").attributes["device_class"] == "timestamp"
    assert hass.states.get("sensor.mokka_batterie_soc").attributes["unit_of_measurement"] == "%"
    assert hass.states.get("binary_sensor.mokka_angesteckt").attributes["device_class"] == "plug"


async def test_buttons_enabled_and_disabled_by_default(hass, setup):
    reg = er.async_get(hass)
    for eid in ENABLED_BUTTONS:
        assert hass.states.get(eid) is not None, eid
    for eid in DISABLED_BUTTONS:
        ent = reg.async_get(eid)
        assert ent is not None, eid
        assert ent.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(eid) is None


async def test_registry(hass, setup):
    reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(reg, setup.entry_id)
    assert len(entries) == len(EXPECTED) + 1 + len(ENABLED_BUTTONS) + len(DISABLED_BUTTONS)  # + device_tracker
    assert reg.async_get("number.mokka_akkukapazitat").entity_category is er.EntityCategory.CONFIG
    assert reg.async_get("binary_sensor.mokka_cloud_daten_aktuell").entity_category is er.EntityCategory.DIAGNOSTIC
    dev = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, setup.entry_id)})
    assert dev.name == "Mokka"


async def test_stale_data_flag(hass, setup, psacc, freezer):
    from datetime import timedelta
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from homeassistant.util import dt as dt_util
    freezer.tick(timedelta(minutes=40))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.mokka_cloud_daten_aktuell").state == STATE_OFF


async def test_precondition_switch(hass, setup, psacc):
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.mokka_vorklimatisierung"}, blocking=True)
    assert psacc.calls("/preconditioning/") and str(psacc.calls("/preconditioning/")[-1][1]).endswith("/1")
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.mokka_vorklimatisierung"}, blocking=True)
    assert str(psacc.calls("/preconditioning/")[-1][1]).endswith("/0")


async def test_charge_limit_number(hass, setup, psacc):
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_ladelimit", "value": 80}, blocking=True)
    cc = [c for c in psacc.calls("/charge_control") if "percentage=80" in str(c[1])]
    assert cc and "vin=" in str(cc[0][1])


async def test_charge_time_time(hass, setup, psacc):
    await hass.services.async_call("time", "set_value", {"entity_id": "time.mokka_ladezeit", "time": "06:30:00"}, blocking=True)
    assert [c for c in psacc.calls("/charge_control") if "hour=6" in str(c[1]) and "minute=30" in str(c[1])]
    assert hass.states.get("time.mokka_ladezeit").state == "06:30:00"


async def test_enabled_button_wakeup_and_enabled_horn(hass, setup, psacc):
    await hass.services.async_call("button", "press", {"entity_id": "button.mokka_wakeup"}, blocking=True)
    assert len(psacc.calls("/wakeup/")) == 1
    reg = er.async_get(hass)
    reg.async_update_entity("button.mokka_hupe", disabled_by=None)
    reg.async_update_entity("button.mokka_lichter", disabled_by=None)
    reg.async_update_entity("button.mokka_turen_verriegeln", disabled_by=None)
    reg.async_update_entity("button.mokka_turen_entriegeln", disabled_by=None)
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    for eid in DISABLED_BUTTONS:
        await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
    urls = [str(c[1]) for c in psacc.mock.mock_calls]
    for suffix in (f"/horn/{VIN}/3", f"/lights/{VIN}/10", f"/lock_door/{VIN}/1", f"/lock_door/{VIN}/0"):
        assert any(u.endswith(suffix) for u in urls), suffix


async def test_precond_state_requested_then_not_started(hass, setup, psacc, freezer):
    from datetime import timedelta
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from homeassistant.util import dt as dt_util
    sid = "sensor.mokka_vorklimatisierung_zustand"
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.mokka_vorklimatisierung"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(sid).state == "angefordert"
    freezer.tick(timedelta(seconds=150))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(sid).state == "nicht_gestartet"


async def test_precond_state_running_and_remaining(hass, setup, psacc, freezer):
    from datetime import timedelta
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from homeassistant.util import dt as dt_util
    psacc.info["preconditionning"]["air_conditioning"]["status"] = "Enabled"
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mokka_vorklimatisierung_zustand").state == "laeuft"
    assert hass.states.get("sensor.mokka_vorklimatisierung_restlaufzeit").state == "20"
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mokka_vorklimatisierung_restlaufzeit").state == "9"


async def test_precond_log_sensor_from_addon_log(hass, setup, psacc):
    from homeassistant.components.hassio import DATA_COMPONENT
    from custom_components.psacc_fahrtenbuch.const import DOMAIN
    from .conftest import VIN

    log = ("2026-10-27 12:14:38,148 :: INFO :: mqtt msg received: psa/RemoteServices/to/cid/OV-X/ThermalPrecond "
           f"b'{{\"resp_date\":\"2026-10-27T11:14:38Z\",\"vin\":\"{VIN}\",\"return_code\":\"300\"}}'\n")

    class FakeHassio:
        async def send_command(self, command, **kwargs):
            assert command == "/addons/psacc.test/logs" and kwargs["return_text"] is True
            return log

    hass.data[DATA_COMPONENT] = FakeHassio()
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.coordinator
    await coordinator._async_fetch_precond_log()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mokka_vorklimatisierung_antwort")
    assert state.state == "antwort 300"
    assert VIN not in str(state.attributes["verlauf"]) and "OV-X" not in str(state.attributes["verlauf"])
