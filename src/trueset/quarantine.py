"""Row-level routing: split a batch into clean and quarantined rows.

trueset detects; it never silently reroutes your data. This module gives a
pipeline the *material* to route with: the actual rows that failed, partitioned
from the rows that passed. What you do with them -- load the good, dead-letter
the bad for repair/replay -- is your call.

This operates on an in-memory DataFrame, which is where quarantine / dead-letter
belongs (at ingestion, in flight). Only row-wise checks contribute
(`Check.failure_spec()`); dataset-level checks like row_count/metric/freshness
don't fail per row, so they don't split anything -- run those as a normal gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .backends.pandas_backend import PandasBackend
from .result import Severity

#: column added by `bad_annotated()` listing why each row was quarantined
REASONS_COLUMN = "_trueset_reasons"


def _label(check) -> str:
    column = getattr(check, "column", None)
    return f"{check.type}({column})" if column else check.type


def _row_mask(check, be, df) -> pd.Series | None:
    """The per-row failing mask for a check, or None if it has no per-row notion.

    Prefers the simple `failure_spec()` predicate (works on any backend); falls
    back to a check's own `pandas_row_mask(df)` for analytical checks like
    corroboration that can't be expressed as a single predicate.
    """
    spec = check.failure_spec()
    if spec is not None:
        return be.failing_mask(spec)
    fn = getattr(check, "pandas_row_mask", None)
    if fn is not None:
        return fn(df)
    return None


@dataclass
class Split:
    """The result of partitioning a DataFrame against a suite's row-wise checks."""

    good: pd.DataFrame
    bad: pd.DataFrame
    #: row label (DataFrame index) -> the check labels it failed
    reasons: dict[Any, list[str]] = field(default_factory=dict)

    @property
    def n_good(self) -> int:
        return len(self.good)

    @property
    def n_bad(self) -> int:
        return len(self.bad)

    def bad_annotated(self) -> pd.DataFrame:
        """`bad`, plus a `_trueset_reasons` column -- ready for a dead-letter sink."""
        out = self.bad.copy()
        out[REASONS_COLUMN] = [
            "; ".join(self.reasons.get(idx, [])) for idx in out.index
        ]
        return out


def split(df: pd.DataFrame, suite, include_warnings: bool = False) -> Split:
    """Partition `df` into rows that pass every row-wise check (`good`) and rows
    that fail at least one (`bad`), recording why each bad row failed.

    `suite` may be a `Suite`, a dict spec, or a path to a checks YAML. By default
    only `error`-severity checks quarantine a row -- a `warn` check surfaces a
    problem without diverting the row, matching trueset's run semantics. Set
    `include_warnings=True` to quarantine on warnings too.
    """
    from .suite import Suite

    if isinstance(suite, (str, Path)):
        suite = Suite.from_yaml(suite)
    elif isinstance(suite, dict):
        suite = Suite.from_dict(suite)

    be = PandasBackend(df)
    bad_mask = pd.Series(False, index=df.index)
    reasons: dict[Any, list[str]] = {}

    for check in suite.checks:
        if check.severity is Severity.WARN and not include_warnings:
            continue  # a warning surfaces the issue but doesn't divert the row
        try:
            mask = _row_mask(check, be, df)
        except (KeyError, ValueError):
            continue  # e.g. missing column -- surfaced as an ERROR by evaluate()
        if mask is None:
            continue  # dataset-level or cross-system check: no per-row failures
        label = _label(check)
        for idx in df.index[mask]:
            reasons.setdefault(idx, []).append(label)
        bad_mask = bad_mask | mask

    return Split(good=df[~bad_mask].copy(), bad=df[bad_mask].copy(), reasons=reasons)


def failing_rows(backend, check, limit: int | None = None) -> list[dict]:
    """The rows failing a single check on any backend (a warehouse sample too).
    Returns [] for dataset-level / cross-system checks (no per-row failures)."""
    spec = check.failure_spec()
    if spec is None:
        return []
    return backend.failing_rows(spec, limit)
