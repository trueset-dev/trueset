"""Ambiguity-aware validation: corroboration, annotate-and-flow, adjudication,
context-aware ranges, and the robust stats under them."""

import numpy as np
import pandas as pd
import pytest

from trueset import (
    Adjudications,
    Suite,
    annotate,
    corroboration_flags,
    robust_bounds,
    robust_z,
    segment_bounds,
)
from trueset.ambiguity import FLAGS_COLUMN, QUALITY_COLUMN, Corroboration
from trueset.result import Status

# -- robust stats ----------------------------------------------------------- #

def test_robust_z_ignores_outlier_inflation():
    # one huge outlier shouldn't drag the scale enough to hide itself
    s = pd.Series([10, 11, 9, 10, 12, 8, 1000])
    z = robust_z(s)
    assert abs(z.iloc[-1]) > 3.5          # the 1000 is clearly an outlier
    assert (z.iloc[:-1].abs() < 3.5).all()  # the normal values are not


def test_robust_bounds_constant_series():
    lo, hi = robust_bounds(pd.Series([5, 5, 5, 5]))
    assert lo == 5 and hi == 5


# -- 1. corroboration ------------------------------------------------------- #

def _spike_df(volume_at_spike):
    price = [100.0] * 19 + [1000.0]        # a big price spike on the last row
    volume = [50.0] * 19 + [volume_at_spike]
    return pd.DataFrame({"price": price, "volume": volume})


def test_corroborated_spike_is_not_flagged():
    # price spikes AND volume spikes together -> a real move, corroborated
    res = corroboration_flags(_spike_df(500.0), "price", ["volume"])
    assert res.n_flagged == 0


def test_uncorroborated_spike_is_flagged():
    # price spikes but volume is flat -> nothing backs it up -> surface it
    res = corroboration_flags(_spike_df(50.0), "price", ["volume"])
    assert res.n_flagged == 1
    assert bool(res.uncorroborated.iloc[-1]) is True


def test_directional_spike_wrong_way_is_not_support():
    # price spikes UP, volume spikes DOWN -> opposite direction -> no support
    df = _spike_df(500.0)
    df.loc[19, "volume"] = 0.001  # volume collapses instead of rising
    res = corroboration_flags(df, "price", ["volume"], directional=True)
    assert res.n_flagged == 1


def test_corroboration_check_runs_in_a_suite():
    suite = Suite.from_dict(
        {"suite": "c", "checks": [
            {"type": "corroboration", "column": "price",
             "corroborate_with": ["volume"], "severity": "warn"},
        ]}
    )
    from trueset import PandasBackend
    result = suite.run(PandasBackend(_spike_df(50.0)))
    assert result.results[0].status is Status.FAIL
    assert result.passed is True  # warn severity: surfaced, not blocking


def test_corroboration_errors_on_non_pandas_backend():
    class FakeSQL:  # no .df attribute
        name = "sqlish"

    r = Corroboration("price", ["volume"]).evaluate(FakeSQL())
    assert r.status is Status.ERROR
    assert "pandas" in r.message


# -- 2. annotate-and-flow --------------------------------------------------- #

def _annot_suite():
    return Suite.from_dict(
        {"suite": "a", "checks": [
            {"type": "not_null", "column": "price"},
            {"type": "in_range", "column": "price", "min": 0, "severity": "warn"},
        ]}
    )


def test_annotate_keeps_every_row_and_scores_them():
    df = pd.DataFrame({"id": [1, 2, 3], "price": [10.0, -5.0, None]})
    out = annotate(df, _annot_suite())
    assert len(out) == len(df)                       # nothing blocked -- all flow
    assert set([QUALITY_COLUMN, FLAGS_COLUMN]).issubset(out.columns)
    assert out.loc[0, QUALITY_COLUMN] == 1.0          # clean row
    assert out.loc[2, QUALITY_COLUMN] < 1.0           # null price (error weight)
    assert "not_null(price)" in out.loc[2, FLAGS_COLUMN]


def test_error_costs_more_than_warn():
    df = pd.DataFrame({"id": [1, 2], "price": [-5.0, None]})
    out = annotate(df, _annot_suite())
    # row 1 fails only the warn range; row 2 fails the error not_null -> lower score
    assert out.loc[1, QUALITY_COLUMN] < out.loc[0, QUALITY_COLUMN]


# -- 5. adjudication feedback loop ------------------------------------------ #

def test_adjudication_suppresses_a_known_valid_flag(tmp_path):
    df = pd.DataFrame({"id": ["a", "b"], "price": [10.0, -5.0]})
    suite = Suite.from_dict(
        {"suite": "a", "checks": [{"type": "in_range", "column": "price", "min": 0}]}
    )
    # before: row b is flagged
    before = annotate(df, suite, key="id")
    assert before.loc[1, FLAGS_COLUMN] == "in_range(price)"

    adj = Adjudications()
    adj.mark_valid("in_range(price)", "b", note="legit negative adjustment")
    after = annotate(df, suite, key="id", adjudications=adj)
    assert after.loc[1, FLAGS_COLUMN] == ""          # suppressed
    assert after.loc[1, QUALITY_COLUMN] == 1.0

    # round-trips to disk (auditable, git-committable)
    p = tmp_path / "adj.json"
    adj.save(p)
    assert Adjudications.load(p).is_valid("in_range(price)", "b")


# -- 3. context-aware ranges ------------------------------------------------ #

def test_segment_bounds_are_per_segment():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({
        "region": ["north"] * 50 + ["south"] * 50,
        "demand": list(rng.normal(10, 1, 50)) + list(rng.normal(1000, 5, 50)),
    })
    bounds = segment_bounds(df, "demand", "region")
    assert set(bounds) == {"north", "south"}
    assert bounds["north"]["max"] < 100 < bounds["south"]["min"]  # very different bands


def test_segment_bounds_missing_column_raises():
    with pytest.raises(KeyError):
        segment_bounds(pd.DataFrame({"a": [1]}), "nope", "a")
