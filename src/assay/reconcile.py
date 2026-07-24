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

from abc import abstractmethod
from collections.abc import Sequence

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

        allowed = ref_backend.distinct_values(self.ref_column)
        orphans = backend.count_not_in_set(self.column, list(allowed))
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
        **kw,
    ):
        super().__init__(reference, **kw)
        self.key = key
        self.columns = list(columns)
        self.ref_key = ref_key or key
        self.ref_columns = list(ref_columns) if ref_columns else list(columns)

    def evaluate(self, backend: Backend, ref_backend: Backend) -> CheckResult:
        a = backend.key_map(self.key, self.columns)
        b = ref_backend.key_map(self.ref_key, self.ref_columns)

        a_keys, b_keys = set(a), set(b)
        common = a_keys & b_keys
        mismatched = sum(1 for k in common if a[k] != b[k])
        only_primary = len(a_keys - b_keys)
        only_reference = len(b_keys - a_keys)
        failing = mismatched + only_primary + only_reference

        observed = {
            "mismatched_values": mismatched,
            "only_in_primary": only_primary,
            "only_in_reference": only_reference,
            "compared_keys": len(common),
        }
        return CheckResult(
            check=self.type,
            status=Status.PASS if failing == 0 else Status.FAIL,
            severity=self.severity,
            column=self.key,
            observed=observed,
            total_rows=len(a),
            failing_rows=failing,
            message="" if failing == 0 else (
                f"{mismatched} mismatch(es), "
                f"{only_primary} only-in-primary, "
                f"{only_reference} only-in-reference"
            ),
        )
