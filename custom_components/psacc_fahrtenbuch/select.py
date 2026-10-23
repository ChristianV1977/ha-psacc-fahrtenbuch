from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .entity import BookEntity

MONTHS = [f"{m:02d}" for m in range(1, 13)]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Month(entry, entry.runtime_data.manager, "fahrtenbuch_monat")])


class Month(BookEntity, SelectEntity):
    _attr_options = MONTHS
    _attr_icon = "mdi:calendar-month"

    @property
    def current_option(self):
        return f"{int(self.manager.cfg['monat']):02d}"

    async def async_select_option(self, option: str) -> None:
        await self.manager.async_set_selection(monat=int(option))
