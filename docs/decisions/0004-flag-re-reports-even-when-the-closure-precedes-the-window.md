# 0004. Flag re-reports even when the issue closed before the digest window

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, adopting the second round of ChatGPT's plan review
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

The design's "reported after issue closure" flag marks a customer report about an issue that
had already closed. Revision 2 of the plan required both the closure and the report to fall
inside the digest window. That hides the most useful case: an issue closed last week and
reported again this week.

## Decision

Flag a report when all three hold:

1. the report is inside the digest window and before its cutoff (`window_start <= t < cutoff`)
2. a **confirmed** `reports` link ties it to the issue (a mere mention never counts)
3. the issue's `closed_at` is earlier than the report

The closure may fall before the window. The digest shows the issue's `stateReason` beside the
flag and never calls it a regression.

## Consequences

The view `v_run_reported_after_closure` (migration `0001`) implements the rule.
`tests/test_schema.py` covers five cases:
- a closure a week before the window (flagged)
- a closure after the report (not flagged)
- an unconfirmed link (not flagged)
- a mention (not flagged)
- a report after the cutoff (not flagged)

## Alternatives considered

- **Both dates inside the window:** hides re-reports of recently closed issues. Rejected.

## References

- DESIGN.md, section 8
- `src/customer_pulse/migrations/0001_initial.sql`
- `tests/test_schema.py`
