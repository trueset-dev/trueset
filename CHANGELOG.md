# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `py.typed` marker so downstream projects get type information when they import assay.
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
