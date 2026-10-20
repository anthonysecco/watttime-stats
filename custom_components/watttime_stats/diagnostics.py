"""Diagnostics download (credentials and location removed)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL
from .coordinator import WattTimeConfigEntry

REDACT = {CONF_USERNAME, CONF_PASSWORD, CONF_EMAIL, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WattTimeConfigEntry) -> dict[str, Any]:
    """Return diagnostics for one entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    summary = asdict(data)
    summary["forecast"] = {
        "points": len(data.forecast),
        "first": data.forecast[0].time.isoformat() if data.forecast else None,
        "last": data.forecast[-1].time.isoformat() if data.forecast else None,
    }
    return {
        "entry": {"data": async_redact_data(dict(entry.data), REDACT), "options": dict(entry.options)},
        "access": sorted(coordinator.access),
        "last_update_success": coordinator.last_update_success,
        "data": summary,
    }
