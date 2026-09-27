# Docs that disagree with the code

**ox:** 0.18.0 (`f52d5c94`) · **Found:** from source

These are small, but each one led us to a wrong assumption while building an integration.

## The team-context guide says the daemon pushes

`cmd/ox/guides/team-context.md:66`: "The ox daemon pulls and pushes the team-context git repo
periodically. … You don't need to push manually — the daemon handles it after `ox` commands
write to team context."

The daemon's team-context sync is pull-only: `internal/daemon/sync_team.go` pulls, with
divergence detection, and never pushes. Line 68 of the same guide correctly tells people to
push their own direct edits. Line 66 should match.

## The guide says imports land in `documents/`

`cmd/ox/guides/team-context.md:39` shows `documents/ ← imported docs (via ox import)`.
`cmd/ox/import.go:206` stores imports under `data/docs/<date>/<slug>`.

## The guide's layout omits `docs/`

Team docs in `docs/` are cataloged at every `ox agent prime` (`teamdocs.DiscoverDocs`, called
from `cmd/ox/agent_prime.go`), but the guide's repository layout doesn't list `docs/` at all.
The seeded `docs/README.md` in a new team context does document it.

## The seeded docs README describes a richer catalog than prime shows

The `docs/README.md` that sageox.ai seeds into a new team context says coworkers "see
document titles and descriptions at session start". `cmd/ox/agent_prime_xml.go` emits only
`| Name | When to Read |`: the file name and the `when:` text, falling back to the title. The
description never appears. Authors who rely on `description` for discoverability get nothing
from it at prime.

## `ox doctor --help` implies nothing changes without `--fix`

The help says "Use --fix to auto-repair common issues". But checks at `FixLevelAuto`
(`cmd/ox/doctor_types.go:13-16`) repair without `--fix`. That includes the legacy-files check,
which can commit ("Committed as … revert it if you disagree"). And `ox doctor` starts the
daemon (`cmd/ox/doctor.go:172`). The help should say that a plain `ox doctor` may apply safe
fixes and start the daemon.
