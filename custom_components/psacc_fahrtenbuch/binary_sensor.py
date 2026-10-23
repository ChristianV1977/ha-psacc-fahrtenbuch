from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import BookEntity, CarEntity
from .trips import is_fresh


async def async_setup_entry(hass, entry, async_add_entities):
    rt = entry.runtime_data
    async_add_entities([
        PlugSensor(entry, rt.coordinator, "angesteckt"),
        MovingSensor(entry, rt.coordinator, "in_bewegung"),
        FreshSensor(entry, rt.coordinator, "daten_aktuell"),
        TripActive(entry, rt.manager, "fahrt_aktiv"),
    ])


class PlugSensor(CarEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def is_on(self):
        return self.p.get("angesteckt")


class MovingSensor(CarEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOVING

    @property
    def is_on(self):
        v = self.p.get("in_bewegung")
        return None if v is None else bool(v)


class FreshSensor(CarEntity, BinarySensorEntity):
    """Aus: Cloud-Daten aelter als 30 Minuten (Fahrzeug im Tiefschlaf / Cloud haengt)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-check"

    @property
    def is_on(self):
        from homeassistant.util import dt as dt_util
        lu = self.p.get("letztes_update")
        return None if lu is None else is_fresh(lu, dt_util.utcnow())


class TripActive(BookEntity, BinarySensorEntity):
    _attr_icon = "mdi:car-clock"

    @property
    def is_on(self):
        return self.manager.active is not None
