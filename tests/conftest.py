"""Shared fixtures: a fake WattTime account with synthetic data."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watttime_stats.const import CONF_REGION, CONF_REGION_NAME, DOMAIN
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util

ENTRY_DATA = {
    CONF_USERNAME: "someone",
    CONF_PASSWORD: "secret",
    CONF_LATITUDE: 37.33,
    CONF_LONGITUDE: -121.95,
    CONF_REGION: "CAISO_NORTH",
    CONF_REGION_NAME: "California ISO Northern",
}

FULL_ACCESS = {
    "signal_types": [
        {
            "signal_type": "co2_moer",
            "regions": [
                {
                    "region": "CAISO_NORTH",
                    "endpoints": [{"endpoint": "v3/forecast"}, {"endpoint": "v3/historical"}],
                }
            ],
        },
        {
            "signal_type": "health_damage",
            "regions": [{"region": "CAISO_NORTH", "endpoints": [{"endpoint": "v3/historical"}]}],
        },
    ]
}


def five_minutes_ago() -> datetime:
    now = dt_util.utcnow()
    return now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)


def forecast_rows(start: datetime) -> list[dict[str, Any]]:
    """24 h of 5-minute values: clean (0) for the first hour and hours 8-10, gas (900) otherwise."""
    rows = []
    for i in range(288):
        clean = i < 12 or 96 <= i < 120
        rows.append({"point_time": (start + timedelta(minutes=5 * i)).isoformat(), "value": 0.0 if clean else 900.0})
    return rows


def historical(region: str, signal: str, start: datetime, end: datetime) -> dict[str, Any]:
    value = 900.0 if signal == "co2_moer" else 12.5
    return {"data": [{"point_time": (end - timedelta(minutes=10)).isoformat(), "value": value}]}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """WattTimeClient as used by the integration, with full CAISO_NORTH access."""
    with patch("custom_components.watttime_stats.WattTimeClient", autospec=True) as cls:
        client = cls.return_value
        start = five_minutes_ago()
        client.my_access.return_value = FULL_ACCESS
        client.signal_index.return_value = {"data": [{"point_time": start.isoformat(), "value": 37}]}
        client.forecast.return_value = {
            "data": forecast_rows(start),
            "meta": {"generated_at": start.isoformat()},
        }
        client.historical.side_effect = historical
        yield client


@pytest.fixture
def entry() -> MockConfigEntry:
    """A config entry for CAISO_NORTH."""
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="CAISO_NORTH", title="California ISO Northern")
