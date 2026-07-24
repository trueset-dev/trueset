"""CLI tests for SQL sources (--url/--table and SQL --ref specs)."""

from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine  # noqa: E402

from trueset.cli import cli  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    eng = create_engine(f"sqlite:///{path}")
    for name, csv in (
        ("orders", "orders.csv"),
        ("source", "source_orders.csv"),
        ("warehouse", "warehouse_orders.csv"),
    ):
        pd.read_csv(EX / csv).to_sql(name, eng, index=False, if_exists="replace")
    return f"sqlite:///{path}"


def test_run_against_sql_table(db, tmp_path):
    checks = tmp_path / "c.yml"
    checks.write_text("suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(
        cli, ["run", "--url", db, "--table", "orders", "--checks", str(checks)]
    )
    assert res.exit_code == 0


def test_run_sql_url_without_table_errors(db, tmp_path):
    checks = tmp_path / "c.yml"
    checks.write_text("suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(cli, ["run", "--url", db, "--checks", str(checks)])
    assert res.exit_code != 0
    assert "--table is required" in res.output


def test_run_no_source_errors(tmp_path):
    checks = tmp_path / "c.yml"
    checks.write_text("suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(cli, ["run", "--checks", str(checks)])
    assert res.exit_code != 0
    assert "provide a source" in res.output


def test_reconcile_sql_primary_and_ref(db, tmp_path):
    res = CliRunner().invoke(
        cli,
        [
            "reconcile",
            "--url", db, "--table", "warehouse",
            "--checks", str(EX / "reconcile.yml"),
            "--ref", f"source={db}::source",
        ],
    )
    # reconcile.yml is designed to fail (orphan + value drift) -> exit 1, cleanly
    assert res.exit_code == 1
    assert "Traceback" not in res.output


def test_reconcile_malformed_sql_ref_errors(db, tmp_path):
    res = CliRunner().invoke(
        cli,
        [
            "reconcile",
            "--url", db, "--table", "warehouse",
            "--checks", str(EX / "reconcile.yml"),
            "--ref", f"source={db}",  # missing ::table
        ],
    )
    assert res.exit_code != 0
    assert "URL::TABLE" in res.output
