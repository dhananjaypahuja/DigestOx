import sqlite3

import pytest

from customer_pulse import db
from customer_pulse.errors import PulseError

SHIPPED = db.available_migrations()
LATEST = len(SHIPPED)

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
    "run_imports",
    "run_sessions",
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
    "publish_events",
    "llm_cache",
    "schema_migrations",
}

VIEWS = {
    "v_theme_resolution",
    "v_theme_unresolved",
    "v_effective_assignment",
    "v_issue_latest",
    "v_run_signals",
    "v_run_issue_observations",
    "v_run_issue_closures",
    "v_run_issue_state",
    "v_run_theme_facts",
    "v_run_theme_customers",
    "v_digest_theme_trend",
    "v_run_reported_after_closure",
    "v_run_theme_attention",
    "v_publish_steps",
    "v_last_published_doc",
}


def names(conn, kind):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,)).fetchall()
    return {row["name"] for row in rows if not row["name"].startswith("sqlite_")}


def test_migrations_create_every_table_and_view(conn):
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
    assert db.schema_version(conn) == LATEST


def test_applied_migrations_are_recorded_with_their_checksums(conn):
    rows = conn.execute("SELECT * FROM schema_migrations ORDER BY version").fetchall()
    assert [(row["version"], row["sha256"]) for row in rows] == [
        (m.version, m.sha256) for m in SHIPPED
    ]
    assert rows[0]["name"] == "initial"
    assert {row["applied_at"] for row in rows} == {"2026-10-12T17:00:00.000000Z"}


def test_an_existing_database_upgrades_in_order_and_keeps_its_data(db_path, clock, monkeypatch):
    conn = db.connect(db_path)
    monkeypatch.setattr(db, "available_migrations", lambda: SHIPPED[:1])
    assert db.migrate(conn, clock) == [1]
    conn.execute(
        "INSERT INTO accounts (account_id, name, created_at) VALUES (?, ?, ?)",
        ("acct_morrowvale", "Morrowvale Athletic Clubs", "2026-10-12T17:00:00.000000Z"),
    )
    monkeypatch.setattr(db, "available_migrations", lambda: SHIPPED)
    assert db.migrate(conn, clock) == list(range(2, LATEST + 1))
    assert conn.execute("SELECT name FROM accounts").fetchone()[0] == "Morrowvale Athletic Clubs"
    conn.close()


def test_a_failed_migration_leaves_no_trace(conn, clock, monkeypatch):
    broken = db.Migration(
        version=LATEST + 1,
        name="broken",
        sql="CREATE TABLE half_done (x INTEGER) STRICT;\nTHIS IS NOT SQL;\n",
        sha256="0" * 64,
    )
    monkeypatch.setattr(db, "available_migrations", lambda: [*SHIPPED, broken])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(conn, clock)
    assert not conn.in_transaction
    assert db.schema_version(conn) == LATEST
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


@pytest.mark.parametrize(
    ("versions", "text"),
    [
        ([2], "migration 0002"),
        ([2, 3], "migrations 0002 and 0003"),
        ([1, 2, 4], "migrations 0001, 0002, and 0004"),
    ],
)
def test_migrations_are_named_for_people(versions, text):
    assert db.describe_migrations(versions) == text


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute(
            "INSERT INTO account_domains (domain, account_id) VALUES (?, ?)",
            ("morrowvale.example", "acct_missing"),
        )


def test_migrations_are_numbered_without_gaps():
    assert [m.version for m in SHIPPED] == list(range(1, LATEST + 1))


def test_inspecting_a_missing_database_creates_nothing(tmp_path):
    path = tmp_path / "missing.db"
    report = db.inspect(path)
    assert report["initialized"] is False
    assert report["migrations_pending"] == list(range(1, LATEST + 1))
    assert not path.exists()


def test_inspecting_a_migrated_database_reports_counts(conn, db_path):
    report = db.inspect(db_path)
    assert report["initialized"] is True
    assert report["schema_version"] == report["latest_schema_version"] == LATEST
    assert report["migrations_pending"] == []
    assert report["migrations_modified"] == []
    assert set(report["counts"].values()) == {0}
    assert report["last_digest"] is None


def test_inspection_is_read_only(conn, db_path):
    before = db_path.read_bytes()
    db.inspect(db_path)
    assert db_path.read_bytes() == before
