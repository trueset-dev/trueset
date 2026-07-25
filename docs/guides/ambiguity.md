# Corroboration & ambiguity

!!! warning "Newer / experimental"
    These features are the newest part of trueset. The checks run on any backend
    (they materialize the analyzed columns); `annotate` and `segment_bounds`
    operate on an in-memory DataFrame. See the [roadmap](https://github.com/trueset-dev/trueset/blob/main/ROADMAP.md).

Some data — commodities, markets, sensors — has a hard property: an extreme value
is often the **truth**, not an error (a cold-snap demand spike, a geopolitical
event, a market move). A fixed threshold can't tell a real extreme from a mistake.
trueset's job here is to **surface and quantify** the ambiguity, not pretend to
resolve it.

## Corroboration — is a suspicious value supported?

Judge an outlier against **supporting signals**, not in isolation. A real price
spike shows up in volume too; a silent bad tick doesn't.

```yaml
- type: corroboration
  column: price
  corroborate_with: [volume]   # trust the spike only if volume backs it
  z: 3.5                       # robust-outlier threshold on the primary
  min_support: 1               # how many corroborators must agree
  severity: warn               # surface it — real extremes happen, don't block
```

### Cross-source corroboration — do 2+ sources agree?

Corroborate against an independent feed instead of a sibling column:

```yaml
- type: source_corroboration
  column: price
  key: date
  reference: source_b          # resolved at run time like a reconciliation ref
  rel_tol: 0.1                 # confirmed if the other source agrees within 10%
  severity: warn
```

A real move shows up in both feeds; a one-source phantom is surfaced.

## Annotate-and-flow — score, don't block

Market data often can't be blocked — you need a full view. Instead of dropping
bad rows, attach a quality score and let everything flow:

```python
from trueset import annotate
scored = annotate(df, "checks.yml", key="day")
# adds _trueset_quality (0..1) and _trueset_flags (checks each row failed)
```

or from the CLI:

```bash
trueset annotate --data ticks.csv --checks checks.yml --out scored.csv
```

Nothing is dropped; downstream decides what to do with low-quality rows.

## Adjudications — review once, stop re-flagging

When a human rules a flag "actually valid," record it so future runs don't
re-flag it — the feedback loop that kills repeat false positives:

```python
from trueset import Adjudications
adj = Adjudications()
adj.mark_valid("in_range(price)", "2026-03-09", note="real cold-snap spike")
adj.save("adjudications.json")            # auditable, git-committable

annotate(df, "checks.yml", key="day", adjudications=adj)   # suppressed going forward
```

## Context-aware ranges

A legitimate seasonal spike in one segment shouldn't trip a global threshold set
by the others. Derive an expected band **per segment**:

```python
from trueset import segment_bounds
segment_bounds(df, "price", "region")
# {'north': {'min': .., 'max': .., 'n': ..}, 'south': {...}}
```

All of it rests on robust statistics (`trueset.robust_z` / MAD, with a
flat-baseline fallback) — a defensible basis, never a hand-picked number.

Runnable end-to-end example: [`examples/ambiguity_demo.py`](https://github.com/trueset-dev/trueset/blob/main/examples/ambiguity_demo.py).
