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
SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")  # US SSN
IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_PHONE_CHARS_RE = re.compile(r"^\+?[\d\s().-]+$")

SMALL_CARDINALITY = 20  # object columns at/below this look categorical

#: which detected semantic type implies which data-classification level.
#: Deterministic, high-precision only -- these become *suggested* tags a human
#: reviews (never auto-applied). pii = personal, pci = payment/financial.
SENSITIVITY_BY_SEMANTIC = {
    "email": "pii",
    "phone": "pii",
    "ssn": "pii",
    "credit_card": "pci",
    "iban": "pci",
}


def _is_phone(value: str) -> bool:
    if not _PHONE_CHARS_RE.match(value):
        return False
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _is_credit_card(value: str) -> bool:
    digits = re.sub(r"[\s-]", "", value)
    return digits.isdigit() and 13 <= len(digits) <= 19 and _luhn_ok(digits)


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
    #: SUGGESTED classification (pii/pci) from the semantic type; None if unknown.
    #: A suggestion for human review -- trueset never auto-applies a tag.
    sensitivity: str | None = None

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
        # A card number stored as a bare integer still deserves the pci tag, but
        # only if the WHOLE column looks like one (length + Luhn) -- a random ID
        # column passing Luhn everywhere is vanishingly unlikely.
        if pd.api.types.is_integer_dtype(s):
            ints = non_null.head(200)
            if (ints.map(lambda v: _is_credit_card(str(int(v)))).mean()) > 0.99:
                return "credit_card"
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"

    sample = non_null.astype(str).head(200)

    def frac_match(rx: re.Pattern) -> float:
        return sample.map(lambda x: bool(rx.match(x))).mean()

    def frac_pred(pred) -> float:
        return sample.map(pred).mean()

    if frac_match(EMAIL_RE) > 0.8:
        return "email"
    if frac_match(UUID_RE) > 0.8:
        return "uuid"
    if frac_match(URL_RE) > 0.8:
        return "url"
    if frac_match(SSN_RE) > 0.8:
        return "ssn"
    if frac_match(IBAN_RE) > 0.8:
        return "iban"
    if frac_pred(_is_credit_card) > 0.8:
        return "credit_card"
    if frac_pred(_is_phone) > 0.8:
        return "phone"

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
                sensitivity=SENSITIVITY_BY_SEMANTIC.get(inferred),
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
        col_checks: list[dict[str, Any]] = []
        if c.null_rate == 0 and c.inferred != "empty":
            col_checks.append({"type": "not_null", "column": c.name})
        if c.is_unique:
            col_checks.append({"type": "unique", "column": c.name})
        if c.inferred == "categorical" and c.categories:
            col_checks.append({"type": "in_set", "column": c.name, "values": c.categories})
        if c.inferred == "numeric" and c.numeric_min is not None and c.numeric_min >= 0:
            col_checks.append({"type": "in_range", "column": c.name, "min": 0})
        if c.inferred == "email":
            col_checks.append(
                {
                    "type": "matches_regex",
                    "column": c.name,
                    "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+",
                    "severity": "warn",
                }
            )

        # Pre-tag every check on a classified column with the SUGGESTED
        # sensitivity, for a human to review and commit (never auto-applied).
        if c.sensitivity:
            for chk in col_checks:
                chk["sensitivity"] = c.sensitivity
        checks.extend(col_checks)
    return {"suite": suite_name, "checks": checks}
