# Session JSON omits the ID that commit trailers carry

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed on 2026-09-28

## What happened

A commit made during a recorded session carries a trailer such as
`SageOx-Session: https://sageox.ai/c/ses_01a0ea6a-…`. A tool that reads session history
wants to map that trailer back to the session, so it can say which session produced which
commit. Neither documented JSON view carries the `ses_…` ID:

- `ox session list --json` gives each session's name, date, time, user, status, title,
  summary, entry count, and hydration state.
- `ox session view <name> --json --metadata` gives the agent ID and type, the user, the repo
  ID, and the creation time.

So the trailer can't be matched to a session by ID. The workaround we use is to find the
commit, with its trailer, in the session's own recorded git output. That's weaker: a session
that merely printed another session's commit matches too.

## Expected

Include the session's `ses_…` ID (or its URL) in `ox session list --json` and in
`ox session view --json --metadata`. The commits the session produced would help as well.
Per the source, `ox agent session stop` already records them as `ProducedCommits`.
