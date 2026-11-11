# Backends & warehouses

The core bet: **write a check once, run it on any engine.** A check never touches
pandas, DuckDB, or SQL directly — it only calls a small `Backend` protocol. To
support a new engine you implement one class; not a single check is rewritten.

## Available backends

| Backend | Use it for | Extra |
|---------|-----------|-------|
| `PandasBackend` | in-memory DataFrames (pipelines, tests) | — |
| `DuckDBBackend` | local/embedded SQL, Parquet | `[sql]` |
| `SQLAlchemyBackend` | Postgres, MySQL/MariaDB, SQLite, Snowflake, BigQuery, Redshift, … | `[sql]` |

On the SQL backends, **single-table checks** are pushed down as
`SELECT count(*) … WHERE …` executed inside the database — those tables never
move across the wire.

!!! note "Two honest limits"
    - **Cross-system reconciliation:** when both sides share one database,
      `value_parity` and `referential_integrity` push down as SQL (inner join +
      anti-joins) — nothing is materialized. Across *different* engines (what
      makes CSV-vs-warehouse checks possible), they compare the **key + compared
      columns** in memory; cross-engine hashing to avoid that is on the
      [roadmap](https://github.com/trueset-dev/trueset/blob/main/ROADMAP.md).
    - **Regex pushdown** (`matches_regex`) is wired for Postgres, Redshift,
      MySQL/MariaDB and SQLite. Other dialects (e.g. Snowflake, BigQuery) raise a
      clear "not yet wired" error for that one check type; everything else runs.

## Run against your warehouse

```bash
trueset run --url "postgresql://user:pass@host:5432/db" --table orders --checks checks.yml
```

From Python:

```python
from sqlalchemy import create_engine
from trueset import Suite
from trueset.backends.sqlalchemy_backend import SQLAlchemyBackend

engine = create_engine("postgresql+psycopg://…")
result = Suite.from_yaml("checks.yml").run(SQLAlchemyBackend(engine, "orders"))
```

## Portability, proven

The whole thesis is tested, not asserted. The identical suite, run on pandas
(in-memory) and on DuckDB (SQL pushed into the database), returns the same verdict
— and the cross-engine parity is enforced in CI, including against a **real
Postgres 16** (exercising the dialect-specific paths: the `~` regex operator,
casts, window functions).

```
check                   pandas      duckdb      match
------------------------------------------------------
row_count_parity        pass(0)     pass(0)     OK
referential_integrity   fail(1)     fail(1)     OK
value_parity            fail(3)     fail(3)     OK
```

## Adding a backend

Implement every method in `backends/base.py` (mirror `duckdb_backend.py`), then add
a cross-engine parity test asserting it agrees with pandas on the example suites.
That's the entire contribution — no check changes. See
[CONTRIBUTING](https://github.com/trueset-dev/trueset/blob/main/CONTRIBUTING.md).
