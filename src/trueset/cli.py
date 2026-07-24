"""Command line interface.

    trueset run --data orders.csv --checks checks.yml
    trueset run --data orders.csv --checks checks.yml --json
    trueset list-checks

Exit code is non-zero when any ERROR-severity check fails, so it drops
straight into CI / dbt / Airflow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import pandas as pd
from rich.console import Console
from rich.table import Table

from .backends.pandas_backend import PandasBackend
from .checks import available_checks
from .governance import BY_DIMENSIONS, group_results
from .result import Status
from .suite import Suite, SuiteLoadError

console = Console()


def _load_data(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise click.ClickException(f"data file not found: {p}")
    suffix = p.suffix.lower()
    try:
        if suffix in {".csv", ".tsv"}:
            return pd.read_csv(p, sep="\t" if suffix == ".tsv" else ",")
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(p)
        if suffix == ".json":
            return pd.read_json(p)
    except Exception as exc:  # malformed file, unreadable, missing engine, ...
        raise click.ClickException(f"could not read {p}: {exc}") from exc
    raise click.ClickException(
        f"unsupported data format '{p.suffix}' (expected .csv/.tsv/.parquet/.json)"
    )


def _load_suite(path: str) -> Suite:
    try:
        return Suite.from_yaml(path)
    except SuiteLoadError as exc:
        raise click.ClickException(str(exc)) from exc


def _sql_backend(url: str, table: str):
    """Build a SQLAlchemyBackend, with friendly errors if [sql] is missing."""
    try:
        from sqlalchemy import create_engine

        from .backends.sqlalchemy_backend import SQLAlchemyBackend
    except Exception as exc:  # sqlalchemy not installed
        raise click.ClickException(
            "SQL sources need the [sql] extra:  pip install 'trueset[sql]'"
        ) from exc
    try:
        return SQLAlchemyBackend(create_engine(url), table)
    except Exception as exc:
        raise click.ClickException(f"could not open table '{table}' at {url}: {exc}") from exc


def _primary_backend(data: str | None, url: str | None, table: str | None):
    """Resolve the dataset under test: a file (--data) or a SQL table (--url/--table)."""
    if url:
        if not table:
            raise click.ClickException("--table is required when using --url")
        return _sql_backend(url, table)
    if not data:
        raise click.ClickException(
            "provide a source: --data <file>  OR  --url <sqlalchemy-url> --table <name>"
        )
    return PandasBackend(_load_data(data))


def _reference_backend(value: str):
    """A --ref value is either a file path or a SQL 'url::table' spec."""
    if "://" in value:  # looks like a SQLAlchemy URL
        url, sep, table = value.partition("::")
        if not sep:
            raise click.ClickException(
                f"SQL reference must be URL::TABLE, got: {value}"
            )
        return _sql_backend(url, table)
    return PandasBackend(_load_data(value))


def _render(result) -> None:
    table = Table(title=f"trueset :: {result.name}", show_lines=False)
    for col in ("check", "column", "status", "sev", "failing / total", "detail"):
        table.add_column(col)

    style = {Status.PASS: "green", Status.FAIL: "red", Status.ERROR: "yellow"}
    glyph = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.ERROR: "ERR "}

    for r in result.results:
        ft = ""
        if r.failing_rows is not None and r.total_rows is not None:
            ft = f"{r.failing_rows} / {r.total_rows}"
        table.add_row(
            r.check,
            r.column or "-",
            f"[{style[r.status]}]{glyph[r.status]}[/]",
            r.severity.value,
            ft,
            r.message or "",
        )
    console.print(table)
    c = result.counts
    verdict = "[green]PASSED[/]" if result.passed else "[red]FAILED[/]"
    console.print(
        f"{verdict}  pass={c['pass']} fail={c['fail']} "
        f"error={c['error']} (warn-only={c['warn']})"
    )


@click.group()
@click.version_option()
def cli() -> None:
    """trueset -- portable data quality checks."""


@cli.command()
@click.option("--data", default=None, help="Path to CSV/TSV/Parquet/JSON data.")
@click.option("--url", default=None, help="SQLAlchemy URL of a database to validate in place.")
@click.option("--table", default=None, help="Table name to validate (with --url).")
@click.option("--checks", "checks_path", required=True, help="Path to a checks YAML file.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def run(data: str | None, url: str | None, table: str | None, checks_path: str, as_json: bool) -> None:
    """Run a check suite against a dataset (a file, or a SQL table via --url/--table)."""
    backend = _primary_backend(data, url, table)
    suite = _load_suite(checks_path)
    result = suite.run(backend)

    if as_json:
        console.print_json(json.dumps(result.to_dict()))
        sys.exit(0 if result.passed else 1)

    _render(result)
    sys.exit(0 if result.passed else 1)


@cli.command()
@click.option("--data", default=None, help="Primary dataset file (the one being validated).")
@click.option("--url", default=None, help="SQLAlchemy URL for the primary (with --table).")
@click.option("--table", default=None, help="Primary table name (with --url).")
@click.option("--checks", "checks_path", required=True, help="Reconciliation checks YAML.")
@click.option(
    "--ref",
    "refs",
    multiple=True,
    metavar="NAME=SOURCE",
    help=(
        "A reference, repeatable. SOURCE is a file path (source=orders.csv) or a "
        "SQL table (source=postgresql://host/db::orders)."
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def reconcile(
    data: str | None,
    url: str | None,
    table: str | None,
    checks_path: str,
    refs: tuple[str, ...],
    as_json: bool,
) -> None:
    """Validate a dataset AGAINST other systems (cross-source reconciliation).

    Primary and each reference can independently be a file or a SQL table, so
    you can reconcile a warehouse against a source database directly."""
    primary = _primary_backend(data, url, table)
    references = {}
    for spec in refs:
        if "=" not in spec:
            raise click.ClickException(f"--ref must be NAME=SOURCE, got: {spec}")
        name, source = spec.split("=", 1)
        references[name] = _reference_backend(source)

    suite = _load_suite(checks_path)
    result = suite.run(primary, references=references)

    if as_json:
        console.print_json(json.dumps(result.to_dict()))
        sys.exit(0 if result.passed else 1)

    _render(result)
    sys.exit(0 if result.passed else 1)


@cli.command()
@click.option("--data", default=None, help="Path to CSV/TSV/Parquet/JSON data.")
@click.option("--url", default=None, help="SQLAlchemy URL of a database to validate in place.")
@click.option("--table", default=None, help="Table name to validate (with --url).")
@click.option("--checks", "checks_path", required=True, help="Path to a checks YAML file.")
@click.option(
    "--by",
    type=click.Choice(BY_DIMENSIONS),
    default="sensitivity",
    help="Governance dimension to group by.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON evidence.")
@click.option(
    "--fail/--no-fail",
    "fail_on_error",
    default=True,
    help="Exit non-zero if any error-severity check fails (default: --fail).",
)
def report(
    data: str | None,
    url: str | None,
    table: str | None,
    checks_path: str,
    by: str,
    as_json: bool,
    fail_on_error: bool,
) -> None:
    """Run a suite and report pass/fail grouped by governance metadata.

    Answers policy questions like "are any PII checks failing?" or "what's our
    GDPR posture?" by reading the deterministic results your checks already
    produce -- auditable evidence, no new engine work.
    """
    backend = _primary_backend(data, url, table)
    suite = _load_suite(checks_path)
    result = suite.run(backend)
    groups = group_results(result.results, by)

    if as_json:
        payload = {
            "suite": result.name,
            "by": by,
            "passed": result.passed,
            "groups": [
                {
                    "group": g["group"],
                    "counts": g["counts"],
                    "passed": g["passed"],
                    "checks": [r.to_dict() for r in g["results"]],
                }
                for g in groups
            ],
        }
        console.print_json(json.dumps(payload))
        sys.exit(0 if result.passed or not fail_on_error else 1)

    table_out = Table(title=f"governance report :: {result.name}  (by {by})")
    for col in (by, "checks", "pass", "fail", "error", "status"):
        table_out.add_column(col)
    for g in groups:
        c = g["counts"]
        n = c["pass"] + c["fail"] + c["error"]
        verdict = "[green]OK[/]" if g["passed"] else "[red]VIOLATION[/]"
        table_out.add_row(
            g["group"], str(n), str(c["pass"]), str(c["fail"]), str(c["error"]), verdict
        )
    console.print(table_out)

    # Call out the thing a compliance owner cares about most.
    sensitive_failures = [
        r for r in result.results if not r.ok and r.meta.is_sensitive
    ]
    if sensitive_failures:
        console.print(
            f"[red]⚠ {len(sensitive_failures)} failing check(s) on "
            f"sensitive (pii/pci/phi/confidential) data.[/]"
        )
    verdict = "[green]PASSED[/]" if result.passed else "[red]FAILED[/]"
    console.print(verdict)
    sys.exit(0 if result.passed or not fail_on_error else 1)


@cli.command()
@click.option("--data", required=True, help="Path to CSV/TSV/Parquet/JSON data.")
@click.option("--out", "out_path", default=None, help="Write draft suite to this YAML.")
@click.option("--ai", is_flag=True, help="Use the AI copilot (needs ANTHROPIC_API_KEY).")
@click.option("--describe", default=None, help="Plain-English intent (implies --ai).")
def suggest(data: str, out_path: str | None, ai: bool, describe: str | None) -> None:
    """Draft a check suite from your data (deterministic, or AI-assisted).

    Whatever the source, every proposed check is validated against the
    deterministic registry -- so the output is always something you can read,
    trust, and commit.
    """
    import yaml as _yaml

    from .profile import profile_dataframe, suggest_from_profile

    df = _load_data(data)

    if describe or ai:
        from .copilot import anthropic_completer, checks_from_profile, checks_from_text

        try:
            complete = anthropic_completer()
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
        if describe:
            suite = checks_from_text(describe, list(df.columns), complete)
        else:
            suite = checks_from_profile(profile_dataframe(df), complete)
    else:
        suite = suggest_from_profile(profile_dataframe(df))

    text = _yaml.safe_dump(suite, sort_keys=False)
    if out_path:
        Path(out_path).write_text(text)
        console.print(f"[green]wrote[/] {out_path}  ({len(suite['checks'])} checks)")
    else:
        console.print(text)


@cli.command()
@click.option("--data", required=True, help="Path to CSV/TSV/Parquet/JSON data.")
def profile(data: str) -> None:
    """Profile a dataset (stats + inferred semantic type per column)."""
    from .profile import profile_dataframe

    df = _load_data(data)
    prof = profile_dataframe(df)
    table = Table(title=f"profile :: {Path(data).name} ({prof.rows} rows)")
    for col in ("column", "dtype", "inferred", "nulls", "distinct", "unique"):
        table.add_column(col)
    for c in prof.columns:
        table.add_row(
            c.name, c.dtype, c.inferred, str(c.nulls), str(c.distinct), str(c.is_unique)
        )
    console.print(table)


@cli.command(name="list-checks")
def list_checks() -> None:
    """List available check types."""
    for name in available_checks():
        console.print(f"  - {name}")


if __name__ == "__main__":
    cli()
