#!/usr/bin/env python3
"""Selbsttest gegen eine KOPIE einer echten fahrten.db (Pfad als Argument; nie im Repo ablegen).

Prueft: Schema-Migration idempotent, Monats-/Gesamtsummen gleich einer unabhaengigen SUM()-Rechnung,
Hinweis-Roundtrip (Wert wird gesetzt und exakt wiederhergestellt). Gibt nur Zaehler aus, keine Inhalte.
"""
import sqlite3, sys, pathlib
from datetime import datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from custom_components.psacc_fahrtenbuch.db import TripDB

path = sys.argv[1]
db = TripDB(path)
db.init(); db.init()  # idempotent
raw = sqlite3.connect(path)
n, km, kwh = raw.execute("select count(*), round(sum(distanz_km),1), round(sum(verbrauch_kwh),2) from fahrten").fetchone()
o = db.overall(datetime.now())
assert (o["anzahl"], o["gesamt_km"], o["gesamt_kwh"]) == (n, km, kwh), (o, n, km, kwh)
for (ym, c, k, e) in raw.execute("select substr(start_zeit,1,7), count(*), round(sum(distanz_km),1), round(sum(verbrauch_kwh),2) from fahrten group by 1"):
    m = db.month(int(ym[:4]), int(ym[5:]))
    assert (m["anzahl"], m["gesamt_km"], m["gesamt_kwh"]) == (c, k, e), ym
    assert len(m["trips"]) == c
tid, old = raw.execute("select id, hinweis from fahrten order by id limit 1").fetchone()
assert db.set_hinweis(tid, "selbsttest") and db.get_hinweis(tid) == "selbsttest"
assert db.set_hinweis(tid, old) and db.get_hinweis(tid) == old
print(f"OK: {n} Fahrten, {km} km, {kwh} kWh, Monate geprueft, Hinweis-Roundtrip identisch")
