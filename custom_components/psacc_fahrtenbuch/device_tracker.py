from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity

from .entity import CarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Tracker(entry, entry.runtime_data.coordinator, "standort")])


class Tracker(CarEntity, TrackerEntity):
    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self):
        return self.p.get("lat")

    @property
    def longitude(self):
        return self.p.get("lon")
