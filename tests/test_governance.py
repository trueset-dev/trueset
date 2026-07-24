"""Tests for the governance metadata layer (additive; core stays unchanged)."""

import json

import pandas as pd
import pytest
from click.testing import CliRunner

from trueset import GovernanceMeta, PandasBackend, Suite, build_check
from trueset.checks import NotNull
from trueset.cli import cli
from trueset.governance import group_results, split_meta

# -- split_meta / GovernanceMeta -------------------------------------------- #


def test_split_meta_separates_governance_from_kwargs():
    rest, meta = split_meta(
        {"type": "not_null", "column": "ssn", "owner": "risk", "sensitivity": "pii"}
    )
    assert rest == {"type": "not_null", "column": "ssn"}
    assert meta.owner == "risk"
    assert meta.sensitivity == "pii"
    assert meta.is_sensitive is True


def test_governance_fields_do_not_crash_the_check_constructor():
    # The whole point of split_meta: these extra keys must not reach NotNull.__init__
    check = build_check(
        {
            "type": "not_null",
            "column": "email",
            "owner": "risk",
            "sensitivity": "pii",
            "regulation": ["gdpr", "ccpa"],
            "tags": ["identity"],
            "description": "must be present",
        }
    )
    assert isinstance(check, NotNull)
    assert check.meta.regulation == ["gdpr", "ccpa"]
    assert check.meta.description == "must be present"


def test_bare_string_regulation_and_tags_normalize_to_lists():
    meta = GovernanceMeta(regulation="gdpr", tags="pii")
    assert meta.regulation == ["gdpr"]
    assert meta.tags == ["pii"]


def test_invalid_sensitivity_rejected():
    with pytest.raises(ValueError, match="invalid sensitivity"):
        GovernanceMeta(sensitivity="ultra-secret")


def test_ungoverned_check_has_empty_meta():
    check = build_check({"type": "row_count", "min": 1})
    assert check.meta.is_set() is False


# -- meta rides onto results ------------------------------------------------- #


def test_meta_appears_on_result_via_suite():
    df = pd.DataFrame({"ssn": [None, "123-45-6789"]})
    suite = Suite.from_dict(
        {
            "suite": "t",
            "checks": [
                {"type": "not_null", "column": "ssn", "owner": "risk", "sensitivity": "pii"}
            ],
        }
    )
    result = suite.run(PandasBackend(df))
    r = result.results[0]
    assert r.meta.owner == "risk"
    assert r.to_dict()["meta"]["sensitivity"] == "pii"


def test_to_dict_omits_meta_when_unset():
    df = pd.DataFrame({"id": [1, 2]})
    result = Suite.from_dict(
        {"suite": "t", "checks": [{"type": "row_count", "min": 1}]}
    ).run(PandasBackend(df))
    assert "meta" not in result.results[0].to_dict()


# -- group_results ----------------------------------------------------------- #


def _run():
    df = pd.DataFrame({"amount": [10, -5], "email": ["a@b.com", "bad"]})
    return Suite.from_dict(
        {
            "suite": "g",
            "checks": [
                {"type": "in_range", "column": "amount", "min": 0,
                 "owner": "finance", "sensitivity": "confidential", "regulation": ["sox"]},
                {"type": "matches_regex", "column": "email",
                 "pattern": r"[^@\s]+@[^@\s]+\.[^@\s]+",
                 "owner": "risk", "sensitivity": "pii", "regulation": ["gdpr", "ccpa"]},
                {"type": "row_count", "min": 1},  # ungoverned
            ],
        }
    ).run(PandasBackend(df))


def test_group_by_sensitivity_orders_most_sensitive_first():
    groups = group_results(_run().results, "sensitivity")
    names = [g["group"] for g in groups]
    assert names == ["pii", "confidential", "(none)"]
    assert groups[-1]["group"] == "(none)"  # ungoverned bucket last


def test_group_by_regulation_explodes_lists():
    groups = {g["group"]: g for g in group_results(_run().results, "regulation")}
    assert set(groups) == {"gdpr", "ccpa", "sox", "(none)"}
    assert groups["gdpr"]["counts"]["fail"] == 1


def test_group_by_owner():
    groups = {g["group"]: g for g in group_results(_run().results, "owner")}
    assert groups["finance"]["counts"]["fail"] == 1
    assert groups["risk"]["counts"]["fail"] == 1


def test_group_by_invalid_dimension_raises():
    with pytest.raises(ValueError, match="cannot group by"):
        group_results(_run().results, "nonsense")


# -- report CLI -------------------------------------------------------------- #


def test_report_cli_json(tmp_path):
    data = tmp_path / "d.csv"
    data.write_text("amount\n10\n-5\n")
    checks = tmp_path / "c.yml"
    checks.write_text(
        "suite: t\nchecks:\n"
        "  - type: in_range\n    column: amount\n    min: 0\n"
        "    sensitivity: pii\n    owner: risk\n"
    )
    res = CliRunner().invoke(
        cli,
        ["report", "--data", str(data), "--checks", str(checks), "--by", "sensitivity", "--json"],
    )
    payload = json.loads(res.output)
    assert payload["by"] == "sensitivity"
    assert payload["passed"] is False
    assert payload["groups"][0]["group"] == "pii"
    assert res.exit_code == 1  # --fail is default


def test_report_cli_no_fail_exit_zero(tmp_path):
    data = tmp_path / "d.csv"
    data.write_text("amount\n10\n-5\n")
    checks = tmp_path / "c.yml"
    checks.write_text(
        "suite: t\nchecks:\n  - type: in_range\n    column: amount\n    min: 0\n    sensitivity: pii\n"
    )
    res = CliRunner().invoke(
        cli, ["report", "--data", str(data), "--checks", str(checks), "--no-fail"]
    )
    assert res.exit_code == 0
    assert "VIOLATION" in res.output
