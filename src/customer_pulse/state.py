"""Local state: the state directory and the database, kept private to the current user.

The database holds customer evidence (redacted, but still customers' words), so on POSIX
systems the state directory must be 0700 and the database and its SQLite companion files 0600.
Pulse creates them that way. It never silently changes the permissions of a directory or file
that already exists: an existing one that other users can read is refused, with the exact
command to fix it. Symbolic links and other non-regular database paths are refused so Pulse
cannot follow them outside the private state directory.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

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


def _path_problem(path: Path) -> str | None:
    """Return a privacy/path problem without following an unsafe database path."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return f"{path} is a symbolic link"
    if not stat.S_ISREG(info.st_mode):
        return f"{path} is not a regular file"
    if _exposed(path):
        return f"{path} has mode {_mode(path):04o}"
    return None


def _is_unsafe_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)


def database_files(db_path: Path) -> list[Path]:
    """The database and whichever SQLite companion files exist next to it."""
    companions = [db_path.with_name(db_path.name + suffix) for suffix in _COMPANION_SUFFIXES]
    return [path for path in (db_path, *companions) if _present(path)]


def privacy_problems(config: Config) -> list[str]:
    """Describe any existing state that other users could read. Changes nothing."""
    if not permissions_apply() or not config.state_dir.is_dir():
        return []
    problems = []
    if _exposed(config.state_dir):
        problems.append(f"{config.state_dir} has mode {_mode(config.state_dir):04o}")
    problems.extend(
        problem for path in database_files(config.db_path) if (problem := _path_problem(path))
    )
    return problems


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

    for path in database_files(config.db_path):
        problem = _path_problem(path)
        if problem and _is_unsafe_path(path):
            raise PulseError(
                "database_path_not_regular",
                f"{problem}; Pulse will not follow it",
                hint="move it aside, or set pulse.state_dir to a private directory",
            )

    created = False
    try:
        # Create the database file private before SQLite opens it; SQLite gives its journal
        # files the same permissions as the database.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        os.close(os.open(config.db_path, flags, PRIVATE_FILE_MODE))
        created = True
    except FileExistsError:
        pass

    problems = [
        problem for path in database_files(config.db_path) if (problem := _path_problem(path))
    ]
    if problems:
        unsafe = [path for path in database_files(config.db_path) if _is_unsafe_path(path)]
        if unsafe:
            listing = ", ".join(problems)
            raise PulseError(
                "database_path_not_regular",
                f"{listing}; Pulse will not follow it",
                hint="move it aside, or set pulse.state_dir to a private directory",
            )
        listing = ", ".join(problems)
        exposed = [path for path in database_files(config.db_path) if _exposed(path)]
        commands = " ".join(f"'{path}'" for path in exposed)
        raise PulseError(
            "database_not_private",
            f"other users can read {listing} in {state_dir}",
            hint=f"run `chmod 600 {commands}`",
        )
    return created
