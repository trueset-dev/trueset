"""Run the identical reconciliation suite on two different engines.

    python examples/portability_demo.py

Same YAML. Same check specs. One runs in pandas memory, the other pushes SQL
into DuckDB. The verdicts must match -- that's the portability thesis, proven.
"""

from pathlib import Path

import duckdb
import pandas as pd

from trueset import PandasBackend, Suite
from trueset.backends.duckdb_backend import DuckDBBackend

EX = Path(__file__).resolve().parent
suite = Suite.from_yaml(EX / "reconcile.yml")

# --- engine 1: pandas (in-memory) ---
pandas_result = suite.run(
    PandasBackend(pd.read_csv(EX / "warehouse_orders.csv")),
    references={"source": PandasBackend(pd.read_csv(EX / "source_orders.csv"))},
)

# --- engine 2: duckdb (SQL pushdown) ---
con = duckdb.connect()
con.execute(f"CREATE TABLE warehouse AS SELECT * FROM read_csv_auto('{EX/'warehouse_orders.csv'}')")
con.execute(f"CREATE TABLE source AS SELECT * FROM read_csv_auto('{EX/'source_orders.csv'}')")
duck_result = suite.run(
    DuckDBBackend(con, "warehouse"),
    references={"source": DuckDBBackend(con, "source")},
)

print(f"{'check':<24}{'pandas':<12}{'duckdb':<12}{'match':<6}")
print("-" * 54)
for p, d in zip(pandas_result.results, duck_result.results, strict=True):
    match = "OK" if (p.status, p.failing_rows) == (d.status, d.failing_rows) else "DIFF"
    print(f"{p.check:<24}{p.status.value + f'({p.failing_rows})':<12}"
          f"{d.status.value + f'({d.failing_rows})':<12}{match:<6}")

print("-" * 54)
print(f"suite passed -> pandas={pandas_result.passed}  duckdb={duck_result.passed}")
print("identical verdict:" ,
      [(r.check, r.status.value) for r in pandas_result.results]
      == [(r.check, r.status.value) for r in duck_result.results])
