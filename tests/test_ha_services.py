"""Services, Hinweis-Bearbeitung (number/text/button) und Recorder-Datenschutz."""
import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from voluptuous import MultipleInvalid

from custom_components.psacc_fahrtenbuch.sensor import BookSensor

DOMAIN = "psacc_fahrtenbuch"

TRIP = {
    "start_zeit": "2026-01-05 08:00:00", "start_ort": "Teststrasse, Beispielstadt",
    "end_zeit": "2026-01-05 08:30:00", "end_ort": "Zuhause",
    "distanz_km": 12.5, "dauer_min": 30, "geschwindigkeit_kmh": 25.0, "verbrauch_kwh": 1.5,
    "soc_start": 60, "soc_end": 57, "km_start": 1000.0, "km_end": 1012.5,
}


async def add_trip(hass, **kw):
    res = await hass.services.async_call(DOMAIN, "fahrt_hinzufuegen", {**TRIP, **kw}, blocking=True, return_response=True)
    return res["id"]


async def query(hass, **data):
    return await hass.services.async_call(DOMAIN, "fahrten_abfragen", data, blocking=True, return_response=True)


async def test_fahrt_hinzufuegen_and_abfragen_month(hass, setup):
    tid = await add_trip(hass)
    assert tid == 1
    await add_trip(hass, start_zeit="2026-02-01 09:00:00", end_zeit="2026-02-01 09:10:00", distanz_km=2.5, verbrauch_kwh=0.5)
    jan = await query(hass, jahr=2026, monat=1)
    assert jan["anzahl"] == 1 and jan["jahr"] == 2026 and jan["monat"] == "01"
    assert jan["gesamt_km"] == 12.5 and jan["gesamt_kwh"] == 1.5 and jan["kwh_pro_100km"] == 12.0
    t = jan["trips"][0]
    assert t["id"] == 1 and t["start_ort"] == "Teststrasse, Beispielstadt" and t["hinweis"] == "" and t["soc_anstieg"] == ""
    # ohne Angaben: aktueller Monat (Januar 2026 laut eingefrorener Zeit)
    assert (await query(hass))["anzahl"] == 1
    assert (await query(hass, jahr=2026, monat=3))["anzahl"] == 0


async def test_abfragen_gesamt(hass, setup):
    await add_trip(hass)
    await add_trip(hass, start_zeit="2025-12-31 23:00:00", end_zeit="2025-12-31 23:30:00", distanz_km=7.5, verbrauch_kwh=1.0)
    res = await query(hass, gesamt=True)
    assert res["anzahl"] == 2 and res["gesamt_km"] == 20.0 and res["gesamt_kwh"] == 2.5
    assert "trips" not in res


async def test_sensors_follow_added_trip(hass, setup):
    await add_trip(hass)
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten").state == "1"
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_km").state == "12.5"
    assert hass.states.get("sensor.mokka_fahrtenbuch_gesamt_fahrten").state == "1"
    attrs = hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten").attributes
    assert attrs["jahr"] == 2026 and attrs["monat"] == "01" and attrs["trips"][0]["id"] == 1


async def test_fahrt_hinzufuegen_validation(hass, setup):
    bad = {k: v for k, v in TRIP.items() if k != "km_end"}
    with pytest.raises(MultipleInvalid):
        await hass.services.async_call(DOMAIN, "fahrt_hinzufuegen", bad, blocking=True)


async def test_hinweis_setzen(hass, setup):
    tid = await add_trip(hass)
    await hass.services.async_call(DOMAIN, "hinweis_setzen", {"fahrt_id": tid, "hinweis": "Test\nhinweis\x07 ok"}, blocking=True)
    assert (await query(hass, jahr=2026, monat=1))["trips"][0]["hinweis"] == "Testhinweis ok"  # nur druckbare Zeichen


async def test_hinweis_truncated_to_255(hass, setup):
    tid = await add_trip(hass)
    await hass.services.async_call(DOMAIN, "hinweis_setzen", {"fahrt_id": tid, "hinweis": "x" * 400}, blocking=True)
    assert len((await query(hass, jahr=2026, monat=1))["trips"][0]["hinweis"]) == 255


async def test_hinweis_setzen_unknown_id(hass, setup):
    with pytest.raises(HomeAssistantError, match="999"):
        await hass.services.async_call(DOMAIN, "hinweis_setzen", {"fahrt_id": 999, "hinweis": "x"}, blocking=True)


async def test_soc_anstieg_setzen(hass, setup):
    tid = await add_trip(hass)
    await hass.services.async_call(DOMAIN, "soc_anstieg_setzen", {"fahrt_id": tid, "wert": True}, blocking=True)
    assert (await query(hass, jahr=2026, monat=1))["trips"][0]["soc_anstieg"] == "X"
    await hass.services.async_call(DOMAIN, "soc_anstieg_setzen", {"fahrt_id": tid, "wert": False}, blocking=True)
    assert (await query(hass, jahr=2026, monat=1))["trips"][0]["soc_anstieg"] == ""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "soc_anstieg_setzen", {"fahrt_id": 999, "wert": True}, blocking=True)


async def test_auswahl_setzen(hass, setup):
    await add_trip(hass)
    await hass.services.async_call(DOMAIN, "auswahl_setzen", {"jahr": 2025, "monat": 12}, blocking=True)
    assert hass.states.get("number.mokka_fahrtenbuch_jahr").state == "2025"
    assert hass.states.get("select.mokka_fahrtenbuch_monat").state == "12"
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten").state == "0"
    await hass.services.async_call(DOMAIN, "auswahl_setzen", {"jahr": 2026, "monat": 1}, blocking=True)
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten").state == "1"
    with pytest.raises(MultipleInvalid):
        await hass.services.async_call(DOMAIN, "auswahl_setzen", {"monat": 13}, blocking=True)


async def test_select_and_current_month_button(hass, setup):
    await hass.services.async_call("select", "select_option", {"entity_id": "select.mokka_fahrtenbuch_monat", "option": "07"}, blocking=True)
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_fahrtenbuch_jahr", "value": 2024}, blocking=True)
    assert setup.runtime_data.manager.cfg["monat"] == 7 and setup.runtime_data.manager.cfg["jahr"] == 2024
    await hass.services.async_call("button", "press", {"entity_id": "button.mokka_fahrtenbuch_aktueller_monat"}, blocking=True)
    assert hass.states.get("select.mokka_fahrtenbuch_monat").state == "01"
    assert hass.states.get("number.mokka_fahrtenbuch_jahr").state == "2026"


async def test_wakeup_service(hass, setup, psacc):
    await hass.services.async_call(DOMAIN, "wakeup", {}, blocking=True)
    assert len(psacc.calls("/wakeup/")) == 1


async def test_capacity_number_changes_future_calc(hass, setup):
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_akkukapazitat", "value": 60}, blocking=True)
    assert setup.runtime_data.manager.cfg["kapazitaet"] == 60.0
    assert hass.states.get("number.mokka_akkukapazitat").state == "60.0"


# --- Hinweis ueber number/text/button -----------------------------------------
async def test_hinweis_edit_flow(hass, setup):
    t1 = await add_trip(hass)
    t2 = await add_trip(hass, start_zeit="2026-01-06 08:00:00", end_zeit="2026-01-06 08:30:00")
    await hass.services.async_call(DOMAIN, "hinweis_setzen", {"fahrt_id": t1, "hinweis": "alt eins"}, blocking=True)
    # ID waehlen -> Text wird vorbefuellt
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_fahrtenbuch_bearbeiten_id", "value": t1}, blocking=True)
    assert hass.states.get("text.mokka_fahrtenbuch_hinweis").state == "alt eins"
    # Entwurf aendern, speichern per Button
    await hass.services.async_call("text", "set_value", {"entity_id": "text.mokka_fahrtenbuch_hinweis", "value": "neu eins"}, blocking=True)
    assert hass.states.get("text.mokka_fahrtenbuch_hinweis").state == "neu eins"
    trips = {t["id"]: t["hinweis"] for t in (await query(hass, jahr=2026, monat=1))["trips"]}
    assert trips[t1] == "alt eins"  # noch nicht gespeichert
    await hass.services.async_call("button", "press", {"entity_id": "button.mokka_fahrtenbuch_hinweis_speichern"}, blocking=True)
    trips = {t["id"]: t["hinweis"] for t in (await query(hass, jahr=2026, monat=1))["trips"]}
    assert trips == {t1: "neu eins", t2: ""}
    # andere ID waehlen -> leerer Entwurf, nichts ueberschrieben
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_fahrtenbuch_bearbeiten_id", "value": t2}, blocking=True)
    assert hass.states.get("text.mokka_fahrtenbuch_hinweis").state == ""


async def test_hinweis_save_unknown_id(hass, setup):
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_fahrtenbuch_bearbeiten_id", "value": 42}, blocking=True)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("button", "press", {"entity_id": "button.mokka_fahrtenbuch_hinweis_speichern"}, blocking=True)


async def test_edit_id_persists_over_reload(hass, setup):
    t1 = await add_trip(hass)
    await hass.services.async_call(DOMAIN, "hinweis_setzen", {"fahrt_id": t1, "hinweis": "bleibt"}, blocking=True)
    await hass.services.async_call("number", "set_value", {"entity_id": "number.mokka_fahrtenbuch_bearbeiten_id", "value": t1}, blocking=True)
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.mokka_fahrtenbuch_bearbeiten_id").state == "1"
    assert hass.states.get("text.mokka_fahrtenbuch_hinweis").state == "bleibt"


# --- Recorder-Datenschutz ----------------------------------------------------
def test_trips_attribute_unrecorded():
    assert "trips" in BookSensor._unrecorded_attributes


async def test_trips_attribute_unrecorded_at_runtime(hass, setup):
    """Genau diese Info wertet der Recorder aus (State.state_info)."""
    state = hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten")
    assert "trips" in state.attributes
    assert "trips" in state.state_info["unrecorded_attributes"]
