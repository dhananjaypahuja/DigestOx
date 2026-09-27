# 0001. Pull ox session history instead of relying on the `session.uploaded` hook

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, answering the first session's setup questions
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

The kickoff planned a `session.uploaded` hook as a doorbell. It would append each upload event
to a local queue, and `pulse status` would report new engineering sessions from that queue. A
pull of ox's session history would remain the source of truth.

Re-checking ox 0.18.0 (`f52d5c94`) showed the hook can't ring:

- The daemon emits `session.uploaded` only from its handler for a `session_uploaded` IPC message
  (`internal/daemon/ipc_handlers.go:455-468`, `internal/daemon/daemon.go:2148-2155`).
- Nothing in ox sends that message, and nothing has since hooks shipped in #491.
- The CLI uploads a session itself and then notifies sageox.ai over HTTP
  (`cmd/ox/session_linkage_finalize.go:75`).
- `ox hooks test` runs hooks inside the CLI, so it can't reveal the gap.

The only other candidate, `sync.completed`, fires after every ledger pull: every 60 seconds
while the daemon runs.

## Decision

No hook in v1. `pulse status` and every `pulse digest` pull `ox session list --json` and
`ox session view <name> --json`, plus `git` in the vendor repo, with the **vendor repo as the
working directory**. The working directory matters because `ox session list --repo <path>`
still merges the current directory's ledger.

## Consequences

- Works with ox as shipped: one code path, no user-level `hooks.yaml`, no daemon restarts.
- There's no instant notification. Nothing in v1 needs one.
- The kickoff's hook queue is gone from the design (DESIGN.md sections 4 and 10).
- The finding is drafted for ox in `docs/upstream/session-uploaded-never-fires.md`.

## Alternatives considered

- **Doorbell on `sync.completed`:** it fires today, but every 60 seconds, and it means
  "something synced", not "a session arrived". Rejected.
- **Keep the `session.uploaded` hook registered for when ox fixes it:** offered, not chosen, to
  keep v1 simple.

## References

- DESIGN.md, section 10
- `docs/upstream/session-uploaded-never-fires.md`
- `docs/sessions/00-setup-and-plan.md`
