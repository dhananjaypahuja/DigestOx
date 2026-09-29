# Session 3: readers and the stored-data privacy gate

- **Date:** 2026-09-28 (PDT)
- **Outcome:** Pulse imports Slack exports and GitHub issue lists into SQLite with stable
  identities, attributes each record before redacting it, and stores only redacted text. The
  privacy gate for stored data passes, and it fails when redaction is switched off.
- **Plan:** session 3 of `2026-09-27-customer-pulse-v1-build-plan`. Its gate, Dhananjay's
  review of the thin fixtures, was passed before any reader was written.
- **Recording:** Claude, SageOx session `ses_01a0eacf-d63a-7153-a868-289c4a0b84b9` (agent
  `OxDKKq`). Every commit below carries its `SageOx-Session:` trailer.
- **Context used:** the approved plan and the session 2 records, retrieved with `ox plan view`
  (`customer-pulse-v1-build-plan`, `session-2-completion-re-review`). A WIP murmur was posted
  at Dhananjay's request.

## Correction to session 2's record

Session 2's record says DigestOx `origin/main` was still at `b165529` and asks for push
approval. That was stale by the time it was saved: at this session's start, local and remote
`main` were both at `79d3a14`, as Codex's re-review noted.

## The fixture review

`fixtures/thin/` holds one fictional week, 14 to 20 September 2026, in native formats:
- two Slack exports that overlap on the 16th and 17th, one with an edited message
- two `gh issue list --json` snapshots, between which #23 closes and #24 appears
- the customer list and a manifest of planted cases

The planted privacy cases are a phone number, an email address in Slack's `mailto:` markup,
an email address and a bearer token in an issue body, a pasted API key, and a prompt-injection
line. `scripts/build_thin_fixtures.py` writes them all, and a re-run changes nothing. Every
email address and URL uses `.example` or `bivo-fictional/bivo-platform`.

The review raised three questions, and Dhananjay chose the recommended answer each time:

| Question | Decision |
|---|---|
| The plan wants attribution by email domain in session 3, but CSV import arrives in session 9 | Slack attributes by channel first, then by a customer author's email domain in channels that name no customer |
| Vendor staff replies would inflate counts, and one in `#bivo-community` would count as unattributed | Keep them for thread context, mark them `vendor`, and leave them out of every fact (migration `0006`) |
| Where the customer list lives | `pulse accounts load <file>`, not `pulse.toml` |

These are recorded in
[decision 0011](../decisions/0011-vendor-messages-are-context-and-slack-falls-back-to-email-domains.md).
`ox decision enrich --file` reports no unresolved references, and the record reconciles the
four related decisions it surfaced.

## What was built

- **Readers** (`readers/slack.py`, `readers/github.py`) only parse.
  - Slack: a ZIP, a ZIP with one top-level folder, or the unzipped folder. `ts` is parsed
    exactly, without float rounding. Slack markup is rendered, and joins, topic changes, and
    bot posts are skipped. Every message gets a thread key, so a message that gains replies
    later keeps its thread.
  - GitHub: issues, comments, state, `stateReason` (lowercased), `closedAt`, and labels. An
    inconsistent issue is refused, for example `CLOSED` without `closedAt`.
- **Attribution** (`attribution.py`) runs before redaction and returns the account, the
  author role, and how the account was found.
- **Redaction** (`redact.py`) is pattern-based. It covers emails, phone numbers with 9 to 15
  digits, and secrets, recognised by shape or by label. Each match becomes a readable marker,
  and the per-kind counts go to the import report.
- **Ingest** (`ingest.py`) handles each import in one transaction, keyed by its content hash.
  - A new record is added; an unchanged one only notes the later import. An edited one is
    revised, with its old text in `signal_revisions`.
  - A later import that would re-attribute a record keeps the first attribution and says so.
  - An import that would change fixed evidence fails as a whole with `evidence_conflict`.
- **The log** (`pulse.log`) holds content-free JSON events. It is created 0600, never followed
  through a link, and checked before an import writes anything.
- **Commands:** `pulse accounts load`, `pulse import slack`, and `pulse import github`, all
  with `--json`. An import without a `[vendor]` section warns that staff replies will count.
- **Config:** a `[vendor]` section, with Bivo's domain and workspace in the repo's
  `pulse.toml`.

## Evidence

The plan asked for four results. Each is proved by a test:

| Required | Proof |
|---|---|
| Re-importing overlapping exports never duplicates a record | Export A: 12 new. Export B: 4 new, 1 revised, 5 unchanged. Export A again: already imported. A ZIP of B: 10 unchanged. 16 Slack signals, all distinct. GitHub: 4 issues, 7 observations, 4 comments |
| Attribution by email domain works | In `#bivo-community`, Oren (`kettlewren.example`) is attributed to Kettlewren. Rowan's unknown domain stays unattributed, and Priya is vendor context |
| No raw email, phone number, or token in any SQLite text column or log | After importing every fixture from folders and ZIPs, a byte-level scan of `pulse.db` and `pulse.log` finds no planted value or identifying fragment. No text column in any table holds anything the patterns would catch |
| The injection line is stored only as evidence text | It appears only in `signals.text_redacted`, once, quoted as the customer wrote it |

**Mutation check:** with redaction patched out, four of the six privacy-gate tests fail.

**By hand:** `pulse init`, `accounts load`, both Slack exports, a repeat of export A, and both
GitHub snapshots ran on a pinned clock. They produced the counts above, a 0600 database and
log, and a log of counts only.

## Commits

| Commit | Change | Validation |
|---|---|---|
| `1fa9b9b` | test: add the thin synthetic fixtures for session 3 | Deterministic re-run; domain check; ruff clean |
| `074ba48` | feat: add the Slack and GitHub readers behind the stored-data privacy gate | 259 passed; `ruff check` and `ruff format --check` clean; `git diff --check` clean |
| `8f0610d` | docs: record session 3's readers, attribution, and vendor-message decision | documents only |

This record is committed after `8f0610d`. Its ledger copy is saved right after that commit.
None of session 3's commits has been pushed; pushing waits for Dhananjay's OK.

## Critiques and open items

| Item | Status |
|---|---|
| A log that couldn't be written was detected only after the import committed, so the user saw an error while the data was stored | Resolved before commit: the log is checked with the database before any write, and tests assert nothing is imported |
| Without `[vendor]`, staff replies would silently count as customer evidence | Resolved: the import warns |
| An older Slack export imported after a newer one revises an edited message back to its older text | Open, documented in DESIGN.md section 16. Both versions are kept |
| GitHub authors stay unattributed | Open by design (DESIGN.md section 6) until a mapping names them |
| Redaction misses secrets with no shape or label, and phone numbers under nine digits | Open, documented as a limit |
| Mapping a commit trailer to its session (Codex's session 2 re-review) | Open, scheduled for session 8 |
| Recordings: at session start, `ox session status` showed Codex's `OxyOAs` and Claude's `OxD7vu` still recording alongside this one. `ox session list` showed session 2's `Oxx108` as `local` (not uploaded) | Reported only. Recording repair is Dhananjay's |

## Next step

Session 4: the Claude module, the request gate, and stable themes.
- Confirm the model ID and parameters from the `claude-api` skill or Anthropic's docs.
- Build one typed LLM module with key handling, a request-hash cache, and replay.
- Prove with a fake model that requests and cache entries hold only redacted text, that
  evidence sits inside delimiters, that thread context stops at the cutoff, and that theme
  IDs stay stable.
- The one live run on the thin fixtures spends API credit, so it waits for Dhananjay's OK.
- Thread context reads `signals` directly, including vendor replies.

Retrieve this record with `ox plan view <slug>`; the slug is given in the session summary.
