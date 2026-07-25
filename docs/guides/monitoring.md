# Monitoring & history

Turn one-shot validation into continuous monitoring: persist every run, then watch
for staleness and drift over time.

## Freshness

An ordinary check — the newest timestamp must be recent (catches stale pipelines):

```yaml
- type: freshness
  column: created_at
  max_age_hours: 6        # fail if the table hasn't updated in 6 hours
```

Runs on every backend via a pushed-down `max()`.

## Results history

Persist runs to any SQLAlchemy database as an auditable trail:

```bash
trueset run --data orders.csv --checks checks.yml --save "postgresql://…/trueset_history"
trueset history --store "postgresql://…/trueset_history"
```

Two tables (`trueset_runs`, `trueset_results`) keep verdicts, counts, row volume,
and full per-check evidence.

## Anomaly detection

`trueset monitor` trends a metric against the baseline of past runs and exits
non-zero on an anomaly — a silent 90% drop in rows is caught even when every row
that *is* there passes every check:

```bash
trueset monitor --store "$H" --suite orders --metric rows --method mad
trueset monitor --store "$H" --suite orders --metric failing_rows --check not_null --column email
```

- `--metric` — `rows`, `failing_rows`, or `total_rows` (with `--check` / `--column`
  to pick a specific check's trend).
- `--method` — `zscore` (mean/std) or `mad` (median-absolute-deviation, robust when
  a few past runs were themselves outliers).

Detection is deterministic and explainable — never a black box.
