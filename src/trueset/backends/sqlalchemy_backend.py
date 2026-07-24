"""Generic SQLAlchemy backend -- one class, every SQL warehouse.

This is the payoff of the Backend protocol. DuckDB proved a single engine could
answer checks as pushed-down SQL; this backend generalizes that to *anything*
SQLAlchemy speaks: Postgres, MySQL/MariaDB, SQLite, Snowflake, BigQuery,
Redshift, and more. Every method compiles to `SELECT count(*) ... WHERE ...`
executed inside the database, so full tables never move across the wire.

The check classes are unchanged and unaware of which engine answers them -- add
a warehouse by pointing this class at a connection, not by rewriting a check.

Only one operation isn't portable across dialects out of the box: regular
expression matching. We handle the common dialects explicitly (Postgres, MySQL,
SQLite, DuckDB) and raise a clear error for the rest rather than silently
producing wrong counts.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import (
    Float,
    MetaData,
    Table,
    cast,
    distinct,
    func,
    not_,
    select,
)
from sqlalchemy.engine import Engine


class SQLAlchemyBackend:
    """Implements the Backend protocol over any SQLAlchemy Engine.

    Parameters
    ----------
    engine : an ``sqlalchemy.Engine`` (from ``create_engine(url)``).
    table  : the table name to validate.
    schema : optional schema/namespace the table lives in.
    """

    def __init__(self, engine: Engine, table: str, *, schema: str | None = None):
        self.engine = engine
        self.table_name = table
        self.schema = schema
        self.name = f"sqlalchemy:{engine.dialect.name}"
        md = MetaData()
        self.table = Table(table, md, autoload_with=engine, schema=schema)

    # -- helpers ------------------------------------------------------------- #

    def _col(self, column: str):
        try:
            return self.table.c[column]
        except KeyError as exc:  # pragma: no cover - guarded by _fail_if_missing
            raise KeyError(f"column '{column}' not in table '{self.table_name}'") from exc

    def _scalar(self, stmt) -> Any:
        with self.engine.connect() as conn:
            return conn.execute(stmt).scalar()

    # -- protocol ------------------------------------------------------------ #

    def columns(self) -> list[str]:
        return [c.name for c in self.table.c]

    def row_count(self) -> int:
        return int(self._scalar(select(func.count()).select_from(self.table)))

    def null_count(self, column: str) -> int:
        col = self._col(column)
        return int(self._scalar(
            select(func.count()).select_from(self.table).where(col.is_(None))
        ))

    def distinct_count(self, column: str) -> int:
        # count(DISTINCT col) excludes NULLs on every SQL dialect, matching
        # pandas' nunique(dropna=True).
        col = self._col(column)
        return int(self._scalar(select(func.count(distinct(col)))))

    def duplicate_row_count(self, subset: Sequence[str] | None = None) -> int:
        cols = [self._col(c) for c in subset] if subset else list(self.table.c)
        grouped = (
            select(func.count().label("c"))
            .select_from(self.table)
            .group_by(*cols)
            .having(func.count() > 1)
            .subquery()
        )
        total = self._scalar(select(func.coalesce(func.sum(grouped.c.c), 0)))
        return int(total)

    def count_not_in_set(self, column: str, allowed: Sequence[Any]) -> int:
        col = self._col(column)
        allowed = list(allowed)
        stmt = select(func.count()).select_from(self.table).where(col.is_not(None))
        if allowed:
            stmt = stmt.where(col.not_in(allowed))
        return int(self._scalar(stmt))

    def count_out_of_range(
        self, column: str, minimum: float | None = None, maximum: float | None = None
    ) -> int:
        col = self._col(column)
        if minimum is None and maximum is None:
            return 0
        val = cast(col, Float)
        stmt = select(func.count()).select_from(self.table).where(col.is_not(None))
        conds = []
        if minimum is not None:
            conds.append(val < minimum)
        if maximum is not None:
            conds.append(val > maximum)
        return int(self._scalar(stmt.where(_or(conds))))

    def count_regex_mismatch(self, column: str, pattern: str) -> int:
        col = self._col(column)
        matches = _regex_matches_expr(self.engine, col, pattern)
        stmt = (
            select(func.count())
            .select_from(self.table)
            .where(col.is_not(None))
            .where(not_(matches))
        )
        return int(self._scalar(stmt))

    # -- reconciliation primitives ------------------------------------------- #
    # These read distinct keys / a key->row map from the reference so a check
    # can compare two systems. They materialize the projected columns (not the
    # whole table); a same-engine pushdown optimization is future work.

    def distinct_values(self, column: str) -> set:
        col = self._col(column)
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(distinct(col)).where(col.is_not(None))
            ).fetchall()
        return {r[0] for r in rows}

    def key_map(self, key: str, columns) -> dict:
        kcol = self._col(key)
        cols = [self._col(c) for c in columns]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(kcol, *cols).where(kcol.is_not(None))
            ).fetchall()
        return {r[0]: tuple(r[1:]) for r in rows}


def _or(conds):
    """OR a list of SQLAlchemy conditions (at least one element)."""
    expr = conds[0]
    for c in conds[1:]:
        expr = expr | c
    return expr


def _regex_matches_expr(engine: Engine, col, pattern: str):
    """A dialect-correct boolean expression: does `col` FULLY match `pattern`?

    pandas and DuckDB use full-match semantics; we anchor the pattern so every
    dialect agrees. SQLite has no built-in REGEXP, so we register a Python one
    (the connection is per-run and cheap).
    """
    dialect = engine.dialect.name
    anchored = f"^(?:{pattern})$"

    if dialect in ("postgresql", "redshift"):
        return col.op("~")(anchored)
    if dialect in ("mysql", "mariadb"):
        return col.op("REGEXP")(anchored)
    if dialect == "sqlite":
        _register_sqlite_regexp(engine)
        return col.op("REGEXP")(anchored)
    raise NotImplementedError(
        f"regex checks are not yet wired for the '{dialect}' dialect; "
        "supported: postgresql/redshift, mysql/mariadb, sqlite "
        "(use the native DuckDBBackend for DuckDB)"
    )


_SQLITE_REGISTERED: set[int] = set()


def _register_sqlite_regexp(engine: Engine) -> None:
    """Teach a SQLite engine the REGEXP operator (once per engine)."""
    if id(engine) in _SQLITE_REGISTERED:
        return

    def _regexp(pattern: str, value: Any) -> bool:
        if value is None:
            return False
        return re.search(pattern, str(value)) is not None

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _rec):  # pragma: no cover - exercised via checks
        dbapi_conn.create_function("regexp", 2, _regexp)

    # Also register on any already-open pooled connection.
    raw = engine.raw_connection()
    try:
        raw.create_function("regexp", 2, _regexp)
    finally:
        raw.close()
    _SQLITE_REGISTERED.add(id(engine))
