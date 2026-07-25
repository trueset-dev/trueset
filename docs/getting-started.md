# Getting started

## Install

```bash
pip install trueset          # core (pandas)
pip install "trueset[sql]"   # + DuckDB / SQLAlchemy warehouses
```

Requires Python 3.10+.

## Your first check suite

Checks are declared in YAML. Create `checks.yml`:

```yaml
suite: orders_quality
checks:
  - type: not_null
    column: order_id
  - type: unique
    column: order_id
  - type: in_range
    column: amount
    min: 0
  - type: in_set
    column: status
    values: [pending, shipped, delivered, cancelled]
  - type: matches_regex
    column: email
    pattern: '[^@\s]+@[^@\s]+\.[^@\s]+'
    severity: warn        # warns, doesn't fail the run
```

Run it against a data file:

```bash
trueset run --data orders.csv --checks checks.yml
```

The command exits non-zero if any `error`-severity check fails, so it drops
straight into CI, dbt, or Airflow. Add `--json` for machine-readable output.

## From Python

```python
import pandas as pd
from trueset import validate_dataframe

df = pd.read_csv("orders.csv")
result = validate_dataframe(df, "checks.yml")

print(result.passed)        # False
print(result.to_dict())     # JSON-ready — ship to a warehouse or dashboard
```

Because a check only ever talks to the `Backend` protocol, the *same* `checks.yml`
runs unchanged against a warehouse table:

```bash
trueset run --url "postgresql://user:pass@host/db" --table orders --checks checks.yml
```

## Severities

- `error` (default) — a failing check fails the run (non-zero exit). Gate CI with it.
- `warn` — surfaces the problem but keeps the run green (exit 0).

## Next steps

- [Cross-system reconciliation](guides/reconciliation.md) — the headline use case
- [Draft checks from your data](guides/authoring.md) with `profile` / `suggest`
- [Run in a pipeline](guides/pipelines.md) and quarantine bad rows
