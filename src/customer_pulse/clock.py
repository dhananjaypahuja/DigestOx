"""Where Pulse gets "now". Tests and demos pin it so runs are reproducible."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from customer_pulse.errors import PulseError
from customer_pulse.timewin import parse_instant, to_utc

CLOCK_ENV = "PULSE_NOW"


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current instant as an aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class FixedClock:
    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", to_utc(self.instant, "fixed clock instant"))

    def now(self) -> datetime:
        return self.instant


def clock_from_env(environ: Mapping[str, str]) -> Clock:
    """Use the instant in ``PULSE_NOW`` when it is set, otherwise the system clock."""
    value = environ.get(CLOCK_ENV)
    if not value:
        return SystemClock()
    try:
        return FixedClock(parse_instant(value))
    except ValueError as exc:
        raise PulseError(
            "invalid_clock",
            f"{CLOCK_ENV} must be an ISO 8601 instant with an offset, got {value!r}",
            hint="for example 2026-10-12T17:00:00Z",
        ) from exc
