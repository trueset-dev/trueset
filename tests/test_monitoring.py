"""Tests for monitoring: the freshness check and volume-anomaly detection."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from trueset import PandasBackend, build_check, volume_anomaly
from trueset.checks import Freshness
from trueset.result import Status

EX = Path(__file__).resolve().parents[1] / "examples"


# -- freshness --------------------------------------------------------------- #


def _orders():
    return PandasBackend(pd.read_csv(EX / "orders.csv"))  # max created_at = 2026-01-10


def test_freshness_passes_when_recent():
    r = Freshness("created_at", max_age_hours=48, now=datetime(2026, 1, 11)).evaluate(_orders())
    assert r.status is Status.PASS
    assert r.observed["age_hours"] == 24.0


def test_freshness_fails_when_stale():
    r = Freshness("created_at", max_age_hours=24, now=datetime(2026, 3, 1)).evaluate(_orders())
    assert r.status is Status.FAIL
    assert "stale" in r.message


def test_freshness_empty_column_fails():
    be = PandasBackend(pd.DataFrame({"ts": [None, None]}))
    r = Freshness("ts", max_age_hours=24, now=datetime(2026, 1, 1)).evaluate(be)
    assert r.status is Status.FAIL


def test_freshness_unparseable_is_error():
    be = PandasBackend(pd.DataFrame({"ts": ["not-a-date"]}))
    r = Freshness("ts", max_age_hours=24, now=datetime(2026, 1, 1)).evaluate(be)
    assert r.status is Status.ERROR


def test_freshness_builds_from_yaml_spec():
    check = build_check({"type": "freshness", "column": "created_at", "max_age_hours": 6})
    assert isinstance(check, Freshness)


def test_freshness_now_accepts_iso_string():
    r = Freshness("created_at", max_age_hours=48, now="2026-01-11").evaluate(_orders())
    assert r.status is Status.PASS


def test_freshness_matches_across_engines():
    """Same verdict on pandas, DuckDB, and SQLAlchemy despite different max types."""
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine

    from trueset.backends.duckdb_backend import DuckDBBackend
    from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend

    df = pd.read_csv(EX / "orders.csv")
    con = duckdb.connect()
    con.execute("CREATE TABLE o AS SELECT * FROM df")
    eng = create_engine("sqlite://")  # in-memory ok: single connection reused below
    df.to_sql("o", eng, index=False)

    now = datetime(2026, 2, 1)
    check = Freshness("created_at", max_age_hours=24, now=now)
    verdicts = {
        check.evaluate(PandasBackend(df)).status,
        check.evaluate(DuckDBBackend(con, "o")).status,
        check.evaluate(SQLAlchemyBackend(eng, "o")).status,
    }
    assert verdicts == {Status.FAIL}  # all agree: stale


# -- volume anomaly ---------------------------------------------------------- #


def test_volume_insufficient_history():
    v = volume_anomaly([100, 100])
    assert v["status"] == "insufficient_history"
    assert v["anomaly"] is False


def test_volume_stable_is_not_anomalous():
    v = volume_anomaly([1000, 1010, 990, 1005, 1002])
    assert v["anomaly"] is False


def test_volume_sudden_drop_is_anomalous():
    v = volume_anomaly([1000, 1010, 990, 1005, 200])
    assert v["anomaly"] is True
    assert v["zscore"] < 0


def test_volume_flat_baseline_any_change_is_anomalous():
    v = volume_anomaly([500, 500, 500, 700])
    assert v["anomaly"] is True
    assert v["zscore"] is None  # std==0 path


def test_volume_within_sigma_is_ok():
    # current (102) sits well inside 3 std-devs of the baseline mean
    v = volume_anomaly([100, 102, 98, 101, 102], sigma=3.0)
    assert v["anomaly"] is False
