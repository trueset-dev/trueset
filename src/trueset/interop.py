"""Interop: adopt trueset without rewriting your existing tests.

The first importer targets **dbt**, because a dbt team should be able to point
trueset at their `schema.yml` and get a runnable suite in one command -- then run
that same suite on any engine, or reconcile the dbt output against its source.

dbt column tests map cleanly onto trueset checks:

    dbt test            -> trueset check
    not_null            -> not_null
    unique              -> unique
    accepted_values     -> in_set
    relationships       -> referential_integrity   (needs a --ref at run time)

Anything without a mapping (custom/singular dbt tests, macros) is skipped and
reported -- never silently dropped -- and every produced check is validated
through `build_check`, so the output is always something trueset can actually run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .checks import build_check


@dataclass
class DbtImport:
    """Result of importing a dbt schema: one suite per model/source table."""

    suites: dict[str, dict[str, Any]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def _parse_test(test: Any) -> tuple[str, dict[str, Any]] | None:
    """Normalize a dbt test entry to (name, args). Handles both the shorthand
    string form (`not_null`) and the mapping form (`{accepted_values: {...}}`)."""
    if isinstance(test, str):
        return test, {}
    if isinstance(test, dict) and len(test) == 1:
        name, args = next(iter(test.items()))
        return str(name), dict(args or {})
    return None


def _severity(args: dict[str, Any]) -> str | None:
    """dbt severity ('warn'/'error') lives at the top level or under config; both
    match trueset's own severity values."""
    sev = args.get("severity")
    if sev is None and isinstance(args.get("config"), dict):
        sev = args["config"].get("severity")
    return str(sev).lower() if sev else None


def _ref_name(to: str) -> str:
    """Extract the model name from a dbt relationship target like `ref('customers')`."""
    inner = to
    if "(" in to and ")" in to:
        inner = to[to.index("(") + 1 : to.rindex(")")]
    return inner.strip().strip("'\"")


def _column_tests_to_checks(column: str, tests: list[Any], skipped: list[str]) -> list[dict]:
    checks: list[dict[str, Any]] = []
    for raw in tests or []:
        parsed = _parse_test(raw)
        if parsed is None:
            skipped.append(f"{column}: unrecognized test {raw!r}")
            continue
        name, args = parsed
        sev = _severity(args)

        if name == "not_null":
            spec = {"type": "not_null", "column": column}
        elif name == "unique":
            spec = {"type": "unique", "column": column}
        elif name == "accepted_values":
            spec = {"type": "in_set", "column": column, "values": args.get("values", [])}
        elif name == "relationships":
            spec = {
                "type": "referential_integrity",
                "column": column,
                "reference": _ref_name(str(args.get("to", ""))),
                "ref_column": args.get("field", "id"),
            }
        else:
            skipped.append(f"{column}: no trueset mapping for dbt test '{name}'")
            continue

        if sev in ("warn", "error"):
            spec["severity"] = sev
        checks.append(spec)
    return checks


def _tests_key(node: dict[str, Any]) -> list[Any]:
    """dbt used `tests:`; dbt >=1.8 prefers `data_tests:`. Accept either."""
    return node.get("data_tests") or node.get("tests") or []


def _model_to_suite(name: str, columns: list[dict], skipped: list[str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for col in columns or []:
        cname = col.get("name")
        if not cname:
            continue
        checks.extend(_column_tests_to_checks(cname, _tests_key(col), skipped))
    # Validate through the trust gate; drop (and report) anything that won't build.
    valid: list[dict[str, Any]] = []
    for spec in checks:
        try:
            build_check(dict(spec))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{name}: {spec.get('type')} did not validate ({exc})")
            continue
        valid.append(spec)
    return {"suite": name, "checks": valid}


def import_dbt_schema(schema: dict[str, Any]) -> DbtImport:
    """Convert a parsed dbt schema.yml dict into trueset suites (one per model
    and per source table)."""
    result = DbtImport()
    for model in schema.get("models", []) or []:
        name = model.get("name")
        if not name:
            continue
        result.suites[name] = _model_to_suite(name, model.get("columns", []), result.skipped)
    for source in schema.get("sources", []) or []:
        src = source.get("name", "source")
        for tbl in source.get("tables", []) or []:
            tname = tbl.get("name")
            if not tname:
                continue
            key = f"{src}.{tname}"
            result.suites[key] = _model_to_suite(key, tbl.get("columns", []), result.skipped)
    return result


def import_dbt_file(path: str | Path) -> DbtImport:
    text = Path(path).read_text()
    schema = yaml.safe_load(text)
    if not isinstance(schema, dict):
        raise ValueError(f"{path} is not a dbt schema.yml (expected a mapping)")
    return import_dbt_schema(schema)
