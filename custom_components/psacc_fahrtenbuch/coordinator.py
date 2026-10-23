"""DataUpdateCoordinator gegen psacc: Fahrzeugdaten (schnell), SOH (stuendlich), Ladesteuerung (minuetlich)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PsaccClient, PsaccError
from .const import CHARGE_CONTROL_INTERVAL, DOMAIN, SOH_INTERVAL
from .parse import parse_info

_LOGGER = logging.getLogger(__name__)


class PsaccCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PsaccClient, interval: int) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(seconds=interval))
        self.client = client
        self._soh: dict = {}
        self._cc: dict = {}
        self._soh_at = 0.0
        self._cc_at = 0.0

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
