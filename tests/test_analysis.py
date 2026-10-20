"""Clean-window maths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.watttime_stats.analysis import (
    Point,
    clean_outlook,
    cleanest_window,
    latest,
    parse_points,
    threshold_for,
    upcoming,
)

T0 = datetime(2026, 10, 20, 17, 0, tzinfo=UTC)
STEP = timedelta(minutes=5)


def series(values: list[float]) -> list[Point]:
    return [Point(T0 + i * STEP, v) for i, v in enumerate(values)]


def test_parse_points_sorts_and_skips_missing() -> None:
    rows = [
        {"point_time": "2026-10-20T17:05:00Z", "value": 2},
        {"point_time": "2026-10-20T17:00:00+00:00", "value": 1},
        {"point_time": "2026-10-20T17:10:00+00:00", "value": None},
    ]
    assert [p.value for p in parse_points(rows)] == [1.0, 2.0]


def test_latest_and_upcoming() -> None:
    pts = series([1, 2, 3, 4])
    now = T0 + timedelta(minutes=7)
    assert latest(pts, now).value == 2
    assert [p.value for p in upcoming(pts, now, 1)] == [2, 3, 4]  # the 17:05 interval is still running


def test_cleanest_window() -> None:
    pts = series([9, 9, 1, 1, 9, 2, 2, 9])
    win = cleanest_window(pts, 2 * STEP)
    assert (win.start, win.end, win.average) == (T0 + 2 * STEP, T0 + 4 * STEP, 1)


def test_threshold_is_capped() -> None:
    all_gas = series([900] * 100)
    assert threshold_for(all_gas, 25, 500) == 500
    assert clean_outlook(all_gas, 25, 500) == clean_outlook(all_gas, 25, 500)
    assert not clean_outlook(all_gas, 25, 500).clean_now
    assert clean_outlook(all_gas, 25, 500).next_start is None


def test_clean_now_until() -> None:
    pts = series([0, 0, 900, 900, 900, 900, 900, 900])
    out = clean_outlook(pts, 25, 500)
    assert out.clean_now
    assert out.until == T0 + 2 * STEP


def test_next_clean() -> None:
    pts = series([900, 900, 0, 0, 900, 900, 900, 900])
    out = clean_outlook(pts, 25, 500)
    assert not out.clean_now
    assert (out.next_start, out.next_end) == (T0 + 2 * STEP, T0 + 4 * STEP)


def test_clean_to_end_of_forecast() -> None:
    pts = series([900, 900, 900, 900, 900, 900, 0, 0])
    out = clean_outlook(pts, 25, 500)
    assert out.next_end == T0 + 8 * STEP
