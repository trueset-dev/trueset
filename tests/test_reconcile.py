"""Tests for cross-system reconciliation checks."""

import pandas as pd
import pytest

from assay import PandasBackend, Suite
from assay.reconcile import ReferentialIntegrity, RowCountParity, ValueParity
from assay.result import Status


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
