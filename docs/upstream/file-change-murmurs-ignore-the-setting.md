# File-change murmurs ignore the murmuring setting

**ox:** 0.18.0 (`f52d5c94`) · **Found:** from source; one automatic murmur observed

## Summary

While a repo's daemon runs, it publishes `file-changes` murmurs to the ledger whenever tracked
files change. It does this whatever the murmuring setting says. A user who wants control over
what goes to their team can't turn these off, short of keeping the daemon stopped. The daemon
starts on its own for agent sessions, so that isn't a real option.

## Evidence

- `internal/daemon/daemon.go:1343-1363` creates `NewFileChangeMurmurPublisher` whenever the
  daemon has a project root and a ledger path.
- `internal/daemon/file_change_source.go` never calls `config.MurmuringEnabled`. The murmur
  relay does: the comment at `daemon.go:1291` says the relay and nudge tracker "re-check
  MurmuringEnabled() on every tick".
- `config.MurmuringEnabled` (`internal/config/murmuring.go:190`) is true only for the `auto`
  mode.
- Observed: after creating a file named `DESIGN.md`, a murmur with topic `file-changes` and
  content `[main] new DESIGN.md` appeared. `ox plan save` then reported it as a "collision"
  on DESIGN.md, attributed to the same person who made the edit.

## Expected

Either the murmuring setting also governs file-change murmurs, or there is a separate,
documented setting for them. A self-collision (the plan's author editing the file) probably
shouldn't count as a collision at all.

## Impact

Teams with strict rules about what gets shared (for example, file names under an NDA) can't
use a murmuring setting to stop file names reaching the ledger.
