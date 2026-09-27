from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from customer_pulse.clock import FixedClock, SystemClock, clock_from_env
from customer_pulse.errors import PulseError
from customer_pulse.timewin import (
    Window,
    from_db,
    local_day_start,
    parse_instant,
    to_db,
)

LA = ZoneInfo("America/Los_Angeles")
MICRO = timedelta(microseconds=1)


def utc(text: str) -> datetime:
    return parse_instant(text)


# Stored text


def test_stored_text_is_fixed_width_utc_and_round_trips():
    instant = datetime(2026, 10, 5, 9, 30, 1, 42, tzinfo=LA)
    text = to_db(instant)
    assert text == "2026-10-05T16:30:01.000042Z"
    assert len(text) == 27
    assert from_db(text) == instant


def test_stored_text_sorts_like_time():
    instants = [
        utc("2026-10-05T09:00:00.000001Z"),
        utc("2026-10-05T09:00:00Z"),
        utc("2025-12-31T23:59:59.999999Z"),
        utc("2026-10-05T08:59:59.500000-07:00"),
        utc("2026-01-10T00:00:00Z"),
    ]
    assert sorted(to_db(i) for i in instants) == [to_db(i) for i in sorted(instants)]


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        to_db(datetime(2026, 10, 5, 9, 0))
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_instant("2026-10-05T09:00:00")


def test_malformed_stored_text_is_rejected():
    with pytest.raises(ValueError, match="stored UTC timestamp"):
        from_db("2026-10-05 09:00:00")


def test_instants_accept_z_and_offsets():
    assert parse_instant("2026-10-05T16:00:00Z") == parse_instant("2026-10-05T09:00:00-07:00")


# Window edges and cutoffs


def test_start_edge_is_included_and_end_edge_is_excluded():
    window = Window.parse("2026-10-05..2026-10-11", LA)
    assert window.start == utc("2026-10-05T07:00:00Z")
    assert window.end == utc("2026-10-12T07:00:00Z")
    assert window.contains(window.start)
    assert not window.contains(window.start - MICRO)
    assert window.contains(window.end - MICRO)
    assert not window.contains(window.end)


def test_cutoff_defaults_to_the_window_end():
    window = Window.parse("2026-10-05..2026-10-11", LA)
    assert window.cutoff == window.end


def test_an_earlier_cutoff_bounds_the_evidence():
    cutoff = utc("2026-10-09T17:00:00Z")
    window = Window.parse("2026-10-05..2026-10-11", LA, cutoff=cutoff)
    assert window.contains(cutoff - MICRO)
    assert not window.contains(cutoff)
    assert not window.contains(window.end - MICRO)


@pytest.mark.parametrize(
    "cutoff",
    [
        "2026-10-05T07:00:00Z",  # at the start: the evidence range would be empty
        "2026-10-12T07:00:00.000001Z",  # after the end
    ],
)
def test_cutoff_must_sit_inside_the_window(cutoff):
    with pytest.raises(ValueError, match="cutoff"):
        Window.parse("2026-10-05..2026-10-11", LA, cutoff=utc(cutoff))


def test_windows_reject_naive_instants_and_reversed_days():
    with pytest.raises(ValueError, match="timezone-aware"):
        Window.parse("2026-10-05..2026-10-11", LA).contains(datetime(2026, 10, 6))
    with pytest.raises(ValueError, match="before first day"):
        Window.parse("2026-10-11..2026-10-05", LA)


@pytest.mark.parametrize(
    "spec", ["2026-10-05", "2026-10-05...2026-10-11", "2026-02-30..2026-03-01"]
)
def test_window_specs_are_validated(spec):
    with pytest.raises(ValueError):  # noqa: PT011 - the message differs per case
        Window.parse(spec, LA)


# Daylight saving


def test_fall_back_week_is_169_hours():
    # Los Angeles leaves daylight time at 02:00 on Sunday 2026-11-01.
    window = Window.parse("2026-10-26..2026-11-01", LA)
    assert window.start == utc("2026-10-26T07:00:00Z")
    assert window.end == utc("2026-11-02T08:00:00Z")
    assert window.end - window.start == timedelta(hours=169)
    assert window.contains(utc("2026-11-01T09:30:00Z"))  # 01:30 PST, the repeated hour


def test_spring_forward_week_is_167_hours():
    # Los Angeles enters daylight time at 02:00 on Sunday 2026-03-08.
    window = Window.parse("2026-03-02..2026-03-08", LA)
    assert window.start == utc("2026-03-02T08:00:00Z")
    assert window.end == utc("2026-03-09T07:00:00Z")
    assert window.end - window.start == timedelta(hours=167)


def test_a_day_whose_midnight_is_skipped_starts_at_the_jump():
    # Sao Paulo skipped 00:00-01:00 local on 2018-11-04; that day began at 01:00 (-02:00).
    start = local_day_start(date(2018, 11, 4), ZoneInfo("America/Sao_Paulo"))
    assert start == utc("2018-11-04T03:00:00Z")


def test_labels_and_local_days_round_trip():
    window = Window.parse("2026-10-26..2026-11-01", LA)
    assert (window.first_day, window.last_day) == (date(2026, 10, 26), date(2026, 11, 1))
    assert window.label == "2026-10-26..2026-11-01"


def test_previous_window_covers_the_same_number_of_local_days():
    window = Window.parse("2026-11-02..2026-11-08", LA)
    previous = window.previous()
    assert previous.label == "2026-10-26..2026-11-01"
    assert previous.end == window.start
    assert previous.cutoff == previous.end


def test_windows_normalize_their_instants_to_utc():
    window = Window(
        start=datetime(2026, 10, 5, 7, tzinfo=UTC),
        end=datetime(2026, 10, 5, 13, tzinfo=timezone(timedelta(hours=3))),  # 10:00 UTC
        cutoff=datetime(2026, 10, 5, 7, 30, tzinfo=UTC),
        tz=LA,
    )
    assert window.end == utc("2026-10-05T10:00:00Z")
    assert window.end.tzinfo is UTC


# Clock


def test_fixed_clock_returns_its_instant_in_utc():
    clock = FixedClock(datetime(2026, 10, 12, 10, tzinfo=LA))
    assert clock.now() == utc("2026-10-12T17:00:00Z")
    assert clock.now().tzinfo is UTC


def test_fixed_clock_rejects_naive_instants():
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 10, 12, 10))


def test_clock_comes_from_the_environment_when_pinned():
    assert isinstance(clock_from_env({}), SystemClock)
    pinned = clock_from_env({"PULSE_NOW": "2026-10-12T17:00:00Z"})
    assert pinned.now() == utc("2026-10-12T17:00:00Z")


def test_a_bad_pinned_clock_is_a_clear_error():
    with pytest.raises(PulseError) as caught:
        clock_from_env({"PULSE_NOW": "tomorrow"})
    assert caught.value.code == "invalid_clock"
