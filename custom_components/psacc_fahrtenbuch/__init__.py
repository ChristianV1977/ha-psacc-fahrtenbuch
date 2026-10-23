"""PSA Car Controller Fahrtenbuch: Fahrzeugdaten und Fahrtenbuch auf Basis des Add-ons PSA Car Controller."""
from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import PsaccClient
from .const import CONF_SCAN_INTERVAL, CONF_URL, CONF_VIN, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import PsaccCoordinator
from .db import TRIP_FIELDS
from .manager import Manager

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FRONTEND_URL = f"/{DOMAIN}/frontend"
CARD_FILE = "psacc-fahrzeug-card.js"
_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Mitgelieferte Lovelace-Karte ausliefern und als Modul laden (nur einmal pro HA-Lauf)."""
    if hass.data.get(_FRONTEND_REGISTERED):
        return
    hass.data[_FRONTEND_REGISTERED] = True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)])
    version = (await async_get_integration(hass, DOMAIN)).version
    frontend.add_extra_js_url(hass, f"{FRONTEND_URL}/{CARD_FILE}?v={version}")


@dataclass
class RuntimeData:
    coordinator: PsaccCoordinator
    manager: Manager


type PsaccConfigEntry = ConfigEntry[RuntimeData]


def _manager(hass: HomeAssistant) -> Manager:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Integration ist nicht geladen")
    return entries[0].runtime_data.manager


_TRIP_SCHEMA = vol.Schema({
    vol.Required("start_zeit"): cv.string, vol.Required("start_ort"): cv.string,
    vol.Required("end_zeit"): cv.string, vol.Required("end_ort"): cv.string,
    vol.Required("distanz_km"): vol.Coerce(float), vol.Required("dauer_min"): vol.Coerce(float),
    vol.Required("geschwindigkeit_kmh"): vol.Coerce(float), vol.Required("verbrauch_kwh"): vol.Coerce(float),
    vol.Required("soc_start"): vol.Coerce(int), vol.Required("soc_end"): vol.Coerce(int),
    vol.Required("km_start"): vol.Coerce(float), vol.Required("km_end"): vol.Coerce(float),
    vol.Optional("hinweis", default=""): cv.string, vol.Optional("soc_anstieg", default=""): cv.string,
})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def hinweis_setzen(call: ServiceCall) -> None:
        await _manager(hass).async_set_hinweis(call.data["fahrt_id"], call.data["hinweis"])

    async def soc_anstieg_setzen(call: ServiceCall) -> None:
        m = _manager(hass)
        wert = "X" if call.data["wert"] else ""
        if not await hass.async_add_executor_job(m.db.set_soc_anstieg, call.data["fahrt_id"], wert):
            raise ServiceValidationError(f"Fahrt {call.data['fahrt_id']} existiert nicht")
        await m.async_refresh_views()

    async def fahrten_abfragen(call: ServiceCall) -> dict:
        m = _manager(hass)
        if call.data.get("gesamt"):
            from homeassistant.util import dt as dt_util
            return await hass.async_add_executor_job(m.db.overall, dt_util.now().replace(tzinfo=None))
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        return await hass.async_add_executor_job(
            m.db.month, call.data["jahr"] or now.year, call.data["monat"] or now.month)

    async def fahrt_hinzufuegen(call: ServiceCall) -> dict:
        rec = {f: call.data[f] for f in TRIP_FIELDS}
        return {"id": await _manager(hass).async_add_trip(rec)}

    async def auswahl_setzen(call: ServiceCall) -> None:
        await _manager(hass).async_set_selection(call.data.get("jahr"), call.data.get("monat"))

    async def wakeup(call: ServiceCall) -> None:
        await _manager(hass).async_wakeup()

    reg = hass.services.async_register
    reg(DOMAIN, "hinweis_setzen", hinweis_setzen, vol.Schema({
        vol.Required("fahrt_id"): vol.Coerce(int), vol.Required("hinweis"): cv.string}))
    reg(DOMAIN, "soc_anstieg_setzen", soc_anstieg_setzen, vol.Schema({
        vol.Required("fahrt_id"): vol.Coerce(int), vol.Required("wert"): cv.boolean}))
    reg(DOMAIN, "fahrten_abfragen", fahrten_abfragen, vol.Schema({
        vol.Optional("jahr", default=0): vol.Coerce(int), vol.Optional("monat", default=0): vol.All(vol.Coerce(int), vol.Range(0, 12)),
        vol.Optional("gesamt", default=False): cv.boolean}), supports_response=SupportsResponse.ONLY)
    reg(DOMAIN, "fahrt_hinzufuegen", fahrt_hinzufuegen, _TRIP_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "auswahl_setzen", auswahl_setzen, vol.Schema({
        vol.Optional("jahr"): vol.Coerce(int), vol.Optional("monat"): vol.All(vol.Coerce(int), vol.Range(1, 12))}))
    reg(DOMAIN, "wakeup", wakeup, vol.Schema({}))
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PsaccConfigEntry) -> bool:
    client = PsaccClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_VIN])
    coordinator = PsaccCoordinator(hass, entry, client, entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    await coordinator.async_config_entry_first_refresh()
    manager = Manager(hass, entry, coordinator)
    await manager.async_setup()
    entry.runtime_data = RuntimeData(coordinator, manager)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PsaccConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry.runtime_data.manager.async_unload()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: PsaccConfigEntry) -> None:
    """Nur den kleinen Auswahl-Store entfernen; fahrten.db bleibt bewusst erhalten (Fahrtdaten)."""
    from homeassistant.helpers.storage import Store
    await Store(hass, 1, f"psacc_fahrtenbuch.{entry.entry_id}").async_remove()
