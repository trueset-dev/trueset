"""Tests for dbt schema.yml -> trueset suite import."""

from trueset import Suite
from trueset.interop import import_dbt_file, import_dbt_schema

SCHEMA = {
    "version": 2,
    "models": [
        {
            "name": "orders",
            "columns": [
                {"name": "order_id", "tests": ["not_null", "unique"]},
                {
                    "name": "status",
                    "tests": [
                        {"accepted_values": {"values": ["a", "b"], "config": {"severity": "warn"}}}
                    ],
                },
                {
                    "name": "customer_id",
                    "tests": [{"relationships": {"to": "ref('customers')", "field": "id"}}],
                },
                {"name": "notes", "data_tests": ["custom_macro"]},
            ],
        }
    ],
}


def test_basic_test_mapping():
    suites = import_dbt_schema(SCHEMA).suites
    checks = suites["orders"]["checks"]
    types = [c["type"] for c in checks]
    assert types == ["not_null", "unique", "in_set", "referential_integrity"]


def test_accepted_values_and_severity():
    checks = import_dbt_schema(SCHEMA).suites["orders"]["checks"]
    in_set = next(c for c in checks if c["type"] == "in_set")
    assert in_set["column"] == "status"
    assert in_set["values"] == ["a", "b"]
    assert in_set["severity"] == "warn"


def test_relationships_maps_to_referential_integrity():
    checks = import_dbt_schema(SCHEMA).suites["orders"]["checks"]
    ri = next(c for c in checks if c["type"] == "referential_integrity")
    assert ri == {
        "type": "referential_integrity",
        "column": "customer_id",
        "reference": "customers",  # ref('customers') -> customers
        "ref_column": "id",
    }


def test_unmappable_test_is_reported_not_dropped():
    result = import_dbt_schema(SCHEMA)
    assert any("custom_macro" in s for s in result.skipped)


def test_top_level_severity_is_honored():
    schema = {
        "models": [
            {"name": "m", "columns": [{"name": "c", "tests": [{"not_null": {"severity": "warn"}}]}]}
        ]
    }
    check = import_dbt_schema(schema).suites["m"]["checks"][0]
    assert check["severity"] == "warn"


def test_sources_are_imported():
    schema = {
        "sources": [
            {"name": "raw", "tables": [{"name": "orders", "columns": [{"name": "id", "tests": ["unique"]}]}]}
        ]
    }
    suites = import_dbt_schema(schema).suites
    assert "raw.orders" in suites
    assert suites["raw.orders"]["checks"][0]["type"] == "unique"


def test_imported_suite_is_runnable():
    # The whole promise: the output must load and run as a real trueset suite.
    suite_spec = import_dbt_schema(SCHEMA).suites["orders"]
    suite = Suite.from_dict(suite_spec)
    assert len(suite.checks) == 4


def test_import_from_file(tmp_path):
    import yaml

    p = tmp_path / "schema.yml"
    p.write_text(yaml.safe_dump(SCHEMA))
    assert "orders" in import_dbt_file(p).suites
