# Draft issues for ox

These are drafts for Dhananjay to file on [sageox/ox](https://github.com/sageox/ox).
None has been posted. Each was found while building Customer Pulse against **ox 0.18.0**
(commit `f52d5c94`); `main` at `c7a76ab` touches none of the files involved. Source paths and
line numbers refer to `f52d5c94`.

Each draft says how the problem was found. "Observed" means it happened on this machine;
"from source" means it was read in the code and not yet reproduced end to end.

| Draft | Found | Severity |
|---|---|---|
| [`session.uploaded` hooks never fire](session-uploaded-never-fires.md) | from source | high: a documented hook is silent |
| [A re-prime inside a session started a new recording](reprime-started-a-new-recording.md) | observed | high: recording continuity |
| [`ox agent prime` waits forever on an open stdin](prime-waits-on-open-stdin.md) | observed | medium |
| [File-change murmurs ignore the murmuring setting](file-change-murmurs-ignore-the-setting.md) | from source, and one observed murmur | medium |
| [`ox hooks test` sends a zero timestamp](hooks-test-sends-a-zero-timestamp.md) | observed | low |
| [`ox plan lint --file` flags a credit that only exists in ox's own script](plan-lint-matches-its-own-chrome.md) | observed and from source | low |
| [Docs that disagree with the code](docs-that-disagree-with-the-code.md) | from source | low |
