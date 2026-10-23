from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data

TO_REDACT = {"vin", "url", "lat", "lon", "coordinates", "href", "vehicle_id", "trips"}


async def async_get_config_entry_diagnostics(hass, entry):
    rt = entry.runtime_data
    return async_redact_data({
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "parsed": {k: str(v) for k, v in (rt.coordinator.data or {}).get("p", {}).items()},
        "active_trip": rt.manager.active is not None,
        "totals": {k: v for k, v in rt.manager.overall_data.items()},
    }, TO_REDACT)
