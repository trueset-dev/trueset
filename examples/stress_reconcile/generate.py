"""Generate a realistic two-source reconciliation case study (with planted drift).

Makes a `source` and a `warehouse` version of an orders table that mostly agree
but disagree in known, counted ways -- so you can run `trueset reconcile` on a
realistic row count and check its output against the printed ground truth.

    python examples/stress_reconcile/generate.py --rows 1000000

Writes CSVs to examples/stress_reconcile/_data/ (git-ignored). Pass --sqlite to
also load both tables into one SQLite DB, so you can reconcile same-engine
(SQL URLs) as well as cross-engine (CSV vs CSV).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STATUSES = ["pending", "shipped", "delivered", "cancelled"]


def build(rows: int, mismatch_frac: float, only_wh: int, only_src: int, dups: int, seed: int):
    rng = np.random.default_rng(seed)
    ids = np.arange(1, rows + 1)
    source = pd.DataFrame({
        "order_id": ids,
        "customer_id": rng.integers(1, max(2, rows // 10), size=rows),
        "amount": np.round(rng.uniform(5, 500, size=rows), 2),
        "status": rng.choice(STATUSES, size=rows),
    })
    warehouse = source.copy()

    # 1) value mismatches on shared keys: perturb `amount` on a random subset
    n_mis = int(rows * mismatch_frac)
    mis_idx = rng.choice(rows, size=n_mis, replace=False)
    warehouse.loc[mis_idx, "amount"] = np.round(warehouse.loc[mis_idx, "amount"] + 1.0, 2)

    # 2) keys only in the warehouse (primary): append brand-new ids
    extra = pd.DataFrame({
        "order_id": np.arange(rows + 1, rows + 1 + only_wh),
        "customer_id": rng.integers(1, max(2, rows // 10), size=only_wh),
        "amount": np.round(rng.uniform(5, 500, size=only_wh), 2),
        "status": rng.choice(STATUSES, size=only_wh),
    })
    warehouse = pd.concat([warehouse, extra], ignore_index=True)

    # 3) keys only in the source (reference): drop some rows from the warehouse
    drop_idx = rng.choice(rows, size=only_src, replace=False)
    warehouse = warehouse[~warehouse["order_id"].isin(ids[drop_idx])]

    # 4) duplicate keys in the warehouse
    if dups:
        warehouse = pd.concat([warehouse, warehouse.iloc[:dups]], ignore_index=True)

    return source, warehouse, {
        "mismatched_values": n_mis,
        "only_in_primary (warehouse)": only_wh,
        "only_in_reference (source)": only_src,
        "duplicate_keys_primary": dups,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--mismatch-frac", type=float, default=0.001)
    ap.add_argument("--only-wh", type=int, default=25)
    ap.add_argument("--only-src", type=int, default=40)
    ap.add_argument("--dups", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sqlite", action="store_true", help="also load both tables into one SQLite DB")
    args = ap.parse_args()

    out = HERE / "_data"
    out.mkdir(exist_ok=True)
    source, warehouse, truth = build(
        args.rows, args.mismatch_frac, args.only_wh, args.only_src, args.dups, args.seed
    )
    source.to_csv(out / "source_orders.csv", index=False)
    warehouse.to_csv(out / "warehouse_orders.csv", index=False)

    if args.sqlite:
        from sqlalchemy import create_engine

        eng = create_engine(f"sqlite:///{out / 'reconcile.sqlite'}")
        source.to_sql("source_orders", eng, index=False, if_exists="replace")
        warehouse.to_sql("warehouse_orders", eng, index=False, if_exists="replace")

    print(f"wrote {len(source):,} source rows and {len(warehouse):,} warehouse rows to {out}")
    print("GROUND TRUTH (what reconcile should report as failing):")
    for k, v in truth.items():
        print(f"  {k:32} {v:,}")
    print(f"  {'TOTAL failing':32} {sum(truth.values()):,}")


if __name__ == "__main__":
    main()
