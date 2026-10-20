"""Fetches WattTime data every 5 minutes and works out the clean outlook."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .analysis import Outlook, Point, Window, clean_outlook, cleanest_window, latest, parse_points, upcoming
from .api import WattTimeAccessError, WattTimeAuthError, WattTimeClient, WattTimeError, access_set
from .const import (
    ACCESS_RECHECK,
    CONF_CLEAN_MAX,
    CONF_CLEAN_PERCENTILE,
    CONF_LOOKAHEAD_HOURS,
    CONF_REGION,
    CONF_WINDOW_HOURS,
    DEFAULT_CLEAN_MAX,
    DEFAULT_CLEAN_PERCENTILE,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_WINDOW_HOURS,
    DOMAIN,
    ENDPOINT_FORECAST,
    ENDPOINT_HISTORICAL,
    G_KWH_PER_LBS_MWH,
    LIVE_LOOKBACK,
    SIGNAL_HEALTH,
    SIGNAL_MOER,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type WattTimeConfigEntry = ConfigEntry[WattTimeCoordinator]


@dataclass
class WattTimeData:
    """Everything the entities show. CO2 values are in lbs/MWh."""

    index: float | None = None
    index_time: datetime | None = None
    moer: Point | None = None
    moer_source: str | None = None  # "live" (measured) or "forecast"
    health: Point | None = None
    forecast: list[Point] = field(default_factory=list)
    forecast_generated_at: datetime | None = None
    window: Window | None = None
    outlook: Outlook | None = None


class WattTimeCoordinator(DataUpdateCoordinator[WattTimeData]):
    """One coordinator per config entry (one grid region)."""

    config_entry: WattTimeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: WattTimeConfigEntry, client: WattTimeClient) -> None:
        """Set up the coordinator."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.client = client
        self.region: str = entry.data[CONF_REGION]
        self.access: frozenset[tuple[str, str]] = frozenset()
        self._access_checked: float | None = None
        opts = entry.options
        self.lookahead = float(opts.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS))
        self.window_hours = float(opts.get(CONF_WINDOW_HOURS, DEFAULT_WINDOW_HOURS))
        self.percentile = float(opts.get(CONF_CLEAN_PERCENTILE, DEFAULT_CLEAN_PERCENTILE))
        self.cap = float(opts.get(CONF_CLEAN_MAX, DEFAULT_CLEAN_MAX)) / G_KWH_PER_LBS_MWH

    def has(self, signal: str, endpoint: str) -> bool:
        """Whether this account can use an endpoint for a signal in this region."""
        return (signal, endpoint) in self.access

    async def _refresh_access(self) -> None:
        checked = self._access_checked
        if checked is not None and time.monotonic() - checked < ACCESS_RECHECK.total_seconds():
            return
        try:
            self.access = access_set(await self.client.my_access(), self.region)
        except WattTimeAccessError:
            self.access = frozenset()
        self._access_checked = time.monotonic()
        _LOGGER.debug("WattTime access for %s: %s", self.region, sorted(self.access))

    async def _latest(self, signal: str, now: datetime) -> Point | None:
        resp = await self.client.historical(self.region, signal, now - LIVE_LOOKBACK, now)
        return latest(parse_points(resp.get("data", [])), now)

    async def _async_update_data(self) -> WattTimeData:
        now = dt_util.utcnow()
        data = WattTimeData()
        try:
            await self._refresh_access()
            idx = (await self.client.signal_index(self.region)).get("data") or []
            if idx:
                data.index = idx[0].get("value")
                data.index_time = dt_util.parse_datetime(idx[0].get("point_time", ""))
            if self.has(SIGNAL_MOER, ENDPOINT_FORECAST):
                resp = await self.client.forecast(self.region, SIGNAL_MOER, math.ceil(self.lookahead))
                data.forecast = parse_points(resp.get("data", []))
                data.forecast_generated_at = dt_util.parse_datetime((resp.get("meta") or {}).get("generated_at", ""))
            if self.has(SIGNAL_MOER, ENDPOINT_HISTORICAL):
                data.moer, data.moer_source = await self._latest(SIGNAL_MOER, now), "live"
            if data.moer is None and data.forecast:
                data.moer, data.moer_source = latest(data.forecast, now) or data.forecast[0], "forecast"
            if self.has(SIGNAL_HEALTH, ENDPOINT_HISTORICAL):
                data.health = await self._latest(SIGNAL_HEALTH, now)
        except WattTimeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except WattTimeAccessError as err:
            self._access_checked = None  # plan changed; look again next time
            raise UpdateFailed(str(err)) from err
        except WattTimeError as err:
            raise UpdateFailed(str(err)) from err

        ahead = upcoming(data.forecast, now, self.lookahead)
        data.window = cleanest_window(ahead, timedelta(hours=self.window_hours))
        data.outlook = clean_outlook(ahead, self.percentile, self.cap)
        return data
