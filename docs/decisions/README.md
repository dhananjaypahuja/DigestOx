# Decision records

Each significant decision in Customer Pulse gets a numbered record here. SageOx discovers
this directory (`ox decision enrich`), and `ox code search` indexes it, so the same context is
available on GitHub and through SageOx. Records are drafted by the AI coworker in recorded
sessions and decided by Dhananjay Pahuja. When the first records were drafted (2026-09-27),
`ox decision enrich` found no earlier team decisions on these topics.

| # | Decision | Status |
|---|---|---|
| [0001](0001-pull-session-history-instead-of-a-hook.md) | Pull ox session history instead of relying on the `session.uploaded` hook | Accepted |
| [0002](0002-keep-bivo-fictional-with-traceroot-conventions.md) | Keep Bivo fictional and borrow TraceRoot's open-source conventions | Accepted |
| [0003](0003-publish-with-sync-first-and-parent-checked-pushes.md) | Publish the team doc with sync first and ownership checked before every push | Accepted; amended 2026-09-28 |
| [0004](0004-flag-re-reports-even-when-the-closure-precedes-the-window.md) | Flag re-reports even when the issue closed before the digest window | Accepted; amended 2026-09-28 |
| [0005](0005-privacy-gates-before-storage-model-calls-and-publishing.md) | Privacy gates before storage, before model calls, and before publishing | Accepted; amended 2026-09-28 |
| [0006](0006-thin-slice-first-with-evidence-gates.md) | Build a thin slice first, with evidence and gates in every session | Accepted |
| [0007](0007-enforce-invariants-in-the-schema.md) | Enforce the data invariants in the SQLite schema itself | Accepted; amended 2026-09-28 |
| [0008](0008-no-prime-or-doctor-inside-a-working-session.md) | Never run `ox agent prime` or `ox doctor` inside a working session | Accepted |
| [0009](0009-keep-review-context-in-sageox.md) | Keep every session's decisions and evidence available through SageOx | Accepted; amended 2026-09-27 |
| [0010](0010-bind-every-run-to-an-evidence-snapshot.md) | Bind every run to an evidence snapshot, so later imports can't change its facts | Accepted |
