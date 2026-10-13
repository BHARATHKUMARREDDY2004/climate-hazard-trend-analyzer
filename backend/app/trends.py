"""Trend statistics for a yearly series.

Two tests are reported side by side:
  - ordinary least squares, because it is familiar and gives a line to draw;
  - Mann-Kendall with Sen's slope, which makes no assumption about the
    distribution. Heatwave counts are skewed and full of zeros, so the
    verdict ("increasing" / "no significant trend") is taken from this one.
"""

import math

import numpy as np
from scipy import stats

ALPHA = 0.05
MIN_POINTS = 10


def mann_kendall(values: np.ndarray) -> dict:
    y = np.asarray(values, dtype=float)
    n = y.size
    s = float(np.triu(np.sign(y[None, :] - y[:, None]), k=1).sum())

    # Variance with the correction for tied values (many years share a count of 0).
    _, ties = np.unique(y, return_counts=True)
    variance = (n * (n - 1) * (2 * n + 5) - np.sum(ties * (ties - 1) * (2 * ties + 5))) / 18.0

    if variance <= 0:
        z = 0.0
    elif s > 0:
        z = (s - 1) / math.sqrt(variance)
    elif s < 0:
        z = (s + 1) / math.sqrt(variance)
    else:
        z = 0.0
    return {
        "s": s,
        "z": z,
        "p_value": float(2 * stats.norm.sf(abs(z))),
        "tau": s / (0.5 * n * (n - 1)),
    }


def rolling_mean(values: list, window: int = 5, min_points: int = 3) -> list:
    """Centred moving average that tolerates missing years."""
    arr = np.array([np.nan if v is None else v for v in values], dtype=float)
    half = window // 2
    out = []
    for i in range(arr.size):
        chunk = arr[max(0, i - half) : i + half + 1]
        chunk = chunk[~np.isnan(chunk)]
        out.append(round(float(chunk.mean()), 3) if chunk.size >= min_points else None)
    return out


def analyze_trend(years: list[int], values: list) -> dict:
    pairs = [(y, v) for y, v in zip(years, values) if v is not None and not math.isnan(v)]
    n = len(pairs)
    if n < MIN_POINTS:
        return {"status": "insufficient", "n": n}

    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)

    if np.all(y == y[0]):
        # A flat series has no trend, and linregress would warn about it.
        ols = {"slope": 0.0, "intercept": float(y[0]), "r_squared": 0.0, "p_value": 1.0,
               "slope_ci": [0.0, 0.0]}
        sen = (0.0, float(y[0]), 0.0, 0.0)
    else:
        fit = stats.linregress(x, y)
        margin = stats.t.ppf(1 - ALPHA / 2, n - 2) * fit.stderr
        ols = {
            "slope": float(fit.slope),
            "intercept": float(fit.intercept),
            "r_squared": float(fit.rvalue**2),
            "p_value": float(fit.pvalue),
            "slope_ci": [float(fit.slope - margin), float(fit.slope + margin)],
        }
        sen = stats.theilslopes(y, x, 1 - ALPHA)

    mk = mann_kendall(y)
    if mk["p_value"] < ALPHA and mk["s"] != 0:
        direction = "increasing" if mk["s"] > 0 else "decreasing"
    else:
        direction = "no_significant_trend"

    # Compare the two ends of the record with plain averages. Ten year blocks
    # when the record allows it, otherwise the first and second half.
    block = 10 if n >= 20 else n // 2
    early, late = pairs[:block], pairs[-block:]
    early_mean = float(np.mean([v for _, v in early]))
    late_mean = float(np.mean([v for _, v in late]))

    return {
        "status": "ok",
        "n": n,
        "direction": direction,
        "ols": ols,
        "mann_kendall": mk,
        "sen_slope": float(sen[0]),
        "sen_slope_ci": [float(sen[2]), float(sen[3])],
        "early": {"from": early[0][0], "to": early[-1][0], "mean": early_mean},
        "late": {"from": late[0][0], "to": late[-1][0], "mean": late_mean},
        "change": late_mean - early_mean,
    }
