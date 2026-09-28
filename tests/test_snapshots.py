"""Runs read only their evidence snapshot (migration 0002, review finding R2).

A later import feeds later runs, including valid earlier facts it reveals, but it can't
change a run that already exists. Window: local days 2026-10-05..2026-10-07 in Los Angeles,
cutoff 2026-10-08T07:00Z, unless a test says otherwise.
"""

import sqlite3

import pytest

from conftest import ts

START, END = "2026-10-05T07:00:00Z", "2026-10-08T07:00:00Z"


def count(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def closure_flags(conn, run):
    return count(conn, "SELECT count(*) FROM v_run_reported_after_closure WHERE run_id = ?", run)


def state(conn, run, issue):
    row = conn.execute(
        "SELECT state_at_cutoff, last_closed_before_cutoff FROM v_run_issue_state "
        "WHERE run_id = ? AND issue_number = ?",
        (run, issue),
    ).fetchone()
    return tuple(row) if row else None


def confirmed_report(build, key="C1:report", at="2026-10-06T12:00:00Z", issue=18):
    signal = build.signal(key, at)
    build.link(signal, issue, "reports", "confirmed")
    return signal


def test_a_later_import_cannot_change_an_existing_run(build):
    # Codex's reproduction: closed 2026-09-30, confirmed report 2026-10-06, cutoff 2026-10-08.
    build.issue(18, closed_at="2026-09-30T00:00:00Z", reason="COMPLETED")
    confirmed_report(build)
    run = build.run(START, END)
    assert closure_flags(build.conn, run) == 1
    assert state(build.conn, run, 18) == ("closed", ts("2026-09-30T00:00:00Z"))

    # An export after the cutoff shows the issue reopened.
    build.observe(18, build.import_batch("github", new=True), closed_at=None)

    assert closure_flags(build.conn, run) == 1
    assert state(build.conn, run, 18) == ("closed", ts("2026-09-30T00:00:00Z"))


def test_a_new_run_sees_the_later_export_honestly(build):
    build.issue(18, closed_at="2026-09-30T00:00:00Z", reason="COMPLETED")
    confirmed_report(build)
    build.observe(18, build.import_batch("github", new=True), closed_at=None)  # reopened later
    run = build.run(START, END)
    # The closure still happened before the report, so the flag stands; but the issue reopened
    # at a time the export can't place relative to the cutoff.
    assert closure_flags(build.conn, run) == 1
    assert state(build.conn, run, 18) == ("unknown", ts("2026-09-30T00:00:00Z"))


def test_a_later_export_can_supply_a_valid_earlier_fact_to_a_new_run(build):
    build.issue(18, closed_at=None)  # the first export shows the issue open
    confirmed_report(build)
    first = build.run(START, END)
    assert state(build.conn, first, 18) == ("open", None)
    assert closure_flags(build.conn, first) == 0

    # A later export reveals it had closed on 2026-10-06 at 01:00, before the report.
    build.observe(18, build.import_batch("github", new=True), closed_at="2026-10-06T01:00:00Z")
    second = build.run(START, END)

    assert state(build.conn, first, 18) == ("open", None)  # the existing run is unchanged
    assert closure_flags(build.conn, first) == 0
    assert state(build.conn, second, 18) == ("closed", ts("2026-10-06T01:00:00Z"))
    assert closure_flags(build.conn, second) == 1


@pytest.mark.parametrize(
    ("observations", "expected"),
    [
        # Each export in import order: None means the export shows the issue open.
        (["2026-10-01T00:00:00Z"], "closed"),
        (["2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z"], "closed"),  # re-exported, unchanged
        ([None, "2026-10-01T00:00:00Z"], "closed"),  # opened, then closed before the cutoff
        (["2026-10-01T00:00:00Z", None], "unknown"),  # reopened, when is unknown
        (["2026-10-01T00:00:00Z", "2026-10-09T00:00:00Z"], "unknown"),  # reopened, reclosed later
        (["2026-10-01T00:00:00Z", "2026-10-03T00:00:00Z"], "closed"),  # reclosed before cutoff
        (["2026-10-09T00:00:00Z"], "open"),  # closed only after the cutoff
        ([None], "open"),
    ],
)
def test_issue_state_at_the_cutoff_is_honest_about_reopens(build, observations, expected):
    build.issue(18, closed_at=observations[0])
    for closed_at in observations[1:]:
        build.observe(18, build.import_batch("github", new=True), closed_at=closed_at)
    run = build.run(START, END)
    assert state(build.conn, run, 18)[0] == expected


def test_issues_created_after_the_cutoff_have_no_state(build):
    batch = build.import_batch("github")
    build.insert(
        "issues",
        issue_number=30,
        title="Later issue",
        body_redacted="body",
        url="https://github.com/bivo-fictional/bivo-platform/issues/30",
        created_at=ts("2026-10-09T00:00:00Z"),
        first_import_id=batch,
        last_import_id=batch,
    )
    build.observe(30, batch, closed_at=None)
    run = build.run(START, END)
    assert state(build.conn, run, 30) is None


def test_a_later_message_cannot_change_an_existing_run(build):
    build.signal("C1:1", "2026-10-06T12:00:00Z")
    run = build.run(START, END)
    later = build.import_batch("slack", new=True)
    build.signal("C1:2", "2026-10-06T13:00:00Z", batch=later)  # inside the window, imported later
    assert count(build.conn, "SELECT count(*) FROM v_run_signals WHERE run_id = ?", run) == 1
    assert count(build.conn, "SELECT count(*) FROM v_run_signals") == 1


def test_a_run_snapshot_is_fixed_once_the_run_finishes(build):
    build.signal("C1:1", "2026-10-06T12:00:00Z")
    run = build.run(START, END)
    later = build.import_batch("slack", new=True)
    with pytest.raises(sqlite3.IntegrityError, match="only while the run is running"):
        build.insert("run_imports", run_id=run, import_id=later)
    with pytest.raises(sqlite3.IntegrityError, match="snapshot is fixed"):
        build.conn.execute("DELETE FROM run_imports WHERE run_id = ?", (run,))


def test_a_run_window_and_finished_status_are_fixed(build):
    run = build.run(START, END)
    with pytest.raises(sqlite3.IntegrityError, match="window and cutoff are fixed"):
        build.conn.execute(
            "UPDATE runs SET cutoff = ? WHERE run_id = ?", (ts("2026-10-07T07:00:00Z"), run)
        )
    with pytest.raises(sqlite3.IntegrityError, match="finished run"):
        build.conn.execute("UPDATE runs SET status = 'failed' WHERE run_id = ?", (run,))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("occurred_at", ts("2026-10-07T12:00:00Z")),
        ("account_id", "acct_copperfen"),
        ("thread_key", "C1:other"),
        ("is_pulse_output", 1),
    ],
)
def test_a_signals_evidence_is_fixed_at_its_first_import(build, column, value):
    build.account("acct_copperfen", "Copperfen Fitness")
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="fixed at its first import"):
        build.conn.execute(f"UPDATE signals SET {column} = ? WHERE signal_id = ?", (value, signal))


def test_a_signals_text_can_still_be_revised(build):
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    build.conn.execute(
        "UPDATE signals SET text_redacted = 'edited', last_import_id = ? WHERE signal_id = ?",
        (build.import_batch("slack", new=True), signal),
    )


def test_issue_observations_are_history(build):
    build.issue(18, closed_at="2026-09-30T00:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="history"):
        build.conn.execute("UPDATE issue_observations SET closed_at = NULL")
    with pytest.raises(sqlite3.IntegrityError, match="history"):
        build.conn.execute("DELETE FROM issue_observations")


def test_session_evidence_is_fixed_once_a_run_uses_it(build):
    session = build.session("fix", "2026-10-06T20:00:00Z")
    build.evidence(session, "bivo/wearable_sync/tokens.py", committed_at="2026-10-06T19:50:00Z")
    build.run(START, END)
    with pytest.raises(sqlite3.IntegrityError, match="fixed once a run has used it"):
        build.evidence(session, "bivo/wearable_sync/sync.py")
    with pytest.raises(sqlite3.IntegrityError, match="fixed once a run has used it"):
        build.conn.execute(
            "UPDATE sessions SET stopped_at = ? WHERE session_name = ?",
            (ts("2026-10-09T00:00:00Z"), session),
        )


def test_a_later_session_cannot_change_an_existing_runs_attention(build):
    build.theme("th_0003")
    build.theme_area("th_0003", build.area("wearable_sync", "bivo/wearable_sync/"))
    run = build.run(START, END)
    session = build.session("late-reconcile", "2026-10-06T20:00:00Z")  # stopped in the window
    build.evidence(session, "bivo/wearable_sync/tokens.py", committed_at="2026-10-06T19:50:00Z")
    assert (
        count(build.conn, "SELECT count(*) FROM v_run_theme_attention WHERE run_id = ?", run) == 0
    )
    later_run = build.run(START, END)
    attention = count(
        build.conn, "SELECT count(*) FROM v_run_theme_attention WHERE run_id = ?", later_run
    )
    assert attention == 1
