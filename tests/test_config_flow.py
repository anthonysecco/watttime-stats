"""Config, reauth and options flows."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watttime_stats.api import WattTimeAuthError, WattTimeError, WattTimeNotFoundError
from custom_components.watttime_stats.const import (
    CONF_CLEAN_MAX,
    CONF_CLEAN_PERCENTILE,
    CONF_EMAIL,
    CONF_LOOKAHEAD_HOURS,
    CONF_UNIT,
    CONF_WINDOW_HOURS,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

LOGIN = {CONF_USERNAME: "someone", CONF_PASSWORD: "secret", CONF_LATITUDE: 37.33, CONF_LONGITUDE: -121.95}
REGION = {"region": "CAISO_NORTH", "region_full_name": "California ISO Northern"}


@pytest.fixture
def flow_client() -> Generator[AsyncMock]:
    """The client the config flow creates."""
    with (
        patch("custom_components.watttime_stats.config_flow.WattTimeClient", autospec=True) as cls,
        patch("custom_components.watttime_stats.async_setup_entry", return_value=True),
    ):
        cls.return_value.region_from_location.return_value = REGION
        yield cls.return_value


async def _start(hass: HomeAssistant, step: str) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": step})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    return result


async def test_login(hass: HomeAssistant, flow_client: AsyncMock) -> None:
    """Signing in creates an entry for the grid region."""
    result = await _start(hass, "login")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "California ISO Northern"
    assert result["data"]["region"] == "CAISO_NORTH"
    assert result["result"].unique_id == "CAISO_NORTH"


@pytest.mark.parametrize(
    ("error", "key"),
    [(WattTimeAuthError, "invalid_auth"), (WattTimeNotFoundError, "no_region"), (RuntimeError, "unknown")],
)
async def test_login_errors(hass: HomeAssistant, flow_client: AsyncMock, error: type, key: str) -> None:
    """Errors show on the form, and the user can try again."""
    result = await _start(hass, "login")
    flow_client.login.side_effect = error("x")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}

    flow_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(hass: HomeAssistant, flow_client: AsyncMock, entry: MockConfigEntry) -> None:
    """The same grid region can't be added twice."""
    entry.add_to_hass(hass)
    result = await _start(hass, "login")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_register(hass: HomeAssistant, flow_client: AsyncMock) -> None:
    """Creating an account signs in with it."""
    with patch("custom_components.watttime_stats.config_flow.register", AsyncMock()) as register:
        result = await _start(hass, "register")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**LOGIN, CONF_EMAIL: "someone@example.com"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    register.assert_awaited_once()
    assert CONF_EMAIL not in result["data"]


async def test_register_rejected(hass: HomeAssistant, flow_client: AsyncMock) -> None:
    """WattTime refusing the sign-up shows an error."""
    with patch("custom_components.watttime_stats.config_flow.register", AsyncMock(side_effect=WattTimeError("taken"))):
        result = await _start(hass, "register")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**LOGIN, CONF_EMAIL: "someone@example.com"}
        )
    assert result["errors"] == {"base": "register_failed"}


async def test_reauth(hass: HomeAssistant, flow_client: AsyncMock, entry: MockConfigEntry) -> None:
    """A new password is saved."""
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new"


async def test_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Options are saved."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    options = {
        CONF_UNIT: "lbs_mwh",
        CONF_CLEAN_PERCENTILE: 20,
        CONF_CLEAN_MAX: 200,
        CONF_WINDOW_HOURS: 3,
        CONF_LOOKAHEAD_HOURS: 48,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options
