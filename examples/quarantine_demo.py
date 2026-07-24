"""Route bad rows to a dead-letter, keep the clean ones flowing.

trueset detects and hands you the material; you route. `split()` partitions an
in-memory batch into rows that pass every row-wise check and rows that don't,
recording WHY each bad row failed -- exactly what a dead-letter / quarantine
sink needs for repair and replay.

Run:  python examples/quarantine_demo.py
"""

from __future__ import annotations

import pandas as pd

from trueset import Suite, split

CONTRACT = Suite.from_dict(
    {
        "suite": "orders_ingest",
        "checks": [
            {"type": "not_null", "column": "order_id"},
            {"type": "unique", "column": "order_id"},
            {"type": "in_range", "column": "amount", "min": 0},
            {"type": "in_set", "column": "status",
             "values": ["pending", "shipped", "delivered", "cancelled"]},
        ],
    }
)


def load_to_warehouse(df: pd.DataFrame) -> None:
    print(f"  -> LOADED {len(df)} clean row(s)")


def dead_letter(df: pd.DataFrame) -> None:
    print(f"  -> DEAD-LETTERED {len(df)} bad row(s) for repair/replay:")
    for _, row in df.iterrows():
        print(f"       id={row['order_id']!r:>6}  reason: {row['_trueset_reasons']}")


def main() -> None:
    batch = pd.DataFrame(
        {
            "order_id": [1, 2, 2, 4, 5],       # 2 is duplicated
            "amount": [10.0, 20.0, 30.0, -5.0, 15.0],  # -5 is out of range
            "status": ["pending", "shipped", "delivered", "shipped", "teleported"],  # bad status
        }
    )

    result = split(batch, CONTRACT)
    print(f"batch of {len(batch)} rows -> {result.n_good} clean, {result.n_bad} quarantined\n")

    # Keep the pipeline moving: good rows proceed, bad rows are diverted.
    load_to_warehouse(result.good)
    dead_letter(result.bad_annotated())

    assert result.n_good == 1 and result.n_bad == 4
    print("\nclean rows loaded; bad rows quarantined with reasons -- pipeline never stalled.")


if __name__ == "__main__":
    main()
