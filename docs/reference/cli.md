# CLI reference

All commands exit non-zero when an `error`-severity check fails (except `annotate`,
which never blocks). Add `--json` to `run` / `reconcile` for machine-readable output.

```bash
trueset --help
trueset list-checks         # every available check type
```

## `run`

Validate a dataset (a file, or a live SQL table) against a suite.

```bash
trueset run --data orders.csv --checks checks.yml
trueset run --url "postgresql://…/db" --table orders --checks checks.yml
trueset run --data batch.csv --checks checks.yml --quarantine bad.csv   # write failing rows
```

## `reconcile`

Validate a dataset against other systems. See [Reconciliation](../guides/reconciliation.md).

```bash
trueset reconcile --data warehouse.csv --checks reconcile.yml --ref source=source.csv
trueset reconcile --url "…/warehouse" --table orders --checks reconcile.yml \
  --ref "source=…/source::orders"
```

## `annotate`

Score every row and keep them all (annotate-and-flow).

```bash
trueset annotate --data ticks.csv --checks checks.yml --out scored.csv
trueset annotate --data ticks.csv --checks checks.yml --key day --adjudications adj.json
```

## `report`

Group pass/fail by a governance dimension.

```bash
trueset report --data orders.csv --checks governed.yml --by sensitivity   # or owner | regulation
```

## `profile` / `suggest`

Draft checks from your data. See [Authoring](../guides/authoring.md).

```bash
trueset profile --data orders.csv
trueset suggest --data orders.csv --calibrate --out checks.yml
trueset suggest --data orders.csv --describe "amount can't be negative"     # needs ANTHROPIC_API_KEY
```

## `monitor` / `history`

Persist runs and detect anomalies over time. See [Monitoring](../guides/monitoring.md).

```bash
trueset run … --save "postgresql://…/trueset_history"
trueset history --store "postgresql://…/trueset_history"
trueset monitor --store "$H" --suite orders --metric rows --method mad
```

## `import-dbt`

Convert dbt column tests into a trueset suite.

```bash
trueset import-dbt --schema schema.yml --model orders --out checks.yml
```

`not_null`/`unique` map directly, `accepted_values` → `in_set`, `relationships` →
`referential_integrity`; severity is preserved; unmappable tests are reported, not
silently dropped.
