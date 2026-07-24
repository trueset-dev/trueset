"""Portability proof: the SAME check specs must produce the SAME results
whether they run on pandas (in-memory) or DuckDB (SQL pushdown)."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from trueset import PandasBackend, Suite
from trueset.backends.duckdb_backend import DuckDBBackend

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute(f"CREATE TABLE orders AS SELECT * FROM read_csv_auto('{EX/'orders.csv'}')")
    c.execute(f"CREATE TABLE source AS SELECT * FROM read_csv_auto('{EX/'source_orders.csv'}')")
    c.execute(f"CREATE TABLE warehouse AS SELECT * FROM read_csv_auto('{EX/'warehouse_orders.csv'}')")
    return c


def _verdict(result):
    """Reduce a SuiteResult to a comparable (check, status) list."""
    return [(r.check, r.status.value) for r in result.results]


def test_single_source_suite_matches_across_engines(con):
    suite = Suite.from_yaml(EX / "checks.yml")

    pandas_result = suite.run(PandasBackend(pd.read_csv(EX / "orders.csv")))
    duck_result = suite.run(DuckDBBackend(con, "orders"))

    assert _verdict(pandas_result) == _verdict(duck_result)
    assert pandas_result.passed == duck_result.passed


def test_reconciliation_suite_matches_across_engines(con):
    suite = Suite.from_yaml(EX / "reconcile.yml")

    pandas_result = suite.run(
        PandasBackend(pd.read_csv(EX / "warehouse_orders.csv")),
        references={"source": PandasBackend(pd.read_csv(EX / "source_orders.csv"))},
    )
    duck_result = suite.run(
        DuckDBBackend(con, "warehouse"),
        references={"source": DuckDBBackend(con, "source")},
    )

    assert _verdict(pandas_result) == _verdict(duck_result)
    assert pandas_result.passed == duck_result.passed is False


def test_duckdb_pushes_down_referential_integrity(con):
    from trueset.reconcile import ReferentialIntegrity

    r = ReferentialIntegrity(
        column="order_id", reference="source", ref_column="id"
    ).evaluate(DuckDBBackend(con, "warehouse"), DuckDBBackend(con, "source"))
    assert r.failing_rows == 1  # order_id 1006 orphaned
