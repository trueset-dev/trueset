# trueset

**Catch the data problems every other check misses.**

`dbt` tests, Great Expectations, and Soda all validate one table in isolation.
They can't see the failures that matter most: a value that silently changed
*between* two systems, or an extreme reading that's either a real event or an
expensive error. trueset is built for exactly those — and every check is written
once and runs on any engine (pandas, DuckDB, or your warehouse as pushed-down SQL).

```bash
pip install trueset
```

## The two things trueset does that single-table tools can't

<div class="grid cards" markdown>

- **Cross-system reconciliation** — validate one dataset *against another system*.
  Did the warehouse match the source after the load? The one capability GE / Soda /
  dbt tests aren't architected for. → [Guide](guides/reconciliation.md)

- **Corroboration** *(newer)* — when an extreme value is often the *truth*, not an
  error, judge it against supporting signals instead of a fixed threshold.
  → [Guide](guides/ambiguity.md)

</div>

## Everything trueset ships

| Area | What you get |
|------|--------------|
| [Checks](guides/checks.md) | `not_null`, `unique`, `in_set`, `in_range`, `matches_regex`, `row_count`, `no_duplicate_rows`, `columns_exist`, `metric` |
| [Reconciliation](guides/reconciliation.md) | `row_count_parity`, `referential_integrity`, `value_parity` — cross-system, cross-engine |
| [Ambiguity](guides/ambiguity.md) | `corroboration`, `source_corroboration`, `annotate`, `Adjudications`, `segment_bounds`, robust MAD stats |
| [Backends](guides/backends.md) | one check on pandas, DuckDB, or any SQLAlchemy warehouse — verified identical, incl. real Postgres |
| [Pipelines](guides/pipelines.md) | validate at ingestion / in-flight / post-load; quarantine bad rows to a dead-letter sink |
| [Governance](guides/governance.md) | `owner`/`sensitivity`/`regulation`/`tags`; `report --by`; PII/PCI classification |
| [Monitoring](guides/monitoring.md) | `freshness`, volume/metric anomaly over run history, results persistence |
| [Authoring](guides/authoring.md) | `profile`, `suggest --calibrate`, AI copilot (drafts checks; never judges data) |

!!! info "One trust rule throughout"
    AI can *author* and *explain* checks; only deterministic, auditable code ever
    decides pass/fail. Your validation stays reproducible and audit-ready.

Ready? → **[Getting started](getting-started.md)**
