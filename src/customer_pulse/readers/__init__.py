"""Fixed readers for sources with known formats. They parse only: attribution, redaction, and
storage happen in customer_pulse.ingest, in that order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawSignal:
    """One message or comment as exported, before attribution and redaction.

    ``raw_text`` and ``author_email`` may hold contact details and secrets. They never leave
    customer_pulse.ingest unredacted, and ``author_email`` is never stored at all.
    """

    source: str
    source_key: str
    occurred_at: datetime
    raw_text: str  # exactly as exported; its hash detects later edits
    author_name: str | None
    thread_key: str
    url: str | None = None
    issue_number: int | None = None
    # Attribution inputs
    slack_channel_id: str | None = None
    slack_channel_name: str | None = None
    author_email: str | None = None
    author_team: str | None = None
    author_association: str | None = None
    # The raw text as a person reads it (Slack markup rendered), still unredacted
    readable_text: str | None = None

    @property
    def text(self) -> str:
        return self.raw_text if self.readable_text is None else self.readable_text
