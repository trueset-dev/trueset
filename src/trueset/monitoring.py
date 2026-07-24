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


# --------------------------------------------------------------------------- #
# Generalized, pluggable detectors -- monitor ANY metric, not just row volume.
# --------------------------------------------------------------------------- #

DETECTORS = ("zscore", "mad")


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def detect_anomaly(
    history: Sequence[float], sigma: float = 3.0, method: str = "zscore"
) -> dict[str, Any]:
    """Is the latest value an anomaly vs the baseline of prior values?

    Deterministic and explainable -- never an opaque model. Two methods:

    - ``zscore``: distance from the baseline MEAN in standard deviations. Simple,
      but a single past outlier inflates the std and hides real anomalies.
    - ``mad``: distance from the baseline MEDIAN in (scaled) median-absolute-
      deviations. Robust -- a few bad past runs don't blind it.

    The last element of `history` is the current value; the rest is the baseline.
    Returns a uniform verdict: center/spread/score/anomaly.
    """
    if method not in DETECTORS:
        raise ValueError(f"unknown method '{method}'. choose one of: {', '.join(DETECTORS)}")

    data = [float(x) for x in history]
    if len(data) < MIN_BASELINE + 1:
        return {
            "status": "insufficient_history",
            "method": method,
            "have": len(data),
            "need": MIN_BASELINE + 1,
            "anomaly": False,
        }

    *baseline, current = data
    n = len(baseline)

    if method == "zscore":
        center = sum(baseline) / n
        spread = (sum((x - center) ** 2 for x in baseline) / n) ** 0.5
    else:  # mad
        center = _median(baseline)
        # 1.4826 scales MAD to be a consistent estimator of std for normal data
        spread = 1.4826 * _median([abs(x - center) for x in baseline])

    if spread == 0:
        anomaly = current != center
        score = None
    else:
        score = (current - center) / spread
        anomaly = abs(score) > sigma

    return {
        "status": "ok",
        "method": method,
        "current": current,
        "center": round(center, 3),
        "spread": round(spread, 3),
        "score": round(score, 3) if score is not None else None,
        "sigma": sigma,
        "anomaly": anomaly,
    }
