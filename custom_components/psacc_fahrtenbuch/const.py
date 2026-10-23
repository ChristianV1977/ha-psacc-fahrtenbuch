"""Konstanten der Integration psacc_fahrtenbuch."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "psacc_fahrtenbuch"
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.TIME,
]

CONF_URL = "url"
CONF_VIN = "vin"
CONF_CAPACITY = "kapazitaet_kwh"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_WAKEUP_HOURLY = "wakeup_stuendlich"
CONF_WAKEUP_CHARGE_ENTITY = "wakeup_bei_ladeende_entity"
CONF_GEOCODE = "geocoding"
CONF_USER_AGENT = "user_agent"

DEFAULT_URL = "http://b9f12d83-psacc:5000"
DEFAULT_CAPACITY = 50.0
DEFAULT_SCAN_INTERVAL = 20
DEFAULT_USER_AGENT = "ha-psacc-fahrtenbuch (Home Assistant custom integration)"

SOH_INTERVAL = 3600  # s
CHARGE_CONTROL_INTERVAL = 60  # s
SOC_RESYNC_DELAY = 90  # s nach Zuendung: SoC-Startwert nachreichen
FRESH_SECONDS = 1800  # Cloud-Daten aelter als 30 min -> Hinweis
GEOCODE_MIN_INTERVAL = 1.0  # s, Nominatim-Nutzungsrichtlinie

SIGNAL_VIEWS = f"{DOMAIN}_views_{{}}"  # .format(entry_id)
EVENT_TRIP = f"{DOMAIN}_fahrt_erfasst"
