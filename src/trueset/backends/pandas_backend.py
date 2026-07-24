"""Pandas implementation of the Backend protocol.

This is the reference backend. A Spark backend would mirror these methods
using DataFrame ops; a SQL/warehouse backend would translate each into a
`SELECT count(*) ... WHERE ...` pushed down to the engine so we never pull
the data locally.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


class PandasBackend:
    name = "pandas"

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def columns(self) -> list[str]:
        return list(self.df.columns)

    def row_count(self) -> int:
        return int(len(self.df))

    def null_count(self, column: str) -> int:
        return int(self.df[column].isna().sum())

    def distinct_count(self, column: str) -> int:
        return int(self.df[column].nunique(dropna=True))

    def duplicate_row_count(self, subset: Sequence[str] | None = None) -> int:
        cols = list(subset) if subset else None
        return int(self.df.duplicated(subset=cols, keep=False).sum())

    def count_not_in_set(self, column: str, allowed: Sequence[Any]) -> int:
        s = self.df[column].dropna()
        return int((~s.isin(list(allowed))).sum())

    def count_out_of_range(
        self,
        column: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> int:
        s = pd.to_numeric(self.df[column], errors="coerce").dropna()
        mask = pd.Series(False, index=s.index)
        if minimum is not None:
            mask |= s < minimum
        if maximum is not None:
            mask |= s > maximum
        return int(mask.sum())

    def count_regex_mismatch(self, column: str, pattern: str) -> int:
        s = self.df[column].dropna().astype(str)
        matches = s.str.fullmatch(pattern)
        return int((~matches.fillna(False)).sum())

    def max_value(self, column: str) -> Any:
        s = self.df[column].dropna()
        if s.empty:
            return None
        return s.max()

    # -- reconciliation primitives (cross-system) ---------------------------- #
    # In a warehouse backend these become pushed-down SQL / sampled checksums
    # (the data-diff approach) so we never pull full tables locally. For the
    # pandas reference backend we materialize, which is fine at dev scale.

    def distinct_values(self, column: str) -> set:
        return set(self.df[column].dropna().tolist())

    def key_map(self, key: str, columns) -> dict:
        cols = list(columns)
        sub = self.df[[key, *cols]].dropna(subset=[key])
        return {
            row[key]: tuple(row[c] for c in cols)
            for _, row in sub.iterrows()
        }
