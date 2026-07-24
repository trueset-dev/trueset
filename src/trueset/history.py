"""Results-history persistence: turn runs into an auditable, queryable trail.

Every SuiteResult is already deterministic JSON. Persisting runs makes that an
immutable audit trail -- proof that dataset X met policy Y on date Z -- and the
foundation monitoring builds on (trend a row count, spot a volume anomaly,
diagnose a regression).

The store is backed by SQLAlchemy, so history lives wherever you point it: a
local SQLite file for a laptop, or Postgres/Snowflake for a team. Two tables:

  trueset_runs     -- one row per suite run (verdict, counts, row volume, time)
  trueset_results  -- one row per check result within a run (full evidence)

This module depends on the optional [sql] extra (SQLAlchemy). It is never
imported by the core check path, so a pandas-only install stays dependency-free.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    desc,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from .result import SuiteResult

_META = MetaData()

RUNS = Table(
    "trueset_runs",
    _META,
    Column("run_id", String(36), primary_key=True),
    Column("suite", String(255), index=True),
    Column("dataset", String(255), nullable=True),
    Column("ts", String(32), index=True),  # ISO-8601 UTC
    Column("passed", Boolean),
    Column("rows", Integer, nullable=True),
    Column("n_pass", Integer),
    Column("n_fail", Integer),
    Column("n_error", Integer),
)

RESULTS = Table(
    "trueset_results",
    _META,
    Column("run_id", String(36), index=True),
    Column("idx", Integer),
    Column("check", String(64)),
    Column("column", String(255), nullable=True),
    Column("status", String(16)),
    Column("severity", String(16)),
    Column("failing_rows", Integer, nullable=True),
    Column("total_rows", Integer, nullable=True),
    Column("observed", Text, nullable=True),  # JSON
    Column("meta", Text, nullable=True),  # JSON (governance)
    Column("message", Text, nullable=True),
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dataset_rows(result: SuiteResult) -> int | None:
    """The dataset's row volume for this run, inferred from any check that saw it."""
    for r in result.results:
        if r.total_rows is not None:
            return r.total_rows
    return None


class ResultStore:
    """Persist and query SuiteResults through any SQLAlchemy engine."""

    def __init__(self, engine_or_url: Engine | str):
        self.engine: Engine = (
            engine_or_url
            if isinstance(engine_or_url, Engine)
            else create_engine(engine_or_url)
        )
        _META.create_all(self.engine)

    def save(
        self,
        result: SuiteResult,
        *,
        dataset: str | None = None,
        run_id: str | None = None,
        at: str | None = None,
    ) -> str:
        """Persist one run; returns its run_id."""
        run_id = run_id or uuid.uuid4().hex
        ts = at or _utcnow_iso()
        counts = result.counts
        with self.engine.begin() as conn:
            conn.execute(
                insert(RUNS).values(
                    run_id=run_id,
                    suite=result.name,
                    dataset=dataset or result.dataset,
                    ts=ts,
                    passed=result.passed,
                    rows=_dataset_rows(result),
                    n_pass=counts["pass"],
                    n_fail=counts["fail"],
                    n_error=counts["error"],
                )
            )
            rows = [
                {
                    "run_id": run_id,
                    "idx": i,
                    "check": r.check,
                    "column": r.column,
                    "status": r.status.value,
                    "severity": r.severity.value,
                    "failing_rows": r.failing_rows,
                    "total_rows": r.total_rows,
                    "observed": json.dumps(r.observed) if r.observed is not None else None,
                    "meta": json.dumps(r.meta.to_dict()) if r.meta.is_set() else None,
                    "message": r.message or None,
                }
                for i, r in enumerate(result.results)
            ]
            if rows:
                conn.execute(insert(RESULTS), rows)
        return run_id

    def runs(self, suite: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Most-recent runs first, optionally filtered to one suite."""
        stmt = select(RUNS).order_by(desc(RUNS.c.ts)).limit(limit)
        if suite is not None:
            stmt = stmt.where(RUNS.c.suite == suite)
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt)]

    def results(self, run_id: str) -> list[dict[str, Any]]:
        """All check results for a run, in order."""
        stmt = select(RESULTS).where(RESULTS.c.run_id == run_id).order_by(RESULTS.c.idx)
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt)]

    def row_count_history(
        self, suite: str, dataset: str | None = None, limit: int = 100
    ) -> list[tuple[str, int]]:
        """(timestamp, rows) oldest->newest for a suite -- the input to volume monitoring."""
        stmt = (
            select(RUNS.c.ts, RUNS.c.rows)
            .where(RUNS.c.suite == suite, RUNS.c.rows.is_not(None))
            .order_by(desc(RUNS.c.ts))
            .limit(limit)
        )
        if dataset is not None:
            stmt = stmt.where(RUNS.c.dataset == dataset)
        with self.engine.connect() as conn:
            rows = [(r[0], int(r[1])) for r in conn.execute(stmt)]
        return list(reversed(rows))

    def metric_history(
        self,
        suite: str,
        *,
        metric: str = "rows",
        check: str | None = None,
        column: str | None = None,
        dataset: str | None = None,
        limit: int = 100,
    ) -> list[tuple[str, float]]:
        """(timestamp, value) oldest->newest for a numeric metric across runs.

        `metric="rows"` trends the dataset row volume. Otherwise `metric` is a
        per-check numeric column (`failing_rows` or `total_rows`) and `check`
        (optionally `column`) selects which check to trend -- e.g. the failing-row
        count of a specific not_null check over time. This lets monitoring watch
        any metric, not just volume, with no schema changes.
        """
        if metric == "rows":
            return [(ts, float(v)) for ts, v in
                    self.row_count_history(suite, dataset=dataset, limit=limit)]
        if metric not in ("failing_rows", "total_rows"):
            raise ValueError("metric must be 'rows', 'failing_rows', or 'total_rows'")
        if check is None:
            raise ValueError("check=... is required for per-check metrics")

        col = RESULTS.c.failing_rows if metric == "failing_rows" else RESULTS.c.total_rows
        stmt = (
            select(RUNS.c.ts, col)
            .select_from(RESULTS.join(RUNS, RESULTS.c.run_id == RUNS.c.run_id))
            .where(RUNS.c.suite == suite, RESULTS.c.check == check, col.is_not(None))
            .order_by(desc(RUNS.c.ts))
            .limit(limit)
        )
        if column is not None:
            stmt = stmt.where(RESULTS.c.column == column)
        if dataset is not None:
            stmt = stmt.where(RUNS.c.dataset == dataset)
        with self.engine.connect() as conn:
            rows = [(r[0], float(r[1])) for r in conn.execute(stmt)]
        return list(reversed(rows))
