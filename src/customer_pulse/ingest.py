"""Store what the readers parse: parse, then attribute, then redact, then store.

Each import is one batch in one transaction, identified by the hash of what was imported.
Re-importing overlapping exports never duplicates a record:

- A record Pulse hasn't seen is added.
- A record whose raw text is unchanged only notes the later import.
- A record whose raw text changed is revised: the old redacted text goes to
  ``signal_revisions``, and the new redacted text replaces it.

A signal's identity, time, customer, author role, and thread are fixed at its first import
(decisions 0010 and 0011). If a later import would attribute it differently, the first
attribution is kept and the import reports how many such records it saw.

Only redacted text reaches the database or the log. Raw text and author email addresses exist
in memory only while one record is processed.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from customer_pulse import state
from customer_pulse.attribution import Attribution, Directory
from customer_pulse.clock import Clock
from customer_pulse.config import Config
from customer_pulse.errors import PulseError
from customer_pulse.readers import RawSignal, github, slack
from customer_pulse.redact import redact, redact_text
from customer_pulse.timewin import to_db

NEW, UPDATED, UNCHANGED = "new", "updated", "unchanged"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Batch:
    """One import in progress: its row, counts, and redaction tallies."""

    def __init__(
        self, conn: sqlite3.Connection, source: str, file_name: str, sha: str, clock: Clock
    ) -> None:
        self.conn = conn
        self.now = to_db(clock.now())
        self.counts: Counter[str] = Counter()
        self.redactions: Counter[str] = Counter()
        self.attribution: Counter[str] = Counter()
        self.kept_first_attribution = 0
        self.import_id = conn.execute(
            "INSERT INTO imports (source, file_name, content_sha256, imported_at) "
            "VALUES (?, ?, ?, ?)",
            (source, file_name, sha, self.now),
        ).lastrowid

    def redact(self, text: str) -> str:
        result = redact(text)
        self.redactions.update(result.counts)
        return result.text

    def store_signal(self, raw: RawSignal, who: Attribution) -> str:
        """Add or revise one signal, redacting its text on the way in."""
        raw_sha = _sha(raw.raw_text)
        redacted = self.redact(raw.text)
        author = redact_text(raw.author_name)
        url = redact_text(raw.url)
        existing = self.conn.execute(
            "SELECT signal_id, raw_sha256, text_redacted, account_id, author_role "
            "FROM signals WHERE source = ? AND source_key = ?",
            (raw.source, raw.source_key),
        ).fetchone()
        self.attribution[f"{who.author_role}:{who.method}"] += 1
        if existing is None:
            self.conn.execute(
                "INSERT INTO signals (source, source_key, account_id, author_name, author_role, "
                "occurred_at, text_redacted, raw_sha256, url, thread_key, issue_number, "
                "first_import_id, last_import_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    raw.source,
                    raw.source_key,
                    who.account_id,
                    author,
                    who.author_role,
                    to_db(raw.occurred_at),
                    redacted,
                    raw_sha,
                    url,
                    raw.thread_key,
                    raw.issue_number,
                    self.import_id,
                    self.import_id,
                ),
            )
            return NEW
        if (existing["account_id"], existing["author_role"]) != (who.account_id, who.author_role):
            self.kept_first_attribution += 1
        if existing["raw_sha256"] == raw_sha:
            self.conn.execute(
                "UPDATE signals SET last_import_id = ? WHERE signal_id = ?",
                (self.import_id, existing["signal_id"]),
            )
            return UNCHANGED
        self.conn.execute(
            "INSERT INTO signal_revisions (signal_id, import_id, old_raw_sha256, new_raw_sha256, "
            "old_text_redacted, seen_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                existing["signal_id"],
                self.import_id,
                existing["raw_sha256"],
                raw_sha,
                existing["text_redacted"],
                self.now,
            ),
        )
        self.conn.execute(
            "UPDATE signals SET text_redacted = ?, raw_sha256 = ?, author_name = ?, url = ?, "
            "last_import_id = ? WHERE signal_id = ?",
            (redacted, raw_sha, author, url, self.import_id, existing["signal_id"]),
        )
        return UPDATED

    def finish(self) -> None:
        self.conn.execute(
            "UPDATE imports SET new_count = ?, updated_count = ?, unchanged_count = ? "
            "WHERE import_id = ?",
            (self.counts[NEW], self.counts[UPDATED], self.counts[UNCHANGED], self.import_id),
        )

    def result(self, source: str, file_name: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": "imported",
            "source": source,
            "file_name": file_name,
            "import_id": self.import_id,
            "new": self.counts[NEW],
            "updated": self.counts[UPDATED],
            "unchanged": self.counts[UNCHANGED],
            "redacted": dict(sorted(self.redactions.items())),
            "attribution": dict(sorted(self.attribution.items())),
            "kept_first_attribution": self.kept_first_attribution,
            **extra,
        }


def _already_imported(conn: sqlite3.Connection, source: str, sha: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT import_id, file_name, imported_at FROM imports "
        "WHERE source = ? AND content_sha256 = ?",
        (source, sha),
    ).fetchone()
    if row is None:
        return None
    return {"status": "already_imported", "source": source, **dict(row)}


def _run(
    conn: sqlite3.Connection,
    config: Config,
    source: str,
    sha: str,
    file_name: str,
    clock: Clock,
    work: Any,
) -> dict[str, Any]:
    # Export basenames are supplied by the caller, not trusted metadata. They reach both
    # imports.file_name and pulse.log, so they need the same privacy gate as evidence text.
    file_name = redact(file_name).text
    conn.execute("BEGIN IMMEDIATE")
    try:
        if done := _already_imported(conn, source, sha):
            conn.execute("ROLLBACK")
            done["file_name"] = redact(done["file_name"]).text
            state.append_log(config, {"event": "import_skipped", **done})
            return done
        batch = _Batch(conn, source, file_name, sha, clock)
        extra = work(batch)
        batch.finish()
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        conn.execute("ROLLBACK")
        raise PulseError(
            "evidence_conflict",
            f"the import would change stored evidence, so nothing was imported: {exc}",
            hint="an earlier import fixed this record; check the export is from the same source",
        ) from exc
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    result = batch.result(source, file_name, **extra)
    state.append_log(config, {"event": "import", **result})
    return result


def import_slack(
    conn: sqlite3.Connection, config: Config, path: Path, clock: Clock
) -> dict[str, Any]:
    export = slack.read_export(path)

    def work(batch: _Batch) -> dict[str, Any]:
        directory = Directory(conn, config.vendor)
        _claim_channels(conn, directory, export.channels)
        unmapped = set()
        for raw in export.signals:
            channel_account = directory.slack_channel(
                raw.slack_channel_id or "", raw.slack_channel_name or ""
            )
            if channel_account is None:
                unmapped.add(raw.slack_channel_name)
            who = directory.slack(channel_account, raw.author_email, raw.author_team)
            batch.counts[batch.store_signal(raw, who)] += 1
        return {
            "vendor_configured": bool(config.vendor.email_domains or config.vendor.slack_team_ids),
            "skipped_events": export.skipped,
            "channels_naming_no_customer": sorted(unmapped),
        }

    return _run(conn, config, "slack", export.content_sha256, export.file_name, clock, work)


def _claim_channels(
    conn: sqlite3.Connection, directory: Directory, channels: list[slack.Channel]
) -> None:
    """Record the Slack ID of each customer's channel the first time an export shows it."""
    for channel in channels:
        account = directory.by_channel_name.get(channel.name)
        if (
            account
            and channel.id not in directory.by_channel_id
            and directory.channel_id_by_account.get(account) is None
        ):
            cursor = conn.execute(
                "UPDATE accounts SET slack_channel_id = ? "
                "WHERE account_id = ? AND slack_channel_id IS NULL",
                (channel.id, account),
            )
            if cursor.rowcount:
                directory.by_channel_id[channel.id] = account
                directory.channel_id_by_account[account] = channel.id


def import_github(
    conn: sqlite3.Connection, config: Config, path: Path, clock: Clock
) -> dict[str, Any]:
    export = github.read_export(path)

    def work(batch: _Batch) -> dict[str, Any]:
        directory = Directory(conn, config.vendor)
        issues = Counter()
        for issue in export.issues:
            issues[_store_issue(batch, issue)] += 1
        for raw in export.comments:
            who = directory.github(raw.author_association)
            batch.counts[batch.store_signal(raw, who)] += 1
        return {"issues": {k: issues[k] for k in (NEW, UPDATED, UNCHANGED)}}

    return _run(conn, config, "github", export.content_sha256, export.file_name, clock, work)


def _store_issue(batch: _Batch, issue: github.RawIssue) -> str:
    conn = batch.conn
    title, body, url = batch.redact(issue.title), batch.redact(issue.body), batch.redact(issue.url)
    author = redact_text(issue.author_login)
    closed_at = to_db(issue.closed_at) if issue.closed_at else None
    labels = json.dumps([batch.redact(label) for label in issue.labels])
    existing = conn.execute(
        "SELECT i.title, i.body_redacted, i.url, i.created_at, o.state, o.state_reason, "
        "o.closed_at, o.labels_json FROM issues AS i LEFT JOIN v_issue_latest AS o "
        "ON o.issue_number = i.issue_number WHERE i.issue_number = ?",
        (issue.number,),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO issues (issue_number, title, body_redacted, url, author_login, "
            "created_at, first_import_id, last_import_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                issue.number,
                title,
                body,
                url,
                author,
                to_db(issue.created_at),
                batch.import_id,
                batch.import_id,
            ),
        )
        outcome = NEW
    else:
        conn.execute(
            "UPDATE issues SET title = ?, body_redacted = ?, url = ?, author_login = ?, "
            "created_at = ?, last_import_id = ? WHERE issue_number = ?",
            (title, body, url, author, to_db(issue.created_at), batch.import_id, issue.number),
        )
        before = (
            existing["title"],
            existing["body_redacted"],
            existing["url"],
            existing["state"],
            existing["state_reason"],
            existing["closed_at"],
            existing["labels_json"],
        )
        after = (title, body, url, issue.state, issue.state_reason, closed_at, labels)
        outcome = UNCHANGED if before == after else UPDATED
    conn.execute(
        "INSERT INTO issue_observations (issue_number, import_id, state, state_reason, "
        "closed_at, labels_json, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            issue.number,
            batch.import_id,
            issue.state,
            issue.state_reason,
            closed_at,
            labels,
            batch.now,
        ),
    )
    return outcome
