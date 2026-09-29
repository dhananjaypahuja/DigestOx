# 0012. One model, no fallback: Claude Opus 5.5 at high effort

- **Status:** Accepted
- **Date:** 2026-09-29
- **Decided by:** Dhananjay Pahuja, before session 4's code ("we need reliable inferred
  results"; "no fallback, need consistent results with no drifts")
- **Drafted by:** Claude, AI coworker, in SageOx-recorded session 4

## Context

The kickoff set one Claude model at high effort for every task, and named `claude-opus-5`.
The plan left the model ID to be confirmed against Anthropic's documentation when the module
was written (DESIGN.md section 13, open item 2). The current reference (checked 2026-09-29)
shows:

- `claude-opus-5-5` is the current Opus and the recommended default. It costs $4 / $20 per
  million input / output tokens, against $5 / $25 for `claude-opus-5`.
- Its effort defaults to `medium`, one level below `claude-opus-5`'s `high`, so it has to be set
  explicitly. Thinking is always on (adaptive), and forced tool choice is refused, so typed
  output comes from structured JSON output.
- The reference recommends a server-side refusal fallback: when the model declines, the API
  re-runs the request on another model inside the same call.

A fallback conflicts with replay. Pulse keys each saved response by its request, which names
the model, and replay promises that the same request gives the same saved answer. A response
written by a fallback model would sit under a request that names a different one.

## Decision

1. **Model:** `claude-opus-5-5` for every task, at `effort: high`, with adaptive thinking (its
   only mode) and structured JSON output (`output_config.format`). The settings live in
   `pulse.toml` under `[llm]`, and every request's hash covers them.
2. **No fallback.** A refusal (`stop_reason: "refusal"`) stops the run with `model_refused`.
   So does a truncated reply (`model_incomplete`). No other model ever answers.
3. **Only checked answers are saved.** A response is cached only after it validates against
   its schema and passes the task's own checks, so a bad answer is asked again, not replayed.

## Consequences

- A run on the same inputs and the same saved responses gives the same result; replay needs
  no key and costs nothing.
- A refusal on real customer text stops the run for a person to look at the evidence. The
  fixtures are synthetic, so none is expected in the demo.
- Changing `[llm]` changes every request's hash, so saved responses stop answering until a
  new live run.

## Related decisions

- **Aligns with 0005:** the request gate (gate 2) runs on every request before it is sent,
  cached, or replayed, and no fallback path bypasses it.

<!-- SOURCE: sageox adr:docs/decisions/0005-privacy-gates-before-storage-model-calls-and-publishing.md -->

## References

- DESIGN.md, section 7
- `src/customer_pulse/llm.py`, `src/customer_pulse/themes.py`, `tests/test_grouping.py`
