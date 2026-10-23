"""Config-Flow: psacc-URL, Fahrzeug (VIN) waehlen, Grundeinstellungen; Options-Flow fuer Laufzeit-Optionen."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PsaccClient, PsaccError
from .const import (
    CONF_CAPACITY, CONF_GEOCODE, CONF_SCAN_INTERVAL, CONF_URL, CONF_USER_AGENT, CONF_VIN,
    CONF_WAKEUP_CHARGE_ENTITY, CONF_WAKEUP_HOURLY, DEFAULT_CAPACITY, DEFAULT_SCAN_INTERVAL,
    DEFAULT_URL, DEFAULT_USER_AGENT, DOMAIN,
)


def _runtime_schema(opts: dict[str, Any]) -> dict:
    ent = {"description": {"suggested_value": opts.get(CONF_WAKEUP_CHARGE_ENTITY)}}
    return {
        vol.Required(CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=600, unit_of_measurement="s", mode="box")),
        vol.Required(CONF_WAKEUP_HOURLY, default=opts.get(CONF_WAKEUP_HOURLY, True)): bool,
        vol.Optional(CONF_WAKEUP_CHARGE_ENTITY, **ent):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
        vol.Required(CONF_GEOCODE, default=opts.get(CONF_GEOCODE, True)): bool,
        vol.Required(CONF_USER_AGENT, default=opts.get(CONF_USER_AGENT, DEFAULT_USER_AGENT)): str,
    }


def _clean(opts: dict[str, Any]) -> dict[str, Any]:
    opts = dict(opts)
    opts[CONF_SCAN_INTERVAL] = int(opts[CONF_SCAN_INTERVAL])
    if not opts.get(CONF_WAKEUP_CHARGE_ENTITY):
        opts.pop(CONF_WAKEUP_CHARGE_ENTITY, None)
    return opts


class PsaccFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._url = DEFAULT_URL
        self._vehicles: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._url = user_input[CONF_URL].rstrip("/")
            try:
                vehicles = await PsaccClient(async_get_clientsession(self.hass), self._url).vehicles()
            except PsaccError:
                errors["base"] = "cannot_connect"
            else:
                self._vehicles = {
                    v["vin"]: f"{v.get('label') or 'Fahrzeug'} (…{v['vin'][-5:]})" for v in vehicles if v.get("vin")
                }
                if not self._vehicles:
                    errors["base"] = "no_vehicles"
                else:
                    return await self.async_step_vehicle()
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_URL, default=self._url): str}),
        )

    async def async_step_vehicle(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            vin = user_input[CONF_VIN]
            await self.async_set_unique_id(vin)
            self._abort_if_unique_id_configured()
            self._vin = vin
            return await self.async_step_settings()
        options = [selector.SelectOptionDict(value=k, label=v) for k, v in self._vehicles.items()]
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema({vol.Required(CONF_VIN, default=options[0]["value"]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode="dropdown"))}),
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input = dict(user_input)
            title = user_input.pop("titel")
            capacity = float(user_input.pop(CONF_CAPACITY))
            return self.async_create_entry(
                title=title,
                data={CONF_URL: self._url, CONF_VIN: self._vin},
                options={**_clean(user_input), CONF_CAPACITY: capacity},
            )
        label = self._vehicles[self._vin].split(" (")[0]
        schema = {
            vol.Required("titel", default=label): str,
            vol.Required(CONF_CAPACITY, default=DEFAULT_CAPACITY):
                selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=200, step=0.5, unit_of_measurement="kWh", mode="box")),
            **_runtime_schema({}),
        }
        return self.async_show_form(step_id="settings", data_schema=vol.Schema(schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> PsaccOptionsFlow:
        return PsaccOptionsFlow()


class PsaccOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **_clean(user_input)})
        return self.async_show_form(step_id="init", data_schema=vol.Schema(_runtime_schema(dict(self.config_entry.options))))
