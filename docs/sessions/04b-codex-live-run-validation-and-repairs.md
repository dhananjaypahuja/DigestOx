# Session 4b: Codex validation and response/replay repairs

- **Date:** 2026-09-29 (PDT)
- **Scope:** validate Claude's session 4 live-run handoff (`205c6be..af5a9f2`), repair quick findings, and clear the code gate for session 5.
- **Plan:** `ox plan view 2026-09-27-customer-pulse-v1-build-plan`
- **Session 4 evidence:** `ox plan view 2026-09-29-session-4-the-claude-module`
- **Recording:** Codex `https://sageox.ai/c/ses_01a0ed42-6d1a-7242-9a62-7e88175eb1fe`.

## Validation of the live run

Claude's record reports one paid request in scratch run 9: 3,327 input and 1,836 output tokens, approximately $0.05, grouping 14 synthetic signals into four themes. This review did **not** make another API request or independently observe the provider transaction. It verified the committed response in `fixtures/replay/thin-group.json`: its response digest matches, it contains four new themes and 14 assignments, and the response privacy scan finds no recognizable raw contact data or secrets. The no-key committed-replay test loads it and reproduces the expected theme counts and injection assignment. The run is adequate evidence for the session 4 implementation gate; model quality remains subject to human review in session 5.

## Findings and repairs

| Finding | Reproduction and repair | Status |
|---|---|---|
| A schema-valid model reply could put an email or other recognizable raw detail in `llm_cache` and theme text | Regression test failed before repair. `llm.call` now privacy-checks response keys and values, including data outside Pydantic's retained fields, before caching; cache hits are checked too. | Resolved for new calls and cache reads; pattern redaction's known blind spots remain. |
| A replay file could have its response edited without changing the request hash, then load the altered response | Regression test failed before repair. Export now includes a canonical response SHA-256, import checks it and rejects missing/mismatched digests before caching. The committed live replay was updated with its digest, without changing the response or making a live call. | Resolved for accidental edits. Hashes are not signatures; a deliberate editor can recompute one. |
| Replay import could store raw contact details even with a matching response digest | Regression test failed before repair. Import now runs the response privacy gate before insertion; the CLI's transaction leaves no entry on rejection. | Resolved for recognizable patterns. |
| A transport could return a different model while its response was cached under the requested model | Regression test failed before repair. Live calls now compare returned and requested model IDs and refuse a mismatch, enforcing decision 0012's no-fallback rule. Replay import also checks model and effort metadata against the hashed request. | Resolved. |

These are implementations of existing privacy decision 0005 and model decision 0012, not new design decisions. `DESIGN.md` and the replay-load help text now describe the checks. Claude's prior two-line edit to its session 4 record (commit SHA and retrieval command) is carried forward unchanged in this repair commit.

## Checks

- Four new focused tests failed before implementation. A fifth checks contact data in response object keys.
- `.venv/bin/pytest -q`: **287 passed**, including no-key replay of the committed live response.
- `.venv/bin/ruff check .`: clean; `.venv/bin/ruff format --check .`: 80 files formatted; `git diff --check`: clean.
- No paid model call, push, recording repair, or team-context write was made.

## Boundary and next step

Replay hashes detect edits but do not authenticate a file. `pulse replay load` privacy-checks and hashes entries before storage; task-specific schema and assignment checks still run when the cached answer is used, not at load time. No existing local databases were scanned or rewritten. These limits do not block session 5's digest, review, and approval-gate work; that stage should continue to treat model labels, summaries, and low-confidence assignments as proposals, not approved facts.

The code and record are a local commit only. Pushing requires Dhananjay's approval. Retrieve this checkpoint with `ox plan view 2026-09-29-session-4b-codex-validation-and-response`; remote sharing/search indexing must be reported separately from local retrieval.
