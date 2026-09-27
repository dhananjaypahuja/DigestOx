"""Shared fixtures: a migrated database on a fixed clock, and a builder for test rows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from itertools import count
from pathlib import Path

import pytest

from customer_pulse import db
from customer_pulse.clock import FixedClock
from customer_pulse.timewin import parse_instant, to_db

NOW = "2026-10-12T17:00:00Z"


def ts(text: str) -> str:
    """Stored form of an ISO 8601 instant, for concise test data."""
    return to_db(parse_instant(text))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(parse_instant(NOW))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pulse.db"


@pytest.fixture
def conn(db_path: Path, clock: FixedClock) -> Iterator[sqlite3.Connection]:
    connection = db.connect(db_path)
    db.migrate(connection, clock)
    yield connection
    connection.close()


class Builder:
    """Inserts rows with sensible defaults so each test states only what it's about."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._imports: dict[str, int] = {}
        self._serial = count(1)
        self.now = ts(NOW)

    def insert(self, table: str, **values: object) -> int:
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cursor = self.conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values())
        )
        return cursor.lastrowid

    def import_batch(self, source: str = "slack") -> int:
        if source not in self._imports:
            self._imports[source] = self.insert(
                "imports",
                source=source,
                file_name=f"{source}-export",
                content_sha256=sha(f"{source}-{next(self._serial)}"),
                imported_at=self.now,
            )
        return self._imports[source]

    def account(self, account_id: str, name: str) -> str:
        self.insert("accounts", account_id=account_id, name=name, created_at=self.now)
        return account_id

    def signal(
        self,
        key: str,
        at: str,
        *,
        account: str | None = None,
        source: str = "slack",
        thread: str | None = None,
        pulse_output: bool = False,
        issue: int | None = None,
    ) -> int:
        batch = self.import_batch(source)
        return self.insert(
            "signals",
            source=source,
            source_key=key,
            account_id=account,
            author_name="Example Person",
            occurred_at=ts(at),
            text_redacted=f"text of {key}",
            raw_sha256=sha(key),
            thread_key=thread,
            issue_number=issue,
            is_pulse_output=int(pulse_output),
            first_import_id=batch,
            last_import_id=batch,
        )

    def run(self, start: str, end: str, cutoff: str | None = None, kind: str = "digest") -> int:
        return self.insert(
            "runs",
            kind=kind,
            mode="offline",
            window_start=ts(start),
            window_end=ts(end),
            cutoff=ts(cutoff or end),
            timezone="America/Los_Angeles",
            started_at=self.now,
            status="succeeded",
        )

    def theme(self, theme_id: str, *, merged_into: str | None = None) -> str:
        self.insert(
            "themes",
            theme_id=theme_id,
            title=f"Theme {theme_id}",
            status="merged" if merged_into else "active",
            merged_into=merged_into,
            created_at=self.now,
        )
        return theme_id

    def correction(self, command: str = "theme move", digest: str | None = None) -> int:
        return self.insert(
            "corrections",
            created_at=self.now,
            command=command,
            args_json=json.dumps({"n": next(self._serial)}),
            digest_id=digest,
        )

    def assign(
        self, signal: int, theme: str, *, run: int | None = None, person: bool = False
    ) -> int:
        return self.insert(
            "assignments",
            signal_id=signal,
            theme_id=theme,
            set_by="person" if person else "model",
            confidence=None if person else 0.8,
            run_id=None if person else run,
            correction_id=self.correction() if person else None,
            created_at=self.now,
        )

    def issue(self, number: int, *, closed_at: str | None = None, reason: str | None = None) -> int:
        batch = self.import_batch("github")
        self.insert(
            "issues",
            issue_number=number,
            title=f"Issue {number}",
            body_redacted="body",
            url=f"https://github.com/bivo-fictional/bivo-platform/issues/{number}",
            created_at=ts("2026-09-01T00:00:00Z"),
            first_import_id=batch,
            last_import_id=batch,
        )
        self.observe(number, batch, closed_at=closed_at, reason=reason)
        return number

    def observe(
        self, number: int, batch: int, *, closed_at: str | None, reason: str | None = None
    ) -> None:
        self.insert(
            "issue_observations",
            issue_number=number,
            import_id=batch,
            state="CLOSED" if closed_at else "OPEN",
            state_reason=reason,
            closed_at=ts(closed_at) if closed_at else None,
            observed_at=self.now,
        )

    def link(self, signal: int, issue: int, relation: str, status: str) -> int:
        reviewed = status in ("confirmed", "rejected")
        return self.insert(
            "links",
            signal_id=signal,
            issue_number=issue,
            relation=relation,
            found_by="code" if relation == "references" else "model",
            review_status=status,
            correction_id=self.correction("link confirm") if reviewed else None,
            created_at=self.now,
        )

    def area(self, key: str, *prefixes: str) -> str:
        self.insert("code_areas", area_key=key)
        for prefix in prefixes:
            self.insert("code_area_paths", area_key=key, path_prefix=prefix)
        return key

    def theme_area(self, theme: str, area: str) -> None:
        self.insert("theme_code_areas", theme_id=theme, area_key=area, set_by="model")

    def session(self, name: str, stopped_at: str) -> str:
        self.insert(
            "sessions",
            session_name=name,
            repo_id="repo_bivo",
            stopped_at=ts(stopped_at),
            reconciled_at=self.now,
        )
        return name

    def evidence(self, session: str, path: str, *, committed_at: str | None = None) -> None:
        verified = committed_at is not None
        self.insert(
            "session_evidence",
            session_name=session,
            path=path,
            level="verified" if verified else "reported",
            commit_sha=sha(session + path)[:40] if verified else None,
            committed_at=ts(committed_at) if verified else None,
            observed_at=self.now,
        )

    def digest(
        self, digest_id: str, run: int, *, previous: str | None = None, approved: bool = False
    ) -> str:
        content = f"# Digest {digest_id}"
        self.insert(
            "digests",
            digest_id=digest_id,
            run_id=run,
            previous_digest_id=previous,
            content_md=content,
            content_sha256=sha(content),
            status="approved" if approved else "draft",
            approved_sha256=sha(content) if approved else None,
            approved_at=self.now if approved else None,
            created_at=self.now,
        )
        return digest_id


@pytest.fixture
def build(conn: sqlite3.Connection) -> Builder:
    return Builder(conn)
