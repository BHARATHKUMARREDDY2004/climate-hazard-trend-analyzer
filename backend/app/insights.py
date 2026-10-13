"""Turns the numbers into sentences, and is careful about what it claims.

Rules followed here:
  - a change is only called a trend when Mann-Kendall is significant at 5%;
  - percentages are not quoted when the starting value is close to zero,
    because "+800%" from 0.1 days a year says nothing useful;
  - every limitation that affects how far the result can be trusted is
    stated next to it rather than left for the README.
"""

METRICS = {
    "days": {"label": "Heatwave days", "unit": "days per year", "short": "days", "decimals": 1},
    "events": {"label": "Heatwave events", "unit": "events per year", "short": "events", "decimals": 1},
    "longest": {"label": "Longest heatwave", "unit": "days", "short": "days", "decimals": 1},
    "mean_excess": {"label": "Mean intensity above threshold", "unit": "°C", "short": "°C", "decimals": 2},
    "peak_tmax": {"label": "Hottest heatwave day", "unit": "°C", "short": "°C", "decimals": 1},
    "mean_tmax": {"label": "Annual mean of daily maximum temperature", "unit": "°C", "short": "°C", "decimals": 2},
}

# Below this many days (or events) per year a percentage change is not meaningful.
MIN_BASE_FOR_PERCENT = 0.5


def _p(p_value: float) -> str:
    return "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"


def _span(block: dict) -> str:
    return f"{block['from']}–{block['to']}"


def _signed(value: float, decimals: int = 1) -> str:
    return f"{value:+.{decimals}f}"


def _count_sentence(noun: str, region: str, trend: dict) -> str:
    early, late = trend["early"], trend["late"]
    mk_p = _p(trend["mann_kendall"]["p_value"])
    per_decade = _signed(trend["sen_slope"] * 10, 1)
    averages = (
        f"an average of {early['mean']:.1f} per year in {_span(early)} "
        f"to {late['mean']:.1f} per year in {_span(late)}"
    )

    if trend["direction"] == "no_significant_trend":
        return (
            f"{noun} in {region} averaged {early['mean']:.1f} per year in {_span(early)} and "
            f"{late['mean']:.1f} per year in {_span(late)}. Year-to-year variability is large "
            f"relative to that difference and the trend is not statistically significant "
            f"(Mann-Kendall {mk_p}), so this should not be read as a sustained change."
        )

    verb = "increased" if trend["direction"] == "increasing" else "decreased"
    if early["mean"] >= MIN_BASE_FOR_PERCENT:
        percent = abs(trend["change"]) / early["mean"] * 100
        change = f"have {verb} by {percent:.0f}% in {region}, from {averages}"
    else:
        change = f"have {verb} in {region}, from {averages}"
    return (
        f"{noun} {change}. The trend is statistically significant "
        f"(Mann-Kendall {mk_p}; Sen's slope {per_decade} per decade)."
    )


def build_insights(doc: dict) -> list[dict]:
    region = doc["region"]["label"]
    params = doc["params"]
    trends = doc["trends"]
    annual = doc["annual"]
    n_cells = len(doc["region"]["cells"])
    out: list[dict] = []

    def add(kind: str, text: str) -> None:
        out.append({"kind": kind, "text": text})

    days = trends["days"]
    if days["status"] != "ok":
        add(
            "headline",
            f"Only {days['n']} complete years are available for {region}, which is too few to "
            f"assess a trend. The yearly figures are still shown below.",
        )
    else:
        add("headline", _count_sentence("Heatwave days", region, days))

    events = trends["events"]
    if events["status"] == "ok":
        add("finding", _count_sentence("Heatwave events", region, events))

    longest = trends["longest"]
    if longest["status"] == "ok" and longest["direction"] != "no_significant_trend":
        word = "longer" if longest["direction"] == "increasing" else "shorter"
        add(
            "finding",
            f"Heatwaves are getting {word}: the longest event of the year changed by "
            f"{_signed(longest['sen_slope'] * 10)} days per decade "
            f"(Mann-Kendall {_p(longest['mann_kendall']['p_value'])}).",
        )

    intensity = trends["mean_excess"]
    if intensity["status"] == "ok":
        if intensity["direction"] == "no_significant_trend":
            frequency_changed = days["status"] == "ok" and days["direction"] != "no_significant_trend"
            add(
                "finding",
                "When heatwaves occur, how far they exceed the threshold shows no significant "
                f"change (Mann-Kendall {_p(intensity['mann_kendall']['p_value'])})."
                + (
                    " The change is in how often they occur, not in how extreme each one is."
                    if frequency_changed
                    else ""
                ),
            )
        else:
            word = "more" if intensity["direction"] == "increasing" else "less"
            add(
                "finding",
                f"Heatwaves are also becoming {word} intense: mean exceedance above the threshold "
                f"changed by {_signed(intensity['sen_slope'] * 10, 2)} °C per decade "
                f"(Mann-Kendall {_p(intensity['mann_kendall']['p_value'])}).",
            )
    elif days["status"] == "ok":
        add(
            "finding",
            f"Intensity trends are not reported: only {intensity['n']} years had a heatwave, "
            "too few for a reliable estimate.",
        )

    warming = trends["mean_tmax"]
    if warming["status"] == "ok":
        slope = warming["ols"]["slope"] * 10
        low, high = (v * 10 for v in warming["ols"]["slope_ci"])
        significant = warming["direction"] != "no_significant_trend"
        add(
            "finding",
            f"Background warming: the annual mean of daily maximum temperature changed by "
            f"{_signed(slope, 2)} °C per decade (95% CI {_signed(low, 2)} to {_signed(high, 2)}), "
            + (
                "a significant trend that shifts the whole distribution towards the threshold."
                if significant
                else "which is not statistically significant over this period."
            ),
        )

    complete = [row for row in annual if row["complete"]]
    if complete:
        worst = max(complete, key=lambda row: row["days"])
        if worst["days"] > 0:
            add(
                "finding",
                f"The most affected year was {worst['year']} with "
                + (
                    f"{worst['days']:g} heatwave days across {worst['events']:g} events."
                    if n_cells == 1
                    else f"{worst['days']:.1f} heatwave days on average across the sample points."
                ),
            )

    # Limitations. These are part of the result, not small print.
    n_years = params["end_year"] - params["start_year"] + 1
    if n_years < 20:
        add(
            "caution",
            f"The selected period covers {n_years} years. Climate trends are normally assessed "
            "over 30 years or more; over shorter periods natural variability such as El Niño "
            "can look like a trend or hide one.",
        )
    if params["baseline"] == "period":
        add(
            "caution",
            f"The threshold is the {params['percentile']:g}th percentile of the selected period "
            "itself, so the share of hot days over the whole period is fixed by construction. "
            "What the analysis measures is how those days are distributed across the years. "
            "Choose a fixed baseline (for example 1961–1990) to measure change against an earlier climate.",
        )
    if days["status"] == "ok" and days["early"]["mean"] < MIN_BASE_FOR_PERCENT and days["direction"] != "no_significant_trend":
        add(
            "caution",
            "A percentage change is not quoted because the starting level is close to zero, "
            "where percentages become very large and unstable.",
        )
    if n_cells > 1:
        add(
            "caution",
            f"The region is represented by {n_cells} sample points on a regular grid inside its "
            "bounding box, each judged against its own local threshold and then averaged. "
            "This approximates the area; it does not follow the exact boundary.",
        )
    incomplete = [row["year"] for row in annual if not row["complete"]]
    if incomplete:
        listed = ", ".join(str(y) for y in incomplete[:6]) + ("…" if len(incomplete) > 6 else "")
        add(
            "caution",
            f"{len(incomplete)} year(s) with under 90% data coverage ({listed}) are shown but "
            "left out of the trend statistics.",
        )
    add(
        "caution",
        "Temperatures are from the ERA5 reanalysis on a grid of roughly 25–30 km. They represent "
        "an area average, so local effects such as urban heat islands are smoothed out and "
        "values will be lower than a city weather station on the hottest days.",
    )
    return out
