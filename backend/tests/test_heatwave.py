import numpy as np
import pytest

from app import heatwave


def days(start: str, count: int) -> np.ndarray:
    return np.datetime64(start) + np.arange(count)


def test_three_consecutive_hot_days_make_one_event():
    dates = days("2001-05-01", 8)
    tmax = np.array([30, 41, 42, 43, 30, 41, 41, 30], dtype=float)
    events = heatwave.detect_events(dates, tmax, np.full(8, 40.0), min_days=3)
    assert len(events) == 1
    event = events[0]
    assert (event.start, event.end, event.duration) == ("2001-05-02", "2001-05-04", 3)
    assert event.peak_tmax == 43.0
    assert event.mean_excess == 2.0
    assert event.severity == 6.0


def test_a_day_equal_to_the_threshold_does_not_count():
    dates = days("2001-05-01", 5)
    tmax = np.array([41, 40, 41, 41, 30], dtype=float)
    assert heatwave.detect_events(dates, tmax, np.full(5, 40.0), min_days=3) == []


def test_a_missing_day_breaks_the_run():
    dates = days("2001-05-01", 7)
    tmax = np.array([41, 41, np.nan, 41, 41, 30, 30], dtype=float)
    assert heatwave.detect_events(dates, tmax, np.full(7, 40.0), min_days=3) == []


def test_fixed_threshold_is_the_percentile_of_the_baseline_only():
    dates = days("2000-01-01", 2000)
    tmax = np.concatenate([np.linspace(0, 100, 1500), np.full(500, 500.0)])
    baseline = np.arange(2000) < 1500
    threshold, description = heatwave.compute_threshold(dates, tmax, baseline, 95, "fixed")
    assert description["value"] == pytest.approx(95.0, abs=0.1)
    assert np.all(threshold == threshold[0])


def test_seasonal_threshold_follows_the_time_of_year():
    dates = days("1990-01-01", 365 * 12 + 3)
    doy = heatwave.day_of_year_365(dates)
    rng = np.random.default_rng(1)
    tmax = 25 + 10 * np.sin(2 * np.pi * (doy - 100) / 365) + rng.normal(0, 1, dates.size)
    threshold, description = heatwave.compute_threshold(
        dates, tmax, np.ones(dates.size, dtype=bool), 90, "seasonal"
    )
    profile = np.array(description["doy"])
    assert profile.size == 365
    assert profile.max() - profile.min() > 15
    # about 10% of days should exceed a 90th percentile threshold, in every season
    share = np.mean(tmax > threshold)
    assert 0.07 < share < 0.13
    winter = (doy < 60) | (doy > 330)
    assert np.mean(tmax[winter] > threshold[winter]) > 0.05


def test_leap_day_shares_the_slot_of_28_february():
    dates = np.array(["2020-02-28", "2020-02-29", "2020-03-01", "2021-03-01", "2020-12-31"], dtype="datetime64[D]")
    assert heatwave.day_of_year_365(dates).tolist() == [58, 58, 59, 59, 364]


def test_too_little_baseline_data_is_refused():
    dates = days("2000-01-01", 400)
    with pytest.raises(heatwave.InsufficientData):
        heatwave.compute_threshold(dates, np.full(400, 30.0), np.ones(400, dtype=bool), 95, "fixed")


def test_annual_indices():
    dates = days("2001-01-01", 730)
    tmax = np.full(730, 30.0)
    tmax[100:104] = 42.0          # 4 day event in 2001
    tmax[200:203] = 41.0          # 3 day event in 2001
    tmax[300:302] = 45.0          # 2 hot days, too short to be an event
    tmax[365 + 50 : 365 + 55] = 44.0  # 5 day event in 2002
    result = heatwave.annual_indices(dates, tmax, np.full(730, 40.0), 3, 2001, 2002)

    assert result["events"].tolist() == [2, 1]
    assert result["days"].tolist() == [7, 5]
    assert result["longest"].tolist() == [4, 5]
    assert result["hot_days"].tolist() == [9, 5]
    assert result["peak_tmax"].tolist() == [42.0, 44.0]
    assert result["mean_excess"][0] == pytest.approx((4 * 2 + 3 * 1) / 7)
    assert result["max_tmax"].tolist() == [45.0, 44.0]
    assert result["coverage"].tolist() == [1.0, 1.0]


def test_event_across_new_year_is_counted_once_and_days_are_split():
    dates = days("2001-01-01", 730)
    tmax = np.full(730, 30.0)
    tmax[362:369] = 42.0  # 29 Dec 2001 to 4 Jan 2002
    result = heatwave.annual_indices(dates, tmax, np.full(730, 40.0), 3, 2001, 2002)
    assert result["events"].tolist() == [1, 0]
    assert result["days"].tolist() == [3, 4]
    assert result["longest"].tolist() == [7, 0]


def test_year_without_events_has_no_intensity():
    dates = days("2001-01-01", 365)
    result = heatwave.annual_indices(dates, np.full(365, 30.0), np.full(365, 40.0), 3, 2001, 2001)
    assert result["days"][0] == 0
    assert np.isnan(result["mean_excess"][0]) and np.isnan(result["peak_tmax"][0])
