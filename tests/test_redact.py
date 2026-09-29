"""Redaction removes contact details and secrets by pattern, and leaves ordinary text alone."""

import pytest

from customer_pulse.redact import find_raw, redact

# Built at runtime, so no token-shaped string sits in the repository for scanners to flag.
GITHUB_TOKEN = "ghp_" + "A1b2C3d4" * 5
SLACK_TOKEN = "xoxb-" + "1234567890-abcdefghij"
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [
        ("mail dana.whitcombe@morrowvale.example today", "email", "mail [redacted email] today"),
        (
            "<mailto:a.b@c.example|a.b@c.example>",
            "email",
            "<mailto:[redacted email]|[redacted email]>",
        ),
        ("call +1 (415) 555-0142", "phone", "call [redacted phone]"),
        ("call +44 20 7946 0958.", "phone", "call [redacted phone]."),
        ("or 415-555-0142 or 415.555.0142", "phone", "or [redacted phone] or [redacted phone]"),
        (
            "Authorization: Bearer abcdefgh12345678",
            "secret",
            "Authorization: Bearer [redacted secret]",
        ),
        (
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl",
            "secret",
            "jwt [redacted secret]",
        ),
        ("key bivo_live_sk_7Qm2Xr9LpT4vW8zN3cK6 here", "secret", "key [redacted secret] here"),
        ("api_key=abcd1234efgh", "secret", "api_key=[redacted secret]"),
        ('password: "hunter22!"', "secret", 'password: "[redacted secret]"'),
        (f"token={GITHUB_TOKEN}", "secret", "token=[redacted secret]"),
        (f"slack {SLACK_TOKEN}", "secret", "slack [redacted secret]"),
        (f"aws {AWS_KEY}", "secret", "aws [redacted secret]"),
    ],
)
def test_redacts(text, kind, expected):
    result = redact(text)
    assert result.text == expected
    assert set(result.counts) == {kind}
    assert find_raw(result.text) == []


@pytest.mark.parametrize(
    "text",
    [
        "members MV-40213 and MV-40877 did 3 classes",
        "version 2.14.1 on 2026-09-17 at 10:40",
        "412 members, order 1234 5678",
        "sync ok member=MV-39120 fetched=50",
        "https://github.com/bivo-fictional/bivo-platform/issues/18#issuecomment-2780",
        "Slack ts 1789402320.000100",
        "a sha 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "Names like O'Neill and D'Souza get rejected",
        "the token expired, the password reset page works",
    ],
)
def test_leaves_ordinary_text_alone(text):
    result = redact(text)
    assert result.text == text
    assert not result.counts


def test_redacting_twice_changes_nothing():
    once = redact("reach me at +1 (415) 555-0142 or ines@copperfen.example; token=abcd1234efgh")
    assert redact(once.text).text == once.text
    assert not redact(once.text).counts


def test_find_raw_names_what_remains():
    assert find_raw("mail a@b.example, call +1 415 555 0100") == ["email", "phone"]
