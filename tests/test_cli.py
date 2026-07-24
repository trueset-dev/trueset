"""CLI smoke + error-handling tests via Click's CliRunner (no subprocess)."""

from click.testing import CliRunner

from assay.cli import cli


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_run_happy_path_exit_zero(tmp_path):
    data = _write(tmp_path, "d.csv", "id,amount\n1,10\n2,20\n")
    checks = _write(tmp_path, "c.yml", "suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(cli, ["run", "--data", data, "--checks", checks])
    assert res.exit_code == 0


def test_run_failing_check_exit_nonzero(tmp_path):
    data = _write(tmp_path, "d.csv", "id,amount\n1,10\n1,20\n")
    checks = _write(tmp_path, "c.yml", "suite: t\nchecks:\n  - type: unique\n    column: id\n")
    res = CliRunner().invoke(cli, ["run", "--data", data, "--checks", checks])
    assert res.exit_code == 1


def test_run_missing_data_file_is_clean_error(tmp_path):
    checks = _write(tmp_path, "c.yml", "suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(cli, ["run", "--data", "nope.csv", "--checks", checks])
    assert res.exit_code != 0
    assert "data file not found" in res.output
    assert "Traceback" not in res.output


def test_run_bad_check_type_is_clean_error(tmp_path):
    data = _write(tmp_path, "d.csv", "id\n1\n")
    checks = _write(tmp_path, "c.yml", "suite: t\nchecks:\n  - type: bogus\n")
    res = CliRunner().invoke(cli, ["run", "--data", data, "--checks", checks])
    assert res.exit_code != 0
    assert "check #1" in res.output
    assert "Traceback" not in res.output


def test_run_json_output_is_valid(tmp_path):
    import json

    data = _write(tmp_path, "d.csv", "id\n1\n2\n")
    checks = _write(tmp_path, "c.yml", "suite: t\nchecks:\n  - type: row_count\n    min: 1\n")
    res = CliRunner().invoke(cli, ["run", "--data", data, "--checks", checks, "--json"])
    payload = json.loads(res.output)
    assert payload["passed"] is True
    assert payload["suite"] == "t"


def test_list_checks_lists_registry():
    res = CliRunner().invoke(cli, ["list-checks"])
    assert res.exit_code == 0
    assert "not_null" in res.output
    assert "value_parity" in res.output
