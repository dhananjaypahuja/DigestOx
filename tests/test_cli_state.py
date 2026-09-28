"""Operational failures and private local state (review findings R5 and R6).

Expected filesystem and SQLite failures become stable JSON errors, while programming errors
still raise. Local state is created private, and existing state that other users can read is
refused with the command to fix it, never changed silently.
"""

import json
import os
import sqlite3
import stat

import pytest

from conftest import pulse, pulse_json, pulse_result
from customer_pulse import cli

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores permission bits"
)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def error_code(out):
    return json.loads(out)["error"]["code"]


# R5: expected failures are structured errors


def test_codex_reproduction_a_file_in_place_of_the_state_directory(project):
    (project / ".pulse").touch()
    code, out = pulse("init", "--json")
    assert code == 1
    assert error_code(out) == "state_path_not_a_directory"


@POSIX_ONLY
@NOT_ROOT
def test_denied_io_is_a_json_error(project):
    state_dir = project / ".pulse"
    state_dir.mkdir(mode=0o700)
    state_dir.chmod(0o500)  # private, but not writable
    try:
        code, out = pulse("init", "--json")
    finally:
        state_dir.chmod(0o700)
    assert code == 1
    assert error_code(out) == "permission_denied"


@pytest.mark.parametrize("command", ["status", "init"])
def test_a_corrupt_database_is_a_json_error(project, command):
    pulse("init")
    (project / ".pulse" / "pulse.db").write_bytes(b"this is not a database " * 64)
    code, out = pulse(command, "--json")
    assert code == 1
    assert error_code(out) == "database_unreadable"


def test_a_locked_database_is_a_json_error(project, monkeypatch):
    pulse("init")
    monkeypatch.setattr(cli.db, "LOCK_WAIT_SECONDS", 0.05)  # don't wait the full five seconds
    holder = sqlite3.connect(project / ".pulse" / "pulse.db", isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        code, out = pulse("status", "--json")
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert code == 1
    assert error_code(out) == "database_locked"


def test_human_errors_go_to_stderr_with_a_hint(project):
    (project / ".pulse").touch()
    result = pulse_result("init")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "error: " in result.stderr
    assert "not a directory" in result.stderr
    assert "hint: " in result.stderr


def test_programming_errors_are_not_hidden(project, monkeypatch):
    def broken(path):
        raise RuntimeError("a bug, not an operational failure")

    monkeypatch.setattr(cli.db, "inspect", broken)
    result = pulse_result("status", "--json")
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (sqlite3.OperationalError("database is locked"), "database_locked"),
        (sqlite3.OperationalError("unable to open database file"), "database_unavailable"),
        (sqlite3.OperationalError("attempt to write a readonly database"), "permission_denied"),
        (sqlite3.DatabaseError("file is not a database"), "database_unreadable"),
        (sqlite3.OperationalError("disk I/O error"), "database_error"),
        (FileExistsError(17, "File exists", ".pulse"), "state_path_not_a_directory"),
        (
            NotADirectoryError(20, "Not a directory", ".pulse/pulse.db"),
            "state_path_not_a_directory",
        ),
        (PermissionError(13, "Permission denied", ".pulse/pulse.db"), "permission_denied"),
        (OSError(28, "No space left on device", ".pulse/pulse.db"), "filesystem_error"),
    ],
)
def test_operational_failures_map_to_stable_codes(exc, code):
    assert cli.operational_error(exc).code == code


# R6: local state is private


@POSIX_ONLY
def test_new_state_is_created_private(project):
    code, _ = pulse_json("init")
    assert code == 0
    assert mode(project / ".pulse") == 0o700
    assert mode(project / ".pulse" / "pulse.db") == 0o600
    code, status = pulse_json("status")
    assert status["database"]["privacy_problems"] == []


@POSIX_ONLY
def test_codex_reproduction_an_existing_readable_state_directory_is_refused(project):
    state_dir = project / ".pulse"
    state_dir.mkdir()
    state_dir.chmod(0o755)
    code, out = pulse("init", "--json")
    error = json.loads(out)["error"]
    assert code == 1
    assert error["code"] == "state_dir_not_private"
    assert "chmod 700" in error["hint"]
    assert mode(state_dir) == 0o755  # nothing was changed silently
    assert not (state_dir / "pulse.db").exists()

    state_dir.chmod(0o700)  # the user applies the fix
    code, _ = pulse_json("init")
    assert code == 0
    assert mode(state_dir / "pulse.db") == 0o600


@POSIX_ONLY
def test_an_existing_readable_database_is_refused_and_reported(project):
    pulse("init")
    database = project / ".pulse" / "pulse.db"
    database.chmod(0o644)
    code, out = pulse("init", "--json")
    error = json.loads(out)["error"]
    assert code == 1
    assert error["code"] == "database_not_private"
    state_dir = (project / ".pulse").resolve()
    assert error["message"] == f"other users can read pulse.db (mode 0644) in {state_dir}"
    assert error["hint"] == f"run `chmod 600 '{state_dir / 'pulse.db'}'`"
    assert mode(database) == 0o644

    code, status = pulse_json("status")  # status reports it and changes nothing
    assert code == 0
    assert status["database"]["privacy_problems"] == [f"{database.resolve()} has mode 0644"]
    code, out = pulse("status")
    assert f"warning   local state isn't private: {database.resolve()} has mode 0644" in out


@POSIX_ONLY
def test_a_readable_sqlite_companion_file_is_refused(project):
    pulse("init")
    journal = project / ".pulse" / "pulse.db-journal"
    journal.write_bytes(b"")
    journal.chmod(0o644)
    code, out = pulse("init", "--json")
    assert code == 1
    assert error_code(out) == "database_not_private"


@POSIX_ONLY
def test_database_symlink_is_refused_without_following_it(project, tmp_path):
    state = project / ".pulse"
    state.mkdir(mode=0o700)
    target = tmp_path / "outside" / "pulse.db"
    state.joinpath("pulse.db").symlink_to(target)

    code, out = pulse("init", "--json")

    assert code == 1
    error = json.loads(out)["error"]
    assert error["code"] == "database_path_not_regular"
    link = state.resolve() / "pulse.db"  # the link itself, never its target
    assert error["message"] == f"{link} is a symbolic link, so Pulse won't open it"
    assert not target.exists()


def _link_to_a_private_file(state, tmp_path):
    target = tmp_path / "elsewhere.db"
    target.touch(mode=0o600)
    (state / "pulse.db").symlink_to(target)


@POSIX_ONLY
@pytest.mark.parametrize(
    ("make", "reason"),
    [
        pytest.param(_link_to_a_private_file, "is a symbolic link", id="link to a private file"),
        pytest.param(
            lambda state, tmp_path: (state / "pulse.db").mkdir(), "is not a regular file",
            id="directory",
        ),
        pytest.param(
            lambda state, tmp_path: os.mkfifo(state / "pulse.db"), "is not a regular file",
            id="fifo",
        ),
        pytest.param(
            lambda state, tmp_path: (state / "pulse.db-wal").symlink_to(tmp_path / "gone"),
            "is a symbolic link",
            id="dangling companion link",
        ),
    ],
)  # fmt: skip
def test_database_paths_pulse_wont_open_are_refused_and_reported(project, tmp_path, make, reason):
    state = project / ".pulse"
    state.mkdir(mode=0o700)
    make(state, tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    code, out = pulse("init", "--json")
    assert code == 1
    error = json.loads(out)["error"]
    assert error["code"] == "database_path_not_regular"
    assert error["message"].endswith(f"{reason}, so Pulse won't open it")
    assert sorted(path.name for path in tmp_path.iterdir()) == before  # nothing followed

    code, status = pulse_json("status")
    assert code == 0
    assert [p.endswith(reason) for p in status["database"]["privacy_problems"]] == [True]
