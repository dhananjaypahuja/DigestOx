"""The time model: UTC storage, a configured timezone, half-open windows, and cutoffs.

Every stored timestamp is UTC text in one fixed-width form, ``YYYY-MM-DDTHH:MM:SS.ffffffZ``,
so text order is time order and SQL can compare timestamps as plain text.

A digest window covers whole local calendar days in the configured timezone. It is stored as
the half-open UTC range ``[start, end)``. Evidence counts only when ``start <= t < cutoff``;
the cutoff defaults to the window end and may be earlier, never later. Nothing at or after
the cutoff can influence a digest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_DB_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_DB_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
_WINDOW_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})")


def to_utc(instant: datetime, what: str = "timestamp") -> datetime:
    """Return ``instant`` in UTC. Naive datetimes are rejected, never guessed."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware, got {instant!r}")
    return instant.astimezone(UTC)


def to_db(instant: datetime) -> str:
    """Format an aware datetime as the fixed-width UTC text stored in the database."""
    utc = to_utc(instant)
    if utc.year < 1000:
        raise ValueError(f"year {utc.year} can't be stored in fixed-width form")
    return utc.strftime(_DB_FORMAT)


def from_db(text: str) -> datetime:
    """Parse stored UTC text back into an aware datetime."""
    if not _DB_PATTERN.fullmatch(text):
        raise ValueError(f"not a stored UTC timestamp: {text!r}")
    return datetime.strptime(text, _DB_FORMAT).replace(tzinfo=UTC)


def parse_instant(text: str) -> datetime:
    """Parse an ISO 8601 instant that carries an explicit offset or ``Z``."""
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"not an ISO 8601 instant: {text!r}") from exc
    return to_utc(value, f"instant {text!r}")


def local_day_start(day: date, tz: ZoneInfo) -> datetime:
    """Return the first UTC instant whose local date in ``tz`` is ``day``.

    That is local midnight on almost every day. When a daylight-saving jump skips midnight,
    the day starts at the jump instead; when midnight repeats, it starts at the first one.
    """
    starts = []
    for fold in (0, 1):
        candidate = datetime.combine(day, time(), tzinfo=tz).replace(fold=fold).astimezone(UTC)
        if candidate.astimezone(tz).date() == day:
            starts.append(candidate)
    if not starts:  # no real timezone skips a whole day at midnight, but don't guess
        raise ValueError(f"{day} has no local midnight in {tz.key}")
    return min(starts)


@dataclass(frozen=True)
class Window:
    """A half-open UTC range ``[start, end)`` with a cutoff inside it.

    Evidence counts when ``start <= t < cutoff``. Build windows from local days with
    :meth:`for_local_days` or :meth:`parse`; construct one directly only from UTC instants.
    """

    start: datetime
    end: datetime
    cutoff: datetime
    tz: ZoneInfo

    def __post_init__(self) -> None:
        for name in ("start", "end", "cutoff"):
            object.__setattr__(self, name, to_utc(getattr(self, name), f"window {name}"))
        if not self.start < self.end:
            raise ValueError(f"window start {self.start} must be before its end {self.end}")
        if not self.start < self.cutoff <= self.end:
            raise ValueError(
                f"cutoff {self.cutoff} must be after the window start {self.start} "
                f"and no later than its end {self.end}"
            )

    @classmethod
    def for_local_days(
        cls, first: date, last: date, tz: ZoneInfo, cutoff: datetime | None = None
    ) -> Window:
        """Cover the local calendar days ``first`` through ``last``, both inclusive."""
        if last < first:
            raise ValueError(f"last day {last} is before first day {first}")
        start = local_day_start(first, tz)
        end = local_day_start(last + timedelta(days=1), tz)
        return cls(start=start, end=end, cutoff=end if cutoff is None else cutoff, tz=tz)

    @classmethod
    def parse(cls, spec: str, tz: ZoneInfo, cutoff: datetime | None = None) -> Window:
        """Parse ``YYYY-MM-DD..YYYY-MM-DD``: local calendar days, both inclusive."""
        match = _WINDOW_PATTERN.fullmatch(spec.strip())
        if not match:
            raise ValueError(f"window must look like 2026-10-05..2026-10-11, got {spec!r}")
        first, last = (date.fromisoformat(part) for part in match.groups())
        return cls.for_local_days(first, last, tz, cutoff)

    @property
    def first_day(self) -> date:
        """The first local calendar day the window covers."""
        return self.start.astimezone(self.tz).date()

    @property
    def last_day(self) -> date:
        """The last local calendar day the window covers."""
        return (self.end - timedelta(microseconds=1)).astimezone(self.tz).date()

    @property
    def label(self) -> str:
        return f"{self.first_day.isoformat()}..{self.last_day.isoformat()}"

    def contains(self, instant: datetime) -> bool:
        """True when ``instant`` counts as evidence: ``start <= instant < cutoff``."""
        moment = to_utc(instant)
        return self.start <= moment < self.cutoff

    def previous(self) -> Window:
        """The window of the same number of local days immediately before this one."""
        days = (self.last_day - self.first_day).days + 1
        return Window.for_local_days(
            self.first_day - timedelta(days=days), self.first_day - timedelta(days=1), self.tz
        )
