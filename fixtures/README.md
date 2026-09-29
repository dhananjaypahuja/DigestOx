# Fixtures

> **Everything here is fictional.** Bivo, its customers (Morrowvale Athletic Clubs, Copperfen
> Fitness, Kettlewren Coaching, Brackenlight Strength), their people, every Slack message, and
> every GitHub issue are invented for Customer Pulse. No real customer data is used. Email
> addresses and web URLs use `.example` domains; issue URLs name
> `bivo-fictional/bivo-platform`, which doesn't exist and isn't meant to resolve. Phone numbers
> are in the ranges reserved for fiction (`555-01xx` in North America, `020 7946 0xxx` in London).

The data files stay valid in their native formats, so this notice lives here and in each
set's `manifest.json` rather than inside them.

## `thin/`: the thin slice (sessions 3 to 8)

A small week, 14 to 20 September 2026 in `America/Los_Angeles`, just big enough to prove each
stage of the loop. `scripts/build_thin_fixtures.py` writes every file; re-running it changes
nothing.

| Path | Format | What it is |
|---|---|---|
| `accounts.json` | Pulse's own | The four customers, the shared Slack channel that names each, and their email domains |
| `slack/export-a/` | Slack export, unzipped | Taken on 17 September at 09:30: 14 to 17 September |
| `slack/export-b/` | Slack export, unzipped | Taken on 20 September: 16 to 20 September. Overlaps export A on the 16th and 17th, and carries one edited message |
| `github/issues-2026-09-17.json` | `gh issue list --state all --json number,title,body,url,author,createdAt,state,stateReason,closedAt,labels,comments` | Three issues as seen on 17 September |
| `github/issues-2026-09-20.json` | the same | Four issues as seen on 20 September; #23 has closed since |
| `manifest.json` | Pulse's own | The notice, the files, the planted raw values the privacy tests search for, and each planted case |

A real Slack export arrives as a ZIP. The reader accepts the ZIP or its unzipped folder, and
the tests zip these folders to cover both.

The planted cases are listed in `manifest.json`. The privacy-relevant ones are a phone number,
an email address in Slack's `mailto:` markup, an email and a bearer token in an issue body, a
pasted API key, and a prompt-injection line that must survive as quoted evidence.

## `replay/`: saved model responses

`thin-group.json` holds the response from session 4's one live grouping run on the thin
fixtures (`claude-opus-5-5` at high effort, 29 September 2026; 3,327 input and 1,836 output
tokens, $0.05). `pulse replay load` checks each request's hash, and `pulse group` then answers
from it with no key and no cost. It holds only redacted text; the injection line appears as
quoted evidence. If the grouping prompt, schema, settings, or fixtures change, the request's
hash changes and replay reports a miss until a new live run replaces this file.

The full two-week dataset (session 11) and its evaluation answers (under `eval/`, readable only
by `pulse eval`) arrive later.
