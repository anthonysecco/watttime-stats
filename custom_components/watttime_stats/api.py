"""Small async client for the WattTime v3 API."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any

import aiohttp

from .const import API_URL, SIGNAL_MOER

TOKEN_MAX_AGE = 25 * 60  # tokens last 30 minutes
TIMEOUT = aiohttp.ClientTimeout(total=20)


class WattTimeError(Exception):
    """Base error."""


class WattTimeAuthError(WattTimeError):
    """Username or password was rejected."""


class WattTimeAccessError(WattTimeError):
    """The account's plan does not include this data."""


class WattTimeConnectionError(WattTimeError):
    """WattTime could not be reached or returned a server error."""


class WattTimeNotFoundError(WattTimeError):
    """WattTime has no data for the request (for example, a location outside coverage)."""


def _utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class WattTimeClient:
    """Talks to api.watttime.org; logs in on demand and refreshes the token."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        """Store the session and credentials."""
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_at = 0.0

    async def login(self) -> None:
        """Exchange the username and password for a token."""
        try:
            async with self._session.get(
                f"{API_URL}/login",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise WattTimeAuthError("WattTime rejected the username or password")
                if resp.status >= 400:
                    raise WattTimeConnectionError(f"Login failed: HTTP {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WattTimeConnectionError(f"Cannot reach WattTime: {err}") from err
        self._token = data["token"]
        self._token_at = time.monotonic()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._token is None or time.monotonic() - self._token_at > TOKEN_MAX_AGE:
            await self.login()
        for attempt in range(2):
            try:
                async with self._session.request(
                    method,
                    f"{API_URL}/{path}",
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=TIMEOUT,
                    **kwargs,
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        await self.login()  # token expired early
                        continue
                    if resp.status == 401:
                        raise WattTimeAuthError("WattTime rejected the login token")
                    if resp.status == 403:
                        raise WattTimeAccessError(f"{path} is not included in this WattTime plan")
                    if resp.status == 404:
                        raise WattTimeNotFoundError(f"{path}: no data")
                    if resp.status == 429:
                        raise WattTimeConnectionError("WattTime rate limit reached")
                    if resp.status >= 400:
                        text = (await resp.text())[:200]
                        if resp.status < 500 and "not found" in text.lower():
                            raise WattTimeNotFoundError(text)
                        raise WattTimeConnectionError(f"{path}: HTTP {resp.status} {text}")
                    return await resp.json()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise WattTimeConnectionError(f"Cannot reach WattTime: {err}") from err
        raise WattTimeAuthError("WattTime rejected the login token")  # pragma: no cover

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params or {})

    async def region_from_location(
        self, latitude: float, longitude: float, signal_type: str = SIGNAL_MOER
    ) -> dict[str, Any]:
        """Return the grid region serving a location."""
        return await self._get(
            "v3/region-from-loc",
            {"signal_type": signal_type, "latitude": latitude, "longitude": longitude},
        )

    async def my_access(self) -> dict[str, Any]:
        """Return what this account can access."""
        return await self._get("v3/my-access")

    async def signal_index(self, region: str) -> dict[str, Any]:
        """Return the current 0-100 index (free in every region)."""
        return await self._get("v3/signal-index", {"region": region, "signal_type": SIGNAL_MOER})

    async def forecast(self, region: str, signal_type: str, horizon_hours: int) -> dict[str, Any]:
        """Return the latest forecast."""
        return await self._get(
            "v3/forecast",
            {"region": region, "signal_type": signal_type, "horizon_hours": horizon_hours},
        )

    async def historical(
        self, region: str, signal_type: str, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Return measured values between start and end (UTC)."""
        return await self._get(
            "v3/historical",
            {"region": region, "signal_type": signal_type, "start": _utc(start), "end": _utc(end)},
        )


async def register(
    session: aiohttp.ClientSession, username: str, password: str, email: str, org: str | None
) -> None:
    """Create a WattTime account (WattTime has no sign-up web page)."""
    body = {"username": username, "password": password, "email": email}
    if org:
        body["org"] = org
    try:
        async with session.post(f"{API_URL}/register", json=body, timeout=TIMEOUT) as resp:
            if resp.status >= 400:
                text = (await resp.text())[:300]
                raise WattTimeError(text or f"HTTP {resp.status}")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise WattTimeConnectionError(f"Cannot reach WattTime: {err}") from err


def access_set(access: dict[str, Any], region: str) -> frozenset[tuple[str, str]]:
    """Turn a /v3/my-access response into {(signal_type, endpoint)} for one region."""
    found = set()
    for signal in access.get("signal_types", []):
        for reg in signal.get("regions", []):
            if reg.get("region") != region:
                continue
            for endpoint in reg.get("endpoints", []):
                found.add((signal.get("signal_type"), endpoint.get("endpoint")))
    return frozenset(found)
