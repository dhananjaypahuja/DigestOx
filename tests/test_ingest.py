"""Importing Slack and GitHub exports: stable identities, no duplicates, and revisions."""

import json
import sqlite3

import pytest

from conftest import (
    GITHUB_17,
    GITHUB_20,
    SLACK_A,
    SLACK_B,
    THIN,
    Builder,
    open_db,
    pulse,
    pulse_json,
    zip_export,
)


def _import(source, path):
    code, result = pulse_json("import", source, str(path))
    assert code == 0, result
    return result


def _counts(result):
    return result["new"], result["updated"], result["unchanged"]


def _signal_keys(project):
    with open_db(project) as conn:
        return sorted(r[0] for r in conn.execute("SELECT source || ':' || source_key FROM signals"))


def test_overlapping_slack_exports_never_duplicate_a_message(thin_project, tmp_path):
    a = _import("slack", SLACK_A)
    assert _counts(a) == (12, 0, 0)
    assert a["skipped_events"] == 1  # the channel join
    b = _import("slack", SLACK_B)
    # Export B repeats five messages from 16 and 17 September and edits one of them.
    assert _counts(b) == (4, 1, 5)
    keys = _signal_keys(thin_project)
    assert len(keys) == len(set(keys)) == 16

    # The same folder again is recognised by its hash; a ZIP of it is a new batch whose
    # messages are all unchanged.
    again = _import("slack", SLACK_A)
    assert again["status"] == "already_imported"
    assert again["import_id"] == a["import_id"]
    zipped = _import("slack", zip_export(SLACK_B, tmp_path))
    assert _counts(zipped) == (0, 0, 10)
    assert _signal_keys(thin_project) == keys


def test_an_edited_message_is_revised_and_its_old_text_kept(thin_project):
    _import("slack", SLACK_A)
    b = _import("slack", SLACK_B)
    with open_db(thin_project) as conn:
        signal = conn.execute(
            "SELECT signal_id, text_redacted, first_import_id, last_import_id FROM signals "
            "WHERE text_redacted LIKE '%needs attention%'"
        ).fetchone()
        revisions = conn.execute("SELECT * FROM signal_revisions").fetchall()
    assert signal["text_redacted"].endswith("since Monday's update.")
    assert (signal["first_import_id"], signal["last_import_id"]) == (1, b["import_id"])
    assert len(revisions) == 1
    assert revisions[0]["signal_id"] == signal["signal_id"]
    assert revisions[0]["old_text_redacted"].endswith("since the last update.")


def test_messages_keep_their_thread_and_time(thin_project):
    _import("slack", SLACK_A)
    _import("slack", SLACK_B)
    with open_db(thin_project) as conn:
        rows = conn.execute(
            "SELECT source_key, thread_key, occurred_at FROM signals "
            "WHERE thread_key = 'slack:C0CPF00001:1789495320.000600' ORDER BY occurred_at"
        ).fetchall()
    # Copperfen's thread: the parent and first reply come from export A, the second reply
    # only from export B, and all three share the parent's thread.
    assert [r["occurred_at"] for r in rows] == [
        "2026-09-15T18:02:00.000600Z",
        "2026-09-15T18:30:00.000700Z",
        "2026-09-16T16:15:00.000800Z",
    ]


def test_a_message_that_gains_replies_keeps_its_thread(thin_project, tmp_path):
    export = tmp_path / "export"
    (export / "c").mkdir(parents=True)
    (export / "users.json").write_text("[]")
    (export / "channels.json").write_text(json.dumps([{"id": "C1", "name": "c"}]))
    day = export / "c" / "2026-09-14.json"
    parent = {"type": "message", "user": "U1", "ts": "1789402320.000100", "text": "hello"}
    day.write_text(json.dumps([parent]))
    _import("slack", export)
    reply = {**parent, "ts": "1789402999.000200", "thread_ts": parent["ts"], "text": "hi"}
    day.write_text(json.dumps([{**parent, "thread_ts": parent["ts"], "reply_count": 1}, reply]))
    assert _counts(_import("slack", export)) == (1, 0, 1)
    with open_db(thin_project) as conn:
        threads = {r[0] for r in conn.execute("SELECT thread_key FROM signals")}
    assert threads == {"slack:C1:1789402320.000100"}


def test_github_snapshots_add_observations_not_duplicates(thin_project):
    first = _import("github", GITHUB_17)
    assert first["issues"] == {"new": 3, "updated": 0, "unchanged": 0}
    assert _counts(first) == (2, 0, 0)
    second = _import("github", GITHUB_20)
    # #24 is new; #23 closed; #18 and #21 are unchanged apart from a new comment on #21.
    assert second["issues"] == {"new": 1, "updated": 1, "unchanged": 2}
    assert _counts(second) == (2, 0, 2)
    with open_db(thin_project) as conn:
        issues = conn.execute("SELECT count(*) FROM issues").fetchone()[0]
        observed = conn.execute(
            "SELECT issue_number, import_id, state, state_reason FROM issue_observations "
            "WHERE issue_number = 23 ORDER BY import_id"
        ).fetchall()
        comments = conn.execute(
            "SELECT source_key, issue_number, thread_key, author_role FROM signals "
            "WHERE source = 'github' ORDER BY occurred_at"
        ).fetchall()
    assert issues == 4
    assert [tuple(r) for r in observed] == [
        (23, first["import_id"], "OPEN", None),
        (23, second["import_id"], "CLOSED", "not_planned"),
    ]
    assert [tuple(r) for r in comments] == [
        ("IC_kwDOBivo18a", 18, "github:issue:18", "vendor"),
        ("IC_kwDOBivo21a", 21, "github:issue:21", "vendor"),
        ("IC_kwDOBivo21b", 21, "github:issue:21", "customer"),
        ("IC_kwDOBivo23a", 23, "github:issue:23", "vendor"),
    ]


def test_an_import_that_would_change_fixed_evidence_changes_nothing(thin_project, tmp_path):
    _import("github", GITHUB_17)
    issues = json.loads(GITHUB_20.read_text())
    for issue in issues:
        if issue["number"] == 18:
            issue["createdAt"] = "2026-09-03T10:00:00Z"
    changed = tmp_path / "issues-changed.json"
    changed.write_text(json.dumps(issues))
    code, result = pulse_json("import", "github", str(changed))
    assert code == 1
    assert result["error"]["code"] == "evidence_conflict"
    with open_db(thin_project) as conn:
        assert conn.execute("SELECT count(*) FROM imports").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM issues").fetchone()[0] == 3


def test_a_later_import_keeps_the_first_attribution(thin_project, tmp_path):
    _import("slack", SLACK_A)
    export = tmp_path / "export-a-moved"
    for file in SLACK_A.rglob("*.json"):
        target = export / file.relative_to(SLACK_A)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file.read_bytes())
    # Rowan's unknown domain becomes a customer's: the stored message stays unattributed.
    users = json.loads((export / "users.json").read_text())
    for user in users:
        if user["id"] == "U0TRM00001":
            user["profile"]["email"] = "rowan.pike@copperfen.example"
    (export / "users.json").write_text(json.dumps(users))
    result = _import("slack", export)
    assert result["kept_first_attribution"] == 1
    with open_db(thin_project) as conn:
        row = conn.execute(
            "SELECT account_id FROM signals WHERE author_name = 'Rowan Pike'"
        ).fetchone()
    assert row[0] is None


def test_channel_ids_are_claimed_from_the_first_export(thin_project):
    _import("slack", SLACK_A)
    with open_db(thin_project) as conn:
        ids = dict(conn.execute("SELECT account_id, slack_channel_id FROM accounts"))
    assert ids == {
        "acct_morrowvale": "C0MRV00001",
        "acct_copperfen": "C0CPF00001",
        "acct_kettlewren": "C0KTW00001",
        "acct_brackenlight": "C0BRK00001",
    }


def test_same_name_with_a_new_slack_id_does_not_claim_a_pinned_account(thin_project, tmp_path):
    _import("slack", SLACK_A)
    export = tmp_path / "reused-name"
    channel_dir = export / "bivo-copperfen"
    channel_dir.mkdir(parents=True)
    (export / "users.json").write_text("[]", encoding="utf-8")
    (export / "channels.json").write_text(
        json.dumps([{"id": "C_NEW", "name": "bivo-copperfen"}]), encoding="utf-8"
    )
    (channel_dir / "2026-09-18.json").write_text(
        json.dumps(
            [{"type": "message", "user": "U_NEW", "ts": "1790000000.000001", "text": "hello"}]
        ),
        encoding="utf-8",
    )
    result = _import("slack", export)
    assert result["channels_naming_no_customer"] == ["bivo-copperfen"]
    with open_db(thin_project) as conn:
        pinned = conn.execute(
            "SELECT slack_channel_id FROM accounts WHERE account_id = 'acct_copperfen'"
        ).fetchone()[0]
        attributed = conn.execute(
            "SELECT account_id FROM signals WHERE source_key = 'C_NEW:1790000000.000001'"
        ).fetchone()[0]
    assert pinned == "C0CPF00001"
    assert attributed is None


@pytest.mark.parametrize("source", ["slack", "github"])
def test_import_needs_an_initialized_database(project, source):
    target = SLACK_A if source == "slack" else GITHUB_17
    code, result = pulse_json("import", source, str(target))
    assert code == 1
    assert result["error"]["code"] == "not_initialized"
    assert not (project / ".pulse").exists()


def test_import_reports_a_bad_export_cleanly(thin_project, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    code, result = pulse_json("import", "slack", str(bad))
    assert code == 1
    assert result["error"]["code"] == "invalid_export"
    code, result = pulse_json("import", "github", str(tmp_path / "missing.json"))
    assert code == 1
    assert result["error"]["code"] == "file_not_found"


def test_import_prints_a_summary_for_people(thin_project):
    code, out = pulse("import", "slack", str(SLACK_A))
    assert code == 0
    assert "Imported export-a as import 1: 12 new, 0 updated, 0 unchanged." in out
    assert "redacted  1 email, 1 phone" in out
    assert "naming no customer: #bivo-community" in out


# Vendor messages are context, never evidence (migration 0006, decision 0011)


def test_vendor_messages_are_not_counted_as_evidence(build: Builder):
    build.account("acct_a", "A")
    customer = build.signal("m1", "2026-09-14T10:00:00Z", account="acct_a")
    vendor = build.signal("m2", "2026-09-14T11:00:00Z", account="acct_a")
    build.conn.execute(
        "UPDATE signals SET author_role = 'customer' WHERE signal_id = ?", (customer,)
    )
    with pytest.raises(sqlite3.IntegrityError, match="author role is fixed"):
        build.conn.execute(
            "UPDATE signals SET author_role = 'vendor' WHERE signal_id = ?", (vendor,)
        )
    build.insert(
        "signals",
        source="slack",
        source_key="m3",
        account_id="acct_a",
        author_role="vendor",
        occurred_at=build.now.replace("2026-10-12", "2026-09-14"),
        text_redacted="we're looking",
        raw_sha256="0" * 64,
        first_import_id=build.import_batch(),
        last_import_id=build.import_batch(),
    )
    run = build.run("2026-09-14T00:00:00Z", "2026-09-21T00:00:00Z")
    counted = [
        r[0]
        for r in build.conn.execute(
            "SELECT source_key FROM v_run_signals WHERE run_id = ? ORDER BY source_key", (run,)
        )
    ]
    assert counted == ["m1", "m2"]


def test_author_role_is_checked(build: Builder):
    with pytest.raises(sqlite3.IntegrityError):
        build.insert(
            "signals",
            source="slack",
            source_key="x",
            author_role="staff",
            occurred_at=build.now,
            text_redacted="",
            raw_sha256="0" * 64,
            first_import_id=build.import_batch(),
            last_import_id=build.import_batch(),
        )


# Accounts


def test_accounts_load_is_idempotent_and_never_removes(thin_project, tmp_path):
    code, again = pulse_json("accounts", "load", str(THIN / "accounts.json"))
    assert code == 0
    assert again["added"] == []
    assert again["updated"] == []
    assert len(again["unchanged"]) == 4
    smaller = tmp_path / "accounts.json"
    accounts = json.loads((THIN / "accounts.json").read_text())
    accounts[0]["name"] = "Morrowvale Clubs"
    smaller.write_text(json.dumps(accounts[:2]))
    code, result = pulse_json("accounts", "load", str(smaller))
    assert code == 0
    assert result["updated"] == ["acct_morrowvale"]
    assert result["not_in_file"] == ["acct_brackenlight", "acct_kettlewren"]
    with open_db(thin_project) as conn:
        assert conn.execute("SELECT count(*) FROM accounts").fetchone()[0] == 4


@pytest.mark.parametrize(
    ("entries", "code"),
    [
        ([{"account_id": "morrowvale", "name": "M"}], "invalid_accounts_file"),
        (
            [{"account_id": "acct_x", "name": "X", "email_domains": ["X.example"]}],
            "invalid_accounts_file",
        ),
        ([{"account_id": "acct_x", "name": "X", "colour": "red"}], "invalid_accounts_file"),
        (
            [{"account_id": "acct_x", "name": "X"}, {"account_id": "acct_x", "name": "Y"}],
            "invalid_accounts_file",
        ),
        (
            [{"account_id": "acct_x", "name": "X", "email_domains": ["copperfen.example"]}],
            "domain_conflict",
        ),
        (
            [{"account_id": "acct_x", "name": "X", "slack_channel": "bivo-copperfen"}],
            "channel_conflict",
        ),
    ],
)
def test_accounts_load_refuses_bad_files(thin_project, tmp_path, entries, code):
    file = tmp_path / "accounts.json"
    file.write_text(json.dumps(entries))
    exit_code, result = pulse_json("accounts", "load", str(file))
    assert exit_code == 1
    assert result["error"]["code"] == code
    with open_db(thin_project) as conn:
        assert conn.execute("SELECT count(*) FROM accounts").fetchone()[0] == 4


def test_import_warns_when_the_vendor_is_not_configured(project):
    pulse("init")
    code, out = pulse("import", "slack", str(SLACK_A))
    assert code == 0
    assert "no [vendor] in pulse.toml" in out
    assert _import("slack", SLACK_B)["vendor_configured"] is False
