"""Ambiguity-aware validation, the commodities way.

The hard problem: an extreme value is often the *truth* (a cold-snap demand
spike, a geopolitical event), not an error. A fixed threshold can't tell them
apart. trueset corroborates, scores confidence, and learns from review instead.

Run:  python examples/ambiguity_demo.py
"""

from __future__ import annotations

import pandas as pd

from trueset import Adjudications, Suite, annotate, corroboration_flags, segment_bounds

# 20 days of natural-gas ticks. Two extreme prices:
#   day 18 — a REAL cold-snap spike: price AND demand jump together (corroborated)
#   day 19 — a SILENT bad tick: price jumps but demand is flat (uncorroborated)
price = [3.1, 3.2, 3.0, 3.1, 3.3, 3.2, 3.1, 3.0, 3.2, 3.1,
         3.2, 3.3, 3.1, 3.0, 3.2, 3.1, 3.2, 9.8, 9.9, 3.1]
demand = [50, 51, 49, 50, 52, 51, 50, 49, 51, 50,
          51, 52, 50, 49, 51, 50, 51, 140, 51, 50]   # demand spikes day 18, flat day 19
df = pd.DataFrame({
    "day": range(1, 21),
    "region": (["TX"] * 10) + (["OK"] * 10),
    "price": price,
    "demand": demand,
})

print("1) CORROBORATION — which spike is real?")
res = corroboration_flags(df, "price", corroborate_with=["demand"])
for day in (18, 19):
    row = df[df.day == day].index[0]
    verdict = "FLAGGED (uncorroborated)" if res.uncorroborated.iloc[row] else "trusted (corroborated)"
    print(f"   day {day}: price={df.at[row,'price']}, demand={df.at[row,'demand']}  ->  {verdict}")
print("   -> the real cold-snap spike passes; only the unsupported bad tick is flagged\n")

print("2) ANNOTATE-AND-FLOW — score every row, block nothing")
suite = Suite.from_dict({"suite": "gas", "checks": [
    {"type": "corroboration", "column": "price", "corroborate_with": ["demand"],
     "severity": "warn"},
    {"type": "in_range", "column": "price", "min": 0, "max": 8, "severity": "warn"},
]})
scored = annotate(df, suite, key="day")
print(scored[scored["_trueset_flags"] != ""][["day", "price", "demand",
      "_trueset_quality", "_trueset_flags"]].to_string(index=False))
print("   -> both extremes get a low quality score and flow on with metadata\n")

print("3) ADJUDICATION — a human rules the cold snap valid; stop re-flagging it")
adj = Adjudications()
adj.mark_valid("in_range(price)", 18, note="real cold-snap demand spike")
rescored = annotate(df, suite, key="day", adjudications=adj)
day18 = rescored[rescored.day == 18].iloc[0]
print(f"   day 18 flags now: {day18['_trueset_flags']!r}  (in_range suppressed by review)\n")

print("4) CONTEXT-AWARE RANGES — one expected band per region, not one globally")
for region, b in segment_bounds(df, "price", "region").items():
    print(f"   {region}: [{b['min']}, {b['max']}]  (n={b['n']})")
print("   -> a legitimate regional regime isn't judged by another region's band")
