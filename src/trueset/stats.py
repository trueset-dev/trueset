"""Robust statistics for ambiguity-aware validation.

Commodities data is heavy-tailed: a fixed mean/standard-deviation z-score is
dragged around by the very outliers you're trying to judge, so a real spike
inflates the threshold and hides the next one. The median and MAD (median
absolute deviation) are outlier-robust -- they give every threshold a defensible
statistical basis instead of a hand-picked number.

Everything here is deterministic and explainable; no model decides pass/fail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: scale factor making MAD a consistent estimator of the standard deviation
#: for normally distributed data (1 / 0.6745).
_MAD_TO_SIGMA = 1.4826
#: scale factor for mean absolute deviation -> standard deviation.
_MEANAD_TO_SIGMA = 1.2533


def mad(values: pd.Series) -> float:
    """Median absolute deviation, scaled to be comparable to a standard dev."""
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return 0.0
    med = float(s.median())
    return float((s - med).abs().median()) * _MAD_TO_SIGMA


def _robust_scale(s: pd.Series) -> float:
    """A non-degenerate spread estimate around the median.

    Prefers MAD (outlier-robust). But MAD collapses to 0 when >50% of values are
    identical -- a flat baseline that then spikes, common in sensor/market data --
    which would hide the very spike we want to catch. In that case we fall back to
    the mean absolute deviation so a genuine excursion above a constant baseline
    still scores as an outlier. Returns 0 only for a truly constant series.
    """
    med = float(s.median())
    scale = float((s - med).abs().median()) * _MAD_TO_SIGMA
    if scale == 0:
        scale = float((s - med).abs().mean()) * _MEANAD_TO_SIGMA
    return scale


def robust_z(values: pd.Series) -> pd.Series:
    """Per-value robust z-score: (x - median) / robust-scale.

    Returns all-zero for a truly constant column so a degenerate series never
    reports spurious outliers.
    """
    s = pd.to_numeric(values, errors="coerce")
    med = float(s.median())
    scale = _robust_scale(s.dropna())
    if scale == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - med) / scale


def robust_bounds(values: pd.Series, z: float = 3.5) -> tuple[float, float]:
    """A [low, high] band at +/- `z` robust deviations from the median.

    z=3.5 is the common Iglewicz-Hoaglin outlier cutoff. Returns (nan, nan) if
    there is no numeric data to derive a band from.
    """
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return (float("nan"), float("nan"))
    med = float(s.median())
    scale = _robust_scale(s)
    if scale == 0:  # constant column: the band is the value itself
        return (med, med)
    return (med - z * scale, med + z * scale)
