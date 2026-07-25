# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  calibration learns from the sample, so run it on known-good/representative
  data. (First layer of the roadmap's auto-thresholds; history- and
  segment-calibrated thresholds are next.)
- **Real-Postgres parity, verified.** The "runs on any warehouse" claim is now
  proven against an actual Postgres 16 (not just SQLite): a `tests/test_postgres.py`
  parity suite (skipped unless `TRUESET_PG_URL` is set) and a CI job that runs it
  against a Postgres service container — exercising the dialect-specific paths
  (`~` regex operator, casts, window functions).
- **Failing-row extraction + quarantine.** Checks expose a per-row `failure_spec()`
  and backends implement `failing_rows(spec, limit)` (pandas/DuckDB/SQLAlchemy,
  proven identical). `trueset.split(df, suite)` partitions a batch into clean and
  quarantined rows with per-row reasons (`bad_annotated()` adds a
  `_trueset_reasons` column) — for dead-letter / quarantine routing at ingestion.
  Only `error`-severity checks divert rows by default (`include_warnings=True` to
  opt in). `trueset run --data … --quarantine bad.csv` writes failing rows to CSV.
  trueset still only *identifies* the bad rows; the pipeline routes them.
- **`metric` check** — validate an aggregate (sum/avg/min/max/count) `equals` a
  target within `tolerance`, or falls in a `min`/`max` range. For metrics/report
  validation ("total revenue ≈ X", "avg order value in [10, 100]"). Runs as a
  pushed-down aggregate via a new `aggregate` protocol primitive, proven
  identical across pandas/DuckDB/SQLAlchemy.
- **Generalized anomaly detection.** `trueset monitor` can now trend *any* metric,
  not just row volume: `--metric rows|failing_rows|total_rows` with `--check`/
  `--column` to watch a specific check's failing-row trend. Two deterministic
  detectors via `--method`: `zscore` (mean/std) and `mad` (median-absolute-
  deviation, robust to past outliers). `ResultStore.metric_history()` reads any
  metric from existing history — no schema change.
- **dbt interop.** `trueset import-dbt --schema schema.yml [--model X]` converts
  dbt column tests into a runnable trueset suite: `not_null`/`unique` map
  directly, `accepted_values`→`in_set`, `relationships`→`referential_integrity`;
  dbt test severity is preserved; both `tests:` and `data_tests:` keys and dbt
  `sources` are supported. Unmappable/custom dbt tests are reported (not silently
  dropped) and every produced check is validated through `build_check`. Adopt
  trueset without rewriting your existing tests.
- **Data classification.** The profiler now infers a suggested `sensitivity`
  (pii/pci) for high-precision patterns — email, phone, US SSN, credit card
  (length + Luhn, incl. bare-integer columns), IBAN. `trueset profile` shows a
  sensitivity column and `trueset suggest` pre-tags the drafted checks. These are
  *suggestions for human review* — trueset never auto-applies a classification.
- **Monitoring.** New `freshness` check — the newest value in a timestamp column
  must be within `max_age_hours` of now (catches stale pipelines); runs on every
  backend via a new `max_value` protocol primitive, proven identical across
  pandas/DuckDB/SQLAlchemy. New `trueset monitor` command + `volume_anomaly()`
  flag a sudden drop/spike in row volume vs the baseline of past runs (reads the
  results store), exiting non-zero on an anomaly for CI.
- **Results-history persistence** (`ResultStore`, needs `[sql]`). Persist every
  run to any SQLAlchemy database (SQLite → Postgres/Snowflake) as an auditable
  trail: `trueset run … --save <url>` and `trueset history --store <url>`. Two
  tables (`trueset_runs`, `trueset_results`) keep run verdicts, counts, row
  volume, and full per-check evidence (observed + governance metadata).
- **Governance layer** (additive, non-breaking). Any check may carry optional
  `owner` / `sensitivity` / `regulation` / `tags` / `description`. `split_meta`
  separates these from check kwargs in `build_check`, they ride onto every
  `CheckResult`, and serialize into JSON evidence when set. New `trueset report
  --by {sensitivity|owner|regulation}` groups pass/fail by policy dimension and
  flags failing checks on sensitive (pii/pci/phi/confidential) data. Sensitivity
  is validated against `public<internal<confidential<pii<pci<phi`.
- **`SQLAlchemyBackend`** — one class turns any SQLAlchemy-supported database
  (Postgres, MySQL/MariaDB, SQLite, Snowflake, BigQuery, Redshift, …) into a
  first-class engine. Every check is pushed down as `SELECT count(*) … WHERE …`
  so full tables never leave the warehouse. Dialect-aware regex handling;
  proven identical to pandas via a cross-engine parity test (`test_sqlalchemy.py`).
- CLI can now validate a live SQL table: `trueset run --url <sqlalchemy-url>
  --table <name> --checks <yml>`. `reconcile` accepts SQL for both the primary
  (`--url/--table`) and references (`--ref name=<url>::<table>`), so you can
  reconcile a warehouse against a source database directly.
- `py.typed` marker so downstream projects get type information when they import trueset.
- GitHub composite Action (`action.yml`) — add data-quality gates to any CI in a few lines.
- Packaging metadata: project URLs, trove classifiers, expanded keywords.
- `SuiteLoadError` with actionable messages; the CLI now reports bad YAML, missing
  files, and invalid check specs cleanly instead of raising a traceback.

### Changed
- `value_parity` now detects and reports **duplicate keys** on either side. A
  repeated join key previously collapsed silently (last-write-wins); it is now
  surfaced in `observed` (`duplicate_keys_primary` / `duplicate_keys_reference`)
  and counted as a failure, because an ambiguous join is a reconciliation defect.
- `value_parity` reports a clean, itemized message listing only the failure modes
  that actually occurred.

## [0.1.0]
First tagged pre-release. Core engine, 8 single-source checks, 3 reconciliation
checks, pandas + DuckDB backends (proven identical), AI copilot, profiler, CLI.
