"""Place search.

Cities come from the Open-Meteo geocoder. States and provinces need an extent,
which that API does not return, so those come from OpenStreetMap Nominatim.
Results are cached for a month; place names and outlines rarely change.
"""

import time

from .config import MAX_BOX_SPAN_DEG
from .storage import GEOCODE, Store
from .upstream import UpstreamError, get_json

CITY_URL = "https://geocoding-api.open-meteo.com/v1/search"
STATE_URL = "https://nominatim.openstreetmap.org/search"
CACHE_SECONDS = 30 * 24 * 3600


def _search_cities(query: str) -> list[dict]:
    payload = get_json(CITY_URL, {"name": query, "count": 8, "language": "en", "format": "json"})
    results = []
    for item in payload.get("results") or []:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        parts = [item.get("name"), item.get("admin1"), item.get("country")]
        results.append(
            {
                "kind": "city",
                "label": ", ".join(dict.fromkeys(p for p in parts if p)),
                "lat": lat,
                "lon": lon,
            }
        )
    return results


def _search_states(query: str) -> list[dict]:
    # Nominatim's usage policy allows at most one request per second.
    payload = get_json(
        STATE_URL,
        {"q": query, "format": "jsonv2", "featureType": "state", "limit": 6, "accept-language": "en"},
        min_interval=1.1,
    )
    if not isinstance(payload, list):
        raise UpstreamError("place search returned an unexpected response")
    results = []
    for item in payload:
        try:
            south, north, west, east = (float(v) for v in item["boundingbox"])
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        results.append(
            {
                "kind": "state",
                "label": item.get("display_name") or item.get("name") or query,
                "lat": lat,
                "lon": lon,
                "bbox": {"south": south, "north": north, "west": west, "east": east},
                "too_large": east <= west
                or north - south > MAX_BOX_SPAN_DEG
                or east - west > MAX_BOX_SPAN_DEG,
            }
        )
    return results


def search_places(query: str, kind: str, store: Store) -> list[dict]:
    key = f"{kind}:{' '.join(query.lower().split())}"
    cached = store.get(GEOCODE, key)
    if cached:
        return cached["results"]

    results = _search_states(query) if kind == "state" else _search_cities(query)
    now = time.time()
    store.put_many(
        GEOCODE,
        [{"_id": key, "results": results, "created_at": now, "expires_at": now + CACHE_SECONDS}],
    )
    return results
