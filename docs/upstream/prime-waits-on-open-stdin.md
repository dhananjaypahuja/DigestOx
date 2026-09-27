# `ox agent prime` waits forever on an open stdin

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed

## Summary

Run from an agent's tool shell, where stdin is an open pipe that never closes, `ox agent prime`
printed nothing for more than 45 seconds and had to be killed. The same command with
`</dev/null` finished in about a second.

## Evidence

- `cmd/ox/agent_prime.go:231` calls `ReadAgentHookInput()`, which calls
  `agentx.ReadHookInputFromStdin()` in the external `agentx` module. We didn't inspect that
  module, but the behavior fits a read that waits for end-of-file.
- The command's own help (`cmd/ox/agent_prime.go:105`) promises the opposite: "designed for
  fail-fast operation - it will never block coding agents for extended periods."

## To reproduce

From a process whose stdin is an open pipe with no data, for example:

```sh
sleep 600 | ox agent prime    # waits
ox agent prime </dev/null     # returns promptly
```

## Suggested fix

Read hook input from stdin only when data arrives within a short deadline, for example
200 ms. Otherwise continue as if there were no hook input. This matters beyond tool shells:
the repo's `AGENTS.md` asks agents to re-run prime after compaction, and agents usually do
that from a shell like this one.
