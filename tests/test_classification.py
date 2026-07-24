"""Tests for deterministic data classification (PII/PCI suggestion)."""

import pandas as pd

from trueset import build_check
from trueset.profile import (
    _is_credit_card,
    _is_phone,
    profile_dataframe,
    suggest_from_profile,
)


def _sens(df, col):
    prof = profile_dataframe(df)
    return next(c.sensitivity for c in prof.columns if c.name == col)


def test_email_phone_ssn_are_pii():
    df = pd.DataFrame(
        {
            "email": ["a@b.com", "c@d.org", "e@f.io"],
            "phone": ["+1 (415) 555-0100", "415-555-0101", "(212) 555-0199"],
            "ssn": ["123-45-6789", "987-65-4321", "555-12-3456"],
        }
    )
    assert _sens(df, "email") == "pii"
    assert _sens(df, "phone") == "pii"
    assert _sens(df, "ssn") == "pii"


def test_iban_and_credit_card_are_pci():
    df = pd.DataFrame(
        {
            "iban": ["GB82WEST12345698765432", "DE89370400440532013000", "FR7630006000011234567890189"],
            "card_str": ["4111 1111 1111 1111", "5500-0055-5555-5559", "340000000000009"],
        }
    )
    assert _sens(df, "iban") == "pci"
    assert _sens(df, "card_str") == "pci"


def test_credit_card_as_bare_integer_is_pci():
    df = pd.DataFrame({"card": [4111111111111111, 5500005555555559, 340000000000009]})
    assert _sens(df, "card") == "pci"


def test_plain_columns_have_no_sensitivity():
    df = pd.DataFrame({"id": [1, 2, 3], "qty": [10, 20, 30], "note": ["x", "y", "z"]})
    assert _sens(df, "id") is None
    assert _sens(df, "qty") is None
    assert _sens(df, "note") is None


def test_id_column_not_mistaken_for_card_or_phone():
    # sequential small ints must NOT trip Luhn/phone detection
    df = pd.DataFrame({"order_id": [1001, 1002, 1003, 1004]})
    assert _sens(df, "order_id") is None


def test_luhn_and_phone_predicates():
    assert _is_credit_card("4111 1111 1111 1111") is True  # valid Luhn
    assert _is_credit_card("4111 1111 1111 1112") is False  # bad Luhn
    assert _is_credit_card("12345") is False  # too short
    assert _is_phone("+1 (415) 555-0100") is True
    assert _is_phone("hello") is False
    assert _is_phone("42") is False  # too few digits


def test_suggested_checks_are_pretagged_and_still_build():
    df = pd.DataFrame({"email": ["a@b.com", "c@d.org"]})
    suite = suggest_from_profile(profile_dataframe(df))
    email_checks = [c for c in suite["checks"] if c.get("column") == "email"]
    assert email_checks and all(c["sensitivity"] == "pii" for c in email_checks)
    # crucially: the pre-tagged specs must round-trip through the trust gate
    for spec in email_checks:
        check = build_check(dict(spec))
        assert check.meta.sensitivity == "pii"
