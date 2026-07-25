# Authoring checks

You don't have to write every check by hand. trueset can draft a suite from your
data — deterministically, or with an AI copilot — and *every* proposed check is
validated through the same registry, so the output is always something you can
read, trust, and commit.

## Profile your data

```bash
trueset profile --data orders.csv
```

Shows per-column stats and an inferred semantic type (email / uuid / url /
datetime / categorical / numeric / …) plus a suggested [sensitivity](governance.md#data-classification).

## Draft a suite (deterministic, no AI)

```bash
trueset suggest --data orders.csv                 # rule-based draft, always safe
trueset suggest --data orders.csv --out checks.yml
```

### Auto-calibrated thresholds

Rather than hand-picking limits, derive them from the data — numeric `in_range`
bounds (from the 1st/99th percentiles, widened so current data passes) and a
row-count volume band, emitted as `warn` for you to review:

```bash
trueset suggest --data orders.csv --calibrate
```

!!! tip "Run calibration on known-good data"
    Calibration learns from the sample — representative input in means sensible
    thresholds out.

## AI copilot

The copilot turns a data profile or a plain-English intent into checks:

```bash
export ANTHROPIC_API_KEY=…
trueset suggest --data orders.csv --ai --out checks.yml
trueset suggest --data orders.csv --describe "amount can't be negative; \
    status is one of pending/shipped/delivered/cancelled"
```

!!! info "The trust rule that makes AI safe here"
    The copilot only ever *authors* checks. Every spec it returns is passed through
    the deterministic registry (`build_check`) — anything it hallucinates or
    misconfigures is discarded before it can reach your data. The AI is never in
    the runtime pass/fail path, so your validation stays deterministic and
    auditable. The model is injected as a plain callable, so it's provider-agnostic
    and fully testable without a key.
