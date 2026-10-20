"""The HTTP client, against a mocked api.watttime.org."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from custom_components.watttime_stats.api import (
    WattTimeAccessError,
    WattTimeAuthError,
    WattTimeClient,
    access_set,
)
from custom_components.watttime_stats.const import API_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import FULL_ACCESS

INDEX = {"data": [{"point_time": "2026-10-20T22:00:00+00:00", "value": 5}]}


def _client(hass: HomeAssistant) -> WattTimeClient:
    return WattTimeClient(async_get_clientsession(hass), "someone", "secret")


async def test_logs_in_once(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The token is reused across calls."""
    aioclient_mock.get(f"{API_URL}/login", json={"token": "abc"})
    aioclient_mock.get(f"{API_URL}/v3/signal-index", json=INDEX)
    client = _client(hass)
    assert (await client.signal_index("CAISO_NORTH"))["data"][0]["value"] == 5
    await client.signal_index("CAISO_NORTH")
    assert aioclient_mock.call_count == 3  # 1 login + 2 data calls
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Basic c29tZW9uZTpzZWNyZXQ="  # someone:secret
    assert aioclient_mock.mock_calls[1][3]["Authorization"] == "Bearer abc"


async def test_bad_password(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A rejected login raises an auth error."""
    aioclient_mock.get(f"{API_URL}/login", status=HTTPStatus.FORBIDDEN)
    with pytest.raises(WattTimeAuthError):
        await _client(hass).signal_index("CAISO_NORTH")


async def test_expired_token_retries(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A 401 on a data call logs in again and retries once."""
    calls = 0

    async def index(method, url, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AiohttpClientMockResponse(method, url, status=HTTPStatus.UNAUTHORIZED)
        return AiohttpClientMockResponse(method, url, json=INDEX)

    aioclient_mock.get(f"{API_URL}/login", json={"token": "abc"})
    aioclient_mock.get(f"{API_URL}/v3/signal-index", side_effect=index)
    assert (await _client(hass).signal_index("CAISO_NORTH"))["data"][0]["value"] == 5
    assert calls == 2


async def test_plan_without_access(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A 403 on a data call means the plan doesn't include it."""
    aioclient_mock.get(f"{API_URL}/login", json={"token": "abc"})
    aioclient_mock.get(f"{API_URL}/v3/forecast", status=HTTPStatus.FORBIDDEN)
    with pytest.raises(WattTimeAccessError):
        await _client(hass).forecast("PJM_DC", "co2_moer", 24)


def test_access_set() -> None:
    """my-access is reduced to (signal, endpoint) pairs for one region."""
    assert access_set(FULL_ACCESS, "CAISO_NORTH") == {
        ("co2_moer", "v3/forecast"),
        ("co2_moer", "v3/historical"),
        ("health_damage", "v3/historical"),
    }
    assert access_set(FULL_ACCESS, "PJM_DC") == frozenset()
