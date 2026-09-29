"""Session 3's privacy gate for stored data (decision 0005, gate 1).

After importing every thin fixture, including a zipped copy of each Slack export:
- no planted phone number, email address, token, or key appears anywhere in the database file
  or the log, byte for byte, and nothing redaction would catch is left in any text column;
- attribution by email domain still worked, because it ran before redaction;
- the prompt-injection line is stored only as a message's evidence text.
"""

import json
import sqlite3

import pytest

from conftest import (
    GITHUB_17,
    GITHUB_20,
    SLACK_A,
    SLACK_B,
    THIN,
    THIN_MANIFEST,
    open_db,
    pulse_json,
    zip_export,
)
from customer_pulse.redact import find_raw

PLANTED = THIN_MANIFEST["planted_raw_values"]
CONTACT_AND_SECRETS = {k: v for k, v in PLANTED.items() if k != "injection"}


@pytest.fixture
def imported(thin_project, tmp_path_factory):
    zips = tmp_path_factory.mktemp("zips")
    for args in (
        ("slack", SLACK_A),
        ("slack", SLACK_B),
        ("slack", zip_export(SLACK_A, zips)),
        ("slack", zip_export(SLACK_B, zips, root="bivo-export")),
        ("github", GITHUB_17),
        ("github", GITHUB_20),
    ):
        code, result = pulse_json("import", args[0], str(args[1]))
        assert code == 0, result
    return thin_project


def _text_values(conn: sqlite3.Connection):
    """Every text value in every table, as (table, column, value)."""
    tables = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not r[0].startswith("sqlite_")
    ]
    for table in tables:
        cursor = conn.execute(f"SELECT * FROM {table}")  # names come from sqlite_master
        columns = [d[0] for d in cursor.description]
        for row in cursor:
            for column, value in zip(columns, row, strict=True):
                if isinstance(value, str):
                    yield table, column, value


def _stored_bytes(project):
    state = project / ".pulse"
    return {path.name: path.read_bytes() for path in sorted(state.iterdir()) if path.is_file()}


def test_no_planted_contact_detail_or_secret_is_stored_or_logged(imported):
    files = _stored_bytes(imported)
    assert {"pulse.db", "pulse.log"} <= set(files)
    for name, data in files.items():
        for kind, value in CONTACT_AND_SECRETS.items():
            assert value.encode("utf-8") not in data, f"raw {kind} found in {name}"
            # Also no fragment long enough to identify it, e.g. the address without markup.
            core = value.split("@")[0] if "@" in value else value[-12:]
            assert core.encode("utf-8") not in data, f"part of the raw {kind} found in {name}"


def test_no_text_column_holds_anything_redaction_would_catch(imported):
    with open_db(imported) as conn:
        leftovers = [
            (table, column, kinds)
            for table, column, value in _text_values(conn)
            if (kinds := find_raw(value))
        ]
    assert leftovers == []


def test_the_log_holds_only_content_free_events(imported):
    lines = (imported / ".pulse" / "pulse.log").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["event"] for e in events] == ["accounts_load"] + ["import"] * 6
    for line in lines:
        assert find_raw(line) == []
        assert PLANTED["injection"] not in line
    # The redaction counts show the gate did its work without saying what it removed.
    assert sum(sum(e.get("redacted", {}).values()) for e in events) > 0


def test_attribution_by_email_domain_happens_before_redaction(imported):
    with open_db(imported) as conn:
        rows = {
            r["author_name"]: (r["account_id"], r["author_role"])
            for r in conn.execute(
                "SELECT author_name, account_id, author_role FROM signals "
                "WHERE source_key LIKE 'C0COM00001:%'"
            )
        }
    # The community channel names no customer. Oren's kettlewren.example address attributes
    # him; Rowan's domain is unknown, so his message stays unattributed rather than guessed;
    # Priya works for Bivo, so her message is vendor context.
    assert rows == {
        "Oren Blake": ("acct_kettlewren", "customer"),
        "Rowan Pike": (None, "customer"),
        "Priya Raman": (None, "vendor"),
    }


def test_the_injection_line_is_stored_only_as_evidence_text(imported):
    with open_db(imported) as conn:
        places = {
            (table, column)
            for table, column, value in _text_values(conn)
            if PLANTED["injection"] in value
        }
        stored = conn.execute(
            "SELECT text_redacted FROM signals WHERE text_redacted LIKE '%Ignore all previous%'"
        ).fetchall()
    assert places == {("signals", "text_redacted")}
    assert len(stored) == 1
    assert f"> {PLANTED['injection']}\n" in stored[0][0]  # kept as the customer quoted it


def test_redacted_text_stays_readable(imported):
    with open_db(imported) as conn:
        texts = [r[0] for r in conn.execute("SELECT text_redacted FROM signals")]
        body = conn.execute("SELECT body_redacted FROM issues WHERE issue_number = 21").fetchone()
    assert any("email me at [redacted email] with a status" in t for t in texts)
    assert any("reach me on [redacted phone]" in t for t in texts)
    assert any("test: [redacted secret] (please rotate it after)" in t for t in texts)
    assert "Sign in as [redacted email]" in body[0]
    assert "Authorization: Bearer [redacted secret]" in body[0]


def test_github_issue_labels_are_redacted_before_storage(thin_project, tmp_path):
    issues = json.loads(GITHUB_17.read_text(encoding="utf-8"))
    issues[0]["labels"].append({"name": "contact alice@copperfen.example"})
    export = tmp_path / "issues-with-sensitive-label.json"
    export.write_text(json.dumps(issues), encoding="utf-8")
    code, result = pulse_json("import", "github", str(export))
    assert code == 0, result
    with open_db(thin_project) as conn:
        labels = [row[0] for row in conn.execute("SELECT labels_json FROM issue_observations")]
    assert any("contact [redacted email]" in value for value in labels)
    assert all(find_raw(value) == [] for value in labels)


def test_sensitive_filenames_are_not_stored_or_logged(thin_project, tmp_path):
    accounts_file = tmp_path / "staff@bivo.example.json"
    accounts_file.write_bytes((THIN / "accounts.json").read_bytes())
    code, result = pulse_json("accounts", "load", str(accounts_file))
    assert code == 0, result

    export = tmp_path / "alice@copperfen.example.json"
    export.write_bytes(GITHUB_17.read_bytes())
    code, result = pulse_json("import", "github", str(export))
    assert code == 0, result
    with open_db(thin_project) as conn:
        names = [row[0] for row in conn.execute("SELECT file_name FROM imports")]
    log = (thin_project / ".pulse" / "pulse.log").read_text(encoding="utf-8")
    assert all(find_raw(name) == [] for name in names)
    assert "alice@copperfen.example" not in log
    assert "staff@bivo.example" not in log
    assert find_raw(log) == []
