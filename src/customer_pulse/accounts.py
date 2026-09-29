"""The customer list: which accounts exist, the Slack channel that names each, and the email
domains that attribute evidence to them. `pulse accounts load` reads it from a JSON file.

The file is a list of objects::

    [{"account_id": "acct_morrowvale", "name": "Morrowvale Athletic Clubs",
      "slack_channel": "bivo-morrowvale", "email_domains": ["morrowvale.example"]}]

Loading adds new accounts and updates the name and channel of existing ones. It never
removes an account or a domain, because stored evidence points at them; an account missing
from the file is reported instead. A domain can belong to only one account.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from customer_pulse.clock import Clock
from customer_pulse.errors import PulseError
from customer_pulse.timewin import to_db

_ACCOUNT_ID = re.compile(r"acct_[a-z0-9_]+")
_DOMAIN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
_CHANNEL = re.compile(r"[a-z0-9][a-z0-9_-]*")


def _invalid(path: Path, message: str) -> PulseError:
    return PulseError(
        "invalid_accounts_file",
        f"{path}: {message}",
        hint="each entry needs account_id (acct_...), name, and optionally slack_channel and "
        "email_domains",
    )


def read_accounts_file(path: Path) -> list[dict[str, Any]]:
    """Parse and validate the file. Nothing is written."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PulseError("file_not_found", f"{path} does not exist") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid(path, f"not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise _invalid(path, "the file must hold a JSON list of accounts")
    accounts, seen_ids, seen_domains, seen_channels = [], set(), set(), set()
    for n, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise _invalid(path, f"entry {n} is not an object")
        unknown = set(entry) - {"account_id", "name", "slack_channel", "email_domains"}
        if unknown:
            raise _invalid(path, f"entry {n} has unknown keys: {', '.join(sorted(unknown))}")
        account_id, name = entry.get("account_id"), entry.get("name")
        channel, domains = entry.get("slack_channel"), entry.get("email_domains", [])
        if not isinstance(account_id, str) or not _ACCOUNT_ID.fullmatch(account_id):
            raise _invalid(path, f"entry {n}: account_id must look like acct_name")
        if not isinstance(name, str) or not name.strip():
            raise _invalid(path, f"entry {n}: name is required")
        if channel is not None and (
            not isinstance(channel, str) or not _CHANNEL.fullmatch(channel)
        ):
            raise _invalid(path, f"entry {n}: slack_channel must be a channel name without #")
        if not isinstance(domains, list) or not all(
            isinstance(d, str) and _DOMAIN.fullmatch(d) for d in domains
        ):
            raise _invalid(path, f"entry {n}: email_domains must be lowercase domains")
        for value, seen, what in (
            (account_id, seen_ids, "account_id"),
            (channel, seen_channels, "slack_channel"),
            *((d, seen_domains, "email domain") for d in domains),
        ):
            if value is None:
                continue
            if value in seen:
                raise _invalid(path, f"{what} {value} appears more than once")
            seen.add(value)
        accounts.append(
            {
                "account_id": account_id,
                "name": name.strip(),
                "slack_channel": channel,
                "email_domains": sorted(domains),
            }
        )
    return accounts


def load_accounts(conn: sqlite3.Connection, path: Path, clock: Clock) -> dict[str, Any]:
    """Add or update the accounts in ``path`` in one transaction, and report what changed."""
    accounts = read_accounts_file(path)
    now = to_db(clock.now())
    added, updated, unchanged, domains_added = [], [], [], 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for acct in accounts:
            row = conn.execute(
                "SELECT name, slack_channel_name FROM accounts WHERE account_id = ?",
                (acct["account_id"],),
            ).fetchone()
            _check_channel_free(conn, acct)
            if row is None:
                conn.execute(
                    "INSERT INTO accounts (account_id, name, slack_channel_name, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (acct["account_id"], acct["name"], acct["slack_channel"], now),
                )
                added.append(acct["account_id"])
            elif (row["name"], row["slack_channel_name"]) != (acct["name"], acct["slack_channel"]):
                # A renamed channel has a new name but the same Slack ID, so the ID is cleared
                # only when the name changes; the next Slack import sets it again.
                conn.execute(
                    "UPDATE accounts SET name = ?, slack_channel_name = ?, "
                    "slack_channel_id = CASE WHEN slack_channel_name IS ? THEN slack_channel_id "
                    "ELSE NULL END WHERE account_id = ?",
                    (
                        acct["name"],
                        acct["slack_channel"],
                        acct["slack_channel"],
                        acct["account_id"],
                    ),
                )
                updated.append(acct["account_id"])
            else:
                unchanged.append(acct["account_id"])
            for domain in acct["email_domains"]:
                owner = conn.execute(
                    "SELECT account_id FROM account_domains WHERE domain = ?", (domain,)
                ).fetchone()
                if owner is None:
                    conn.execute(
                        "INSERT INTO account_domains (domain, account_id) VALUES (?, ?)",
                        (domain, acct["account_id"]),
                    )
                    domains_added += 1
                elif owner[0] != acct["account_id"]:
                    raise PulseError(
                        "domain_conflict",
                        f"{domain} already belongs to {owner[0]}, not {acct['account_id']}",
                        hint="a domain attributes evidence to one customer; fix the file",
                    )
        in_file = {a["account_id"] for a in accounts}
        missing = [
            r[0]
            for r in conn.execute("SELECT account_id FROM accounts ORDER BY account_id")
            if r[0] not in in_file
        ]
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "email_domains_added": domains_added,
        "not_in_file": missing,
    }


def _check_channel_free(conn: sqlite3.Connection, acct: dict[str, Any]) -> None:
    if acct["slack_channel"] is None:
        return
    owner = conn.execute(
        "SELECT account_id FROM accounts WHERE slack_channel_name = ? AND account_id <> ?",
        (acct["slack_channel"], acct["account_id"]),
    ).fetchone()
    if owner is not None:
        raise PulseError(
            "channel_conflict",
            f"#{acct['slack_channel']} already names {owner[0]}, not {acct['account_id']}",
            hint="a shared channel names one customer; fix the file",
        )
