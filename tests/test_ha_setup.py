"""Setup / Unload / Remove / Reload des Config Entries."""
import os

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE

from custom_components.psacc_fahrtenbuch.const import DOMAIN


async def test_setup_unload(hass, setup):
    assert setup.state is ConfigEntryState.LOADED
    for svc in ("hinweis_setzen", "soc_anstieg_setzen", "fahrten_abfragen", "fahrt_hinzufuegen", "auswahl_setzen", "wakeup"):
        assert hass.services.has_service(DOMAIN, svc)
    assert await hass.config_entries.async_unload(setup.entry_id)
    await hass.async_block_till_done()
    assert setup.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("sensor.mokka_batterie_soc").state == STATE_UNAVAILABLE
    assert await hass.config_entries.async_setup(setup.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mokka_batterie_soc").state == "53"


async def test_setup_retry_when_psacc_down(hass, entry, psacc):
    psacc.down = True
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_remove_keeps_db_deletes_store(hass, setup, hass_storage, tmp_path):
    db = tmp_path / "psacc_fahrtenbuch" / "fahrten.db"
    assert db.exists()
    await hass.services.async_call(DOMAIN, "auswahl_setzen", {"jahr": 2025, "monat": 3}, blocking=True)
    key = f"psacc_fahrtenbuch.{setup.entry_id}"
    assert hass_storage[key]["data"]["jahr"] == 2025
    await hass.config_entries.async_remove(setup.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage  # Store entfernt
    assert db.exists() and os.path.getsize(db) > 0  # Fahrtdaten bleiben
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_store_restored_after_reload(hass, setup):
    await hass.services.async_call(DOMAIN, "auswahl_setzen", {"jahr": 2025, "monat": 3}, blocking=True)
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.mokka_fahrtenbuch_jahr").state == "2025"
    assert hass.states.get("select.mokka_fahrtenbuch_monat").state == "03"


async def test_service_without_loaded_entry(hass, setup):
    from homeassistant.exceptions import ServiceValidationError
    import pytest
    await hass.config_entries.async_unload(setup.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "wakeup", {}, blocking=True)


async def test_diagnostics_redacts(hass, setup):
    from homeassistant.components.diagnostics import REDACTED
    from custom_components.psacc_fahrtenbuch.diagnostics import async_get_config_entry_diagnostics
    d = await async_get_config_entry_diagnostics(hass, setup)
    assert d["entry"]["data"]["vin"] == REDACTED and d["entry"]["data"]["url"] == REDACTED
    assert d["parsed"]["lat"] == REDACTED and d["parsed"]["lon"] == REDACTED
