from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import BookEntity, CarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    rt = entry.runtime_data
    c, m = rt.coordinator, rt.manager
    cl = c.client
    async_add_entities([
        CarButton(entry, c, "wakeup", m.async_wakeup, True),
        # Hupe, Lichter, Tueren: bewusst standardmaessig deaktiviert (reale Fahrzeugaktion)
        CarButton(entry, c, "hupe", lambda: cl.horn(3), False),
        CarButton(entry, c, "lichter", lambda: cl.lights(10), False),
        CarButton(entry, c, "tueren_verriegeln", lambda: cl.lock_door(True), False),
        CarButton(entry, c, "tueren_entriegeln", lambda: cl.lock_door(False), False),
        BookButton(entry, m, "aktueller_monat", m.async_current_month),
        BookButton(entry, m, "hinweis_speichern", m.async_save_draft),
    ])


class CarButton(CarEntity, ButtonEntity):
    def __init__(self, entry, coordinator, key, action, enabled) -> None:
        super().__init__(entry, coordinator, key)
        self._action = action
        self._attr_entity_registry_enabled_default = enabled

    async def async_press(self) -> None:
        await self._action()


class BookButton(BookEntity, ButtonEntity):
    def __init__(self, entry, manager, key, action) -> None:
        super().__init__(entry, manager, key)
        self._action = action

    async def async_press(self) -> None:
        await self._action()
