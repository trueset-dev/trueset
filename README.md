# trueset

[![CI](https://github.com/trueset-dev/trueset/actions/workflows/ci.yml/badge.svg)](https://github.com/trueset-dev/trueset/actions/workflows/ci.yml)

**Write a data-quality check once, run it anywhere** — pandas today, PySpark and
your warehouse next. One declarative check language, one Python API, one CLI.

Data quality tools today force a trade-off: `dbt` tests are SQL-only, Great
Expectations is powerful but heavy, and each engine (pandas / Spark / SQL) tends
to want its own syntax. `trueset` bets on a single small **Backend protocol** — a
check is written once and runs unchanged on any engine that implements the
protocol. Adding Spark or Snowflake support means writing *one class*, not
re-authoring a single check.

## Quickstart

```bash
# From source (PyPI release coming — the name is being finalized):
git clone https://github.com/trueset-dev/trueset && cd trueset
pip install -e ".[sql]"          # [sql] adds the DuckDB backend; omit for pandas-only

trueset run --data examples/orders.csv --checks examples/checks.yml
trueset list-checks
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
from trueset import Suite, validate_dataframe

df = pd.read_csv("orders.csv")
result = validate_dataframe(df, "checks.yml")

print(result.passed)                    # False
print(result.to_dict())                 # JSON-ready, ship to a warehouse/dashboard
```

The CLI exits non-zero when any `error`-severity check fails, so it drops
straight into CI, dbt, or Airflow.

## Use it anywhere in your pipeline (not just the warehouse)

trueset is a **library first**. Because checks only speak to the `Backend`
protocol and the pandas backend takes any DataFrame, you can validate data
*in flight* — at ingestion, before loading — and fail the pipeline the instant a
batch is bad, so garbage never reaches storage (the "shift-left" pattern):

```python
from trueset import validate_dataframe

df = extract_from_api()                        # your ingestion step
result = validate_dataframe(df, "checks.yml")  # same suite, in-memory
if not result.passed:
    raise ValueError(f"bad batch, not loading: {result.counts}")   # fail the task
load_to_warehouse(df)                          # only reached if data is clean
```

Drop that into an Airflow `PythonOperator`, a Dagster op, a Prefect task, a
Lambda, or a plain script. The *same* `checks.yml` then runs post-load against
the warehouse (`SQLAlchemyBackend`) and in CI (the Action) — write once, enforce
at ingestion, in transit, and at rest. See
[`examples/pipeline_demo.py`](examples/pipeline_demo.py) for a runnable gate.
(Batch / micro-batch oriented; native Spark validation is on the roadmap.)

## Gate your CI in three lines

trueset ships a GitHub Action, so a data-quality check becomes a required status
check on every pull request:

```yaml
# .github/workflows/data-quality.yml
name: data-quality
on: [pull_request]
jobs:
  trueset:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: trueset-dev/trueset@v0
        with:
          data: data/orders.csv
          checks: quality/orders.yml
```

The job fails the moment an `error`-severity check fails. Use `severity: warn` on
a check to surface a problem without blocking the merge.

## Profiling & AI-assisted authoring

Draft a check suite instead of writing one by hand:

```bash
trueset profile  --data orders.csv                 # stats + inferred semantic types
trueset suggest  --data orders.csv                 # deterministic draft suite (no AI)
trueset suggest  --data orders.csv --ai --out checks.yml           # AI copilot
trueset suggest  --data orders.csv --describe "amount can't be negative; \
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
from trueset import profile_dataframe, suggest_from_profile
from trueset.copilot import anthropic_completer, checks_from_profile

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
tables never move. `tests/test_duckdb.py` asserts the two engines agree.

## Run against your warehouse (Postgres, Snowflake, BigQuery, …)

The `SQLAlchemyBackend` generalizes the DuckDB proof to **anything SQLAlchemy
speaks** — Postgres, MySQL/MariaDB, SQLite, Snowflake, BigQuery, Redshift. Same
checks, same verdicts, pushed down as SQL. Point the CLI straight at a table:

```bash
trueset run \
  --url "postgresql+psycopg://user:pw@host:5432/analytics" \
  --table public.orders \
  --checks quality/orders.yml
```

Or from Python:

```python
from sqlalchemy import create_engine
from trueset import Suite, SQLAlchemyBackend

engine = create_engine("snowflake://…")          # any SQLAlchemy URL
backend = SQLAlchemyBackend(engine, "ORDERS")
result = Suite.from_yaml("orders.yml").run(backend)
```

`tests/test_sqlalchemy.py` runs the identical example suite on pandas **and** on
a SQL database and asserts the verdicts match — the same guarantee we hold for
DuckDB, now for every warehouse. Reconciliation works across engines too: the
primary can be a pandas DataFrame while the reference is a Postgres table.

## Cross-system reconciliation (the wedge)

The thing no single-source tool (GE, Soda, Pandera, dbt tests) is architected
to do, and whose only open-source option (`data-diff`) was archived in 2024:
validate one dataset **against another system**. Because checks talk only to
the `Backend` protocol, a reconciliation check just holds a second backend --
which can be a totally different engine.

```bash
trueset reconcile \
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

`value_parity` reports four failure modes at once: mismatched values on shared
keys, keys only in the primary, keys only in the reference, and **duplicate join
keys** on either side (an ambiguous join is itself a reconciliation defect).
Either side can be a file, DuckDB, or any SQLAlchemy warehouse — they need not
share an engine.

## Governance: enforcement + evidence

trueset isn't a catalog (that's DataHub/Collibra territory). It owns the half
catalogs are weak on — **enforcing** policy and **proving** compliance happened.
Governance is optional metadata on a check, nothing more:

```yaml
- type: matches_regex
  column: email
  pattern: '[^@\s]+@[^@\s]+\.[^@\s]+'
  owner: risk-team              # accountable party
  sensitivity: pii              # public|internal|confidential|pii|pci|phi
  regulation: [gdpr, ccpa]      # regime tags
  description: "Customer email is PII and must be well-formed"
```

These fields change nothing about how the check runs — they ride onto the result
as machine-readable, auditable evidence. `trueset report` then answers policy
questions directly:

```bash
trueset report --data orders.csv --checks governed.yml --by sensitivity
```

```
 governance report :: orders_quality_governed  (by sensitivity)
┏━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━━┓
┃ sensitivity  ┃ checks ┃ pass ┃ fail ┃ error ┃ status    ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━━┩
│ pii          │ 1      │ 0    │ 1    │ 0     │ VIOLATION │
│ confidential │ 2      │ 0    │ 2    │ 0     │ VIOLATION │
└──────────────┴────────┴──────┴──────┴───────┴───────────┘
⚠ 3 failing check(s) on sensitive (pii/pci/phi/confidential) data.
```

Group `--by owner` to route failures to a team, or `--by regulation` for a GDPR
/ SOX posture. `--json` emits the same as auditable evidence for a compliance
trail.

**Classification is suggested, never imposed.** `trueset profile` infers a
`sensitivity` for high-precision patterns (email, phone, SSN, credit card via
Luhn, IBAN), and `trueset suggest` pre-tags the drafted checks:

```
column   inferred   sensitivity
email    email      pii
ssn      ssn        pii
card     credit_card pci
```

Both the deterministic profiler and the AI copilot only *suggest* tags — like
every check, they are reviewed and committed by a human, never auto-applied.

## Monitoring: freshness & volume

Turn one-shot validation into continuous monitoring. Persist runs, then watch for
staleness and volume drift:

```bash
trueset run --url "postgresql://…" --table orders --checks orders.yml --save "postgresql://…/trueset_history"
trueset history --store "postgresql://…/trueset_history"      # the audit trail
trueset monitor --store "postgresql://…/trueset_history" --suite orders_quality --sigma 3
```

- **`freshness`** is an ordinary check — the newest timestamp must be recent:
  ```yaml
  - type: freshness
    column: created_at
    max_age_hours: 6        # fail if the table hasn't updated in 6 hours
  ```
- **`trueset monitor`** trends any metric against the baseline of past runs and
  exits non-zero on a >`sigma` anomaly — a silent 90% drop in rows is caught even
  when every row that *is* there passes every check:
  ```bash
  trueset monitor --store "$H" --suite orders --metric rows --method mad
  trueset monitor --store "$H" --suite orders --metric failing_rows --check not_null --column email
  ```
  `--metric` can be `rows`, `failing_rows`, or `total_rows` (with `--check`/
  `--column` to pick a check); `--method` is `zscore` (mean/std) or `mad`
  (median-absolute-deviation — robust when a few past runs were themselves
  outliers). Detection is deterministic and explainable — never a black box.

## Works with your stack (dbt today)

trueset composes with the tools you already run — it doesn't replace them. If you
have dbt tests, adopt trueset **without rewriting a single one**:

```bash
trueset import-dbt --schema models/schema.yml --model orders --out orders.yml
trueset run --url "$WAREHOUSE" --table analytics.orders --checks orders.yml
```

`not_null`/`unique` map directly, `accepted_values`→`in_set`,
`relationships`→`referential_integrity`, and dbt test severity is preserved.
Custom/singular dbt tests are reported (never silently dropped), and every
imported check is validated so the output always runs. Point trueset at the
tables dbt builds and you also get cross-engine portability, reconciliation
against the source, governance, and monitoring — on top of your existing tests.

## Built-in checks

`columns_exist`, `not_null`, `unique`, `in_set`, `in_range`, `matches_regex`,
`row_count`, `no_duplicate_rows`, `freshness`, `metric`, plus the reconciliation
checks `row_count_parity`, `referential_integrity`, `value_parity`. Each has a
`severity` of `error` (default) or `warn`.

## Architecture

```
YAML / Python API
        │
     Suite ── list of ── Check          checks speak ONLY to the Backend
        │                  │            protocol, never to an engine
        ▼                  ▼
   SuiteResult  ◀──  Backend protocol
                          ▲
        ┌────────────┬───────┴───────┬────────────┐
   PandasBackend  DuckDBBackend  SQLAlchemyBackend  (SparkBackend)
     [built]        [built]     [built: any warehouse]  [next]
```

The `Backend` protocol (`src/trueset/backends/base.py`) is deliberately tiny:
`row_count`, `null_count`, `distinct_count`, `count_out_of_range`, etc. A SQL
backend implements each as a pushed-down `SELECT count(*) ... WHERE ...` so data
never leaves the warehouse.

## Roadmap

- [x] **Backends**: pandas, DuckDB, and SQLAlchemy (any warehouse).
- [ ] **Governance**: `owner`/`sensitivity`/`regulation` metadata + policy reports.
- [ ] **Results sink**: write run history to a table for trend/anomaly monitoring.
- [ ] **Freshness & volume** checks for pipeline monitoring.
- [ ] **Interop**: import dbt tests + Great Expectations / Soda suites.
- [ ] **Backends**: PySpark.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0 (recommended for broad corporate adoption).
