import pandas as pd
import pytest

from assay import PandasBackend, Suite, validate_dataframe
from assay.checks import (
    ColumnsExist,
    InRange,
    InSet,
    MatchesRegex,
    NoDuplicateRows,
    NotNull,
    RowCount,
    Unique,
)
from assay.result import Severity, Status


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 3, 5],
            "amount": [10, 20, -5, 40, None],
            "status": ["a", "b", "a", "z", "b"],
            "email": ["x@y.com", "bad", "p@q.io", "m@n.co", "e@f.gg"],
        }
    )


@pytest.fixture
def be(df):
    return PandasBackend(df)


def test_not_null_detects_nulls(be):
    assert NotNull("amount").evaluate(be).status is Status.FAIL
    assert NotNull("id").evaluate(be).status is Status.PASS


def test_unique_counts_duplicates(be):
    r = Unique("id").evaluate(be)
    assert r.status is Status.FAIL
    assert r.failing_rows == 1  # the duplicated 3


def test_in_set(be):
    assert InSet("status", ["a", "b"]).evaluate(be).failing_rows == 1  # 'z'


def test_in_range_ignores_nulls(be):
    r = InRange("amount", min=0).evaluate(be)
    assert r.failing_rows == 1  # only -5; null skipped


def test_regex(be):
    r = MatchesRegex("email", r"[^@\s]+@[^@\s]+\.[^@\s]+").evaluate(be)
    assert r.failing_rows == 1  # 'bad'


def test_row_count(be):
    assert RowCount(min=10).evaluate(be).status is Status.FAIL
    assert RowCount(min=1, max=100).evaluate(be).status is Status.PASS


def test_no_duplicate_rows(be):
    assert NoDuplicateRows().evaluate(be).status is Status.PASS  # no full-row dup


def test_missing_column_errors(be):
    assert NotNull("nope").evaluate(be).status is Status.ERROR


def test_columns_exist(be):
    assert ColumnsExist(["id", "ghost"]).evaluate(be).status is Status.FAIL


def test_severity_controls_pass(be):
    # a failing check marked warn should not fail the suite
    warn = NotNull("amount", severity=Severity.WARN).evaluate(be)
    assert warn.status is Status.FAIL
    assert warn.ok is True  # warn-only failures are "ok" for the run verdict


def test_suite_from_dict_runs(df):
    suite = Suite.from_dict(
        {
            "suite": "t",
            "checks": [
                {"type": "unique", "column": "id"},
                {"type": "row_count", "min": 1},
            ],
        }
    )
    result = suite.run(PandasBackend(df))
    assert result.passed is False  # id has a duplicate
    assert len(result.results) == 2


def test_validate_dataframe_helper(df):
    result = validate_dataframe(
        df, Suite.from_dict({"suite": "t", "checks": [{"type": "row_count", "min": 1}]})
    )
    assert result.passed is True
