"""Registrierung der mitgelieferten Lovelace-Karte."""
import json
import pathlib

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.psacc_fahrtenbuch.const import DOMAIN

PKG = pathlib.Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_static_path_and_extra_js_registered_once(hass, setup):
    version = json.loads((PKG / "manifest.json").read_text())["version"]
    url = f"/{DOMAIN}/frontend/psacc-fahrzeug-card.js?v={version}"
    assert url in hass.data[DATA_EXTRA_MODULE_URL].urls
    assert (PKG / "frontend" / "psacc-fahrzeug-card.js").is_file()
    # Reload darf nicht doppelt registrieren
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert list(hass.data[DATA_EXTRA_MODULE_URL].urls).count(url) == 1


async def test_card_is_served(hass, hass_client, setup):
    client = await hass_client()
    resp = await client.get(f"/{DOMAIN}/frontend/psacc-fahrzeug-card.js")
    assert resp.status == 200 and "psacc-fahrzeug-card" in await resp.text()
    svg = await client.get(f"/{DOMAIN}/frontend/fahrzeug.svg")
    assert svg.status == 200


def test_manifest_dependencies():
    deps = json.loads((PKG / "manifest.json").read_text())["dependencies"]
    assert {"http", "frontend"} <= set(deps)
