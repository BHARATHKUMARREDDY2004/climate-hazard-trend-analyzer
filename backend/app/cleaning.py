"""Quality control for a daily temperature series.

Order matters: bad values are removed first, and only then are short gaps
filled, so an interpolated value is never built from a value we rejected.
"""

import numpy as np

# World records are roughly -89 C and +57 C; anything outside is a sensor or
# encoding error (e.g. a -9999 fill value, or Fahrenheit labelled as Celsius).
PHYSICAL_MIN_C = -90.0
PHYSICAL_MAX_C = 60.0

# A single day that sits this far from BOTH neighbours, in the same direction.
SPIKE_C = 15.0

# Longer gaps are left empty. Filling them could invent or bridge a heatwave.
MAX_FILL_DAYS = 2


def clean_series(tmax: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Returns the cleaned series and one boolean flag array per check."""
    values = np.array(tmax, dtype=float)
    values[~np.isfinite(values)] = np.nan
    missing = np.isnan(values)

    out_of_range = np.zeros(values.shape, dtype=bool)
    out_of_range[~missing] = (values[~missing] < PHYSICAL_MIN_C) | (
        values[~missing] > PHYSICAL_MAX_C
    )
    values[out_of_range] = np.nan

    spike = np.zeros(values.shape, dtype=bool)
    if values.size >= 3:
        with np.errstate(invalid="ignore"):
            before = values[1:-1] - values[:-2]
            after = values[1:-1] - values[2:]
            spike[1:-1] = (
                (np.abs(before) > SPIKE_C)
                & (np.abs(after) > SPIKE_C)
                & (np.sign(before) == np.sign(after))
            )
    values[spike] = np.nan

    interpolated = _fill_short_gaps(values)

    flags = {
        "missing": missing,
        "out_of_range": out_of_range,
        "spike": spike,
        "interpolated": interpolated,
        "unfilled": np.isnan(values),
    }
    return values, flags


def _fill_short_gaps(values: np.ndarray) -> np.ndarray:
    """Linear interpolation across gaps of up to MAX_FILL_DAYS, in place."""
    filled = np.zeros(values.shape, dtype=bool)
    gap = np.isnan(values)
    if not gap.any() or gap.all():
        return filled

    edges = np.diff(np.concatenate(([0], gap.astype(np.int8), [0])))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    for start, end in zip(starts, ends):  # end is exclusive
        if start == 0 or end == values.size or end - start > MAX_FILL_DAYS:
            continue
        left, right = values[start - 1], values[end]
        steps = np.arange(1, end - start + 1) / (end - start + 1)
        values[start:end] = left + (right - left) * steps
        filled[start:end] = True
    return filled
