"""Configuration from pulse.toml, with defaults that work without one."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from customer_pulse.errors import PulseError

CONFIG_FILE_NAME = "pulse.toml"
DATABASE_FILE_NAME = "pulse.db"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_STATE_DIR = ".pulse"

# Every key Pulse understands, by table. Unknown keys are errors, so a typo can't silently
# fall back to a default. Later sessions add tables here as features arrive.
_KNOWN_KEYS: dict[str, set[str]] = {"pulse": {"timezone", "state_dir"}}


@dataclass(frozen=True)
class Config:
    file: Path | None
    timezone: ZoneInfo
    state_dir: Path

    @property
    def db_path(self) -> Path:
        return self.state_dir / DATABASE_FILE_NAME


def load_config(explicit: Path | None, cwd: Path) -> Config:
    """Load ``explicit`` if given, else ``pulse.toml`` in ``cwd`` if present, else defaults.

    Relative paths in the file resolve against the file's own directory, so a config file
    behaves the same from any working directory.
    """
    path: Path | None
    if explicit is not None:
        path = explicit.expanduser()
        if not path.is_file():
            raise PulseError("config_not_found", f"config file {path} does not exist")
    else:
        candidate = cwd / CONFIG_FILE_NAME
        path = candidate if candidate.is_file() else None

    data = _read(path) if path else {}
    _check_keys(data, path)
    section = data.get("pulse", {})
    base = path.parent.resolve() if path else cwd.resolve()
    return Config(
        file=path.resolve() if path else None,
        timezone=_timezone(section.get("timezone", DEFAULT_TIMEZONE), path),
        state_dir=_state_dir(section.get("state_dir", DEFAULT_STATE_DIR), base, path),
    )


def _where(path: Path | None) -> str:
    return f"{path}: " if path else ""


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise PulseError("invalid_config", f"{path} is not valid TOML: {exc}") from exc


def _check_keys(data: dict[str, Any], path: Path | None) -> None:
    for table, value in data.items():
        if table not in _KNOWN_KEYS:
            raise PulseError(
                "invalid_config",
                f"{_where(path)}unknown table or key {table!r}",
                hint=f"known tables: {', '.join(sorted(_KNOWN_KEYS))}",
            )
        if not isinstance(value, dict):
            raise PulseError("invalid_config", f"{_where(path)}[{table}] must be a table")
        unknown = sorted(set(value) - _KNOWN_KEYS[table])
        if unknown:
            raise PulseError(
                "invalid_config",
                f"{_where(path)}unknown key(s) in [{table}]: {', '.join(unknown)}",
                hint=f"known keys: {', '.join(sorted(_KNOWN_KEYS[table]))}",
            )


def _timezone(name: Any, path: Path | None) -> ZoneInfo:
    if not isinstance(name, str) or not name:
        raise PulseError(
            "invalid_config",
            f"{_where(path)}pulse.timezone must be an IANA timezone name",
            hint="for example America/Los_Angeles or UTC",
        )
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PulseError(
            "invalid_config",
            f"{_where(path)}unknown timezone {name!r}",
            hint="use an IANA name such as America/Los_Angeles or UTC",
        ) from exc


def _state_dir(value: Any, base: Path, path: Path | None) -> Path:
    if not isinstance(value, str) or not value:
        raise PulseError("invalid_config", f"{_where(path)}pulse.state_dir must be a path")
    return (base / Path(value).expanduser()).resolve()
