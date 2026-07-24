"""Tests for failing-row extraction and quarantine (split)."""

from pathlib import Path

import pandas as pd
import pytest

from trueset import PandasBackend, Suite, split
from trueset.quarantine import REASONS_COLUMN, failing_rows

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def batch():
    return pd.DataFrame(
        {
            "order_id": [1, 2, 2, 4, 5],  # 2 duplicated
            "amount": [10.0, 20.0, 30.0, -5.0, 15.0],  # -5 out of range
            "status": ["pending", "shipped", "delivered", "shipped", "teleported"],
        }
    )


CHECKS = {
    "suite": "t",
    "checks": [
        {"type": "unique", "column": "order_id"},
        {"type": "in_range", "column": "amount", "min": 0},
        {"type": "in_set", "column": "status", "values": ["pending", "shipped", "delivered"]},
    ],
}


# -- split ------------------------------------------------------------------- #


def test_split_partitions_good_and_bad(batch):
    s = split(batch, CHECKS)
    assert s.n_good == 1  # only order_id 1 is clean
    assert s.n_bad == 4
    assert s.n_good + s.n_bad == len(batch)


def test_split_records_reasons(batch):
    s = split(batch, CHECKS)
    # the two order_id==2 rows both fail uniqueness
    dup_reasons = [v for k, v in s.reasons.items() if "unique(order_id)" in v]
    assert len(dup_reasons) == 2
    # row with -5 fails in_range
    assert any("in_range(amount)" in r for r in s.reasons.values())


def test_bad_annotated_has_reasons_column(batch):
    annotated = split(batch, CHECKS).bad_annotated()
    assert REASONS_COLUMN in annotated.columns
    assert all(annotated[REASONS_COLUMN].str.len() > 0)


def test_warn_checks_do_not_quarantine_by_default():
    df = pd.DataFrame({"email": ["ok@x.com", "bad"]})
    spec = {"suite": "t", "checks": [
        {"type": "matches_regex", "column": "email",
         "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+", "severity": "warn"}
    ]}
    assert split(df, spec).n_bad == 0                      # warn: not diverted
    assert split(df, spec, include_warnings=True).n_bad == 1  # opt-in


def test_dataset_level_checks_dont_split(batch):
    # row_count / metric have no per-row failure -> they never quarantine a row
    spec = {"suite": "t", "checks": [
        {"type": "row_count", "min": 100},          # fails, but not per-row
        {"type": "metric", "column": "amount", "agg": "sum", "equals": 0},
    ]}
    s = split(batch, spec)
    assert s.n_bad == 0


def test_split_missing_column_does_not_crash(batch):
    s = split(batch, {"suite": "t", "checks": [{"type": "not_null", "column": "ghost"}]})
    assert s.n_bad == 0  # missing column is an ERROR at evaluate time, not a row split


def test_split_accepts_suite_object(batch):
    s = split(batch, Suite.from_dict(CHECKS))
    assert s.n_bad == 4


# -- failing_rows ------------------------------------------------------------ #


def test_failing_rows_helper_and_limit(batch):
    be = PandasBackend(batch)
    from trueset.checks import InRange

    rows = failing_rows(be, InRange("amount", min=0))
    assert len(rows) == 1 and rows[0]["amount"] == -5.0


def test_failing_rows_empty_for_dataset_level_check(batch):
    from trueset.checks import RowCount

    assert failing_rows(PandasBackend(batch), RowCount(min=100)) == []


def test_failing_rows_matches_across_engines():
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine

    from trueset.backends.duckdb_backend import DuckDBBackend
    from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend

    df = pd.read_csv(EX / "orders.csv")
    con = duckdb.connect()
    con.execute("CREATE TABLE o AS SELECT * FROM df")
    eng = create_engine("sqlite://")
    df.to_sql("o", eng, index=False)
    backends = [PandasBackend(df), DuckDBBackend(con, "o"), SQLAlchemyBackend(eng, "o")]

    specs = [
        {"kind": "null", "column": "amount"},
        {"kind": "not_in_set", "column": "status",
         "allowed": ["pending", "shipped", "delivered", "cancelled"]},
        {"kind": "out_of_range", "column": "amount", "min": 0, "max": None},
        {"kind": "regex_mismatch", "column": "email", "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+"},
        {"kind": "duplicate_value", "column": "order_id"},
        {"kind": "duplicate_row", "subset": None},
    ]
    for spec in specs:
        counts = [len(b.failing_rows(spec)) for b in backends]
        assert counts[0] == counts[1] == counts[2], f"{spec['kind']}: {counts}"
