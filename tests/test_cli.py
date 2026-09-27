"""The CLI end to end, on an empty working directory with a pinned clock."""

import json
import sys

import pytest
from typer.testing import CliRunner

from customer_pulse import __version__
from customer_pulse.cli import app


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_NOW", "2026-10-12T17:00:00Z")
    monkeypatch.delenv("PULSE_CONFIG", raising=False)
    (tmp_path / "pulse.toml").write_text(
        '[pulse]\ntimezone = "America/Los_Angeles"\n', encoding="utf-8"
    )
    return tmp_path


def pulse(*args):
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.stdout


def pulse_json(*args):
    code, out = pulse(*args, "--json")
    return code, json.loads(out)


def test_status_before_init_reports_an_uninitialized_database(project):
    code, status = pulse_json("status")
    assert code == 0
    assert status["database"]["initialized"] is False
    assert status["database"]["migrations_pending"] == [1]
    assert status["counts"] is None
    assert not (project / ".pulse").exists()  # status never creates anything


def test_init_creates_the_database_and_status_reads_it(project):
    code, init = pulse_json("init")
    assert code == 0
    assert init["created"] is True
    assert init["applied_migrations"] == [1]
    assert init["schema_version"] == 1
    assert init["timezone"] == "America/Los_Angeles"
    assert (project / ".pulse" / "pulse.db").is_file()

    code, status = pulse_json("status")
    assert code == 0
    assert status["pulse_version"] == __version__
    assert status["config"]["timezone"] == "America/Los_Angeles"
    assert status["database"]["initialized"] is True
    assert status["database"]["schema_version"] == 1
    assert status["database"]["migrations_pending"] == []
    assert status["counts"] == {
        "accounts": 0,
        "digests": 0,
        "imports": 0,
        "issues": 0,
        "sessions": 0,
        "signals": 0,
        "themes": 0,
    }
    assert status["last_digest"] is None


def test_init_is_idempotent(project):
    pulse("init")
    code, init = pulse_json("init")
    assert code == 0
    assert init["created"] is False
    assert init["applied_migrations"] == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_state_directory_is_private(project):
    pulse("init")
    assert (project / ".pulse").stat().st_mode & 0o077 == 0


def test_human_output_says_what_to_do_next(project):
    code, out = pulse("status")
    assert code == 0
    assert "Run `pulse init`" in out
    code, out = pulse("init")
    assert "applied migration 0001" in out
    code, out = pulse("status")
    assert "schema 1 of 1" in out
    assert "0 signals" in out


def test_errors_are_json_with_a_stable_code(project):
    (project / "pulse.toml").write_text('[pulse]\ntimezone = "Mars/Olympus"\n', encoding="utf-8")
    code, out = pulse("status", "--json")
    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_config"


def test_a_config_path_can_come_from_the_command_line(project, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    config = elsewhere / "custom.toml"
    config.write_text('[pulse]\ntimezone = "UTC"\nstate_dir = "state"\n', encoding="utf-8")
    code, init = pulse_json("--config", str(config), "init")
    assert code == 0
    assert init["timezone"] == "UTC"
    assert (elsewhere / "state" / "pulse.db").is_file()


def test_a_bad_pinned_clock_is_reported(project, monkeypatch):
    monkeypatch.setenv("PULSE_NOW", "yesterday")
    code, out = pulse("init", "--json")
    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_clock"


def test_version_flag(project):
    code, out = pulse("--version")
    assert code == 0
    assert out.strip() == f"pulse {__version__}"
