import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import storage, weather  # noqa: E402


def synthetic_year(lat: float, lon: float, year: int) -> list:
    """Seasonal cycle plus a warming trend of 0.5 C per decade and daily noise."""
    rng = np.random.default_rng(abs(hash((round(lat, 1), round(lon, 1), year))) % (2**32))
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    doy = np.arange(days)
    seasonal = 30 + 10 * np.sin(2 * np.pi * (doy - 110) / 365.25)
    values = seasonal + 0.05 * (year - 1980) + rng.normal(0, 2.5, days)
    return [round(float(v), 1) for v in values]


@pytest.fixture
def store(tmp_path):
    tiny = storage.TinyStore(tmp_path)
    storage.set_store(tiny)
    yield tiny
    tiny.close()
    storage.set_store(None)


@pytest.fixture
def fake_weather(monkeypatch):
    """Replaces the network download and records what was asked for."""
    calls = []

    def download(cells, first_year, last_year):
        calls.append((list(cells), first_year, last_year))
        today = date.today()
        docs = []
        for lat, lon in cells:
            for year in range(first_year, last_year + 1):
                values = synthetic_year(lat, lon, year)
                if year == today.year:
                    cutoff = (today - timedelta(days=6) - date(year, 1, 1)).days + 1
                    values = [v if i < cutoff else None for i, v in enumerate(values)]
                docs.append(
                    {
                        "_id": f"{weather.cell_key(lat, lon)}_{year}",
                        "cell": weather.cell_key(lat, lon),
                        "lat": lat, "lon": lon, "grid_lat": lat, "grid_lon": lon,
                        "elevation": 100.0, "year": year, "tmax": values, "unit": "C",
                        "source": "synthetic", "fetched_at": time.time(),
                        "final": year < today.year,
                    }
                )
        return docs

    monkeypatch.setattr(weather, "_download", download)
    return calls
