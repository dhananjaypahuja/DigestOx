"""Preflight for engineering attention: prove ox's session history works for the vendor repo.

Run it from the vendor repo (Bivo) after a short recorded session there has committed a change
and ended. Against that real session it checks five things:

1. visible: the session is in the vendor repo's `ox session list`, finished and uploaded
2. trailer: a vendor commit's `SageOx-Session:` trailer resolves to the session
3. changed files: git gives the files that commit changed
4. transcript: the session's transcript has write or edit actions whose paths match them
5. separate repos: DigestOx's sessions never appear in the vendor's list, and the vendor's
   never appear in DigestOx's

Every ox command runs with stdin closed, and its JSON is parsed defensively. The preflight
changes nothing, except that `ox session download` may cache the session's content locally.

Usage, from the vendor repo:

    uv run --project <DigestOx> python <DigestOx>/scripts/ox_preflight.py [--session NAME] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

DIGESTOX = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 180
SESSION_ID = re.compile(r"\bses_[0-9a-z][0-9a-z-]*[0-9a-z]\b")
FILE_TOOLS = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch", "write_file", "edit_file"}
)
PATH_KEYS = ("file_path", "path", "notebook_path", "filename")
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
NOISE = ("otel export paused",)

Runner = Callable[[list[str], Path], str]


class PreflightError(RuntimeError):
    """A command failed, or printed something the preflight can't read."""


def run_command(argv: list[str], cwd: Path) -> str:
    """Run a command in ``cwd`` with stdin closed and return its stdout."""
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"`{' '.join(argv)}` couldn't run: {exc}") from exc
    if result.returncode != 0:
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        lines = [line for line in lines if not any(noise in line for noise in NOISE)]
        detail = lines[0] if lines else "no error message"
        raise PreflightError(f"`{' '.join(argv)}` exited {result.returncode}: {detail}")
    return result.stdout


def load_json(text: str, what: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"{what} didn't print JSON ({exc.msg}, line {exc.lineno})") from exc


@dataclass
class Check:
    number: int
    name: str
    passed: bool | None  # None: couldn't run yet
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass
class Report:
    vendor_repo: str
    other_repo: str
    session: str | None
    checks: list[Check]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_json(self) -> dict[str, object]:
        return {
            "vendor_repo": self.vendor_repo,
            "other_repo": self.other_repo,
            "session": self.session,
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


# Reading ox and git


def list_sessions(run: Runner, repo: Path) -> list[dict]:
    """Every session in the repo's ledger, newest first as ox lists them."""
    what = f"`ox session list` in {repo}"
    data = load_json(run(["ox", "session", "list", "--json", "--all"], repo), what)
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list):
        raise PreflightError(f"{what} has no sessions list")
    return [s for s in sessions if isinstance(s, dict) and isinstance(s.get("name"), str)]


def view_session(run: Runner, repo: Path, name: str, *extra: str) -> object:
    """`ox session view --json`, downloading the session's content once if it's a stub."""
    argv = ["ox", "session", "view", name, "--json", *extra]
    what = f"`ox session view {name}`"
    try:
        return load_json(run(argv, repo), what)
    except PreflightError:
        run(["ox", "session", "download", name], repo)
        return load_json(run(argv, repo), what)


def session_trailers(run: Runner, repo: Path) -> dict[str, list[str]]:
    """Commit SHA to the session IDs its `SageOx-Session:` trailers name."""
    out = run(
        [
            "git",
            "log",
            "--all",
            "--format=%H%x1f%(trailers:key=SageOx-Session,valueonly,separator=%x1d)%x1e",
        ],
        repo,
    )
    found: dict[str, list[str]] = {}
    for record in out.split("\x1e"):
        sha, _, values = record.strip().partition("\x1f")
        ids = SESSION_ID.findall(values)
        if sha and ids:
            found[sha] = ids
    return found


def changed_files(run: Runner, repo: Path, sha: str) -> list[str]:
    out = run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], repo)
    return [line for line in out.splitlines() if line]


# Reading a session's JSON, whatever its exact shape


def strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


def session_ids(node: object) -> set[str]:
    return {found for text in strings(node) for found in SESSION_ID.findall(text)}


def _paths(tool: str, arguments: object) -> list[str]:
    if isinstance(arguments, str):
        if tool == "apply_patch":
            return PATCH_FILE.findall(arguments)
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return []
    if not isinstance(arguments, dict):
        return []
    if tool == "apply_patch":
        return [path for text in strings(arguments) for path in PATCH_FILE.findall(text)]
    for key in PATH_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return [value]
    return []


def file_actions(node: object) -> list[tuple[str, str]]:
    """(tool, path) for each recorded tool call that writes or edits a file, first seen first."""
    found: list[tuple[str, str]] = []

    def walk(item: object) -> None:
        if isinstance(item, dict):
            tool = item.get("name") or item.get("tool_name") or item.get("tool")
            if isinstance(tool, str) and tool in FILE_TOOLS:
                for key in ("input", "tool_input", "arguments", "params", "args"):
                    if key in item:
                        for path in _paths(tool, item[key]):
                            if (tool, path) not in found:
                                found.append((tool, path))
                        break
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(node)
    return found


def repo_relative(path: str, repo: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


# The five checks


def preflight(
    vendor: Path, other: Path, session: str | None = None, run: Runner = run_command
) -> Report:
    vendor_sessions = list_sessions(run, vendor)
    other_sessions = list_sessions(run, other)
    vendor_names = [s["name"] for s in vendor_sessions]
    other_names = {s["name"] for s in other_sessions}

    chosen = None
    if session:
        chosen = next((s for s in vendor_sessions if s["name"] == session), None)
    else:
        chosen = next((s for s in vendor_sessions if s.get("status") != "recording"), None)
    name = chosen["name"] if chosen else session

    checks: list[Check] = []
    overlap = sorted(set(vendor_names) & other_names)
    exclusion = Check(
        5,
        "separate repos",
        not overlap,
        f"{len(overlap)} of {vendor.name}'s {len(vendor_names)} sessions appear in "
        f"{other.name}'s {len(other_names)}",
        [f"in both lists: {n}" for n in overlap],
    )

    if chosen is None:
        wanted = f"session {session}" if session else "a finished session"
        missing = f"{wanted} isn't in {vendor.name}'s session list yet"
        checks.append(Check(1, "visible", False, missing, [f"listed: {len(vendor_names)}"]))
        for number, label in ((2, "trailer"), (3, "changed files"), (4, "transcript")):
            checks.append(Check(number, label, None, "waiting for a finished session"))
        return Report(str(vendor), str(other), name, [*checks, exclusion])

    status = chosen.get("status")
    checks.append(
        Check(
            1,
            "visible",
            status == "uploaded" and not chosen.get("recording"),
            f"{status}, in {vendor.name}'s session list",
            [f"entries: {chosen.get('entry_count')}"],
        )
    )

    metadata = view_session(run, vendor, name, "--metadata")
    own_ids = session_ids(metadata)
    trailers = session_trailers(run, vendor)
    commits = [sha for sha, ids in trailers.items() if own_ids & set(ids)]
    trailer_details = [f"{sha[:7]} names {', '.join(ids)}" for sha, ids in trailers.items()]
    checks.append(
        Check(
            2,
            "trailer",
            bool(commits),
            (
                f"{len(commits)} commit(s) name this session: {', '.join(c[:7] for c in commits)}"
                if commits
                else f"no commit's trailer names {', '.join(sorted(own_ids)) or 'this session'}"
            ),
            trailer_details or ["no commit carries a SageOx-Session trailer"],
        )
    )

    changed = sorted({path for sha in commits for path in changed_files(run, vendor, sha)})
    checks.append(
        Check(
            3,
            "changed files",
            bool(changed) if commits else None,
            f"{len(changed)} file(s) changed" if commits else "waiting for a resolved commit",
            changed,
        )
    )

    transcript = view_session(run, vendor, name)
    actions = [(tool, repo_relative(path, vendor)) for tool, path in file_actions(transcript)]
    matched = sorted({path for _, path in actions} & set(changed))
    checks.append(
        Check(
            4,
            "transcript",
            bool(actions) and bool(matched),
            f"{len(actions)} write or edit action(s) with paths; "
            f"{len(matched)} match the changed files",
            [f"{tool} {path}" for tool, path in actions],
        )
    )
    exclusion.details.append(f"{name} in {other.name}'s list: {name in other_names}")
    exclusion.passed = exclusion.passed and name not in other_names
    return Report(str(vendor), str(other), name, [*checks, exclusion])


def render(report: Report) -> str:
    marks = {True: "✓", False: "✗", None: "…"}
    lines = [
        f"Preflight: engineering attention in {report.vendor_repo}",
        f"Session: {report.session or 'none yet'}",
        "",
    ]
    for check in report.checks:
        lines.append(f"{marks[check.passed]} {check.number} {check.name:<15} {check.summary}")
        lines.extend(f"      {detail}" for detail in check.details)
    lines.append("")
    lines.append("All five checks pass." if report.passed else "The preflight hasn't passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vendor-repo", type=Path, default=Path.cwd(), help="default: here")
    parser.add_argument("--other-repo", type=Path, default=DIGESTOX, help="default: DigestOx")
    parser.add_argument("--session", help="the session to check (default: newest finished)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = preflight(args.vendor_repo.resolve(), args.other_repo.resolve(), args.session)
    except PreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_json(), indent=2) if args.json else render(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
