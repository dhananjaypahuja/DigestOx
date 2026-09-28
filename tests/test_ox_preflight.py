"""The engineering-attention preflight (scripts/ox_preflight.py), against fake ox and git output.

The real evidence is the preflight's run against a real Bivo session; these tests pin how it
reads ox's JSON, git's trailers, and transcripts of different shapes, and how each check fails.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ox_preflight.py"
spec = importlib.util.spec_from_file_location("ox_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight  # dataclasses resolve annotations through it
spec.loader.exec_module(preflight)

BIVO_SESSION = "2026-10-01T17-00-pahuja-dhananjay-OxB1v0"
BIVO_ID = "ses_01a0eb00-1111-7222-8333-444455556666"
OTHER_ID = "ses_01a0e910-fe34-76e9-9a87-92258c59c9e8"
SHA = "a" * 40


class FakeOx:
    """Answers each (command, repo folder) with canned output, and records the calls."""

    def __init__(self, vendor, other):
        self.vendor, self.other = vendor, other
        self.calls = []
        self.answers = {
            ("list", vendor.name): {
                "sessions": [
                    {"name": BIVO_SESSION, "status": "uploaded", "recording": False,
                     "entry_count": 14},
                ]
            },
            ("list", other.name): {
                "sessions": [{"name": "2026-09-28T17-30-pahuja-dhananjay-Oxx108",
                              "status": "recording", "recording": True}]
            },
            ("metadata", vendor.name): {"session_id": BIVO_ID, "agent": "claude"},
            ("view", vendor.name): {
                "entries": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": str(vendor / "bivo/sso/service.py")}},
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": str(vendor / "bivo/coach_tools/service.py")}},
                    {"type": "tool", "tool_name": "Write",
                     "tool_input": {"file_path": str(vendor / "CHANGELOG.md")}},
                ]
            },
            ("log", vendor.name): (
                f"{SHA}\x1fhttps://sageox.ai/c/{BIVO_ID}\x1e\n{'b' * 40}\x1f\x1e\n"
            ),
            ("diff-tree", vendor.name): "CHANGELOG.md\nbivo/coach_tools/service.py\n",
            ("download", vendor.name): "",
        }  # fmt: skip

    def __call__(self, argv, cwd):
        self.calls.append((argv, Path(cwd).name))
        kind = {"list": "list", "download": "download", "log": "log", "diff-tree": "diff-tree"}
        key = "metadata" if "--metadata" in argv else ("view" if "view" in argv else None)
        key = key or next(kind[word] for word in argv if word in kind)
        answer = self.answers[(key, Path(cwd).name)]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, list):
            answer = answer.pop(0)
            if isinstance(answer, Exception):
                raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


@pytest.fixture
def repos(tmp_path):
    return tmp_path / "bivo-platform", tmp_path / "DigestOx"


@pytest.fixture
def ox(repos):
    return FakeOx(*repos)


def check(report, number):
    return next(c for c in report.checks if c.number == number)


def test_all_five_checks_pass_on_a_finished_session(repos, ox):
    report = preflight.preflight(*repos, run=ox)
    assert [c.passed for c in report.checks] == [True, True, True, True, True]
    assert report.passed
    assert check(report, 3).details == ["CHANGELOG.md", "bivo/coach_tools/service.py"]
    assert check(report, 4).details == [
        "Edit bivo/coach_tools/service.py",
        "Write CHANGELOG.md",
    ]
    assert "All five checks pass." in preflight.render(report)


def test_every_ox_command_runs_in_the_right_repo(repos, ox):
    preflight.preflight(*repos, run=ox)
    ox_calls = [(argv[:3], where) for argv, where in ox.calls if argv[0] == "ox"]
    assert (["ox", "session", "list"], "DigestOx") in ox_calls
    assert all(where == "bivo-platform" for argv, where in ox_calls if argv[2] == "view")


def test_without_a_finished_session_the_session_checks_wait(repos, ox):
    vendor = repos[0]
    ox.answers[("list", vendor.name)] = {
        "sessions": [{"name": BIVO_SESSION, "status": "recording", "recording": True}]
    }
    report = preflight.preflight(*repos, run=ox)
    assert [c.passed for c in report.checks] == [False, None, None, None, True]
    assert not report.passed
    assert "isn't in bivo-platform's session list yet" in check(report, 1).summary


def test_a_trailer_naming_another_session_does_not_resolve(repos, ox):
    ox.answers[("log", repos[0].name)] = f"{SHA}\x1fhttps://sageox.ai/c/{OTHER_ID}\x1e"
    report = preflight.preflight(*repos, run=ox)
    assert check(report, 2).passed is False
    assert check(report, 3).passed is None
    assert check(report, 2).details == [f"{SHA[:7]} names {OTHER_ID}"]


def test_transcript_actions_must_touch_the_committed_files(repos, ox):
    vendor = repos[0]
    ox.answers[("view", vendor.name)] = {
        "entries": [{"name": "Edit", "input": {"file_path": str(vendor / "bivo/sso/router.py")}}]
    }
    report = preflight.preflight(*repos, run=ox)
    assert check(report, 4).passed is False
    assert check(report, 4).summary.endswith("0 match the changed files")


def test_a_session_in_both_lists_fails_the_separation_check(repos, ox):
    ox.answers[("list", repos[1].name)] = {"sessions": [{"name": BIVO_SESSION}]}
    report = preflight.preflight(*repos, run=ox)
    assert check(report, 5).passed is False
    assert check(report, 5).details[0] == f"in both lists: {BIVO_SESSION}"


def test_a_stub_session_is_downloaded_once_then_read(repos, ox):
    vendor = repos[0]
    stub = preflight.PreflightError("`ox session view` exited 1: session not found")
    ox.answers[("metadata", vendor.name)] = [stub, {"session_id": BIVO_ID}]
    report = preflight.preflight(*repos, run=ox)
    assert check(report, 2).passed
    kinds = [argv[2] for argv, _ in ox.calls if argv[0] == "ox"]
    assert kinds.count("download") == 1
    assert kinds.index("download") < len(kinds) - 1


def test_output_that_isnt_json_is_a_clear_error(repos, ox):
    ox.answers[("list", repos[0].name)] = "Syncing ledger…\n"
    with pytest.raises(preflight.PreflightError, match="didn't print JSON"):
        preflight.preflight(*repos, run=ox)


def test_file_actions_reads_the_shapes_agents_record():
    transcript = [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/a.py"}},
        {"tool_name": "MultiEdit", "tool_input": {"file_path": "/repo/b.py"}},
        {"tool": "write_file", "arguments": json.dumps({"path": "c.md"})},
        {"name": "apply_patch", "input": "*** Begin Patch\n*** Update File: d.py\n*** End Patch"},
        {"name": "NotebookEdit", "input": {"notebook_path": "/repo/e.ipynb"}},
        {"name": "Read", "input": {"file_path": "/repo/ignored.py"}},
        {"name": "Edit", "input": {"file_path": "/repo/a.py"}},
    ]
    assert preflight.file_actions({"entries": transcript}) == [
        ("Edit", "/repo/a.py"),
        ("MultiEdit", "/repo/b.py"),
        ("write_file", "c.md"),
        ("apply_patch", "d.py"),
        ("NotebookEdit", "/repo/e.ipynb"),
    ]


def test_commands_run_with_stdin_closed_and_failures_are_readable(monkeypatch, tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="otel export paused\nError: session not found\n"
        )

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    with pytest.raises(preflight.PreflightError, match="exited 1: Error: session not found"):
        preflight.run_command(["ox", "session", "view", "x", "--json"], tmp_path)
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["cwd"] == tmp_path
