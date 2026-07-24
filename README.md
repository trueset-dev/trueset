# assay

[![CI](https://github.com/YOUR_ORG/assay/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/assay/actions/workflows/ci.yml)

> Working name — trivially renameable. Candidates: assay, touchstone, litmus, aegis.

**Write a data-quality check once, run it anywhere** — pandas today, PySpark and
your warehouse next. One declarative check language, one Python API, one CLI.

Data quality tools today force a trade-off: `dbt` tests are SQL-only, Great
Expectations is powerful but heavy, and each engine (pandas / Spark / SQL) tends
to want its own syntax. `assay` bets on a single small **Backend protocol** — a
check is written once and runs unchanged on any engine that implements the
protocol. Adding Spark or Snowflake support means writing *one class*, not
re-authoring a single check.

## Quickstart

```bash
pip install -e ".[dev]"          # from source, for now

assay run --data examples/orders.csv --checks examples/checks.yml
assay list-checks
```

Declarative checks (`checks.yml`):

```yaml
suite: orders_quality
checks:
  - type: not_null
    column: order_id
  - type: unique
    column: order_id
  - type: in_range
    column: amount
    min: 0
  - type: in_set
    column: status
    values: [pending, shipped, delivered, cancelled]
  - type: matches_regex
    column: email
    pattern: '[^@\s]+@[^@\s]+\.[^@\s]+'
    severity: warn        # warns, doesn't fail the run
```

Or the Python API:

```python
import pandas as pd
from assay import Suite, validate_dataframe

df = pd.read_csv("orders.csv")
result = validate_dataframe(df, "checks.yml")

print(result.passed)                    # False
print(result.to_dict())                 # JSON-ready, ship to a warehouse/dashboard
```

The CLI exits non-zero when any `error`-severity check fails, so it drops
straight into CI, dbt, or Airflow.

## Profiling & AI-assisted authoring

Draft a check suite instead of writing one by hand:

```bash
assay profile  --data orders.csv                 # stats + inferred semantic types
assay suggest  --data orders.csv                 # deterministic draft suite (no AI)
assay suggest  --data orders.csv --ai --out checks.yml           # AI copilot
assay suggest  --data orders.csv --describe "amount can't be negative; \
    status is one of pending/shipped/delivered/cancelled"        # English -> checks
```

**The trust rule that makes AI safe here:** the copilot only ever *authors*
checks. Every spec it returns — from profiling or natural language — is passed
through the same deterministic check registry (`build_check`). Anything the
model hallucinates or mis-configures is discarded before it can reach your
data. The AI is never in the runtime pass/fail path, so your validation stays
deterministic and auditable. The model is injected as a plain callable
(`Completer`), so it's provider-agnostic and fully testable without a key.

```python
from assay import profile_dataframe, suggest_from_profile
from assay.copilot import anthropic_completer, checks_from_profile

prof = profile_dataframe(df)
draft = suggest_from_profile(prof)                      # deterministic
draft = checks_from_profile(prof, anthropic_completer())  # AI (needs ANTHROPIC_API_KEY)
```

## Portability, proven (pandas ⇄ DuckDB)

The whole bet is that a check is written once and runs on any engine. It's not
a slogan -- it's tested. The identical suite, run on pandas (in-memory) and on
DuckDB (SQL pushed into the database), returns the same verdict:

```
check                   pandas      duckdb      match
------------------------------------------------------
row_count_parity        pass(0)     pass(0)     OK
referential_integrity   fail(1)     fail(1)     OK
value_parity            fail(3)     fail(3)     OK
------------------------------------------------------
identical verdict: True
```

```bash
pip install -e ".[sql]"                 # adds duckdb
python examples/portability_demo.py     # runs the comparison above
```

The DuckDB backend implements the same `Backend` protocol, but every check
becomes `SELECT count(*) ... WHERE ...` executed inside the database -- so full
tables never move. The same SQL shape extends to Postgres, Snowflake, and
BigQuery via SQLAlchemy. `tests/test_duckdb.py` asserts the two engines agree.

## Cross-system reconciliation (the wedge)

The thing no single-source tool (GE, Soda, Pandera, dbt tests) is architected
to do, and whose only open-source option (`data-diff`) was archived in 2024:
validate one dataset **against another system**. Because checks talk only to
the `Backend` protocol, a reconciliation check just holds a second backend --
which can be a totally different engine.

```bash
assay reconcile \
  --data   warehouse_orders.csv \
  --checks reconcile.yml \
  --ref    source=source_orders.csv
```

```yaml
suite: warehouse_vs_source
checks:
  - type: row_count_parity        # counts agree within tolerance
    reference: source
    tolerance: 0.0
  - type: referential_integrity   # every key traces back to the source
    column: order_id
    reference: source
    ref_column: id
  - type: value_parity            # join on key, compare actual values
    key: order_id
    columns: [amount, status]
    reference: source
    ref_key: id
```

`value_parity` reports three failure modes at once: mismatched values on shared
keys, keys only in the primary, and keys only in the reference. (Today both
sides load via pandas; the same checks drop straight onto a warehouse backend,
where they become pushed-down SQL / sampled checksums so full tables never move.)

## Built-in checks

`columns_exist`, `not_null`, `unique`, `in_set`, `in_range`, `matches_regex`,
`row_count`, `no_duplicate_rows`. Each has a `severity` of `error` (default) or
`warn`.

## Architecture

```
YAML / Python API
        │
     Suite ── list of ── Check          checks speak ONLY to the Backend
        │                  │            protocol, never to an engine
        ▼                  ▼
   SuiteResult  ◀──  Backend protocol
                          ▲
        ┌─────────────────┼─────────────────┐
   PandasBackend    (SparkBackend)     (SQLBackend)
     [built]          [next]             [next]
```

The `Backend` protocol (`src/assay/backends/base.py`) is deliberately tiny:
`row_count`, `null_count`, `distinct_count`, `count_out_of_range`, etc. A SQL
backend implements each as a pushed-down `SELECT count(*) ... WHERE ...` so data
never leaves the warehouse.

## Roadmap (proposed)

1. **Backends**: PySpark, then SQLAlchemy/warehouse (DuckDB, Snowflake, BigQuery).
2. **Interop**: import dbt tests + Great Expectations suites; emit dbt sources.
3. **Custom checks**: user-defined SQL / Python expressions.
4. **Results sink**: write run history to a table for trend/anomaly monitoring.
5. **Freshness & volume** checks for pipeline monitoring.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0 (recommended for broad corporate adoption).
