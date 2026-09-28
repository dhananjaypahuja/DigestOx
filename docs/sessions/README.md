# Session records

One record per working session: its outcome, the evidence for it, the commits it produced,
the decisions it made, and what it left open. Each record is committed here and also saved to
the SageOx ledger with `ox plan save --kind evidence`, so reviewers find the same context on
GitHub and in SageOx ([decision 0009](../decisions/0009-keep-review-context-in-sageox.md)).

| Session | Outcome | Record | SageOx recording |
|---|---|---|---|
| 0 | Setup verified, ox facts re-checked, design written, build plan approved | [00-setup-and-plan.md](00-setup-and-plan.md) | `ses_01a0e4a5` (the first hour is missing; see the record) |
| 1 | Foundation: package, time model, schema, `pulse init` and `pulse status` | [01-foundation.md](01-foundation.md) | `ses_01a0e4a5` |
| Codex reviews | Plan critique, resolution status, foundation verification, and the next implementation handoff | [codex-plan-review-handoff.md](codex-plan-review-handoff.md) | `ses_01a0e4f5` |
| Session 1 implementation review | Hold foundation sign-off: 2 P1 and 4 P2 findings; fresh Claude automatic priming verified | [codex-session-1-review.html](codex-session-1-review.html) | `ses_01a0e56c` |
| Codex re-review | Six repairs verified; two adversarial bypasses fixed in `ca5cadd`; 157 tests pass | [02-codex-rereview.md](02-codex-rereview.md) | `ses_01a0e56c` |
| 1b | Foundation repairs: all six review findings fixed in migrations `0002` to `0004` and the CLI, with regression tests; design and decision records updated | [01b-foundation-repairs.md](01b-foundation-repairs.md) | `ses_01a0e4a5`, then `ses_01a0e910` after a context compaction |

The implementation review is HTML-primary; SageOx derives its terminal-readable record.
Retrieve it with `ox plan view codex-session-1-review-95fc080`. Its findings supersede the
earlier test-only foundation verification, not the approved build plan.

Refresh and save the working session record after each commit, including while its recording
is active. The final session record can be committed at the session's end; the intermediate
SageOx evidence checkpoints must not wait for it. Verify each saved version with
`ox plan view <returned-slug>` and distinguish local ledger availability from remote sharing.

Recordings open at `https://sageox.ai/c/<session id>` for members of the SageOx team. Every
commit's `SageOx-Session:` trailer names the recording that produced it.
