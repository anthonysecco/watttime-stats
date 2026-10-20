"""Forecast analysis: current value, cleanest window, and when it is "clean".

Pure functions with no Home Assistant imports, so they are easy to test.
All values are in WattTime's native lbs/MWh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

DEFAULT_STEP = timedelta(minutes=5)


@dataclass(frozen=True)
class Point:
    """One value, valid from `time` for one step."""

    time: datetime
    value: float


@dataclass(frozen=True)
class Window:
    """The lowest-average stretch of a given length."""

    start: datetime
    end: datetime
    average: float


@dataclass(frozen=True)
class Outlook:
    """Whether it is clean now, and until when; or when the next clean stretch is."""

    threshold: float
    clean_now: bool
    until: datetime | None = None
    next_start: datetime | None = None
    next_end: datetime | None = None


def parse_points(data: list[dict[str, Any]]) -> list[Point]:
    """Turn WattTime `data` rows into sorted Points."""
    points = [
        Point(datetime.fromisoformat(row["point_time"].replace("Z", "+00:00")), float(row["value"]))
        for row in data
        if row.get("value") is not None
    ]
    return sorted(points, key=lambda p: p.time)


def step_of(points: list[Point]) -> timedelta:
    """Spacing between points."""
    return points[1].time - points[0].time if len(points) > 1 else DEFAULT_STEP


def latest(points: list[Point], now: datetime) -> Point | None:
    """The most recent point that has started by `now`."""
    started = [p for p in points if p.time <= now]
    return started[-1] if started else None


def upcoming(points: list[Point], now: datetime, hours: float) -> list[Point]:
    """Points whose interval is still running at `now`, up to `hours` ahead."""
    if not points:
        return []
    step = step_of(points)
    end = now + timedelta(hours=hours)
    return [p for p in points if p.time + step > now and p.time <= end]


def cleanest_window(points: list[Point], length: timedelta) -> Window | None:
    """Lowest-average stretch of `length` within `points`."""
    if not points:
        return None
    step = step_of(points)
    n = max(1, min(len(points), round(length / step)))
    best_i, best_sum = 0, sum(p.value for p in points[:n])
    run = best_sum
    for i in range(1, len(points) - n + 1):
        run += points[i + n - 1].value - points[i - 1].value
        if run < best_sum - 1e-9:
            best_i, best_sum = i, run
    chunk = points[best_i : best_i + n]
    return Window(chunk[0].time, chunk[-1].time + step, best_sum / len(chunk))


def threshold_for(points: list[Point], percentile: float, cap: float) -> float:
    """Value at `percentile` of `points`, never above `cap`."""
    ranked = sorted(p.value for p in points)
    return min(ranked[int(percentile / 100 * (len(ranked) - 1))], cap)


def clean_outlook(points: list[Point], percentile: float, cap: float) -> Outlook | None:
    """Clean = at or below the percentile threshold (capped). `points` starts now."""
    if not points:
        return None
    step = step_of(points)
    threshold = threshold_for(points, percentile, cap)
    if points[0].value <= threshold:
        until = next((p.time for p in points if p.value > threshold), None)
        return Outlook(threshold, True, until=until)
    start = next((p.time for p in points if p.value <= threshold), None)
    if start is None:
        return Outlook(threshold, False)
    end = next((p.time for p in points if p.time > start and p.value > threshold), None)
    return Outlook(threshold, False, next_start=start, next_end=end or points[-1].time + step)
