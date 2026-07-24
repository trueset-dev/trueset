"""Check definitions and the registry that maps YAML `type:` -> a Check.

Every check implements `evaluate(backend) -> CheckResult` and only ever
speaks to the Backend protocol, never to a concrete engine. Adding a new
check is: subclass Check, implement evaluate, and register it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from .backends.base import Backend
from .result import CheckResult, Severity, Status


class Check(ABC):
    #: stable identifier used in YAML `type:` and in results
    type: str = "check"

    def __init__(self, severity: Severity | str = Severity.ERROR):
        self.severity = Severity(severity)

    @abstractmethod
    def evaluate(self, backend: Backend) -> CheckResult:
        ...

    # -- helpers so subclasses stay tiny -------------------------------------

    def _fail_if_missing(self, backend: Backend, column: str) -> CheckResult | None:
        if column not in backend.columns():
            return CheckResult(
                check=self.type,
                column=column,
                status=Status.ERROR,
                severity=self.severity,
                message=f"column '{column}' does not exist",
            )
        return None

    def _result(
        self,
        failing: int,
        total: int,
        column: str | None = None,
        observed: Any = None,
        message: str = "",
    ) -> CheckResult:
        return CheckResult(
            check=self.type,
            column=column,
            status=Status.PASS if failing == 0 else Status.FAIL,
            severity=self.severity,
            observed=observed,
            total_rows=total,
            failing_rows=failing,
            message=message,
        )


# --------------------------------------------------------------------------- #
# Concrete checks
# --------------------------------------------------------------------------- #


class ColumnsExist(Check):
    type = "columns_exist"

    def __init__(self, columns: Sequence[str], **kw):
        super().__init__(**kw)
        self.columns = list(columns)

    def evaluate(self, backend: Backend) -> CheckResult:
        present = set(backend.columns())
        missing = [c for c in self.columns if c not in present]
        return CheckResult(
            check=self.type,
            status=Status.PASS if not missing else Status.FAIL,
            severity=self.severity,
            observed=missing,
            message="" if not missing else f"missing columns: {missing}",
        )


class NotNull(Check):
    type = "not_null"

    def __init__(self, column: str, **kw):
        super().__init__(**kw)
        self.column = column

    def evaluate(self, backend: Backend) -> CheckResult:
        if (err := self._fail_if_missing(backend, self.column)):
            return err
        nulls = backend.null_count(self.column)
        return self._result(
            failing=nulls,
            total=backend.row_count(),
            column=self.column,
            observed=nulls,
            message="" if nulls == 0 else f"{nulls} null value(s)",
        )


class Unique(Check):
    type = "unique"

    def __init__(self, column: str, **kw):
        super().__init__(**kw)
        self.column = column

    def evaluate(self, backend: Backend) -> CheckResult:
        if (err := self._fail_if_missing(backend, self.column)):
            return err
        total = backend.row_count()
        nulls = backend.null_count(self.column)
        distinct = backend.distinct_count(self.column)
        non_null = total - nulls
        dupes = non_null - distinct
        return self._result(
            failing=dupes,
            total=total,
            column=self.column,
            observed=dupes,
            message="" if dupes == 0 else f"{dupes} duplicate value(s)",
        )


class InSet(Check):
    type = "in_set"

    def __init__(self, column: str, values: Sequence[Any], **kw):
        super().__init__(**kw)
        self.column = column
        self.values = list(values)

    def evaluate(self, backend: Backend) -> CheckResult:
        if (err := self._fail_if_missing(backend, self.column)):
            return err
        bad = backend.count_not_in_set(self.column, self.values)
        return self._result(
            failing=bad,
            total=backend.row_count(),
            column=self.column,
            observed=bad,
            message="" if bad == 0 else f"{bad} value(s) outside allowed set",
        )


class InRange(Check):
    type = "in_range"

    def __init__(
        self,
        column: str,
        min: float | None = None,
        max: float | None = None,
        **kw,
    ):
        super().__init__(**kw)
        self.column = column
        self.min = min
        self.max = max

    def evaluate(self, backend: Backend) -> CheckResult:
        if (err := self._fail_if_missing(backend, self.column)):
            return err
        bad = backend.count_out_of_range(self.column, self.min, self.max)
        return self._result(
            failing=bad,
            total=backend.row_count(),
            column=self.column,
            observed=bad,
            message="" if bad == 0 else f"{bad} value(s) out of [{self.min}, {self.max}]",
        )


class MatchesRegex(Check):
    type = "matches_regex"

    def __init__(self, column: str, pattern: str, **kw):
        super().__init__(**kw)
        self.column = column
        self.pattern = pattern

    def evaluate(self, backend: Backend) -> CheckResult:
        if (err := self._fail_if_missing(backend, self.column)):
            return err
        bad = backend.count_regex_mismatch(self.column, self.pattern)
        return self._result(
            failing=bad,
            total=backend.row_count(),
            column=self.column,
            observed=bad,
            message="" if bad == 0 else f"{bad} value(s) do not match /{self.pattern}/",
        )


class RowCount(Check):
    type = "row_count"

    def __init__(self, min: int | None = None, max: int | None = None, **kw):
        super().__init__(**kw)
        self.min = min
        self.max = max

    def evaluate(self, backend: Backend) -> CheckResult:
        n = backend.row_count()
        bad = 0
        if self.min is not None and n < self.min:
            bad = 1
        if self.max is not None and n > self.max:
            bad = 1
        return CheckResult(
            check=self.type,
            status=Status.PASS if bad == 0 else Status.FAIL,
            severity=self.severity,
            observed=n,
            total_rows=n,
            message="" if bad == 0 else f"row count {n} outside [{self.min}, {self.max}]",
        )


class NoDuplicateRows(Check):
    type = "no_duplicate_rows"

    def __init__(self, subset: Sequence[str] | None = None, **kw):
        super().__init__(**kw)
        self.subset = list(subset) if subset else None

    def evaluate(self, backend: Backend) -> CheckResult:
        dupes = backend.duplicate_row_count(self.subset)
        return self._result(
            failing=dupes,
            total=backend.row_count(),
            observed=dupes,
            message="" if dupes == 0 else f"{dupes} duplicate row(s)",
        )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_REGISTRY: dict[str, type[Check]] = {}


def register(check_cls: type[Check]) -> type[Check]:
    _REGISTRY[check_cls.type] = check_cls
    return check_cls


for _c in (
    ColumnsExist,
    NotNull,
    Unique,
    InSet,
    InRange,
    MatchesRegex,
    RowCount,
    NoDuplicateRows,
):
    register(_c)


def build_check(spec: dict[str, Any]) -> Check:
    """Turn one YAML mapping into a Check instance."""
    spec = dict(spec)
    type_ = spec.pop("type", None)
    if type_ is None:
        raise ValueError(f"check is missing a 'type': {spec!r}")
    if type_ not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"unknown check type '{type_}'. known types: {known}")
    return _REGISTRY[type_](**spec)


def available_checks() -> list[str]:
    return sorted(_REGISTRY)
