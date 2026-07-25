# Pipelines & quarantine

trueset is a **library first**, not a warehouse-only CLI. Because the pandas
backend accepts any DataFrame, you can validate data at *every* stage of a
pipeline — not just after loading.

| Where | Works? | How |
|-------|--------|-----|
| At ingestion / pre-load | ✅ | validate the DataFrame *before* it lands |
| Mid-transform (Airflow/Dagster/Prefect task, Lambda, script) | ✅ | `validate_dataframe(df, suite)` on any intermediate frame |
| Post-load / in the warehouse | ✅ | `SQLAlchemyBackend` — pushed-down SQL |
| Across the boundary (source vs warehouse) | ✅ | [reconciliation](reconciliation.md) |
| Per-event streaming | ⚠️ | batch / micro-batch oriented; validate each batch |
| Native Spark (in-cluster) | ❌ | roadmap — today `.toPandas()` or push to the warehouse |

## Shift-left: a quality gate at ingestion

Stop bad data before it ever reaches storage:

```python
from trueset import validate_dataframe

df = extract_from_api()                        # your ingestion step
result = validate_dataframe(df, "checks.yml")  # same suite, in-memory
if not result.passed:
    raise ValueError(f"bad batch, not loading: {result.counts}")
load_to_warehouse(df)                          # only reached if data is clean
```

## Quarantine / dead-letter routing

trueset detects; it never silently reroutes your data. `split()` gives you the
*material* to route with — the failing rows partitioned from the clean ones:

```python
from trueset import split

result = split(df, "checks.yml")
load_to_warehouse(result.good)          # clean rows through
dead_letter(result.bad_annotated())     # bad rows + a _trueset_reasons column
```

By default only `error`-severity checks divert a row (`include_warnings=True` to
opt in). From the CLI, write failing rows to a file:

```bash
trueset run --data batch.csv --checks checks.yml --quarantine bad.csv
```

For the annotate-and-flow alternative (score every row, block nothing), see
[Corroboration & ambiguity](ambiguity.md#annotate-and-flow-score-dont-block).
