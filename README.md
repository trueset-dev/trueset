# trueset

[![CI](https://github.com/trueset-dev/trueset/actions/workflows/ci.yml/badge.svg)](https://github.com/trueset-dev/trueset/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/trueset.svg)](https://pypi.org/project/trueset/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Catch the data problems every other check misses.**

`dbt` tests, Great Expectations, and Soda all validate one table in isolation.
They can't see the failures that matter most: a value that silently changed
*between* two systems, or an extreme reading that's either a real event or a
$2.9M error. trueset is built for exactly those — and every check is written once
and runs on any engine (pandas, DuckDB, or your warehouse as pushed-down SQL).

```bash
pip install trueset
```

---

## Proof #1 — Cross-system reconciliation

The thing single-table tools aren't architected to do, and whose only OSS option
(`data-diff`) was archived in 2024: validate one dataset **against another
system**. Did the warehouse match the source after the load?

```bash
trueset reconcile --data warehouse.csv --checks reconcile.yml --ref source=source.csv
```
```yaml
suite: warehouse_vs_source
checks:
  - type: row_count_parity        # counts agree within tolerance
    reference: source
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

`value_parity` reports every failure mode at once — mismatched values on shared
keys, keys only in the primary, keys only in the reference, and duplicate keys.
Both sides can be *different engines* (a CSV vs a warehouse table), because a
check only ever talks to the `Backend` protocol. Runs pushed-down on the
warehouse — full tables never move.

## Proof #2 — Corroboration *(newer, experimental)*

When an extreme value is often the *truth*, not an error (a demand spike, a
market move), a fixed threshold can't tell signal from mistake. trueset judges a
suspicious value against **supporting signals** instead of in isolation:

```yaml
- type: corroboration
  column: price
  corroborate_with: [volume]      # trust the spike only if volume backs it
  severity: warn
- type: source_corroboration
  column: price
  key: date
  reference: source_b             # …or if a second independent feed agrees
```

A real move shows up in volume and in both feeds; a lone spike (the silent error)
gets surfaced. See [`examples/ambiguity_demo.py`](examples/ambiguity_demo.py).

---

## The full toolkit

trueset is more than the two proofs — everything below ships today:

| Area | What you get |
|------|--------------|
| **Checks** | `not_null`, `unique`, `in_set`, `in_range`, `matches_regex`, `row_count`, `no_duplicate_rows`, `columns_exist`, `metric` (aggregate validation) |
| **Reconciliation** | `row_count_parity`, `referential_integrity`, `value_parity` — cross-system, cross-engine |
| **Ambiguity** | `corroboration`, `source_corroboration`, `annotate` (per-row quality score + flow), `Adjudications` (review once, stop re-flagging), `segment_bounds` (context-aware ranges), robust MAD stats |
| **Portability** | one check runs on pandas, DuckDB, or any SQLAlchemy warehouse (Postgres/MySQL/Snowflake/BigQuery) — verified identical, incl. real Postgres |
| **Pipeline** | run at ingestion / in-flight / post-load; `split()` + `--quarantine` route bad rows to a dead-letter sink |
| **Governance** | `owner`/`sensitivity`/`regulation`/`tags` on any check; `report --by`; PII/PCI classification |
| **Monitoring** | `freshness` + `monitor` (volume/metric anomaly over run history); results persistence for an audit trail |
| **Authoring** | `profile`, `suggest` (+ `--calibrate` for data-derived thresholds), AI copilot (drafts checks; never judges data) |
| **Adopt & ship** | `import-dbt` (reuse existing dbt tests), a GitHub Action, `pip install trueset` |

**One trust rule throughout:** AI can *author* and *explain*; only deterministic,
auditable code ever decides pass/fail. Your validation stays reproducible.

## Write once, run anywhere

```python
from trueset import Suite, PandasBackend, validate_dataframe
result = validate_dataframe(df, "checks.yml")   # in a pipeline step
print(result.passed, result.to_dict())           # JSON-ready for CI / dashboards
```
The same `checks.yml` runs unchanged against a warehouse table
(`trueset run --url postgresql://… --table orders --checks checks.yml`) and in CI
(the Action). Exit code is non-zero on any `error`-severity failure.

## Learn more

- [ROADMAP.md](ROADMAP.md) — what's shipped, what's next, the idea inbox
- [CHANGELOG.md](CHANGELOG.md) · [examples/](examples/) · [CONTRIBUTING.md](CONTRIBUTING.md)

## License

Apache-2.0.
