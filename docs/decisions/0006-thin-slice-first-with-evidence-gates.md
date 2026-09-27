# 0006. Build a thin slice first, with evidence and gates in every session

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, approving revision 3 of the build plan
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

Pulse matters only if a coding agent acts on reviewed customer evidence, so that loop has to
be proved early. Revision 1 of the plan proved it loosely. Two rounds of ChatGPT review found
nine gaps, and all nine were adopted:

- the loop lacked explicit evidence at each stage
- the time and privacy rules came after the first publish
- the preflight used the wrong repo
- approval had no negative tests
- theme stability was checked late
- the plan page wasn't durable
- the publish order was wrong
- the closure rule was too narrow

## Decision

Thirteen recorded sessions, each with one outcome and an evidence line.

- **Thin slice, sessions 1 to 8.** These close the loop on a few synthetic threads:
  1. foundation
  2. Bivo's repo and a preflight on a real Bivo session
  3. readers and the stored-data privacy gate
  4. the Claude module, the request gate, and stable themes
  5. the digest, review, and the approval gate
  6. publishing the team doc
  7. a fresh agent in Bivo that reads the doc and commits a fix
  8. reconciliation and the next digest
- **Breadth, sessions 9 to 13:** the CSV workbench, week-over-week comparison and the archive,
  the full dataset, evaluation, and the demo run.

Sessions 2 and 7 are short Claude Code sessions that Dhananjay starts in Bivo's repo.

The plan of record is in the SageOx ledger as `2026-09-27-customer-pulse-v1-build-plan`, and
its status there is approved.

## Consequences

- The first live model call and the first publish come after their gates.
- Two more sessions than revision 1, in exchange for a trustworthy first publish.

## References

- The ledger plan above (`ox plan view 2026-09-27-customer-pulse-v1-build-plan`)
- Decision records [0003](0003-publish-with-sync-first-and-parent-checked-pushes.md),
  [0004](0004-flag-re-reports-even-when-the-closure-precedes-the-window.md), and
  [0005](0005-privacy-gates-before-storage-model-calls-and-publishing.md)
