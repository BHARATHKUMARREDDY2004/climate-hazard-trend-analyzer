"""Heatwave definition and yearly indices.

A heatwave is a run of at least `min_days` consecutive days whose maximum
temperature is above a percentile threshold computed from a baseline period
at the same location.

Two thresholds are supported:
  fixed    - one value for the whole year (the definition in the brief).
             Heatwaves can only occur in the hottest part of the year.
  seasonal - one value per calendar day, from a 15 day window centred on that
             day. Finds unusually hot spells relative to the time of year.

The yearly indices follow the usual heatwave metrics (Perkins and Alexander,
2013): number of events, heatwave days, longest event, mean and peak intensity.
"""

from dataclasses import asdict, dataclass

import numpy as np

SEASONAL_HALF_WINDOW = 7
MIN_BASELINE_DAYS = 1000


class InsufficientData(Exception):
    pass


@dataclass
class Event:
    start: str
    end: str
    duration: int
    peak_tmax: float
    mean_tmax: float
    mean_excess: float
    # Sum of degrees above the threshold over the event: combines length and intensity.
    severity: float

    def to_dict(self) -> dict:
        return asdict(self)


def years_of(dates: np.ndarray) -> np.ndarray:
    return dates.astype("datetime64[Y]").astype(int) + 1970


def day_of_year_365(dates: np.ndarray) -> np.ndarray:
    """0..364 index on a no-leap calendar. 29 Feb shares the slot of 28 Feb."""
    year_start = dates.astype("datetime64[Y]")
    doy = (dates - year_start).astype(int)
    year = year_start.astype(int) + 1970
    leap = ((year % 4 == 0) & (year % 100 != 0)) | (year % 400 == 0)
    return np.where(leap & (doy >= 59), doy - 1, doy)


def seasonal_profile(
    dates: np.ndarray, tmax: np.ndarray, baseline: np.ndarray, percentile: float
) -> np.ndarray:
    """Threshold for each of the 365 calendar days."""
    doy = day_of_year_365(dates[baseline])
    values = tmax[baseline]
    profile = np.full(365, np.nan)
    for day in range(365):
        distance = np.abs(doy - day)
        window = values[np.minimum(distance, 365 - distance) <= SEASONAL_HALF_WINDOW]
        window = window[~np.isnan(window)]
        if window.size:
            profile[day] = np.percentile(window, percentile)
    if np.isnan(profile).any():
        raise InsufficientData("baseline period does not cover every part of the year")
    return profile


def compute_threshold(
    dates: np.ndarray,
    tmax: np.ndarray,
    baseline: np.ndarray,
    percentile: float,
    method: str,
) -> tuple[np.ndarray, dict]:
    """Returns the threshold for every day in `dates` plus a compact description."""
    valid = int(np.sum(baseline & ~np.isnan(tmax)))
    if valid < MIN_BASELINE_DAYS:
        raise InsufficientData(
            "not enough valid temperature data in the baseline period to set a threshold"
        )
    if method == "seasonal":
        profile = seasonal_profile(dates, tmax, baseline, percentile)
        return profile[day_of_year_365(dates)], {"doy": np.round(profile, 2).tolist()}

    value = float(np.nanpercentile(tmax[baseline], percentile))
    return np.full(tmax.shape, value), {"value": round(value, 2)}


def threshold_from_description(dates: np.ndarray, description: dict) -> np.ndarray:
    if "doy" in description:
        return np.asarray(description["doy"], dtype=float)[day_of_year_365(dates)]
    return np.full(dates.shape, float(description["value"]))


def hot_runs(tmax: np.ndarray, threshold: np.ndarray, min_days: int) -> list[tuple[int, int]]:
    """(start, end) index pairs, end exclusive. A missing day breaks a run."""
    with np.errstate(invalid="ignore"):
        hot = tmax > threshold
    edges = np.diff(np.concatenate(([0], hot.astype(np.int8), [0])))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_days]


def detect_events(
    dates: np.ndarray, tmax: np.ndarray, threshold: np.ndarray, min_days: int
) -> list[Event]:
    events = []
    for start, end in hot_runs(tmax, threshold, min_days):
        temps = tmax[start:end]
        excess = temps - threshold[start:end]
        events.append(
            Event(
                start=str(dates[start]),
                end=str(dates[end - 1]),
                duration=end - start,
                peak_tmax=round(float(temps.max()), 1),
                mean_tmax=round(float(temps.mean()), 1),
                mean_excess=round(float(excess.mean()), 2),
                severity=round(float(excess.sum()), 1),
            )
        )
    return events


def annual_indices(
    dates: np.ndarray,
    tmax: np.ndarray,
    threshold: np.ndarray,
    min_days: int,
    first_year: int,
    last_year: int,
) -> dict[str, np.ndarray]:
    """One value per year for every index. Intensity is nan in years without events."""
    n = last_year - first_year + 1
    year_idx = years_of(dates) - first_year
    valid = ~np.isnan(tmax)

    in_event = np.zeros(tmax.shape, dtype=bool)
    events = np.zeros(n)
    longest = np.zeros(n)
    for start, end in hot_runs(tmax, threshold, min_days):
        in_event[start:end] = True
        # An event that runs over New Year is counted once, in the year it began,
        # while its days are still credited to the calendar year they fall in.
        y = year_idx[start]
        events[y] += 1
        longest[y] = max(longest[y], end - start)

    def per_year(weights) -> np.ndarray:
        return np.bincount(year_idx, weights=weights, minlength=n).astype(float)

    days = per_year(in_event)
    excess = np.where(in_event, tmax - threshold, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        hot_days = per_year(np.nan_to_num(tmax - threshold, nan=-1.0) > 0)
        mean_excess = np.where(days > 0, per_year(excess) / days, np.nan)
        mean_tmax = per_year(np.nan_to_num(tmax)) / per_year(valid)
        coverage = per_year(valid) / per_year(np.ones(tmax.shape))

    peak = np.full(n, np.nan)
    max_tmax = np.full(n, np.nan)
    for y in range(n):
        in_year = year_idx == y
        if (in_year & in_event).any():
            peak[y] = tmax[in_year & in_event].max()
        if (in_year & valid).any():
            max_tmax[y] = tmax[in_year & valid].max()

    return {
        "events": events,
        "days": days,
        "longest": longest,
        "mean_excess": mean_excess,
        "peak_tmax": peak,
        "hot_days": hot_days,
        "mean_tmax": mean_tmax,
        "max_tmax": max_tmax,
        "coverage": coverage,
    }


def monthly_heatwave_days(
    dates: np.ndarray, tmax: np.ndarray, threshold: np.ndarray, min_days: int, year_mask: np.ndarray
) -> np.ndarray:
    """Total heatwave days per calendar month over the years selected by `year_mask`."""
    in_event = np.zeros(tmax.shape, dtype=bool)
    for start, end in hot_runs(tmax, threshold, min_days):
        in_event[start:end] = True
    month = dates.astype("datetime64[M]").astype(int) % 12
    return np.bincount(month[in_event & year_mask], minlength=12).astype(float)
