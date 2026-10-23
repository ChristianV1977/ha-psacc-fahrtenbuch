"""Fahrtenbuch-Engine (manager.py): Zuendungserkennung, Persistenz, Geocoding, Wakeup."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.helpers import entity_registry as er  # noqa: F401
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.psacc_fahrtenbuch.const import EVENT_TRIP, SOC_RESYNC_DELAY
from custom_components.psacc_fahrtenbuch.trips import compute_trip

START_TS = "2026-01-01 12:10:00+00:00"   # == "jetzt" im Test
START_LOCAL = "2026-01-01 13:10:00"      # Europe/Berlin
END_TS = "2026-01-01 12:40:00+00:00"
END_LOCAL = "2026-01-01 13:40:00"


async def feed(hass, entry, psacc, ign, **kw):
    """Neue psacc-Antwort einspielen und den Coordinator sofort abfragen."""
    psacc.set_ign(ign, **kw)
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def rows(hass, entry):
    m = entry.runtime_data.manager
    return (await hass.async_add_executor_job(m.db.month, 2026, 1))["trips"]


async def active(hass, entry):
    return await hass.async_add_executor_job(entry.runtime_data.manager.db.get_active)


async def start_trip(hass, entry, psacc, soc=53):
    await feed(hass, entry, psacc, "StartUp", soc=soc, km=38061.2, updated=START_TS)


async def test_start_creates_running_trip(hass, setup, psacc):
    await start_trip(hass, setup, psacc)
    a = await active(hass, setup)
    assert a["start_zeit"] == START_LOCAL and a["km_start"] == 38061.2 and a["soc_start"] == 53.0
    assert a["start_ort"] == "Teststrasse, Beispielstadt"
    assert hass.states.get("binary_sensor.mokka_fahrt_aktiv").state == "on"
    assert await rows(hass, setup) == []  # noch keine abgeschlossene Fahrt


async def test_stop_saves_trip_with_compute_trip_formulas(hass, setup, psacc, freezer):
    events = async_capture_events(hass, EVENT_TRIP)
    await start_trip(hass, setup, psacc)
    freezer.move_to("2026-01-01 12:41:00+00:00")  # Daten 1 min alt -> frisch
    await feed(hass, setup, psacc, "Stop", soc=49, km=38081.2, updated=END_TS)
    expected = compute_trip(
        start_zeit=START_LOCAL, start_ort="Teststrasse, Beispielstadt", end_zeit=END_LOCAL,
        end_ort="Teststrasse, Beispielstadt", km_start=38061.2, km_end=38081.2,
        soc_start=53, soc_end=49, kapazitaet=50.0, frisch=True)
    got = await rows(hass, setup)
    assert len(got) == 1
    t = got[0]
    assert t.pop("id") == 1 and t.pop("erfasst_am")
    assert t == expected
    # konkrete Werte: 20 km in 30 min, 4 % von 50 kWh
    assert (t["distanz_km"], t["dauer_min"], t["geschwindigkeit_kmh"], t["verbrauch_kwh"]) == (20.0, 30.0, 40.0, 2.0)
    assert t["hinweis"] == "" and t["soc_anstieg"] == ""
    assert await active(hass, setup) is None
    assert hass.states.get("binary_sensor.mokka_fahrt_aktiv").state == "off"
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_fahrten").state == "1"
    assert hass.states.get("sensor.mokka_fahrtenbuch_monat_kwh").state == "2.0"
    assert hass.states.get("sensor.mokka_fahrtenbuch_gesamt_km").state == "20.0"
    assert len(events) == 1 and events[0].data == {"id": 1, "distanz_km": 20.0, "verbrauch_kwh": 2.0}


async def test_stale_cloud_data_hint(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc)
    freezer.move_to("2026-01-01 14:00:00+00:00")  # Daten > 30 min alt
    await feed(hass, setup, psacc, "Stop", soc=49, km=38081.2, updated=END_TS)
    assert (await rows(hass, setup))[0]["hinweis"] == "Cloud-Daten evtl. veraltet"


async def test_soc_rise_flag(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc, soc=50)
    freezer.move_to("2026-01-01 12:41:00+00:00")
    await feed(hass, setup, psacc, "Stop", soc=55, km=38065.2, updated=END_TS)
    t = (await rows(hass, setup))[0]
    assert t["soc_anstieg"] == "X" and t["verbrauch_kwh"] == 0


async def test_soc_resync_after_90s(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc, soc=53)
    # frischerer Cloud-Sync mit korrigiertem SoC, noch vor Ablauf der 90 s
    await feed(hass, setup, psacc, "StartUp", soc=51, updated="2026-01-01 12:11:00+00:00")
    assert (await active(hass, setup))["soc_start"] == 53.0  # noch nicht nachgereicht
    freezer.tick(timedelta(seconds=SOC_RESYNC_DELAY + 1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert (await active(hass, setup))["soc_start"] == 51.0


async def test_no_soc_resync_without_newer_sync(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc, soc=53)
    await feed(hass, setup, psacc, "StartUp", soc=40)  # gleicher Zeitstempel -> kein frischer Sync
    freezer.tick(timedelta(seconds=SOC_RESYNC_DELAY + 1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert (await active(hass, setup))["soc_start"] == 53.0


async def test_no_double_start(hass, setup, psacc):
    await start_trip(hass, setup, psacc)
    first = await active(hass, setup)
    await feed(hass, setup, psacc, "StartUp", km=38070.0)  # unveraendert StartUp
    await feed(hass, setup, psacc, "Free", km=38071.0)  # Zwischenzustand ...
    await feed(hass, setup, psacc, "StartUp", km=38072.0)  # ... und erneut StartUp bei laufender Fahrt
    assert await active(hass, setup) == first
    assert len(psacc.geo_calls) == 1  # nur der erste Start hat geocodiert


async def test_restart_during_trip_keeps_trip(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc)
    before = await active(hass, setup)
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert await active(hass, setup) == before
    assert setup.runtime_data.manager.active == before
    assert hass.states.get("binary_sensor.mokka_fahrt_aktiv").state == "on"
    freezer.move_to("2026-01-01 12:41:00+00:00")
    await feed(hass, setup, psacc, "Stop", soc=49, km=38081.2, updated=END_TS)
    got = await rows(hass, setup)
    assert len(got) == 1 and got[0]["start_zeit"] == START_LOCAL and got[0]["km_start"] == 38061.2


async def test_outage_between_start_and_stop(hass, setup, psacc, freezer):
    await start_trip(hass, setup, psacc)
    psacc.down = True
    for _ in range(3):
        await setup.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()
    assert not setup.runtime_data.coordinator.last_update_success
    assert hass.states.get("sensor.mokka_batterie_soc").state == "unavailable"
    psacc.down = False
    await feed(hass, setup, psacc, "StartUp")  # zurueck, Zuendung unveraendert -> nichts ausloesen
    assert len(psacc.geo_calls) == 1 and await rows(hass, setup) == []
    freezer.move_to("2026-01-01 12:41:00+00:00")
    await feed(hass, setup, psacc, "Stop", soc=49, km=38081.2, updated=END_TS)
    assert len(await rows(hass, setup)) == 1


async def test_outage_does_not_swallow_stop(hass, setup, psacc, freezer):
    """Ausfall endet direkt mit Stop: genau eine Fahrt, kein Verwerfen des Zustands."""
    await start_trip(hass, setup, psacc)
    psacc.down = True
    await setup.runtime_data.coordinator.async_refresh()
    psacc.down = False
    freezer.move_to("2026-01-01 12:41:00+00:00")
    await feed(hass, setup, psacc, "Stop", soc=49, km=38081.2, updated=END_TS)
    assert len(await rows(hass, setup)) == 1
    await feed(hass, setup, psacc, "Stop")
    assert len(await rows(hass, setup)) == 1


async def test_stop_without_running_trip_does_nothing(hass, setup, psacc):
    await feed(hass, setup, psacc, "Free")
    await feed(hass, setup, psacc, "Stop")
    assert await rows(hass, setup) == []


# --- Geocoding / Zonen -------------------------------------------------------
def _zone(hass, entity_id, name, lat, lon, radius=200):
    hass.states.async_set(entity_id, "zoning", {"latitude": lat, "longitude": lon, "radius": radius,
                                                "passive": False, "friendly_name": name})


async def test_zone_home_shortcut_skips_nominatim(hass, setup, psacc):
    _zone(hass, "zone.home", "Home", 50.0, 8.0)
    await start_trip(hass, setup, psacc)
    assert (await active(hass, setup))["start_ort"] == "Zuhause"
    assert psacc.geo_calls == []


async def test_other_zone_uses_cleaned_name(hass, setup, psacc):
    _zone(hass, "zone.buero", "Büro <Test>;", 50.0, 8.0)
    await start_trip(hass, setup, psacc)
    assert (await active(hass, setup))["start_ort"] == "Büro Test"
    assert psacc.geo_calls == []


async def test_nominatim_request_details(hass, setup, psacc):
    await start_trip(hass, setup, psacc)
    calls = psacc.calls("nominatim.openstreetmap.org")
    assert len(calls) == 1
    _, url, _, headers = calls[0]
    assert headers["User-Agent"] == "test-agent/1.0"
    q = dict(url.query)
    assert q["lat"] == "50.0" and q["lon"] == "8.0" and q["format"] == "jsonv2"
    assert q["addressdetails"] == "1" and q["accept-language"] == "de"


async def test_nominatim_min_interval_one_second(hass, setup, psacc):
    m = setup.runtime_data.manager
    real_sleep = __import__("asyncio").sleep
    waits = []

    async def fake_sleep(delay, *a):
        waits.append(delay)
        await real_sleep(0)

    with patch("custom_components.psacc_fahrtenbuch.manager.asyncio.sleep", fake_sleep):
        await m.resolve_ort(50.0, 8.0)
        await m.resolve_ort(50.0, 8.0)
    assert len(psacc.geo_calls) == 2
    assert len(waits) == 1 and 0 < waits[0] <= 1.0


async def test_geocode_http_error_unknown_place(hass, setup, psacc):
    psacc.nominatim_fail = True
    await start_trip(hass, setup, psacc)
    assert (await active(hass, setup))["start_ort"] == "Unbekannter Ort"


async def test_geocode_exception_unknown_place(hass, setup, psacc):
    psacc.nominatim_exc = True
    await start_trip(hass, setup, psacc)
    assert (await active(hass, setup))["start_ort"] == "Unbekannter Ort"


async def test_geocode_disabled_option(hass, entry, psacc):
    hass.config_entries.async_update_entry(entry, options={**entry.options, "geocoding": False})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await start_trip(hass, entry, psacc)
    assert (await active(hass, entry))["start_ort"] == "Unbekannter Ort" and psacc.geo_calls == []


async def test_no_position_unknown_place(hass, setup, psacc):
    m = setup.runtime_data.manager
    assert await m.resolve_ort(None, None) == "Unbekannter Ort"
    assert psacc.geo_calls == []


# --- Wakeup ------------------------------------------------------------------
async def test_hourly_wakeup(hass, setup, psacc, freezer):
    assert psacc.calls("/wakeup/") == []
    freezer.move_to("2026-01-01 13:00:00+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(psacc.calls("/wakeup/")) == 1
    freezer.move_to("2026-01-01 14:00:00+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(psacc.calls("/wakeup/")) == 2


async def test_no_hourly_wakeup_when_disabled(hass, entry, psacc, freezer):
    hass.config_entries.async_update_entry(entry, options={**entry.options, "wakeup_stuendlich": False})
    assert await hass.config_entries.async_setup(entry.entry_id)
    freezer.move_to("2026-01-01 13:00:00+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert psacc.calls("/wakeup/") == []


async def test_wakeup_at_charge_end(hass, entry, psacc):
    hass.states.async_set("binary_sensor.wallbox_laedt", "off")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "wakeup_stuendlich": False, "wakeup_bei_ladeende_entity": "binary_sensor.wallbox_laedt"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.wallbox_laedt", "on")
    await hass.async_block_till_done()
    assert psacc.calls("/wakeup/") == []  # Ladebeginn loest nichts aus
    hass.states.async_set("binary_sensor.wallbox_laedt", "off")
    await hass.async_block_till_done()
    assert len(psacc.calls("/wakeup/")) == 1
    hass.states.async_set("binary_sensor.wallbox_laedt", "unavailable")
    hass.states.async_set("binary_sensor.wallbox_laedt", "off")
    await hass.async_block_till_done()
    assert len(psacc.calls("/wakeup/")) == 1


async def test_wakeup_failure_is_not_fatal(hass, setup, psacc):
    psacc.wakeup_fail = True
    await hass.services.async_call("psacc_fahrtenbuch", "wakeup", {}, blocking=True)
    assert len(psacc.calls("/wakeup/")) == 1


async def test_unload_cancels_listeners(hass, setup, psacc, freezer):
    await hass.config_entries.async_unload(setup.entry_id)
    freezer.move_to("2026-01-01 13:00:00+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert psacc.calls("/wakeup/") == []
