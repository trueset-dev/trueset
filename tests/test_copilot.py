"""Tests for profiling and the AI copilot's trust gate.

The copilot is tested with a FAKE completer so we exercise the crucial
behaviour -- invalid / hallucinated checks are discarded -- without any
network or API key.
"""

import json

import pandas as pd
import pytest

from assay.copilot import checks_from_profile, checks_from_text
from assay.profile import profile_dataframe, suggest_from_profile


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4, 5],
            "status": ["pending", "shipped", "shipped", "delivered", "pending"],
            "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
            "email": ["a@b.com", "c@d.io", "e@f.net", "g@h.org", "i@j.co"],
        }
    )


def test_profile_infers_semantics(df):
    prof = profile_dataframe(df)
    by_name = {c.name: c for c in prof.columns}
    assert by_name["email"].inferred == "email"
    assert by_name["amount"].inferred == "numeric"
    assert by_name["status"].inferred == "categorical"
    assert by_name["order_id"].is_unique is True


def test_heuristic_suggester(df):
    suite = suggest_from_profile(profile_dataframe(df))
    types = [c["type"] for c in suite["checks"]]
    assert "columns_exist" in types
    assert "unique" in types          # order_id
    assert "in_set" in types          # status categorical
    assert "in_range" in types        # amount >= 0
    assert "matches_regex" in types   # email
    # every suggested check must be buildable
    from assay.checks import build_check
    for spec in suite["checks"]:
        build_check(dict(spec))


def test_copilot_discards_hallucinated_checks(df):
    """The trust gate: model returns 3 specs, only the 2 valid ones survive."""
    def fake_completer(system, user):
        return json.dumps([
            {"type": "not_null", "column": "order_id"},        # valid
            {"type": "quantum_entanglement", "column": "amount"},  # not a real check
            {"type": "in_set", "column": "status", "values": ["pending", "shipped"]},  # valid
        ])

    suite = checks_from_profile(profile_dataframe(df), fake_completer)
    types = [c["type"] for c in suite["checks"]]
    assert types == ["not_null", "in_set"]  # the fake type was dropped


def test_copilot_handles_fenced_and_prosey_output(df):
    def messy_completer(system, user):
        return "Sure! Here you go:\n```json\n" + json.dumps(
            [{"type": "row_count", "min": 1}]
        ) + "\n```"

    suite = checks_from_text("there should be at least one row", ["a"], messy_completer)
    assert suite["checks"] == [{"type": "row_count", "min": 1}]


def test_copilot_rejects_bad_arguments(df):
    def bad_args_completer(system, user):
        # 'in_set' with no 'values' should fail to build and be dropped
        return json.dumps([{"type": "in_set", "column": "status"}])

    suite = checks_from_profile(profile_dataframe(df), bad_args_completer)
    assert suite["checks"] == []
