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
