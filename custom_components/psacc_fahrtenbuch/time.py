from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity

from .entity import CarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    rt = entry.runtime_data
    async_add_entities([ChargeTime(entry, rt.coordinator, "ladezeit", rt.manager)])


class ChargeTime(CarEntity, TimeEntity):
    """Ladeende-Zeit der psacc-Ladesteuerung; der Wert wird nur lokal gemerkt (psacc liefert ihn nicht lesbar)."""

    _attr_icon = "mdi:clock-end"

    def __init__(self, entry, coordinator, key, manager) -> None:
        super().__init__(entry, coordinator, key)
        self.manager = manager

    @property
    def native_value(self):
        v = self.manager.cfg.get("ladezeit")
        return time.fromisoformat(v) if v else None

    async def async_set_value(self, value: time) -> None:
        await self.manager.async_set_ladezeit(value.hour, value.minute)
        self.async_write_ha_state()
