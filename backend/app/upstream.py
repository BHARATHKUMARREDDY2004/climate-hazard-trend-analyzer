"""Single place where the service talks to third-party APIs.

Everything goes through `get_json`, which pins the allowed hosts, spaces out
calls per host, and retries transient failures with backoff.
"""

import logging
import threading
import time
from urllib.parse import urlparse

import httpx

from .config import settings

log = logging.getLogger(__name__)

ALLOWED_HOSTS = {
    "archive-api.open-meteo.com",
    "geocoding-api.open-meteo.com",
    "nominatim.openstreetmap.org",
}

_user_agent = "climate-hazard-trend-analyzer/1.0"
if settings.contact_email:
    _user_agent += f" ({settings.contact_email})"

_client = httpx.Client(
    timeout=httpx.Timeout(45.0, connect=10.0),
    headers={"User-Agent": _user_agent, "Accept": "application/json"},
    follow_redirects=False,
)

_throttle_lock = threading.Lock()
_next_slot: dict[str, float] = {}


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _wait_for_slot(host: str, min_interval: float) -> None:
    with _throttle_lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + min_interval
    if slot > now:
        time.sleep(slot - now)


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        try:
            return min(float(response.headers.get("Retry-After", "")), 10.0)
        except ValueError:
            pass
    return min(0.6 * 2**attempt, 8.0)


def get_json(url: str, params: dict, *, min_interval: float = 0.2, retries: int = 3):
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not allowed: {host}")

    for attempt in range(retries + 1):
        _wait_for_slot(host, min_interval)
        response = None
        try:
            response = _client.get(url, params=params)
        except httpx.HTTPError as exc:
            log.warning("%s request failed: %s", host, exc.__class__.__name__)
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    raise UpstreamError(f"{host} returned an unreadable response")
            if response.status_code != 429 and response.status_code < 500:
                log.warning("%s -> %s %s", host, response.status_code, response.text[:200])
                raise UpstreamError(f"{host} rejected the request")
            log.warning("%s -> %s, attempt %s", host, response.status_code, attempt + 1)
        if attempt < retries:
            time.sleep(_retry_delay(response, attempt))

    raise UpstreamError(
        f"{host} is unavailable or rate limiting us, please try again shortly", 503
    )
