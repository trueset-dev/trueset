"""Portability proof #2: the SAME check specs must produce the SAME verdicts
whether they run on pandas (in-memory) or on a real SQL database reached through
SQLAlchemy. We use SQLite here (stdlib, zero setup); the identical code path
serves Postgres/MySQL/Snowflake/BigQuery via their SQLAlchemy dialects.
"""

from pathlib import Path

import pandas as pd
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine  # noqa: E402

from trueset import PandasBackend, Suite  # noqa: E402
from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def engine(tmp_path):
    """A file-based SQLite engine loaded with the example datasets.

    File-based (not `:memory:`) so every new connection sees the same tables.
    """
    eng = create_engine(f"sqlite:///{tmp_path / 'trueset.db'}")
    for name, csv in (
        ("orders", "orders.csv"),
        ("source", "source_orders.csv"),
        ("warehouse", "warehouse_orders.csv"),
    ):
        pd.read_csv(EX / csv).to_sql(name, eng, index=False, if_exists="replace")
    return eng


def _verdict(result):
    return [(r.check, r.status.value) for r in result.results]


def test_single_source_suite_matches_pandas(engine):
    suite = Suite.from_yaml(EX / "checks.yml")
    pandas_result = suite.run(PandasBackend(pd.read_csv(EX / "orders.csv")))
    sa_result = suite.run(SQLAlchemyBackend(engine, "orders"))
    assert _verdict(pandas_result) == _verdict(sa_result)
    assert pandas_result.passed == sa_result.passed


def test_reconciliation_suite_matches_pandas(engine):
    suite = Suite.from_yaml(EX / "reconcile.yml")
    pandas_result = suite.run(
        PandasBackend(pd.read_csv(EX / "warehouse_orders.csv")),
        references={"source": PandasBackend(pd.read_csv(EX / "source_orders.csv"))},
    )
    sa_result = suite.run(
        SQLAlchemyBackend(engine, "warehouse"),
        references={"source": SQLAlchemyBackend(engine, "source")},
    )
    assert _verdict(pandas_result) == _verdict(sa_result)
    assert pandas_result.passed == sa_result.passed is False


def test_cross_engine_pandas_primary_sql_reference(engine):
    """Reconciliation across DIFFERENT engines: pandas primary, SQL reference.
    This is the whole thesis -- a check written once compares two systems that
    need not share an engine."""
    from trueset.reconcile import ReferentialIntegrity

    primary = PandasBackend(pd.read_csv(EX / "warehouse_orders.csv"))
    reference = SQLAlchemyBackend(engine, "source")
    r = ReferentialIntegrity(
        column="order_id", reference="source", ref_column="id"
    ).evaluate(primary, reference)
    assert r.failing_rows == 1  # one orphaned warehouse order_id


# -- per-primitive checks (dialect-specific SQL that must match pandas) ------- #


def test_regex_pushdown_matches_pandas(engine):
    be = SQLAlchemyBackend(engine, "orders")
    pattern = r"[^@\s]+@[^@\s]+\.[^@\s]+"
    assert be.count_regex_mismatch("email", pattern) == 1  # 'not-an-email'


def test_range_and_null_pushdown(engine):
    be = SQLAlchemyBackend(engine, "orders")
    assert be.count_out_of_range("amount", minimum=0) == 1  # the -5.00
    assert be.null_count("amount") == 1  # the blank cell
    assert be.duplicate_row_count() == 2  # the repeated 1002 row


def test_columns_and_row_count(engine):
    be = SQLAlchemyBackend(engine, "orders")
    assert be.row_count() == 7
    assert "email" in be.columns()
    assert be.distinct_count("order_id") == 6  # 1002 repeats
