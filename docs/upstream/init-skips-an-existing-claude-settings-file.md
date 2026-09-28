# `ox init` skips an existing `.claude/settings.json`, so Claude Code sessions go unrecorded

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed on 2026-09-28

## What happened

A new repository already had a project `.claude/settings.json` holding one hook of its own: a
PostToolUse lint check. `ox init --team <team id> --agents claude,codex --no-input` printed
"✓ Installed AI coworker integrations and skills" and finished successfully. But it left
`.claude/settings.json` unchanged: none of ox's six Claude Code hooks (SessionStart,
SessionEnd, Stop, PreCompact, PostToolUse, UserPromptSubmit) were added. Codex's hooks and the
git hooks were installed.

Afterwards, `ox integrate list` showed Claude Code as not integrated. A Claude Code session in
that repository would neither prime nor record, and nothing warned about it. In another
repository with no `.claude/settings.json`, the same `ox init` created the file with all six
hooks (2026-09-26).

## Reproduce

This mirrors what we observed. We haven't run it separately, because `ox init` registers the
repository with a team.

```sh
mkdir demo && cd demo && git init -q && mkdir .claude
printf '%s\n' '{"hooks": {"PostToolUse": [{"matcher": "Edit",
  "hooks": [{"type": "command", "command": "true"}]}]}}' > .claude/settings.json
git add -A && git commit -qm "project settings"
ox init --team <team id> --agents claude --no-input </dev/null
python3 -c 'import json; print(sorted(json.load(open(".claude/settings.json"))["hooks"]))'
# ['PostToolUse']: only the project's own hook
ox integrate list    # Claude Code: ✗
```

## Expected

`ox init` merges its hooks into an existing project settings file and keeps the entries already
there. Failing that, it should say it didn't install them, and how to.

## Workaround

Copy the six hook entries from a repository where `ox init` created the file, and keep the
project's own entries next to them. `ox integrate list` then reports Claude Code as
integrated. `ox integrate install` isn't the same fix: its help says it writes to
`~/.claude/settings.json`, which affects every project on the machine.
