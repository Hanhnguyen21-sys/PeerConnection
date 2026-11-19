"""Concurrent sign-ups against a real Postgres: no overbooking, no double booking.

Each test starts many sign-ups at the same moment (threading.Barrier), each in
its own database transaction. ``slow_clock`` makes every sign-up pause *inside*
its transaction, after reading the counts and before inserting, so without the
row locks the requests would all see the same counts and the tests would fail.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn

from app import campus_time
from app.errors import ApiError
from app.main import app
from app.routes import registrations
from app.routes import events
from helpers import DEFAULT_NOW, fake_authenticated_user_id, free_port


@pytest.fixture
def slow_clock(monkeypatch):
    def slow_now():
        time.sleep(0.05)
        return DEFAULT_NOW

    monkeypatch.setattr(campus_time, "campus_now", slow_now)


def race(calls):
    """Runs the calls at the same moment and returns each one's result code."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait()
        try:
            call()
            return "created"
        except ApiError as error:
            return error.code or error.message

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls, timeout=60))


def sign_up(user_id, shift_id):
    return lambda: registrations.register_for_shift(shift_id, user_id=user_id)


def active_count(make, shift_id=None, user_id=None):
    return make.one(
        """
        SELECT COUNT(*)::int AS n FROM public.registrations
        WHERE status = 'active'
          AND (%(shift)s::bigint IS NULL OR shift_id = %(shift)s::bigint)
          AND (%(user)s::uuid IS NULL OR user_id = %(user)s::uuid)
        """,
        {"shift": shift_id, "user": user_id},
    )["n"]


def test_many_people_racing_for_the_last_spots(make, slow_clock):
    shift = make.shift(capacity=3)
    people = [make.user() for _ in range(20)]

    results = race([sign_up(person, shift) for person in people])

    assert results.count("created") == 3
    assert results.count("full") == 17
    assert active_count(make, shift_id=shift) == 3


def test_one_person_racing_for_overlapping_shifts_in_different_events(make, slow_clock):
    educator = make.user()
    shifts = [make.shift(make.event(), day="2030-01-20", start="10:00", end="12:00") for _ in range(6)]

    results = race([sign_up(educator, shift) for shift in shifts])

    assert results.count("created") == 1
    assert results.count("conflict") == 5
    assert active_count(make, user_id=educator) == 1


def test_one_person_racing_for_several_shifts_in_one_event(make, slow_clock):
    educator, event = make.user(), make.event()
    shifts = [make.shift(event, day=f"2030-01-{20 + index}") for index in range(6)]

    results = race([sign_up(educator, shift) for shift in shifts])

    assert results.count("created") == 1
    assert results.count("registered_other_shift") == 5
    assert active_count(make, user_id=educator) == 1


def test_double_clicking_sign_up(make, slow_clock):
    educator, shift = make.user(), make.shift()

    results = race([sign_up(educator, shift) for _ in range(8)])

    assert results.count("created") == 1
    assert results.count("registered") == 7
    assert active_count(make) == 1


def test_mixed_crowd_never_exceeds_any_capacity(make, slow_clock):
    events = [make.event() for _ in range(3)]
    shifts = [make.shift(event, start="10:00", end="12:00", capacity=2) for event in events]
    people = [make.user() for _ in range(8)]
    # Everyone tries every shift. All three overlap, so each person can hold at most one.
    calls = [sign_up(person, shift) for person in people for shift in shifts]

    race(calls)

    for shift in shifts:
        assert active_count(make, shift_id=shift) <= 2
    for person in people:
        assert active_count(make, user_id=person) <= 1
    assert active_count(make) == 6  # every spot gets filled


def test_sign_ups_while_the_supervisor_cancels_the_event(make, slow_clock):
    """Uses the real cancel_event. Nothing deadlocks, and every sign-up either
    lands before the cancellation or is refused with event_cancelled."""
    supervisor = make.supervisor()
    event = make.event(organizer=supervisor)
    shift = make.shift(event, capacity=50)
    people = [make.user() for _ in range(12)]

    def cancel():
        events.cancel_event(event, user_id=supervisor)

    *results, _ = race([sign_up(person, shift) for person in people] + [cancel])

    assert results.count("created") + results.count("event_cancelled") == 12
    assert results.count("created") == active_count(make, shift_id=shift)
    assert make.one("SELECT status FROM public.events WHERE event_id = %s", (event,))["status"] == "cancelled"


def test_sign_ups_while_the_supervisor_lowers_capacity(make, slow_clock):
    """Uses the real update_event. It locks the event and then its shifts, the same
    order as a sign-up, so the two never deadlock and capacity always holds."""
    supervisor = make.supervisor()
    event = make.event(organizer=supervisor, title="Tabling")
    location = make.location()
    shift = make.shift(event, day="2030-01-20", start="10:00", end="12:00", capacity=10, location=location)
    people = [make.user() for _ in range(12)]
    outcome = {}

    def lower_capacity():
        try:
            events.update_event(event, events.EventInput(
                title="Tabling", description="", is_urgent=False,
                shifts=[events.ShiftInput(shift_id=shift, shift_date="2030-01-20", start_time="10:00",
                                          end_time="12:00", location_id=location, capacity=4)],
            ), user_id=supervisor)
            outcome["update"] = "saved"
        except ApiError as error:
            outcome["update"] = error.status_code  # 422 when more than 4 had already signed up

    *results, _ = race([sign_up(person, shift) for person in people] + [lower_capacity])

    assert set(results) <= {"created", "full"}
    capacity = make.one("SELECT capacity FROM public.shifts WHERE shift_id = %s", (shift,))["capacity"]
    assert capacity == (4 if outcome["update"] == "saved" else 10)
    assert active_count(make, shift_id=shift) <= capacity
    assert active_count(make, shift_id=shift) == results.count("created")


def test_over_http_with_a_real_server(make, monkeypatch):
    """The same race through uvicorn and real HTTP requests."""
    from app.auth import get_authenticated_user_id

    monkeypatch.setitem(app.dependency_overrides, get_authenticated_user_id, fake_authenticated_user_id)
    shift = make.shift(capacity=2)
    people = [make.user() for _ in range(15)]

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "uvicorn didn't start"
            time.sleep(0.02)

        barrier = threading.Barrier(len(people))

        def post(person):
            barrier.wait()
            response = httpx.post(
                f"http://127.0.0.1:{port}/api/shifts/{shift}/registrations",
                headers={"Authorization": f"Bearer {person}"},
                timeout=30,
            )
            return response.status_code, response.json().get("code")

        with ThreadPoolExecutor(max_workers=len(people)) as pool:
            results = list(pool.map(post, people))
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    assert results.count((201, None)) == 2
    assert results.count((409, "full")) == 13
    assert active_count(make, shift_id=shift) == 2
