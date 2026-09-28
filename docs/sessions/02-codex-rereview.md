# Codex re-review: foundation hardening

- **Date:** 2026-09-28 (PDT)
- **Reviewed range:** `30ccb9c..02dccb7`, Claude's foundation repairs after the six findings in
  Codex's review of `95fc080`.
- **Fix commit:** `ca5cadd` (`fix: close replacement and database path privacy bypasses`),
  requested by Dhananjay and pushed with this documentation follow-up.
- **Plan:** `2026-09-27-customer-pulse-v1-build-plan`.
- **SageOx checkpoint:** `codex-re-review-checkpoint-foundation-hardening`, saved and read back
  locally with `ox plan view`. Remote SageOx sharing and search indexing are not confirmed.

## Verdict

The six repairs in session 1b were re-tested successfully. The re-review then found two
adversarial bypasses and fixed them before session 2:

1. **SQLite conflict replacement could rewrite immutable history.** With the default connection
   settings, `INSERT OR REPLACE` deletes the conflicting row without firing the append-only or
   immutable DELETE trigger. A replacement could therefore downgrade an approved digest or turn
   a successful publish event into a failed event. `db.connect` now enables
   `PRAGMA recursive_triggers = ON`; regression coverage proves both replacements are refused
   and the original records remain visible.
2. **A dangling database symlink bypassed the privacy gate.** `Path.exists()` omitted the link,
   then SQLite followed it and created the target with default permissions. State inspection now
   includes dangling links; init refuses symlinks and other non-regular database/companion paths,
   uses `O_NOFOLLOW` where available, and returns stable error code
   `database_path_not_regular`. The regression test proves no outside target is created.

No product behavior outside these two fixes was changed. Migration `0001` remains untouched;
the connection-level trigger setting protects migration `0003`'s existing append-only guards.

## Validation

- `.venv/bin/pytest -q`: **157 passed**.
- `.venv/bin/ruff check .`: clean.
- `.venv/bin/ruff format --check .`: clean; 51 files already formatted.
- `git diff --check`: clean before `ca5cadd`.
- Focused adversarial tests cover `INSERT OR REPLACE` against approved digests and successful
  publish events, plus a dangling `pulse.db` symlink.

The previous Codex review's startup result still stands: Claude Code's project `SessionStart`
hook automatically delivered `<ox-prime>` in a fresh `--init-only` launch, so no manual prime is
needed. This review did not run prime, doctor, recording repair, or alter the other open
recordings (`OxyOAs` and `OxD7vu`).

## Next step

Foundation is ready for the next planned stage after these fixes. Session 2 still needs the
separate explicit approval to run `ox init` in `~/Workbench/bivo-platform` and Dhananjay to start
the short Bivo session. The stale “pushing waits for Dhananjay's OK” line in the 1b record is
corrected by this real follow-up commit.
