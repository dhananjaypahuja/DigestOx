# 0009. Keep every session's decisions and evidence available through SageOx

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja: "After each session and commit, make sure all your context
  about decisions and design are available using SageOx so ChatGPT can review properly."
- **Drafted by:** Claude, AI coworker, in session 1

## Context

ChatGPT reviews the work after each push, and it should see the same reasoning the coding
agent had. Session transcripts alone aren't enough: a decision buried in a long conversation is
hard to find, and the first hour of the first session is missing from the ledger's list.

## Decision

After each session and commit:

1. **Decision records.** Every significant decision gets a numbered record in
   `docs/decisions/`, checked with `ox decision enrich --file`. SageOx discovers that directory,
   and `ox code search` indexes it.
2. **Session records.** Each session gets a record in `docs/sessions/`: its outcome, evidence,
   commits, decisions, and open items. The record is committed and also saved to the SageOx
   ledger with `ox plan save --kind evidence`.
3. **Design.** DESIGN.md stays current with what was built.
4. **Commits.** Every commit carries the `SageOx-Session:` trailer that ox's git hook adds,
   linking the code to its recording.
5. **Recordings.** A session's recording uploads when the Claude Code session ends. The next
   session starts by checking that it did (`ox session list`).
6. **The plan.** The build plan's lifecycle stays current in the ledger (`ox plan work`, and
   `ox plan realize` when v1 is done).

## Consequences

- Reviewers find the same context on GitHub and in SageOx.
- Each session spends a few minutes on records. That cost is accepted.

## References

- `docs/decisions/`
- `docs/sessions/`
- `AGENTS.md`, "Working in this repo"
