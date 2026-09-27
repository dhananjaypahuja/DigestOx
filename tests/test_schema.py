"""The schema's invariants, and the views that compute Pulse's facts.

Session 1 ships the whole schema, so these tests pin its behaviour before any feature code
depends on it. Dates: the test window is local days 2026-10-05..2026-10-11 in Los Angeles,
which is [2026-10-05T07:00Z, 2026-10-12T07:00Z).
"""

import sqlite3

import pytest

from conftest import sha, ts

START, END = "2026-10-05T07:00:00Z", "2026-10-12T07:00:00Z"


def rows(conn, sql, *params):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# Invariants enforced by the schema


def test_timestamps_must_be_stored_in_fixed_width_utc(build):
    batch = build.import_batch()
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.insert(
            "signals",
            source="slack",
            source_key="C1:1",
            occurred_at="2026-10-05 09:00:00",
            text_redacted="hi",
            raw_sha256=sha("hi"),
            first_import_id=batch,
            last_import_id=batch,
        )


@pytest.mark.parametrize(
    ("start", "end", "cutoff"),
    [
        (START, END, "2026-10-12T07:00:00.000001Z"),  # cutoff after the window end
        (START, END, START),  # cutoff at the start: an empty evidence range
        (END, START, START),  # window reversed
    ],
)
def test_a_run_cutoff_must_sit_inside_its_window(build, start, end, cutoff):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.run(start, end, cutoff)


def test_a_run_window_is_all_or_nothing(build):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.insert(
            "runs",
            kind="digest",
            mode="offline",
            window_start=ts(START),
            window_end=ts(END),
            cutoff=ts(END),
            started_at=build.now,
            status="running",
        )  # no timezone


def test_corrections_are_append_only(build):
    correction = build.correction()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        build.conn.execute(
            "UPDATE corrections SET note = 'x' WHERE correction_id = ?", (correction,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        build.conn.execute("DELETE FROM corrections WHERE correction_id = ?", (correction,))


def test_assignments_are_append_only(build):
    run = build.run(START, END)
    build.theme("th_0001")
    assignment = build.assign(build.signal("C1:1", "2026-10-06T12:00:00Z"), "th_0001", run=run)
    with pytest.raises(sqlite3.IntegrityError, match="history"):
        build.conn.execute("DELETE FROM assignments WHERE assignment_id = ?", (assignment,))


def test_assignments_carry_their_source(build):
    build.theme("th_0001")
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # a person needs a correction
        build.insert(
            "assignments", signal_id=signal, theme_id="th_0001", set_by="person",
            created_at=build.now,
        )  # fmt: skip
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # the model needs a run
        build.insert(
            "assignments", signal_id=signal, theme_id="th_0001", set_by="model",
            created_at=build.now,
        )  # fmt: skip


@pytest.mark.parametrize(
    ("relation", "found_by", "status", "reviewed"),
    [
        ("references", "code", "confirmed", True),  # a mention can't be confirmed as a claim
        ("references", "model", "observed", False),  # mentions are found by code only
        ("reports", "model", "observed", False),  # a report needs review
        ("reports", "model", "confirmed", False),  # confirmation needs a logged correction
    ],
)
def test_a_mention_is_never_a_report(build, relation, found_by, status, reviewed):
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.insert(
            "links",
            signal_id=signal,
            issue_number=142,
            relation=relation,
            found_by=found_by,
            review_status=status,
            correction_id=build.correction() if reviewed else None,
            created_at=build.now,
        )


def test_approved_digest_content_is_frozen(build):
    digest = build.digest("dg_0001", build.run(START, END), approved=True)
    with pytest.raises(sqlite3.IntegrityError, match="cannot change"):
        build.conn.execute(
            "UPDATE digests SET content_md = 'edited', content_sha256 = ? WHERE digest_id = ?",
            (sha("edited"), digest),
        )


def test_approval_must_match_the_content_hash(build):
    run = build.run(START, END)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.insert(
            "digests",
            digest_id="dg_0001",
            run_id=run,
            content_md="# Digest",
            content_sha256=sha("# Digest"),
            status="approved",
            approved_sha256=sha("something else"),
            approved_at=build.now,
            created_at=build.now,
        )


def test_publish_steps_act_only_on_the_approved_hash(build):
    run = build.run(START, END)
    draft = build.digest("dg_0001", run)
    approved = build.digest("dg_0002", run, approved=True)
    good = build.conn.execute(
        "SELECT approved_sha256 FROM digests WHERE digest_id = ?", (approved,)
    ).fetchone()[0]

    def step(digest, approved_sha256):
        build.insert(
            "publish_steps",
            digest_id=digest,
            step="doc_written",
            status="done",
            approved_sha256=approved_sha256,
            updated_at=build.now,
        )

    with pytest.raises(sqlite3.IntegrityError, match="approved content hash"):
        step(draft, sha("# Digest dg_0001"))  # never approved
    with pytest.raises(sqlite3.IntegrityError, match="approved content hash"):
        step(approved, "b" * 64)  # a different version
    step(approved, good)
    with pytest.raises(sqlite3.IntegrityError, match="approved content hash"):
        build.conn.execute("UPDATE publish_steps SET approved_sha256 = ?", ("c" * 64,))


# Views


def test_a_person_assignment_wins_over_a_later_model_run(build):
    for theme in ("th_0001", "th_0002"):
        build.theme(theme)
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    build.assign(signal, "th_0001", run=build.run(START, END))
    build.assign(signal, "th_0002", person=True)
    build.assign(signal, "th_0001", run=build.run(START, END))  # a later model run disagrees
    effective = rows(build.conn, "SELECT theme_id, set_by FROM v_effective_assignment")
    assert effective == [{"theme_id": "th_0002", "set_by": "person"}]


def test_merged_themes_resolve_to_the_theme_that_survives(build):
    build.theme("th_0001")
    build.theme("th_0002", merged_into="th_0001")
    build.theme("th_0003", merged_into="th_0002")  # merged twice over
    signal = build.signal("C1:1", "2026-10-06T12:00:00Z")
    build.assign(signal, "th_0003", run=build.run(START, END))
    effective = rows(build.conn, "SELECT theme_id, assigned_theme_id FROM v_effective_assignment")
    assert effective == [{"theme_id": "th_0001", "assigned_theme_id": "th_0003"}]


def test_run_evidence_is_half_open_and_excludes_pulse_output(build):
    run = build.run(START, END, cutoff="2026-10-10T07:00:00Z")
    inside = [
        build.signal("C1:start", START),
        build.signal("C1:last", "2026-10-10T06:59:59.999999Z"),
    ]
    build.signal("C1:before", "2026-10-05T06:59:59.999999Z")
    build.signal("C1:at-cutoff", "2026-10-10T07:00:00Z")
    build.signal("C1:pulse", "2026-10-06T12:00:00Z", pulse_output=True)
    counted = rows(build.conn, "SELECT signal_id FROM v_run_signals WHERE run_id = ?", run)
    assert sorted(row["signal_id"] for row in counted) == sorted(inside)


def test_theme_facts_count_customers_threads_and_review_state(build):
    build.account("acct_morrowvale", "Morrowvale Athletic Clubs")
    build.account("acct_copperfen", "Copperfen Fitness")
    build.theme("th_0003")
    run = build.run(START, END)
    signals = [
        build.signal("C1:1", "2026-10-06T12:00:00Z", account="acct_morrowvale", thread="C1:1"),
        build.signal("C1:2", "2026-10-06T13:00:00Z", account="acct_morrowvale", thread="C1:1"),
        build.signal("C2:1", "2026-10-07T12:00:00Z", account="acct_copperfen", thread="C2:1"),
        build.signal("T-9", "2026-10-08T12:00:00Z", source="csv"),  # unattributed
    ]
    for signal in signals[:3]:
        build.assign(signal, "th_0003", run=run)
    build.assign(signals[3], "th_0003", person=True)
    facts = rows(build.conn, "SELECT * FROM v_run_theme_facts WHERE run_id = ?", run)[0]
    assert facts["signal_count"] == 4
    assert facts["thread_count"] == 3
    assert facts["affected_customer_count"] == 2
    assert facts["unattributed_count"] == 1
    assert (facts["confirmed_assignment_count"], facts["proposed_assignment_count"]) == (1, 3)
    assert (facts["first_seen"], facts["last_seen"]) == (
        ts("2026-10-06T12:00:00Z"),
        ts("2026-10-08T12:00:00Z"),
    )
    customers = rows(
        build.conn, "SELECT account_name FROM v_run_theme_customers ORDER BY account_name"
    )
    assert [row["account_name"] for row in customers] == [
        "Copperfen Fitness",
        "Morrowvale Athletic Clubs",
    ]


def test_reported_after_closure_allows_a_closure_before_the_window(build):
    run = build.run(START, END)
    build.issue(18, closed_at="2026-09-30T18:00:00Z", reason="COMPLETED")  # a week earlier
    build.issue(19, closed_at="2026-10-08T18:00:00Z", reason="COMPLETED")  # after the report
    report = build.signal("C1:report", "2026-10-06T12:00:00Z")
    build.link(report, 18, "reports", "confirmed")
    build.link(report, 19, "reports", "confirmed")
    unconfirmed = build.signal("C1:proposed", "2026-10-07T12:00:00Z")
    build.link(unconfirmed, 18, "reports", "proposed")
    mention = build.signal("C1:mention", "2026-10-07T13:00:00Z")
    build.link(mention, 18, "references", "observed")
    late = build.signal("C1:late", "2026-10-12T08:00:00Z")  # after the cutoff
    build.link(late, 18, "reports", "confirmed")

    flagged = rows(
        build.conn,
        "SELECT signal_id, issue_number, closed_at, state_reason "
        "FROM v_run_reported_after_closure WHERE run_id = ?",
        run,
    )
    assert flagged == [
        {
            "signal_id": report,
            "issue_number": 18,
            "closed_at": ts("2026-09-30T18:00:00Z"),
            "state_reason": "COMPLETED",
        }
    ]


def test_issue_state_comes_from_the_latest_import(build):
    build.issue(18, closed_at="2026-09-30T18:00:00Z")
    later = build.insert(
        "imports",
        source="github",
        file_name="issues-later.json",
        content_sha256=sha("later"),
        imported_at=build.now,
    )
    build.observe(18, later, closed_at=None)  # reopened in a later export
    latest = rows(build.conn, "SELECT state, closed_at FROM v_issue_latest")
    assert latest == [{"state": "OPEN", "closed_at": None}]


def test_engineering_attention_needs_the_theme_area_and_the_window(build):
    build.theme("th_0003")
    build.theme_area("th_0003", build.area("wearable_sync", "bivo/wearable_sync/"))
    run = build.run(START, END)
    verified = build.session("fix", "2026-10-08T20:00:00Z")
    build.evidence(verified, "bivo/wearable_sync/tokens.py", committed_at="2026-10-08T19:50:00Z")
    build.evidence(verified, "bivo/wearable_sync/sync.py")  # also edited without a commit
    reported = build.session("edit-only", "2026-10-09T20:00:00Z")
    build.evidence(reported, "bivo/wearable_sync/sync.py")
    elsewhere = build.session("sso", "2026-10-09T21:00:00Z")
    build.evidence(elsewhere, "bivo/sso/saml.py", committed_at="2026-10-09T20:50:00Z")
    after = build.session("too-late", "2026-10-12T08:00:00Z")
    build.evidence(after, "bivo/wearable_sync/sync.py", committed_at="2026-10-12T07:59:00Z")

    attention = rows(
        build.conn,
        "SELECT theme_id, session_name, level FROM v_run_theme_attention "
        "WHERE run_id = ? ORDER BY session_name",
        run,
    )
    assert attention == [
        {"theme_id": "th_0003", "session_name": "edit-only", "level": "reported"},
        {"theme_id": "th_0003", "session_name": "fix", "level": "verified"},
    ]


def test_trend_compares_each_digest_with_the_previous_one(build):
    for theme in ("th_0001", "th_0002", "th_0003"):
        build.theme(theme)
    week1 = build.run("2026-09-28T07:00:00Z", START)
    week2 = build.run(START, END)
    build.assign(build.signal("w1:a", "2026-09-29T12:00:00Z"), "th_0001", run=week1)
    build.assign(build.signal("w1:b", "2026-09-30T12:00:00Z"), "th_0003", run=week1)
    build.assign(build.signal("w2:a", "2026-10-06T12:00:00Z"), "th_0001", run=week2)
    build.assign(build.signal("w2:b", "2026-10-07T12:00:00Z"), "th_0001", run=week2)
    build.assign(build.signal("w2:c", "2026-10-08T12:00:00Z"), "th_0002", run=week2)
    build.digest("dg_0001", week1)
    build.digest("dg_0002", week2, previous="dg_0001")

    trend = rows(
        build.conn,
        "SELECT digest_id, theme_id, signal_count, previous_signal_count, trend "
        "FROM v_digest_theme_trend ORDER BY digest_id, theme_id",
    )
    assert trend == [
        {"digest_id": "dg_0001", "theme_id": "th_0001", "signal_count": 1,
         "previous_signal_count": 0, "trend": "no_previous"},
        {"digest_id": "dg_0001", "theme_id": "th_0003", "signal_count": 1,
         "previous_signal_count": 0, "trend": "no_previous"},
        {"digest_id": "dg_0002", "theme_id": "th_0001", "signal_count": 2,
         "previous_signal_count": 1, "trend": "growing"},
        {"digest_id": "dg_0002", "theme_id": "th_0002", "signal_count": 1,
         "previous_signal_count": 0, "trend": "new"},
        {"digest_id": "dg_0002", "theme_id": "th_0003", "signal_count": 0,
         "previous_signal_count": 1, "trend": "quiet"},
    ]  # fmt: skip


def test_the_last_published_doc_is_the_latest_push(build):
    run = build.run(START, END)
    for digest_id, when in (
        ("dg_0001", "2026-10-06T00:00:00Z"),
        ("dg_0002", "2026-10-13T00:00:00Z"),
    ):
        build.digest(digest_id, run, approved=True)
        approved = build.conn.execute(
            "SELECT approved_sha256 FROM digests WHERE digest_id = ?", (digest_id,)
        ).fetchone()[0]
        build.insert(
            "publish_steps",
            digest_id=digest_id,
            step="doc_pushed",
            status="done",
            approved_sha256=approved,
            doc_sha256=sha(f"doc {digest_id}"),
            team_commit=sha(digest_id)[:40],
            updated_at=ts(when),
        )
    last = rows(build.conn, "SELECT digest_id, doc_sha256 FROM v_last_published_doc")
    assert last == [{"digest_id": "dg_0002", "doc_sha256": sha("doc dg_0002")}]
