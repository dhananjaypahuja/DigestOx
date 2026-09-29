"""Pattern-based redaction of contact details and secrets. Never done by a model.

Only redacted text is stored, sent to a model, or published (DESIGN.md section 6). People's
names are kept. Each match becomes a marker naming what was removed, so a reader can still
follow the evidence: "email me at [redacted email]".

The patterns favour catching too much over too little. Their known limits: a secret with no
recognisable shape (no prefix, no ``key=`` label) isn't caught, and a phone number written
with fewer than nine digits isn't either.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

EMAIL = "email"
PHONE = "phone"
SECRET = "secret"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Secrets: shapes that are secrets whatever surrounds them. Order matters only for readability;
# every pattern is applied.
_SECRET_SHAPES = [
    re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),  # JWT
    re.compile(r"\b[A-Za-z]{2,12}_(?:live|test|prod)_[A-Za-z0-9_]{12,}"),  # vendor_live_sk_...
    re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|ant|proj)[-_][A-Za-z0-9_-]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprse]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key IDs
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]

# Secrets identified by their label: keep the label, remove the value.
_BEARER = re.compile(r"\b(Bearer|Basic|Token)(\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_LABELLED = re.compile(
    r"\b((?:api[_-]?key|apikey|access[_-]?key|secret(?:[_-]?key)?|client[_-]?secret|password|"
    r"passwd|pwd|token|auth[_-]?token|access[_-]?token|refresh[_-]?token)"
    r"[\"']?\s*[:=]\s*[\"']?)(?!\[redacted )([^\s\"',;]{4,})",
    re.IGNORECASE,
)

# Phone numbers: an optional country code, an optional bracketed area code, then groups of
# digits separated by spaces, dots, or hyphens. A match counts only with 9 to 15 digits, so
# member IDs, versions, and dates are left alone.
_PHONE = re.compile(
    r"(?<![\w.+-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,5}\)[\s.-]?)?\d{2,5}(?:[\s.-]\d{2,5}){1,5}"
    r"(?![\w.-]*\w)"
)
_PHONE_DIGITS = range(9, 16)
_DATE_LIKE = re.compile(r"\d{4}-\d{2}-\d{2}")

MARKERS = {EMAIL: "[redacted email]", PHONE: "[redacted phone]", SECRET: "[redacted secret]"}


@dataclass
class Redaction:
    """Redacted text and how many of each kind were removed. The counts carry no content."""

    text: str
    counts: Counter[str] = field(default_factory=Counter)


def redact(text: str) -> Redaction:
    """Remove secrets, then email addresses, then phone numbers."""
    counts: Counter[str] = Counter()

    def sub(pattern: re.Pattern[str], kind: str, value: str, keep_group: int = 0) -> str:
        def replace(match: re.Match[str]) -> str:
            counts[kind] += 1
            kept = "".join(match.group(i) for i in range(1, keep_group + 1))
            return kept + MARKERS[kind]

        return pattern.sub(replace, value)

    out = text
    for shape in _SECRET_SHAPES:
        out = sub(shape, SECRET, out)
    out = sub(_BEARER, SECRET, out, keep_group=2)
    out = sub(_LABELLED, SECRET, out, keep_group=1)
    out = sub(_EMAIL, EMAIL, out)

    def phone(match: re.Match[str]) -> str:
        found = match.group(0)
        digits = sum(ch.isdigit() for ch in found)
        if digits not in _PHONE_DIGITS or _DATE_LIKE.fullmatch(found):
            return found
        counts[PHONE] += 1
        return MARKERS[PHONE]

    out = _PHONE.sub(phone, out)
    return Redaction(out, counts)


def redact_text(text: str | None) -> str | None:
    """Redacted text only, for fields whose counts aren't reported."""
    return None if text is None else redact(text).text


def find_raw(text: str) -> list[str]:
    """The kinds of contact detail or secret still present in ``text``. Used by checks that
    stored or logged text holds nothing redaction should have removed."""
    return sorted(kind for kind, n in redact(text).counts.items() if n)
