"""A deterministic stand-in for Claude that records every request it receives.

It groups by keywords, reuses an existing theme whose title matches, and otherwise proposes
one. It never touches the network.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from customer_pulse.llm import Reply

_THEME = re.compile(r'<theme id="(th_\d+)" title="([^"]*)">')
_SIGNAL = re.compile(r'<evidence signal_id="(\d+)"[^>]*>\n(.*?)\n</evidence>', re.S)

# Checked in order: the first match wins.
RULES = [
    ("sso", "Coaches sent back to login after SSO", ("saml", "login")),
    ("roster", "Roster import rejects apostrophes", ("roster", "import")),
    ("wearable", "Workouts missing after wearable sync", ("workout", "sync", "class")),
    ("coach", "Coach attention filter missing", ("filter", "coaches")),
]
OTHER = ("other", "Other requests", ())


def classify(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for key, title, words in RULES:
        if any(word in lowered for word in words):
            return key, title
    return OTHER[0], OTHER[1]


class FakeModel:
    def __init__(self, *, drop_one: bool = False) -> None:
        self.requests: list[dict[str, Any]] = []
        self.drop_one = drop_one

    def __call__(self) -> FakeModel:  # the transport factory
        return self

    def send(self, body: dict[str, Any]) -> Reply:
        self.requests.append(json.loads(json.dumps(body)))
        user = body["messages"][0]["content"]
        existing = {html.unescape(title): theme for theme, title in _THEME.findall(user)}
        proposals: dict[str, dict[str, str]] = {}
        assignments = []
        for signal_id, text in _SIGNAL.findall(user):
            key, title = classify(html.unescape(text))
            if title in existing:
                theme = existing[title]
            else:
                proposals.setdefault(key, {"key": key, "title": title, "summary": f"{title}."})
                theme = f"new:{key}"
            assignments.append(
                {
                    "signal_id": int(signal_id),
                    "theme": theme,
                    "confidence": 0.8,
                    "rationale": f"Mentions {key}.",
                }
            )
        if self.drop_one and assignments:
            assignments.pop()
        answer = {"new_themes": list(proposals.values()), "assignments": assignments}
        return Reply(json.dumps(answer), len(user) // 4, 200, body["model"])


def never_called() -> Any:
    raise AssertionError("the model must not be called here")
