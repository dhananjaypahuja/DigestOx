"""Attribution: which customer a record belongs to, and whether the vendor's staff wrote it.

It runs before redaction, because it may read an author's email address; the address itself
is never stored (DESIGN.md section 6). Evidence that can't be attributed stays unattributed,
never guessed.

- **Slack:** the shared channel names the customer. In a channel that names no customer,
  the author's email domain may (decision 0011).
- **GitHub:** authors stay unattributed; no mapping names them yet.
- **Vendor staff** are recognised by their Slack workspace or email domain, and on GitHub by
  ``authorAssociation``. Their messages are kept as context and never counted.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from customer_pulse.config import Vendor

CUSTOMER = "customer"
VENDOR = "vendor"

# GitHub's authorAssociation values that mean the author works on the repository.
_GITHUB_STAFF = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


@dataclass(frozen=True)
class Attribution:
    account_id: str | None
    author_role: str
    method: str  # channel, email_domain, or none: how the account was found


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower() or None


def _matches(domain: str | None, domains: frozenset[str] | dict[str, str]) -> str | None:
    """The configured domain that ``domain`` equals or is a subdomain of."""
    if not domain:
        return None
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in domains:
            return candidate
    return None


class Directory:
    """The accounts, their channels and domains, and the vendor, read once per import."""

    def __init__(self, conn: sqlite3.Connection, vendor: Vendor) -> None:
        self.vendor = vendor
        rows = conn.execute(
            "SELECT account_id, slack_channel_id, slack_channel_name FROM accounts"
        ).fetchall()
        self.by_channel_id = {r["slack_channel_id"]: r["account_id"] for r in rows if r[1]}
        self.by_channel_name = {r["slack_channel_name"]: r["account_id"] for r in rows if r[2]}
        self.by_domain = dict(conn.execute("SELECT domain, account_id FROM account_domains"))

    def slack_channel(self, channel_id: str, channel_name: str) -> str | None:
        """The account a shared channel names, by ID first, then by name."""
        return self.by_channel_id.get(channel_id) or self.by_channel_name.get(channel_name)

    def slack(
        self, channel_account: str | None, author_email: str | None, author_team: str | None
    ) -> Attribution:
        domain = email_domain(author_email)
        is_vendor = (author_team is not None and author_team in self.vendor.slack_team_ids) or (
            _matches(domain, self.vendor.email_domains) is not None
        )
        role = VENDOR if is_vendor else CUSTOMER
        if channel_account:
            return Attribution(channel_account, role, "channel")
        if not is_vendor and (match := _matches(domain, self.by_domain)):
            return Attribution(self.by_domain[match], role, "email_domain")
        return Attribution(None, role, "none")

    def github(self, author_association: str | None) -> Attribution:
        role = VENDOR if (author_association or "").upper() in _GITHUB_STAFF else CUSTOMER
        return Attribution(None, role, "none")
