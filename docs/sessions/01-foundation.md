# Session 1: foundation

- **Date:** 2026-09-27 (PDT)
- **Outcome:** the `customer-pulse` package, the time model, the full schema, and
  `pulse init` and `pulse status`, all tested.
- **Recording:** SageOx session `ses_01a0e4a5`. Every commit below carries its
  `SageOx-Session:` trailer.
- **Plan:** session 1 of the approved plan `2026-09-27-customer-pulse-v1-build-plan`.

## What was built

- **Package:** `customer-pulse` (uv, Typer, pytest, ruff, MIT licence), with a README that
  leads with the fictional-data notice.
- **Time model** (`src/customer_pulse/timewin.py`, `clock.py`):
  - timestamps stored as fixed-width UTC text
  - windows of whole local days stored as half-open UTC ranges
  - evidence counted only when `start <= t < cutoff`
  - `PULSE_NOW` to pin the clock
- **Schema:** migration `0001` with every table and view in DESIGN.md section 4, enforcing its
  own invariants ([decision 0007](../decisions/0007-enforce-invariants-in-the-schema.md)).
- **Migration runner** (`src/customer_pulse/db.py`):
  - applies each migration in order, in its own transaction
  - records a checksum for each
  - refuses edited migrations, and databases from a newer Pulse
- **CLI:**
  - `pulse init` creates the database in a private state directory.
  - `pulse status` reports without changing anything.
  - Both support `--json`, with stable error codes.
- **Config:** `pulse.toml` is validated strictly; unknown keys are errors.
- **Upstream drafts:** seven draft ox issues in `docs/upstream/`.

## Evidence

The plan asked that both commands run on an empty database and that the window tests pass at
both edges and on a daylight-saving day.

```text
$ uv run pulse status
  database  .pulse/pulse.db is not initialized. Run `pulse init`.
$ uv run pulse init
Created .pulse/pulse.db: applied migration 0001, now at schema 1.
$ uv run pulse status
  database  .pulse/pulse.db, schema 1 of 1
  evidence  0 signals, 0 issues, 0 accounts, 0 imports
```

- **81 tests pass**, and `ruff check` and `ruff format --check` are clean.
- **Window tests:**
  - the start edge (included) and the end edge (excluded)
  - an earlier cutoff
  - a 169-hour fall-back week and a 167-hour spring-forward week
  - a day whose midnight falls in a daylight-saving gap
- **View tests:**
  - person over model
  - merge resolution
  - the half-open evidence range
  - customer, thread, and unattributed counts
  - the closure rule ([decision 0004](../decisions/0004-flag-re-reports-even-when-the-closure-precedes-the-window.md))
  - engineering-attention levels and cutoff
  - trend, including quiet themes
  - the last published doc
- **Each commit passes on its own.** Checked in throwaway worktrees: the scaffold builds, then
  24, 61, and 81 tests pass as the time model, schema, and CLI land.

## Commits

| Commit | Change |
|---|---|
| `d119428` | docs: add design and project kickoff |
| `5e2c8f6` | build: scaffold the customer-pulse package |
| `d55c575` | feat: add the time model and an injectable clock |
| `db6d1f0` | feat: add the SQLite schema and migration runner |
| `0bd42c7` | feat: add pulse init and pulse status |
| `7d91902` | docs: draft upstream issues found in ox 0.18.0 |
| `9b511ef` | docs: record decisions and sessions for review |
| `cac026c` | docs: add Codex's review handoff and per-commit checkpoints |

This record is committed at the session's end. Its SageOx ledger copy is refreshed after every
commit.

## Decisions

- [0007](../decisions/0007-enforce-invariants-in-the-schema.md): enforce the invariants in
  the schema; store code areas as tables.
- [0009](../decisions/0009-keep-review-context-in-sageox.md): keep every session's decisions
  and evidence available through SageOx. Amended after Codex's review to checkpoint after every
  commit.

## Review status

Codex reviewed the plan and the foundation. Its handoff is in the ledger as
`codex-plan-review-handoff-9b511ef`, and in the repo as
[codex-plan-review-handoff.md](codex-plan-review-handoff.md).

| Item | Status |
|---|---|
| First review round, 7 findings | Resolved in plan revision 2 |
| Second review round, 2 findings (publish order, closure rule) | Resolved in DESIGN.md and plan revision 3. The closure rule is implemented and tested; the publish order is designed and gets its tests in session 6 |
| Foundation tests | Codex: 81 passed at `7d91902`. Claude, checkpoint at `cac026c`: 81 passed, `ruff check` and `ruff format --check` clean |
| Replayable engineering evidence: commit the session and commit inputs so reconciliation can be replayed from a fresh clone | Open, scheduled for sessions 8 and 12 |
| CSV mapping reuse against invalid rows under the same header | Open, scheduled for session 9 |
| Evaluation metrics checked against small hand-calculated examples | Open, scheduled for session 12 |

## Open items and next session

- **Pushing** to GitHub waits for Dhananjay's OK.
- **Codex imported a preliminary handoff into team context.** It's at
  `data/docs/2026/09/27/digestox-engineering-handoff-7d91902-codex-plan-review-2026-09-27`.
  `ox import` is on the ask-first list and can't be undone from the CLI, so Dhananjay has been
  told. Session 7 will check the fresh Bivo agent's context trace for whether it surfaced.
- **Only one writer is supported.** Two `pulse init` runs at the same moment would make the
  second fail rather than wait. That's accepted for a single-user CLI.
- **The recording gap** from session 0 is still Dhananjay's decision.
- **Session 2 needs:**
  - OK to run `ox init` in `~/Workbench/bivo-platform`
  - a short Claude Code session that Dhananjay starts there, with a prompt the agent will write
- **Retrieve the context for the next agent:**
  - `ox plan view 2026-09-27-session-1-foundation` (this record)
  - `ox plan view codex-plan-review-handoff-9b511ef` (Codex's review)
  - `ox plan view 2026-09-27-customer-pulse-v1-build-plan` (the approved plan)
