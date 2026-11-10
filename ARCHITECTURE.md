# Architecture

A map for contributors. If you read one thing before touching the code, read
this — it explains the single bet the whole project is built on.

## The core bet, in one paragraph

A data-quality check (`not null`, `in range`, `values match another system`)
should be written **once** and run **anywhere** — on a pandas DataFrame in a
unit test, on DuckDB locally, or pushed down as SQL inside Snowflake / BigQuery /
Databricks / Postgres / Redshift. The way we get that: **a check never touches
pandas or SQL directly.** It only calls a tiny set of primitive operations
defined by the `Backend` protocol. To support a new engine you implement *one*
class; you do not rewrite a single check. Everything else in the repo is layers
on top of that seam.

## Request flow

```
checks.yml / CLI args / Python
        │
        ▼
   Suite  ──loads & validates──►  [ Check, Check, Check, … ]
        │                               │  each check calls only…
        │                               ▼
        │                         Backend protocol  ◄── one of:
        │                           • PandasBackend
        │                           • DuckDBBackend
        │                           • SQLAlchemyBackend  (pushes down as SQL)
        ▼                               │
   SuiteResult  ◄── CheckResult ×N ─────┘
        │
        ├─► exit code (CI gate)      ├─► ResultStore (history, --save)
        ├─► split() → quarantine     └─► dashboard (the Data Trust view)
```

A check's job is only to **identify** good vs. bad. Routing bad rows
(dead-letter, block, alert) is the caller's job. Remembering results across many
runs and teams is the Hub's job. Keeping those three concerns separate is what
keeps the engine small and composable — see *Boundaries* below.

## The one seam: the `Backend` protocol

`src/trueset/backends/base.py` is the most important file in the repo. It is a
small, deliberately boring `Protocol`:

| Primitive | Answers |
|---|---|
| `columns()` / `row_count()` | shape |
| `null_count(col)` | completeness |
| `distinct_count(col)` / `duplicate_row_count(subset)` | uniqueness |
| `count_not_in_set(col, allowed)` | validity (enums) |
| `count_out_of_range(col, min, max)` | validity (numeric) |
| `count_regex_mismatch(col, pattern)` | validity (format) |
| `max_value(col)` | freshness (newest timestamp) |
| `aggregate(func, col)` | the `metric` check (sum/avg/min/max/count) |
| `failing_rows(spec, limit)` | quarantine — the actual rows that failed |
| `fetch_columns(cols)` | analytical checks that need a distribution, not a count (projects only those columns) |

**Rule:** only add a primitive here if *several* checks share it. Every method
added is a method every future backend must implement.

The three implementations (`pandas_backend.py`, `duckdb_backend.py`,
`sqlalchemy_backend.py`) each satisfy this protocol and are proven to agree with
each other (see *The parity invariant*). `SQLAlchemyBackend` is the important
one for the product story: it turns each primitive into a
`SELECT count(*) … WHERE …`, so the full table never leaves the warehouse.

## Module map

| File | Responsibility |
|---|---|
| `backends/base.py` | **The `Backend` protocol** — the seam. |
| `backends/{pandas,duckdb,sqlalchemy}_backend.py` | The three engines. |
| `checks.py` | `Check` base class, the `type:` → check registry, and the single-table checks. |
| `suite.py` | `Suite` / `SuiteResult`, YAML loading, `SuiteLoadError`. |
| `result.py` | `CheckResult`, `Severity`, `Status`, JSON-serializable evidence. |
| `reconcile.py` | Cross-system checks: `value_parity`, `row_count_parity`, `referential_integrity`. |
| `ambiguity.py` | Corroboration, `annotate()`, adjudications, per-segment bounds (pandas-first). |
| `stats.py` | Robust statistics (z-score / MAD) that give thresholds a defensible basis. |
| `monitoring.py` | `detect_anomaly`, `volume_anomaly`, freshness — trend a metric over run history. |
| `history.py` | `ResultStore` — persist every run to any SQLAlchemy DB (needs `[sql]`). |
| `governance.py` | `GovernanceMeta` + `split_meta`: owner / sensitivity / regulation / tags on any check. |
| `profile.py` | Deterministic profiler, `suggest` drafts, PII/PCI classification. |
| `interop.py` | dbt import: convert a dbt `schema.yml` into a runnable trueset suite. |
| `quarantine.py` | `split(df, suite)` → clean / bad DataFrames with per-row reasons. |
| `dashboard.py` | The self-contained "Data Trust" HTML view over `ResultStore`. |
| `copilot.py` | AI **check authoring** only — gated through `build_check`, never in the pass/fail path. |
| `cli.py` | The `trueset` command (Click). |

## The parity invariant

> Every backend must produce the **same verdict** as pandas for the same data
> and the same suite.

This is non-negotiable and it is what makes "runs anywhere" true rather than
aspirational. A new backend is not done until it has a cross-engine parity test
(`tests/test_duckdb.py`, `tests/test_sqlalchemy.py`, and a real-Postgres suite in
`tests/test_postgres.py`, skipped unless `TRUESET_PG_URL` is set). If you add a
`Backend` primitive, you extend the parity tests too.

## Extension points

### Add a check (the common case)

1. Subclass `Check` in `checks.py`; set a stable `type` string (used as YAML
   `type:` and in results).
2. Implement `evaluate(backend) -> CheckResult`, calling **only** `Backend`
   primitives. Use the `_fail_if_missing` and `_result` helpers so the subclass
   stays tiny. If none of the existing primitives can express your check, add
   one to `backends/base.py` *and all three backends* (and the parity tests).
3. If the check fails per-row (so rows can be quarantined), implement
   `failure_spec()` to return a small engine-agnostic predicate. Dataset-level
   and cross-system checks return `None`.
4. Register it so YAML can find it, and add a test. Done.

### Add a backend (the high-value case)

1. Create `backends/<engine>_backend.py` with a class satisfying the `Backend`
   protocol. Set `name`.
2. Wire an optional import in `__init__.py` (guarded, like `DuckDBBackend`), so a
   missing dependency degrades gracefully instead of breaking `import trueset`.
3. **Add a parity test** asserting it agrees with pandas on the example suites.
   This is the acceptance criterion.

### Add an integration

Integrations live at the edges (`interop.py` for dbt, `action.yml` for GitHub
Actions, `cli.py` exit codes for any orchestrator). An integration should
*translate into* the engine (import other tools' tests, emit results other tools
consume) — it should not pull orchestration or lineage *into* the engine.

## Boundaries (what trueset is **not**)

Holding these lines is how the project stays defensible instead of sprawling:

- **The engine identifies; the pipeline routes.** trueset finds the bad rows and
  hands them back (`split`/`--quarantine`). It does not move, block, or
  orchestrate data.
- **It is not an ETL tool or an orchestrator.** It runs *inside* Airflow / dbt /
  CI, it does not replace them.
- **It composes with catalogs; it does not rebuild lineage.** Lineage and
  cataloging are a different product.
- **The local dashboard is a read-only view** over `ResultStore`. Multi-team,
  hosted, alerting, SSO — that is the Hub, built *on* this data, not inside the
  engine.
- **No LLM in the pass/fail path.** The copilot authors checks; only
  deterministic, registry-validated checks run against data.

If a change blurs one of these lines, it probably belongs in a different layer —
raise it in an issue first.
