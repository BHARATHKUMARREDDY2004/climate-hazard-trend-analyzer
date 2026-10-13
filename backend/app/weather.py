"""Daily maximum temperature from the Open-Meteo archive (ERA5), cached per
grid cell and calendar year.

Caching by year means a request for 1990-2020 followed by one for 1980-2020
only downloads 1980-1989. Years that can still change (the running year and
the last three months, which ERA5 revises) are refreshed once a day.
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from .config import ARCHIVE_LAG_DAYS
from .storage import DAILY, Store
from .upstream import UpstreamError, get_json

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE = "Open-Meteo Historical Weather API, ERA5 reanalysis (0.25 degree)"

CELLS_PER_REQUEST = 10
REFRESH_SECONDS = 24 * 3600
FINAL_AFTER_DAYS = 90


@dataclass
class CellSeries:
    lat: float
    lon: float
    grid_lat: float | None
    grid_lon: float | None
    elevation: float | None
    dates: np.ndarray  # datetime64[D]
    tmax: np.ndarray  # degrees C, nan where missing


def snap(value: float) -> float:
    # 0.1 degree is finer than the 0.25 degree ERA5 grid, so nothing is lost,
    # and nearby map clicks land on the same cache entry.
    return round(round(value * 10) / 10, 1)


def cell_key(lat: float, lon: float) -> str:
    return f"{lat:.1f}_{lon:.1f}"


def _doc_id(lat: float, lon: float, year: int) -> str:
    return f"{cell_key(lat, lon)}_{year}"


def _is_fresh(doc: dict) -> bool:
    return bool(doc.get("final")) or time.time() - doc.get("fetched_at", 0) < REFRESH_SECONDS


def _to_celsius(values: list, unit: str) -> list:
    unit = (unit or "").strip().lower()
    if unit in ("°c", "c", "celsius"):
        convert = lambda v: v
    elif unit in ("°f", "f", "fahrenheit"):
        convert = lambda v: (v - 32.0) * 5.0 / 9.0
    elif unit in ("k", "kelvin"):
        convert = lambda v: v - 273.15
    else:
        raise UpstreamError(f"unexpected temperature unit from weather provider: {unit!r}")
    out = []
    for v in values:
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v
        out.append(round(convert(float(v)), 2) if ok else None)
    return out


def _download(cells: list[tuple[float, float]], first_year: int, last_year: int) -> list[dict]:
    today = date.today()
    start = date(first_year, 1, 1)
    end = min(date(last_year, 12, 31), today - timedelta(days=ARCHIVE_LAG_DAYS))

    locations: list[dict] = [{} for _ in cells]
    if start <= end:
        payload = get_json(
            ARCHIVE_URL,
            {
                "latitude": ",".join(f"{lat:.1f}" for lat, _ in cells),
                "longitude": ",".join(f"{lon:.1f}" for _, lon in cells),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_max",
                "temperature_unit": "celsius",
                # ERA5 only: mixing in the newer high resolution models would add
                # an artificial step to a multi-decade record.
                "models": "era5",
                "timezone": "auto",
            },
        )
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(cells):
            raise UpstreamError("weather provider returned an unexpected number of locations")

    now = time.time()
    docs = []
    for (lat, lon), loc in zip(cells, locations):
        daily = loc.get("daily") or {}
        times = daily.get("time") or []
        raw = daily.get("temperature_2m_max") or []
        if len(times) != len(raw):
            raise UpstreamError("weather provider returned misaligned data")
        unit = (loc.get("daily_units") or {}).get("temperature_2m_max", "°C")
        by_day = dict(zip(times, _to_celsius(raw, unit)))

        for year in range(first_year, last_year + 1):
            # Index by date rather than trusting position, so a response with
            # skipped days still lines up with the calendar.
            day, values = date(year, 1, 1), []
            while day.year == year:
                values.append(by_day.get(day.isoformat()))
                day += timedelta(days=1)
            docs.append(
                {
                    "_id": _doc_id(lat, lon, year),
                    "cell": cell_key(lat, lon),
                    "lat": lat,
                    "lon": lon,
                    "grid_lat": loc.get("latitude"),
                    "grid_lon": loc.get("longitude"),
                    "elevation": loc.get("elevation"),
                    "year": year,
                    "tmax": values,
                    "unit": "C",
                    "source": "open-meteo/era5",
                    "fetched_at": now,
                    "final": date(year, 12, 31) <= today - timedelta(days=FINAL_AFTER_DAYS),
                }
            )
    return docs


def load_daily_tmax(
    cells: list[tuple[float, float]], first_year: int, last_year: int, store: Store
) -> tuple[list[CellSeries], dict]:
    years = range(first_year, last_year + 1)
    wanted = [_doc_id(lat, lon, y) for lat, lon in cells for y in years]
    have = {d["_id"]: d for d in store.get_many(DAILY, wanted) if _is_fresh(d)}
    cached_count = len(have)

    # Group cells that are missing the same span so they share one request.
    spans: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lat, lon in cells:
        missing = [y for y in years if _doc_id(lat, lon, y) not in have]
        if missing:
            spans.setdefault((min(missing), max(missing)), []).append((lat, lon))

    for (y0, y1), group in spans.items():
        for i in range(0, len(group), CELLS_PER_REQUEST):
            chunk = group[i : i + CELLS_PER_REQUEST]
            log.info("Downloading %s-%s for %s cell(s)", y0, y1, len(chunk))
            docs = _download(chunk, y0, y1)
            store.put_many(DAILY, docs)
            have.update({d["_id"]: d for d in docs})

    dates = np.arange(f"{first_year}-01-01", f"{last_year + 1}-01-01", dtype="datetime64[D]")
    series = []
    for lat, lon in cells:
        values: list = []
        meta = {}
        for y in years:
            doc = have[_doc_id(lat, lon, y)]
            values.extend(doc["tmax"])
            meta = doc
        series.append(
            CellSeries(
                lat=lat,
                lon=lon,
                grid_lat=meta.get("grid_lat"),
                grid_lon=meta.get("grid_lon"),
                elevation=meta.get("elevation"),
                dates=dates,
                tmax=np.array([np.nan if v is None else v for v in values], dtype=float),
            )
        )
    stats = {"cell_years": len(wanted), "from_cache": cached_count}
    return series, stats
