import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from . import exports
from .analysis import daily_detail, run_analysis
from .config import MAX_BOX_SPAN_DEG, MIN_PERIOD_YEARS, MIN_YEAR
from .geocode import search_places
from .heatwave import InsufficientData
from .insights import METRICS
from .schemas import AnalysisRequest
from .storage import ANALYSES, get_store

router = APIRouter(prefix="/api")

AnalysisId = Path(pattern=r"^[a-f0-9]{16}$")
# Letters in any script, digits, spaces and the punctuation found in place names.
_PLACE_QUERY = re.compile(r"^[\w\s.,'’()\-]+$", re.UNICODE)


def _load(analysis_id: str) -> dict:
    doc = get_store().get(ANALYSES, analysis_id)
    if not doc:
        raise HTTPException(404, "Analysis not found or expired. Run it again.")
    return doc


def _public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


def _filename(doc: dict, suffix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", doc["region"]["label"].lower()).strip("-")[:40] or "region"
    p = doc["params"]
    return f"heatwaves-{slug}-{p['start_year']}-{p['end_year']}{suffix}"


def _download(content, media_type: str, filename: str) -> Response:
    return Response(
        content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/health")
def health():
    store = get_store()
    return {"status": "ok" if store.ping() else "degraded", "storage": store.name}


@router.get("/meta")
def meta():
    return {
        "min_year": MIN_YEAR,
        "max_year": date.today().year,
        "min_period_years": MIN_PERIOD_YEARS,
        "max_box_span_deg": MAX_BOX_SPAN_DEG,
        "hazards": [{"id": "heatwave", "label": "Heatwave", "available": True}],
        "metrics": METRICS,
    }


@router.get("/regions/search")
def region_search(
    q: str = Query(min_length=2, max_length=80),
    kind: Literal["city", "state"] = "city",
):
    q = q.strip()
    if len(q) < 2 or not _PLACE_QUERY.match(q):
        raise HTTPException(422, "Search text contains unsupported characters.")
    return {"results": search_places(q, kind, get_store())}


@router.post("/analyses")
def create_analysis(request: AnalysisRequest):
    try:
        return _public(run_analysis(request, get_store()))
    except InsufficientData as exc:
        raise HTTPException(422, str(exc))


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str = AnalysisId):
    return _public(_load(analysis_id))


@router.get("/analyses/{analysis_id}/daily")
def get_daily(
    analysis_id: str = AnalysisId,
    year: int = Query(ge=MIN_YEAR, le=2100),
    cell: int = Query(default=0, ge=0, le=20),
):
    doc = _load(analysis_id)
    params = doc["params"]
    if not params["start_year"] <= year <= params["end_year"]:
        raise HTTPException(422, "Year is outside the analysed period.")
    if cell >= len(doc["region"]["cells"]):
        raise HTTPException(422, "Unknown sample point.")
    return daily_detail(doc, year, cell, get_store())


@router.get("/analyses/{analysis_id}/export.csv")
def export_csv(analysis_id: str = AnalysisId, table: Literal["annual", "events"] = "annual"):
    doc = _load(analysis_id)
    text = exports.annual_csv(doc) if table == "annual" else exports.events_csv(doc)
    # BOM so Excel opens the file as UTF-8.
    return _download("﻿" + text, "text/csv; charset=utf-8", _filename(doc, f"-{table}.csv"))


@router.get("/analyses/{analysis_id}/export.pdf")
def export_pdf(analysis_id: str = AnalysisId):
    doc = _load(analysis_id)
    return _download(exports.report_pdf(doc), "application/pdf", _filename(doc, ".pdf"))


@router.get("/analyses/{analysis_id}/plot.png")
def plot_png(
    analysis_id: str = AnalysisId,
    metric: Literal["days", "events", "longest", "mean_excess", "peak_tmax", "mean_tmax"] = "days",
):
    return Response(exports.trend_plot_png(_load(analysis_id), metric), media_type="image/png")
