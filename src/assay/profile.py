"""Profiling and heuristic check suggestion.

Two responsibilities, both fully deterministic and requiring NO AI:

1. `profile_dataframe` -> a structured DatasetProfile (stats + a cheap
   semantic guess per column: email / uuid / url / datetime / categorical /
   numeric / text).
2. `suggest_from_profile` -> a draft check suite (plain dicts, YAML-ready)
   inferred by simple rules.

This is the trustworthy baseline. The AI copilot (copilot.py) builds ON TOP
of this: it gets far richer, more semantic suggestions, but its output is
funnelled through the same deterministic check registry so nothing
un-auditable ever reaches your data.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
URL_RE = re.compile(r"^https?://", re.IGNORECASE)

SMALL_CARDINALITY = 20  # object columns at/below this look categorical


def _jsonable(v: Any) -> Any:
    """Coerce numpy/pandas scalars to plain python for clean serialization."""
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    total: int
    nulls: int
    null_rate: float
    distinct: int
    is_unique: bool
    inferred: str
    numeric_min: float | None = None
    numeric_max: float | None = None
    categories: list[Any] | None = None
    samples: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetProfile:
    rows: int
    columns: list[ColumnProfile]

    def to_dict(self) -> dict[str, Any]:
        return {"rows": self.rows, "columns": [c.to_dict() for c in self.columns]}


def _infer_semantic(s: pd.Series) -> str:
    non_null = s.dropna()
    if non_null.empty:
        return "empty"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"

    sample = non_null.astype(str).head(200)

    def frac_match(rx: re.Pattern) -> float:
        return sample.map(lambda x: bool(rx.match(x))).mean()

    if frac_match(EMAIL_RE) > 0.8:
        return "email"
    if frac_match(UUID_RE) > 0.8:
        return "uuid"
    if frac_match(URL_RE) > 0.8:
        return "url"

    # try datetime parse on strings
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().mean() > 0.9:
            return "datetime"
    except Exception:
        pass

    if non_null.nunique() <= SMALL_CARDINALITY:
        return "categorical"
    return "text"


def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    rows = int(len(df))
    cols: list[ColumnProfile] = []
    for name in df.columns:
        s = df[name]
        nulls = int(s.isna().sum())
        distinct = int(s.nunique(dropna=True))
        inferred = _infer_semantic(s)

        nmin = nmax = None
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            nmin = float(s.min())
            nmax = float(s.max())

        categories = None
        if inferred == "categorical":
            categories = [_jsonable(v) for v in sorted(s.dropna().unique().tolist())]

        cols.append(
            ColumnProfile(
                name=str(name),
                dtype=str(s.dtype),
                total=rows,
                nulls=nulls,
                null_rate=round(nulls / rows, 4) if rows else 0.0,
                distinct=distinct,
                is_unique=(distinct == rows - nulls and nulls == 0 and rows > 0),
                inferred=inferred,
                numeric_min=nmin,
                numeric_max=nmax,
                categories=categories,
                samples=[_jsonable(v) for v in s.dropna().head(3).tolist()],
            )
        )
    return DatasetProfile(rows=rows, columns=cols)


def suggest_from_profile(
    profile: DatasetProfile, suite_name: str = "suggested_suite"
) -> dict[str, Any]:
    """Deterministic, rule-based draft suite. No AI. Always safe to review."""
    checks: list[dict[str, Any]] = [
        {"type": "columns_exist", "columns": [c.name for c in profile.columns]},
        {"type": "row_count", "min": 1},
    ]
    for c in profile.columns:
        if c.null_rate == 0 and c.inferred != "empty":
            checks.append({"type": "not_null", "column": c.name})
        if c.is_unique:
            checks.append({"type": "unique", "column": c.name})
        if c.inferred == "categorical" and c.categories:
            checks.append(
                {"type": "in_set", "column": c.name, "values": c.categories}
            )
        if c.inferred == "numeric" and c.numeric_min is not None and c.numeric_min >= 0:
            checks.append({"type": "in_range", "column": c.name, "min": 0})
        if c.inferred == "email":
            checks.append(
                {
                    "type": "matches_regex",
                    "column": c.name,
                    "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+",
                    "severity": "warn",
                }
            )
    return {"suite": suite_name, "checks": checks}
