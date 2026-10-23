from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.helpers.entity import EntityCategory

from .entity import BookEntity, CarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    rt = entry.runtime_data
    async_add_entities([
        ChargeLimit(entry, rt.coordinator, "ladelimit"),
        Capacity(entry, rt.manager, "akkukapazitaet"),
        Year(entry, rt.manager, "fahrtenbuch_jahr"),
        EditId(entry, rt.manager, "fahrtenbuch_bearbeiten_id"),
    ])


class ChargeLimit(CarEntity, NumberEntity):
    _attr_native_min_value = 20
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self):
        return self.p.get("ladelimit")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.charge_control(percentage=int(value))
        await self.coordinator.async_refresh_charge_control()


class Capacity(BookEntity, NumberEntity):
    """Angenommene nutzbare Akkukapazitaet (Basis der kWh-Berechnung je Fahrt)."""

    _attr_native_min_value = 10
    _attr_native_max_value = 200
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self):
        return self.manager.cfg.get("kapazitaet")

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.async_set_capacity(value)


class Year(BookEntity, NumberEntity):
    _attr_native_min_value = 2000
    _attr_native_max_value = 2100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:calendar"

    @property
    def native_value(self):
        return self.manager.cfg.get("jahr")

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.async_set_selection(jahr=int(value))


class EditId(BookEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 10_000_000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:identifier"

    @property
    def native_value(self):
        return self.manager.cfg.get("edit_id")

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.async_set_edit_id(int(value))
