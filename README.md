# Customer Pulse

> **Everything in the demo is fictional.** Bivo, its customers, their messages, the GitHub
> issues, the support tickets, and the Bivo codebase are invented for this project. No real
> customer data is used anywhere.

Customer Pulse turns a software vendor's scattered customer feedback (shared Slack channels,
GitHub issues, and a messy support-ticket CSV) into an evidence-backed friction digest. A
person reviews the draft, and the reviewed findings are published into
[SageOx](https://sageox.ai) team context, so coding agents know what customers are struggling
with before they touch the code.

It was built as an application project for SageOx's Forward Deployed Engineer role, in
recorded [ox](https://github.com/sageox/ox) sessions.

## Status

v1 is being built in 13 recorded sessions, thin slice first; the approved plan lives in the
SageOx ledger. **Sessions 1 to 4 are done:**

- the SQLite schema, with every table and view the design calls for
- the time model: UTC storage, a configured timezone, half-open windows, and cutoffs
- `pulse init` and `pulse status`
- Bivo's fictional vendor repo and a preflight against its real ox sessions (session 2)
- the Slack and GitHub readers, attribution, and pattern redaction, with a privacy gate
  proving no raw contact detail or secret is stored or logged (session 3)
- the Claude module, with a request gate, a request-hash cache, and replay, and theme
  grouping with stable IDs (session 4)

The digest, review, and publishing arrive in sessions 5 to 8.

## Quick start

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pulse init              # create the local database
uv run pulse status            # add --json for machine-readable output
uv run pytest
```

Import the thin fictional fixtures:

```sh
uv run pulse accounts load fixtures/thin/accounts.json
uv run pulse import slack fixtures/thin/slack/export-a      # a Slack export ZIP or folder
uv run pulse import slack fixtures/thin/slack/export-b      # overlaps export-a; no duplicates
uv run pulse import github fixtures/thin/github/issues-2026-09-20.json
```

The GitHub file is `gh issue list --state all --json
number,title,body,url,author,createdAt,state,stateReason,closedAt,labels,comments` output.
Importing the same file twice changes nothing. Only redacted text is stored.

Group the imported signals into themes:

```sh
uv run pulse replay load fixtures/replay/thin-group.json   # saved responses: no key, no cost
uv run pulse group --window 2026-09-14..2026-09-20          # answers only from saved responses
uv run pulse group --window 2026-09-14..2026-09-20 --live   # calls Claude; spends API credit
```

`--live` needs Anthropic credentials in the environment (`ANTHROPIC_API_KEY`, or an
`ant auth login` profile). Pulse never stores or prints them.

Every command accepts `--json`. Errors in JSON mode print `{"error": {"code": ..., "message":
...}}` and exit with status 1, so an agent can drive Pulse too.

## Configuration

Pulse reads `pulse.toml` from the working directory, from `--config PATH`, or from the path in
`PULSE_CONFIG`. Without a file it uses the defaults.

| Key | Default | Meaning |
|---|---|---|
| `pulse.timezone` | `UTC` | IANA timezone for digest windows. A window covers whole local calendar days here; everything is stored in UTC. |
| `pulse.state_dir` | `.pulse` | Where the SQLite database and `pulse.log` live, relative to the config file. Git ignores it. |
| `vendor.name` | none | The vendor whose customers Pulse tracks |
| `vendor.email_domains` | none | Its staff's email domains. Their messages are kept as context but never counted as customer evidence |
| `vendor.slack_team_ids` | none | Its Slack workspace IDs, for the same purpose |
| `llm.model` | `claude-opus-5-5` | The one model every task uses (decision 0012). Changing it invalidates saved responses |
| `llm.effort` | `high` | `low`, `medium`, `high`, `xhigh`, or `max` |
| `llm.max_tokens` | `16000` | The most a reply may use, thinking included |

Unknown keys are errors, so a typo can't silently fall back to a default.

Set `PULSE_NOW` to an ISO 8601 instant (for example `2026-10-12T17:00:00Z`) to pin the clock
for reproducible runs.

## How time works

- Every timestamp is stored as UTC text in one fixed-width form,
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`, so text order is time order.
- A window such as `2026-10-05..2026-10-11` means those local calendar days, both inclusive.
  It is stored as the half-open UTC range `[start, end)`.
- Evidence counts only when `start <= t < cutoff`. The cutoff defaults to the window end and
  may be earlier, never later. Nothing at or after the cutoff can influence a digest.

## Repository map

| Path | What it holds |
|---|---|
| [`DESIGN.md`](DESIGN.md) | The design, the verified ox facts it relies on, and how it was reached |
| [`docs/kickoff.md`](docs/kickoff.md) | The project brief |
| [`docs/upstream/`](docs/upstream/) | Draft issues about ox, found while building this, for filing upstream |
| `src/customer_pulse/` | The package; SQL migrations live in `migrations/` |
| `fixtures/` | Fictional fixtures in native export formats; see [`fixtures/README.md`](fixtures/README.md) |
| `scripts/` | The Bivo preflight and the fixture builder |
| `tests/` | pytest suite |

## License

MIT. See [LICENSE](LICENSE).
