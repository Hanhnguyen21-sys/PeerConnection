"""app/campus_time.py agrees with frontend/src/lib/campusTime.js.

The parity tests run the real frontend module in Node (skipped if Node isn't
installed), so the backend and the UI can't drift apart on messages or on
whether a shift has started.
"""
import itertools
import json
import shutil
import subprocess
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import campus_time
from pg import REPO_ROOT

# Captured at import, before the autouse clock fixture replaces it.
REAL_CAMPUS_NOW = campus_time.campus_now
CAMPUS_TIME_JS = REPO_ROOT / "frontend" / "src" / "lib" / "campusTime.js"
NODE = shutil.which("node")


def run_frontend(expression_body, cases):
    """Evaluates ``expression_body`` (JS using the campusTime exports and ``cases``) in Node."""
    script = (
        f"import * as t from {json.dumps(CAMPUS_TIME_JS.as_uri())};\n"
        "const cases = JSON.parse(process.argv[1]);\n"
        f"console.log(JSON.stringify({expression_body}));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script, json.dumps(cases)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def as_shift(day, start, end):
    return {
        "shift_date": date.fromisoformat(day),
        "start_time": time.fromisoformat(start),
        "end_time": time.fromisoformat(end),
    }


DATES = ["2030-01-20", "2026-11-18", "2028-02-29", "2031-12-31", "2027-07-04", "2029-03-11"]
TIMES = [("00:00", "00:30"), ("00:05", "11:59"), ("11:30", "12:00"), ("12:00", "12:01"), ("12:59", "13:00"), ("23:00", "23:59")]


@pytest.mark.skipif(NODE is None, reason="Node.js isn't installed")
def test_formatting_matches_the_frontend():
    cases = [[day, start, end] for day in DATES for start, end in TIMES]

    expected = run_frontend("cases.map(([d, s, e]) => [t.formatDate(d), t.formatTimeRange(s, e)])", cases)

    actual = [
        [campus_time.format_date(date.fromisoformat(d)),
         campus_time.format_time_range(time.fromisoformat(s), time.fromisoformat(e))]
        for d, s, e in cases
    ]
    assert actual == expected


@pytest.mark.skipif(NODE is None, reason="Node.js isn't installed")
def test_started_and_ended_match_the_frontend():
    shift = ("2030-01-20", "10:00", "12:00")
    nows = [
        ("2030-01-19", "23:59"), ("2030-01-20", "09:59"), ("2030-01-20", "10:00"), ("2030-01-20", "10:01"),
        ("2030-01-20", "11:59"), ("2030-01-20", "12:00"), ("2030-01-20", "12:01"), ("2030-01-21", "00:00"),
    ]
    cases = [[*shift, now_date, now_time] for now_date, now_time in nows]

    expected = run_frontend(
        "cases.map(([d, s, e, nd, nt]) => {"
        " const shift = {shift_date: d, start_time: s, end_time: e}, now = {date: nd, time: nt};"
        " return [t.hasShiftStarted(shift, now), t.hasShiftEnded(shift, now)]; })",
        cases,
    )

    actual = []
    for d, s, e, now_date, now_time in cases:
        now = datetime.combine(date.fromisoformat(now_date), time.fromisoformat(now_time))
        actual.append([campus_time.has_shift_started(as_shift(d, s, e), now),
                       campus_time.has_shift_ended(as_shift(d, s, e), now)])
    assert actual == expected


@pytest.mark.skipif(NODE is None, reason="Node.js isn't installed")
def test_overlap_matches_the_frontend():
    times = ["09:00", "10:00", "10:30", "11:00", "12:00"]
    intervals = [(start, end) for start, end in itertools.combinations(times, 2)]
    cases = [
        [day_a, a[0], a[1], day_b, b[0], b[1]]
        for a in intervals for b in intervals
        for day_a, day_b in [("2030-01-20", "2030-01-20"), ("2030-01-20", "2030-01-21")]
    ]

    expected = run_frontend(
        "cases.map(([da, sa, ea, db, sb, eb]) => t.shiftsOverlap("
        "{shift_date: da, start_time: sa, end_time: ea}, {shift_date: db, start_time: sb, end_time: eb}))",
        cases,
    )

    actual = [campus_time.shifts_overlap(as_shift(da, sa, ea), as_shift(db, sb, eb)) for da, sa, ea, db, sb, eb in cases]
    assert actual == expected
    assert any(expected) and not all(expected)


def test_shift_minutes():
    assert campus_time.shift_minutes(as_shift("2030-01-20", "10:00", "12:00")) == 120
    assert campus_time.shift_minutes(as_shift("2030-01-20", "09:15", "09:40")) == 25


def test_campus_now_is_campus_wall_clock_time_to_the_minute():
    before = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
    now = REAL_CAMPUS_NOW()
    after = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)

    assert now.tzinfo is None
    assert now.second == 0 and now.microsecond == 0
    assert before - timedelta(minutes=1) <= now <= after
