from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_VIEWS
from .coordinator import PsaccCoordinator
from .manager import Manager


def device_info(entry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="PSA Car Controller",
        model="Fahrzeug + Fahrtenbuch",
    )


class CarEntity(CoordinatorEntity[PsaccCoordinator]):
    """Entity, die von den psacc-Fahrzeugdaten abhaengt."""

    _attr_has_entity_name = True

    def __init__(self, entry, coordinator: PsaccCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    @property
    def p(self) -> dict:
        return (self.coordinator.data or {}).get("p", {})


class BookEntity(Entity):
    """Entity, die vom Fahrtenbuch-Manager (SQLite/Auswahl) abhaengt, nicht vom Fahrzeug."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, manager: Manager, key: str) -> None:
        self.entry = entry
        self.manager = manager
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_VIEWS.format(self.entry.entry_id), self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
