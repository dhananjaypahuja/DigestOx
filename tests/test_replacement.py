"""Nothing a finished run, review, or publishing relies on can be replaced or deleted.

SQLite's REPLACE conflict resolution deletes the conflicting row without firing UPDATE
triggers. Every connection enables recursive triggers (Codex's re-review, ca5cadd), so that
deletion fires DELETE triggers, and every table guarded against UPDATE also guards DELETE
(migration 0005). Window: local days 2026-10-05..2026-10-11 in Los Angeles.
"""

import re
import sqlite3

import pytest

from conftest import ts

START, END = "2026-10-05T07:00:00Z", "2026-10-12T07:00:00Z"


def replace(conn, table, where, **changes):
    """INSERT OR REPLACE the row matching ``where``, with ``changes`` applied and its key kept."""
    clause = " AND ".join(f"{column} = ?" for column in where)
    query = f"SELECT * FROM {table} WHERE {clause}"
    row = dict(conn.execute(query, tuple(where.values())).fetchone())
    row.update(changes)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({marks})", tuple(row.values())
    )


def run_facts(conn, run):
    """What the run counted: its signals, its issues' states, and its window."""
    signals = conn.execute(
        "SELECT signal_id, account_id, occurred_at FROM v_run_signals WHERE run_id = ? "
        "ORDER BY signal_id",
        (run,),
    ).fetchall()
    issues = conn.execute(
        "SELECT issue_number, state_at_cutoff FROM v_run_issue_state WHERE run_id = ? "
        "ORDER BY issue_number",
        (run,),
    ).fetchall()
    window = conn.execute(
        "SELECT window_start, window_end, cutoff, status FROM runs WHERE run_id = ?", (run,)
    ).fetchone()
    return [tuple(row) for row in signals], [tuple(row) for row in issues], tuple(window)


@pytest.fixture
def finished(build):
    """A finished run that counted a signal, an issue, and an engineering session."""
    build.account("acct_morrowvale", "Morrowvale Athletic Clubs")
    build.account("acct_copperfen", "Copperfen Fitness")
    signal = build.signal("C1:1", "2026-10-06T00:00:00Z", account="acct_morrowvale")
    build.issue(142, closed_at="2026-10-07T00:00:00Z")
    build.session("bivo-s1", "2026-10-08T00:00:00Z")
    build.evidence("bivo-s1", "bivo/wearable_sync/sync.py", committed_at="2026-10-08T00:00:00Z")
    return {"run": build.run(START, END), "signal": signal}


def test_every_connection_enforces_keys_and_fires_delete_guards_on_replacement(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA recursive_triggers").fetchone()[0] == 1


def test_every_table_guarded_against_updates_also_guards_deletes(conn):
    """Replacement bypasses UPDATE triggers, so an UPDATE guard alone protects nothing."""
    events = {}
    for table, sql in conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'trigger'"
    ):
        head = sql.split("BEGIN", 1)[0]
        event = re.search(r"\b(INSERT|UPDATE|DELETE)\b", head, re.IGNORECASE).group(1).upper()
        events.setdefault(table, set()).add(event)
    unguarded = sorted(
        t for t, found in events.items() if "UPDATE" in found and "DELETE" not in found
    )
    assert unguarded == []


@pytest.mark.parametrize(
    ("table", "changes", "message"),
    [
        pytest.param(
            "signals",
            {"account_id": "acct_copperfen", "occurred_at": ts("2026-10-09T00:00:00Z")},
            "signals are evidence and are kept",
            id="a signal's customer and time",
        ),
        pytest.param(
            "runs",
            {"window_start": ts("2026-09-01T07:00:00Z"), "status": "running"},
            "runs are kept",
            id="a run's window and status",
        ),
        pytest.param(
            "sessions",
            {"stopped_at": ts("2026-10-20T00:00:00Z")},
            "a session is kept once a run has used it",
            id="a used session's stop time",
        ),
        pytest.param(
            "issues",
            {"created_at": ts("2026-11-01T00:00:00Z")},
            "issues are kept",
            id="an issue's creation time",
        ),
    ],
)
def test_review_reproduction_replacement_cannot_rewrite_what_a_run_counted(
    build, finished, table, changes, message
):
    """Before migration 0005, each of these replacements succeeded and changed the run's facts."""
    keys = {
        "signals": {"signal_id": finished["signal"]},
        "runs": {"run_id": finished["run"]},
        "sessions": {"session_name": "bivo-s1"},
        "issues": {"issue_number": 142},
    }
    before = run_facts(build.conn, finished["run"])
    with pytest.raises(sqlite3.IntegrityError, match=message):
        replace(build.conn, table, keys[table], **changes)
    assert run_facts(build.conn, finished["run"]) == before


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        ("DELETE FROM signals", "signals are evidence and are kept"),
        ("DELETE FROM runs", "runs are kept"),
        ("DELETE FROM sessions", "a session is kept once a run has used it"),
        ("DELETE FROM issues", "issues are kept"),
    ],
)
def test_what_a_run_counted_cant_be_deleted(build, finished, statement, message):
    before = run_facts(build.conn, finished["run"])
    with pytest.raises(sqlite3.IntegrityError, match=message):
        build.conn.execute(statement)
    assert run_facts(build.conn, finished["run"]) == before


def test_an_issue_keeps_its_creation_time_but_its_title_can_change(build, finished):
    with pytest.raises(sqlite3.IntegrityError, match="creation time is fixed"):
        build.conn.execute(
            "UPDATE issues SET created_at = ? WHERE issue_number = 142",
            (ts("2026-11-01T00:00:00Z"),),
        )
    build.conn.execute(
        "UPDATE issues SET title = 'Wearable sync drops workouts' WHERE issue_number = 142"
    )


def test_a_session_no_run_has_used_can_still_be_refreshed_or_dropped(build, finished):
    build.session("bivo-s2", "2026-10-13T00:00:00Z")
    replace(
        build.conn, "sessions", {"session_name": "bivo-s2"}, stopped_at=ts("2026-10-13T01:00:00Z")
    )
    build.conn.execute("DELETE FROM sessions WHERE session_name = 'bivo-s2'")
    assert build.conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_reimports_update_in_place_and_the_field_rules_judge_them(build, finished):
    """The path readers will use: an upsert fires UPDATE triggers, so fixed fields stay fixed."""
    batch = build.import_batch("slack", new=True)
    upsert = (
        "INSERT INTO signals (source, source_key, account_id, author_name, occurred_at, "
        "text_redacted, raw_sha256, first_import_id, last_import_id) "
        "VALUES ('slack', 'C1:1', ?, 'Example Person', ?, ?, ?, ?, ?) "
        "ON CONFLICT (source, source_key) DO UPDATE SET account_id = excluded.account_id, "
        "text_redacted = excluded.text_redacted, last_import_id = excluded.last_import_id"
    )
    at = ts("2026-10-06T00:00:00Z")
    build.conn.execute(upsert, ("acct_morrowvale", at, "edited text", "0" * 64, batch, batch))
    text = build.conn.execute("SELECT text_redacted FROM signals WHERE source_key = 'C1:1'")
    assert text.fetchone()[0] == "edited text"
    with pytest.raises(sqlite3.IntegrityError, match="customer"):
        build.conn.execute(upsert, ("acct_copperfen", at, "edited text", "0" * 64, batch, batch))


def test_replacement_cannot_rewrite_review_history(build, finished):
    build.theme("th_0001")
    build.theme("th_0002")
    build.merge("th_0001", "th_0002")
    assignment = build.assign(finished["signal"], "th_0002", run=finished["run"])
    correction = build.correction()
    cases = [
        ("themes", {"theme_id": "th_0001"}, {"status": "active", "merged_into": None}, "themes"),
        ("assignments", {"assignment_id": assignment}, {"theme_id": "th_0001"}, "assignments"),
        ("corrections", {"correction_id": correction}, {"command": "theme merge"}, "corrections"),
    ]
    for table, where, changes, message in cases:
        with pytest.raises(sqlite3.IntegrityError, match=message):
            replace(build.conn, table, where, **changes)
    merged = build.conn.execute("SELECT merged_into FROM themes WHERE theme_id = 'th_0001'")
    assert merged.fetchone()[0] == "th_0002"


def test_replacement_cannot_rewrite_a_runs_evidence_or_snapshot(build, finished):
    run = finished["run"]
    batch = build.conn.execute(
        "SELECT import_id FROM issue_observations WHERE issue_number = 142"
    ).fetchone()[0]
    evidence = build.conn.execute("SELECT evidence_id FROM session_evidence").fetchone()[0]
    cases = [
        (
            "issue_observations",
            {"issue_number": 142, "import_id": batch},
            {"state": "OPEN", "closed_at": None},
            "issue observations are history",
        ),
        (
            "session_evidence",
            {"evidence_id": evidence},
            {"level": "reported", "commit_sha": None, "committed_at": None},
            "evidence is (history|fixed)",
        ),
        ("run_imports", {"run_id": run, "import_id": batch}, {}, "snapshot is (fixed|recorded)"),
        (
            "run_sessions",
            {"run_id": run, "session_name": "bivo-s1"},
            {},
            "snapshot is (fixed|recorded)",
        ),
    ]
    before = run_facts(build.conn, run)
    for table, where, changes, message in cases:
        with pytest.raises(sqlite3.IntegrityError, match=message):
            replace(build.conn, table, where, **changes)
    assert run_facts(build.conn, run) == before
