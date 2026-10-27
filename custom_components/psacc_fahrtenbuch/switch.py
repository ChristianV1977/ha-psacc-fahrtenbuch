from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import CarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Precond(entry, entry.runtime_data.coordinator, "vorklimatisierung")])


class Precond(CarEntity, SwitchEntity):
    _attr_icon = "mdi:car-defrost-front"

    @property
    def is_on(self):
        s = self.p.get("vorklimatisierung_status")
        return None if s is None else s == "Enabled"

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.mark_precond_request(True)
        await self.coordinator.client.preconditioning(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.mark_precond_request(False)
        await self.coordinator.client.preconditioning(False)
        await self.coordinator.async_request_refresh()
