"""trueset inside a data pipeline — a shift-left quality gate.

The point: trueset is a LIBRARY, not a warehouse-only CLI. Because checks only
speak to the Backend protocol, and the pandas backend accepts any DataFrame, you
can validate data *in flight* — at ingestion, before loading — and fail the
pipeline the instant a batch is bad, so garbage never reaches your warehouse.

The SAME suite then runs post-load against the warehouse (SQLAlchemyBackend) and
in CI (the GitHub Action). Write once, enforce everywhere.

Run:  python examples/pipeline_demo.py
"""

from __future__ import annotations

import pandas as pd

from trueset import Suite, validate_dataframe

# A suite you'd normally keep in a YAML file next to the pipeline.
INGEST_CONTRACT = Suite.from_dict(
    {
        "suite": "orders_ingest_contract",
        "checks": [
            {"type": "columns_exist", "columns": ["order_id", "amount", "status"]},
            {"type": "not_null", "column": "order_id"},
            {"type": "unique", "column": "order_id"},
            {"type": "in_range", "column": "amount", "min": 0},
            {"type": "in_set", "column": "status",
             "values": ["pending", "shipped", "delivered", "cancelled"]},
            # a metric gate: the batch total should look sane
            {"type": "metric", "column": "amount", "agg": "sum", "min": 0, "max": 1_000_000},
        ],
    }
)


def load_to_warehouse(df: pd.DataFrame) -> None:
    print(f"  -> LOADED {len(df)} rows to the warehouse")


def ingest_batch(name: str, df: pd.DataFrame) -> bool:
    """The gate: validate the in-memory batch; load only if it passes."""
    print(f"\nbatch '{name}' ({len(df)} rows)")
    result = validate_dataframe(df, INGEST_CONTRACT)
    if result.passed:
        load_to_warehouse(df)
        return True
    print(f"  ✗ BLOCKED — not loading. counts={result.counts}")
    for r in result.results:
        if not r.ok:
            print(f"      - {r.check}({r.column or '-'}): {r.message}")
    return False


def main() -> None:
    clean = pd.DataFrame(
        {
            "order_id": [1, 2, 3],
            "amount": [10.0, 20.0, 30.0],
            "status": ["pending", "shipped", "delivered"],
        }
    )
    # a duplicate id, a negative amount, and an unknown status
    dirty = pd.DataFrame(
        {
            "order_id": [1, 1, 3],
            "amount": [10.0, -5.0, 30.0],
            "status": ["pending", "teleported", "delivered"],
        }
    )

    ok_clean = ingest_batch("clean", clean)
    ok_dirty = ingest_batch("dirty", dirty)

    print("\nresult: clean batch loaded =", ok_clean, "| dirty batch loaded =", ok_dirty)
    assert ok_clean and not ok_dirty, "gate should pass clean and block dirty"
    print("shift-left gate works: bad data never reached the warehouse.")


if __name__ == "__main__":
    main()
