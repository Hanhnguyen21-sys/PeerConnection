"""Campus-time helpers, matching frontend/src/lib/campusTime.js.

Shift dates and times are wall-clock values in America/Los_Angeles. "Now" is
truncated to the minute, like the frontend, so the backend and the UI agree on
whether a shift has started.

Call these through the module (``campus_time.campus_now()``) so tests can
replace the clock.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

CAMPUS_TIME_ZONE = ZoneInfo("America/Los_Angeles")


def campus_now() -> datetime:
    """Current campus wall-clock time as a naive datetime, to the minute."""
    return datetime.now(CAMPUS_TIME_ZONE).replace(tzinfo=None, second=0, microsecond=0)


def shift_start(shift) -> datetime:
    return datetime.combine(shift["shift_date"], shift["start_time"])


def shift_end(shift) -> datetime:
    return datetime.combine(shift["shift_date"], shift["end_time"])


def has_shift_started(shift, now: datetime) -> bool:
    return shift_start(shift) <= now


def has_shift_ended(shift, now: datetime) -> bool:
    return shift_end(shift) <= now


def shifts_overlap(a, b) -> bool:
    """Same-day intervals overlap when a starts before b ends and ends after b starts.

    Back-to-back shifts (10:00-11:00 and 11:00-12:00) do not overlap.
    """
    return (
        a["shift_date"] == b["shift_date"]
        and a["start_time"] < b["end_time"]
        and a["end_time"] > b["start_time"]
    )


def shift_minutes(shift) -> int:
    return int((shift_end(shift) - shift_start(shift)).total_seconds() // 60)


# ---------- Formatting (same output as formatDate / formatTimeRange in campusTime.js) ----------

# Spelled out so the output doesn't depend on the server's locale.
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_date(value: date) -> str:
    """'Tue, Jan 15, 2030'"""
    return f"{WEEKDAYS[value.weekday()]}, {MONTHS[value.month - 1]} {value.day}, {value.year}"


def format_time(value: time) -> str:
    """'9:05 AM'"""
    suffix = "PM" if value.hour >= 12 else "AM"
    return f"{value.hour % 12 or 12}:{value.minute:02d} {suffix}"


def format_time_range(start: time, end: time) -> str:
    """'9:00 AM – 11:00 AM PT'"""
    return f"{format_time(start)} – {format_time(end)} PT"


def iso_date(value: date) -> str:
    return value.isoformat()


def hh_mm(value: time) -> str:
    return value.strftime("%H:%M")
