"""Tests for results-history persistence (ResultStore)."""

import json

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")

from trueset import PandasBackend, Suite  # noqa: E402
from trueset.history import ResultStore  # noqa: E402


def _result(rows=3, dupe=False):
    ids = [1, 2, 3] if not dupe else [1, 1, 3]
    df = pd.DataFrame({"id": ids[:rows], "ssn": [None, "x", "y"][:rows]})
    return Suite.from_dict(
        {
            "suite": "orders",
            "dataset": "orders",
            "checks": [
                {"type": "unique", "column": "id"},
                {"type": "not_null", "column": "ssn", "owner": "risk", "sensitivity": "pii"},
            ],
        }
    ).run(PandasBackend(df))


@pytest.fixture
def store(tmp_path):
    return ResultStore(f"sqlite:///{tmp_path / 'h.db'}")


def test_save_and_read_run(store):
    run_id = store.save(_result(), at="2026-01-01T00:00:00+00:00")
    runs = store.runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["suite"] == "orders"
    assert runs[0]["rows"] == 3
    assert runs[0]["passed"] is False  # ssn has a null (error severity)


def test_results_persist_evidence_including_meta(store):
    run_id = store.save(_result())
    rows = store.results(run_id)
    assert [r["check"] for r in rows] == ["unique", "not_null"]
    ssn_row = rows[1]
    assert json.loads(ssn_row["meta"])["sensitivity"] == "pii"


def test_runs_ordered_newest_first_and_filterable(store):
    store.save(_result(), at="2026-01-01T00:00:00+00:00")
    store.save(_result(), at="2026-01-03T00:00:00+00:00")
    store.save(_result(), at="2026-01-02T00:00:00+00:00")
    runs = store.runs(suite="orders")
    assert [r["ts"] for r in runs] == [
        "2026-01-03T00:00:00+00:00",
        "2026-01-02T00:00:00+00:00",
        "2026-01-01T00:00:00+00:00",
    ]
    assert store.runs(suite="does-not-exist") == []


def test_row_count_history_oldest_to_newest(store):
    store.save(_result(rows=3), at="2026-01-01T00:00:00+00:00")
    store.save(_result(rows=2), at="2026-01-02T00:00:00+00:00")
    hist = store.row_count_history("orders", dataset="orders")
    assert [rows for _ts, rows in hist] == [3, 2]  # chronological


def test_store_survives_reopen(tmp_path):
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    ResultStore(url).save(_result(), at="2026-01-01T00:00:00+00:00")
    # A fresh store against the same URL must see the prior run.
    assert len(ResultStore(url).runs()) == 1
