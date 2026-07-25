"""Ambiguity-aware validation: for data where an extreme value is often the
*truth*, not an error (a geopolitical event, a cold-snap demand spike, a market
move). You can't threshold your way out of that. trueset's job is to surface and
quantify the ambiguity, not pretend to resolve it. This module provides:

- **corroboration** -- judge a suspicious value against *supporting signals*
  (does volume back the price spike? does a second source agree?), not in
  isolation. A robust outlier that nothing corroborates is the one worth a look.
- **annotate** -- attach a confidence score + flags to every row and let them
  *flow* (market data often can't be blocked; you need a full view). The opposite
  of a hard gate.
- **Adjudications** -- when a human rules a flag "actually valid", record it so
  future runs stop re-flagging it: the feedback loop that kills repeat false
  positives.
- **segment_bounds** -- context-aware expected ranges per segment (per region /
  regime / season) so a legitimate seasonal spike isn't judged by a global band.

All deterministic and explainable. Operates on an in-memory DataFrame -- the
natural home for this row-level statistical analysis; warehouse pushdown is on
the roadmap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .checks import Check, register
from .result import CheckResult, Severity, Status
from .stats import robust_bounds, robust_z

QUALITY_COLUMN = "_trueset_quality"
FLAGS_COLUMN = "_trueset_flags"


# --------------------------------------------------------------------------- #
# 1. Corroboration -- is a suspicious value supported by related signals?
# --------------------------------------------------------------------------- #


@dataclass
class CorroborationResult:
    #: True where the primary is a robust outlier that nothing corroborates
    uncorroborated: pd.Series
    #: per-row detail: primary z, support count, and each corroborator's z
    detail: pd.DataFrame

    @property
    def n_flagged(self) -> int:
        return int(self.uncorroborated.sum())


def corroboration_flags(
    df: pd.DataFrame,
    column: str,
    corroborate_with: list[str],
    z: float = 3.5,
    support_z: float = 2.0,
    min_support: int = 1,
    directional: bool = True,
) -> CorroborationResult:
    """Flag rows where `column` is a robust outlier that its corroborators do NOT
    support -- i.e. a spike with nothing backing it up.

    A corroborator "supports" a primary outlier when it, too, moves beyond
    `support_z` robust deviations -- and, if `directional`, in the *same*
    direction (a real price spike shows up as a volume spike, not a volume drop).
    A row is flagged when the primary is beyond `z` and fewer than `min_support`
    corroborators back it. Real extremes get corroborated and pass; lone spikes
    (the silent errors) get surfaced.
    """
    missing = [c for c in [column, *corroborate_with] if c not in df.columns]
    if missing:
        raise KeyError(f"corroboration: missing column(s) {missing}")

    rz_primary = robust_z(df[column])
    primary_outlier = rz_primary.abs() > z

    detail = pd.DataFrame({f"z_{column}": rz_primary}, index=df.index)
    support = pd.Series(0, index=df.index)
    for c in corroborate_with:
        rz_c = robust_z(df[c])
        detail[f"z_{c}"] = rz_c
        moves = rz_c.abs() > support_z
        if directional:
            moves &= np.sign(rz_c) == np.sign(rz_primary)
        support = support + moves.astype(int)
    detail["support"] = support

    uncorroborated = primary_outlier & (support < min_support)
    return CorroborationResult(uncorroborated=uncorroborated, detail=detail)


@register
class Corroboration(Check):
    """Suite-level corroboration check: fails on rows where `column` is a robust
    outlier that its corroborating signals do not support.

    ```yaml
    - type: corroboration
      column: price
      corroborate_with: [volume]   # a real price spike shows up in volume too
      z: 3.5                        # primary outlier threshold (robust)
      min_support: 1               # how many corroborators must agree
      severity: warn               # surface it; don't block (real extremes happen)
    ```
    """

    type = "corroboration"

    def __init__(
        self,
        column: str,
        corroborate_with: list[str],
        z: float = 3.5,
        support_z: float = 2.0,
        min_support: int = 1,
        directional: bool = True,
        **kw,
    ):
        super().__init__(**kw)
        self.column = column
        self.corroborate_with = list(corroborate_with)
        self.z = z
        self.support_z = support_z
        self.min_support = min_support
        self.directional = directional

    def evaluate(self, backend: Any) -> CheckResult:
        df = getattr(backend, "df", None)
        if df is None:  # SQL/warehouse backends: not yet supported
            return CheckResult(
                check=self.type, status=Status.ERROR, severity=self.severity,
                column=self.column,
                message="corroboration currently requires the in-memory (pandas) "
                        "backend; warehouse pushdown is on the roadmap",
            )
        try:
            res = corroboration_flags(
                df, self.column, self.corroborate_with, self.z,
                self.support_z, self.min_support, self.directional,
            )
        except KeyError as exc:
            return CheckResult(check=self.type, status=Status.ERROR,
                               severity=self.severity, column=self.column, message=str(exc))
        bad = res.n_flagged
        return CheckResult(
            check=self.type,
            status=Status.PASS if bad == 0 else Status.FAIL,
            severity=self.severity,
            column=self.column,
            observed=bad,
            total_rows=len(df),
            failing_rows=bad,
            message="" if bad == 0 else (
                f"{bad} outlier(s) in '{self.column}' uncorroborated by "
                f"{self.corroborate_with}"
            ),
        )

    def pandas_row_mask(self, df: pd.DataFrame) -> pd.Series:
        """Per-row failing mask, so annotate()/split() can include corroboration
        even though it isn't a simple `failure_spec()` predicate."""
        return corroboration_flags(
            df, self.column, self.corroborate_with, self.z,
            self.support_z, self.min_support, self.directional,
        ).uncorroborated


# --------------------------------------------------------------------------- #
# 5. Adjudications -- human verdicts that stop repeat false positives
# --------------------------------------------------------------------------- #


@dataclass
class Adjudications:
    """A record of human calls that a flag was actually valid, so future runs
    don't re-flag the same thing. The feedback loop: review once, suppress after.

    Keyed by (check label, key value) -- e.g. ``("in_range(price)", "BRENT-2026-03-09")``.
    Deliberately dumb and auditable: a list of verdicts you can read, diff, and
    commit to git next to your checks.
    """

    valid: dict[str, set] = field(default_factory=dict)

    def mark_valid(self, check_label: str, key: Any, note: str = "") -> None:
        self.valid.setdefault(check_label, set()).add(str(key))

    def is_valid(self, check_label: str, key: Any) -> bool:
        return str(key) in self.valid.get(check_label, set())

    def to_dict(self) -> dict[str, list]:
        return {k: sorted(v) for k, v in self.valid.items()}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> Adjudications:
        raw = json.loads(Path(path).read_text())
        return cls(valid={k: set(v) for k, v in raw.items()})


# --------------------------------------------------------------------------- #
# 2. Annotate-and-flow -- confidence score + flags, nothing blocked
# --------------------------------------------------------------------------- #

_WEIGHT = {"error": 1.0, "warn": 0.4}


def annotate(
    df: pd.DataFrame,
    suite,
    key: str | None = None,
    adjudications: Adjudications | None = None,
) -> pd.DataFrame:
    """Return `df` with two added columns and *every row kept*:

    - ``_trueset_quality`` -- a 0..1 confidence score (1 = passes every row-wise
      check; error failures cost more than warnings).
    - ``_trueset_flags`` -- the checks each row failed (``""`` if clean).

    This is the annotate-and-flow model: instead of blocking bad rows, you let
    them through carrying their quality so downstream can decide -- essential when
    you need a full view of the data. Pass `adjudications` (+ the `key` column) to
    suppress flags a human already ruled valid.
    """
    from .quarantine import _label, _row_mask
    from .suite import Suite

    if isinstance(suite, (str, Path)):
        suite = Suite.from_yaml(suite)
    elif isinstance(suite, dict):
        suite = Suite.from_dict(suite)

    from .backends.pandas_backend import PandasBackend

    be = PandasBackend(df)
    total_weight = 0.0
    penalty = pd.Series(0.0, index=df.index)
    flags: dict[Any, list[str]] = {idx: [] for idx in df.index}

    for check in suite.checks:
        try:
            mask = _row_mask(check, be, df)
        except (KeyError, ValueError):
            continue
        if mask is None:
            continue
        w = _WEIGHT.get(check.severity.value, 1.0) if isinstance(check.severity, Severity) \
            else _WEIGHT.get(str(check.severity), 1.0)
        total_weight += w
        label = _label(check)
        for idx in df.index[mask]:
            if adjudications and key is not None and adjudications.is_valid(label, df.at[idx, key]):
                continue  # a human already ruled this one valid -- don't re-flag
            penalty.at[idx] += w
            flags[idx].append(label)

    out = df.copy()
    if total_weight > 0:
        out[QUALITY_COLUMN] = (1.0 - penalty / total_weight).clip(0.0, 1.0).round(3)
    else:
        out[QUALITY_COLUMN] = 1.0
    out[FLAGS_COLUMN] = [("; ".join(flags[idx])) for idx in df.index]
    return out


# --------------------------------------------------------------------------- #
# 3. Context-aware expected ranges -- one band per segment, not one globally
# --------------------------------------------------------------------------- #


def segment_bounds(
    df: pd.DataFrame,
    column: str,
    segment_by: str,
    z: float = 3.5,
) -> dict[Any, dict[str, float]]:
    """Robust [low, high] bounds for `column` computed *within each segment* of
    `segment_by` (per region / regime / season). A legitimate seasonal spike in
    one segment no longer trips a global threshold set by the others.

    Returns ``{segment_value: {"min": lo, "max": hi, "n": count}}`` for review --
    the calibrated, context-aware ranges you'd otherwise hand-tune per segment.
    """
    for c in (column, segment_by):
        if c not in df.columns:
            raise KeyError(f"segment_bounds: missing column '{c}'")
    out: dict[Any, dict[str, float]] = {}
    for seg, grp in df.groupby(segment_by):
        lo, hi = robust_bounds(grp[column], z=z)
        if lo != lo:  # nan -> no numeric data in this segment
            continue
        out[seg] = {"min": round(float(lo), 4), "max": round(float(hi), 4), "n": int(len(grp))}
    return out
