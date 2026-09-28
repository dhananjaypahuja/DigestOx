# 0010. Bind every run to an evidence snapshot

- **Status:** Accepted
- **Date:** 2026-09-28
- **Decided by:** Claude, fixing review finding R2 at Dhananjay's request; recorded for
  Dhananjay's review
- **Drafted by:** Claude, AI coworker, in session 1b

## Context

Design principle 9 says nothing after a digest's cutoff can influence it. Session 1 applied
that to the times of messages, replies, and sessions, but not to the evidence itself. Codex's
review of `95fc080` (2026-09-28) reproduced the gap: `v_run_reported_after_closure` read each
issue's latest observation across all imports. Importing a later GitHub export changed the
facts of a run that already existed, and with them the facts behind its digest.

<!-- SOURCE: sageox plan:2026-09-28-codex-session-1-review-95fc080 -->

Two constraints shape the fix:
- The review asked for an explicit representation of historical evidence, not a time filter
  bolted onto the live view.
- A GitHub export holds each issue's current state and `closedAt`, with no reopen history. A
  later export can show that an issue reopened, but not when.

## Decision

1. **A run records its evidence.** It records the imports (`run_imports`) and engineering
   sessions (`run_sessions`) it uses. The snapshot can be recorded only while the run is
   running, and it is fixed afterwards. The run's window and cutoff are fixed too, and a
   finished run can't change status. The digest command (session 5) will snapshot every
   import and reconciled session that exists when the run starts.
2. **Run-scoped views read only the snapshot:** `v_run_signals`, `v_run_issue_observations`,
   `v_run_issue_closures`, `v_run_issue_state`, `v_run_reported_after_closure`, and
   `v_run_theme_attention`. `v_issue_latest` stays as a live view for status output, and no
   run reads it.
3. **Issue state at the cutoff is `open`, `closed`, or `unknown`.** It comes from the
   snapshot's observations in import order, for issues created before the cutoff:
   - `open`: no observation shows a closure before the cutoff.
   - `closed`: the latest observation that shows one isn't contradicted by a later
     observation.
   - `unknown`: a later observation shows the issue reopened, or closed on another date, so
     the change can't be placed relative to the cutoff.
4. **What a snapshot relies on is fixed.**
   - A signal's source, key, customer, time, thread, issue, Pulse-output flag, and first
     import can't change. Its text can still be revised, and `signal_revisions` records each
     revision.
   - Issue observations and session evidence are history: never updated or deleted.
   - Once a run has used a session, its evidence, times, and repo are fixed.
5. **Later exports aren't rejected.** They feed new runs, including earlier facts they reveal,
   such as a closure the earlier export didn't show.

## Consequences

- A run over the same window after a new import can give a different answer. It is a new run
  with its own snapshot. The earlier run, and any digest built from it, keep theirs.
- The digest shows `unknown` as unknown and never guesses.
- Migration `0002` implements this. `tests/test_snapshots.py` covers:
  - Codex's reproduction, with the earlier run unchanged
  - a reopen seen as `unknown`
  - a later export supplying an earlier closure to a new run
  - eight close and reopen orderings
  - the immutability rules

## Alternatives considered

- **Filter the live view by import time:** the bolted-on time filter the review ruled out. It
  is implicit, and it depends on two clocks agreeing.
- **Refuse imports that contradict earlier ones:** discards real information, because a later
  export can legitimately reveal an earlier closure.
- **Copy each run's computed facts into tables:** freezes the results, but duplicates every
  fact view and hides how each fact was derived.

## Related decisions

- **[0004](0004-flag-re-reports-even-when-the-closure-precedes-the-window.md) is amended:** its
  closure rule reads the snapshot.
- **[0007](0007-enforce-invariants-in-the-schema.md) is the approach this follows:** the schema
  refuses any change to a snapshot, and 0007's amendment lists the new invariants.
- **[0003](0003-publish-with-sync-first-and-parent-checked-pushes.md) aligns:** publishing
  proves which approved content was pushed, and the snapshot keeps the facts behind that
  content from changing.
- **[0006](0006-thin-slice-first-with-evidence-gates.md) aligns:** the plan moved the time
  rules before the first publish, and this extends them from timestamps to the state of the
  evidence.
- **[0008](0008-no-prime-or-doctor-inside-a-working-session.md) and
  [0009](0009-keep-review-context-in-sageox.md) don't apply.** They concern ox's own recordings
  and review context. The sessions in this record are engineering sessions in the vendor's
  repo.

## References

- `src/customer_pulse/migrations/0002_run_evidence_snapshots.sql`
- DESIGN.md, sections 3 (principle 9), 4, and 5
- `docs/sessions/01b-foundation-repairs.md`, also in the ledger as
  `2026-09-28-session-1b-foundation-repairs-after-codex`
- Codex's review: `docs/sessions/codex-session-1-review.html`, also in the ledger as
  `2026-09-28-codex-session-1-review-95fc080`

<!-- SOURCE: sageox plan:2026-09-28-session-1b-foundation-repairs-after-codex -->
