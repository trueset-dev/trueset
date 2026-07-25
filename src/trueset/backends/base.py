"""The Backend protocol: the single seam that makes checks portable.

A Check never touches pandas, Spark, or SQL directly. It only calls the
small set of primitive operations defined here. To support a new engine you
implement ONE class satisfying this protocol -- you do not rewrite a single
check. This is the core bet of the project: write a check once, run it
anywhere.

Keep this interface small and boring. Every method you add here is a method
every future backend must implement, so only add primitives that many checks
share.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    name: str

    def columns(self) -> list[str]:
        """Return the dataset's column names."""
        ...

    def row_count(self) -> int:
        ...

    def null_count(self, column: str) -> int:
        ...

    def distinct_count(self, column: str) -> int:
        ...

    def duplicate_row_count(self, subset: Sequence[str] | None = None) -> int:
        """Rows that are part of a duplicate group (total minus distinct)."""
        ...

    def count_not_in_set(self, column: str, allowed: Sequence[Any]) -> int:
        """Non-null values not present in `allowed`."""
        ...

    def count_out_of_range(
        self,
        column: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> int:
        """Non-null numeric values below `minimum` or above `maximum`."""
        ...

    def count_regex_mismatch(self, column: str, pattern: str) -> int:
        """Non-null values that do NOT fully match `pattern`."""
        ...

    def max_value(self, column: str) -> Any:
        """The maximum non-null value of `column` (None if empty/all-null).

        Used by freshness monitoring: the newest timestamp in a column.
        """
        ...

    def aggregate(self, func: str, column: str | None = None) -> float | None:
        """A numeric aggregate over `column`: one of sum/avg/min/max/count.

        `count` with no column is the row count; with a column it counts
        non-null values. The others operate on non-null numeric values and
        return None when there are none. Used by the `metric` check.
        """
        ...

    def failing_rows(self, spec: dict[str, Any], limit: int | None = None) -> list[dict]:
        """Return the actual rows that fail a check's `failure_spec()` predicate.

        `spec` is one of the engine-agnostic predicates a check produces (e.g.
        ``{"kind": "null", "column": "email"}``). Returns up to `limit` rows as
        plain dicts. This is what lets a pipeline quarantine / dead-letter the
        bad rows -- trueset still only identifies them; the caller routes them.
        """
        ...

    def fetch_columns(self, columns: Sequence[str]) -> Any:
        """Materialize just `columns` as a pandas DataFrame.

        For row-level *analytical* checks (e.g. corroboration) whose statistics
        need the whole distribution, not a count. It projects only the requested
        columns -- never the full table -- so an engine can answer without moving
        everything. (Aggregate pushdown of the statistics themselves is a future
        optimization for very large tables.)
        """
        ...
