"""Fahrtenbuch-Formeln (exakt wie die fruehere YAML-Automation), ohne HA-Imports."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .const import FRESH_SECONDS

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Prioritaet: Strassen, dann Flaechen, POIs, Orts-Unterebenen; erst danach die Stadt.
ORT_KEYS = [
    "road", "pedestrian", "footway", "cycleway", "path", "track", "bridleway",
    "living_street", "residential", "industrial", "commercial", "retail",
    "construction", "farm", "farmyard", "amenity", "shop", "tourism", "leisure",
    "natural", "man_made", "building", "hamlet", "isolated_dwelling",
    "neighbourhood", "quarter", "suburb", "city_district", "borough",
]
_ORT_CLEAN = re.compile(r"[^A-Za-z0-9äöüÄÖÜß .,-]")
UNKNOWN_PLACE = "Unbekannter Ort"


def clean_ort(text: str) -> str:
    return _ORT_CLEAN.sub("", text).strip()


def format_ort(nominatim: dict | None) -> str:
    """Nominatim-Antwort (jsonv2, addressdetails=1) -> 'Strasse, Ort'."""
    addr = (nominatim or {}).get("address") or {}
    strasse = next((addr[k] for k in ORT_KEYS if addr.get(k)), "")
    ort = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
    if strasse and ort:
        roh = f"{strasse}, {ort}"
    else:
        roh = ort or strasse or UNKNOWN_PLACE
    return clean_ort(roh)


def fmt_local(dt: datetime) -> str:
    return dt.strftime(TIME_FMT)


def is_fresh(updated_at: datetime | None, now: datetime) -> bool:
    if updated_at is None:
        return False
    return (now - updated_at).total_seconds() < FRESH_SECONDS


def compute_trip(
    *,
    start_zeit: str,
    start_ort: str,
    end_zeit: str,
    end_ort: str,
    km_start: float,
    km_end: float,
    soc_start: float,
    soc_end: float,
    kapazitaet: float,
    frisch: bool,
) -> dict[str, Any]:
    """Berechnet einen Fahrtdatensatz; Rundungen wie das fruehere append_trip.py."""
    distanz_roh = km_end - km_start
    dauer_roh = (datetime.strptime(end_zeit, TIME_FMT) - datetime.strptime(start_zeit, TIME_FMT)).total_seconds() / 60
    distanz = distanz_roh if distanz_roh > 0 else 0
    dauer = dauer_roh if dauer_roh > 0.1 else 0.1
    delta = soc_start - soc_end
    verbrauch = (delta / 100 * kapazitaet) if delta > 0 else 0
    speed = round(distanz / (dauer / 60), 1) if dauer > 0.1 else 0
    hinweise = []
    if not frisch:
        hinweise.append("Cloud-Daten evtl. veraltet")
    if distanz_roh < 0:
        hinweise.append("Kilometerstand-Anomalie ignoriert")
    return {
        "start_zeit": start_zeit,
        "start_ort": start_ort,
        "end_zeit": end_zeit,
        "end_ort": end_ort,
        "distanz_km": round(float(distanz), 1),
        "dauer_min": round(float(dauer), 1),
        "geschwindigkeit_kmh": round(float(speed), 1),
        "verbrauch_kwh": round(float(verbrauch), 2),
        "soc_start": int(float(soc_start)),
        "soc_end": int(float(soc_end)),
        "km_start": round(float(km_start), 1),
        "km_end": round(float(km_end), 1),
        "hinweis": "; ".join(hinweise),
        "soc_anstieg": "X" if delta <= 0 else "",
    }


def aggregates(trips: list[dict]) -> dict[str, Any]:
    n = len(trips)
    km = round(sum(t["distanz_km"] for t in trips), 1) if n else 0
    kwh = round(sum(t["verbrauch_kwh"] for t in trips), 2) if n else 0
    return finalize(n, km, kwh)


def finalize(n: int, km: float, kwh: float) -> dict[str, Any]:
    km, kwh = round(km, 1), round(kwh, 2)
    return {
        "anzahl": n,
        "gesamt_km": km,
        "gesamt_kwh": kwh,
        "avg_kwh_pro_fahrt": round(kwh / n, 2) if n > 0 else 0,
        "kwh_pro_100km": round(kwh / km * 100, 1) if km > 0 else 0,
    }


__all__ = ["compute_trip", "format_ort", "is_fresh", "aggregates", "finalize", "fmt_local"]
