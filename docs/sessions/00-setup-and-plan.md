# Session 0: setup checks, verified facts, and the approved plan

- **Date:** 2026-09-27 (PDT)
- **Outcome:** the setup is verified, the ox facts v1 relies on are re-checked against the
  installed release, DESIGN.md is written, and the build plan is approved.
- **Recording:** SageOx session `ses_01a0e4a5`, from 13:54 PDT. The session's first hour, from
  the kickoff to 13:54, was recorded under `ses_01a0e080`, which no longer appears in the
  ledger's session list (see "The recording gap" below). This record summarizes that hour
  from its verified outputs.

## What happened

1. **Environment and setup.**
   - Environment: macOS 26.6.2 on arm64, git 2.54, Python 3.14.6, gh 2.94.0 (not logged in).
   - ox: 0.18.0 (`f52d5c94`, the latest release), logged in; the repo was initialized in the
     FDE_Submission team.
   - uv was missing and was installed (0.12.19) with approval.
   - The git author was left as it is, at Dhananjay's request.
2. **Recording gate.** Recording was in progress. The CLI uploads a session when it stops, so
   the stopped daemon didn't block it.
3. **Source re-verification.** ox was cloned at `f52d5c94` and each fact the kickoff relied on
   was checked. Changes are recorded in DESIGN.md section 14. The biggest: `session.uploaded`
   never fires, bare `ox doctor` applies fixes, the daemon only pulls team context, and prime
   catalogs team docs by filename and `when:` only.
4. **Answers to the setup questions.**
   - approved: the hook-runner test, the team-doc test, and installing uv
   - dropped: the doorbell hook ([0001](../decisions/0001-pull-session-history-instead-of-a-hook.md))
   - confirmed: four fictional customers
   - raised: a proposal to use TraceRoot instead of Bivo
5. **Live tests.**
   - A standard-library hook ran through `ox hooks test` in 25 ms and revealed a zero
     timestamp. It was removed afterwards.
   - A labelled test doc was published to team context (commit `582c553`), verified on the
     remote, and removed the same way (`ad2f49c`).
6. **Recording incident, 13:54.** Re-running `ox agent prime` to check the docs listing
   started a new recording
   ([0008](../decisions/0008-no-prime-or-doctor-inside-a-working-session.md)).
7. **TraceRoot evaluated.** Bivo stays fictional and borrows TraceRoot's open-source conventions
   ([0002](../decisions/0002-keep-bivo-fictional-with-traceroot-conventions.md)).
8. **Plan.** The plan was written as an ox plan page, linted, saved to the ledger, and rendered.
   Two ChatGPT review rounds found 7 and 2 gaps; all were adopted
   ([0003](../decisions/0003-publish-with-sync-first-and-parent-checked-pushes.md),
   [0004](../decisions/0004-flag-re-reports-even-when-the-closure-precedes-the-window.md),
   [0005](../decisions/0005-privacy-gates-before-storage-model-calls-and-publishing.md),
   [0006](../decisions/0006-thin-slice-first-with-evidence-gates.md)).
   Revision 3 was approved.

## Evidence

| Claim | Where to check |
|---|---|
| ox facts and live test results | DESIGN.md section 14 |
| Upstream findings | `docs/upstream/` |
| Approved build plan | ledger plan `2026-09-27-customer-pulse-v1-build-plan` (`ox plan view` / `ox plan status`) |
| Design and brief committed | commit `d119428` |
| Team-doc publish path | team-context commits `582c553` (add) and `ad2f49c` (remove) |

## The recording gap

The first hour's transcript isn't in the ledger's session list. Its substance is preserved
here, in DESIGN.md section 14, and in `docs/upstream/`. Whether to try recovering the
transcript is Dhananjay's decision; nothing was changed in ox's recording state.

## Open items

- The recording gap above.
- Confirm the Claude model ID and parameters (session 4).
- Confirm jobs@sageox.ai joined the SageOx team; the CLI couldn't show the roster.
- `gh` isn't logged in. It's needed only for pull requests.
