"""Tests der reinen Logik (Parsen, Formeln, SQLite) mit fiktiven/anonymisierten Daten."""
import json, pathlib
from datetime import datetime

import pytest

from custom_components.psacc_fahrtenbuch.db import TripDB
from custom_components.psacc_fahrtenbuch.parse import parse_info, parse_iso_duration_minutes
from custom_components.psacc_fahrtenbuch.trips import compute_trip, format_ort, is_fresh

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_fixture():
    p = parse_info(json.loads((FIX / "vehicleinfo.json").read_text()))
    assert p["soc"] == 53 and p["reichweite"] == 118 and p["kilometerstand"] == 38061.2
    assert p["batteriespannung"] == 242.0  # Spannung x4 wie bisher
    assert p["zuendung"] == "Stop" and p["ladestatus"] == "disconnected" and p["lademodus"] == "none"
    assert p["angesteckt"] is True and p["umgebungslicht"] == "day"
    assert p["verbleibende_ladezeit"] == 0 and p["letztes_update"].year == 2026
    assert (p["lat"], p["lon"]) == (50.0, 8.0)


def test_parse_empty_never_raises():
    p = parse_info({})
    assert p["soc"] is None and p["angesteckt"] is None and p["lat"] is None


@pytest.mark.parametrize("v,exp", [("PT1H30M", 90), ("PT13H", 780), ("PT0S", 0), ("P1DT2H", 1560), (None, None), ("x", None)])
def test_duration(v, exp):
    assert parse_iso_duration_minutes(v) == exp


def test_format_ort():
    assert format_ort({"address": {"road": "Teststr.", "town": "Beispielstadt"}}) == "Teststr., Beispielstadt"
    assert format_ort({"address": {"industrial": "Gewerbepark", "city": "Ort"}}) == "Gewerbepark, Ort"
    assert format_ort({"address": {"village": "Dorf"}}) == "Dorf"
    assert format_ort({}) == "Unbekannter Ort" and format_ort(None) == "Unbekannter Ort"
    assert format_ort({"address": {"road": "A<b>;rm", "city": "X"}}) == "Abrm, X"


def trip(**kw):
    base = dict(start_zeit="2026-01-01 08:00:00", start_ort="A", end_zeit="2026-01-01 08:30:00", end_ort="B",
                km_start=1000.0, km_end=1015.0, soc_start=60, soc_end=56, kapazitaet=50.0, frisch=True)
    base.update(kw)
    return compute_trip(**base)


def test_formulas_like_before():
    t = trip()
    assert t["distanz_km"] == 15.0 and t["dauer_min"] == 30.0 and t["geschwindigkeit_kmh"] == 30.0
    assert t["verbrauch_kwh"] == 2.0 and t["hinweis"] == "" and t["soc_anstieg"] == ""


def test_soc_rise_and_anomalies():
    t = trip(soc_end=60, km_end=990, frisch=False)
    assert t["verbrauch_kwh"] == 0 and t["soc_anstieg"] == "X" and t["distanz_km"] == 0
    assert t["hinweis"] == "Cloud-Daten evtl. veraltet; Kilometerstand-Anomalie ignoriert"
    assert t["dauer_min"] == 30.0


def test_zero_duration_min_clamp():
    t = trip(end_zeit="2026-01-01 08:00:00")
    assert t["dauer_min"] == 0.1 and t["geschwindigkeit_kmh"] == 0


def test_fresh():
    now = datetime(2026, 1, 1, 12, 0)
    assert is_fresh(datetime(2026, 1, 1, 11, 45), now) and not is_fresh(datetime(2026, 1, 1, 11, 0), now)
    assert not is_fresh(None, now)


@pytest.fixture
def db(tmp_path):
    d = TripDB(str(tmp_path / "x" / "fahrten.db"))
    d.init()
    return d


def test_db_roundtrip_and_cache(db):
    ids = [db.insert_trip(trip(start_zeit=f"2026-0{m}-05 08:00:00", end_zeit=f"2026-0{m}-05 08:30:00")) for m in (1, 1, 2)]
    assert ids == [1, 2, 3]
    now = datetime(2026, 3, 10)
    assert db.month(2026, 1)["anzahl"] == 2 and db.month(2026, 4)["anzahl"] == 0
    o = db.overall(now)
    assert o["anzahl"] == 3 and o["gesamt_km"] == 45.0 and o["gesamt_kwh"] == 6.0 and o["kwh_pro_100km"] == 13.3
    # rueckwirkender Nachtrag in einen bereits gecachten Monat darf den Cache nicht veralten lassen
    db.insert_trip(trip(start_zeit="2026-01-06 08:00:00", end_zeit="2026-01-06 08:30:00"))
    assert db.overall(now)["anzahl"] == 4 and db.overall(now)["gesamt_km"] == 60.0


def test_db_hinweis_and_active(db):
    tid = db.insert_trip(trip())
    assert db.set_hinweis(tid, "Test") and db.get_hinweis(tid) == "Test"
    assert not db.set_hinweis(999, "x") and db.get_hinweis(999) is None
    assert db.set_soc_anstieg(tid, "X")
    assert db.get_active() is None
    db.set_active({"start_zeit": "2026-01-01 08:00:00", "start_ort": "A", "km_start": 1.0, "soc_start": 50.0, "sync_ts": None})
    assert db.get_active()["soc_start"] == 50.0
    db.set_active(None)
    assert db.get_active() is None


def test_month_sorted_desc(db):
    db.insert_trip(trip(start_zeit="2026-05-01 08:00:00", end_zeit="2026-05-01 09:00:00"))
    db.insert_trip(trip(start_zeit="2026-05-02 08:00:00", end_zeit="2026-05-02 09:00:00"))
    assert [t["start_zeit"][:10] for t in db.month(2026, 5)["trips"]] == ["2026-05-02", "2026-05-01"]
