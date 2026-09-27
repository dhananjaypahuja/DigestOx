# 0003. Publish the team doc with sync first and ownership checked before every push

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, adopting the second round of ChatGPT's plan review
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

Pulse publishes `docs/customer-friction.md` by committing inside the team-context checkout.
Pulse owns the file and must never overwrite someone else's edit. Three facts from ox 0.18.0
shape how:

- **The daemon only pulls team context.** It never pushes (`internal/daemon/sync_team.go`),
  and it pulls every 15 seconds while running (`internal/daemon/config.go:135`).
- **The daemon locks its own git operations.** It serializes them with a per-clone lock
  (`internal/gitutil/repolock.go`). A raw `git pull --rebase` from Pulse wouldn't take that
  lock, and could corrupt `FETCH_HEAD` the way ox's own incident review of 2026-09-02
  describes.
- **Revision 2 of the plan checked ownership before syncing.** The review caught this: a sync
  after the check could fetch a foreign edit that the publish would then overwrite.

## Decision

1. `ox sync`.
2. Check that the doc in the checkout is exactly what Pulse last published.
3. Write the doc and commit it.
4. Before every push, check again against the doc in the **parent** of Pulse's commit. The
   daemon's own pulls can bring in a foreign edit after step 2. Pushes are fast-forward only,
   so if the parent holds what Pulse last published, no one else's edit can be overwritten.
5. `git push`, never force.
6. If the push is rejected, run `ox sync` (the daemon pulls and rebases under its lock), repeat
   step 4, and push once more.
7. If any check fails, the rebase fails, or the second push is rejected:
   - drop Pulse's own unpushed commit
   - leave the other edit in place
   - record the step
   - stop to ask

   Pulse never resolves a conflict in the team doc.
8. Confirm the remote `main` equals the local commit.
9. Prove the doc is listed from a fresh session's start-up prime (see
   [0008](0008-no-prime-or-doctor-inside-a-working-session.md)).

## Consequences

- Publishing can stop and ask, which is correct when a person edited the doc.
- Session 6 tests this against a local bare remote, injecting a foreign edit before the check
  and again during the retry sync.
- `publish_steps` records each step, so a retry resumes where it stopped.

## Alternatives considered

- **Retry with a raw `git pull --rebase`:** races the daemon's fetch.
- **Take ox's lock by mirroring its sidecar path:** couples Pulse to ox internals.
- **Commit and let the daemon push:** the daemon never pushes team context.

## References

- DESIGN.md, section 9
- `docs/upstream/docs-that-disagree-with-the-code.md`, which covers the guide that says the
  daemon pushes
