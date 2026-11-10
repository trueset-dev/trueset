# Trusting volatile data

*When an extreme value might be the truth, not an error.*

Most data-quality tools are built on a quiet assumption: an outlier is a mistake.
Set a threshold, reject anything past it. That works for a `country_code` or an
`email` — and **fails badly** for data where a spike is often *real*:

> A natural-gas price triples during a cold snap. A sensor reading jumps when the
> machine actually gets hot. Checkout traffic 10×s on launch day. Blood pressure
> spikes because the patient is genuinely in distress.

A fixed threshold flags the real event as an error (false positive — you cry
wolf and get ignored) *or* it's loose enough to miss a genuine bad value (a
silent error slips through). In volatile domains you can't win with rules alone.
You have to answer a harder question: **is this extreme corroborated?**

That's what this part of trueset is for. It doesn't pretend to "know" whether an
extreme is real — it **surfaces and quantifies the ambiguity** so a human or a
downstream system can decide, and it stops re-asking once someone has.

## Where this shows up

The pattern — *legitimate extremes mixed with real errors* — is not a
commodities thing. It's everywhere volatile:

| Domain | A real extreme looks like… | The silent error looks like… |
|---|---|---|
| **Commodities / markets** | cold-snap price spike, backed by demand/volume | a one-feed phantom tick no other source confirms |
| **IoT / sensors** | temperature spike when load genuinely rises | a stuck/garbled reading with no matching signal |
| **Energy / utilities** | demand surge in a heatwave | a meter misread |
| **Observability / web traffic** | launch-day or incident spike | a logging double-count |
| **Healthcare / vitals** | a genuine clinical event | a probe artifact |
| **Fraud / risk** | a real large transaction | a decimal-point data-entry error |
| **Ad / marketing** | a viral-moment conversion jump | duplicate event tracking |

If your data has this shape, the four moves below apply unchanged — only the
"corroborating signal" differs (volume, a sibling sensor, a second feed, …).

## The four moves

### 1. Corroboration — tell a real extreme from a bad value

Judge a suspicious value against a **supporting signal**, not in isolation. A
real price spike shows up in volume too; a stuck sensor's jump doesn't match the
load.

```yaml
- type: corroboration
  column: price
  corroborate_with: [demand]   # trust the spike only if demand backs it
  severity: warn               # surface it — real extremes happen; don't block
```

```
day 18: price=9.8, demand=140  ->  trusted (corroborated — demand backs it)
day 19: price=9.9, demand=51   ->  FLAGGED (uncorroborated — a lone bad tick)
```

The real event passes; only the unsupported extreme is flagged. (Cross-feed
variant: `source_corroboration` confirms against an independent source instead
of a sibling column — a move shows up in both feeds; a phantom shows up in one.)

### 2. Annotate-and-flow — score, don't block

Volatile data usually **can't be blocked** — a trading desk, an ops dashboard, a
monitoring system needs the full picture. So instead of dropping rows, attach a
quality score and let everything flow:

```python
from trueset import annotate
scored = annotate(df, "checks.yml", key="day")
# every row gets _trueset_quality (0..1) and _trueset_flags; nothing is dropped
```

Downstream decides what to do with low-quality rows (weight them down, review
them, alert) — the data keeps moving.

### 3. Adjudication — review once, stop re-flagging

The thing that kills trust in a DQ tool is re-flagging the same known-good event
every single run. When a human rules an extreme valid, record it:

```python
from trueset import Adjudications
adj = Adjudications()
adj.mark_valid("in_range(price)", 18, note="real cold-snap demand spike")
adj.save("adjudications.json")          # auditable, git-committable
annotate(df, "checks.yml", key="day", adjudications=adj)   # suppressed from now on
```

### 4. Context-aware ranges — not one global threshold

A legitimate regime in one segment shouldn't be judged by another's baseline.
Derive the expected band **per segment** (region, regime, season, device):

```python
from trueset import segment_bounds
segment_bounds(df, "price", "region")
# OK: [2.68, 3.72]   TX: [2.58, 3.62]   ← each segment judged on its own history
```

All four rest on **robust statistics** (`trueset.robust_z` / MAD, with a
flat-baseline fallback) — a defensible basis, never a hand-picked number.

## Try it

A runnable, end-to-end version of all four moves (the natural-gas example above)
ships in the repo:

```bash
python examples/ambiguity_demo.py
```

For the full YAML/API reference, see
[Corroboration & ambiguity](guides/ambiguity.md).

!!! note "Honest status"
    The `corroboration` / `source_corroboration` checks materialize the analyzed
    columns; `annotate` and `segment_bounds` operate on an in-memory (pandas)
    DataFrame today. That's fine for market/sensor data volumes; pushing the
    statistics down into the warehouse for very large tables is on the
    [roadmap](https://github.com/trueset-dev/trueset/blob/main/ROADMAP.md).
