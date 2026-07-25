"""Auto-calibrated thresholds (layer 1: data-derived suggestions).

The calibrated suggestions must (a) be opt-in — default output is unchanged —
(b) produce ranges the sample itself passes, and (c) build into real checks.
"""

import pandas as pd

from trueset import PandasBackend, Suite, build_check
from trueset.profile import profile_dataframe, suggest_from_profile


def _df():
    # amount 10..1000 with one high outlier; qty small ints; status categorical
    return pd.DataFrame(
        {
            "id": range(1, 101),
            "amount": [float(x) for x in list(range(10, 1000, 10)) + [50] * 2] [:100],
            "status": (["pending", "shipped", "delivered"] * 34)[:100],
        }
    )


def test_profile_has_percentiles_for_numeric():
    prof = profile_dataframe(_df())
    amount = next(c for c in prof.columns if c.name == "amount")
    assert amount.numeric_p01 is not None and amount.numeric_p99 is not None
    assert amount.numeric_p01 <= amount.numeric_p99


def test_default_suggest_is_unchanged_by_calibration_feature():
    prof = profile_dataframe(_df())
    plain = suggest_from_profile(prof)
    # default: row_count is a bare min:1, numeric range is min:0 only (no max)
    row = next(c for c in plain["checks"] if c["type"] == "row_count")
    assert row == {"type": "row_count", "min": 1}
    rng = [c for c in plain["checks"] if c["type"] == "in_range" and c["column"] == "amount"]
    assert rng and "max" not in rng[0] and rng[0]["min"] == 0


def test_calibrate_emits_data_driven_range_and_volume_band():
    prof = profile_dataframe(_df())
    cal = suggest_from_profile(prof, calibrate=True)

    rng = next(c for c in cal["checks"] if c["type"] == "in_range" and c["column"] == "amount")
    assert "min" in rng and "max" in rng
    assert rng["severity"] == "warn"                 # a proposal, not a hard gate
    assert rng["min"] <= 10 and rng["max"] >= 990     # bounds contain the data

    row = next(c for c in cal["checks"] if c["type"] == "row_count")
    assert row["min"] <= 100 <= row["max"] and row["severity"] == "warn"


def test_calibrated_range_never_fails_on_its_own_sample():
    df = _df()
    cal = suggest_from_profile(profile_dataframe(df), calibrate=True)
    # every calibrated check is warn, so the suite passes on the source data
    result = Suite.from_dict(cal).run(PandasBackend(df))
    assert result.passed
    # and the amount range in particular flags nothing on the sample
    amount_range = next(
        r for r in result.results
        if r.check == "in_range" and r.column == "amount"
    )
    assert amount_range.failing_rows == 0


def test_all_calibrated_specs_build():
    cal = suggest_from_profile(profile_dataframe(_df()), calibrate=True)
    for spec in cal["checks"]:
        build_check(dict(spec))  # raises if any spec is invalid
