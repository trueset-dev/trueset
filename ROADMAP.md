# trueset roadmap

The single source of truth for what's built, what's next, and every idea worth
remembering. **Got an idea? Don't lose it — drop it in the [Idea inbox](#idea-inbox)
below (or open a [feature request issue](../../issues/new?template=feature_request.md)).**
Nothing here is a promise; it's a living list we triage as real users test.

---

## ✅ Shipped (v0.1.0)

**Core engine**
- Portable `Backend` protocol — write a check once, run on any engine
- 12 checks: `columns_exist`, `not_null`, `unique`, `in_set`, `in_range`,
  `matches_regex`, `row_count`, `no_duplicate_rows`, `metric`, `freshness`,
  + 3 reconciliation checks (`row_count_parity`, `referential_integrity`, `value_parity`)
- Deterministic, JSON-serializable results; `warn`/`error` severities → exit codes

**Engines (backends)**
- pandas (in-memory), DuckDB, SQLAlchemy (Postgres/MySQL/… — pushed-down SQL)
- Verdicts proven identical across pandas ⇄ DuckDB ⇄ real Postgres

**Runs anywhere in the pipeline**
- Ingestion gate / in-flight / post-load; `split()` to quarantine bad rows
- `run --quarantine` writes failing rows to a dead-letter file

**Governance**
- `owner` / `sensitivity` / `regulation` / `tags` metadata on any check
- `trueset report --by {sensitivity|owner|regulation}`; PII/PCI classification

**Monitoring & history**
- `run --save` persists results; `trueset history`
- `trueset monitor` — freshness + volume/metric anomaly vs a historical baseline

**Authoring & interop**
- `trueset profile` + `suggest` (deterministic) + AI copilot (check *authoring* only)
- `trueset import-dbt` — adopt from dbt `schema.yml` without rewriting
- GitHub Action for CI; PyPI release automation (`pip install trueset`)

---

## 🔜 Next up (near-term, roughly ordered)

1. **Auto-calibrated thresholds** — stop making users hand-tune limits. See
   [Idea inbox](#idea-inbox); this is the top candidate.
2. **AI failure diagnosis** — explain *why* a check failed (root-cause hints on
   top of the deterministic result), building on run history. AI explains; it
   never decides pass/fail.
3. **Data contracts** — a named, versioned suite bound to a dataset with an
   `owner` + `sla` header. Reconciliation is already cross-system contract
   enforcement; this formalizes naming/versioning/ownership.
4. **More interop** — import Great Expectations + Soda suites (dbt already done).

## 🌅 Later / bigger bets

- **Spark backend** — native validation of a Spark DataFrame in-cluster.
- **More warehouse coverage** — Snowflake / BigQuery dialect tests (code path
  exists via SQLAlchemy; needs real-warehouse parity tests).
- **Catalog composition** — push classifications + pass/fail evidence *out* to
  DataHub / OpenMetadata; pull ownership/lineage *in*. (We compose with catalogs;
  we do not rebuild them — lineage/catalog/IAM stay out of scope.)
- **Reconciliation at scale** — sampled checksums / same-engine pushdown so full
  tables never move for cross-system checks.

---

## 💡 Idea inbox

Raw capture — unfiltered, un-prioritized. Move to "Next up" when it earns it.

### Auto-calibrated thresholds *(top candidate)*
Users shouldn't have to know the right number for every limit. Let trueset
*propose* thresholds the user reviews and commits (never auto-applied silently —
same trust rule as checks):
- **From a data sample (static):** `suggest` proposes numeric ranges (e.g.
  p1–p99), null-rate tolerances, cardinality bounds — pre-filled, editable.
  *Partly exists:* the profiler already suggests `in_range min=0`, `in_set` from
  categoricals. Extend it to percentile ranges + tolerances.
- **From run history (dynamic):** learn "normal" bands from past runs and
  auto-set anomaly thresholds (row count 10k ± 3σ, freshness from observed
  cadence). Makes monitoring set *itself* up. *Not built yet.*
- **Per-scenario / per-segment:** different thresholds by partition (per region,
  per source, weekday vs weekend) so one global number doesn't cause false alarms.

<!-- Add new ideas below this line -->
