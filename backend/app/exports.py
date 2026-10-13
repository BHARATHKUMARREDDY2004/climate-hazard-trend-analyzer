"""CSV, PNG and PDF renderings of a stored analysis."""

import csv
import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .insights import METRICS

NAVY = "#1f3a5f"
BURGUNDY = "#7a1f2b"
INK = "#2b2b2b"
RULE = "#cfc7b4"
PAPER = "#f4efe3"

ANNUAL_COLUMNS = [
    ("year", "Year"),
    ("events", "Heatwave events"),
    ("days", "Heatwave days"),
    ("longest", "Longest event (days)"),
    ("mean_excess", "Mean excess above threshold (C)"),
    ("peak_tmax", "Hottest heatwave day (C)"),
    ("hot_days", "Days above threshold"),
    ("mean_tmax", "Annual mean Tmax (C)"),
    ("max_tmax", "Annual max Tmax (C)"),
    ("coverage", "Data coverage"),
    ("complete", "Used in trend"),
]
EVENT_COLUMNS = [
    ("start", "Start"),
    ("end", "End"),
    ("duration", "Duration (days)"),
    ("peak_tmax", "Peak Tmax (C)"),
    ("mean_tmax", "Mean Tmax (C)"),
    ("mean_excess", "Mean excess (C)"),
    ("severity", "Cumulative excess (C days)"),
]


def _safe_cell(value):
    # Spreadsheet programs run cells that start with these characters as formulas.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def _describe(doc: dict) -> list[tuple[str, str]]:
    params, threshold = doc["params"], doc["threshold"]
    if threshold["method"] == "seasonal":
        rule = f"{params['percentile']:g}th percentile for each calendar day (15 day window)"
    elif threshold["min_value"] == threshold["max_value"]:
        rule = f"{params['percentile']:g}th percentile of daily maximum temperature = {threshold['mean_value']:.1f} °C"
    else:
        rule = (
            f"{params['percentile']:g}th percentile of daily maximum temperature, "
            f"{threshold['min_value']:.1f} to {threshold['max_value']:.1f} °C across sample points"
        )
    base = params["baseline_years"]
    return [
        ("Region", doc["region"]["label"]),
        ("Period", f"{params['start_year']}–{params['end_year']}"),
        ("Heatwave definition", f"At least {params['min_duration']} consecutive days above the threshold"),
        ("Threshold", rule),
        ("Baseline", f"{base[0]}–{base[1]}"),
        ("Sample points", str(len(doc["region"]["cells"]))),
        ("Data source", doc["source"]["name"]),
    ]


def annual_csv(doc: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["region", "start_year", "end_year", "percentile", "min_duration", "threshold_method", "baseline"])
    p = doc["params"]
    writer.writerow(
        [_safe_cell(doc["region"]["label"]), p["start_year"], p["end_year"], p["percentile"],
         p["min_duration"], p["threshold_method"], f"{p['baseline_years'][0]}-{p['baseline_years'][1]}"]
    )
    writer.writerow([])
    writer.writerow([label for _, label in ANNUAL_COLUMNS])
    for row in doc["annual"]:
        writer.writerow([_safe_cell(row.get(key)) for key, _ in ANNUAL_COLUMNS])
    return out.getvalue()


def events_csv(doc: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([label for _, label in EVENT_COLUMNS] + ["Sample point lat", "Sample point lon"])
    cells = doc["region"]["cells"]
    for event in doc["events"]:
        cell = cells[event["cell"]]
        writer.writerow([_safe_cell(event[key]) for key, _ in EVENT_COLUMNS] + [cell["lat"], cell["lon"]])
    return out.getvalue()


def trend_plot_png(doc: dict, metric: str, width: float = 8.0, height: float = 3.6, dpi: int = 150) -> bytes:
    meta = METRICS[metric]
    years = [row["year"] for row in doc["annual"]]
    values = [row[metric] if row["complete"] else None for row in doc["annual"]]
    as_bars = metric in ("days", "events", "longest")

    fig = Figure(figsize=(width, height), dpi=dpi, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    font = {"family": "serif"}

    shown = [(y, v) for y, v in zip(years, values) if v is not None]
    if as_bars:
        ax.bar([y for y, _ in shown], [v for _, v in shown], color=BURGUNDY, width=0.7, label="Yearly value")
    else:
        ax.plot([y for y, _ in shown], [v for _, v in shown], color=BURGUNDY, marker="o",
                markersize=3, linewidth=1, label="Yearly value")

    smooth = [(y, v) for y, v in zip(years, doc["rolling"][metric]) if v is not None]
    if smooth:
        ax.plot([y for y, _ in smooth], [v for _, v in smooth], color=NAVY, linewidth=1.8, label="5-year mean")

    trend = doc["trends"][metric]
    if trend["status"] == "ok":
        ends = [years[0], years[-1]]
        fit = [trend["ols"]["intercept"] + trend["ols"]["slope"] * y for y in ends]
        ax.plot(ends, fit, color=INK, linewidth=1.2, linestyle="--", label="Linear trend")

    ax.set_title(f"{meta['label']} — {doc['region']['label']}", fontdict={**font, "size": 11}, loc="left")
    ax.set_ylabel(meta["unit"], fontdict={**font, "size": 9})
    if as_bars:
        ax.set_ylim(bottom=0)
    ax.grid(axis="y", color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily("serif")
        label.set_fontsize(8)
    fig.legend(frameon=False, prop={"family": "serif", "size": 8}, loc="lower center", ncols=3)
    fig.tight_layout(rect=(0, 0.07, 1, 1))

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()


def _fmt(value, decimals: int = 1) -> str:
    return "–" if value is None else f"{value:.{decimals}f}"


def _slope(per_year: float) -> str:
    text = f"{per_year * 10:+.2f}"
    return "0.00" if float(text) == 0 else text


def _trend_row(doc: dict, metric: str) -> list[str]:
    meta, trend = METRICS[metric], doc["trends"][metric]
    if trend["status"] != "ok":
        return [meta["label"], "–", "–", "–", f"Too few years (n = {trend['n']})"]
    verdict = {"increasing": "Increasing", "decreasing": "Decreasing",
               "no_significant_trend": "No significant trend"}[trend["direction"]]
    p_value = trend["mann_kendall"]["p_value"]
    return [
        meta["label"],
        _slope(trend["ols"]["slope"]),
        _slope(trend["sen_slope"]),
        "< 0.001" if p_value < 0.001 else f"{p_value:.3f}",
        verdict,
    ]


def report_pdf(doc: dict) -> bytes:
    base = dict(fontName="Times-Roman", textColor=colors.HexColor(INK), alignment=TA_LEFT)
    title = ParagraphStyle("title", fontSize=20, leading=24, **{**base, "fontName": "Times-Bold", "textColor": colors.HexColor(NAVY)})
    subtitle = ParagraphStyle("subtitle", fontSize=11, leading=14, spaceAfter=10, **{**base, "fontName": "Times-Italic"})
    heading = ParagraphStyle("heading", fontSize=13, leading=16, spaceBefore=12, spaceAfter=6, keepWithNext=1, **{**base, "fontName": "Times-Bold", "textColor": colors.HexColor(NAVY)})
    body = ParagraphStyle("body", fontSize=10.5, leading=14.5, spaceAfter=6, **base)
    lead = ParagraphStyle("lead", fontSize=12, leading=16.5, spaceAfter=8, **base)
    small = ParagraphStyle("small", fontSize=9, leading=12, spaceAfter=4, **base)

    def table(rows, widths, header=True, size=9):
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("FONT", (0, 0), (-1, -1), "Times-Roman", size),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [
                ("FONT", (0, 0), (-1, 0), "Times-Bold", size),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PAPER)),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(NAVY)),
            ]
        else:
            style.append(("FONT", (0, 0), (0, -1), "Times-Bold", size))
        t.setStyle(TableStyle(style))
        return t

    insights = doc["insights"]
    flow = [
        Paragraph("Heatwave Trend Report", title),
        Paragraph(escape(doc["region"]["label"]), subtitle),
        table([[k, Paragraph(escape(v), small)] for k, v in _describe(doc)], [38 * mm, 132 * mm], header=False),
        Paragraph("Summary", heading),
    ]
    flow += [Paragraph(escape(i["text"]), lead) for i in insights if i["kind"] == "headline"]
    flow += [Paragraph(escape(i["text"]), body) for i in insights if i["kind"] == "finding"]

    flow.append(Paragraph("Trends", heading))
    flow.append(
        table(
            [["Indicator", "Linear / decade", "Sen's / decade", "Mann-Kendall p", "Verdict (5% level)"]]
            + [_trend_row(doc, m) for m in METRICS],
            [56 * mm, 29 * mm, 28 * mm, 24 * mm, 33 * mm],
        )
    )
    for metric in ("days", "events"):
        flow.append(Spacer(1, 8))
        flow.append(Image(io.BytesIO(trend_plot_png(doc, metric)), width=170 * mm, height=76.5 * mm))

    flow.append(Spacer(1, 8))
    flow.append(Image(io.BytesIO(trend_plot_png(doc, "mean_tmax")), width=170 * mm, height=76.5 * mm))
    flow.append(Paragraph("How to read these results", heading))
    flow += [Paragraph(escape(i["text"]), body) for i in insights if i["kind"] == "caution"]

    q = doc["quality"]
    flow.append(Paragraph("Data quality", heading))
    flow.append(
        Paragraph(
            f"{q['total_days']:,} daily values were examined. {q['missing']:,} were missing from the source, "
            f"{q['out_of_range']:,} were rejected as physically implausible and {q['spike']:,} as isolated spikes. "
            f"{q['interpolated']:,} values in gaps of one or two days were filled by linear interpolation; "
            f"{q['unfilled']:,} remain missing and break any heatwave they fall in.",
            body,
        )
    )

    flow.append(Paragraph("Yearly values", heading))
    rows = [["Year", "Events", "Days", "Longest", "Mean excess °C", "Peak °C", "Mean Tmax °C", "In trend"]]
    for r in doc["annual"]:
        rows.append(
            [str(r["year"]), _fmt(r["events"]), _fmt(r["days"]), _fmt(r["longest"]), _fmt(r["mean_excess"], 2),
             _fmt(r["peak_tmax"]), _fmt(r["mean_tmax"], 2), "yes" if r["complete"] else "no"]
        )
    flow.append(table(rows, [18 * mm, 20 * mm, 20 * mm, 20 * mm, 28 * mm, 20 * mm, 26 * mm, 18 * mm], size=8.5))

    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Times-Italic", 8)
        canvas.setFillColor(colors.HexColor("#6b6558"))
        canvas.drawString(20 * mm, 12 * mm, f"Climate Hazard Trend Analyzer · generated {generated} · analysis {doc['id']}")
        canvas.drawRightString(190 * mm, 12 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
        title=f"Heatwave Trend Report - {doc['region']['label']}", author="Climate Hazard Trend Analyzer",
    ).build(flow, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
