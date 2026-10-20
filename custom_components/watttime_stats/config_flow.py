"""Config flow for WattTime Status."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    WattTimeAuthError,
    WattTimeClient,
    WattTimeConnectionError,
    WattTimeError,
    WattTimeNotFoundError,
    register,
)
from .const import (
    CONF_CLEAN_MAX,
    CONF_CLEAN_PERCENTILE,
    CONF_EMAIL,
    CONF_LOOKAHEAD_HOURS,
    CONF_ORG,
    CONF_REGION,
    CONF_REGION_NAME,
    CONF_UNIT,
    CONF_WINDOW_HOURS,
    DEFAULT_CLEAN_MAX,
    DEFAULT_CLEAN_PERCENTILE,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_UNIT,
    DEFAULT_WINDOW_HOURS,
    DOMAIN,
    UNIT_G_KWH,
    UNIT_OPTIONS,
)

try:
    import probatio as vol
except ImportError:  # Home Assistant before 2026.x ships voluptuous instead
    import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
PLACEHOLDERS = {"docs_url": "https://docs.watttime.org/", "plans_url": "https://watttime.org/docs-dev/data-plans/"}


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


class WattTimeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up WattTime with an existing or new account."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WattTimeOptionsFlow:
        """Return the options flow."""
        return WattTimeOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask whether the user already has a WattTime account."""
        return self.async_show_menu(step_id="user", menu_options=["login", "register"])

    def _location_schema(self, user_input: Mapping[str, Any] | None) -> dict:
        user_input = user_input or {}
        return {
            vol.Required(
                CONF_LATITUDE, default=user_input.get(CONF_LATITUDE, self.hass.config.latitude)
            ): vol.Coerce(float),
            vol.Required(
                CONF_LONGITUDE, default=user_input.get(CONF_LONGITUDE, self.hass.config.longitude)
            ): vol.Coerce(float),
        }

    async def _validate(self, data: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
        """Log in and look up the grid region. Returns (errors, region info)."""
        client = WattTimeClient(async_get_clientsession(self.hass), data[CONF_USERNAME], data[CONF_PASSWORD])
        try:
            await client.login()
            if CONF_LATITUDE not in data:
                return {}, {}
            region = await client.region_from_location(data[CONF_LATITUDE], data[CONF_LONGITUDE])
        except WattTimeAuthError:
            return {"base": "invalid_auth"}, {}
        except WattTimeNotFoundError:
            return {"base": "no_region"}, {}
        except WattTimeConnectionError:
            return {"base": "cannot_connect"}, {}
        except Exception:
            _LOGGER.exception("Unexpected error while checking the WattTime account")
            return {"base": "unknown"}, {}
        return {}, region

    async def _finish(self, data: dict[str, Any], region: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(region["region"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=region.get("region_full_name") or region["region"],
            data={
                **data,
                CONF_REGION: region["region"],
                CONF_REGION_NAME: region.get("region_full_name") or region["region"],
            },
        )

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Sign in with an existing account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, region = await self._validate(user_input)
            if not errors:
                return await self._finish(user_input, region)
        schema = {
            vol.Required(CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): PASSWORD,
            **self._location_schema(user_input),
        }
        return self.async_show_form(
            step_id="login", data_schema=vol.Schema(schema), errors=errors, description_placeholders=PLACEHOLDERS
        )

    async def async_step_register(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create a WattTime account, then sign in with it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await register(
                    async_get_clientsession(self.hass),
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_EMAIL],
                    user_input.get(CONF_ORG),
                )
            except WattTimeConnectionError:
                errors["base"] = "cannot_connect"
            except WattTimeError as err:
                _LOGGER.warning("WattTime did not create the account: %s", err)
                errors["base"] = "register_failed"
            else:
                login = {k: user_input[k] for k in (CONF_USERNAME, CONF_PASSWORD, CONF_LATITUDE, CONF_LONGITUDE)}
                errors, region = await self._validate(login)
                if not errors:
                    return await self._finish(login, region)
        user_input = user_input or {}
        schema = {
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): PASSWORD,
            vol.Required(CONF_EMAIL, default=user_input.get(CONF_EMAIL, "")): str,
            vol.Optional(CONF_ORG, default=user_input.get(CONF_ORG, "")): str,
            **self._location_schema(user_input),
        }
        return self.async_show_form(
            step_id="register", data_schema=vol.Schema(schema), errors=errors, description_placeholders=PLACEHOLDERS
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """WattTime stopped accepting the saved password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, _ = await self._validate(
                {CONF_USERNAME: entry.data[CONF_USERNAME], CONF_PASSWORD: user_input[CONF_PASSWORD]}
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD}),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )


class WattTimeOptionsFlow(OptionsFlow):
    """Tune what counts as "clean" and how far ahead to look."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_UNIT, default=opts.get(CONF_UNIT, DEFAULT_UNIT)): SelectSelector(
                    SelectSelectorConfig(options=list(UNIT_OPTIONS), translation_key="unit")
                ),
                vol.Required(
                    CONF_CLEAN_PERCENTILE, default=opts.get(CONF_CLEAN_PERCENTILE, DEFAULT_CLEAN_PERCENTILE)
                ): _number(1, 75, 1, "%"),
                vol.Required(CONF_CLEAN_MAX, default=opts.get(CONF_CLEAN_MAX, DEFAULT_CLEAN_MAX)): _number(
                    0, 1000, 1, UNIT_G_KWH
                ),
                vol.Required(CONF_WINDOW_HOURS, default=opts.get(CONF_WINDOW_HOURS, DEFAULT_WINDOW_HOURS)): _number(
                    0.5, 12, 0.5, "h"
                ),
                vol.Required(
                    CONF_LOOKAHEAD_HOURS, default=opts.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)
                ): _number(1, 72, 1, "h"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
