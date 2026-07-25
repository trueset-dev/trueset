# Checks

Single-source checks validate one dataset. Each is declared in YAML with a `type`
and its parameters, plus an optional `severity` (`error` default, or `warn`).

## Built-in checks

| Type | Parameters | Fails when |
|------|-----------|------------|
| `columns_exist` | `columns: [str]` | a listed column is missing |
| `not_null` | `column` | the column has null values |
| `unique` | `column` | the column has duplicate values |
| `in_set` | `column`, `values: [...]` | a value isn't in the allowed set |
| `in_range` | `column`, `min?`, `max?` | a numeric value is out of range |
| `matches_regex` | `column`, `pattern` | a value doesn't fully match the pattern |
| `row_count` | `min?`, `max?` | the row count is outside the range |
| `no_duplicate_rows` | `subset?: [str]` | duplicate rows exist (optionally on a subset) |
| `metric` | `column`, `agg`, `equals?`/`tolerance?`, `min?`, `max?` | an aggregate is off target |

## The `metric` check

Validate an aggregate — for metrics/report validation ("total revenue ≈ X", "avg
order value in [10, 100]"):

```yaml
- type: metric
  column: amount
  agg: sum            # sum | avg | min | max | count
  equals: 15000
  tolerance: 0.01     # within 1%
- type: metric
  column: amount
  agg: avg
  min: 10
  max: 100
```

It runs as a pushed-down aggregate, so it works identically on pandas, DuckDB, and
any SQL warehouse.

## Results

Every check produces a structured, JSON-serializable `CheckResult`
(`check`, `status`, `severity`, `column`, `observed`, `failing_rows`,
`total_rows`, `message`). A `SuiteResult` bundles them with a `passed` verdict and
counts — ready for CI, a dashboard, or a warehouse table.

```python
result = validate_dataframe(df, "checks.yml")
result.passed          # bool — False if any error-severity check failed
result.counts          # {"pass": .., "fail": .., "error": .., "warn": ..}
result.to_dict()       # full JSON evidence
```

See the [check reference](../reference/checks.md) for every field, and
[Authoring](authoring.md) to draft a suite from your data automatically.
