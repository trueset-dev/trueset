"""DuckDB / SQL backend -- the proof that checks are engine-portable.

Every method implements the SAME Backend protocol as PandasBackend, but pushes
the work down as SQL: `SELECT count(*) ... WHERE ...` runs inside the database
instead of pulling the table into memory. The check classes are unchanged and
unaware of which engine answers them -- that's the whole point of the seam.

DuckDB is the first SQL target because it's zero-setup and in-process, but the
same SQL shape extends to Postgres / Snowflake / BigQuery through SQLAlchemy;
only the connection and a few dialect quirks differ.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _q(ident: str) -> str:
    """Quote a SQL identifier safely."""
    return '"' + str(ident).replace('"', '""') + '"'


class DuckDBBackend:
    name = "duckdb"

    def __init__(self, con, table: str):
        self.con = con
        self.table = table

    def _scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        return self.con.execute(sql, list(params or [])).fetchone()[0]

    def columns(self) -> list[str]:
        cur = self.con.execute(f"SELECT * FROM {_q(self.table)} LIMIT 0")
        return [d[0] for d in cur.description]

    def row_count(self) -> int:
        return int(self._scalar(f"SELECT count(*) FROM {_q(self.table)}"))

    def null_count(self, column: str) -> int:
        return int(self._scalar(
            f"SELECT count(*) FROM {_q(self.table)} WHERE {_q(column)} IS NULL"
        ))

    def distinct_count(self, column: str) -> int:
        return int(self._scalar(
            f"SELECT count(DISTINCT {_q(column)}) FROM {_q(self.table)}"
        ))

    def duplicate_row_count(self, subset: Sequence[str] | None = None) -> int:
        cols = list(subset) if subset else self.columns()
        collist = ", ".join(_q(c) for c in cols)
        sql = (
            f"SELECT coalesce(sum(c), 0) FROM "
            f"(SELECT count(*) c FROM {_q(self.table)} "
            f"GROUP BY {collist} HAVING count(*) > 1)"
        )
        return int(self._scalar(sql))

    def count_not_in_set(self, column: str, allowed: Sequence[Any]) -> int:
        allowed = list(allowed)
        if not allowed:
            return int(self._scalar(
                f"SELECT count(*) FROM {_q(self.table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            ))
        placeholders = ", ".join(["?"] * len(allowed))
        sql = (
            f"SELECT count(*) FROM {_q(self.table)} "
            f"WHERE {_q(column)} IS NOT NULL AND {_q(column)} NOT IN ({placeholders})"
        )
        return int(self._scalar(sql, allowed))

    def count_out_of_range(
        self, column: str, minimum: float | None = None, maximum: float | None = None
    ) -> int:
        val = f"TRY_CAST({_q(column)} AS DOUBLE)"
        conds, params = [], []
        if minimum is not None:
            conds.append(f"{val} < ?")
            params.append(minimum)
        if maximum is not None:
            conds.append(f"{val} > ?")
            params.append(maximum)
        if not conds:
            return 0
        sql = (
            f"SELECT count(*) FROM {_q(self.table)} "
            f"WHERE {val} IS NOT NULL AND ({' OR '.join(conds)})"
        )
        return int(self._scalar(sql, params))

    def count_regex_mismatch(self, column: str, pattern: str) -> int:
        sql = (
            f"SELECT count(*) FROM {_q(self.table)} "
            f"WHERE {_q(column)} IS NOT NULL "
            f"AND NOT regexp_full_match(CAST({_q(column)} AS VARCHAR), ?)"
        )
        return int(self._scalar(sql, [pattern]))

    def max_value(self, column: str) -> Any:
        return self._scalar(
            f"SELECT max({_q(column)}) FROM {_q(self.table)} "
            f"WHERE {_q(column)} IS NOT NULL"
        )

    # -- reconciliation primitives ------------------------------------------- #

    def distinct_values(self, column: str) -> set:
        rows = self.con.execute(
            f"SELECT DISTINCT {_q(column)} FROM {_q(self.table)} "
            f"WHERE {_q(column)} IS NOT NULL"
        ).fetchall()
        return {r[0] for r in rows}

    def key_map(self, key: str, columns) -> dict:
        cols = list(columns)
        collist = ", ".join(_q(c) for c in [key, *cols])
        rows = self.con.execute(
            f"SELECT {collist} FROM {_q(self.table)} WHERE {_q(key)} IS NOT NULL"
        ).fetchall()
        return {r[0]: tuple(r[1:]) for r in rows}
