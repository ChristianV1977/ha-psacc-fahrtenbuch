"""DataUpdateCoordinator gegen psacc: Fahrzeugdaten (schnell), SOH (stuendlich), Ladesteuerung (minuetlich)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PsaccClient, PsaccError
from .const import CHARGE_CONTROL_INTERVAL, DOMAIN, SOH_INTERVAL
from .parse import parse_info
from .precond import PrecondTracker, merge_log, parse_log

_LOGGER = logging.getLogger(__name__)
LOG_FETCH_DELAYS = (150, 330)  # s nach einem Einschalt-Befehl: Antworten stehen dann im Add-on-Log


class PsaccCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PsaccClient, interval: int) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(seconds=interval))
        self.client = client
        self._soh: dict = {}
        self._cc: dict = {}
        self._soh_at = 0.0
        self._cc_at = 0.0
        self.precond = PrecondTracker()
        self.precond_log: list[dict] = []
        self._plog_store: Store[dict[str, Any]] = Store(hass, 1, f"psacc_fahrtenbuch.{entry.entry_id}.precond_log")
        self._plog_timers: list = []

    async def async_load_precond_log(self) -> None:
        """Gespeicherten Verlauf laden und einmal frisch aus dem Add-on-Log ergaenzen."""
        stored = await self._plog_store.async_load() or {}
        self.precond_log = list(stored.get("log", []))
        await self._async_fetch_precond_log()

    def mark_precond_request(self, on: bool) -> None:
        """Befehlszeitpunkt merken (fuer 'angefordert' / 'nicht gestartet') und Log-Abruf einplanen."""
        self.precond.request(on, dt_util.utcnow())
        if on:
            for delay in LOG_FETCH_DELAYS:
                self._plog_timers.append(async_call_later(self.hass, delay, self._async_fetch_precond_log))

    async def _async_fetch_precond_log(self, _now=None) -> None:
        """ThermalPrecond-Zeilen aus dem Add-on-Log holen (Supervisor); Fehler duerfen nichts stoeren."""
        try:
            from homeassistant.components.hassio import DATA_COMPONENT
            slug = self.client.addon_slug
            text = await self.hass.data[DATA_COMPONENT].send_command(
                f"/addons/{slug}/logs", method="get", return_text=True)
        except Exception as err:  # noqa: BLE001 (kein Hassio, Slug unbekannt, Supervisor-Fehler)
            _LOGGER.debug("Add-on-Log nicht lesbar: %s", type(err).__name__)
            return
        new = parse_log(text, self.client.vin)
        merged = merge_log(self.precond_log, new)
        if merged != self.precond_log:
            self.precond_log = merged
            await self._plog_store.async_save({"log": merged})
            self.async_update_listeners()

    async def async_shutdown(self) -> None:
        for cancel in self._plog_timers:
            cancel()
        self._plog_timers.clear()
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            info = await self.client.vehicleinfo()
        except PsaccError as err:
            raise UpdateFailed(f"psacc nicht erreichbar: {err}") from None
        now = time.monotonic()
        # Nebenabfragen duerfen scheitern, ohne die Fahrzeugdaten zu entwerten
        if now - self._soh_at >= SOH_INTERVAL:
            try:
                self._soh = await self.client.soh()
                self._soh_at = now
            except PsaccError:
                _LOGGER.debug("SOH-Abfrage fehlgeschlagen")
        if now - self._cc_at >= CHARGE_CONTROL_INTERVAL:
            try:
                self._cc = await self.client.charge_control()
                self._cc_at = now
            except PsaccError:
                _LOGGER.debug("charge_control-Abfrage fehlgeschlagen")
        parsed = parse_info(info)
        parsed.update(self.precond.update(
            parsed.get("vorklimatisierung_status"), parsed.get("vorklimatisierung_fehler"), dt_util.utcnow()))
        parsed["soh"] = _int(self._soh.get("soh"))
        parsed["ladelimit"] = _int(self._cc.get("percentage_threshold"))
        parsed["naechste_stoppzeit"] = self._cc.get("_next_stop_hour")
        return {"raw": info, "p": parsed}

    async def async_refresh_charge_control(self) -> None:
        """Nach dem Setzen von Ladelimit/-zeit sofort neu lesen."""
        self._cc_at = 0.0
        await self.async_request_refresh()


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
