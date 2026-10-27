"""Vorklimatisierung: Zustandsableitung und Auswertung des Add-on-Logs (reine Logik, ohne Home-Assistant-Imports)."""
from __future__ import annotations

import ast
import json
import math
import re
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo
from typing import Any

RUN_MINUTES = 20  # ungestoerter Lauf laut Auswertung 24.10.
START_TIMEOUT = timedelta(minutes=2)  # danach gilt der Befehl als "nicht gestartet"
NOT_STARTED_HOLD = timedelta(minutes=30)  # so lange bleibt "nicht gestartet" sichtbar
STATES = ["aus", "angefordert", "laeuft", "beendet", "nicht_gestartet", "fehlgeschlagen"]


class PrecondTracker:
    """Leitet aus dem rohen psacc-Status plus Befehlszeitpunkt einen verstaendlichen Zustand ab.

    shortcut: Zustand liegt nur im Speicher; nach einem HA-Neustart mitten im Lauf beginnt die Restlaufzeit neu, bei Bedarf persistieren.
    """

    def __init__(self) -> None:
        self.requested_at: datetime | None = None
        self.started_at: datetime | None = None

    def request(self, on: bool, now: datetime) -> None:
        self.requested_at = now if on else None
        self.started_at = None

    def update(self, status: str | None, failure: str | None, now: datetime) -> dict[str, Any]:
        if status == "Enabled":
            if self.started_at is None:
                self.started_at = now
            self.requested_at = None
            left = RUN_MINUTES - (now - self.started_at).total_seconds() / 60
            return {"vorklimatisierung_zustand": "laeuft", "vorklimatisierung_restlaufzeit": max(0, math.ceil(left))}
        self.started_at = None
        out = {"vorklimatisierung_restlaufzeit": None}
        if self.requested_at is not None:
            age = now - self.requested_at
            if age <= START_TIMEOUT:
                state = "angefordert"
            elif age <= NOT_STARTED_HOLD:
                state = "nicht_gestartet"
            else:
                self.requested_at = None
                state = self._idle(status, failure)
        else:
            state = self._idle(status, failure)
        return {**out, "vorklimatisierung_zustand": state}

    @staticmethod
    def _idle(status: str | None, failure: str | None) -> str:
        if failure:
            return "fehlgeschlagen"
        return "beendet" if status == "Finished" else "aus"


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ :: \w+ :: (.*)$")
_MQTT = re.compile(r"^mqtt msg received: \S+ (b'.*'|b\".*\")$")
_CMD = re.compile(r"^(?:Preconditioning: )?topic: \S+/ThermalPrecond: (\{.*\})$")
MAX_TEXT = 200


def _clean(text: str, vin: str | None) -> str:
    if vin:
        text = text.replace(vin, "VIN")
    return text[:MAX_TEXT]


def _payload(raw: str) -> dict | None:
    try:
        data = json.loads(ast.literal_eval(raw).decode())
    except (ValueError, SyntaxError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _cmd_text(raw: str) -> str:
    """Befehls-Payload (Python-Dict mit einfachen Quotes) -> 'asap=<wert>'."""
    try:
        d = ast.literal_eval(raw)
        return f"asap={d['asap']}"
    except (ValueError, SyntaxError, KeyError, TypeError):
        return raw


def _utc(ts: str, tz: tzinfo) -> str:
    """Log-Zeitstempel (lokal, ohne Zone) -> UTC-ISO mit Z."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ts


def parse_log(text: str, vin: str | None = None, tz: tzinfo | None = None) -> list[dict[str, str]]:
    """ThermalPrecond-Zeilen aus dem Add-on-Log; ohne VIN, Konto-ID und correlation_id. Aelteste zuerst."""
    tz = tz or ZoneInfo("Europe/Berlin")
    out: list[dict[str, str]] = []
    for line in _ANSI.sub("", text or "").splitlines():
        m = _LINE.match(line.strip())
        if not m or "ThermalPrecond" not in m.group(2):
            continue
        ts, msg = m.groups()
        ts = _utc(ts, tz)
        entry = {"zeit": ts, "art": "log", "code": "", "text": ""}
        if c := _CMD.match(msg):
            entry.update(art="befehl", text=_clean(_cmd_text(c.group(1)), vin))
        elif (q := _MQTT.match(msg)) and (d := _payload(q.group(1))) is not None:
            entry["zeit"] = str(d.get("process_date") or d.get("resp_date") or ts)
            if "return_code" in d:
                entry.update(art="antwort", code=str(d["return_code"]), text=_clean(f"return_code {d['return_code']}", vin))
            elif "process_code" in d:
                entry.update(art="prozess", code=str(d["process_code"]), text=_clean(str(d.get("process_message", "")), vin))
            else:
                entry["text"] = _clean(json.dumps({k: v for k, v in d.items() if k not in ("vin", "correlation_id")}), vin)
        else:
            entry["text"] = _clean(re.sub(r"\S*/cid/\S+", "", msg), vin)
        out.append(entry)
    return out


def merge_log(old: list[dict], new: list[dict], keep: int = 30) -> list[dict]:
    """Neue Eintraege ohne Duplikate anhaengen, die letzten `keep` behalten (aelteste zuerst)."""
    seen = {(e["zeit"], e["art"], e["code"], e["text"]) for e in old}
    merged = list(old)
    for e in new:
        key = (e["zeit"], e["art"], e["code"], e["text"])
        if key not in seen:
            seen.add(key)
            merged.append(e)
    return merged[-keep:]
