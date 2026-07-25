# Cross-system reconciliation

The capability no single-table tool (dbt tests, Great Expectations, Soda, Pandera)
is architected to express, and whose only open-source option (`data-diff`) was
archived in 2024: validate one dataset **against another system**.

This is the failure that passes every row-level check: the warehouse table looks
internally valid, but it silently dropped rows, gained phantom rows, or corrupted
a value somewhere between the source and the load. Reconciliation catches it.

## The idea

A reconciliation check holds a **second (reference) backend** and compares. Because
checks only talk to the `Backend` protocol, the two sides can be *different
engines* — a CSV export vs. a Postgres table, a source database vs. your warehouse.

```bash
trueset reconcile \
  --data   warehouse_orders.csv \
  --checks reconcile.yml \
  --ref    source=source_orders.csv
```

```yaml
suite: warehouse_vs_source
checks:
  - type: row_count_parity        # counts agree within tolerance
    reference: source
    tolerance: 0.0

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

## The three checks

| Check | Catches |
|-------|---------|
| `row_count_parity` | the load dropped or duplicated rows (counts diverge beyond `tolerance`) |
| `referential_integrity` | orphan keys — rows whose key never existed in the source |
| `value_parity` | value drift on shared keys, keys only in one side, **and duplicate keys** |

`value_parity` reports every failure mode in one result:

```json
{
  "mismatched_values": 1,
  "only_in_primary": 1,
  "only_in_reference": 1,
  "duplicate_keys_primary": 0,
  "duplicate_keys_reference": 0,
  "compared_keys": 3
}
```

!!! note "Passing `row_count_parity` alone proves nothing about contents"
    Two datasets can have identical counts and completely different rows. That's
    exactly why `value_parity` and `referential_integrity` exist alongside it.

## Reconcile two SQL systems directly

Both the primary and the references can be live SQL tables — reconcile a warehouse
against its source database without exporting anything:

```bash
trueset reconcile \
  --url  "postgresql://…/warehouse" --table orders \
  --checks reconcile.yml \
  --ref  "source=postgresql://…/source::orders"
```

## Data contracts

A reconciliation suite *is* a cross-system contract between a producer and a
consumer. Give it a name, an owner, and put it in CI, and you have contract
enforcement — the hardest part (the comparison) already exists.
