# Session 1b: foundation repairs after Codex's review

- **Date:** 2026-09-28 (PDT)
- **Outcome:** close the six gaps Codex reproduced in the foundation at `95fc080`, before
  session 2 starts.
- **Review:** ledger `codex-session-1-review-95fc080`; repo copy
  [codex-session-1-review.html](codex-session-1-review.html) (commit `30ccb9c`).
- **Recording:** SageOx session `ses_01a0e4a5` until the context was compacted at 10:30 PDT.
  Compaction re-ran prime, which uploaded that recording (517 entries) and started
  `ses_01a0e910`. Every commit below carries the trailer of the recording that produced it.
- **Rules followed:**
  - migration `0001` stays unedited, so every fix is a new migration
  - each finding gets regression tests, turning Codex's reproductions into assertions that
    the bad state is refused
  - the ledger checkpoint is refreshed after every commit

## Findings

| # | Finding | Status | Fix |
|---|---|---|---|
| R1 · P1 | Approval can be cleared or forged | **Resolved in `af43aec`** | Migration `0003`: approval lifecycle |
| R2 · P1 | Later issue imports rewrite historical run facts | **Resolved in `41d50a1`** | Migration `0002`: evidence snapshots |
| R3 · P2 | A merge cycle silently removes themes and facts | **Resolved in `ae7270d`** | Migration `0004`: merge rules |
| R4 · P2 | Publishing ownership proof is incomplete and mutable | **Resolved in `af43aec`** | Migration `0003`: append-only publish events |
| R5 · P2 | Filesystem and database failures escape JSON output | **Resolved in `76194a8`** | CLI error translation |
| R6 · P2 | An existing permissive state directory exposes the database | **Resolved in `76194a8`** | CLI privacy checks |

## R2: how it was fixed

**The problem.** A run read each issue's latest observation globally, so a later export could
change the facts of a run that already existed.

**The fix, in migration `0002`:**
- **Evidence snapshots.** Each run records the imports and engineering sessions it used
  (`run_imports`, `run_sessions`). The snapshot is recorded only while the run is running and
  is fixed afterwards. Every run-scoped view reads only that snapshot.
- **Honest issue state.** Issue state at the cutoff comes from the snapshot, in import order.
  It is `unknown` when a reopen can't be placed relative to the cutoff.
- **Fixed evidence.** What a snapshot relies on can't change: a signal's identity, time,
  customer, thread, and issue; issue observations; and a session's evidence once a run has used
  it. A signal's text can still be revised.
- **Later exports aren't rejected.** They feed *new* runs, including valid earlier facts they
  reveal.

**Tests** (`tests/test_snapshots.py`):
- Codex's reproduction, now asserting the run is unchanged
- a new run seeing a reopen as `unknown`
- a later export supplying an earlier closure to a new run
- eight close and reopen orderings
- the immutability rules

## R1 and R4: how they were fixed

**The problems.** An approved digest could be downgraded, have its approval cleared, and be
edited. A draft could carry approval fields and accept a successful push. A push could lack
its proof, and editing an older row could reorder which push counted as the latest.

**The fix, in migration `0003`:**
- **Lifecycle.** Digests start as unapproved drafts. Status only moves forward: draft,
  approved, published, superseded. Approval happens only as a draft becomes approved, and it
  is final.
- **Freezing.** Content, run, and lineage are frozen once a digest leaves draft. Digests that
  have left draft can't be deleted.
- **Publish records.** `publish_steps` is replaced by `publish_events`, an append-only log.
  Every success carries its proof: a document hash, a team-context commit, a listing session,
  or an archive reference.
- **Ordering.** A push must match a written document, and a listing a pushed one. A digest is
  `published` only after a successful push, and the latest push is decided by event order.
- **No silent loss.** The migration stops if `publish_steps` holds any record.

**One design detail.** Each rule has a single owner: ordering rules judge only approved
digests with a document hash, so every refusal has a clear reason. The one exception is a
statement that breaks two rules at once, such as Codex's downgrade, where SQLite doesn't
define which refusal reports first.

**Tests** (`tests/test_publishing.py`):
- both Codex reproductions, now refused
- every illegal status move
- the full forward lifecycle, a retry after a failed push, and supersession
- missing proof
- the reordering attack
- the migration guard

## R3: how it was fixed

**The problem.** A merge cycle resolved to nothing, so its assignments vanished from every fact
view. Resolution also stopped silently at a chain depth of 64.

**The fix, in migration `0004`:**
- **No cycles.** A theme can merge only into an active theme, and merges and split lineage are
  final. Closing a cycle would need a merge into an already-merged theme, which is refused.
- **Themes are kept.** Retire a theme instead of deleting it.
- **Resolution at any depth.** It follows chains to any depth, and `v_theme_unresolved` must
  always be empty.
- **No silent acceptance.** A guard stops the migration if an existing database already holds a
  cycle.

**Tests** (`tests/test_themes.py`):
- Codex's two-node cycle, refused, with the facts intact
- a three-node cycle, refused
- an 80-deep chain resolving correctly
- retired themes, final merges, and split lineage
- the migration guard

## R5 and R6: how they were fixed

**R5, errors.** Expected filesystem and SQLite failures are translated into stable codes, in
JSON and in human mode:
- `state_path_not_a_directory`, `permission_denied`, `filesystem_error`
- `database_locked`, `database_unavailable`, `database_unreadable`, `database_error`

Programming errors still raise, so a bug can't hide behind a tidy message.

**R6, privacy.** `src/customer_pulse/state.py` creates the state directory as 0700 and the
database file as 0600 before SQLite opens it. An existing directory, database, or SQLite
companion file that other users can read is refused, with the exact `chmod` to run.
Permissions are never changed silently, as Codex required, and `status` reports privacy
problems without changing anything.

**Lock wait.** Every connection now uses one explicit setting, `LOCK_WAIT_SECONDS`, instead of
relying on Python's implicit five-second default for read-only connections.

**Tests** (`tests/test_cli_state.py`):
- both Codex CLI reproductions
- denied I/O, and corrupt and locked databases
- human-mode errors on stderr with a hint
- programming errors still raising
- every error code in the mapping
- a readable database or companion file refused and reported

## Verification on real state

Upgrading this machine's own database, which session 1 created before the privacy fix,
repeated R6 on real state:
- `pulse init` refused with `other users can read pulse.db (mode 0644)` and the hint to run
  `chmod 600` on it. It changed nothing.
- After that `chmod`, `pulse init` applied migrations 0002, 0003, and 0004, and
  `pulse status` reports schema 4 of 4.
- The upgrade printed "applied migration 0002, 0003, 0004", and two migration errors printed
  raw Python lists such as `[2]`. Commit `982beff` names migration lists properly.

## Design and decision records

Commit `346b2bb` brings the documents in line with the code:
- **DESIGN.md**, sections 4, 5, 8, 9, and 14 to 16:
  - the new tables and views, and the added invariants
  - local-state privacy and the stable error codes
  - evidence snapshots and issue state at the cutoff
  - the merge rules and the publish event log
  - the compaction recording observation, the review history, and two new limits

  It also corrects two rows that were wrong since session 1: `issues` (its state lives in
  `issue_observations`) and the run modes (`offline` was missing).
- **New decision [0010](../decisions/0010-bind-every-run-to-an-evidence-snapshot.md):** bind
  every run to an evidence snapshot. It states how it relates to each decision ox flagged.
- **Dated amendments.** The original text of each decision stands:
  - [0003](../decisions/0003-publish-with-sync-first-and-parent-checked-pushes.md): ownership
    proof comes from the append-only event log; the publishing order is unchanged
  - [0004](../decisions/0004-flag-re-reports-even-when-the-closure-precedes-the-window.md): the
    closure comes from the run's snapshot
  - [0005](../decisions/0005-privacy-gates-before-storage-model-calls-and-publishing.md): local
    state is private, and exposed state is refused rather than changed
  - [0007](../decisions/0007-enforce-invariants-in-the-schema.md): the added invariants, and two
    working rules (never edit a shipped migration; one owner per rule)

`ox decision enrich --file` finds no unresolved references in any of them. It still reports
drift for the amended records, because it compares cited files against each record's original
date; the dated amendments are the answer its guidance asks for.

## Commits

| Commit | Change | Validation run |
|---|---|---|
| `41d50a1` | fix: bind runs to evidence snapshots so later imports can't rewrite them | 105 passed; `ruff check` and `ruff format --check` clean |
| `af43aec` | fix: make approval final and publishing records an append-only log | 124 passed; `ruff check` and `ruff format --check` clean |
| `ae7270d` | fix: make theme merge cycles impossible and resolve chains of any depth | 132 passed; `ruff check` and `ruff format --check` clean |
| `76194a8` | fix: report operational failures as JSON errors and keep local state private | 152 passed; `ruff check` and `ruff format --check` clean |
| `982beff` | fix: name migration lists properly in pulse output and errors | 155 passed; `ruff check` and `ruff format --check` clean |
| `346b2bb` | docs: record the foundation repairs in the design and decision records | documents only; `ox decision enrich --file` on 0003, 0004, 0005, 0007, and 0010: 0 unresolved references |

This record and its row in the sessions README are committed next, after `346b2bb`.

## Next step

All six findings are resolved and documented. Next is Codex's re-review of `30ccb9c..HEAD`.
To review:
- `ox plan view 2026-09-28-session-1b-foundation-repairs-after-codex` (this record)
- `git log --stat 30ccb9c..HEAD`, then the migrations `0002` to `0004`,
  `src/customer_pulse/state.py`, and the regression tests named above
- decision 0010 and the amendments to 0003, 0004, 0005, and 0007

Pushing waits for Dhananjay's OK. Session 2 still needs its own approvals: `ox init` in
`~/Workbench/bivo-platform`, and Dhananjay starting the short Bivo session.

Retrieve this record with `ox plan view 2026-09-28-session-1b-foundation-repairs-after-codex`.
