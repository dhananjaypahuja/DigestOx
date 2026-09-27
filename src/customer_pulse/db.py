"""SQLite storage: connections, numbered migrations, and a read-only inspection for status.

SQLite is the single source of truth. Migrations are plain SQL files shipped inside the
package (``customer_pulse/migrations/NNNN_name.sql``), applied in order, each in its own
transaction, and recorded with a checksum so an edited migration is caught instead of
silently drifting.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from customer_pulse.clock import Clock
from customer_pulse.errors import PulseError
from customer_pulse.timewin import to_db

# STRICT tables need 3.37; json_valid in CHECK constraints is built in from 3.38.
MIN_SQLITE_VERSION = (3, 38, 0)

_MIGRATION_NAME = re.compile(r"(\d{4})_([a-z0-9_]+)\.sql")

_CREATE_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    applied_at  TEXT NOT NULL
) STRICT
"""

# The tables `pulse status` counts, in display order.
COUNTED_TABLES = ("accounts", "imports", "signals", "issues", "themes", "digests", "sessions")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    sha256: str


def available_migrations() -> list[Migration]:
    """Read the migrations shipped with the package, checking they number 1, 2, 3, ..."""
    found = []
    for entry in files("customer_pulse").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.fullmatch(entry.name)
        if not match:
            continue
        sql = entry.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        found.append(Migration(int(match.group(1)), match.group(2), sql, digest))
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise PulseError(
            "migrations_out_of_sequence",
            f"migration files must be numbered 1, 2, 3, ... without gaps; found {versions}",
        )
    return found


def check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        needed = ".".join(map(str, MIN_SQLITE_VERSION))
        raise PulseError(
            "sqlite_too_old",
            f"Customer Pulse needs SQLite {needed} or newer; this Python has "
            f"{sqlite3.sqlite_version}",
            hint="use a Python build with a newer SQLite, for example one installed by uv",
        )


def connect(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a read-write connection with foreign keys enforced.

    The connection is in autocommit mode; callers manage transactions explicitly.
    """
    check_sqlite_version()
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _applied(conn: sqlite3.Connection) -> dict[int, str]:
    rows = conn.execute("SELECT version, sha256 FROM schema_migrations").fetchall()
    return {row[0]: row[1] for row in rows}


def _check_applied(applied: dict[int, str], available: list[Migration]) -> None:
    known = {m.version: m for m in available}
    unknown = sorted(set(applied) - set(known))
    if unknown:
        raise PulseError(
            "schema_too_new",
            f"the database has migrations {unknown} that this version of Customer Pulse "
            "doesn't know",
            hint="upgrade customer-pulse",
        )
    modified = sorted(v for v, sha in applied.items() if known[v].sha256 != sha)
    if modified:
        raise PulseError(
            "migration_modified",
            f"migrations {modified} changed after they were applied to this database",
            hint="add a new numbered migration instead of editing an applied one",
        )


def migrate(conn: sqlite3.Connection, clock: Clock) -> list[int]:
    """Apply pending migrations in order and return the versions applied."""
    conn.execute(_CREATE_SCHEMA_MIGRATIONS)
    available = available_migrations()
    applied = _applied(conn)
    _check_applied(applied, available)
    done = []
    for migration in available:
        if migration.version in applied:
            continue
        _apply(conn, migration, clock)
        done.append(migration.version)
    return done


def _apply(conn: sqlite3.Connection, migration: Migration, clock: Clock) -> None:
    # executescript runs the whole file; the script opens the transaction and the commit
    # happens only after the migration is recorded, so a failure anywhere leaves no trace.
    try:
        conn.executescript("BEGIN IMMEDIATE;\n" + migration.sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, sha256, applied_at) VALUES (?, ?, ?, ?)",
            (migration.version, migration.name, migration.sha256, to_db(clock.now())),
        )
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def schema_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_migrations"):
        return 0
    return conn.execute("SELECT coalesce(max(version), 0) FROM schema_migrations").fetchone()[0]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def inspect(path: Path) -> dict[str, Any]:
    """Describe the database for `pulse status` without creating or changing anything."""
    available = available_migrations()
    latest = available[-1].version if available else 0
    report: dict[str, Any] = {
        "path": str(path),
        "initialized": False,
        "schema_version": 0,
        "latest_schema_version": latest,
        "migrations_pending": [m.version for m in available],
        "migrations_modified": [],
        "counts": None,
        "last_digest": None,
    }
    if not path.is_file():
        return report
    check_sqlite_version()
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "schema_migrations"):
            return report
        applied = _applied(conn)
        known = {m.version: m for m in available}
        report["schema_version"] = max(applied, default=0)
        report["initialized"] = report["schema_version"] >= 1
        report["migrations_pending"] = [m.version for m in available if m.version not in applied]
        report["migrations_modified"] = sorted(
            v for v, sha in applied.items() if v in known and known[v].sha256 != sha
        )
        if report["initialized"]:
            # Table names come from the COUNTED_TABLES constant, never from input.
            report["counts"] = {
                table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in COUNTED_TABLES
            }
            row = conn.execute(
                "SELECT d.digest_id, d.status, r.window_start, r.window_end, d.created_at "
                "FROM digests AS d JOIN runs AS r ON r.run_id = d.run_id "
                "ORDER BY d.created_at DESC, d.digest_id DESC LIMIT 1"
            ).fetchone()
            report["last_digest"] = dict(row) if row else None
    return report
