import sqlite3

import pytest

from customer_pulse import db
from customer_pulse.errors import PulseError

TABLES = {
    "accounts",
    "account_domains",
    "mappings",
    "imports",
    "issues",
    "issue_observations",
    "signals",
    "signal_revisions",
    "runs",
    "themes",
    "code_areas",
    "code_area_paths",
    "theme_code_areas",
    "digests",
    "corrections",
    "assignments",
    "links",
    "sessions",
    "session_evidence",
    "publish_steps",
    "llm_cache",
    "schema_migrations",
}

VIEWS = {
    "v_theme_resolution",
    "v_effective_assignment",
    "v_issue_latest",
    "v_run_signals",
    "v_run_theme_facts",
    "v_run_theme_customers",
    "v_digest_theme_trend",
    "v_run_reported_after_closure",
    "v_run_theme_attention",
    "v_last_published_doc",
}


def names(conn, kind):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,)).fetchall()
    return {row["name"] for row in rows if not row["name"].startswith("sqlite_")}


def test_migration_creates_every_table_and_view(conn):
    assert names(conn, "table") == TABLES
    assert names(conn, "view") == VIEWS


def test_every_view_runs_on_an_empty_database(conn):
    for view in sorted(VIEWS):
        assert conn.execute(f"SELECT * FROM {view}").fetchall() == []


def test_every_table_is_strict(conn):
    rows = conn.execute("PRAGMA table_list").fetchall()
    strict = {row["name"]: row["strict"] for row in rows if row["type"] == "table"}
    assert all(strict[table] == 1 for table in TABLES)


def test_migrating_again_does_nothing(conn, clock):
    assert db.migrate(conn, clock) == []
    assert db.schema_version(conn) == 1


def test_applied_migrations_are_recorded_with_their_checksum(conn):
    row = conn.execute("SELECT * FROM schema_migrations").fetchone()
    assert (row["version"], row["name"]) == (1, "initial")
    assert row["sha256"] == db.available_migrations()[0].sha256
    assert row["applied_at"] == "2026-10-12T17:00:00.000000Z"


def test_a_failed_migration_leaves_no_trace(conn, clock, monkeypatch):
    shipped = db.available_migrations()
    broken = db.Migration(
        version=2,
        name="broken",
        sql="CREATE TABLE half_done (x INTEGER) STRICT;\nTHIS IS NOT SQL;\n",
        sha256="0" * 64,
    )
    monkeypatch.setattr(db, "available_migrations", lambda: [*shipped, broken])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(conn, clock)
    assert not conn.in_transaction
    assert db.schema_version(conn) == 1
    assert "half_done" not in names(conn, "table")


def test_an_edited_migration_is_refused(conn, clock):
    conn.execute("UPDATE schema_migrations SET sha256 = ? WHERE version = 1", ("f" * 64,))
    with pytest.raises(PulseError) as caught:
        db.migrate(conn, clock)
    assert caught.value.code == "migration_modified"


def test_a_database_from_a_newer_pulse_is_refused(conn, clock):
    conn.execute(
        "INSERT INTO schema_migrations VALUES (99, 'future', ?, '2027-01-01T00:00:00.000000Z')",
        ("a" * 64,),
    )
    with pytest.raises(PulseError) as caught:
        db.migrate(conn, clock)
    assert caught.value.code == "schema_too_new"


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            "INSERT INTO account_domains (domain, account_id) VALUES (?, ?)",
            ("morrowvale.example", "acct_missing"),
        )


def test_migrations_are_numbered_without_gaps():
    versions = [m.version for m in db.available_migrations()]
    assert versions == list(range(1, len(versions) + 1))


def test_inspecting_a_missing_database_creates_nothing(tmp_path):
    path = tmp_path / "missing.db"
    report = db.inspect(path)
    assert report["initialized"] is False
    assert report["migrations_pending"] == [1]
    assert not path.exists()


def test_inspecting_a_migrated_database_reports_counts(conn, db_path):
    report = db.inspect(db_path)
    assert report["initialized"] is True
    assert report["schema_version"] == report["latest_schema_version"] == 1
    assert report["migrations_pending"] == []
    assert report["migrations_modified"] == []
    assert set(report["counts"].values()) == {0}
    assert report["last_digest"] is None


def test_inspection_is_read_only(conn, db_path):
    before = db_path.read_bytes()
    db.inspect(db_path)
    assert db_path.read_bytes() == before
