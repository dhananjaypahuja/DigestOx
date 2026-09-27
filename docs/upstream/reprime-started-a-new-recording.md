# A re-prime inside a session started a new recording

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed once on 2026-09-27; root cause not
established

## Summary

A Claude Code session had been recording since the previous evening, and
`ox session status` confirmed it was live. We then ran `ox agent prime` from the agent's tool
shell. ox started a **new** recording for the same agent ID, and the original recording
disappeared from `ox session status` and `ox session list`.

Re-running prime is a normal path, not an edge case. The `AGENTS.md` that `ox init` writes
tells agents to run it "on session start, after compaction, or clear".

## What we saw

1. Before: `ox session status` reported "Recording in progress", a duration of about 18 hours,
   23 entries, and a live agent process. `ox session list` showed that session as `recording`.
2. We ran `ox agent prime` from the tool shell. The first attempt waited on stdin (see
   [prime-waits-on-open-stdin.md](prime-waits-on-open-stdin.md)) and was killed. The second,
   run with `</dev/null`, returned in about a second.
3. Its compact re-prime output carried the same agent ID but a **new** session URL.
4. After: `ox session status` reported a recording started seconds earlier with 0 entries, and
   `ox session list` showed only the new session.
5. The original recording's files (`.recording.json`, `raw.jsonl`) were still on disk, under
   the ledger's `.gc-cache/sessions/<session>/` directory. That directory was dated the
   previous evening, around the time of the ledger's last sync.

## What we don't know

- Whether a ledger GC the previous evening moved the live recording's state into `.gc-cache`,
  so that the next prime found no active recording and started one.
- Whether the original recording can still be uploaded, for example by
  `ox doctor --force-session-uploads`. We didn't try, to avoid further changes.

## Expected

A prime inside a session that already has a live recording reuses it, which is what the
comments in `cmd/ox/agent_prime.go` describe ("reuse that recording's agent ID so prime stays
idempotent"). If the recording's state is missing, prime should say so rather than silently
start another.

## Suggested fixes

- Never let ledger GC move the state of a recording whose agent process is alive.
- When prime would start a recording for an agent that already has one on record, report it
  and keep the existing one, or ask.
