import numpy as np
import pytest

from app.trends import analyze_trend, mann_kendall, rolling_mean


def test_mann_kendall_on_a_strictly_increasing_series():
    result = mann_kendall(np.arange(10))
    assert result["s"] == 45
    assert result["tau"] == 1.0
    # textbook value: var = 125, z = 44 / sqrt(125)
    assert result["z"] == pytest.approx(3.9355, abs=1e-3)
    assert result["p_value"] < 0.001


def test_mann_kendall_tie_correction():
    # Worked by hand: S = 7, tie groups of sizes 2 and 2, variance = 26.33
    result = mann_kendall(np.array([1, 2, 2, 3, 1, 4]))
    assert result["s"] == 7
    assert result["z"] == pytest.approx(6 / np.sqrt(79 / 3), abs=1e-6)


def test_constant_series_has_no_trend():
    trend = analyze_trend(list(range(2000, 2020)), [0.0] * 20)
    assert trend["direction"] == "no_significant_trend"
    assert trend["ols"]["slope"] == 0
    assert trend["mann_kendall"]["p_value"] == 1.0


def test_clear_trend_is_detected_and_slopes_agree():
    years = list(range(1990, 2021))
    rng = np.random.default_rng(7)
    values = [0.3 * (y - 1990) + rng.normal(0, 1) for y in years]
    trend = analyze_trend(years, values)
    assert trend["direction"] == "increasing"
    assert trend["ols"]["slope"] == pytest.approx(0.3, abs=0.05)
    assert trend["sen_slope"] == pytest.approx(0.3, abs=0.05)
    low, high = trend["ols"]["slope_ci"]
    assert low < 0.3 < high
    assert (trend["early"]["from"], trend["early"]["to"]) == (1990, 1999)
    assert (trend["late"]["from"], trend["late"]["to"]) == (2011, 2020)


def test_noise_is_not_reported_as_a_trend():
    years = list(range(1990, 2021))
    rng = np.random.default_rng(3)
    trend = analyze_trend(years, rng.normal(5, 2, len(years)).tolist())
    assert trend["direction"] == "no_significant_trend"


def test_missing_years_are_skipped_and_short_series_refused():
    years = list(range(2000, 2012))
    values = [1, None, 2, 3, None, 4, 5, 6, 7, 8, 9, 10]
    assert analyze_trend(years, values)["n"] == 10
    assert analyze_trend(years[:8], values[:8]) == {"status": "insufficient", "n": 6}


def test_rolling_mean_is_centred_and_handles_gaps():
    assert rolling_mean([1, 2, 3, 4, 5]) == [2.0, 2.5, 3.0, 3.5, 4.0]
    assert rolling_mean([1, None, None, None, 5])[2] is None
