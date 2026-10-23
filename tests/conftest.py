"""Testet die reine Logik OHNE Home-Assistant-Installation.

Das Paket-__init__ (importiert HA) wird nicht ausgefuehrt: ein Platzhalter-Paket mit dem
echten __path__ wird registriert und homeassistant.const minimal gestubbt.
"""
import enum, pathlib, re, sys, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = "custom_components.psacc_fahrtenbuch"

if "homeassistant" not in sys.modules:
    try:
        import homeassistant  # noqa: F401  (echte Installation vorhanden, dann nichts stubben)
    except ImportError:
        ha = types.ModuleType("homeassistant")
        const = types.ModuleType("homeassistant.const")
        const.Platform = enum.Enum("Platform", {n: n.lower() for n in
                                    ["SENSOR", "BINARY_SENSOR", "DEVICE_TRACKER", "BUTTON", "SWITCH", "NUMBER", "SELECT", "TEXT", "TIME"]})
        sys.modules.update({"homeassistant": ha, "homeassistant.const": const})
        cc = types.ModuleType("custom_components"); cc.__path__ = [str(ROOT / "custom_components")]
        pkg = types.ModuleType(PKG); pkg.__path__ = [str(ROOT / "custom_components" / "psacc_fahrtenbuch")]
        sys.modules.update({"custom_components": cc, PKG: pkg})


# --- Fixtures fuer die HA-gebundenen Tests (nur mit installiertem Home Assistant) ---
try:
    import homeassistant.core  # noqa: F401
    HAVE_HA = True
except ImportError:
    HAVE_HA = False

if HAVE_HA:
    import copy, json

    import pytest
    from aiohttp import ClientConnectionError
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

    from custom_components.psacc_fahrtenbuch.const import DOMAIN

    FIX = ROOT / "tests" / "fixtures"
    BASE = "http://psacc.test:5000"
    NOW = "2026-01-01 12:10:00+00:00"  # 10 min nach "letztes_update" der Fixture -> Daten frisch
    VIN = json.loads((FIX / "vehicles.json").read_text())[0]["vin"]

    def load_fixture_json(name):
        return json.loads((FIX / name).read_text())

    class PsaccMock:
        """Veraenderbarer psacc-Mock: info/soh/charge_control aenderbar, Ausfall schaltbar."""

        def __init__(self, aioclient_mock):
            self.mock = aioclient_mock
            self.info = load_fixture_json("vehicleinfo.json")
            self.vehicles = load_fixture_json("vehicles.json")
            self.charge_control = load_fixture_json("charge_control.json")
            self.soh = {"soh": 90.0}
            self.down = False
            self.nominatim = {"address": {"road": "Teststrasse", "town": "Beispielstadt"}}
            self.nominatim_fail = False
            self.nominatim_exc = False
            self.geo_calls = []
            m = aioclient_mock
            m.get(f"{BASE}/get_vehicles", side_effect=self._h(lambda: self.vehicles))
            m.get(f"{BASE}/get_vehicleinfo/{VIN}", side_effect=self._h(lambda: self.info))
            m.get(f"{BASE}/battery/soh/{VIN}", side_effect=self._h(lambda: self.soh))
            m.get(f"{BASE}/charge_control", side_effect=self._h(lambda: self.charge_control))
            self.wakeup_fail = False
            m.get(f"{BASE}/wakeup/{VIN}", side_effect=self._wakeup)
            for cmd in ("horn", "lights", "lock_door", "preconditioning"):
                m.get(f"{BASE}/{cmd}/{VIN}", side_effect=self._h(lambda: {"ok": True}))
            m.get(re.compile(rf"{re.escape(BASE)}/(horn|lights|lock_door|preconditioning)/{VIN}/\d+"),
                  side_effect=self._h(lambda: {"ok": True}))
            m.get("https://nominatim.openstreetmap.org/reverse", side_effect=self._geo)

        def _h(self, get):
            async def handler(method, url, data):
                if self.down:
                    return AiohttpClientMockResponse(method, url, exc=ClientConnectionError("down"))
                return AiohttpClientMockResponse(method, url, json=copy.deepcopy(get()))
            return handler

        async def _wakeup(self, method, url, data):
            if self.wakeup_fail:
                return AiohttpClientMockResponse(method, url, status=500)
            return AiohttpClientMockResponse(method, url, json={"ok": True})

        async def _geo(self, method, url, data):
            self.geo_calls.append((url, data))
            if self.nominatim_exc:
                return AiohttpClientMockResponse(method, url, exc=ClientConnectionError("geo down"))
            if self.nominatim_fail:
                return AiohttpClientMockResponse(method, url, status=500)
            return AiohttpClientMockResponse(method, url, json=self.nominatim)

        def calls(self, path_part):
            return [c for c in self.mock.mock_calls if path_part in str(c[1])]

        def set_ign(self, ign, soc=None, km=None, updated=None):
            self.info["ignition"]["type"] = ign
            if soc is not None:
                self.info["energy"][0]["level"] = float(soc)
            if km is not None:
                self.info["timed_odometer"]["mileage"] = km
            if updated is not None:
                self.info["energy"][0]["updated_at"] = updated

    @pytest.fixture(autouse=True)
    def _enable_custom(enable_custom_integrations):
        yield

    @pytest.fixture(autouse=True)
    async def _isolate_config_dir(hass, tmp_path, freezer):
        """fahrten.db nie im gemeinsamen Test-Konfigverzeichnis anlegen; Entity-IDs deutsch; feste Zeit."""
        hass.config.config_dir = str(tmp_path)
        hass.config.language = "de"
        await hass.config.async_set_time_zone("Europe/Berlin")
        freezer.move_to(NOW)

    @pytest.fixture
    def psacc(aioclient_mock):
        return PsaccMock(aioclient_mock)

    @pytest.fixture
    def entry(hass):
        e = MockConfigEntry(
            domain=DOMAIN, title="Mokka", unique_id=VIN,
            data={"url": BASE, "vin": VIN},
            options={"scan_interval": 20, "wakeup_stuendlich": True, "geocoding": True,
                     "user_agent": "test-agent/1.0", "kapazitaet_kwh": 50.0},
        )
        e.add_to_hass(hass)
        return e

    @pytest.fixture
    async def setup(hass, entry, psacc):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry
