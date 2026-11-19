"""Sign up, cancel, and "my registrations" (POST /api/shifts/{id}/registrations,
POST /api/registrations/{id}/cancel, GET /api/me/registrations).

The expected behaviour comes from API_CONTRACT.md and mockEventService.js.
The clock is frozen at Tue, Jan 15, 2030, 9:00 AM campus time (see conftest).
"""
from datetime import datetime

import psycopg
import pytest

from helpers import assert_error

# Key sets of MyRegistration, as built by registrationDetail in mockEventService.js,
# plus "attendance" (added by this backend).
REGISTRATION_KEYS = {
    "registration_id", "status", "category", "can_cancel", "created_at", "cancelled_at",
    "event", "shift", "location", "attendance",
}
EVENT_KEYS = {"event_id", "title", "status", "is_urgent", "cancelled_at"}
SHIFT_KEYS = {"shift_id", "shift_date", "start_time", "end_time"}
LOCATION_KEYS = {"location_id", "building", "room_or_area", "directions", "map_url"}



# ---------- Signing up ----------

class TestRegister:
    def test_creates_an_active_registration_with_the_contract_shape(self, api, make):
        educator = make.user()
        location = make.location(building="MLK Library", room_or_area="Room 225",
                                 directions="2nd floor", map_url="https://maps.example/mlk")
        event = make.event(title="Wellness Fair", is_urgent=True)
        shift = make.shift(event, day="2030-01-20", start="10:00", end="12:00", location=location)

        response = api.register(educator, shift)

        assert response.status_code == 201, response.text
        body = response.json()
        assert set(body) == REGISTRATION_KEYS
        assert set(body["event"]) == EVENT_KEYS
        assert set(body["shift"]) == SHIFT_KEYS
        assert set(body["location"]) == LOCATION_KEYS
        assert body["status"] == "active"
        assert body["category"] == "upcoming"
        assert body["can_cancel"] is True
        assert body["cancelled_at"] is None
        assert body["attendance"] is None
        assert body["event"] == {
            "event_id": event, "title": "Wellness Fair", "status": "published",
            "is_urgent": True, "cancelled_at": None,
        }
        assert body["shift"] == {
            "shift_id": shift, "shift_date": "2030-01-20", "start_time": "10:00", "end_time": "12:00",
        }
        assert body["location"] == {
            "location_id": location, "building": "MLK Library", "room_or_area": "Room 225",
            "directions": "2nd floor", "map_url": "https://maps.example/mlk",
        }
        datetime.fromisoformat(body["created_at"])  # a real ISO timestamp

    def test_stores_the_shifts_event_on_the_registration(self, api, make):
        educator = make.user()
        event = make.event()
        shift = make.shift(event)

        registration_id = api.register(educator, shift).json()["registration_id"]

        row = make.one("SELECT * FROM public.registrations WHERE registration_id = %s", (registration_id,))
        assert row["event_id"] == event
        assert row["shift_id"] == shift
        assert row["user_id"] == educator
        assert row["status"] == "active"
        assert row["cancelled_at"] is None

    def test_requires_a_token(self, api, make):
        shift = make.shift()
        assert_error(api.post(f"/api/shifts/{shift}/registrations"), 401)

    def test_supervisors_cannot_register(self, api, make):
        shift = make.shift()
        assert_error(api.register(make.supervisor(), shift), 403,
                     detail="Only peer educators can register for shifts")

    def test_a_signed_in_user_without_a_profile_is_forbidden(self, api, make):
        from uuid import uuid4

        assert_error(api.register(uuid4(), make.shift()), 403)

    def test_unknown_shift_is_404(self, api, make):
        assert_error(api.register(make.user(), 999999), 404, detail="Shift not found.")

    def test_draft_events_are_hidden(self, api, make):
        shift = make.shift(make.event(status="draft"))
        assert_error(api.register(make.user(), shift), 404, detail="Shift not found.")

    def test_cancelled_event(self, api, make):
        shift = make.shift(make.event(status="cancelled"))
        assert_error(api.register(make.user(), shift), 409, code="event_cancelled",
                     detail="This event was cancelled, so registration is closed.")

    @pytest.mark.parametrize(
        "now",
        [
            datetime(2030, 1, 20, 10, 0),   # exactly when it starts
            datetime(2030, 1, 20, 11, 0),   # in progress
            datetime(2030, 1, 20, 12, 0),   # exactly when it ends
            datetime(2030, 1, 21, 8, 0),    # the next day
        ],
    )
    def test_closes_when_the_shift_starts(self, api, make, clock, now):
        shift = make.shift(day="2030-01-20", start="10:00", end="12:00")
        clock.set(now)
        assert_error(api.register(make.user(), shift), 409, code="closed",
                     detail="Registration for this shift is closed because it has already started.")

    def test_still_open_one_minute_before_the_start(self, api, make, clock):
        shift = make.shift(day="2030-01-20", start="10:00", end="12:00")
        clock.set(2030, 1, 20, 9, 59)
        assert api.register(make.user(), shift).status_code == 201

    def test_full_shift(self, api, make):
        shift = make.shift(capacity=2)
        assert api.register(make.user(), shift).status_code == 201
        assert api.register(make.user(), shift).status_code == 201
        assert_error(api.register(make.user(), shift), 409, code="full", detail="This shift is full.")

    def test_cancelling_reopens_the_spot(self, api, make):
        shift = make.shift(capacity=1)
        first, second = make.user(), make.user()
        registration = api.register(first, shift).json()
        assert_error(api.register(second, shift), 409, code="full")

        assert api.cancel(first, registration["registration_id"]).status_code == 200

        assert api.register(second, shift).status_code == 201

    def test_cancelled_registrations_made_outside_the_api_dont_count(self, api, make):
        shift = make.shift(capacity=1)
        make.registration(make.user(), shift, status="cancelled")
        assert api.register(make.user(), shift).status_code == 201

    def test_already_registered_for_this_shift(self, api, make):
        educator, shift = make.user(), make.shift()
        registration_id = api.register(educator, shift).json()["registration_id"]
        body = assert_error(api.register(educator, shift), 409, code="registered",
                            detail="You're already registered for this shift.")
        assert set(body) == {"detail", "code"}
        assert make.one("SELECT COUNT(*) AS n FROM public.registrations")["n"] == 1
        assert make.one("SELECT registration_id FROM public.registrations")["registration_id"] == registration_id

    def test_one_shift_per_event(self, api, make):
        educator, event = make.user(), make.event()
        morning = make.shift(event, start="09:00", end="10:00")
        afternoon = make.shift(event, start="14:00", end="15:00")
        other_day = make.shift(event, day="2030-01-27")
        assert api.register(educator, morning).status_code == 201
        for shift in (afternoon, other_day):
            assert_error(
                api.register(educator, shift), 409, code="registered_other_shift",
                detail="You're already registered for another shift in this event. "
                       "Cancel that registration first to switch shifts.",
            )

    def test_switching_shifts_after_cancelling(self, api, make):
        educator, event = make.user(), make.event()
        morning = make.shift(event, start="09:00", end="10:00")
        afternoon = make.shift(event, start="14:00", end="15:00")
        registration_id = api.register(educator, morning).json()["registration_id"]
        api.cancel(educator, registration_id)
        assert api.register(educator, afternoon).status_code == 201

    def test_overlapping_shift_in_another_event(self, api, make):
        educator = make.user()
        first = make.shift(make.event(title="Tabling"), day="2030-01-20", start="10:00", end="12:00")
        overlapping = make.shift(make.event(title="Workshop"), day="2030-01-20", start="11:30", end="13:00")
        api.register(educator, first)

        body = assert_error(api.register(educator, overlapping), 409, code="conflict")

        # Same wording as eligibilityError in mockEventService.js (formatDate + formatTimeRange).
        assert body["detail"] == (
            "This shift overlaps your registration for Tabling on Sun, Jan 20, 2030, "
            "10:00 AM – 12:00 PM PT."
        )

    @pytest.mark.parametrize(
        "start,end,overlaps",
        [
            ("08:00", "10:00", False),  # ends exactly when the other starts
            ("12:00", "13:00", False),  # starts exactly when the other ends
            ("08:00", "10:01", True),
            ("11:59", "13:00", True),
            ("10:30", "11:30", True),   # inside
            ("09:00", "13:00", True),   # around
            ("10:00", "12:00", True),   # identical
        ],
    )
    def test_overlap_boundaries(self, api, make, start, end, overlaps):
        educator = make.user()
        api.register(educator, make.shift(day="2030-01-20", start="10:00", end="12:00"))
        response = api.register(educator, make.shift(day="2030-01-20", start=start, end=end))
        if overlaps:
            assert_error(response, 409, code="conflict")
        else:
            assert response.status_code == 201, response.text

    def test_same_times_on_another_day_dont_overlap(self, api, make):
        educator = make.user()
        api.register(educator, make.shift(day="2030-01-20"))
        assert api.register(educator, make.shift(day="2030-01-21")).status_code == 201

    def test_registrations_on_cancelled_events_dont_block(self, api, make):
        educator = make.user()
        cancelled_event = make.event()
        api.register(educator, make.shift(cancelled_event, start="10:00", end="12:00"))
        make.cancel_event(cancelled_event)
        assert api.register(educator, make.shift(start="10:00", end="12:00")).status_code == 201

    def test_own_cancelled_registrations_dont_block(self, api, make):
        educator = make.user()
        registration_id = api.register(educator, make.shift(start="10:00", end="12:00")).json()["registration_id"]
        api.cancel(educator, registration_id)
        assert api.register(educator, make.shift(start="10:00", end="12:00")).status_code == 201

    def test_other_peoples_registrations_dont_cause_conflicts(self, api, make):
        api.register(make.user(), make.shift(start="10:00", end="12:00"))
        assert api.register(make.user(), make.shift(start="10:00", end="12:00")).status_code == 201

    def test_registering_again_creates_a_new_row(self, api, make):
        educator, shift = make.user(), make.shift()
        first = api.register(educator, shift).json()["registration_id"]
        api.cancel(educator, first)

        second = api.register(educator, shift).json()["registration_id"]

        assert second != first
        rows = make.all("SELECT registration_id, status FROM public.registrations ORDER BY registration_id")
        assert rows == [
            {"registration_id": first, "status": "cancelled"},
            {"registration_id": second, "status": "active"},
        ]

    # Precedence, same order as shiftEligibility in mockEventService.js.

    def test_registered_on_a_cancelled_event_reports_event_cancelled(self, api, make):
        educator, event = make.user(), make.event()
        shift = make.shift(event)
        api.register(educator, shift)
        make.cancel_event(event)
        assert_error(api.register(educator, shift), 409, code="event_cancelled")

    def test_closed_beats_full(self, api, make, clock):
        shift = make.shift(capacity=1, day="2030-01-20", start="10:00")
        api.register(make.user(), shift)
        clock.set(2030, 1, 20, 10, 30)
        assert_error(api.register(make.user(), shift), 409, code="closed")

    def test_other_shift_in_event_beats_full(self, api, make):
        educator, event = make.user(), make.event()
        api.register(educator, make.shift(event, start="08:00", end="09:00"))
        full = make.shift(event, start="13:00", end="14:00", capacity=1)
        api.register(make.user(), full)
        assert_error(api.register(educator, full), 409, code="registered_other_shift")

    def test_full_beats_conflict(self, api, make):
        educator = make.user()
        api.register(educator, make.shift(start="10:00", end="12:00"))
        full = make.shift(start="11:00", end="13:00", capacity=1)
        api.register(make.user(), full)
        assert_error(api.register(educator, full), 409, code="full")


# ---------- Cancelling ----------

class TestCancel:
    def test_cancels_and_keeps_the_row(self, api, make):
        educator = make.user()
        registration_id = api.register(educator, make.shift()).json()["registration_id"]

        response = api.cancel(educator, registration_id)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == REGISTRATION_KEYS
        assert body["status"] == "cancelled"
        assert body["category"] == "cancelled_by_user"
        assert body["can_cancel"] is False
        datetime.fromisoformat(body["cancelled_at"])
        row = make.one("SELECT status, cancelled_at FROM public.registrations WHERE registration_id = %s",
                       (registration_id,))
        assert row["status"] == "cancelled"
        assert row["cancelled_at"] is not None

    def test_cancelling_twice(self, api, make):
        educator = make.user()
        registration_id = api.register(educator, make.shift()).json()["registration_id"]
        api.cancel(educator, registration_id)
        assert_error(api.cancel(educator, registration_id), 409,
                     detail="This registration is already cancelled.")

    def test_someone_elses_registration_is_404(self, api, make):
        owner, other = make.user(), make.user()
        registration_id = api.register(owner, make.shift()).json()["registration_id"]
        assert_error(api.cancel(other, registration_id), 404, detail="Registration not found.")
        assert make.one("SELECT status FROM public.registrations")["status"] == "active"

    def test_unknown_registration_is_404(self, api, make):
        assert_error(api.cancel(make.user(), 424242), 404, detail="Registration not found.")

    def test_supervisors_cannot_use_it(self, api, make):
        educator = make.user()
        registration_id = api.register(educator, make.shift()).json()["registration_id"]
        assert_error(api.cancel(make.supervisor(), registration_id), 403)

    def test_requires_a_token(self, api, make):
        assert_error(api.post("/api/registrations/1/cancel"), 401)

    @pytest.mark.parametrize("now", [datetime(2030, 1, 20, 10, 0), datetime(2030, 1, 20, 13, 0)])
    def test_closed_once_the_shift_starts(self, api, make, clock, now):
        educator = make.user()
        registration_id = api.register(educator, make.shift(day="2030-01-20", start="10:00")).json()["registration_id"]
        clock.set(now)
        assert_error(api.cancel(educator, registration_id), 409,
                     detail="This shift has already started, so it can't be cancelled here.")

    def test_allowed_one_minute_before_the_start(self, api, make, clock):
        educator = make.user()
        registration_id = api.register(educator, make.shift(day="2030-01-20", start="10:00")).json()["registration_id"]
        clock.set(2030, 1, 20, 9, 59)
        assert api.cancel(educator, registration_id).status_code == 200

    def test_cancelled_event(self, api, make):
        educator, event = make.user(), make.event()
        registration_id = api.register(educator, make.shift(event)).json()["registration_id"]
        make.cancel_event(event)
        assert_error(api.cancel(educator, registration_id), 409,
                     detail="This event was cancelled, so there's nothing to cancel.")


# ---------- My registrations ----------

class TestMyRegistrations:
    def test_lists_every_registration_with_its_category(self, api, make, clock):
        educator = make.user()
        clock.set(2030, 1, 1, 8, 0)  # register everything while it's all in the future
        past = make.shift(day="2030-01-10", start="10:00", end="11:00")
        in_progress = make.shift(day="2030-01-15", start="08:30", end="10:00")
        upcoming = make.shift(day="2030-01-20", start="10:00", end="11:00")
        cancelled_by_user = make.shift(day="2030-01-21")
        cancelled_event = make.event()
        on_cancelled_event = make.shift(cancelled_event, day="2030-01-22")
        ids = {
            name: api.register(educator, shift).json()["registration_id"]
            for name, shift in [
                ("past", past), ("in_progress", in_progress), ("upcoming", upcoming),
                ("cancelled_by_user", cancelled_by_user), ("event_cancelled", on_cancelled_event),
            ]
        }
        api.cancel(educator, ids["cancelled_by_user"])
        make.cancel_event(cancelled_event)
        clock.set(2030, 1, 15, 9, 0)

        response = api.my_registrations(educator)

        assert response.status_code == 200
        body = response.json()
        assert [item["registration_id"] for item in body] == [
            ids["past"], ids["in_progress"], ids["upcoming"], ids["cancelled_by_user"], ids["event_cancelled"],
        ]
        assert [item["category"] for item in body] == [
            "past", "in_progress", "upcoming", "cancelled_by_user", "event_cancelled",
        ]
        assert [item["can_cancel"] for item in body] == [False, False, True, False, False]
        assert body[4]["event"]["status"] == "cancelled"
        assert body[4]["event"]["cancelled_at"] is not None
        for item in body:
            assert set(item) == REGISTRATION_KEYS

    def test_same_shift_is_ordered_by_when_you_registered(self, api, make):
        educator, shift = make.user(), make.shift()
        first = api.register(educator, shift).json()["registration_id"]
        api.cancel(educator, first)
        second = api.register(educator, shift).json()["registration_id"]
        assert [item["registration_id"] for item in api.my_registrations(educator).json()] == [first, second]

    def test_only_your_own(self, api, make):
        me, someone_else = make.user(), make.user()
        shift = make.shift()
        mine = api.register(me, shift).json()["registration_id"]
        api.register(someone_else, shift)
        assert [item["registration_id"] for item in api.my_registrations(me).json()] == [mine]

    def test_empty(self, api, make):
        assert api.my_registrations(make.user()).json() == []

    def test_supervisors_get_403(self, api, make):
        assert_error(api.my_registrations(make.supervisor()), 403)

    def test_requires_a_token(self, api, make):
        assert_error(api.get("/api/me/registrations"), 401)


# ---------- Database rules ----------

class TestDatabaseRules:
    """The constraints hold even for writes that skip the API."""

    def test_one_active_registration_per_event(self, make):
        educator, event = make.user(), make.event()
        make.registration(educator, make.shift(event, start="08:00", end="09:00"))
        with pytest.raises(psycopg.errors.UniqueViolation):
            make.registration(educator, make.shift(event, start="13:00", end="14:00"))

    def test_cancelled_rows_dont_count_toward_one_per_event(self, make):
        educator, event = make.user(), make.event()
        make.registration(educator, make.shift(event, start="08:00", end="09:00"), status="cancelled")
        make.registration(educator, make.shift(event, start="13:00", end="14:00"))

    def test_one_active_registration_per_shift(self, make):
        educator, shift = make.user(), make.shift()
        make.registration(educator, shift)
        with pytest.raises(psycopg.errors.UniqueViolation):
            make.registration(educator, shift)

    def test_event_id_must_match_the_shift(self, make):
        shift = make.shift(make.event())
        other_event = make.event()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            make.one(
                "INSERT INTO public.registrations (shift_id, event_id, user_id) VALUES (%s, %s, %s)",
                (shift, other_event, make.user()),
            )

    def test_event_id_is_required(self, make):
        with pytest.raises(psycopg.errors.NotNullViolation):
            make.one(
                "INSERT INTO public.registrations (shift_id, user_id) VALUES (%s, %s)",
                (make.shift(), make.user()),
            )

    def test_active_rows_have_no_cancellation_time(self, make):
        shift = make.shift()
        with pytest.raises(psycopg.errors.CheckViolation):
            make.one(
                """
                INSERT INTO public.registrations (shift_id, event_id, user_id, status, cancelled_at)
                SELECT shift_id, event_id, %s, 'active', now() FROM public.shifts WHERE shift_id = %s
                """,
                (make.user(), shift),
            )

    def test_unknown_status_is_rejected(self, make):
        with pytest.raises(psycopg.errors.CheckViolation):
            make.registration(make.user(), make.shift(), status="pending")

    def test_deleting_a_shift_deletes_its_registrations(self, make):
        shift = make.shift()
        make.registration(make.user(), shift, status="cancelled")
        make.one("DELETE FROM public.shifts WHERE shift_id = %s RETURNING shift_id", (shift,))
        assert make.one("SELECT COUNT(*) AS n FROM public.registrations")["n"] == 0


# ---------- Working with the supervisor endpoints ----------

class TestWithSupervisorEndpoints:
    """Registrations made here show up correctly in the existing supervisor API."""

    def test_counts_and_participants(self, api, make):
        supervisor = make.supervisor()
        event = make.event(organizer=supervisor)
        shift = make.shift(event, capacity=3)
        educator = make.user(name="Ada Lovelace", email="ada@sjsu.edu")
        registration_id = api.register(educator, shift).json()["registration_id"]

        detail = api.get(f"/api/events/{event}", supervisor).json()
        assert detail["active_registrations"] == 1
        assert detail["shifts"][0]["remaining_spots"] == 2
        assert detail["has_registration_history"] is True
        participants = api.get(f"/api/events/{event}/participants", supervisor).json()
        assert [p["user"]["name"] for p in participants] == ["Ada Lovelace"]

        api.cancel(educator, registration_id)

        detail = api.get(f"/api/events/{event}", supervisor).json()
        assert detail["active_registrations"] == 0
        assert detail["shifts"][0]["remaining_spots"] == 3
        assert api.get(f"/api/events/{event}/participants", supervisor).json() == []

    def test_supervisor_cancelling_the_event(self, api, make):
        supervisor = make.supervisor()
        event = make.event(organizer=supervisor)
        shift = make.shift(event)
        educator = make.user()
        api.register(educator, shift)

        assert api.post(f"/api/events/{event}/cancel", supervisor).status_code == 200

        [registration] = api.my_registrations(educator).json()
        assert registration["category"] == "event_cancelled"
        assert registration["can_cancel"] is False
        assert_error(api.register(make.user(), shift), 409, code="event_cancelled")

    def test_supervisor_cant_lower_capacity_below_sign_ups(self, api, make):
        supervisor = make.supervisor()
        event = make.event(organizer=supervisor)
        location = make.location()
        shift = make.shift(event, capacity=3, location=location)
        api.register(make.user(), shift)
        api.register(make.user(), shift)

        response = api.put(f"/api/events/{event}", supervisor, json={
            "title": "Event", "description": "", "is_urgent": False,
            "shifts": [{"shift_id": shift, "shift_date": "2030-01-20", "start_time": "10:00",
                        "end_time": "12:00", "location_id": location, "capacity": 1}],
        })

        assert response.status_code == 422
        assert "capacity" in response.json()["field_errors"]["shiftFields"]["0"]

    def test_removing_a_shift_with_only_cancelled_sign_ups(self, api, make):
        supervisor = make.supervisor()
        event = make.event(organizer=supervisor)
        location = make.location()
        keep = make.shift(event, start="08:00", end="09:00", location=location)
        remove = make.shift(event, start="13:00", end="14:00", location=location)
        educator = make.user()
        registration_id = api.register(educator, remove).json()["registration_id"]
        api.cancel(educator, registration_id)

        response = api.put(f"/api/events/{event}", supervisor, json={
            "title": "Event", "description": "", "is_urgent": False,
            "shifts": [{"shift_id": keep, "shift_date": "2030-01-20", "start_time": "08:00",
                        "end_time": "09:00", "location_id": location, "capacity": 5}],
        })

        assert response.status_code == 200, response.text
        assert api.my_registrations(educator).json() == []
