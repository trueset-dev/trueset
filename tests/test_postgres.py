"""Real-Postgres parity, opt-in.

Runs only when TRUESET_PG_URL points at a reachable Postgres (CI sets it via a
service container; locally, e.g.
`docker run -d -e POSTGRES_PASSWORD=postgres -p 5433:5432 postgres:16` then
`export TRUESET_PG_URL=postgresql+psycopg://postgres:postgres@localhost:5433/postgres`).
Otherwise the whole module is skipped, so the default test run needs no Postgres.

This guards the headline claim -- "runs on any warehouse" -- against a *real*
Postgres, exercising the dialect-specific paths SQLite doesn't (the `~` regex
operator, casts, window functions).
"""

import os
from pathlib import Path

import pandas as pd
import pytest

URL = os.environ.get("TRUESET_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TRUESET_PG_URL to run Postgres parity")

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from sqlalchemy import create_engine  # noqa: E402

from trueset import PandasBackend, Suite  # noqa: E402
from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL)
    for name, csv in (("orders", "orders.csv"), ("source", "source_orders.csv"),
                      ("warehouse", "warehouse_orders.csv")):
        pd.read_csv(EX / csv).to_sql(name, eng, index=False, if_exists="replace")
    return eng


def _verdict(result):
    return [(r.check, r.status.value) for r in result.results]


def test_single_source_suite_matches_pandas(engine):
    suite = Suite.from_yaml(EX / "checks.yml")
    p = suite.run(PandasBackend(pd.read_csv(EX / "orders.csv")))
    pg = suite.run(SQLAlchemyBackend(engine, "orders"))
    assert _verdict(p) == _verdict(pg)
    assert p.passed == pg.passed


def test_reconciliation_matches_pandas(engine):
    suite = Suite.from_yaml(EX / "reconcile.yml")
    p = suite.run(
        PandasBackend(pd.read_csv(EX / "warehouse_orders.csv")),
        references={"source": PandasBackend(pd.read_csv(EX / "source_orders.csv"))},
    )
    pg = suite.run(
        SQLAlchemyBackend(engine, "warehouse"),
        references={"source": SQLAlchemyBackend(engine, "source")},
    )
    assert _verdict(p) == _verdict(pg)


@pytest.mark.parametrize("spec", [
    {"kind": "null", "column": "amount"},
    {"kind": "not_in_set", "column": "status",
     "allowed": ["pending", "shipped", "delivered", "cancelled"]},
    {"kind": "regex_mismatch", "column": "email", "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+"},
    {"kind": "duplicate_value", "column": "order_id"},
    {"kind": "duplicate_row", "subset": None},
])
def test_failing_rows_match_pandas(engine, spec):
    pb = PandasBackend(pd.read_csv(EX / "orders.csv"))
    sb = SQLAlchemyBackend(engine, "orders")
    assert len(pb.failing_rows(spec)) == len(sb.failing_rows(spec))


def test_aggregates_and_regex_match_pandas(engine):
    pb = PandasBackend(pd.read_csv(EX / "orders.csv"))
    sb = SQLAlchemyBackend(engine, "orders")
    assert pb.count_regex_mismatch("email", r"[^@\s]+@[^@\s]+\.[^@\s]+") == \
        sb.count_regex_mismatch("email", r"[^@\s]+@[^@\s]+\.[^@\s]+")
    assert round(pb.aggregate("sum", "amount"), 4) == round(sb.aggregate("sum", "amount"), 4)
    assert pb.distinct_count("order_id") == sb.distinct_count("order_id")
