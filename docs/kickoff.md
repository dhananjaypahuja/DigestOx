# Customer Pulse: kickoff

I'm Dhananjay Pahuja. I'm applying for the Forward Deployed Engineer role at SageOx, and this repository is my application project. You're pairing with me to build it. Read this whole prompt before doing anything. It records the decisions I've made, the facts already verified, and the decisions still open.

## How to work with me

- **When to ask me.** Almost every decision is settled below. Ask me only about scope changes, spending, anything outward-facing, and consequential choices this prompt doesn't cover, with 2 to 4 concrete options and your recommendation. Batch questions into one round instead of stopping repeatedly. Code-level choices inside the agreed design are yours; mention the notable ones.
- **Verify before relying.** The ox facts below were checked against the ox source on 2026-09-27: release 0.18.0 (commit f52d5c94), then rechecked on main (commit c7a76ab). ox ships often, so re-check the facts v1 depends on against the version installed here before building on them (first session, step 4), and tell me what changed.
- **This work is recorded and reviewed.** ox records these sessions, and SageOx will watch them. They care how I think and build more than polish. Explain your reasoning as you go, work in small steps, and give each session one clear outcome. Commit with conventional-commit messages (`feat:`, `fix:`, `docs:`, `test:`), as ox itself does. When you change course, say why.
- **Ask before anything outward-facing, every time:** pushing, GitHub issues or PRs, `ox import`, writing to team context, murmurs, invites, and publishing skills. Local commits are fine. ox's own session recording and sync are expected and don't need asking.
- **Secrets stay out of your hands.** Never ask me for an API key, type one, print environment variables, or read `.env` or credential files. ox records what you see. It redacts known secret formats, but we don't rely on that. I set keys in my own shell.
- **Synthetic data only.** Every demo record is synthetic and labelled as such. No real customer data, ever.

## Background

**SageOx** builds shared memory and coordination for teams of people and AI coding agents. Their open-source CLI, `ox` (https://github.com/sageox/ox, written in Go), records coding-agent sessions into a shared team history, gives agents team context when a session starts, and supports hooks, murmurs, team docs, and imports.

**The role.** SageOx's first Forward Deployed Engineer works at the customer boundary: embedded in customers' shared Slack channels (under about 30 teams today), triaging issues, shipping fixes and small features end to end, and turning recurring questions into docs. The job description names a daily and weekly customer digest for the whole team as a first-class deliverable: issues, trends, feature friction, use-case patterns, and customers' own words.

**The ask.** SageOx's email offered a "build something new" route: set the project up with `ox init` and add jobs@sageox.ai to my SageOx team. In their words: "We care about how you think and build, not polish." They also asked for my GitHub username.

**Already done on this machine.** ox is installed at the latest release and logged in; I ran `ox init` in this repo; and I sent the SageOx team invitation to jobs@sageox.ai. Confirm each of these in the first session without changing anything.

## The project: Customer Pulse

Customer Pulse turns a software vendor's scattered customer feedback into an evidence-backed friction digest. A person reviews the draft, and the reviewed findings are published into SageOx so coding agents know what customers are struggling with before they touch the code.

**Audience:** one software vendor's FDE or engineering team, tracking how several customers experience its product. It is not a tool for an enterprise studying its own internal workflows.

**Each finding answers:** what the customer was trying to do; where the workflow broke; which customers are affected, based on identifiable evidence; what is already tracked or being worked on; what changed since the previous digest; and what would help next.

```
 Slack export ─┐  fixed-format readers (no AI needed)
 GitHub issues ┤
 messy CSV ────┘  AI mapping workbench: suggest · explain · preview
       │
       ▼
   Signals ─► redact ─► themes ◄──── engineering attention
                        (stable IDs,   read from ox session history;
                         evidence)     session.uploaded hook = doorbell
                          │
                          ▼
                    draft digest ─► human review ─► publish
                                    (corrections    ├─► team doc ─► listed at every session start; read when relevant
                                     persist)       └─► ox import ─► dated archive
```

| Source | What it contributes | What not to assume |
|---|---|---|
| Shared Slack channels (export ZIP; one channel per customer) | What customers try to do, where they get stuck, workarounds, urgency | That many messages means many affected customers |
| GitHub issues and comments (JSON, such as `gh issue list --json` output) | Tracked problems, reproduction details, status, close dates | That a closed issue means the customer's problem is solved |
| A messy support-ticket CSV, through the mapping workbench | More customer evidence, and a bounded example of messy input | That an arbitrary file reveals workflow problems without context |
| ox sessions in the vendor's repo | Possibly related engineering activity: which code areas a session changed, verified through its commits | That a session means a fix shipped, worked, or addressed the customer's problem |

**The mapping workbench** handles files whose shape isn't known in advance. It suggests column-to-field mappings with a confidence and a reason; explains validation failures in plain language, grouped by cause rather than one line per row; previews the corrected output before writing anything; and saves the approved mapping so a later export with the same columns can reuse it without the LLM, after every row is validated again. Slack and GitHub have known formats, so they get fixed readers with no LLM involved.

## Design principles (agreed)

1. **Themes keep stable IDs.** "What changed since the last digest" depends on it. Match new signals to existing themes before creating new ones, and pin human corrections so they survive re-runs. This is the core technical problem.
2. **Code computes facts; the LLM doesn't.** Code produces counts, affected customers, dates, links, trends, and a "reported after issue closure" flag: a customer report dated after a specific issue closed, where a confirmed `reports` relationship (not just a mention) ties the report to that issue. Show the issue's `stateReason` (completed or not planned) beside the flag. Never call it a regression; that would need evidence about releases or earlier working behavior. Affected customers come from explicit mappings: Slack messages by channel; CSV tickets by an account column or the requester's email domain, matched against `accounts`; GitHub authors stay unattributed unless a mapping names them. Attribute before redacting, since attribution can use email domains. Evidence that can't be attributed is counted as unattributed, never guessed. The LLM only proposes groupings, titles, summaries, and next steps. Each statement in the digest is labelled Observed, Inferred, or Suggested based on where its data came from, not on the model's wording. A count computed by code can still rest on model-proposed groupings, so show how many of the underlying assignments a person confirmed and how many the model proposed.
3. **A mention isn't a report.** A message containing an issue URL or `#142` proves only that it mentions the issue; "this looks unrelated to #142" mentions it too. Code records mentions as `references`. Whether a message reports the same problem as an issue is a separate `reports` relationship: the model may propose it, with a confidence, and it counts only after review.
4. **Customer text is untrusted twice:** going into the LLM, and going into agents' context. Redact contact details and secrets before any LLM call and before publishing. Keep quotes inside clearly marked evidence blocks. Publish as a team doc, never as a team rule, because ox treats rules as instructions to agents.
5. **Pulse never cites itself.** Everything Pulse publishes is tagged as Pulse output and excluded from evidence. A session that only read the digest isn't engineering attention; only sessions that changed files in a theme's code area count (see "Engineering attention" below).
6. **Engineering attention never marks a theme resolved.** At most it shows possibly related engineering activity.
7. **A person reviews before anything is published,** and their corrections persist.
8. **Prove the loop rather than claim it.** Being listed at `ox agent prime` isn't proof: `when:` is only a hint in a catalog, and the agent decides whether to read the doc. Show that a fresh agent actually read and used the published findings, using `ox session view --context` or whatever the installed version offers.
9. **No information from the future.** Every digest has an explicit window and cutoff in a configured timezone, stored in UTC. Nothing after the cutoff can influence it: not messages, not later replies in a thread (a thread's context stops at the cutoff too), not issue state changes, not engineering sessions. Issue state at the cutoff comes from `createdAt` and `closedAt`; anything the data can't show, such as reopen history or past labels, is marked unknown.

## Settled decisions

- **Language and tooling:** Python, managed with uv (project metadata, lockfile, `uv run`). Check `uv --version` first; if uv isn't installed, ask me before installing it.
- **LLM provider:** Claude only, through Anthropic's official Python SDK.
  - Pulse reads `ANTHROPIC_API_KEY` from the environment. If it isn't set, an interactive terminal gets a hidden prompt that keeps the key in memory for that run only (never written to disk, never logged, never echoed), plus instructions for setting the environment variable. A non-interactive run exits with a clear message saying what to set.
  - **Model:** `claude-opus-5` at `effort: high`, for every LLM task: grouping, digest writing, mapping suggestions, and validation explanations. This is the work people will trust and act on, so quality comes before cost. Keep the model ID and effort in config. Confirm the ID and parameters with the `claude-api` skill, and show me the real cost after the first full run.
  - **Replay mode:** yes. Saved responses let anyone run the demo on the committed demo inputs without a key, and the output is clearly labelled as replay. Key each saved response by a hash of the complete API request: model, effort, prompt and schema version, and the full rendered input, including the current themes and any approved mapping. Changing any of those needs a key. Replay proves reproducibility, not model quality (see Evaluation).
  - Only redacted text is sent (see Redaction). LLM calls go through one small module that returns validated, typed results. Tests use a fake and never touch the network.
  - Before writing the Claude code, load the `claude-api` skill if it's available and follow it; otherwise follow Anthropic's official Python SDK documentation. Don't write API calls from memory.
- **Interface:** the CLI is Pulse's only interface. No REST API and no web server. Every command supports `--json`, as ox's commands do, so an agent can drive Pulse too.
- **Storage:** SQLite through Python's built-in `sqlite3`, in one local file that stays out of git. Use plain SQL with numbered migration files, so a later move to PostgreSQL stays cheap; name that as the growth path in DESIGN.md (several FDEs writing at once, a hosted service, or live Slack ingestion), not something to build now. Use views for the facts code computes (counts, affected customers, trends).
  - Draft tables, for you to refine in DESIGN.md and review with me: `accounts` (customer, Slack channel, email domains); `imports` (each import batch: file, type, content hash, and when); `signals` (one row per Slack message, issue comment, or ticket, keyed by its source identity: account or none, author name, time, redacted text, URL, thread, and a flag marking Pulse's own output); `issues` (GitHub issues, with state observations kept as history rather than overwritten); `themes` (stable IDs such as `th_0007`, title, code areas, first and last seen); `assignments` (signal to theme, set by the model or a person, confidence, run; a person's assignment wins); `links` (signal to issue: a `references` mention found by code, or a `reports` relationship with the model's confidence and who confirmed it); `corrections` (append-only log of review commands and their arguments); `sessions` (ox session name, repo, commits, changed files); `runs` and `digests` (time window, model, prompt version, cost; draft, reviewed, published); `mappings` (CSV header fingerprint to approved mapping); and `llm_cache` (prompt hash to response, for replay mode).
  - The hook queue stays a plain append-only file, not the database, because of the 500ms limit.
  - SQLite is the single source of truth, including the theme registry and the corrections log. No other file owns that state. The one committed derivative is the replay file: export the demo's saved LLM responses to it, so replay mode works on a fresh clone.
  - Determinism test: the fixtures, the replay file, and a scripted list of review corrections, run against an empty database with a fixed clock and a stable ordering, must produce an identical digest every time. Compare the digest's content, not run IDs, execution timestamps, or live session state.
- **Record identity:** every source record has a stable identity: a Slack message by channel and `ts`; a GitHub issue by its number and a comment by its ID; a CSV ticket by the ticket-ID column when the mapping finds one, otherwise by a hash of the normalized row (say in DESIGN.md that rows without an ID can't be matched across edited exports). Re-importing overlapping exports updates existing records and never duplicates messages, comments, tickets, or customer counts. Store changes to existing records deliberately; issue state changes are kept as history. A file's content hash identifies an import batch, not the evidence inside it.
- **Names:** the CLI command is `pulse`; the package is `customer-pulse`, imported as `customer_pulse`; the CLI framework is Typer; the license is MIT, as ox uses.
- **Redaction:** keep people's names (in the synthetic data, their invented names), so readers know who reported or decided what. Before any LLM call and before publishing, redact email addresses, phone numbers, and secrets or tokens, using patterns. No LLM does the redacting. If a real customer's data agreement ever forbids sending names to an LLM, stable aliases are the fallback; note that in DESIGN.md, don't build it.
- **Review step:** CLI commands, such as `pulse review`, `pulse theme move|merge|split`, `pulse link confirm`, and `pulse publish`. Every correction is a logged command that can be replayed.
- **The vendor: Bivo, a fictional company.** The name is borrowed from a project of mine at bivo.ai, but nothing about that project applies here: don't look it up, copy from it, or describe it. For this demo, Bivo is a B2B platform that gym chains and coaching studios use to give their members AI-generated training and nutrition plans. Its customers talk to Bivo in shared Slack channels, one channel per customer. Shape anything else about the company in whatever way best serves the demo.
  - **Customers:** 3 or 4 invented gym chains and coaching studios. Propose names, check they don't belong to real businesses, and confirm them with me.
  - **Label it fictional:** the customers, their feedback, the issues, the tickets, and the codebase are all invented. Say so in the README, in DESIGN.md, and in the fixtures README and manifest, not inside the data files (see Fixture formats).
  - **No real addresses:** use `.example` domains (for example `bivo.example`) for every email address and web URL in the synthetic data, so nothing points at a real site. The one exception is the fixture GitHub issue URLs described under the vendor repo.
- **Demo:** a tiny made-up Bivo codebase in Python, set up with ox, with one small module per code area: member roster import, wearable sync, the plan engine, coach tools, and SSO. The demo's engineering attention then comes from real ox sessions firing the real `session.uploaded` hook. Tests use fixtures.
- **The vendor repo** is local only: no GitHub remote, never pushed. Set it up with `ox init` in my current SageOx team, the same team as this repo; `ox init` is offline-safe for repos without a remote (source: `cmd/ox/init.go`). Its git commits stay on this machine, but ox still syncs its session recordings to the SageOx team; that's what lets SageOx see the demo's engineering sessions. Confirm that they sync like this repo's. Propose where it lives on disk and confirm with me. Because it has no GitHub repo, its issues exist only as fixture JSON in `gh` output format, and their URLs won't resolve; propose an owner/repo name for those URLs that doesn't exist on GitHub, and confirm it with me.
- **Publishing:** two tiers, both only after review.
  1. A doc in the team context's `docs/` directory holding current friction, overwritten on each publish, with `when:` triggers naming the affected code areas. Keep it short, roughly 1,000 to 2,000 tokens: the top themes only, with a pointer to the dated archive for the rest, because an agent reads the whole file when its task matches.
  2. An `ox import` of each dated digest, as the archive. `ox import` can't be undone from the CLI, so import only real reviewed digests during the demo, with my OK each time, never during development or tests.
  - Planned order for the team doc, which stays a hypothesis until first-session step 5 proves it: run `ox sync`; write the file; commit and push from inside the team-context checkout; if the push is rejected, pull with rebase and retry once; never force-push; then confirm the doc is listed in `ox agent prime` output, and fail loudly if it isn't.
  - Track each publishing step per digest version (doc written, pushed, listed in `ox agent prime`, archived with `ox import`), so a retry resumes where it stopped and a partial success is visible.
  - Pulse owns the team doc. Before overwriting it, compare it with what Pulse last published; if someone else changed it, stop and ask instead of overwriting.
  - The doc states "current as of <date>, digest <id>". Archive entries carry their date and digest ID in the title, so readers can tell current findings from superseded ones.
  - Regenerating a draft never loses review work: stored corrections are re-applied to the new draft.
  - Approval belongs to one content version. `pulse review` records the approved digest's content hash; any change makes a new draft that needs review; `pulse publish` refuses anything that isn't approved.
- **Hook:** `session.uploaded` is a doorbell. The hook script uses only the standard library, appends the event (including `project_root` and `repo_id`) to a local queue, logs to a file, and exits well within 500ms. Hooks are user-level, so Pulse ignores events from any repo other than the vendor repo. The script must accept both the real payload and the synthetic one `ox hooks test` sends. Register it once, since `ox hooks add` doesn't check for duplicates. A repo's daemon reads hooks only when it starts, so installing the doorbell also means running `ox daemon restart` from inside the vendor repo, never this one (restarting this repo's daemon could disrupt the current session's recording). Ask me before registering or restarting anything. `pulse status` reads the queue and reports how many new engineering sessions have arrived since the last digest; that is the doorbell's visible job. The source of truth is a pull: each `pulse digest` run reconciles sessions from ox's history.
- **Engineering attention** has three evidence levels, recorded per session and theme:
  - **Verified:** commits the session produced (its `SageOx-Session:` trailer or `ProducedCommits`) changed files in the theme's code area, read from git with their diffs.
  - **Reported:** the transcript shows write or edit actions on those files but no linked commit. Label it unverified.
  - **Unknown:** not enough evidence either way. A file that was only read or mentioned doesn't count.
  - Even verified changes mean possibly related engineering activity, not that the session addressed the customer's problem. Verify all of this on a real session before building on it (first session, step 5).
- **Synthetic data:** you write it directly in a recorded session, with no API script, and I review it. Plant the cases listed under Scope deliberately, record the correct answers in the separate evaluation manifest (see Evaluation), and add a small check script that confirms every planted case is present. Size: about 150 Slack messages, 25 GitHub issues with comments, and 60 support tickets, spread over two consecutive weeks so the digest has a real previous period to compare against.
- **Planning with ox:** run `ox plan enrich --topic` before drafting the build plan, then use `ox plan render` and `ox plan review` for my review of it. If `ox plan review` doesn't work on the installed version, fall back to a written proposal and say why.
- **Evaluation:** the correct answers (each record's theme and its links) live in a separate evaluation manifest keyed by record ID. Nothing in ingestion, grouping, linking, or any LLM call may read it; add a test that enforces this.
  - Tune prompts on week 1 only. Generate week 2 once, with the prompts and settings frozen, and save the results.
  - `pulse eval` scores saved results offline, so re-scoring costs nothing. Theme IDs are arbitrary, so score grouping with pairwise precision and recall over record pairs. Score links with precision and recall over (record, issue, relationship) triples. Score theme continuity too: whether week-2 records join the correct week-1 themes instead of creating duplicates.
  - Report scores before human correction, and after correction separately.
  - Replay tests are separate: they prove reproducibility, not model quality.
  - State the limit in DESIGN.md: the same agent wrote the data and the prompts, so these numbers are a regression check, not a claim about real-world quality.
- **Fixture formats:** every fixture stays valid in its native format.
  - The fictional notice lives in `fixtures/README.md` and a fixture manifest, not inside the JSON or CSV files. The support CSV is messy on purpose, but its mess should look like a real export's.
  - **Slack:** the standard export layout (`users.json`, `channels.json`, and one folder per channel with one JSON file per day), with threads preserved (`thread_ts` and replies). The model interprets a whole thread, not a single message, because a reply like "still broken" or "that worked" means nothing alone. Messages stay the evidence rows.
  - **GitHub:** the output of `gh issue list --state all --json number,title,body,state,stateReason,createdAt,closedAt,labels,author,url,comments`. Confirm these fields against the installed `gh` first.
  - **CSV:** a saved mapping is only a suggestion when the header fingerprint matches; types and required fields are validated again on every import.
- **Code hosting:** this repo is public on GitHub, already set up. Local commits are fine; ask before pushing.
- **The ox hook events that never fire:** optional, and not part of the first session. At a natural pause, re-check on the installed version; if it still reproduces, draft a clean-repro issue in the repo (for example under `docs/upstream/`) for me to file myself. Don't post it.
- **Design history:** this design came from an earlier session that ox didn't record. Capture it in DESIGN.md (see the first-session plan).

## Open decisions: ask me when you reach each one

1. Stretch goals: a murmur when a theme spikes (scoped with `--files` to the theme's code paths, with `critical` kept for regressions), and publishing Pulse as a team skill with `ox skills publish`. Ask before starting either.
2. Anything else this prompt doesn't settle.

## Scope for v1

- **In:** the three sources; redaction; stable themes with evidence; a digest for a chosen time window compared with the previous one; review through CLI corrections; replay mode; both publishing tiers; the hook queue, `pulse status`, and session reconciliation; `pulse eval` on the held-out week; a demo on synthetic data.
- **Out:** a REST API or web server, live Slack or GitHub connections, OAuth, multiple tenants, dashboards, health or churn scores, scheduling, automatic publishing, automatic issue creation or customer replies, and PDFs or other arbitrary documents.

**Plant these cases in the synthetic data:**
- The same failed workflow reported by three customers across five threads.
- The same problem reported in both Slack and the CSV.
- A message that could belong to either of two themes (corrected during review).
- A GitHub issue that was closed, then reported again afterwards in a customer message that links to it and describes the same problem.
- A message that mentions an issue but isn't reporting it (for example "this looks unrelated to #142"), which must not support any claim about that issue.
- A message that can't be attributed to any customer.
- A customer message containing a prompt-injection line, which must stay quoted evidence.
- Pulse's own previous digest sitting in team context, which must not count as evidence.

**The demo:**
1. Ingest the three sources, mapping the CSV live.
2. Generate the draft digest.
3. Fix one wrong grouping and confirm one proposed `reports` link.
4. Publish.
5. In the vendor repo, start a fresh agent session and ask it to plan and make a small fix in an affected area, then commit it. Show that it read and used the Pulse doc, with `ox session view --context`.
6. That session uploads. `pulse status` shows the new session. The next digest shows verified, possibly related engineering activity on that theme, marked not resolved, without counting the previous digest as new evidence.

## ox facts verified on 0.18.0

- **Hooks.** `ox hooks add <event> <cmd>` writes to a user-level `hooks.yaml`, not a per-repo file, so a hook fires for events from every ox repo on this machine. The event arrives as JSON on stdin. The environment adds only `OX_EVENT` and `OX_EVENT_TIMESTAMP`, and it is sanitized so secrets aren't passed through. At 500ms the hook's whole process group gets SIGTERM, then SIGKILL at 1s, so a backgrounded child dies too. stdout and stderr are discarded, so log to a file. At most 4 hooks run at once. `ox hooks list` prints the config file's path. Source: `internal/daemon/hooks/runner.go`, `config.go`.
- **Testing and installing hooks.** `ox hooks test <event>` runs matching hooks inside the CLI process with a synthetic payload (`{"test": true}`, project `/tmp/ox-hooks-test`, repo `repo_test`). It doesn't go through the daemon, so it proves only that the script runs. A repo's daemon reads `hooks.yaml` only when it starts, so a new hook needs `ox daemon restart`, which `ox hooks add` itself prints. There's one daemon per repo, chosen by the working directory. `ox hooks add` appends without checking for duplicates, and there's no command to remove a hook: removing one means editing `hooks.yaml` and restarting the daemon. Source: `cmd/ox/hooks_events_test_cmd.go`, `hooks_events_add.go`, `internal/daemon/daemon.go`, `internal/daemon/config.go`, `internal/daemon/hooks/config.go`.
- **Which events fire.** Emitted: `daemon.started`, `daemon.stopped`, `session.uploaded`, `sync.completed`, `sync.failed`, `murmur.received`, `murmur.critical`. Declared but never emitted: `session.started`, `session.stopped`, `session.available`, `agent.registered`, `agent.idle`. `ox hooks add` accepts these, and they never fire. Source: `internal/daemon/hooks/events.go`; the emit sites are in `internal/daemon/daemon.go`, `sync.go`, and `murmur_relay.go`.
- **`session.uploaded`** fires only for this machine's own uploads. Its payload is `session.{name, url, agent_id, duration_seconds}` plus `project_root`, `repo_id`, and `timestamp`. It has no touched files and no summary. Source: `internal/daemon/hooks/payloads.go`, `events.go`.
- **Team docs.** Markdown in the team context's `docs/` directory is listed for agents at every `ox agent prime`. Frontmatter fields: `title`, `description`, `when` (plain-language triggers), and `visibility` (`indexed` by default, or `hidden`; `always` is accepted but currently treated as `indexed`). `when:` only puts triggers in the catalog; the agent reads the full doc if it decides its task matches. Source: `internal/teamdocs/doc.go`, `discover.go`, `cmd/ox/agent_prime.go`.
- **Writing to team context.** ox's team-context guide says direct edits are committed and pushed from inside the team-context checkout, and the daemon picks them up on its next sync. The guide documents this for `agents/rules/`. Its layout doesn't list `docs/` at all (imports land in `documents/`), so `docs/` works in the code but isn't a documented interface. The daemon also pulls and pushes that repo itself, and SageOx's own incident review of sync races there is in `docs/coes/2026-09-02-daemon-git-sync-race-and-lfs-divergence.md`. Source: `cmd/ox/guides/team-context.md`.
- **`ox import`** brings documents and media into team context. It deduplicates by content hash (`--force` re-imports) and supports `--date`, `--title`, and `--text`. The CLI has no update or delete. Knowledge Bubbles are written by SageOx's Curator and can't be imported into. Behavioral rules belong in team rules, not imports.
- **Automatic recall.** On each prompt, ox runs a local query over session history with a 100ms budget and injects at most a 5-line preamble. An optional cloud query has the same 100ms cap. So an imported digest may never surface on its own. Source: `cmd/ox/agent_hook_recall.go`, `agent_hook_cloud_query.go`, `internal/ledgersearch/`.
- **Reading sessions.** `ox session list`, and `ox session view <name> --json`; `--context` shows what context an agent had and what influenced it. `ox conversation` reads recorded team conversations and their distilled topics.
- **Sessions and commits.** While a session is recording, a `prepare-commit-msg` hook adds a `SageOx-Session: <url>` trailer to each commit, and the session's metadata keeps a `ProducedCommits` list. When the two disagree, the trailer wins. Source: `docs/specs/session-commit-linkage.md`.
- **`ox doctor`** only repairs things when given `--fix` or `--fix-slug`; `--yes` skips its confirmation prompts. Source: `cmd/ox/doctor.go`.
- **`ox murmur`** takes `--importance critical|normal|ambient`, `--scope ledger|team`, `--files`, and `--topic`. Murmurs expire after 24 hours and are rate-limited per coworker.
- **`ox skills publish`** publishes repo skills to team context. Runnable team-skill content has to be approved with `ox skills approve` before it runs in a repo.

## First session

1. Read this prompt in full. Check the environment (OS, git, Python, and what's installed). Don't install anything without asking.
2. Check the existing setup without changing it: `ox version`, `ox status`, `git status`, `git remote -v`, `git log --oneline -5` (to see whether the `ox init` changes are committed), `ox team invite --list`, and `ox doctor` without `--fix`, `--fix-slug`, or `--yes` (in the ox source, those are what let it change things). If ox isn't installed or logged in, this repo isn't initialized, or it belongs to a different team than I expect, stop and tell me the exact command that would fix it; don't run it without my OK. Check the git author: `git config user.name` should be "Dhananjay Pahuja" and `user.email` should be pahuja.dhananjay@gmail.com. My old machine had a stray curly quote in the name. Report anything missing or off, and ask before changing it.
3. **Recording gate.** Run `ox session status` and confirm this session is being recorded to my SageOx team. If it isn't, stop: no design work until recording works.
4. Re-verify the ox facts v1 depends on: hooks, testing and installing hooks, which events fire, `session.uploaded`, team docs, writing to team context, `ox import`, reading sessions, sessions and commits, and `ox doctor`. Clone https://github.com/sageox/ox into a scratch location outside this repo at the installed version, check those facts, and list what changed. Don't audit beyond this list; check the murmur and skills facts only when a stretch goal starts.
5. Test the three things the design depends on, and ask me before each one that writes anything:
   - **Team docs:** walk through the publishing order above with a clearly labelled test doc, confirm it's listed in `ox agent prime`, then remove it the same way.
   - **The hook:** register a tiny standard-library script that appends to a log and accepts both payload shapes, then run `ox hooks test session.uploaded`. That proves only that the script runs. Write down how to remove the test hook (there's no remove command), and remove it when done. The real test, a real session upload arriving through a restarted vendor-repo daemon, belongs to the build session that sets up the vendor repo. Registering a hook changes user-level config, so ask me first.
   - **Engineering attention:** inspect a real session with `ox session view <name> --json` and its commits, and confirm we can get the files it changed. If no finished session with commits exists yet, say so and make this the first check of the first build session that commits.
   If any of these doesn't work as described, stop and bring me options.
6. Write DESIGN.md: the problem, the audience, the design above, settled and open decisions, the verified facts with their date and source, and a short section on how the design was reached. For that section: I brainstormed the idea with ChatGPT and Claude, then had both reviews checked against the ox source. The check corrected several of their claims (the hook event name, how hook context arrives, which sessions trigger the hook) and found the team-docs path that neither review mentioned. A second pass found that the doorbell had no reader, that the hook fires for every repo on the machine, and that engineering attention needed a verified source of changed files. Two further reviews tightened the evaluation (answers kept apart from inputs, a held-out week scored offline), the storage contract, the evidence levels, and the demo; added record identity, digest cutoffs, and the difference between mentioning an issue and reporting it; and found that `ox hooks test` bypasses the daemon, which reads hooks only when it starts. Show me the text before committing it.
7. Propose the build as a sequence of small sessions, each with one clear outcome, following the planning decision above. Build a thin end-to-end path first: a few Slack threads and GitHub issues, then an evidence-backed draft, one correction, publishing, and a fresh agent using it. Then add the CSV workbench, the week-over-week comparison, the hook and session reconciliation, and the full dataset with evaluation.
8. Batch the confirmations this prompt asks for into one round, with your proposals: customer names, the vendor repo's location on disk, and the owner/repo name for fixture issue URLs. Then stop and wait for my go-ahead.
