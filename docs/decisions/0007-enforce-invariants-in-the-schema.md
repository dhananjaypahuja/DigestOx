# 0007. Enforce the data invariants in the SQLite schema itself

- **Status:** Accepted; amended 2026-09-28
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

## Amendment, 2026-09-28: invariants added after Codex's review

Codex's review of `95fc080` reproduced four states the schema still allowed (findings R1 to
R4). Migration `0001` stays unedited. Migrations `0002` to `0004` add:

<!-- SOURCE: sageox plan:2026-09-28-codex-session-1-review-95fc080 -->

- **Runs** ([0010](0010-bind-every-run-to-an-evidence-snapshot.md)): the window and cutoff are
  fixed, a run finishes once, and its evidence snapshot is recorded only while it runs.
- **Evidence:** issue observations and session evidence are history. A signal's identity,
  time, customer, thread, issue, and first import are fixed. Once a run has used a session,
  its evidence and times are fixed.
- **Digests:** a digest is created as an unapproved draft, and its status only moves forward.
  Approval happens only as a draft becomes approved, and it is final. Content, run, and lineage
  are frozen once a digest leaves draft, and such digests are kept. This replaces the trigger
  that froze only approved content, which a downgrade to draft could bypass.
- **Publishing:** `publish_events` replaces `publish_steps`. It is append-only, and every
  success carries its proof (see [0003](0003-publish-with-sync-first-and-parent-checked-pushes.md)'s
  amendment).
- **Themes:** a theme merges only into an active theme, merges and split lineage are final,
  and themes are kept, so a merge cycle can't form. Resolution follows chains to any depth,
  and `v_theme_unresolved` must stay empty.
- **Migration guards:** a migration stops rather than drop existing records (`publish_steps`)
  or accept a broken state (a merge cycle).

Two working rules came out of the repairs:
- A shipped migration is never edited. A fix is a new migration.
- Each rule has one owner, a single trigger or CHECK, so every refusal names one clear reason.
  SQLite doesn't define the order of several BEFORE triggers, so a statement that breaks two
  rules at once may report either.

`tests/test_snapshots.py`, `tests/test_publishing.py`, and `tests/test_themes.py` pin the new
invariants. The suite has 155 tests after session 1b.

## Consequences

- Bugs fail loudly at write time instead of producing wrong facts.
- A later move to PostgreSQL has to rewrite the STRICT, GLOB, and trigger syntax. The rest is
  plain SQL.
- `tests/test_schema.py` pins every invariant and view (81 tests in session 1).

## References

- `src/customer_pulse/migrations/0001_initial.sql`, and `0002` to `0004` (the amendment)
- DESIGN.md, section 4
- `docs/sessions/01-foundation.md`
