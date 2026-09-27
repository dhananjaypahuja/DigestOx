# 0005. Privacy gates before storage, before model calls, and before publishing

- **Status:** Accepted
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

## Consequences

- The first live call waits for the session 4 tests.
- The first publish waits for the session 6 test.
- Redaction is pattern-based and never done by the model. Names are kept.

## References

- DESIGN.md, section 6
- `docs/sessions/00-setup-and-plan.md`
