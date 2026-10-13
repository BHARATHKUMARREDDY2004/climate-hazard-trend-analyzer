import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .ratelimit import SlidingWindowLimiter
from .routes import router
from .storage import init_store
from .upstream import UpstreamError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
MAX_BODY_BYTES = 4096

general_limiter = SlidingWindowLimiter(settings.rate_limit_general)
# Running an analysis or rendering a PDF costs real CPU and upstream quota.
heavy_limiter = SlidingWindowLimiter(settings.rate_limit_heavy)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_store()
    yield


app = FastAPI(title="Climate Hazard Trend Analyzer", version="1.0.0", lifespan=lifespan)


def _client_ip(request: Request) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_heavy(request: Request) -> bool:
    path = request.url.path
    return (request.method == "POST" and path == "/api/analyses") or path.endswith(
        ("/export.pdf", "/plot.png")
    )


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)

        ip = _client_ip(request)
        limiter = heavy_limiter if _is_heavy(request) else general_limiter
        allowed, remaining, retry_after = limiter.hit(ip)
        if not allowed:
            return JSONResponse(
                {"detail": f"Too many requests. Try again in {retry_after} seconds."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # The Swagger page at /docs loads its assets from a CDN, so it is left out.
    if request.url.path not in ("/docs", "/redoc"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
    return response


app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After"],
)


@app.exception_handler(UpstreamError)
async def upstream_error(_request: Request, exc: UpstreamError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Return short, readable messages without echoing the submitted values back.
    problems = []
    for error in exc.errors():
        field = ".".join(str(p) for p in error["loc"] if p not in ("body", "query", "path"))
        message = error["msg"].removeprefix("Value error, ")
        problems.append(f"{field}: {message}" if field else message)
    return JSONResponse({"detail": "; ".join(problems) or "Invalid request."}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)


app.include_router(router)

# In production the built frontend is served by the same process.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
