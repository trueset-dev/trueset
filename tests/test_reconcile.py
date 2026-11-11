"""Tests for cross-system reconciliation checks."""

import pandas as pd
import pytest

from trueset import PandasBackend, Suite
from trueset.reconcile import ReferentialIntegrity, RowCountParity, ValueParity
from trueset.result import Status


@pytest.fixture
def source():
    return PandasBackend(
        pd.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
                "status": ["a", "b", "c", "d", "e"],
            }
        )
    )


@pytest.fixture
def warehouse():
    # id 5 dropped, id 6 phantom, id 4 amount corrupted
    return PandasBackend(
        pd.DataFrame(
            {
                "order_id": [1, 2, 3, 4, 6],
                "amount": [10.0, 20.0, 30.0, 999.0, 60.0],
                "status": ["a", "b", "c", "d", "z"],
            }
        )
    )


def test_row_count_parity_equal_counts_pass(source, warehouse):
    # both have 5 rows -- parity passes even though contents differ
    r = RowCountParity(reference="source").evaluate(warehouse, source)
    assert r.status is Status.PASS


def test_referential_integrity_finds_orphan(source, warehouse):
    r = ReferentialIntegrity(
        column="order_id", reference="source", ref_column="id"
    ).evaluate(warehouse, source)
    assert r.status is Status.FAIL
    assert r.failing_rows == 1  # order_id 6 has no source id


def test_value_parity_reports_all_three_modes(source, warehouse):
    r = ValueParity(
        key="order_id",
        columns=["amount", "status"],
        reference="source",
        ref_key="id",
    ).evaluate(warehouse, source)
    assert r.status is Status.FAIL
    assert r.observed["mismatched_values"] == 1     # id 4 amount
    assert r.observed["only_in_primary"] == 1       # id 6
    assert r.observed["only_in_reference"] == 1     # id 5
    assert r.failing_rows == 3


def test_suite_resolves_named_reference(source, warehouse):
    suite = Suite.from_dict(
        {
            "suite": "recon",
            "checks": [
                {"type": "referential_integrity", "column": "order_id",
                 "reference": "source", "ref_column": "id"},
            ],
        }
    )
    result = suite.run(warehouse, references={"source": source})
    assert result.passed is False


def test_missing_reference_is_error_not_crash(warehouse):
    suite = Suite.from_dict(
        {
            "suite": "recon",
            "checks": [
                {"type": "row_count_parity", "reference": "nope"},
            ],
        }
    )
    result = suite.run(warehouse, references={})
    assert result.results[0].status is Status.ERROR
    assert "not provided" in result.results[0].message


# --- type- and tolerance-aware value comparison (cross-engine false mismatches) ---

from decimal import Decimal  # noqa: E402

import numpy as np  # noqa: E402

from trueset.reconcile import _values_equal  # noqa: E402


def _mismatches(primary_df, ref_df, columns=("amount",), **kw):
    chk = ValueParity(key="id", columns=list(columns), reference="ref", **kw)
    res = chk.evaluate(PandasBackend(primary_df), PandasBackend(ref_df))
    return res.observed["mismatched_values"]


def test_value_parity_normalizes_numeric_types():
    # Decimal vs float vs numeric-string must NOT read as a mismatch
    primary = pd.DataFrame({"id": [1, 2, 3], "amount": [Decimal("10.00"), 20.0, 30.0]})
    ref = pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, "20.0", 31.0]})
    assert _mismatches(primary, ref) == 1          # only id=3 (30 vs 31) truly differs


def test_value_parity_tolerance_absorbs_rounding():
    primary = pd.DataFrame({"id": [1, 2], "amount": [10.0, 20.0]})
    ref = pd.DataFrame({"id": [1, 2], "amount": [10.4, 20.0]})
    assert _mismatches(primary, ref) == 1                    # exact: 10.0 != 10.4
    assert _mismatches(primary, ref, tolerance=0.5) == 0     # within tolerance


def test_value_parity_missing_values():
    primary = pd.DataFrame({"id": [1, 2], "amount": [np.nan, 5.0]})
    both_nan = pd.DataFrame({"id": [1, 2], "amount": [np.nan, 5.0]})
    one_val = pd.DataFrame({"id": [1, 2], "amount": [7.0, 5.0]})
    assert _mismatches(primary, both_nan) == 0     # NaN == NaN
    assert _mismatches(primary, one_val) == 1      # NaN vs value differs


def test_values_equal_helper():
    assert _values_equal(Decimal("10.00"), 10.0, 0.0)
    assert _values_equal("10.0", 10.0, 0.0)
    assert _values_equal(float("nan"), float("nan"), 0.0)
    assert not _values_equal(float("nan"), 1.0, 0.0)
    assert _values_equal(True, 1, 0.0)             # exact bool/int type drift is fine
    assert not _values_equal(True, 1.4, 0.5)       # but bools aren't pulled into tolerance math
    assert _values_equal(10.0, 10.4, 0.5)
    assert not _values_equal(10.0, 10.4, 0.0)
    assert _values_equal("shipped", "shipped", 0.0)
    assert not _values_equal("shipped", "delivered", 0.0)
