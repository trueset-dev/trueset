"""Tests for the `metric` check (aggregate validation)."""

from pathlib import Path

import pandas as pd
import pytest

from trueset import PandasBackend, Suite, build_check
from trueset.checks import Metric
from trueset.result import Status
from trueset.suite import SuiteLoadError

EX = Path(__file__).resolve().parents[1] / "examples"


def _be():
    return PandasBackend(pd.DataFrame({"amount": [10.0, 20.0, 30.0, None]}))  # sum 60, avg 20


def test_equals_within_tolerance_passes():
    r = Metric(agg="sum", column="amount", equals=60, tolerance=0.01).evaluate(_be())
    assert r.status is Status.PASS


def test_equals_outside_tolerance_fails():
    r = Metric(agg="sum", column="amount", equals=100, tolerance=1).evaluate(_be())
    assert r.status is Status.FAIL
    assert "sum(amount)" in r.message


def test_range_bounds():
    assert Metric(agg="avg", column="amount", min=10, max=30).evaluate(_be()).status is Status.PASS
    assert Metric(agg="avg", column="amount", max=15).evaluate(_be()).status is Status.FAIL


def test_count_with_and_without_column():
    be = _be()
    assert Metric(agg="count", equals=4).evaluate(be).status is Status.PASS  # rows incl. null
    assert Metric(agg="count", column="amount", equals=3).evaluate(be).status is Status.PASS  # non-null


def test_missing_column_is_error():
    r = Metric(agg="sum", column="ghost", equals=1).evaluate(_be())
    assert r.status is Status.ERROR


def test_invalid_agg_rejected_at_load():
    with pytest.raises(SuiteLoadError):
        Suite.from_dict({"suite": "t", "checks": [{"type": "metric", "agg": "median", "equals": 1}]})


def test_missing_expectation_rejected_at_load():
    with pytest.raises(SuiteLoadError):
        Suite.from_dict({"suite": "t", "checks": [{"type": "metric", "agg": "sum", "column": "amount"}]})


def test_builds_from_registry():
    check = build_check({"type": "metric", "agg": "avg", "column": "amount", "min": 0})
    assert isinstance(check, Metric)


def test_metric_matches_across_engines():
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine

    from trueset.backends.duckdb_backend import DuckDBBackend
    from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend

    df = pd.read_csv(EX / "orders.csv")
    suite = Suite.from_dict(
        {
            "suite": "m",
            "checks": [
                {"type": "metric", "column": "amount", "agg": "sum", "equals": 389.49, "tolerance": 0.01},
                {"type": "metric", "column": "amount", "agg": "avg", "min": 0, "max": 100},
                {"type": "metric", "agg": "count", "equals": 7},
            ],
        }
    )
    con = duckdb.connect()
    con.execute("CREATE TABLE o AS SELECT * FROM df")
    eng = create_engine("sqlite://")
    df.to_sql("o", eng, index=False)

    verdicts = [
        [(r.check, r.status.value) for r in suite.run(be).results]
        for be in (PandasBackend(df), DuckDBBackend(con, "o"), SQLAlchemyBackend(eng, "o"))
    ]
    assert verdicts[0] == verdicts[1] == verdicts[2]
