"""The get_forecast action."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .analysis import upcoming
from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_GET_FORECAST
from .entity import co2

try:
    import probatio as vol
except ImportError:  # Home Assistant before 2026.x ships voluptuous instead
    import voluptuous as vol

SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): str})


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def get_forecast(call: ServiceCall) -> ServiceResponse:
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if wanted := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entries = [e for e in entries if e.entry_id == wanted]
        if len(entries) != 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_entry" if not entries else "pick_entry",
            )
        coordinator = entries[0].runtime_data
        data = coordinator.data
        if not data.forecast:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_forecast")
        unit, convert = co2(entries[0])
        points = upcoming(data.forecast, dt_util.utcnow(), coordinator.lookahead)
        return {
            "region": coordinator.region,
            "unit": unit,
            "generated_at": data.forecast_generated_at.isoformat() if data.forecast_generated_at else None,
            "forecast": [{"time": p.time.isoformat(), "value": round(convert(p.value), 1)} for p in points],
        }

    hass.services.async_register(
        DOMAIN, SERVICE_GET_FORECAST, get_forecast, schema=SCHEMA, supports_response=SupportsResponse.ONLY
    )
