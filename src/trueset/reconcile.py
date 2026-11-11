"""Reconciliation checks: validate data *across two systems*.

This is the capability no single-source tool (GE, Soda, Pandera, dbt tests)
is architected to express, and the open-source option that did it (data-diff)
was archived in 2024. Because our checks talk only to the Backend protocol, a
reconciliation check simply holds a second ("reference") backend and compares.
The two backends can be different engines entirely -- pandas vs a warehouse vs
a CSV export -- and the check is written once.

A reconciliation check names the reference dataset it needs (`reference:`).
At run time the Suite resolves that name to a concrete backend and passes it in.
"""

from __future__ import annotations

import math
import numbers
from abc import abstractmethod
from collections.abc import Sequence

import pandas as pd

from .backends.base import Backend
from .checks import Check, register
from .result import CheckResult, Severity, Status


class ReconciliationCheck(Check):
    """Base for checks that compare a primary backend to a reference backend."""

    def __init__(self, reference: str, severity: Severity | str = Severity.ERROR):
        super().__init__(severity)
        self.reference = reference

    @abstractmethod
    def evaluate(self, backend: Backend, ref_backend: Backend) -> CheckResult:  # type: ignore[override]
        ...


@register
class RowCountParity(ReconciliationCheck):
    """Row counts of the two datasets agree within a relative tolerance.

    Note: passing this alone proves nothing about *contents* -- two datasets
    can have identical counts and completely different rows. That's exactly
    why value_parity and referential_integrity exist alongside it.
    """

    type = "row_count_parity"

    def __init__(self, reference: str, tolerance: float = 0.0, **kw):
        super().__init__(reference, **kw)
        self.tolerance = tolerance

    def evaluate(self, backend: Backend, ref_backend: Backend) -> CheckResult:
        a, b = backend.row_count(), ref_backend.row_count()
        rel = abs(a - b) / max(b, 1)
        ok = rel <= self.tolerance
        return CheckResult(
            check=self.type,
            status=Status.PASS if ok else Status.FAIL,
            severity=self.severity,
            observed={"primary": a, "reference": b, "rel_diff": round(rel, 6)},
            total_rows=a,
            failing_rows=0 if ok else abs(a - b),
            message="" if ok else f"row counts differ: {a} vs {b}",
        )


@register
class ReferentialIntegrity(ReconciliationCheck):
    """Every value of `column` in the primary exists in `ref_column` of the
    reference. Catches orphans across systems (e.g. warehouse rows whose key
    never existed in the source)."""

    type = "referential_integrity"

    def __init__(self, column: str, reference: str, ref_column: str, **kw):
        super().__init__(reference, **kw)
        self.column = column
        self.ref_column = ref_column

    def evaluate(self, backend: Backend, ref_backend: Backend) -> CheckResult:
        if self.column not in backend.columns():
            return CheckResult(self.type, Status.ERROR, self.severity,
                               column=self.column,
                               message=f"column '{self.column}' missing in primary")
        if self.ref_column not in ref_backend.columns():
            return CheckResult(self.type, Status.ERROR, self.severity,
                               column=self.ref_column,
                               message=f"column '{self.ref_column}' missing in reference")

        orphans = _orphan_count(backend, ref_backend, self.column, self.ref_column)
        return self._result(
            failing=orphans,
            total=backend.row_count(),
            column=self.column,
            observed=orphans,
            message="" if orphans == 0
            else f"{orphans} row(s) with '{self.column}' absent from reference "
                 f"'{self.reference}.{self.ref_column}'",
        )


@register
class ValueParity(ReconciliationCheck):
    """Join primary and reference on a key; compare selected columns.

    Reports three failure modes together: value mismatches on shared keys,
    keys only in the primary, and keys only in the reference.
    """

    type = "value_parity"

    def __init__(
        self,
        key: str,
        columns: Sequence[str],
        reference: str,
        ref_key: str | None = None,
        ref_columns: Sequence[str] | None = None,
        tolerance: float = 0.0,
        **kw,
    ):
        super().__init__(reference, **kw)
        self.key = key
        self.columns = list(columns)
        self.ref_key = ref_key or key
        self.ref_columns = list(ref_columns) if ref_columns else list(columns)
        # Numeric tolerance for value comparison. Even at 0, values are compared
        # type-aware (Decimal('10.00') == 10.0 == '10.0'), so cross-engine type
        # drift doesn't read as a mismatch; raise it to absorb rounding.
        self.tolerance = float(tolerance)

    def evaluate(self, backend: Backend, ref_backend: Backend) -> CheckResult:
        for be, col, side in (
            (backend, self.key, "primary"),
            (ref_backend, self.ref_key, "reference"),
        ):
            if col not in be.columns():
                return CheckResult(
                    self.type, Status.ERROR, self.severity, column=col,
                    message=f"key column '{col}' missing in {side}",
                )

        # A key that repeats collapses in the join map (one row silently wins).
        # For a reconciliation contract that ambiguity IS a defect, so we detect
        # it up front with existing primitives rather than hide it.
        dup_primary = _duplicate_keys(backend, self.key)
        dup_reference = _duplicate_keys(ref_backend, self.ref_key)

        if (
            dup_primary == 0
            and dup_reference == 0
            and _same_sql_engine(backend, ref_backend)
        ):
            # Same database, no duplicate keys: push the whole comparison down as
            # SQL -- an inner join for value mismatches (tolerance included) and
            # anti-joins for only-in-each. No table is pulled into memory, and the
            # result is identical to the in-memory path below.
            mismatched = backend.count_value_mismatches(
                ref_backend, self.key, self.columns, self.ref_key, self.ref_columns,
                self.tolerance,
            )
            only_primary = backend.count_orphans(self.key, ref_backend, self.ref_key)
            only_reference = ref_backend.count_orphans(self.ref_key, backend, self.key)
            compared = backend.count_common_keys(ref_backend, self.key, self.ref_key)
        else:
            # Portable path (cross-engine, tolerant, or duplicate keys present):
            # compare the key + compared columns from each side in memory.
            a = backend.key_map(self.key, self.columns)
            b = ref_backend.key_map(self.ref_key, self.ref_columns)
            a_keys, b_keys = set(a), set(b)
            common = a_keys & b_keys
            mismatched = sum(1 for k in common if not _rows_equal(a[k], b[k], self.tolerance))
            only_primary = len(a_keys - b_keys)
            only_reference = len(b_keys - a_keys)
            compared = len(common)

        failing = mismatched + only_primary + only_reference + dup_primary + dup_reference

        observed = {
            "mismatched_values": mismatched,
            "only_in_primary": only_primary,
            "only_in_reference": only_reference,
            "duplicate_keys_primary": dup_primary,
            "duplicate_keys_reference": dup_reference,
            "compared_keys": compared,
        }
        parts = []
        if mismatched:
            parts.append(f"{mismatched} mismatch(es)")
        if only_primary:
            parts.append(f"{only_primary} only-in-primary")
        if only_reference:
            parts.append(f"{only_reference} only-in-reference")
        if dup_primary:
            parts.append(f"{dup_primary} duplicate key(s) in primary")
        if dup_reference:
            parts.append(f"{dup_reference} duplicate key(s) in reference")
        return CheckResult(
            check=self.type,
            status=Status.PASS if failing == 0 else Status.FAIL,
            severity=self.severity,
            column=self.key,
            observed=observed,
            total_rows=only_primary + compared,  # distinct non-null primary keys
            failing_rows=failing,
            message="" if failing == 0 else ", ".join(parts),
        )


def _duplicate_keys(backend: Backend, key: str) -> int:
    """How many non-null key occurrences collapse because the key repeats.

    Equal to (non-null rows) - (distinct non-null values). Uses only protocol
    primitives, so it works on every backend without new methods.
    """
    non_null = backend.row_count() - backend.null_count(key)
    return max(0, non_null - backend.distinct_count(key))


def _same_sql_engine(a: Backend, b: Backend) -> bool:
    """True if both backends are SQLAlchemy over the *same* database engine."""
    try:
        from .backends.sqlalchemy_backend import SQLAlchemyBackend
    except ImportError:  # pragma: no cover - sqlalchemy not installed
        return False
    return (
        isinstance(a, SQLAlchemyBackend)
        and isinstance(b, SQLAlchemyBackend)
        and str(a.engine.url) == str(b.engine.url)
    )


def _orphan_count(backend: Backend, ref_backend: Backend, column: str, ref_column: str) -> int:
    """Rows in `backend.column` with no match in `ref_backend.ref_column`.

    Same database -> a pushed-down anti-join (never materializes the keys).
    Otherwise the portable path: pull the reference's distinct keys and count
    non-members. Both paths return the identical count.
    """
    if _same_sql_engine(backend, ref_backend):
        return backend.count_orphans(column, ref_backend, ref_column)
    allowed = ref_backend.distinct_values(ref_column)
    return backend.count_not_in_set(column, list(allowed))


def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):  # non-scalar / unorderable -> treat as present
        return False


def _is_real_number(v) -> bool:
    """True for a genuine number (int/float/Decimal/numpy), but NOT bool or str."""
    return isinstance(v, numbers.Number) and not isinstance(v, bool)


def _as_number(v):
    """float(v) for a number or a numeric string, else None (for tolerance math)."""
    if isinstance(v, bool):
        return None
    try:
        f = float(v.strip()) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _values_equal(x, y, tol: float) -> bool:
    """Type- and tolerance-aware equality for a single compared value.

    - **Exact equality first**, so big integers, Decimals, strings and infinities
      are correct: ``2**53+1 != 2**53``, ``inf == inf``, and ``'007' != '7'``
      (text is never silently read as a number).
    - Two missing values (None/NaN) are equal; one-missing differs.
    - A real number vs its string form (``'10.0'`` vs ``10.0``) is reconciled, and
      two real numbers are compared within ``tol``. Numeric coercion only happens
      when **at least one side is a real number** -- two numeric-looking strings
      are compared as strings.
    """
    mx, my = _is_missing(x), _is_missing(y)
    if mx or my:
        return mx and my
    try:
        if x == y:  # exact: ints of any size, Decimal==float, strings, inf
            return True
    except TypeError:
        pass
    x_num, y_num = _is_real_number(x), _is_real_number(y)
    # a real number vs its string form: coerce the pair and compare
    if (x_num and isinstance(y, str)) or (y_num and isinstance(x, str)):
        nx, ny = _as_number(x), _as_number(y)
        return nx is not None and ny is not None and abs(nx - ny) <= tol
    # tolerance between two real numbers (float only for the tolerance step)
    if tol > 0 and x_num and y_num:
        return abs(float(x) - float(y)) <= tol
    return False


def _rows_equal(ta, tb, tol: float) -> bool:
    """Compare two tuples of per-column values element-wise."""
    return len(ta) == len(tb) and all(
        _values_equal(x, y, tol) for x, y in zip(ta, tb, strict=True)
    )
