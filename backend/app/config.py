import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# ERA5 starts in 1940; the archive trails real time by about five days.
MIN_YEAR = 1940
ARCHIVE_LAG_DAYS = 6

# Bump when detection or aggregation logic changes so stored analyses are not reused.
ALGORITHM_VERSION = "1"

MAX_BOX_SPAN_DEG = 20.0
MIN_PERIOD_YEARS = 5


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    storage_backend: str = os.getenv("STORAGE_BACKEND", "auto").lower()
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "climate_hazards")
    tinydb_dir: Path = BACKEND_DIR / os.getenv("TINYDB_DIR", "data")
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ]
    )
    rate_limit_general: int = _int("RATE_LIMIT_GENERAL", 120)
    rate_limit_heavy: int = _int("RATE_LIMIT_HEAVY", 15)
    trust_proxy: bool = os.getenv("TRUST_PROXY", "0") == "1"
    contact_email: str = os.getenv("CONTACT_EMAIL", "")


settings = Settings()
