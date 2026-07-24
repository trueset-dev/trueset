"""Tests for Step 1 hardening: duplicate-key detection and clean load errors."""

import pandas as pd
import pytest

from assay import PandasBackend, Suite, SuiteLoadError
from assay.reconcile import ValueParity
from assay.result import Status

# --- value_parity duplicate-key detection ---------------------------------- #


def _be(**cols) -> PandasBackend:
    return PandasBackend(pd.DataFrame(cols))


def test_value_parity_flags_duplicate_key_in_primary():
    # order_id 1 appears twice in the primary -> ambiguous join, must be caught.
    primary = _be(order_id=[1, 1, 2], amount=[10.0, 10.0, 20.0])
    ref = _be(id=[1, 2], amount=[10.0, 20.0])
    r = ValueParity(
        key="order_id", columns=["amount"], reference="source", ref_key="id"
    ).evaluate(primary, ref)
    assert r.status is Status.FAIL
    assert r.observed["duplicate_keys_primary"] == 1
    assert r.observed["duplicate_keys_reference"] == 0
    assert "duplicate key" in r.message


def test_value_parity_flags_duplicate_key_in_reference():
    primary = _be(id=[1, 2], amount=[10.0, 20.0])
    ref = _be(id=[1, 1, 2], amount=[10.0, 10.0, 20.0])
    r = ValueParity(key="id", columns=["amount"], reference="source").evaluate(primary, ref)
    assert r.observed["duplicate_keys_reference"] == 1
    assert r.status is Status.FAIL


def test_value_parity_clean_pass_has_no_duplicate_noise():
    primary = _be(id=[1, 2, 3], amount=[10.0, 20.0, 30.0])
    ref = _be(id=[1, 2, 3], amount=[10.0, 20.0, 30.0])
    r = ValueParity(key="id", columns=["amount"], reference="source").evaluate(primary, ref)
    assert r.status is Status.PASS
    assert r.observed["duplicate_keys_primary"] == 0
    assert r.message == ""


def test_value_parity_missing_key_column_is_error():
    primary = _be(id=[1, 2], amount=[10.0, 20.0])
    ref = _be(id=[1, 2], amount=[10.0, 20.0])
    r = ValueParity(key="ghost", columns=["amount"], reference="source").evaluate(primary, ref)
    assert r.status is Status.ERROR
    assert "missing in primary" in r.message


# --- loader error handling -------------------------------------------------- #


def test_from_dict_rejects_non_mapping():
    with pytest.raises(SuiteLoadError):
        Suite.from_dict(["not", "a", "mapping"])


def test_from_dict_rejects_non_list_checks():
    with pytest.raises(SuiteLoadError, match="must be a list"):
        Suite.from_dict({"suite": "t", "checks": {"type": "row_count"}})


def test_from_dict_reports_unknown_check_type_with_index():
    with pytest.raises(SuiteLoadError, match="check #2"):
        Suite.from_dict(
            {"suite": "t", "checks": [{"type": "row_count"}, {"type": "not_a_check"}]}
        )


def test_from_dict_reports_bad_arguments():
    with pytest.raises(SuiteLoadError, match="check #1"):
        # not_null requires a column; omitting it must fail at load, not run
        Suite.from_dict({"suite": "t", "checks": [{"type": "not_null"}]})


def test_from_yaml_missing_file():
    with pytest.raises(SuiteLoadError, match="not found"):
        Suite.from_yaml("does/not/exist.yml")


def test_from_yaml_malformed(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("checks: [ : : : unbalanced")
    with pytest.raises(SuiteLoadError, match="parse YAML"):
        Suite.from_yaml(bad)


def test_from_yaml_empty(tmp_path):
    empty = tmp_path / "empty.yml"
    empty.write_text("")
    with pytest.raises(SuiteLoadError, match="empty"):
        Suite.from_yaml(empty)
