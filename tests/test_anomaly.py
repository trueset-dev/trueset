"""Tests for generalized anomaly detection (detectors + per-metric history)."""

import pandas as pd
import pytest

from trueset import detect_anomaly

pytest.importorskip("sqlalchemy")
from trueset import PandasBackend, Suite  # noqa: E402
from trueset.history import ResultStore  # noqa: E402
from trueset.monitoring import detect_anomaly as da  # noqa: E402

# -- detectors --------------------------------------------------------------- #


def test_zscore_flags_spike():
    v = detect_anomaly([100, 101, 99, 100, 500], method="zscore")
    assert v["anomaly"] is True
    assert v["method"] == "zscore"


def test_mad_is_robust_to_a_past_outlier():
    # A single wild past value (500) inflates std and can hide a real anomaly for
    # zscore; MAD uses the median and is unaffected.
    history = [1000, 1010, 500, 990, 1005, 1002]  # current 1002 is normal
    assert detect_anomaly(history, method="zscore")["anomaly"] is False
    assert detect_anomaly(history, method="mad")["anomaly"] is False
    # now a genuine drop as the current value; MAD should catch it
    drop = [1000, 1010, 500, 990, 1005, 100]
    assert detect_anomaly(drop, method="mad")["anomaly"] is True


def test_flat_baseline_any_change_flagged():
    v = da([0, 0, 0, 5], method="mad")
    assert v["anomaly"] is True
    assert v["score"] is None  # spread == 0 path


def test_insufficient_history():
    v = detect_anomaly([1, 2], method="mad")
    assert v["status"] == "insufficient_history"
    assert v["anomaly"] is False


def test_unknown_method_raises():
    with pytest.raises(ValueError, match="unknown method"):
        detect_anomaly([1, 2, 3, 4], method="wavelet")


# -- per-metric history from the store --------------------------------------- #


@pytest.fixture
def store(tmp_path):
    return ResultStore(f"sqlite:///{tmp_path / 'm.db'}")


def _save(store, n_rows, n_email_nulls, day):
    df = pd.DataFrame(
        {"id": range(n_rows), "email": ["a@b.com"] * (n_rows - n_email_nulls) + [None] * n_email_nulls}
    )
    suite = Suite.from_dict(
        {
            "suite": "orders",
            "dataset": "orders",
            "checks": [{"type": "row_count", "min": 1}, {"type": "not_null", "column": "email"}],
        }
    )
    store.save(suite.run(PandasBackend(df)), at=f"2026-01-{day}T00:00:00+00:00")


def test_metric_history_rows(store):
    _save(store, 100, 0, "01")
    _save(store, 90, 0, "02")
    hist = store.metric_history("orders", metric="rows")
    assert [v for _ts, v in hist] == [100.0, 90.0]  # chronological


def test_metric_history_per_check_failing_rows(store):
    _save(store, 100, 0, "01")
    _save(store, 100, 3, "02")  # 3 email nulls on day 2
    hist = store.metric_history(
        "orders", metric="failing_rows", check="not_null", column="email"
    )
    assert [v for _ts, v in hist] == [0.0, 3.0]


def test_metric_history_requires_check_for_per_check(store):
    _save(store, 10, 0, "01")
    with pytest.raises(ValueError, match="check=.* is required"):
        store.metric_history("orders", metric="failing_rows")


def test_metric_history_rejects_unknown_metric(store):
    _save(store, 10, 0, "01")
    with pytest.raises(ValueError, match="metric must be"):
        store.metric_history("orders", metric="p99_latency")
