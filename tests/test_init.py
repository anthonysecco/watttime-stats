"""Setting up the integration with a fake account."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watttime_stats.api import WattTimeAuthError
from custom_components.watttime_stats.const import CONF_UNIT, DOMAIN, SERVICE_GET_FORECAST
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import PAID_ACCESS


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """Every entity is created under the same IDs the old template sensors used."""
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.watttime_emissions_index").state == "37"

    moer = hass.states.get("sensor.watttime_marginal_emissions")
    assert moer.state == "408.2"  # 900 lbs/MWh live value, in g/kWh
    assert moer.attributes["unit_of_measurement"] == "g/kWh"
    assert moer.attributes["source"] == "live"

    assert hass.states.get("sensor.watttime_health_damage").state == "12.5"
    assert hass.states.get("binary_sensor.watttime_clean_now").state == "on"
    assert hass.states.get("sensor.watttime_clean_until").state not in ("unknown", "unavailable")
    assert hass.states.get("sensor.watttime_next_clean").state == "unknown"
    assert hass.states.get("sensor.watttime_clean_status").state.startswith("Clean until ")
    assert hass.states.get("sensor.watttime_clean_threshold").state == "227.0"

    window = hass.states.get("sensor.watttime_cleanest_window")
    assert window.state not in ("unknown", "unavailable")
    assert window.attributes["average"] == 0.0

    # Free plan: no average emissions, and no extra region lookup for them
    assert hass.states.get("sensor.watttime_average_emissions") is None
    mock_client.region_from_location.assert_not_called()


async def test_average_emissions_paid_plan(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """Accounts with AOER get average emissions for the parent region (CAISO)."""
    mock_client.my_access.return_value = PAID_ACCESS
    mock_client.region_from_location.return_value = {"region": "CAISO", "signal_type": "co2_aoer"}
    await _setup(hass, entry)

    state = hass.states.get("sensor.watttime_average_emissions")
    assert state.state == "226.8"  # 500 lbs/MWh in g/kWh
    assert state.attributes["unit_of_measurement"] == "g/kWh"
    assert state.attributes["region"] == "CAISO"
    mock_client.region_from_location.assert_awaited_once_with(37.33, -121.95, "co2_aoer")


async def test_index_is_whole_number(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """WattTime can send the index with decimals; it's shown as a whole number."""
    mock_client.signal_index.return_value = {"data": [{"point_time": "2026-10-20T22:00:00+00:00", "value": 63.6}]}
    await _setup(hass, entry)
    assert hass.states.get("sensor.watttime_emissions_index").state == "64"


async def test_index_only_account(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """Outside California, free accounts only get the index."""
    mock_client.my_access.return_value = {"signal_types": []}
    await _setup(hass, entry)
    assert hass.states.get("sensor.watttime_emissions_index").state == "37"
    assert hass.states.get("sensor.watttime_marginal_emissions").state == "unknown"
    assert hass.states.get("binary_sensor.watttime_clean_now") is None
    assert hass.states.get("sensor.watttime_cleanest_window") is None
    assert hass.states.get("sensor.watttime_health_damage") is None
    mock_client.forecast.assert_not_called()


async def test_get_forecast(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """The action returns the forecast in the chosen unit."""
    await _setup(hass, entry)
    resp = await hass.services.async_call(DOMAIN, SERVICE_GET_FORECAST, {}, blocking=True, return_response=True)
    assert resp["region"] == "CAISO_NORTH"
    assert resp["unit"] == "g/kWh"
    assert 280 <= len(resp["forecast"]) <= 288
    assert {p["value"] for p in resp["forecast"]} == {0.0, 408.2}


async def test_unit_option(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """Switching to lbs/MWh reloads and shows WattTime's native unit."""
    await _setup(hass, entry)
    hass.config_entries.async_update_entry(entry, options={CONF_UNIT: "lbs_mwh"})
    await hass.async_block_till_done()
    moer = hass.states.get("sensor.watttime_marginal_emissions")
    assert moer.state == "900.0"
    assert moer.attributes["unit_of_measurement"] == "lbs/MWh"


async def test_auth_failure_starts_reauth(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """A rejected password asks the user to sign in again."""
    mock_client.my_access.side_effect = WattTimeAuthError("nope")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_unload(hass: HomeAssistant, mock_client: AsyncMock, entry: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
