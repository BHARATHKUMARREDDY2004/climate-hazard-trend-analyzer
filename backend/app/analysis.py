"""Runs a heatwave analysis for a region and stores the result.

Flow: region -> grid cells -> cached daily data -> quality control ->
threshold -> events and yearly indices -> trends -> insights -> database.
"""

import hashlib
import json
import math
import threading
import time
import warnings
from datetime import date

import numpy as np

from . import heatwave, weather
from .cleaning import clean_series
from .config import ALGORITHM_VERSION
from .insights import build_insights
from .schemas import AnalysisRequest, BoxRegion
from .storage import ANALYSES, Store
from .trends import analyze_trend, rolling_mean

TREND_METRICS = ("days", "events", "longest", "mean_excess", "peak_tmax", "mean_tmax")
COMPLETE_YEAR_COVERAGE = 0.9

# Results that include the running year go stale as new days arrive.
TTL_OPEN_PERIOD = 24 * 3600
TTL_CLOSED_PERIOD = 30 * 24 * 3600

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def cells_for_region(region) -> list[tuple[float, float]]:
    if not isinstance(region, BoxRegion):
        return [(weather.snap(region.lat), weather.snap(region.lon))]

    def axis(low: float, high: float) -> list[float]:
        span = high - low
        count = 1 if span < 0.5 else 2 if span < 2 else 3
        return [low + span * (i + 0.5) / count for i in range(count)]

    cells = [
        (weather.snap(lat), weather.snap(lon))
        for lat in axis(region.south, region.north)
        for lon in axis(region.west, region.east)
    ]
    return list(dict.fromkeys(cells))


def region_label(region) -> str:
    if region.label:
        return region.label
    if isinstance(region, BoxRegion):
        return f"{region.south:.2f}°, {region.west:.2f}° to {region.north:.2f}°, {region.east:.2f}°"
    return f"{region.lat:.2f}°, {region.lon:.2f}°"


def analysis_id(request: AnalysisRequest, cells: list) -> str:
    key = {
        "v": ALGORITHM_VERSION,
        "cells": cells,
        "request": request.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def run_analysis(request: AnalysisRequest, store: Store) -> dict:
    cells = cells_for_region(request.region)
    doc_id = analysis_id(request, cells)

    # One lock per analysis: identical requests arriving together wait for the
    # first one instead of all hitting the weather API.
    with _locks_guard:
        lock = _locks.setdefault(doc_id, threading.Lock())
    try:
        with lock:
            stored = store.get(ANALYSES, doc_id)
            if stored:
                stored["served_from"] = "database"
                return stored
            doc = _compute(request, cells, doc_id, store)
            store.put_many(ANALYSES, [doc])
            doc["served_from"] = "computed"
            return doc
    finally:
        with _locks_guard:
            _locks.pop(doc_id, None)


def _num(value, digits: int = 2):
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) or math.isinf(value) else round(value, digits)


def _compute(request: AnalysisRequest, cells: list, doc_id: str, store: Store) -> dict:
    started = time.perf_counter()
    first, last = request.start_year, request.end_year
    base_first, base_last = request.baseline_years()
    years = list(range(first, last + 1))

    series, cache_stats = weather.load_daily_tmax(
        cells, min(first, base_first), max(last, base_last), store
    )

    half = len(years) // 2
    halves = {"early": (first, first + half - 1), "late": (last - half + 1, last)}

    per_cell: list[dict[str, np.ndarray]] = []
    monthly = {"early": np.zeros(12), "late": np.zeros(12)}
    quality = dict.fromkeys(("missing", "out_of_range", "spike", "interpolated", "unfilled"), 0)
    cell_info, events = [], []

    for cell in series:
        cleaned, flags = clean_series(cell.tmax)
        cell_years = heatwave.years_of(cell.dates)
        baseline = (cell_years >= base_first) & (cell_years <= base_last)
        threshold, description = heatwave.compute_threshold(
            cell.dates, cleaned, baseline, request.percentile, request.threshold_method
        )

        period = (cell_years >= first) & (cell_years <= last)
        dates, tmax, limit = cell.dates[period], cleaned[period], threshold[period]

        per_cell.append(
            heatwave.annual_indices(dates, tmax, limit, request.min_duration, first, last)
        )
        for event in heatwave.detect_events(dates, tmax, limit, request.min_duration):
            events.append({**event.to_dict(), "cell": len(cell_info)})
        for name, (y0, y1) in halves.items():
            in_half = (cell_years[period] >= y0) & (cell_years[period] <= y1)
            monthly[name] += heatwave.monthly_heatwave_days(
                dates, tmax, limit, request.min_duration, in_half
            )
        for name in quality:
            quality[name] += int(flags[name][period].sum())

        cell_info.append(
            {
                "lat": cell.lat,
                "lon": cell.lon,
                "grid_lat": cell.grid_lat,
                "grid_lon": cell.grid_lon,
                "elevation": cell.elevation,
                "threshold": description,
            }
        )

    # Regional value = mean over the sample points of each point's own index.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        regional = {
            name: np.nanmean(np.stack([c[name] for c in per_cell]), axis=0)
            for name in per_cell[0]
        }
    coverage = np.min(np.stack([c["coverage"] for c in per_cell]), axis=0)

    annual = []
    for i, year in enumerate(years):
        annual.append(
            {
                "year": year,
                "events": _num(regional["events"][i]),
                "days": _num(regional["days"][i]),
                "longest": _num(regional["longest"][i]),
                "mean_excess": _num(regional["mean_excess"][i]),
                "peak_tmax": _num(regional["peak_tmax"][i], 1),
                "hot_days": _num(regional["hot_days"][i]),
                "mean_tmax": _num(regional["mean_tmax"][i]),
                "max_tmax": _num(regional["max_tmax"][i], 1),
                "coverage": _num(coverage[i], 3) or 0.0,
                "complete": bool(coverage[i] >= COMPLETE_YEAR_COVERAGE),
            }
        )

    def usable(metric: str) -> list:
        return [row[metric] if row["complete"] else None for row in annual]

    trends = {m: analyze_trend(years, usable(m)) for m in TREND_METRICS}
    rolling = {m: rolling_mean(usable(m)) for m in TREND_METRICS}

    decades: dict[int, list[dict]] = {}
    for row in annual:
        if row["complete"]:
            decades.setdefault(row["year"] // 10 * 10, []).append(row)
    decadal = [
        {
            "decade": f"{decade}s",
            "years": len(rows),
            "days": _num(np.mean([r["days"] for r in rows])),
            "events": _num(np.mean([r["events"] for r in rows])),
            "longest": _num(max(r["longest"] for r in rows), 1),
            "mean_tmax": _num(np.mean([r["mean_tmax"] for r in rows])),
        }
        for decade, rows in sorted(decades.items())
    ]

    n_cells = len(series)
    fixed = [c["threshold"]["value"] for c in cell_info if "value" in c["threshold"]]
    total_days = n_cells * int((np.datetime64(f"{last + 1}-01-01") - np.datetime64(f"{first}-01-01")).astype(int))
    events.sort(key=lambda e: e["start"])
    now = time.time()
    open_period = last >= date.today().year - 1

    doc = {
        "_id": doc_id,
        "id": doc_id,
        "created_at": now,
        "expires_at": now + (TTL_OPEN_PERIOD if open_period else TTL_CLOSED_PERIOD),
        "algorithm_version": ALGORITHM_VERSION,
        "params": {
            "hazard": request.hazard,
            "start_year": first,
            "end_year": last,
            "percentile": request.percentile,
            "min_duration": request.min_duration,
            "threshold_method": request.threshold_method,
            "baseline": request.baseline,
            "baseline_years": [base_first, base_last],
        },
        "region": {
            "type": request.region.type,
            "label": region_label(request.region),
            "bounds": request.region.model_dump(exclude={"label", "type"}),
            "cells": cell_info,
        },
        "threshold": {
            "method": request.threshold_method,
            "mean_value": _num(np.mean(fixed)) if fixed else None,
            "min_value": _num(min(fixed)) if fixed else None,
            "max_value": _num(max(fixed)) if fixed else None,
        },
        "annual": annual,
        "rolling": rolling,
        "trends": trends,
        "decadal": decadal,
        "monthly": {
            name: {
                "from": halves[name][0],
                "to": halves[name][1],
                # average heatwave days per year in each month
                "days": [_num(v / n_cells / half) for v in monthly[name]],
            }
            for name in ("early", "late")
        },
        "events": events,
        "summary": _summary(annual, events, n_cells),
        "quality": {
            **quality,
            "total_days": total_days,
            "valid_share": _num(1 - quality["unfilled"] / total_days, 4),
            "incomplete_years": [r["year"] for r in annual if not r["complete"]],
            "cell_years_requested": cache_stats["cell_years"],
            "cell_years_from_cache": cache_stats["from_cache"],
        },
        "source": {"name": weather.SOURCE, "variable": "temperature_2m_max", "unit": "°C"},
    }
    doc["insights"] = build_insights(doc)
    doc["compute_seconds"] = round(time.perf_counter() - started, 2)
    return doc


def _summary(annual: list[dict], events: list[dict], n_cells: int) -> dict:
    complete = [r for r in annual if r["complete"]]
    longest = max(events, key=lambda e: e["duration"], default=None)
    hottest = max(events, key=lambda e: e["peak_tmax"], default=None)
    return {
        "complete_years": len(complete),
        "total_events": len(events) if n_cells == 1 else None,
        "mean_days_per_year": _num(np.mean([r["days"] for r in complete])) if complete else None,
        "mean_events_per_year": _num(np.mean([r["events"] for r in complete])) if complete else None,
        "years_with_heatwave": sum(1 for r in complete if r["days"] > 0),
        "longest_event": longest,
        "hottest_event": hottest,
    }


def daily_detail(doc: dict, year: int, cell_index: int, store: Store) -> dict:
    """Daily series for one year and one sample point, for the drill-down chart."""
    cell = doc["region"]["cells"][cell_index]
    series, _ = weather.load_daily_tmax([(cell["lat"], cell["lon"])], year, year, store)
    cleaned, flags = clean_series(series[0].tmax)
    dates = series[0].dates
    threshold = heatwave.threshold_from_description(dates, cell["threshold"])
    first_day, last_day = f"{year}-01-01", f"{year}-12-31"
    return {
        "year": year,
        "cell": cell_index,
        "lat": cell["lat"],
        "lon": cell["lon"],
        "dates": [str(d) for d in dates],
        "tmax": [_num(v, 1) for v in cleaned],
        "threshold": [_num(v, 1) for v in threshold],
        "interpolated": [i for i, f in enumerate(flags["interpolated"]) if f],
        "events": [
            e
            for e in doc["events"]
            if e["cell"] == cell_index and e["start"] <= last_day and e["end"] >= first_day
        ],
    }
