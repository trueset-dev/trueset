# Reconciliation stress case study

A realistic, two-source reconciliation you can run at scale and check against a
known answer. Use it to feel how `trueset reconcile` behaves — and, honestly,
where it currently strains — on real row counts instead of the 7-row toy data.

## 1. Generate the data

```bash
# two CSVs with planted, counted drift (defaults: 1,000,000 rows)
python examples/stress_reconcile/generate.py --rows 1000000
```

It prints the **ground truth** — exactly how many mismatches, only-in-primary,
only-in-reference, and duplicate keys it planted. `reconcile` should report the
same numbers.

```
GROUND TRUTH (what reconcile should report as failing):
  mismatched_values                1,000
  only_in_primary (warehouse)         25
  only_in_reference (source)          40
  duplicate_keys_primary               5
  TOTAL failing                    1,070
```

## 2. Reconcile (cross-engine: CSV vs CSV)

```bash
trueset reconcile \
  --data   examples/stress_reconcile/_data/warehouse_orders.csv \
  --checks examples/stress_reconcile/reconcile.yml \
  --ref    source=examples/stress_reconcile/_data/source_orders.csv
```

Check the `value_parity` observed counts against the ground truth above. They
should match exactly.

## 3. Reconcile same-engine (both tables in one SQL database)

```bash
python examples/stress_reconcile/generate.py --rows 1000000 --sqlite

trueset reconcile \
  --url    "sqlite:///examples/stress_reconcile/_data/reconcile.sqlite" \
  --table  warehouse_orders \
  --checks examples/stress_reconcile/reconcile.yml \
  --ref    source="sqlite:///examples/stress_reconcile/_data/reconcile.sqlite::source_orders"
```

## What to watch for (this is the point)

- **Correctness:** do the reported counts equal the ground truth? Try bumping
  `--rows` to 5,000,000.
- **Memory / time:** today, `value_parity` compares the key + compared columns
  from *both* sides in memory (it does not fully push the join into SQL yet), and
  `referential_integrity` sends the distinct keys back as an `IN (...)` list.
  Watch RSS and wall-clock as `--rows` grows — this is the known scaling limit
  the roadmap targets (same-engine SQL-join pushdown; cross-engine hashing).
- **Type fidelity:** CSV reads `amount` as float; a warehouse might store it as
  `NUMERIC`. Exact comparison can surface type/rounding drift as false
  mismatches — another reason tolerance + type normalization is on the list.

> The generated files live in `_data/` and are git-ignored.
