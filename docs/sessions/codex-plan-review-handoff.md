# Codex plan review handoff 9b511ef

Checkpoint: 2026-09-27, reviewed repository HEAD
`7d919023e978b206077b7c1b4cc37d6eef29a4c9`.
Follow-up: Claude subsequently committed `9b511ef` with nine decision records, session
records for setup and foundation, and the shared agent workflow. This handoff incorporates
that update; the code/test snapshot below is still the foundation at `7d91902`.

This is engineering context for Claude's next review and implementation session. It is not
customer evidence and must not be counted by Customer Pulse as an input signal.

## Sources and scope

- Current design: `DESIGN.md`; original brief: `docs/kickoff.md`. The kickoff contains
  superseded assumptions; the current design records the corrections.
- Saved plan: `2026-09-27-customer-pulse-v1-build-plan`, retrievable with
  `ox plan view 2026-09-27-customer-pulse-v1-build-plan` or
  `ox plan review 2026-09-27-customer-pulse-v1-build-plan`.
- Codex review recording:
  <https://sageox.ai/c/ses_01a0e4f5-4293-721e-aaf8-78378a409dd4>;
  local session name `2026-09-27T22-21-pahuja-dhananjay-OxyOAs`.
- Claude planning/build recording, linked by the foundation commits:
  <https://sageox.ai/c/ses_01a0e4a5-f771-7412-988b-2a4739c9aad0>.
- The user requested the original plan review, a second review through `ox plan review`,
  and now durable SageOx context after every session and commit so Claude can review and
  implement. `AGENTS.md` records that ongoing DigestOx handoff requirement.
- Claude's decision `docs/decisions/0009-keep-review-context-in-sageox.md` and records
  `docs/sessions/00-setup-and-plan.md` and `docs/sessions/01-foundation.md` are the existing
  handoff workflow. This review record uses the same `ox plan save --kind evidence` path.

## Design direction and rationale

Build the thin end-to-end loop first: ingest synthetic Slack/GitHub evidence, propose
stable themes, review a digest, publish a team doc, observe a fresh Bivo agent using it,
and reconcile its committed work into the next digest. CSV mapping, broader comparisons,
archiving, the full dataset, and held-out evaluation follow. Revision 2 split publication,
fresh-agent work, and reconciliation into separate stages, producing a thirteen-session
plan. The current README identifies foundation/session 1 as complete.

Important boundaries to preserve:

- Bivo and its customer data are fictional. Bivo is a separate local-only repository;
  engineering evidence must come from that repository's sessions and commits.
- Code computes factual counts, dates, and links; the model proposes groupings and prose.
  A mention of an issue is not a confirmed report of the same problem.
- Attribute before redacting. Contact details and secrets must not reach stored evidence,
  logs, model requests, or published text. Prompt-injection text may remain as explicitly
  delimited evidence. My first review overstated this by implying it must be removed;
  the second review explicitly accepted the corrected interpretation.
- Time windows are half-open, with UTC storage and an explicit cutoff. No later reply or
  engineering session may influence a digest before its cutoff.
- Human corrections persist; theme IDs and merge/split lineage are stable; approval binds
  to exact content, and changed or unapproved content cannot publish.
- A read trace alone does not prove the loop. Require a relevant session-linked commit,
  upload, reconciliation, and a subsequent digest showing verified, possibly related
  activity. That activity never establishes that the customer problem is resolved.
- Use pull-based session reconciliation. The prior source investigation found the
  `session.uploaded` hook unusable in ox 0.18.0, so the doorbell was dropped.
- Publish customer findings as a team doc, not a behavioral rule. Ownership checks and
  approvals must protect other contributors' edits.

## Review findings and their status

The first review raised seven findings. Revision 2 addressed them in the plan:

1. The loop could pass after merely reading the doc: split into publish, fresh-agent fix,
   and reconciliation stages, each with evidence.
2. Cutoffs arrived after first publication: moved time and thread boundaries into the
   thin slice, with boundary tests.
3. No privacy gate preceded live calls: added storage, request/cache, and output gates.
4. Engineering preflight inspected DigestOx instead of Bivo: changed to a real recorded
   Bivo session, with commit linkage and repository-isolation checks.
5. Approval tests covered only happy paths: added unapproved/mutated-content rejection
   and resumed-publish hash checks.
6. Stable themes were checked too late: added repeat-run and person-over-model tests
   before first publication.
7. Session cards disappeared from the saved markdown and branding lint failed: changed
   them to semantic list content with separate controls and repaired attribution.

The second review identified two further corrections. They are now present in the current
`DESIGN.md`; do not re-open them as missing design decisions:

- Sync must precede ownership verification. Repeat ownership verification before each push,
  including after retry sync. The design now checks the doc in the parent of Pulse's
  commit to protect a foreign edit introduced by a rebase. The publishing implementation
  is still future work, so this is a corrected design, not verified publish behavior.
- A report this week can flag an issue closed before this week. Require the report inside
  the window and before its cutoff, a confirmed reports link, and closure before the
  report. Do not require the closure itself inside the current window. This rule is now
  documented and implemented in the foundation's SQL view.

Additional implementation questions from the independent review were not final approval
blockers: define committed engineering-evidence inputs for reproducible replay; validate
CSV preview/reuse against invalid same-header rows; and check evaluation metrics against
small hand-calculated examples. Reassess these when their implementation sessions arrive,
without treating them as new user requirements or evidence of existing failures.

## Current implementation and verification

The following commits already exist and link to Claude's planning/build session:

- `d119428`: current design and kickoff.
- `5e2c8f6`: package scaffold.
- `d55c575`: time model and injectable clock.
- `db6d1f0`: SQLite schema and migration runner, including prior-period issue closure.
- `0bd42c7`: `pulse init` and `pulse status`.
- `7d91902`: upstream issue drafts; these are not filed upstream.
- `9b511ef`: decision records 0001–0009, setup/foundation session records, and the repository
  workflow. This later documentation commit also links to Claude's recording.

During this handoff, Codex ran `uv run --offline --no-sync pytest -q` at the HEAD above:
**81 passed in 0.23 seconds**. This was the existing foundation suite, not a new audit of
future ingestion, LLM, publishing, or reconciliation code.

During the second review, `ox plan lint 2026-09-27-customer-pulse-v1-build-plan --strict`
passed, `ox plan view` retained all thirteen sessions, and the live served page was checked
in Chrome in both themes, including diagram highlighting. The first attempt to inspect a
`file://` page was blocked by the browser connector; the requested `ox plan review` server
enabled the later visual check. No plan content or approval was changed by Codex's reviews.

## Next handoff to Claude

Read the latest saved plan and current design before continuing. The README places the
next work at session 2: Bivo setup and a real session/commit preflight, with the existing
user gates. Foundation code is present; do not repeat scaffolding. Before implementing
publication, preserve the corrected sync/ownership sequence and its negative tests.

After each new commit, refresh the session evidence record with its actual SHA, rationale,
review status, validation, and next step. Save it immediately with
`ox plan save --file <record> --kind evidence`, then verify with `ox plan view <returned-slug>`.
Do this during a session as well as at its end; the recording can upload on the established
session-end lifecycle. Active-session logs and expiring murmurs alone are not durable shared
handoffs. Leave recording repair to Dhananjay, and preserve the existing ask-first list.

At the start of this handoff, SageOx listed three recordings as orphaned/unfinished,
including the Codex review recording. That diagnostic does not establish loss of content:
the Codex entry count was still increasing. No recording was stopped or repaired by this
task. Direct local ledger retrieval must not be presented as proof of remote upload.

A preliminary version of this handoff was also imported into team context, before Claude's
`9b511ef` update was received. The import returned status `imported` and path
`data/docs/2026/09/27/digestox-engineering-handoff-7d91902-codex-plan-review-2026-09-27`.
An immediate `ox query` returned no results, so that import's search availability was not
verified. This current ledger evidence record supersedes that earlier checkpoint; retrieve
it directly with `ox plan view` using the slug returned when saved.
