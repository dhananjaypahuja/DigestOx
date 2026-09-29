"""Read GitHub issues exported with the ``gh`` CLI::

    gh issue list --state all --limit 1000 \\
      --json number,title,body,url,author,createdAt,state,stateReason,closedAt,labels,comments

An issue's identity is its number and a comment's is its ``id``. Each export is also an
observation of every issue's state as of that export, kept as history (decision 0010).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from customer_pulse.errors import PulseError
from customer_pulse.readers import RawSignal
from customer_pulse.timewin import parse_instant

FIELDS = "number,title,body,url,author,createdAt,state,stateReason,closedAt,labels,comments"


@dataclass(frozen=True)
class RawIssue:
    number: int
    title: str
    body: str
    url: str
    author_login: str | None
    created_at: datetime
    state: str  # OPEN or CLOSED
    state_reason: str | None  # completed, not_planned, ...; None when GitHub gives none
    closed_at: datetime | None
    labels: list[str]


@dataclass(frozen=True)
class GithubExport:
    content_sha256: str
    file_name: str
    issues: list[RawIssue]
    comments: list[RawSignal]


def _invalid(path: Path, message: str) -> PulseError:
    return PulseError(
        "invalid_export",
        f"{path}: {message}",
        hint=f"export with `gh issue list --state all --json {FIELDS}`",
    )


def _instant(value: Any, what: str, path: Path) -> datetime:
    try:
        return parse_instant(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise _invalid(path, f"{what} is not a timestamp: {value!r}") from exc


def read_export(path: Path) -> GithubExport:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise PulseError("file_not_found", f"{path} does not exist") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid(path, f"not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise _invalid(path, "the export must be a JSON list of issues")
    issues, comments, seen = [], [], set()
    for entry in data:
        issue = _issue(entry, path)
        if issue.number in seen:
            raise _invalid(path, f"issue #{issue.number} appears more than once")
        seen.add(issue.number)
        issues.append(issue)
        comments.extend(_comments(entry, issue, path))
    issues.sort(key=lambda i: i.number)
    comments.sort(key=lambda c: (c.occurred_at, c.source_key))
    return GithubExport(hashlib.sha256(raw).hexdigest(), path.name, issues, comments)


def _issue(entry: Any, path: Path) -> RawIssue:
    if not isinstance(entry, dict):
        raise _invalid(path, "every entry must be an issue object")
    number = entry.get("number")
    if not isinstance(number, int) or number <= 0:
        raise _invalid(path, f"an issue has no valid number: {number!r}")
    where = f"issue #{number}"
    missing = [f for f in ("title", "url", "createdAt", "state") if not entry.get(f)]
    if missing:
        raise _invalid(path, f"{where} is missing {', '.join(missing)}")
    state = entry["state"]
    if state not in ("OPEN", "CLOSED"):
        raise _invalid(path, f"{where} has an unknown state {state!r}")
    closed_at = entry.get("closedAt")
    closed = _instant(closed_at, f"{where} closedAt", path) if closed_at else None
    if (state == "CLOSED") != (closed is not None):
        raise _invalid(path, f"{where} is {state} but its closedAt is {closed_at!r}")
    reason = entry.get("stateReason") or None
    labels = entry.get("labels") or []
    return RawIssue(
        number=number,
        title=entry["title"],
        body=entry.get("body") or "",
        url=entry["url"],
        author_login=(entry.get("author") or {}).get("login"),
        created_at=_instant(entry["createdAt"], f"{where} createdAt", path),
        state=state,
        state_reason=reason.lower() if isinstance(reason, str) else None,
        closed_at=closed,
        labels=sorted(label["name"] for label in labels if isinstance(label, dict)),
    )


def _comments(entry: dict[str, Any], issue: RawIssue, path: Path) -> list[RawSignal]:
    found = []
    for comment in entry.get("comments") or []:
        if not isinstance(comment, dict) or not comment.get("id"):
            raise _invalid(path, f"a comment on issue #{issue.number} has no id")
        login = (comment.get("author") or {}).get("login")
        found.append(
            RawSignal(
                source="github",
                source_key=comment["id"],
                occurred_at=_instant(
                    comment.get("createdAt"), f"comment {comment['id']} createdAt", path
                ),
                raw_text=comment.get("body") or "",
                author_name=login,
                thread_key=f"github:issue:{issue.number}",
                url=comment.get("url"),
                issue_number=issue.number,
                author_association=comment.get("authorAssociation"),
            )
        )
    return found
