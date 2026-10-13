import numpy as np

from app.cleaning import clean_series


def test_clean_data_is_left_alone():
    values = np.array([30.0, 31.5, 29.8, 33.0, 32.1])
    cleaned, flags = clean_series(values)
    assert np.array_equal(cleaned, values)
    assert not any(f.any() for f in flags.values())


def test_fill_values_and_impossible_readings_are_rejected():
    values = np.array([30.0, -9999.0, 31.0, 31.0, 31.0, 75.0, 31.0])
    cleaned, flags = clean_series(values)
    assert flags["out_of_range"].tolist() == [False, True, False, False, False, True, False]
    # both were single-day gaps afterwards, so they get filled from the neighbours
    assert cleaned[1] == 30.5 and cleaned[5] == 31.0
    assert flags["interpolated"].sum() == 2


def test_isolated_spike_is_removed_but_a_real_jump_is_kept():
    spike = np.array([30.0, 30.0, 48.0, 30.0, 30.0])
    cleaned, flags = clean_series(spike)
    assert flags["spike"].tolist() == [False, False, True, False, False]
    assert cleaned[2] == 30.0

    # A front arriving: temperature drops and stays down. Not an error.
    front = np.array([38.0, 38.0, 21.0, 20.0, 21.0])
    _, flags = clean_series(front)
    assert not flags["spike"].any()


def test_short_gaps_are_interpolated_long_gaps_are_not():
    values = np.array([30.0, np.nan, np.nan, 33.0, 34.0, np.nan, np.nan, np.nan, 30.0])
    cleaned, flags = clean_series(values)
    assert np.allclose(cleaned[1:3], [31.0, 32.0])
    assert np.isnan(cleaned[5:8]).all()
    assert flags["interpolated"].sum() == 2
    assert flags["unfilled"].sum() == 3


def test_gaps_at_the_edges_are_not_extrapolated():
    values = np.array([np.nan, 30.0, 31.0, np.nan])
    cleaned, _ = clean_series(values)
    assert np.isnan(cleaned[0]) and np.isnan(cleaned[-1])


def test_all_missing_does_not_crash():
    cleaned, flags = clean_series(np.full(10, np.nan))
    assert np.isnan(cleaned).all()
    assert flags["missing"].sum() == 10
