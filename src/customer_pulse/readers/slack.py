"""Read a Slack workspace export: the ZIP Slack produces, or the folder it unzips to.

An export holds ``channels.json``, ``users.json``, and one ``<channel>/<YYYY-MM-DD>.json`` file
per channel and day, each a list of messages. A message's identity is its channel ID and
``ts``; its thread is the parent's ``thread_ts``, or its own ``ts`` when it starts one. Every
message gets a thread key, so a message that gains replies in a later export keeps it.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from customer_pulse.errors import PulseError
from customer_pulse.readers import RawSignal

# Messages people wrote. Joins, topic changes, and bot posts aren't customer evidence.
_KEPT_SUBTYPES = {None, "thread_broadcast", "file_share", "me_message"}
_DAY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.json")
_TS = re.compile(r"(\d{1,12})\.(\d{6})")
_MARKUP = re.compile(r"<([^<>]*)>")


@dataclass(frozen=True)
class Channel:
    id: str
    name: str


@dataclass(frozen=True)
class SlackExport:
    content_sha256: str
    file_name: str
    channels: list[Channel]
    signals: list[RawSignal]
    skipped: int  # events that aren't messages people wrote


def _invalid(path: Path, message: str) -> PulseError:
    return PulseError(
        "invalid_export",
        f"{path}: {message}",
        hint="pass the Slack export ZIP, or the folder it unzips to",
    )


class _Files:
    """The export's files, from a ZIP or a folder, by POSIX path relative to the export root."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, bytes] = {}
        if path.is_dir():
            for file in sorted(path.rglob("*.json")):
                if file.is_file() and not file.is_symlink():
                    self._data[file.relative_to(path).as_posix()] = file.read_bytes()
            listing = "".join(
                f"{name}\0{hashlib.sha256(data).hexdigest()}\n"
                for name, data in sorted(self._data.items())
            )
            # A folder has no single file to hash, so its batch hash covers every file's
            # path and content.
            self.sha256 = hashlib.sha256(listing.encode("utf-8")).hexdigest()
        elif path.is_file():
            raw = path.read_bytes()
            self.sha256 = hashlib.sha256(raw).hexdigest()
            try:
                with zipfile.ZipFile(path) as archive:
                    for info in archive.infolist():
                        name = PurePosixPath(info.filename)
                        if info.is_dir() or name.suffix != ".json" or ".." in name.parts:
                            continue
                        self._data[name.as_posix()] = archive.read(info)
            except zipfile.BadZipFile as exc:
                raise _invalid(path, "not a ZIP file") from exc
            self._strip_common_root()
        else:
            raise PulseError("file_not_found", f"{path} does not exist")

    def _strip_common_root(self) -> None:
        # Some tools zip the export inside one top-level folder.
        if "channels.json" in self._data:
            return
        roots = {name.split("/", 1)[0] for name in self._data}
        if len(roots) == 1 and (root := roots.pop()) + "/channels.json" in self._data:
            prefix = root + "/"
            self._data = {k.removeprefix(prefix): v for k, v in self._data.items()}

    def json(self, name: str) -> Any:
        try:
            return json.loads(self._data[name].decode("utf-8"))
        except KeyError as exc:
            raise _invalid(self.path, f"{name} is missing") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _invalid(self.path, f"{name} is not valid JSON: {exc}") from exc

    def day_files(self, channel: str) -> Iterator[str]:
        prefix = channel + "/"
        for name in sorted(self._data):
            rest = name.removeprefix(prefix)
            if name.startswith(prefix) and _DAY_FILE.fullmatch(rest):
                yield name


def parse_ts(value: Any) -> datetime:
    """A Slack ``ts`` ("1789402320.000100") as an exact UTC instant, without float rounding."""
    match = _TS.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError(f"not a Slack ts: {value!r}")
    seconds, micros = int(match.group(1)), int(match.group(2))
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=micros)


def render_text(text: str, users: dict[str, dict[str, Any]]) -> str:
    """Turn Slack's markup into plain text a person would read.

    ``<@U123>`` becomes ``@Name``, ``<#C123|general>`` becomes ``#general``, links become their
    URL (with the label first when it differs), ``<mailto:a@b|a@b>`` becomes the address, and
    HTML entities are unescaped. Redaction runs on the result.
    """

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        target, _, label = inner.partition("|")
        if target.startswith("@"):
            user = users.get(target[1:], {})
            return "@" + (user.get("real_name") or label or target[1:])
        if target.startswith("#"):
            return "#" + (label or target[1:])
        if target.startswith("!"):
            return "@" + (label or target[1:].split("^", 1)[0])
        if target.startswith("mailto:"):
            return label or target.removeprefix("mailto:")
        if label and label != target:
            return f"{label} ({target})"
        return target

    return html.unescape(_MARKUP.sub(replace, text))


def read_export(path: Path) -> SlackExport:
    files = _Files(path)
    channels_json, users_json = files.json("channels.json"), files.json("users.json")
    if not isinstance(channels_json, list) or not isinstance(users_json, list):
        raise _invalid(path, "channels.json and users.json must each hold a list")
    users = {u["id"]: _user(u) for u in users_json if isinstance(u, dict) and "id" in u}
    channels, signals, skipped = [], [], 0
    for entry in channels_json:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("name"):
            raise _invalid(path, "every channel in channels.json needs an id and a name")
        channel = Channel(entry["id"], entry["name"])
        channels.append(channel)
        for name in files.day_files(channel.name):
            messages = files.json(name)
            if not isinstance(messages, list):
                raise _invalid(path, f"{name} must hold a list of messages")
            for message in messages:
                signal = _signal(message, channel, users, path, name)
                if signal is None:
                    skipped += 1
                else:
                    signals.append(signal)
    signals.sort(key=lambda s: (s.occurred_at, s.source_key))
    return SlackExport(files.sha256, path.name, channels, signals, skipped)


def _user(entry: dict[str, Any]) -> dict[str, Any]:
    profile = entry.get("profile") or {}
    return {
        "real_name": entry.get("real_name") or profile.get("real_name") or entry.get("name"),
        "email": profile.get("email"),
        "team": entry.get("team_id") or profile.get("team"),
    }


def _signal(
    message: Any, channel: Channel, users: dict[str, dict[str, Any]], path: Path, name: str
) -> RawSignal | None:
    if not isinstance(message, dict):
        raise _invalid(path, f"{name} holds something that isn't a message")
    if message.get("type") != "message" or message.get("subtype") not in _KEPT_SUBTYPES:
        return None
    user_id = message.get("user")
    if not user_id:
        return None
    try:
        occurred_at = parse_ts(message.get("ts"))
        thread_ts = message.get("thread_ts") or message["ts"]
        parse_ts(thread_ts)
    except ValueError as exc:
        raise _invalid(path, f"{name}: {exc}") from exc
    user = users.get(user_id, {})
    profile = message.get("user_profile") or {}
    return RawSignal(
        source="slack",
        source_key=f"{channel.id}:{message['ts']}",
        occurred_at=occurred_at,
        raw_text=message.get("text") or "",
        author_name=user.get("real_name") or profile.get("real_name"),
        thread_key=f"slack:{channel.id}:{thread_ts}",
        slack_channel_id=channel.id,
        slack_channel_name=channel.name,
        author_email=user.get("email"),
        author_team=message.get("user_team") or user.get("team"),
        readable_text=render_text(message.get("text") or "", users),
    )
