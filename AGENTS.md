<!-- ox:prime-check -->
Run `ox agent prime` at session start to load SageOx team context — it's fine to read the user's request first.

# AI Agent Instructions

<!-- ox:prime --> Run SageOx `ox agent prime` on session start, after compaction, or clear. (DO NOT REMOVE)

## Working in this repo

Customer Pulse is built in recorded sessions against an approved plan (SageOx ledger:
`2026-09-27-customer-pulse-v1-build-plan`). Read `DESIGN.md`, `docs/decisions/`, and the latest
record in `docs/sessions/` before changing anything.

- **Develop:** `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
- **Start of a session:** confirm the previous session's recording uploaded (`ox session list`),
  and that `ox session status` shows this one recording.
- **After each session and commit**
  ([decision 0009](docs/decisions/0009-keep-review-context-in-sageox.md)):
  - record each new decision in `docs/decisions/` and check it with
    `ox decision enrich --file <record>`
  - write the session's record in `docs/sessions/`, commit it, and save it with
    `ox plan save --file <record> --kind evidence`
  - after each commit, refresh and save that evidence record immediately, even while the
    recording remains active; include the actual commit SHA, session/plan references,
    decisions and rationale, critiques with open/resolved status, validation actually run,
    and the next step for Claude or Codex. Apply this to review-only handoffs too
  - verify the checkpoint with `ox plan view <returned-slug>` and give the next agent that
    exact command. Local ledger retrieval is distinct from remote sync or search indexing;
    report any unverified sharing status. Do not wait for recording upload to save context,
    or create recursive bookkeeping commits just to include a record's own commit SHA
  - keep `DESIGN.md` current
- **ox rules** ([decision 0008](docs/decisions/0008-no-prime-or-doctor-inside-a-working-session.md)):
  - once the session-start hook has primed, don't run `ox agent prime` or `ox doctor` again
    mid-session
  - run ox subprocesses with stdin closed
  - leave recording repair to Dhananjay
- **Ask first:** pushing, issues or PRs, `ox import`, writing to team context, murmurs, and
  invites all need Dhananjay's OK every time.
- **Secrets:** never print environment variables or read `.env` or credential files.
- **Data:** synthetic only. Every email address and web URL uses a `.example` domain; fixture
  issue URLs use the nonexistent `bivo-fictional/bivo-platform`.
