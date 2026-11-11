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


def test_referential_integrity_sql_pushdown_parity(tmp_path):
    """Same-engine anti-join must return the identical orphan count as the
    portable distinct-values path."""
    from sqlalchemy import create_engine

    from trueset import SQLAlchemyBackend
    from trueset.reconcile import ReferentialIntegrity

    prim = pd.DataFrame({"order_id": [1, 2, 3, 4, 5], "x": [1, 1, 1, 1, 1]})
    ref = pd.DataFrame({"oid": [1, 2, 3]})  # 4 and 5 are orphans
    chk = ReferentialIntegrity(column="order_id", reference="src", ref_column="oid")

    pandas_res = chk.evaluate(PandasBackend(prim), PandasBackend(ref))

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    prim.to_sql("primary", eng, index=False)
    ref.to_sql("refs", eng, index=False)
    sql_res = chk.evaluate(SQLAlchemyBackend(eng, "primary"), SQLAlchemyBackend(eng, "refs"))

    assert pandas_res.observed == sql_res.observed == 2
    assert pandas_res.status is Status.FAIL and sql_res.status is Status.FAIL


def test_value_parity_sql_pushdown_parity(tmp_path):
    """Same-engine value_parity (SQL inner-join + anti-joins) must return the
    identical observed counts as the in-memory key-map path."""
    from sqlalchemy import create_engine

    from trueset import SQLAlchemyBackend

    primary = pd.DataFrame({
        "order_id": [1, 2, 3, 4],              # 4 only-in-primary
        "amount": [10.0, 20.0, 30.0, 40.0],
        "status": ["a", "b", "x", "d"],        # id 3 status differs
    })
    ref = pd.DataFrame({
        "order_id": [1, 2, 3, 5],              # 5 only-in-reference
        "amount": [10.0, 20.0, 30.0, 50.0],
        "status": ["a", "b", "c", "e"],        # id 3: 'c' vs 'x'
    })
    chk = ValueParity(key="order_id", columns=["amount", "status"], reference="src")
    pandas_obs = chk.evaluate(PandasBackend(primary), PandasBackend(ref)).observed

    eng = create_engine(f"sqlite:///{tmp_path / 'vp.db'}")
    primary.to_sql("warehouse", eng, index=False)
    ref.to_sql("source", eng, index=False)
    sql_obs = chk.evaluate(
        SQLAlchemyBackend(eng, "warehouse"), SQLAlchemyBackend(eng, "source")
    ).observed

    assert pandas_obs == sql_obs
    assert sql_obs["mismatched_values"] == 1
    assert sql_obs["only_in_primary"] == 1
    assert sql_obs["only_in_reference"] == 1
    assert sql_obs["compared_keys"] == 3


# --- bug fixes from the second review (type coercion, self-join, both-paths) ---

def test_values_equal_edge_cases():
    assert not _values_equal("007", "7", 0.0)       # numeric-looking strings stay strings
    assert not _values_equal("1e3", "1000", 0.0)
    assert _values_equal(float("inf"), float("inf"), 0.0)
    assert not _values_equal(2**53 + 1, 2**53, 0.0)  # big ints keep precision
    assert _values_equal("10.0", 10.0, 0.0)          # number vs its string form
    assert _values_equal(Decimal("10.00"), 10.0, 0.0)


@pytest.mark.parametrize(
    "pv, rv, tol, expected",
    [
        (["007"], ["7"], 0.0, 1),     # strings differ
        (["abc"], ["abc"], 0.0, 0),
        ([10.0], [10.4], 0.0, 1),
        ([10.0], [10.4], 0.5, 0),     # within tolerance (pushed down too)
        ([None], [None], 0.0, 0),     # both null -> equal
        ([None], [5.0], 0.0, 1),      # one null -> differ
        ([10.0], [10.0], 0.0, 0),
    ],
)
def test_value_parity_both_paths_agree(tmp_path, pv, rv, tol, expected):
    """Every comparison case must give the same answer in-memory and same-engine."""
    from sqlalchemy import create_engine

    from trueset import SQLAlchemyBackend

    prim = pd.DataFrame({"id": [1], "v": pv})
    ref = pd.DataFrame({"id": [1], "v": rv})
    chk = ValueParity(key="id", columns=["v"], reference="r", tolerance=tol)
    mem = chk.evaluate(PandasBackend(prim), PandasBackend(ref)).observed["mismatched_values"]

    eng = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    prim.to_sql("a", eng, index=False)
    ref.to_sql("b", eng, index=False)
    sql = chk.evaluate(SQLAlchemyBackend(eng, "a"), SQLAlchemyBackend(eng, "b")).observed[
        "mismatched_values"
    ]
    assert mem == sql == expected


def test_reconcile_table_against_itself(tmp_path):
    """Self-reconciliation must not crash (value_parity) or silently pass
    (referential_integrity) -- the join/subquery alias the reference table."""
    from sqlalchemy import create_engine

    from trueset import SQLAlchemyBackend
    from trueset.reconcile import ReferentialIntegrity

    eng = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    pd.DataFrame({"id": [1, 2, 3], "child": [1, 2, 9]}).to_sql("t", eng, index=False)
    a = SQLAlchemyBackend(eng, "t")
    b = SQLAlchemyBackend(eng, "t")

    vp = ValueParity(key="id", columns=["child"], reference="self").evaluate(a, b)
    assert vp.observed["mismatched_values"] == 0  # a table always equals itself

    ri = ReferentialIntegrity(column="child", reference="self", ref_column="id").evaluate(a, b)
    assert ri.observed == 1  # child=9 has no matching id (was silently 0 before)


def test_value_parity_decimal_vs_float_money():
    """A warehouse NUMERIC vs a CSV float of the same money value must not be a
    false mismatch -- regression for Decimal('19.99') vs 19.99."""
    primary = pd.DataFrame(
        {"id": [1, 2, 3], "amt": [Decimal("19.99"), Decimal("5.00"), Decimal("100.10")]}
    )
    ref = pd.DataFrame({"id": [1, 2, 3], "amt": [19.99, 5.0, 100.10]})
    chk = ValueParity(key="id", columns=["amt"], reference="r")
    assert chk.evaluate(PandasBackend(primary), PandasBackend(ref)).observed[
        "mismatched_values"
    ] == 0
    # a genuine one-cent difference is still caught
    ref2 = pd.DataFrame({"id": [1, 2, 3], "amt": [19.99, 5.0, 100.11]})
    assert chk.evaluate(PandasBackend(primary), PandasBackend(ref2)).observed[
        "mismatched_values"
    ] == 1


def test_values_equal_decimal_money():
    assert _values_equal(Decimal("19.99"), 19.99, 0.0)
    assert _values_equal(Decimal("0.1"), 0.1, 0.0)
    assert not _values_equal(Decimal("19.99"), 19.98, 0.0)
