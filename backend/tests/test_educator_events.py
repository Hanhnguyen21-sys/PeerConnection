"""Browsing events as a peer educator (educator.py) together with signing up
(registrations.py): the eligibility a shift shows must match what happens
when you try to sign up for it.
"""
import pytest

from helpers import assert_error


def browse(api, user, **params):
    response = api.get("/api/educator/events", user, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def event_detail(api, user, event_id):
    response = api.get(f"/api/educator/events/{event_id}", user)
    assert response.status_code == 200, response.text
    return response.json()


def shown_eligibility(api, user, event_id, shift_id):
    [shift] = [s for s in event_detail(api, user, event_id)["shifts"] if s["shift_id"] == shift_id]
    return shift["eligibility"]


# ---------- Shown eligibility == sign-up outcome ----------

def scenario_open(make, api, me):
    event = make.event()
    return event, make.shift(event)


def scenario_registered(make, api, me):
    event = make.event()
    shift = make.shift(event)
    api.register(me, shift)
    return event, shift


def scenario_registered_other_shift(make, api, me):
    event = make.event()
    api.register(me, make.shift(event, start="08:00", end="09:00"))
    return event, make.shift(event, start="13:00", end="14:00")


def scenario_full(make, api, me):
    event = make.event()
    shift = make.shift(event, capacity=1)
    api.register(make.user(), shift)
    return event, shift


def scenario_conflict(make, api, me):
    api.register(me, make.shift(make.event(title="Tabling"), start="10:00", end="12:00"))
    event = make.event()
    return event, make.shift(event, start="11:00", end="13:00")


def scenario_event_cancelled(make, api, me):
    event = make.event()
    shift = make.shift(event)
    make.cancel_event(event)
    return event, shift


def scenario_closed(make, api, me):
    event = make.event()
    return event, make.shift(event, day="2030-01-15", start="08:00", end="10:00")  # started at 8, now is 9


def scenario_back_to_back(make, api, me):
    api.register(me, make.shift(make.event(), start="10:00", end="12:00"))
    event = make.event()
    return event, make.shift(event, start="12:00", end="13:00")


@pytest.mark.parametrize(
    "scenario,expected",
    [
        (scenario_open, "open"),
        (scenario_registered, "registered"),
        (scenario_registered_other_shift, "registered_other_shift"),
        (scenario_full, "full"),
        (scenario_conflict, "conflict"),
        (scenario_event_cancelled, "event_cancelled"),
        (scenario_closed, "closed"),
        (scenario_back_to_back, "open"),
    ],
)
def test_shown_eligibility_matches_signing_up(api, make, scenario, expected):
    me = make.user()
    event, shift = scenario(make, api, me)

    shown = shown_eligibility(api, me, event, shift)
    response = api.register(me, shift)

    assert shown["code"] == expected
    if expected == "open":
        assert response.status_code == 201, response.text
    else:
        assert_error(response, 409, code=expected)


def test_conflict_details_match(api, make):
    me = make.user()
    other_event = make.event(title="Tabling")
    api.register(me, make.shift(other_event, day="2030-01-20", start="10:00", end="12:00"))
    event = make.event()
    shift = make.shift(event, day="2030-01-20", start="11:00", end="13:00")

    shown = shown_eligibility(api, me, event, shift)

    assert shown["conflict"] == {
        "event_id": other_event, "title": "Tabling",
        "shift_date": "2030-01-20", "start_time": "10:00", "end_time": "12:00",
    }
    assert "Tabling on Sun, Jan 20, 2030, 10:00 AM – 12:00 PM PT" in api.register(me, shift).json()["detail"]


def test_registered_shows_the_registration_id(api, make):
    me = make.user()
    event = make.event()
    shift = make.shift(event)
    registration_id = api.register(me, shift).json()["registration_id"]

    detail = event_detail(api, me, event)

    assert detail["my_registration"] == {"registration_id": registration_id, "shift_id": shift}
    assert detail["shifts"][0]["eligibility"] == {"code": "registered", "registration_id": registration_id}


def test_cancelling_reopens_the_shift_in_the_listing(api, make):
    me = make.user()
    event = make.event()
    shift = make.shift(event, capacity=1)
    registration_id = api.register(me, shift).json()["registration_id"]
    assert shown_eligibility(api, make.user(), event, shift)["code"] == "full"

    api.cancel(me, registration_id)

    assert shown_eligibility(api, make.user(), event, shift)["code"] == "open"
    assert shown_eligibility(api, me, event, shift)["code"] == "open"


# ---------- Listing ----------

def test_listing_counts_sign_ups_and_shows_mine(api, make):
    me = make.user()
    event = make.event(title="Wellness Fair")
    morning = make.shift(event, start="09:00", end="10:00", capacity=2)
    make.shift(event, start="13:00", end="14:00", capacity=3)
    api.register(me, morning)
    api.register(make.user(), morning)

    [listed] = browse(api, me)

    assert listed["title"] == "Wellness Fair"
    assert listed["remaining_spots"] == 3
    assert listed["open_shift_count"] == 1
    assert listed["my_registration"]["shift_id"] == morning
    assert browse(api, me, availability="open")[0]["event_id"] == event


def test_listing_hides_drafts_cancelled_and_started_events(api, make):
    make.shift(make.event(status="draft"))
    make.shift(make.event(status="cancelled"))
    make.shift(make.event(), day="2030-01-15", start="08:00", end="10:00")
    visible = make.event(title="Visible")
    make.shift(visible)

    assert [item["title"] for item in browse(api, make.user())] == ["Visible"]


def test_full_events_are_left_out_of_open_availability(api, make):
    event = make.event()
    shift = make.shift(event, capacity=1)
    api.register(make.user(), shift)
    viewer = make.user()

    assert [item["event_id"] for item in browse(api, viewer)] == [event]
    assert browse(api, viewer, availability="open") == []


def test_drafts_are_404(api, make):
    event = make.event(status="draft")
    make.shift(event)
    assert_error(api.get(f"/api/educator/events/{event}", make.user()), 404)


def test_supervisors_get_403(api, make):
    supervisor = make.supervisor()
    assert_error(api.get("/api/educator/events", supervisor), 403)
    assert_error(api.get(f"/api/educator/events/{make.event()}", supervisor), 403)
