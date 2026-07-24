"""Monitoring that needs HISTORY, not a single dataset.

Freshness is an ordinary check (it only inspects the current data, so it lives in
checks.py and speaks the Backend protocol). Volume anomaly is different: it can
only be judged against a baseline of PAST runs. That baseline comes from a
`ResultStore`, not from a `Backend` -- so it stays out of the check registry and
lives here as a pure function, preserving the rule that checks only ever talk to
the Backend protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: a baseline needs at least this many prior runs to be meaningful
MIN_BASELINE = 3


def volume_anomaly(history: Sequence[int], sigma: float = 3.0) -> dict[str, Any]:
    """Flag whether the latest row count deviates from its historical baseline.

    `history` is chronological row counts; the LAST element is the current run
    and everything before it is the baseline. A run is anomalous when its count
    is more than `sigma` standard deviations from the baseline mean (or, when the
    baseline is perfectly flat, simply differs from it).
    """
    hist = [int(x) for x in history]
    if len(hist) < MIN_BASELINE + 1:
        return {
            "status": "insufficient_history",
            "have": len(hist),
            "need": MIN_BASELINE + 1,
            "anomaly": False,
        }

    *baseline, current = hist
    n = len(baseline)
    mean = sum(baseline) / n
    std = (sum((x - mean) ** 2 for x in baseline) / n) ** 0.5

    if std == 0:
        anomaly = current != mean
        zscore = None
    else:
        z = (current - mean) / std
        anomaly = abs(z) > sigma
        zscore = round(z, 3)

    return {
        "status": "ok",
        "current": current,
        "baseline_mean": round(mean, 3),
        "baseline_std": round(std, 3),
        "zscore": zscore,
        "sigma": sigma,
        "anomaly": anomaly,
    }
