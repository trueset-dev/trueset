# Check reference

Every check accepts an optional `severity` (`error` default, or `warn`) and the
optional [governance fields](../guides/governance.md) (`owner`, `sensitivity`,
`regulation`, `tags`, `description`).

## Single-source checks

| Type | Parameters |
|------|-----------|
| `columns_exist` | `columns: [str]` |
| `not_null` | `column: str` |
| `unique` | `column: str` |
| `in_set` | `column: str`, `values: [any]` |
| `in_range` | `column: str`, `min?: number`, `max?: number` |
| `matches_regex` | `column: str`, `pattern: str` |
| `row_count` | `min?: int`, `max?: int` |
| `no_duplicate_rows` | `subset?: [str]` |
| `metric` | `column: str`, `agg: sum\|avg\|min\|max\|count`, `equals?`, `tolerance?`, `min?`, `max?` |
| `freshness` | `column: str`, `max_age_hours: number` |

## Reconciliation checks

Each takes a `reference:` naming another dataset, resolved at run time.

| Type | Parameters |
|------|-----------|
| `row_count_parity` | `reference: str`, `tolerance?: float` |
| `referential_integrity` | `column`, `reference`, `ref_column` |
| `value_parity` | `key`, `columns: [str]`, `reference`, `ref_key?`, `ref_columns?` |

## Ambiguity checks

*(newer / experimental — see [the guide](../guides/ambiguity.md))*

| Type | Parameters |
|------|-----------|
| `corroboration` | `column`, `corroborate_with: [str]`, `z?`, `support_z?`, `min_support?`, `directional?` |
| `source_corroboration` | `column`, `key`, `reference`, `ref_column?`, `ref_key?`, `z?`, `rel_tol?` |

## CheckResult fields

| Field | Meaning |
|-------|---------|
| `check` | the check type |
| `status` | `pass` \| `fail` \| `error` (the check itself couldn't run) |
| `severity` | `error` \| `warn` |
| `column` | the column checked (if any) |
| `observed` | what was measured (count, or a structured detail) |
| `failing_rows` / `total_rows` | counts |
| `message` | human-readable summary |
| `meta` | governance metadata (when set) |

A `SuiteResult` bundles results with `.passed`, `.counts`, and `.to_dict()`.
