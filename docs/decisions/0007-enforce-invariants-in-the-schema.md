# 0007. Enforce the data invariants in the SQLite schema itself

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Claude, as a code-level choice within the approved design; recorded for
  Dhananjay's review
- **Drafted by:** Claude, AI coworker, in session 1

## Context

Later code (model grouping, review commands, publishing) will write evidence and review
history. A subtle bug there could corrupt facts the digest presents as Observed. Session 1
built the whole schema before any of that code exists.

## Decision

Make the database refuse invalid states:

- **STRICT tables** throughout. The minimum SQLite version is 3.38.
- **Timestamps** must have one fixed-width UTC shape (GLOB checks), so text comparison in the
  views equals time comparison.
- **CHECK constraints:**
  - a run's cutoff sits inside its window
  - a `references` link can never be reviewed into a claim
  - a `reports` link needs a logged correction to be confirmed or rejected
  - an approved hash must equal the content hash
  - `verified` evidence names its commit
- **Triggers:**
  - corrections and assignments are append-only
  - approved digest content is frozen
  - a publish step is refused unless it carries the digest's approved hash
- **Code areas are three tables** (`code_areas`, `code_area_paths`, `theme_code_areas`) instead
  of a JSON column, so the attention view matches changed files to themes in SQL.
- **`pulse status` is read-only.** It opens the database read-only and never creates or
  migrates it.

## Consequences

- Bugs fail loudly at write time instead of producing wrong facts.
- A later move to PostgreSQL has to rewrite the STRICT, GLOB, and trigger syntax. The rest is
  plain SQL.
- `tests/test_schema.py` pins every invariant and view (81 tests in session 1).

## References

- `src/customer_pulse/migrations/0001_initial.sql`
- DESIGN.md, section 4
- `docs/sessions/01-foundation.md`
