# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Corroboration runs on any backend now.** New `fetch_columns(columns)` protocol
  primitive (pandas/DuckDB/SQLAlchemy, cross-engine parity tested) materializes
  *only the analyzed columns* — so the `corroboration` and `source_corroboration`
  checks work against DuckDB and any SQL warehouse, not just in-memory pandas.
  (It projects the needed columns rather than the whole table; pushing the robust
  statistics down as SQL aggregates is a future optimization for very large tables.)
- **Cross-source corroboration** — a new `source_corroboration` check (+
  `source_corroboration_flags()`) that answers *"do 2+ sources agree?"*. For each
  outlier in the primary, it looks up the join key in a **reference source** and
  passes the value only if that independent feed confirms it within `rel_tol`;
  a spike missing from or contradicted by the other source is surfaced. Built as
  a reconciliation-style check (resolves a named `reference:` at run time), so it
  reuses the cross-system machinery. Pandas-first; warehouse pushdown on the
  roadmap.
- **`trueset annotate` CLI** — the annotate-and-flow model from the command line:
  scores every row (`_trueset_quality` + `_trueset_flags`) and keeps them all
  (nothing blocked), prints the lowest-quality rows, and writes a scored CSV with
  `--out`. Supports `--key` + `--adjudications` to suppress human-approved flags.

## [0.2.0] - 2026-07-25

### Added
- **Ambiguity-aware validation (commodities-grade).** For data where an extreme
  value is often the *truth*, not an error. Five capabilities, all deterministic:
  - **Corroboration** — a new `corroboration` check + `corroboration_flags()`:
    judge a suspicious value against *supporting signals* (does volume back the
    price spike? does a second source agree?), not in isolation. A real spike is
    corroborated and passes; a lone spike (the silent error) is surfaced.
  - **Annotate-and-flow** — `annotate(df, suite)` attaches a `_trueset_quality`
    score (0..1) and `_trueset_flags` to every row and lets them *flow* instead
    of blocking (market data needs a full view). Errors cost more than warnings.
  - **Adjudications** — `Adjudications` records human "actually valid" verdicts
    (auditable JSON) so future runs stop re-flagging them: the feedback loop that
    kills repeat false positives.
  - **Context-aware ranges** — `segment_bounds()` derives expected bands *per
    segment* (region/regime/season) so a legitimate seasonal spike isn't judged
    by a global threshold.
  - **Robust statistics** — `stats.py` (robust z-score / MAD, with a mean-AD
    fallback for flat-baseline spikes) gives thresholds a defensible statistical
    basis instead of a hand-picked number.

  Analytical checks now expose an optional `pandas_row_mask(df)` so corroboration
  participates in `annotate()`/`split()`. In-memory (pandas) for now; warehouse
  pushdown is on the roadmap. See `examples/ambiguity_demo.py`.
- **Auto-calibrated thresholds (`suggest --calibrate`).** Stop hand-picking
  numbers: for numeric columns, `suggest` now proposes data-derived `in_range`
  bounds (from the 1st/99th percentiles, widened to clean integers so current
  data passes) and a row-count volume band, all as `warn` for you to review and
  commit — never auto-enforced. Off by default; the plain `suggest` output is
  unchanged. The profiler now records `numeric_p01`/`numeric_p99`. Note:
  calibration learns from the sample, so run it on known-good/representative data.

### Fixed
- `trueset.__version__` is now derived from the installed package metadata rather
  than a hardcoded string (it had drifted to `0.0.1` while packaging said 0.1.0),
  so the two can never disagree again.

## [0.1.0] - 2026-07-24

First public release — `pip install trueset`.

### Added
- **Core engine.** Portable `Backend` protocol (write a check once, run on any
  engine), single-source checks, `Suite`/`SuiteResult`, `warn`/`error` severities
  → exit codes, deterministic JSON-serializable results. pandas + DuckDB backends,
  proven identical. AI copilot (check *authoring* only, gated through
  `build_check`), deterministic profiler + `suggest`, and the CLI.
- **`SQLAlchemyBackend`** — one class turns any SQLAlchemy-supported database
  (Postgres, MySQL/MariaDB, SQLite, Snowflake, BigQuery, Redshift, …) into a
  first-class engine. Every check is pushed down as `SELECT count(*) … WHERE …`
  so full tables never leave the warehouse. Dialect-aware regex handling;
  proven identical to pandas via a cross-engine parity test (`test_sqlalchemy.py`).
- CLI can validate a live SQL table: `trueset run --url <sqlalchemy-url>
  --table <name> --checks <yml>`. `reconcile` accepts SQL for both the primary
  (`--url/--table`) and references (`--ref name=<url>::<table>`).
- **Real-Postgres parity, verified.** The "runs on any warehouse" claim is proven
  against an actual Postgres 16 (not just SQLite): a `tests/test_postgres.py`
  parity suite (skipped unless `TRUESET_PG_URL` is set) and a CI job against a
  Postgres service container — exercising the dialect-specific paths (`~` regex
  operator, casts, window functions).
- **Failing-row extraction + quarantine.** Checks expose a per-row `failure_spec()`
  and backends implement `failing_rows(spec, limit)` (pandas/DuckDB/SQLAlchemy,
  proven identical). `trueset.split(df, suite)` partitions a batch into clean and
  quarantined rows with per-row reasons (`bad_annotated()` adds a
  `_trueset_reasons` column). `trueset run … --quarantine bad.csv` writes failing
  rows to CSV. trueset still only *identifies*; the pipeline routes.
- **`metric` check** — validate an aggregate (sum/avg/min/max/count) `equals` a
  target within `tolerance`, or falls in a `min`/`max` range. Runs as a
  pushed-down aggregate via a new `aggregate` protocol primitive, proven identical
  across pandas/DuckDB/SQLAlchemy.
- **Monitoring.** New `freshness` check (newest timestamp within `max_age_hours`,
  via a new `max_value` primitive). New `trueset monitor` command + generalized
  anomaly detection: trend *any* metric (`--metric rows|failing_rows|total_rows`,
  `--check`/`--column`) with `zscore` or robust `mad` detectors over run history.
- **Results-history persistence** (`ResultStore`, needs `[sql]`). Persist every
  run to any SQLAlchemy database as an auditable trail: `trueset run … --save
  <url>` and `trueset history --store <url>`.
- **Governance layer** (additive). Any check may carry `owner` / `sensitivity` /
  `regulation` / `tags` / `description`; `split_meta` separates these in
  `build_check`, they ride onto every `CheckResult` and serialize into evidence.
  New `trueset report --by {sensitivity|owner|regulation}`.
- **Data classification.** The profiler infers a suggested `sensitivity` (pii/pci)
  for high-precision patterns — email, phone, US SSN, credit card (Luhn), IBAN —
  and `suggest` pre-tags drafted checks. Suggestions for human review; never
  auto-applied.
- **dbt interop.** `trueset import-dbt --schema schema.yml [--model X]` converts
  dbt column tests into a runnable trueset suite (`accepted_values`→`in_set`,
  `relationships`→`referential_integrity`, severity preserved). Unmappable tests
  are reported, not silently dropped.
- `py.typed` marker; GitHub composite Action (`action.yml`); packaging metadata
  (project URLs, trove classifiers, keywords); `SuiteLoadError` with actionable
  messages so the CLI reports bad YAML / missing files / invalid specs cleanly.

### Changed
- `value_parity` now detects and reports **duplicate keys** on either side. A
  repeated join key previously collapsed silently (last-write-wins); it is now
  surfaced in `observed` (`duplicate_keys_primary` / `duplicate_keys_reference`)
  and counted as a failure, and the message is itemized to the failure modes that
  actually occurred.
