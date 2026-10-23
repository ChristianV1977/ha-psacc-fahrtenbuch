"""Fahrtenbuch-Engine: Zuendungserkennung, Ortsaufloesung, Persistenz, Wakeup, Auswahl/Hinweis-Bearbeitung."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.zone import ENTITY_ID_HOME, async_active_zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import PsaccError
from .const import (
    CONF_GEOCODE, CONF_USER_AGENT, CONF_WAKEUP_CHARGE_ENTITY, CONF_WAKEUP_HOURLY, CONF_CAPACITY,
    DEFAULT_CAPACITY, DEFAULT_USER_AGENT, EVENT_TRIP, GEOCODE_MIN_INTERVAL, SIGNAL_VIEWS, SOC_RESYNC_DELAY,
)
from .coordinator import PsaccCoordinator
from .db import TripDB
from .trips import UNKNOWN_PLACE, clean_ort, compute_trip, fmt_local, format_ort, is_fresh

_LOGGER = logging.getLogger(__name__)
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


class Manager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: PsaccCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.db = TripDB(hass.config.path("psacc_fahrtenbuch", "fahrten.db"))
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"psacc_fahrtenbuch.{entry.entry_id}")
        self.cfg: dict[str, Any] = {}
        self.month_data: dict[str, Any] = {"trips": [], "anzahl": 0, "gesamt_km": 0, "gesamt_kwh": 0,
                                           "avg_kwh_pro_fahrt": 0, "kwh_pro_100km": 0}
        self.overall_data: dict[str, Any] = {"anzahl": 0, "gesamt_km": 0, "gesamt_kwh": 0,
                                             "avg_kwh_pro_fahrt": 0, "kwh_pro_100km": 0}
        self.active: dict[str, Any] | None = None
        self.draft = ""
        self._prev_ign: str | None = None
        self._lock = asyncio.Lock()
        self._geo_lock = asyncio.Lock()
        self._geo_last = 0.0
        self._unsub: list[CALLBACK_TYPE] = []
        self._resync: CALLBACK_TYPE | None = None

    # --- Lebenszyklus ----------------------------------------------------
    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(self.db.init)
        now = dt_util.now()
        saved = await self.store.async_load() or {}
        self.cfg = {
            "kapazitaet": float(saved.get("kapazitaet", self.entry.options.get(CONF_CAPACITY, DEFAULT_CAPACITY))),
            "jahr": int(saved.get("jahr", now.year)),
            "monat": int(saved.get("monat", now.month)),
            "edit_id": int(saved.get("edit_id", 0)),
            "ladezeit": saved.get("ladezeit"),
        }
        self.active = await self.hass.async_add_executor_job(self.db.get_active)
        await self.async_refresh_views()
        await self._load_draft()
        self._prev_ign = self.coordinator.data["p"]["zuendung"] if self.coordinator.data else None
        self._unsub.append(self.coordinator.async_add_listener(self._on_update))
        if self.active and self._prev_ign == "Stop":
            # Fahrt endete waehrend HA nicht lief: sonst bliebe sie aktiv und verschmilzt mit der naechsten
            self.hass.async_create_task(self._end())
        opts = self.entry.options
        if opts.get(CONF_WAKEUP_HOURLY, True):
            self._unsub.append(async_track_time_change(self.hass, self._wakeup_cb, minute=0, second=0))
        if ent := opts.get(CONF_WAKEUP_CHARGE_ENTITY):
            self._unsub.append(async_track_state_change_event(self.hass, [ent], self._charge_cb))
        # taeglich: Monatsansicht/Gesamt neu (Monatswechsel)
        self._unsub.append(async_track_time_change(self.hass, self._midnight_cb, hour=0, minute=5, second=0))

    @callback
    def async_unload(self) -> None:
        for u in self._unsub:
            u()
        self._unsub.clear()
        if self._resync:
            self._resync()
            self._resync = None

    async def _save(self) -> None:
        await self.store.async_save(self.cfg)

    def _signal(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_VIEWS.format(self.entry.entry_id))

    # --- Ansichten -------------------------------------------------------
    async def async_refresh_views(self) -> None:
        now = dt_util.now().replace(tzinfo=None)
        self.month_data = await self.hass.async_add_executor_job(self.db.month, self.cfg["jahr"], self.cfg["monat"])
        self.overall_data = await self.hass.async_add_executor_job(self.db.overall, now)
        self._signal()

    @callback
    def _midnight_cb(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh_views())

    async def async_set_selection(self, jahr: int | None = None, monat: int | None = None) -> None:
        if jahr is not None:
            self.cfg["jahr"] = int(jahr)
        if monat is not None:
            self.cfg["monat"] = int(monat)
        await self._save()
        await self.async_refresh_views()

    async def async_current_month(self) -> None:
        now = dt_util.now()
        await self.async_set_selection(now.year, now.month)

    async def async_set_capacity(self, kwh: float) -> None:
        self.cfg["kapazitaet"] = float(kwh)
        await self._save()
        self._signal()

    async def async_set_ladezeit(self, hh: int, mm: int) -> None:
        await self.coordinator.client.charge_control(hour=hh, minute=mm)
        self.cfg["ladezeit"] = f"{hh:02d}:{mm:02d}"
        await self._save()
        self._signal()
        await self.coordinator.async_refresh_charge_control()

    # --- Hinweis-Bearbeitung ----------------------------------------------
    async def _load_draft(self) -> None:
        text = await self.hass.async_add_executor_job(self.db.get_hinweis, self.cfg["edit_id"])
        self.draft = text or ""

    async def async_set_edit_id(self, trip_id: int) -> None:
        self.cfg["edit_id"] = int(trip_id)
        await self._save()
        await self._load_draft()  # vorbefuellen statt blind ueberschreiben
        self._signal()

    def set_draft(self, text: str) -> None:
        self.draft = text
        self._signal()

    async def async_set_hinweis(self, trip_id: int, text: str) -> None:
        text = "".join(ch for ch in text if ch.isprintable())[:255]
        if not await self.hass.async_add_executor_job(self.db.set_hinweis, trip_id, text):
            raise HomeAssistantError(f"Fahrt {trip_id} existiert nicht")
        if trip_id == self.cfg["edit_id"]:
            self.draft = text
        await self.async_refresh_views()

    async def async_save_draft(self) -> None:
        await self.async_set_hinweis(self.cfg["edit_id"], self.draft)

    async def async_add_trip(self, rec: dict[str, Any]) -> int:
        trip_id = await self.hass.async_add_executor_job(self.db.insert_trip, rec)
        await self.async_refresh_views()
        return trip_id

    # --- Wakeup ----------------------------------------------------------
    async def async_wakeup(self) -> None:
        try:
            await self.coordinator.client.wakeup()
        except PsaccError as err:
            _LOGGER.warning("Wakeup fehlgeschlagen: %s", err)

    @callback
    def _wakeup_cb(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_wakeup())

    @callback
    def _charge_cb(self, event: Event) -> None:
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old and new and old.state == "on" and new.state == "off":
            self.hass.async_create_task(self.async_wakeup())  # Ladeende: Cloud neu synchronisieren

    # --- Fahrterkennung ----------------------------------------------------
    @callback
    def _on_update(self) -> None:
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return  # bei Ausfall keinen Zustand verwerfen, kein Fehlausloesen nach Rueckkehr
        ign = self.coordinator.data["p"]["zuendung"]
        prev, self._prev_ign = self._prev_ign, ign
        if ign is None or prev is None or ign == prev:
            return
        if ign == "StartUp":
            self.hass.async_create_task(self._start())
        elif ign == "Stop":
            self.hass.async_create_task(self._end())

    def _p(self) -> dict[str, Any]:
        return self.coordinator.data["p"]

    async def resolve_ort(self, lat: float | None, lon: float | None) -> str:
        if lat is None or lon is None:
            return UNKNOWN_PLACE
        zone = async_active_zone(self.hass, lat, lon)
        if zone is not None:  # Zonen-Kurzschluss spart den Nominatim-Aufruf
            if zone.entity_id == ENTITY_ID_HOME:
                return "Zuhause"
            return clean_ort(zone.name) or UNKNOWN_PLACE
        if not self.entry.options.get(CONF_GEOCODE, True):
            return UNKNOWN_PLACE
        async with self._geo_lock:  # 1 Anfrage/s (Nominatim-Richtlinie)
            loop = asyncio.get_running_loop()
            wait = self._geo_last + GEOCODE_MIN_INTERVAL - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with async_get_clientsession(self.hass).get(
                    NOMINATIM,
                    params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 16, "addressdetails": 1, "accept-language": "de"},
                    headers={"User-Agent": self.entry.options.get(CONF_USER_AGENT) or DEFAULT_USER_AGENT},
                    timeout=10,
                ) as resp:
                    data = await resp.json(content_type=None) if resp.status == 200 else None
            except Exception as err:  # noqa: BLE001 - Geocoding darf nie die Fahrt verhindern
                _LOGGER.debug("Reverse-Geocoding fehlgeschlagen: %s", type(err).__name__)
                data = None
            self._geo_last = loop.time()
        return format_ort(data)

    async def _start(self) -> None:
        async with self._lock:
            if self.active:
                return
            p = self._p()
            ort = await self.resolve_ort(p["lat"], p["lon"])
            lu = p["letztes_update"]
            rec = {
                "start_zeit": fmt_local(dt_util.as_local(lu)) if lu else fmt_local(dt_util.now()),
                "start_ort": ort,
                "km_start": p["kilometerstand"] or 0.0,
                "soc_start": float(p["soc"] or 0),
                "sync_ts": lu.isoformat() if lu else None,
            }
            await self.hass.async_add_executor_job(self.db.set_active, rec)
            self.active = rec
            self._signal()
            if self._resync:
                self._resync()
            self._resync = async_call_later(self.hass, SOC_RESYNC_DELAY, self._soc_resync)

    async def _soc_resync(self, _now: datetime) -> None:
        """90 s nach Zuendung: kam ein frischerer Cloud-Sync, den SoC-Startwert korrigieren."""
        self._resync = None
        async with self._lock:
            if not self.active or not self.coordinator.data:
                return
            lu = self._p()["letztes_update"]
            if lu is None or lu.isoformat() == self.active.get("sync_ts"):
                return
            self.active["soc_start"] = float(self._p()["soc"] or 0)
            await self.hass.async_add_executor_job(self.db.set_active, self.active)

    async def _end(self) -> None:
        async with self._lock:
            if not self.active:
                return
            p = self._p()
            ort = await self.resolve_ort(p["lat"], p["lon"])
            now = dt_util.now()
            lu = p["letztes_update"]
            rec = compute_trip(
                start_zeit=self.active["start_zeit"],
                start_ort=self.active["start_ort"],
                end_zeit=fmt_local(dt_util.as_local(lu)) if lu else fmt_local(now),
                end_ort=ort,
                km_start=self.active["km_start"],
                km_end=p["kilometerstand"] or 0.0,
                soc_start=self.active["soc_start"],
                soc_end=float(p["soc"] or 0),
                kapazitaet=self.cfg["kapazitaet"],
                frisch=is_fresh(lu, now),
            )
            trip_id = await self.hass.async_add_executor_job(self.db.insert_trip, rec)
            await self.hass.async_add_executor_job(self.db.set_active, None)
            self.active = None
            if self._resync:
                self._resync()
                self._resync = None
            await self.async_refresh_views()
            self.hass.bus.async_fire(EVENT_TRIP, {"id": trip_id, "distanz_km": rec["distanz_km"], "verbrauch_kwh": rec["verbrauch_kwh"]})
