# 0008. Never run `ox agent prime` or `ox doctor` inside a working session

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, approving the plan that carries this rule
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

Three things were observed or read on ox 0.18.0 during the first session:

- **Re-running `ox agent prime` inside a live session started a new recording** for the same
  agent. The earlier part of that session no longer appears in the ledger's session list
  (`docs/upstream/reprime-started-a-new-recording.md`).
- **`ox agent prime` waits forever when stdin is an open pipe**, which is the normal state of an
  agent's tool shell (`docs/upstream/prime-waits-on-open-stdin.md`).
- **`ox doctor` without flags isn't read-only.** It starts the daemon and applies the checks
  marked `FixLevelAuto` (`cmd/ox/doctor.go:172`, `cmd/ox/doctor_types.go:13-16`).

## Decision

- Pulse never calls `ox agent prime` or `ox doctor`.
- Agents working on this repo don't run either mid-session. They use `ox status` and
  `ox session status` for checks.
- ox subprocesses always run with stdin closed.
- Whether a team doc is listed is proved only from a **fresh** agent session's start-up prime.

## Consequences

- The listing proof for the team doc moves to session 7 of the plan.
- Setup checks don't include `ox doctor`.

## References

- `docs/upstream/`
- DESIGN.md, section 14
