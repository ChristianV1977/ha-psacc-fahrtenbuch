"""SQLite-Persistenz des Fahrtenbuchs (Schema kompatibel zur frueheren fahrten.db).

Jede Methode oeffnet eine eigene Verbindung und ist fuer den Aufruf im Executor gedacht.
Tabellen: fahrten, monatswerte (Cache NUR abgeschlossener Monate), laufende_fahrt (1 Zeile).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from .trips import aggregates, finalize

TRIP_FIELDS = (
    "start_zeit", "start_ort", "end_zeit", "end_ort", "distanz_km", "dauer_min",
    "geschwindigkeit_kmh", "verbrauch_kwh", "soc_start", "soc_end", "km_start",
    "km_end", "hinweis", "soc_anstieg",
)
_SELECT = "id, " + ", ".join(TRIP_FIELDS) + ", erfasst_am"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fahrten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_zeit TEXT NOT NULL, start_ort TEXT NOT NULL,
    end_zeit TEXT NOT NULL, end_ort TEXT NOT NULL,
    distanz_km REAL NOT NULL, dauer_min REAL NOT NULL,
    geschwindigkeit_kmh REAL NOT NULL, verbrauch_kwh REAL NOT NULL,
    soc_start INTEGER NOT NULL, soc_end INTEGER NOT NULL,
    km_start REAL NOT NULL, km_end REAL NOT NULL,
    hinweis TEXT NOT NULL DEFAULT '',
    erfasst_am TEXT NOT NULL,
    soc_anstieg TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fahrten_start_zeit ON fahrten(start_zeit);
CREATE TABLE IF NOT EXISTS monatswerte (
    jahr INTEGER NOT NULL, monat INTEGER NOT NULL,
    anzahl_fahrten INTEGER NOT NULL, gesamt_km REAL NOT NULL, gesamt_kwh REAL NOT NULL,
    PRIMARY KEY (jahr, monat)
);
CREATE TABLE IF NOT EXISTS laufende_fahrt (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    start_zeit TEXT NOT NULL, start_ort TEXT NOT NULL,
    km_start REAL NOT NULL, soc_start REAL NOT NULL, sync_ts TEXT
);
"""


class TripDB:
    def __init__(self, path: str) -> None:
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with closing(self._conn()) as c:
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(fahrten)")}
            if "soc_anstieg" not in cols:  # DB aus der Zeit vor der Spalte
                c.execute("ALTER TABLE fahrten ADD COLUMN soc_anstieg TEXT NOT NULL DEFAULT ''")
            c.commit()

    # --- Schreiben -------------------------------------------------------
    def insert_trip(self, rec: dict[str, Any]) -> int:
        vals = [rec[f] for f in TRIP_FIELDS]
        erfasst = datetime.now(timezone.utc).isoformat()
        with closing(self._conn()) as c:
            cur = c.execute(
                f"INSERT INTO fahrten ({', '.join(TRIP_FIELDS)}, erfasst_am) "
                f"VALUES ({', '.join('?' * (len(TRIP_FIELDS) + 1))})",
                [*vals, erfasst],
            )
            # Cache des betroffenen Monats verwerfen (rueckwirkende Nachtraege machen ihn sonst falsch)
            c.execute(
                "DELETE FROM monatswerte WHERE jahr = ? AND monat = ?",
                (int(rec["start_zeit"][:4]), int(rec["start_zeit"][5:7])),
            )
            c.commit()
            return int(cur.lastrowid)

    def set_hinweis(self, trip_id: int, text: str) -> bool:
        with closing(self._conn()) as c:
            cur = c.execute("UPDATE fahrten SET hinweis = ? WHERE id = ?", (text, trip_id))
            c.commit()
            return cur.rowcount > 0

    def set_soc_anstieg(self, trip_id: int, wert: str) -> bool:
        with closing(self._conn()) as c:
            cur = c.execute("UPDATE fahrten SET soc_anstieg = ? WHERE id = ?", (wert, trip_id))
            c.commit()
            return cur.rowcount > 0

    # --- Lesen -----------------------------------------------------------
    def get_hinweis(self, trip_id: int) -> str | None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT hinweis FROM fahrten WHERE id = ?", (trip_id,)).fetchone()
        return None if row is None else row["hinweis"]

    def month(self, jahr: int, monat: int) -> dict[str, Any]:
        key = f"{jahr:04d}-{monat:02d}"
        with closing(self._conn()) as c:
            rows = c.execute(
                f"SELECT {_SELECT} FROM fahrten WHERE substr(start_zeit, 1, 7) = ? ORDER BY start_zeit DESC",
                (key,),
            ).fetchall()
        trips = [dict(r) for r in rows]
        return {"trips": trips, "jahr": jahr, "monat": f"{monat:02d}", **aggregates(trips)}

    def overall(self, now: datetime) -> dict[str, Any]:
        """Summe aller Monate: Cache fuer abgeschlossene Monate + Live-Summe des laufenden."""
        cur_ym = (now.year, now.month)
        with closing(self._conn()) as c:
            for r in c.execute(
                "SELECT DISTINCT CAST(substr(start_zeit,1,4) AS INTEGER) j, CAST(substr(start_zeit,6,2) AS INTEGER) m FROM fahrten"
            ).fetchall():
                j, m = r["j"], r["m"]
                if (j, m) >= cur_ym:
                    continue
                if c.execute("SELECT 1 FROM monatswerte WHERE jahr=? AND monat=?", (j, m)).fetchone():
                    continue
                n, km, kwh = c.execute(
                    "SELECT COUNT(*), COALESCE(SUM(distanz_km),0), COALESCE(SUM(verbrauch_kwh),0) "
                    "FROM fahrten WHERE substr(start_zeit,1,7) = ?",
                    (f"{j:04d}-{m:02d}",),
                ).fetchone()
                c.execute(
                    "INSERT OR REPLACE INTO monatswerte VALUES (?,?,?,?,?)",
                    (j, m, n, round(km, 1), round(kwh, 2)),
                )
            c.commit()
            cn, ckm, ckwh = c.execute(
                "SELECT COALESCE(SUM(anzahl_fahrten),0), COALESCE(SUM(gesamt_km),0), COALESCE(SUM(gesamt_kwh),0) FROM monatswerte"
            ).fetchone()
            ln, lkm, lkwh = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(distanz_km),0), COALESCE(SUM(verbrauch_kwh),0) "
                "FROM fahrten WHERE substr(start_zeit,1,7) = ?",
                (f"{now.year:04d}-{now.month:02d}",),
            ).fetchone()
        return finalize(cn + ln, ckm + lkm, ckwh + lkwh)

    def checksum(self) -> dict[str, Any]:
        with closing(self._conn()) as c:
            n, km, kwh = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(distanz_km),0), COALESCE(SUM(verbrauch_kwh),0) FROM fahrten"
            ).fetchone()
        return {"anzahl": n, "km": round(km, 1), "kwh": round(kwh, 2)}

    # --- laufende Fahrt --------------------------------------------------
    def get_active(self) -> dict[str, Any] | None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM laufende_fahrt WHERE id = 1").fetchone()
        return None if row is None else dict(row)

    def set_active(self, data: dict[str, Any] | None) -> None:
        with closing(self._conn()) as c:
            c.execute("DELETE FROM laufende_fahrt")
            if data is not None:
                c.execute(
                    "INSERT INTO laufende_fahrt (id, start_zeit, start_ort, km_start, soc_start, sync_ts) VALUES (1,?,?,?,?,?)",
                    (data["start_zeit"], data["start_ort"], data["km_start"], data["soc_start"], data.get("sync_ts")),
                )
            c.commit()

    def years(self) -> list[int]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT DISTINCT CAST(substr(start_zeit,1,4) AS INTEGER) y FROM fahrten ORDER BY y").fetchall()
        return [r["y"] for r in rows]
