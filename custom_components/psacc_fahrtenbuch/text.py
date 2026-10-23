from __future__ import annotations

from homeassistant.components.text import TextEntity

from .entity import BookEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Hinweis(entry, entry.runtime_data.manager, "fahrtenbuch_hinweis")])


class Hinweis(BookEntity, TextEntity):
    """Entwurf des Hinweis-/Kommentartexts der per ID gewaehlten Fahrt (Speichern per Button)."""

    _attr_native_max = 255
    _attr_icon = "mdi:comment-edit"

    @property
    def native_value(self):
        return self.manager.draft

    async def async_set_value(self, value: str) -> None:
        self.manager.set_draft(value)
