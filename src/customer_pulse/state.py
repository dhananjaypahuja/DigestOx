"""Local state: the state directory and the database, kept private to the current user.

The database holds customer evidence (redacted, but still customers' words), so on POSIX
systems the state directory must be 0700 and the database and its SQLite companion files 0600.
Pulse creates them that way. It never silently changes the permissions of a directory or file
that already exists: an existing one that other users can read is refused, with the exact
command to fix it. Symbolic links and other non-regular database paths are refused so Pulse
cannot follow them outside the private state directory.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from customer_pulse.config import Config
from customer_pulse.errors import PulseError

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
_GROUP_AND_OTHER = 0o077
_COMPANION_SUFFIXES = ("-journal", "-wal", "-shm")


def permissions_apply() -> bool:
    """POSIX permission bits protect the state only on POSIX systems."""
    return os.name == "posix"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _exposed(path: Path) -> bool:
    return permissions_apply() and bool(_mode(path) & _GROUP_AND_OTHER)


def _present(path: Path) -> bool:
    """Whether a path exists, including a dangling symbolic link."""
    return path.exists() or path.is_symlink()


def _database_problem(path: Path) -> tuple[str, str] | None:
    """What stops Pulse using a database file as it is, as (error code, reason), or None.

    It reads the path with lstat, so a symbolic link is reported, never followed.
    """
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return "database_path_not_regular", "is a symbolic link"
    if not stat.S_ISREG(info.st_mode):
        return "database_path_not_regular", "is not a regular file"
    mode = stat.S_IMODE(info.st_mode)
    if permissions_apply() and mode & _GROUP_AND_OTHER:
        return "database_not_private", f"has mode {mode:04o}"
    return None


def database_files(db_path: Path) -> list[Path]:
    """The database and whichever SQLite companion files exist next to it."""
    companions = [db_path.with_name(db_path.name + suffix) for suffix in _COMPANION_SUFFIXES]
    return [path for path in (db_path, *companions) if _present(path)]


def _private_files(config: Config) -> list[Path]:
    """The database, its companions, and the log: every file that must stay private."""
    log = [config.log_path] if _present(config.log_path) else []
    return [*database_files(config.db_path), *log]


def privacy_problems(config: Config) -> list[str]:
    """Describe existing state that isn't private: readable by other users, or a database path
    Pulse won't open. Changes nothing."""
    if not permissions_apply() or not config.state_dir.is_dir():
        return []
    problems = []
    if _exposed(config.state_dir):
        problems.append(f"{config.state_dir} has mode {_mode(config.state_dir):04o}")
    for path in _private_files(config):
        if found := _database_problem(path):
            problems.append(f"{path} {found[1]}")
    return problems


def _refuse_unusable_database_files(config: Config) -> None:
    """Refuse a database or companion file that is a link, isn't a regular file, or that other
    users can read. Nothing is opened or followed first."""
    found = [
        (path, problem) for path in _private_files(config) if (problem := _database_problem(path))
    ]
    unusable = [
        f"{path} {reason}" for path, (code, reason) in found if code != "database_not_private"
    ]
    if unusable:
        them = "it" if len(unusable) == 1 else "them"
        raise PulseError(
            "database_path_not_regular",
            f"{'; '.join(unusable)}, so Pulse won't open {them}",
            hint=f"move {them} aside, or set pulse.state_dir to a private directory",
        )
    if found:
        listing = ", ".join(
            f"{path.name} ({reason.removeprefix('has ')})" for path, (_, reason) in found
        )
        commands = " ".join(f"'{path}'" for path, _ in found)
        raise PulseError(
            "database_not_private",
            f"other users can read {listing} in {config.state_dir}",
            hint=f"run `chmod 600 {commands}`",
        )


def prepare(config: Config) -> bool:
    """Create or validate the private state directory and database file.

    Returns True when this call created the database file.
    """
    state_dir = config.state_dir
    if state_dir.exists() and not state_dir.is_dir():
        raise PulseError(
            "state_path_not_a_directory",
            f"{state_dir} exists but is not a directory",
            hint="move it aside, or set pulse.state_dir to another path",
        )
    if not state_dir.exists():
        state_dir.mkdir(mode=PRIVATE_DIR_MODE, parents=True)
    elif _exposed(state_dir):
        raise PulseError(
            "state_dir_not_private",
            f"{state_dir} can be read by other users (mode {_mode(state_dir):04o}), and it would "
            "hold customer evidence",
            hint=f"run `chmod 700 '{state_dir}'`, or set pulse.state_dir to a private directory",
        )

    _refuse_unusable_database_files(config)

    created = False
    try:
        # Create the database file private before SQLite opens it; SQLite gives its journal
        # files the same permissions as the database. O_EXCL already refuses to follow a link;
        # O_NOFOLLOW says so explicitly where the platform has it.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        os.close(os.open(config.db_path, flags, PRIVATE_FILE_MODE))
        created = True
    except FileExistsError:
        pass
    return created


def append_log(config: Config, event: dict[str, Any]) -> None:
    """Append one event to the private log as a line of JSON.

    Callers log only what carries no customer content: event names, file names, IDs, and
    counts. The log is created 0600 and never followed through a symbolic link; an existing log
    that other users can read is refused, like the database.
    """
    path = config.log_path
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, PRIVATE_FILE_MODE)
    except OSError as exc:
        if path.is_symlink():
            raise PulseError(
                "database_path_not_regular",
                f"{path} is a symbolic link, so Pulse won't write to it",
                hint="move it aside",
            ) from exc
        raise
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise PulseError(
                "database_path_not_regular",
                f"{path} is not a regular file, so Pulse won't write to it",
                hint="move it aside",
            )
        if permissions_apply() and stat.S_IMODE(info.st_mode) & _GROUP_AND_OTHER:
            raise PulseError(
                "database_not_private",
                f"other users can read {path} (mode {stat.S_IMODE(info.st_mode):04o})",
                hint=f"run `chmod 600 '{path}'`",
            )
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def require_initialized(config: Config) -> None:
    """Check existing state before a command that reads or writes evidence. Creates nothing."""
    if not config.db_path.is_file() and not config.db_path.is_symlink():
        raise PulseError(
            "not_initialized",
            f"{config.db_path} doesn't exist",
            hint="run `pulse init` first",
        )
    if _exposed(config.state_dir):
        raise PulseError(
            "state_dir_not_private",
            f"{config.state_dir} can be read by other users (mode {_mode(config.state_dir):04o})",
            hint=f"run `chmod 700 '{config.state_dir}'`",
        )
    _refuse_unusable_database_files(config)
