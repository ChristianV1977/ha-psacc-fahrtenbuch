"""Testet die reine Logik OHNE Home-Assistant-Installation.

Das Paket-__init__ (importiert HA) wird nicht ausgefuehrt: ein Platzhalter-Paket mit dem
echten __path__ wird registriert und homeassistant.const minimal gestubbt.
"""
import enum, pathlib, sys, types

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
