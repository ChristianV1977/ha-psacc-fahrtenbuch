"""Duenner Client fuer die lokale REST-API des Add-ons PSA Car Controller."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=15)


class PsaccError(Exception):
    """Anfrage an psacc fehlgeschlagen (ohne URL/VIN in der Meldung)."""


class PsaccClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, vin: str | None = None) -> None:
        self._s = session
        self._base = url.rstrip("/")
        self.vin = vin

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._s.get(f"{self._base}{path}", params=params, timeout=TIMEOUT) as r:
                if r.status != 200:
                    raise PsaccError(f"HTTP {r.status}")
                try:
                    return await r.json(content_type=None)
                except ValueError:
                    return None  # manche Kommandos antworten mit Text
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PsaccError(type(err).__name__) from None

    @property
    def _v(self) -> str:
        return quote(self.vin or "", safe="")

    async def vehicles(self) -> list[dict]:
        data = await self._get("/get_vehicles")
        return data if isinstance(data, list) else []

    async def vehicleinfo(self) -> dict:
        data = await self._get(f"/get_vehicleinfo/{self._v}", {"from_cache": 1})
        if not isinstance(data, dict):
            raise PsaccError("unerwartete Antwort")
        return data

    async def soh(self) -> dict:
        return await self._get(f"/battery/soh/{self._v}") or {}

    async def charge_control(self, **params: Any) -> dict:
        query = {"vin": self.vin, **params}
        if not params:
            query["always_check"] = "true"
        return await self._get("/charge_control", query) or {}

    async def wakeup(self) -> None:
        await self._get(f"/wakeup/{self._v}")

    async def horn(self, count: int = 3) -> None:
        await self._get(f"/horn/{self._v}/{count}")

    async def lights(self, seconds: int = 10) -> None:
        await self._get(f"/lights/{self._v}/{seconds}")

    async def lock_door(self, lock: bool) -> None:
        await self._get(f"/lock_door/{self._v}/{1 if lock else 0}")

    async def preconditioning(self, on: bool) -> None:
        await self._get(f"/preconditioning/{self._v}/{1 if on else 0}")
