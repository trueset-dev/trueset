# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
