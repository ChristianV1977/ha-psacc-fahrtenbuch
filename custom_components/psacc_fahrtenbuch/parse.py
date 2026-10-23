"""Reines Parsen der psacc-Antwort /get_vehicleinfo (ohne Home-Assistant-Imports)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DUR = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")

FAILURE_CAUSES = {
    "Defect": "defect",
    "DoorOpened": "door_opened",
    "LowBattery": "low_battery",
    "LowFuelLevel": "low_fuel",
    "TooManyUnusedProg": "too_many_programs",
}
CHARGING_STATUS = {
    "Failure": "failure",
    "InProgress": "in_progress",
    "Stopped": "stopped",
    "Finished": "finished",
    "Disconnected": "disconnected",
}
CHARGING_MODE = {"Fast": "fast", "Slow": "slow"}


def dig(obj: Any, *path: Any, default: Any = None) -> Any:
    """Sicherer Zugriff auf verschachtelte dict/list-Strukturen."""
    for key in path:
        try:
            obj = obj[key]
        except (KeyError, IndexError, TypeError):
            return default
        if obj is None:
            return default
    return obj


def parse_iso_duration_minutes(value: Any) -> float | None:
    """ISO-8601-Dauer (z. B. PT1H30M) in Minuten; None bei ungueltig/leer."""
    if not isinstance(value, str):
        return None
    m = _DUR.match(value)
    if not m or value in ("P", "PT"):
        return None
    d, h, mi, s = m.groups()
    return int(d or 0) * 1440 + int(h or 0) * 60 + int(mi or 0) + float(s or 0) / 60


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt


def _num(value: Any, cast=float) -> Any:
    try:
        return cast(float(value))
    except (TypeError, ValueError):
        return None


def parse_info(info: dict | None) -> dict[str, Any]:
    """Aus der psacc-Antwort alle von der Integration genutzten Werte ziehen."""
    info = info or {}
    energy = dig(info, "energy", 0, default={}) or {}
    charging = energy.get("charging") or {}
    coords = dig(info, "last_position", "geometry", "coordinates")
    lat = lon = None
    if isinstance(coords, list) and len(coords) >= 2:
        lon, lat = _num(coords[0]), _num(coords[1])
    voltage = _num(dig(info, "battery", "voltage"))
    day = dig(info, "environment", "luminosity", "day")
    return {
        "soc": _num(energy.get("level"), int),
        "reichweite": _num(energy.get("autonomy"), int),
        "kilometerstand": _num(dig(info, "timed_odometer", "mileage")),
        "batteriespannung": round(voltage * 4, 1) if voltage is not None else None,
        "umgebungstemperatur": _num(dig(info, "environment", "air", "temp")),
        "umgebungslicht": None if day is None else ("day" if day else "night"),
        "zuendung": dig(info, "ignition", "type"),
        "geschwindigkeit": _num(dig(info, "kinetic", "speed")),
        "in_bewegung": dig(info, "kinetic", "moving"),
        "tueren": dig(info, "doors_state"),
        "angesteckt": bool(charging.get("plugged")) if energy else None,
        "lademodus": CHARGING_MODE.get(charging.get("charging_mode"), "none") if energy else None,
        "laderate": charging.get("charging_rate"),
        "ladestatus": CHARGING_STATUS.get(charging.get("status"), "unknown") if energy else None,
        "verbleibende_ladezeit": parse_iso_duration_minutes(charging.get("remaining_time")),
        "vorklimatisierung_status": dig(info, "preconditionning", "air_conditioning", "status"),
        "vorklimatisierung_fehler": FAILURE_CAUSES.get(
            dig(info, "preconditionning", "air_conditioning", "failure_cause"), None
        ),
        "letztes_update": parse_dt(energy.get("updated_at")),
        "lat": lat,
        "lon": lon,
    }
