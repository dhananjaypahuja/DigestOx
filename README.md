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
SageOx ledger. **Session 1 (foundation) is done:**

- the SQLite schema, with every table and view the design calls for
- the time model: UTC storage, a configured timezone, half-open windows, and cutoffs
- `pulse init` and `pulse status`

Ingestion, themes, the digest, review, and publishing arrive in sessions 3 to 8.

## Quick start

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pulse init              # create the local database
uv run pulse status            # add --json for machine-readable output
uv run pytest
```

No API key is needed yet. The Claude module arrives in session 4.

Every command accepts `--json`. Errors in JSON mode print `{"error": {"code": ..., "message":
...}}` and exit with status 1, so an agent can drive Pulse too.

## Configuration

Pulse reads `pulse.toml` from the working directory, from `--config PATH`, or from the path in
`PULSE_CONFIG`. Without a file it uses the defaults.

| Key | Default | Meaning |
|---|---|---|
| `pulse.timezone` | `UTC` | IANA timezone for digest windows. A window covers whole local calendar days here; everything is stored in UTC. |
| `pulse.state_dir` | `.pulse` | Where the SQLite database lives, relative to the config file. Git ignores it. |

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
| `tests/` | pytest suite |

## License

MIT. See [LICENSE](LICENSE).
