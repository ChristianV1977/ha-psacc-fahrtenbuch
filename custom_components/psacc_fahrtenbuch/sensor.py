from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfEnergy, UnitOfLength, UnitOfSpeed, UnitOfTemperature, UnitOfTime

from .entity import BookEntity, CarEntity

CAR: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="soc", device_class=SensorDeviceClass.BATTERY, native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="reichweite", device_class=SensorDeviceClass.DISTANCE, native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="kilometerstand", device_class=SensorDeviceClass.DISTANCE, native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:road-variant"),
    SensorEntityDescription(key="batteriespannung", device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=UnitOfElectricPotential.VOLT, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="soh", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery-heart-variant"),
    SensorEntityDescription(key="umgebungstemperatur", device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="umgebungslicht", device_class=SensorDeviceClass.ENUM, options=["day", "night"]),
    SensorEntityDescription(key="zuendung", icon="mdi:key-variant"),
    SensorEntityDescription(key="geschwindigkeit", device_class=SensorDeviceClass.SPEED, native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR, state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="tueren", icon="mdi:car-door"),
    SensorEntityDescription(key="lademodus", device_class=SensorDeviceClass.ENUM, options=["fast", "slow", "none"], icon="mdi:ev-plug-type2"),
    SensorEntityDescription(key="laderate", icon="mdi:speedometer"),
    SensorEntityDescription(key="ladestatus", device_class=SensorDeviceClass.ENUM, options=["failure", "in_progress", "stopped", "finished", "disconnected", "unknown"], icon="mdi:ev-station"),
    SensorEntityDescription(key="verbleibende_ladezeit", device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.MINUTES),
    SensorEntityDescription(key="vorklimatisierung_status", icon="mdi:air-conditioner"),
    SensorEntityDescription(key="vorklimatisierung_fehler", device_class=SensorDeviceClass.ENUM, options=["defect", "door_opened", "low_battery", "low_fuel", "too_many_programs"], icon="mdi:information"),
    SensorEntityDescription(key="letztes_update", device_class=SensorDeviceClass.TIMESTAMP),
    SensorEntityDescription(key="naechste_stoppzeit", icon="mdi:clock-end"),
)


@dataclass(frozen=True, kw_only=True)
class BookDesc(SensorEntityDescription):
    source: str  # "month" | "overall"
    field: str


def _book() -> tuple[BookDesc, ...]:
    out = []
    for src, pre in (("month", "monat"), ("overall", "gesamt")):
        out += [
            BookDesc(key=f"{pre}_fahrten", source=src, field="anzahl", icon="mdi:notebook-outline"),
            BookDesc(key=f"{pre}_km", source=src, field="gesamt_km", device_class=SensorDeviceClass.DISTANCE, native_unit_of_measurement=UnitOfLength.KILOMETERS),
            BookDesc(key=f"{pre}_kwh", source=src, field="gesamt_kwh", device_class=SensorDeviceClass.ENERGY, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR),
            BookDesc(key=f"{pre}_kwh_pro_100km", source=src, field="kwh_pro_100km", native_unit_of_measurement="kWh/100 km", icon="mdi:gauge"),
            BookDesc(key=f"{pre}_kwh_pro_fahrt", source=src, field="avg_kwh_pro_fahrt", native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR),
        ]
    return tuple(out)


async def async_setup_entry(hass, entry, async_add_entities):
    rt = entry.runtime_data
    async_add_entities([CarSensor(entry, rt.coordinator, d) for d in CAR])
    async_add_entities([BookSensor(entry, rt.manager, d) for d in _book()])


class CarSensor(CarEntity, SensorEntity):
    def __init__(self, entry, coordinator, desc: SensorEntityDescription) -> None:
        super().__init__(entry, coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        return self.p.get(self.entity_description.key)


class BookSensor(BookEntity, SensorEntity):
    # Fahrtenliste enthaelt Orte und Hinweistexte -> nie in Recorder/Verlauf
    _unrecorded_attributes = frozenset({"trips"})

    def __init__(self, entry, manager, desc: BookDesc) -> None:
        super().__init__(entry, manager, desc.key)
        self.entity_description = desc

    @property
    def _data(self) -> dict:
        d = self.entity_description
        return self.manager.month_data if d.source == "month" else self.manager.overall_data

    @property
    def native_value(self) -> Any:
        return self._data.get(self.entity_description.field)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key == "monat_fahrten":
            return {"jahr": self.manager.month_data.get("jahr"), "monat": self.manager.month_data.get("monat"),
                    "trips": self.manager.month_data.get("trips", [])}
        return None
