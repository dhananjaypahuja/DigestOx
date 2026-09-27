# Session records

One record per working session: its outcome, the evidence for it, the commits it produced,
the decisions it made, and what it left open. Each record is committed here and also saved to
the SageOx ledger with `ox plan save --kind evidence`, so reviewers find the same context on
GitHub and in SageOx ([decision 0009](../decisions/0009-keep-review-context-in-sageox.md)).

| Session | Outcome | Record | SageOx recording |
|---|---|---|---|
| 0 | Setup verified, ox facts re-checked, design written, build plan approved | [00-setup-and-plan.md](00-setup-and-plan.md) | `ses_01a0e4a5` (the first hour is missing; see the record) |
| 1 | Foundation: package, time model, schema, `pulse init` and `pulse status` | [01-foundation.md](01-foundation.md) | `ses_01a0e4a5` |

Recordings open at `https://sageox.ai/c/<session id>` for members of the SageOx team. Every
commit's `SageOx-Session:` trailer names the recording that produced it.
