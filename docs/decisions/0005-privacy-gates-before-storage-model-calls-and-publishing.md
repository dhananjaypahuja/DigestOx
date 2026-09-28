# 0005. Privacy gates before storage, before model calls, and before publishing

- **Status:** Accepted; amended 2026-09-28
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja, adopting the first round of ChatGPT's plan review, with
  one refinement
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

Customer text is untrusted twice: going into the model, and going into agents' context.
Revision 1 of the plan let the first live model call happen after a session whose only exit
test was deduplication. The review asked for tests proving that raw contact details, tokens,
and injection text never reach storage, logs, caches, or model requests, and that generated
output is redacted before publishing.

## Decision

Three gates, each a set of tests that must pass before the next step:

1. **Stored data (session 3).**
   - Attribution by email domain happens before redaction.
   - No raw email address, phone number, or token appears in any SQLite text column or log.
2. **Model requests (session 4), before any live call.**
   - Captured requests and cache entries hold no raw contact details or secrets.
   - Evidence goes to the model only inside delimiters.
   - Thread context stops at the cutoff.
3. **Output (session 6).** Generated text that contains a contact detail is redacted before
   the doc is written.

**Refinement.** Prompt-injection text can't be kept out of storage or requests, because it
*is* evidence: one planted case is an injection line that must survive as quoted evidence.
Instead it travels only inside delimited evidence blocks, and a typed output schema keeps it
from steering the result.

## Amendment, 2026-09-28: local state is private

Codex's review of `95fc080` (finding R6) found that an existing state directory kept its mode.
With a 0755 directory, `pulse init` succeeded and the new database was 0644, so other local
users could read it. The review asked Pulse to reject unsafe state or obtain consent, rather
than silently change a directory the user chose.

<!-- SOURCE: sageox plan:2026-09-28-codex-session-1-review-95fc080 -->

- Pulse creates the state directory as 0700, and the database file as 0600 before SQLite
  opens it. SQLite gives its journal files the database's permissions.
- Existing state that other users can read (the directory, the database, or a SQLite
  companion file) is refused with a stable error code and the exact `chmod` to run. Pulse
  never changes permissions itself.
- `pulse status` reports the same problems as warnings and changes nothing.
- Pulse doesn't ask for consent: `--json` and non-interactive runs can't answer a prompt, and a
  refusal behaves the same everywhere.
- The checks rely on POSIX permissions. On other systems Pulse can't make them.

## Consequences

- The first live call waits for the session 4 tests.
- The first publish waits for the session 6 test.
- Redaction is pattern-based and never done by the model. Names are kept.

## References

- DESIGN.md, section 6
- `docs/sessions/00-setup-and-plan.md`
- `src/customer_pulse/state.py` and `tests/test_cli_state.py` (the amendment)
