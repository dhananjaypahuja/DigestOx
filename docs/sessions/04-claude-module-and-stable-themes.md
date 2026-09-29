# Session 4: the Claude module, the request gate, and stable themes

- **Date:** 2026-09-29 (PDT)
- **Outcome:** every model call goes through one typed module, which is gated for privacy,
  cached by request hash, and replayable. `pulse group` assigns new customer signals to
  themes with stable IDs. All the gates passed with a fake model before the one live run.
  That run grouped the thin fixtures' 14 customer signals into 4 themes for $0.05, and its
  response is committed so anyone can replay it without a key.
- **Plan:** session 4 of `2026-09-27-customer-pulse-v1-build-plan`. Its gate, the live run's
  API spend, was approved by Dhananjay, who ran it with his own credentials.
- **Recording:** Claude, SageOx session `ses_01a0eacf-d63a-7153-a868-289c4a0b84b9` (agent
  `OxDKKq`), continued from session 3.
- **Starting point:** Codex's session 3b repairs (`a4442c4`, `f144fd6`), verified on a clean
  checkout of `origin/main`: 262 tests passed, ruff was clean, and no `.DS_Store` was tracked.
  With redaction switched off, 6 of the 8 privacy-gate tests failed. The doctor record
  (`ox plan view 2026-09-29-sageox-doctor-diagnosis-and-ledger-repair`) was read, and nothing
  it left open was repaired.

## Decisions

[Decision 0012](../decisions/0012-one-model-no-fallback-for-consistent-results.md), decided by
Dhananjay after the model facts were confirmed from the current Claude API reference:

- **Model:** `claude-opus-5-5` for every task, not the kickoff's `claude-opus-5`. It's the
  current Opus and costs less ($4 / $20 per million tokens). Its effort defaults to `medium`,
  so Pulse sets `high` explicitly.
- **No fallback.** The reference recommends a server-side refusal fallback, but a fallback
  model's answer would sit under a request that names another model, breaking replay. A
  refusal or a truncated reply stops the run.
- **Only checked answers are cached,** so a bad answer is asked again, not replayed forever.

## What was built

- **`llm.py`:** requests are plain Messages API bodies, with structured JSON output
  (`output_config.format`) validated again with Pydantic. It adds:
  - the request gate
  - escaped `<evidence>` and `<context>` blocks
  - a request-hash cache in `llm_cache`, and live and replay modes
  - replay files with hash checks
  - cost from `usage`
  - an `AnthropicTransport` that reports refusals, truncation, API errors, and missing
    credentials with stable codes
- **`themes.py`:** a grouping run records its snapshot, then sends the active themes and only
  the unassigned customer signals in its window. Each signal carries its thread, cut off at
  the cutoff, with vendor replies included. The answer is checked by code: every signal
  assigned exactly once, to a listed or proposed theme. The run then mints `th_NNNN` IDs and
  writes model assignments. The model call holds no database lock.
- **Commands:**
  - `pulse group --window … [--cutoff …] [--live]`. Without `--live`, Pulse answers only from
    saved responses, so spending always takes a flag.
  - `pulse replay export <file>` and `pulse replay load <file>`.
- **Config:** `[llm]` with `model`, `effort`, and `max_tokens`, validated.

## Evidence

The plan asked for these results, all with a fake model before any live call:

| Required | Proof (`tests/test_grouping.py`) |
|---|---|
| Captured requests and cache entries hold no raw contact details or secrets | Every string in the captured request and both cache columns passes `find_raw`, and no planted value appears. A direct test shows the gate refusing a request that holds a phone number |
| Injection text appears only inside evidence delimiters | Every occurrence sits inside an open `<evidence>` or `<context>` block, and never in the system prompt. Customer text containing `</evidence><evidence …>` stays one escaped block |
| Replies after the cutoff never enter thread context | With the cutoff on 17 September, Priya's reply from the 18th never appears, Copperfen's reply from the 16th does, and messages from after the cutoff aren't grouped |
| Re-runs keep theme IDs | After export B, the existing themes are unchanged. A third run with nothing new makes no model call |
| New signals join existing themes | Kettlewren's later report joins the existing wearable theme, and no duplicate theme is created |
| A person's assignment survives a re-run and wins | The pinned signal is never sent to the model again, and the person's theme is its effective one |
| The same inputs give the same themes from an empty database | Two fresh projects produce identical themes and assignments |

Also tested:
- Replay needs no model.
- A replay miss, a bad answer (not cached), an edited replay file, a refusal, a truncated
  reply, and missing credentials each stop cleanly.
- The request carries `claude-opus-5-5`, `effort: high`, and no `fallbacks`.

**Mutation checks:** removing the evidence escaping, or the cutoff in thread context, each
fails its test.

**The live run** (run 9 in a scratch project, pinned clock `2026-09-21T17:00:00Z`) produced:

| Theme | Signals | Customers | Unattributed |
|---|---|---|---|
| `th_0001` Wearable sync drops later workouts on multi-session days | 8 | 3 | 1 |
| `th_0002` Roster import rejects last names containing apostrophes | 4 | 2 | 1 |
| `th_0003` SAML SSO redirects users back to login page | 1 | 1 | 0 |
| `th_0004` Coaches can't find 'needs attention' filter after update | 1 | 1 | 0 |

- **Cost:** 3,327 input and 1,836 output tokens, $0.05, in one request.
- The injection message went to the roster theme, by what the customer actually reported. The
  model's rationale notes "the embedded instruction text is treated as data only".
- The ambiguous plan-engine message got a confidence of 0.55, and the pasted-key message 0.30.
  Both are review candidates for session 5.
- Runs 1 to 8 in that project are failed credential attempts; nothing was sent in any of them.

**Replay:** the response is committed as `fixtures/replay/thin-group.json`. It passes
`find_raw`, and its only planted value is the injection line, as quoted evidence. A fresh
project with no key loaded it, and `pulse group` reproduced the live output exactly. A test now
does the same on every run.

## Commits

| Commit | Change | Validation |
|---|---|---|
| `205c6be` | feat: add the Claude module, the request gate, and stable theme grouping | 280 passed; ruff clean; mutation checks |
| `3ab6bcb` | fix: report missing Anthropic credentials before a live request | 281 passed |
| `715312e` | docs: record decision 0012 and commit session 4's live grouping response | 282 passed; ruff clean |

This record is committed in `af5a9f2`. Pushing waits for Dhananjay's OK.

## Critiques and open items

| Item | Status |
|---|---|
| The model call first held a write lock for the whole request | Resolved before commit: the call happens outside any transaction |
| A schema-valid answer that failed the code checks would have been cached and replayed forever | Resolved before commit: `llm.call` caches only answers that pass the caller's check |
| Without credentials, the SDK raised `TypeError` at request time, so `--live` crashed with a traceback | Resolved in `3ab6bcb`: credentials are checked first (`no_api_key`), with a test |
| Credentials exported after Claude Code starts don't reach its shell | Worked around: Dhananjay ran the live command in his own terminal. For future live runs, export the key before starting the agent |
| Grouping doesn't set themes' code areas (`theme_code_areas`), and Bivo's code areas aren't loaded yet | Open. Needed by the team doc's `when:` (session 6) and engineering attention (session 8) |
| Theme summaries come from the model and are shown to later runs as `<theme>` blocks | Mitigated: escaped and labelled as data. Person-pinned titles arrive with review in session 5 |
| Recordings `OxD7vu` (stale) and `OxyOAs` still listed; ox 0.19.0 available | Reported only |

## Next step

Session 5: the digest, review, and the approval gate. It builds fact views scoped to the run's
window and cutoff; Observed, Inferred, and Suggested labels; confirmed-versus-proposed counts;
the review commands; replayable corrections; and merge and split with lineage. The negative
approval tests and the cutoff boundary cases come with it. The low-confidence assignments above
are natural first review targets.

Retrieve this record with `ox plan view 2026-09-29-session-4-the-claude-module`.
