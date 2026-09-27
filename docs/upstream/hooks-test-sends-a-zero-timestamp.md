# `ox hooks test` sends a zero timestamp

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed

## Summary

The synthetic event from `ox hooks test <event>` has no timestamp. Hooks receive
`OX_EVENT_TIMESTAMP=0001-01-01T00:00:00Z` and `"timestamp": "0001-01-01T00:00:00Z"` in the
JSON on stdin. A hook that orders, filters, or deduplicates events by time mishandles test
events, so the test doesn't exercise the path it's meant to check.

## Evidence

- `cmd/ox/hooks_events_test_cmd.go:58-63` builds the event with `Name`, `Project`, `RepoID`,
  and `Payload`, and never sets `Timestamp`.
- `internal/daemon/hooks/runner.go:102` sets `OX_EVENT_TIMESTAMP` from `event.Timestamp`, and
  `Event.Marshal` (`internal/daemon/hooks/events.go`) writes it into the JSON.
- Observed with a hook that recorded `OX_EVENT_TIMESTAMP`: `0001-01-01T00:00:00Z`.

## Suggested fix

Set `Timestamp: time.Now()` in the synthetic event.
