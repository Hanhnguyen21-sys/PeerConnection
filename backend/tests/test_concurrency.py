"""Concurrent requests against a real Postgres: no overbooking, no double
booking, no deadlocks, and nothing written to an event after it's cancelled.

Each test starts many sign-ups at the same moment (threading.Barrier), each in
its own database transaction. ``slow_clock`` makes every sign-up pause *inside*
its transaction, after reading the counts and before inserting, so without the
row locks the requests would all see the same counts and the tests would fail.
The test cluster records commit timestamps, so tests can also check the order
transactions committed in.
"""
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn
from fastapi import HTTPException

from app import campus_time
from app.errors import ApiError
from app.main import app
from app.routes import attendance, events, registrations, users
from helpers import DEFAULT_NOW, fake_authenticated_user_id, free_port

DURING_THE_SHIFT = datetime(2030, 1, 20, 11, 0)  # the factory's default shift is 10:00-12:00 that day


def use_slow_clock(monkeypatch, now):
    def slow_now():
        time.sleep(0.05)
        return now

    monkeypatch.setattr(campus_time, "campus_now", slow_now)


@pytest.fixture
def slow_clock(monkeypatch):
    use_slow_clock(monkeypatch, DEFAULT_NOW)


def committed_after_cancellation(make, table, event_id):
    """Rows of ``table`` for the event whose transaction committed after the event's cancellation."""
    join = {
        "registrations": "registrations.event_id = events.event_id",
        "attendance": "attendance.registration_id IN (SELECT registration_id FROM public.registrations"
                      " WHERE registrations.event_id = events.event_id)",
    }[table]
    return make.one(
        f"""
        SELECT COUNT(*)::int AS n
        FROM public.{table}, public.events
        WHERE events.event_id = %s AND {join}
          AND pg_xact_commit_timestamp({table}.xmin) > pg_xact_commit_timestamp(events.xmin)
        """,
        (event_id,),
    )["n"]


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
    commits before the cancellation or is refused with event_cancelled."""
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
    assert committed_after_cancellation(make, "registrations", event) == 0


def test_attendance_while_the_supervisor_cancels_the_event(make, monkeypatch):
    """Marks commit before the cancellation or are refused; cancelled events stay read-only."""
    supervisor = make.supervisor()
    event = make.event(organizer=supervisor)
    shift = make.shift(event, capacity=20)
    registration_ids = [make.registration(make.user(), shift) for _ in range(10)]
    use_slow_clock(monkeypatch, DURING_THE_SHIFT)

    def mark(registration_id):
        body = attendance.AttendanceInput(participation_status="attended")
        return lambda: attendance.record_attendance(registration_id, body, user_id=supervisor)

    def cancel():
        events.cancel_event(event, user_id=supervisor)

    *results, _ = race([mark(registration_id) for registration_id in registration_ids] + [cancel])

    assert set(results) <= {"created", "This event was cancelled, so attendance can't be changed."}
    assert results.count("created") == make.one("SELECT COUNT(*)::int AS n FROM public.attendance")["n"]
    assert committed_after_cancellation(make, "attendance", event) == 0


def test_marking_one_registration_many_times_at_once(make, monkeypatch):
    """Single and whole-shift marks racing on the same registration leave exactly one record."""
    supervisor = make.supervisor()
    shift = make.shift()
    registration_id = make.registration(make.user(), shift)
    use_slow_clock(monkeypatch, DURING_THE_SHIFT)

    def single(status):
        body = attendance.AttendanceInput(participation_status=status)
        return lambda: attendance.record_attendance(registration_id, body, user_id=supervisor)

    def whole_shift(status):
        body = attendance.RosterInput(records=[{"registration_id": registration_id, "participation_status": status}])
        return lambda: attendance.record_shift_attendance(shift, body, user_id=supervisor)

    results = race([single("attended"), single("absent")] * 4 + [whole_shift("attended"), whole_shift("absent")] * 2)

    assert set(results) == {"created"}
    rows = make.all("SELECT participation_status, credited_minutes FROM public.attendance")
    assert len(rows) == 1
    assert rows[0] in ({"participation_status": "attended", "credited_minutes": 120},
                       {"participation_status": "absent", "credited_minutes": 0})


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


# ---------- Roles ----------

def change_role(actor, target, role):
    return lambda: users.set_user_role(target, users.RoleInput(role=role), user_id=actor)


def supervisor_count(make):
    return make.one("SELECT COUNT(*)::int AS n FROM public.users WHERE role = 'supervisor'")["n"]


@pytest.mark.parametrize("attempt", range(3))
def test_two_supervisors_demoting_each_other_leave_one(make, slow_clock, attempt):
    first, second = make.supervisor(), make.supervisor()

    results = race([change_role(first, second, "peer_educator"), change_role(second, first, "peer_educator")])

    assert sorted(results) == ["created", "forbidden"]
    assert supervisor_count(make) == 1


def test_a_ring_of_supervisors_demoting_each_other_never_removes_them_all(make, slow_clock):
    """Each supervisor demotes the next one. Every call succeeding would need each
    to run before the one demoting it, which is a cycle, so at least one remains."""
    supervisors = [make.supervisor() for _ in range(6)]
    calls = [
        change_role(actor, supervisors[(index + 1) % len(supervisors)], "peer_educator")
        for index, actor in enumerate(supervisors)
    ]

    results = race(calls)

    remaining = supervisor_count(make)
    assert remaining >= 1
    assert results.count("created") == len(supervisors) - remaining
    assert results.count("forbidden") == remaining


def test_promoting_someone_while_they_sign_up(make, slow_clock):
    """Either the promotion wins and the sign-up is refused, or the sign-up wins
    and the promotion is refused. Never a supervisor holding a spot."""
    supervisor, educator, shift = make.supervisor(), make.user(), make.shift()

    def sign_up_call():
        try:
            registrations.register_for_shift(shift, user_id=educator)
        except HTTPException as error:  # require_peer_educator's 403
            raise ApiError(error.status_code, error.detail, code="not_peer_educator")

    results = race([change_role(supervisor, educator, "supervisor"), sign_up_call])

    role = make.one("SELECT role FROM public.users WHERE user_id = %s", (educator,))["role"]
    if role == "supervisor":
        assert results == ["created", "not_peer_educator"]
        assert active_count(make, user_id=educator) == 0
    else:
        assert results == ["has_registrations", "created"]
        assert active_count(make, user_id=educator) == 1
