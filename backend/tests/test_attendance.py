"""Attendance: roster, marking attended/absent, clearing, history and summary.

Shifts default to Sun, Jan 20, 2030, 10:00-12:00 (120 minutes). Most tests
move the clock to 11:00 that day so the shift has started.
"""
import psycopg
import pytest

from helpers import assert_error

SHIFT_DAY = (2030, 1, 20)


@pytest.fixture
def during_shift(clock):
    def move():
        clock.set(*SHIFT_DAY, 11, 0)
    return move


@pytest.fixture
def signed_up(api, make, during_shift):
    """A supervisor, a 120-minute shift, and three registrations (one cancelled)."""
    supervisor = make.supervisor()
    event = make.event(organizer=supervisor, title="Tabling")
    shift = make.shift(event, capacity=5)
    people = {name: make.user(name=name, email=f"{name.lower()}@sjsu.edu") for name in ("Cara", "Ana", "Ben")}
    registrations = {name: api.register(user, shift).json()["registration_id"] for name, user in people.items()}
    api.cancel(people["Ben"], registrations["Ben"])
    during_shift()
    return {"supervisor": supervisor, "event": event, "shift": shift, "people": people, "registrations": registrations}


# ---------- Roster ----------

class TestRoster:
    def test_lists_active_sign_ups_by_name(self, api, signed_up):
        response = api.get(f"/api/shifts/{signed_up['shift']}/attendance", signed_up["supervisor"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"shift", "event", "can_record", "blocked_reason", "summary", "roster"}
        assert [entry["user"]["name"] for entry in body["roster"]] == ["Ana", "Cara"]  # Ben cancelled
        assert all(entry["attendance"] is None for entry in body["roster"])
        assert set(body["roster"][0]) == {"registration_id", "registered_at", "user", "attendance"}
        assert body["roster"][0]["user"]["email"] == "ana@sjsu.edu"
        assert body["shift"]["duration_minutes"] == 120
        assert body["shift"]["has_started"] is True
        assert body["shift"]["has_ended"] is False
        assert body["event"] == {"event_id": signed_up["event"], "title": "Tabling", "status": "published"}
        assert body["can_record"] is True
        assert body["blocked_reason"] is None
        assert body["summary"] == {"registered": 2, "attended": 0, "absent": 0, "unmarked": 2, "credited_minutes": 0}

    def test_before_the_shift_starts_it_says_why_recording_is_blocked(self, api, signed_up, clock):
        clock.set(*SHIFT_DAY, 9, 59)
        body = api.get(f"/api/shifts/{signed_up['shift']}/attendance", signed_up["supervisor"]).json()
        assert body["can_record"] is False
        assert body["blocked_reason"] == "Attendance can be recorded once the shift starts."

    def test_summary_counts_marks(self, api, signed_up):
        supervisor, registrations = signed_up["supervisor"], signed_up["registrations"]
        api.mark(supervisor, registrations["Ana"], participation_status="attended", credited_minutes=90)
        api.mark(supervisor, registrations["Cara"], participation_status="absent")

        body = api.get(f"/api/shifts/{signed_up['shift']}/attendance", supervisor).json()

        assert body["summary"] == {"registered": 2, "attended": 1, "absent": 1, "unmarked": 0, "credited_minutes": 90}
        by_name = {entry["user"]["name"]: entry["attendance"] for entry in body["roster"]}
        assert by_name["Ana"]["participation_status"] == "attended"
        assert by_name["Ana"]["credited_minutes"] == 90
        assert by_name["Cara"] == {
            "attendance_id": by_name["Cara"]["attendance_id"], "participation_status": "absent", "credited_minutes": 0,
        }

    def test_peer_educators_cant_see_it(self, api, signed_up):
        assert_error(api.get(f"/api/shifts/{signed_up['shift']}/attendance", signed_up["people"]["Ana"]), 403)

    def test_unknown_shift(self, api, make):
        assert_error(api.get("/api/shifts/9999/attendance", make.supervisor()), 404, detail="Shift not found.")

    def test_requires_a_token(self, api, make):
        assert_error(api.get("/api/shifts/1/attendance"), 401)


# ---------- Marking one registration ----------

class TestMark:
    def test_attended_defaults_to_the_full_shift(self, api, signed_up):
        response = api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"], participation_status="attended")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"attendance_id", "registration_id", "participation_status", "credited_minutes"}
        assert body["registration_id"] == signed_up["registrations"]["Ana"]
        assert body["participation_status"] == "attended"
        assert body["credited_minutes"] == 120

    @pytest.mark.parametrize("minutes", [0, 45, 120, "90", " 60 "])
    def test_attended_with_credited_minutes(self, api, signed_up, minutes):
        body = api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"],
                        participation_status="attended", credited_minutes=minutes).json()
        assert body["credited_minutes"] == int(str(minutes).strip())

    @pytest.mark.parametrize("minutes", [None, 0, "0", ""])
    def test_absent_is_credited_zero_minutes(self, api, signed_up, minutes):
        body = api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"],
                        participation_status="absent", credited_minutes=minutes).json()
        assert body["participation_status"] == "absent"
        assert body["credited_minutes"] == 0

    def test_status_is_case_insensitive(self, api, signed_up):
        body = api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"], participation_status=" Attended ").json()
        assert body["participation_status"] == "attended"

    @pytest.mark.parametrize(
        "payload,field,message",
        [
            ({}, "participation_status", 'Choose "attended" or "absent".'),
            ({"participation_status": "present"}, "participation_status", 'Choose "attended" or "absent".'),
            ({"participation_status": 1}, "participation_status", 'Choose "attended" or "absent".'),
            ({"participation_status": "attended", "credited_minutes": 121}, "credited_minutes",
             "Credited minutes can't be more than the shift's 120 minutes."),
            ({"participation_status": "attended", "credited_minutes": -5}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": 30.5}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": "ninety"}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": True}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            # str.isdigit() accepts these, but they aren't plain whole numbers.
            ({"participation_status": "attended", "credited_minutes": "²"}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": "١٢"}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": "9" * 5000}, "credited_minutes",
             "Enter a whole number of minutes, 0 or more."),
            ({"participation_status": "attended", "credited_minutes": 10 ** 30}, "credited_minutes",
             "Credited minutes can't be more than the shift's 120 minutes."),
            ({"participation_status": "absent", "credited_minutes": 30}, "credited_minutes",
             "Absent participants can't be credited minutes."),
        ],
    )
    def test_validation(self, api, signed_up, make, payload, field, message):
        response = api.put(f"/api/registrations/{signed_up['registrations']['Ana']}/attendance",
                           signed_up["supervisor"], json=payload)
        body = assert_error(response, 422, detail="Please fix the highlighted fields.")
        assert body["field_errors"][field] == message
        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 0

    def test_marking_again_updates_the_same_record(self, api, signed_up, make):
        supervisor, registration_id = signed_up["supervisor"], signed_up["registrations"]["Ana"]
        first = api.mark(supervisor, registration_id, participation_status="attended").json()
        second = api.mark(supervisor, registration_id, participation_status="absent").json()

        assert second["attendance_id"] == first["attendance_id"]
        assert second["participation_status"] == "absent"
        assert second["credited_minutes"] == 0
        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 1

    def test_not_before_the_shift_starts(self, api, signed_up, clock):
        clock.set(*SHIFT_DAY, 9, 59)
        assert_error(api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"], participation_status="attended"),
                     409, detail="Attendance can be recorded once the shift starts.")

    def test_from_the_moment_it_starts_and_after_it_ends(self, api, signed_up, clock):
        for now in [(*SHIFT_DAY, 10, 0), (2030, 2, 1, 9, 0)]:
            clock.set(*now)
            assert api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"],
                            participation_status="attended").status_code == 200

    def test_not_for_cancelled_registrations(self, api, signed_up):
        assert_error(api.mark(signed_up["supervisor"], signed_up["registrations"]["Ben"], participation_status="absent"),
                     409, detail="Cancelled registrations can't have attendance.")

    def test_not_for_cancelled_events(self, api, signed_up, make):
        make.cancel_event(signed_up["event"])
        assert_error(api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"], participation_status="attended"),
                     409, detail="This event was cancelled, so attendance can't be changed.")

    def test_unknown_registration(self, api, make):
        assert_error(api.mark(make.supervisor(), 777, participation_status="attended"), 404,
                     detail="Registration not found.")

    def test_peer_educators_cant_mark(self, api, signed_up):
        ana = signed_up["people"]["Ana"]
        assert_error(api.mark(ana, signed_up["registrations"]["Ana"], participation_status="attended"), 403)

    def test_shows_up_in_my_registrations(self, api, signed_up):
        api.mark(signed_up["supervisor"], signed_up["registrations"]["Ana"], participation_status="attended",
                 credited_minutes=100)
        [registration] = api.my_registrations(signed_up["people"]["Ana"]).json()
        assert registration["category"] == "in_progress"
        assert registration["attendance"]["participation_status"] == "attended"
        assert registration["attendance"]["credited_minutes"] == 100


# ---------- Marking a whole shift ----------

class TestMarkShift:
    def put_roster(self, api, signed_up, records):
        return api.put(f"/api/shifts/{signed_up['shift']}/attendance", signed_up["supervisor"],
                       json={"records": records})

    def test_marks_several_and_returns_the_roster(self, api, signed_up):
        registrations = signed_up["registrations"]
        response = self.put_roster(api, signed_up, [
            {"registration_id": registrations["Ana"], "participation_status": "attended", "credited_minutes": 60},
            {"registration_id": registrations["Cara"], "participation_status": "absent"},
        ])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"] == {"registered": 2, "attended": 1, "absent": 1, "unmarked": 0, "credited_minutes": 60}

    def test_leaves_unlisted_registrations_alone(self, api, signed_up):
        registrations = signed_up["registrations"]
        api.mark(signed_up["supervisor"], registrations["Cara"], participation_status="attended")
        body = self.put_roster(api, signed_up, [
            {"registration_id": registrations["Ana"], "participation_status": "absent"},
        ]).json()
        by_name = {entry["user"]["name"]: entry["attendance"]["participation_status"] for entry in body["roster"]}
        assert by_name == {"Ana": "absent", "Cara": "attended"}

    def test_all_or_nothing(self, api, signed_up, make):
        registrations = signed_up["registrations"]
        other_shift_registration = api.register(make.user(), make.shift(start="13:00", end="14:00")).json()

        response = self.put_roster(api, signed_up, [
            {"registration_id": registrations["Ana"], "participation_status": "attended"},
            {"registration_id": registrations["Cara"], "participation_status": "late"},
            {"registration_id": other_shift_registration["registration_id"], "participation_status": "absent"},
            {"registration_id": registrations["Ben"], "participation_status": "absent"},
            {"registration_id": registrations["Ana"], "participation_status": "absent"},
            {"registration_id": "abc", "participation_status": "absent"},
            {"registration_id": "²", "participation_status": "absent"},
            {"registration_id": "9" * 5000, "participation_status": "absent"},
        ])

        body = assert_error(response, 422, detail="Please fix the highlighted fields.")
        errors = body["field_errors"]["records"]
        assert set(errors) == {"1", "2", "3", "4", "5", "6", "7"}
        assert errors["1"] == {"participation_status": 'Choose "attended" or "absent".'}
        assert errors["2"] == {"registration_id": "This registration isn't on this shift."}
        assert errors["3"] == {"registration_id": "Cancelled registrations can't have attendance."}
        assert errors["4"] == {"registration_id": "This registration is listed more than once."}
        assert errors["5"] == {"registration_id": "This registration isn't on this shift."}
        assert errors["6"] == {"registration_id": "This registration isn't on this shift."}
        assert errors["7"] == {"registration_id": "This registration isn't on this shift."}
        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 0

    def test_needs_at_least_one_record(self, api, signed_up):
        body = assert_error(self.put_roster(api, signed_up, []), 422)
        assert body["field_errors"] == {"records": "Add at least one attendance record."}

    def test_not_before_the_shift_starts(self, api, signed_up, clock):
        clock.set(*SHIFT_DAY, 9, 0)
        assert_error(self.put_roster(api, signed_up, [
            {"registration_id": signed_up["registrations"]["Ana"], "participation_status": "attended"},
        ]), 409, detail="Attendance can be recorded once the shift starts.")

    def test_draft_events(self, api, make, during_shift):
        supervisor = make.supervisor()
        shift = make.shift(make.event(organizer=supervisor, status="draft"))
        during_shift()
        response = api.put(f"/api/shifts/{shift}/attendance", supervisor, json={"records": [{"registration_id": 1}]})
        assert_error(response, 409, detail="Attendance can only be recorded for published events.")

    def test_unknown_shift(self, api, make):
        assert_error(api.put("/api/shifts/4040/attendance", make.supervisor(), json={"records": []}), 404)

    def test_peer_educators_cant_mark(self, api, signed_up):
        response = api.put(f"/api/shifts/{signed_up['shift']}/attendance", signed_up["people"]["Ana"],
                           json={"records": []})
        assert_error(response, 403)


# ---------- Clearing ----------

class TestClear:
    def test_clears_a_mark(self, api, signed_up, make):
        supervisor, registration_id = signed_up["supervisor"], signed_up["registrations"]["Ana"]
        api.mark(supervisor, registration_id, participation_status="attended")

        response = api.delete(f"/api/registrations/{registration_id}/attendance", supervisor)

        assert response.status_code == 204
        assert response.content == b""
        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 0

    def test_clearing_an_unmarked_registration_is_fine(self, api, signed_up):
        response = api.delete(f"/api/registrations/{signed_up['registrations']['Ana']}/attendance", signed_up["supervisor"])
        assert response.status_code == 204

    def test_unknown_registration(self, api, make):
        assert_error(api.delete("/api/registrations/31337/attendance", make.supervisor()), 404)

    def test_not_for_cancelled_events(self, api, signed_up, make):
        supervisor, registration_id = signed_up["supervisor"], signed_up["registrations"]["Ana"]
        api.mark(supervisor, registration_id, participation_status="attended")
        make.cancel_event(signed_up["event"])
        assert_error(api.delete(f"/api/registrations/{registration_id}/attendance", supervisor), 409)
        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 1

    def test_peer_educators_cant_clear(self, api, signed_up):
        response = api.delete(f"/api/registrations/{signed_up['registrations']['Ana']}/attendance",
                              signed_up["people"]["Ana"])
        assert_error(response, 403)


# ---------- Participation history ----------

class TestMyAttendance:
    def test_history_newest_first_with_totals(self, api, make, clock):
        supervisor, educator = make.supervisor(), make.user()
        clock.set(2030, 1, 1, 8, 0)
        early = make.shift(make.event(title="Orientation"), day="2030-01-05", start="09:00", end="10:00")
        late = make.shift(make.event(title="Health Fair"), day="2030-01-10", start="13:00", end="16:00")
        unmarked = make.shift(make.event(title="Tabling"), day="2030-01-12")
        ids = [api.register(educator, shift).json()["registration_id"] for shift in (early, late, unmarked)]
        api.register(make.user(), early)  # someone else's sign-up
        clock.set(2030, 1, 15, 9, 0)
        api.mark(supervisor, ids[0], participation_status="absent")
        api.mark(supervisor, ids[1], participation_status="attended", credited_minutes=150)

        response = api.get("/api/me/attendance", educator)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"] == {"shifts_attended": 1, "shifts_absent": 1, "credited_minutes": 150}
        assert [record["event"]["title"] for record in body["records"]] == ["Health Fair", "Orientation"]
        first = body["records"][0]
        assert set(first) == {"attendance_id", "registration_id", "participation_status", "credited_minutes",
                              "event", "shift", "location"}
        assert first["shift"] == {"shift_id": late, "shift_date": "2030-01-10", "start_time": "13:00", "end_time": "16:00"}
        assert first["registration_id"] == ids[1]

    def test_empty(self, api, make):
        assert api.get("/api/me/attendance", make.user()).json() == {
            "summary": {"shifts_attended": 0, "shifts_absent": 0, "credited_minutes": 0},
            "records": [],
        }

    def test_supervisors_get_403(self, api, make):
        assert_error(api.get("/api/me/attendance", make.supervisor()), 403)


# ---------- Supervisor summary ----------

class TestSummary:
    def test_totals_per_peer_educator_in_range(self, api, make, clock):
        supervisor = make.supervisor()
        ana, ben = make.user(name="Ana"), make.user(name="Ben")
        clock.set(2030, 1, 1, 8, 0)
        in_range_1 = make.shift(day="2030-01-07", start="09:00", end="11:00")
        in_range_2 = make.shift(day="2030-01-13", start="09:00", end="10:00")
        outside = make.shift(day="2030-01-14", start="09:00", end="12:00")
        marks = [
            (ana, in_range_1, "attended", 120),
            (ana, in_range_2, "attended", 60),
            (ben, in_range_1, "absent", None),
            (ben, outside, "attended", 180),
        ]
        registration_ids = [api.register(user, shift).json()["registration_id"] for user, shift, _, _ in marks]
        clock.set(2030, 1, 15, 9, 0)
        for registration_id, (_, _, status, minutes) in zip(registration_ids, marks):
            api.mark(supervisor, registration_id, participation_status=status, credited_minutes=minutes)

        response = api.get("/api/attendance/summary", supervisor, params={"from": "2030-01-07", "to": "2030-01-13"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["range"] == {"from": "2030-01-07", "to": "2030-01-13"}
        assert body["totals"] == {"peer_educators": 2, "shifts_attended": 2, "shifts_absent": 1, "credited_minutes": 180}
        assert [(row["user"]["name"], row["shifts_attended"], row["shifts_absent"], row["credited_minutes"])
                for row in body["rows"]] == [("Ana", 2, 0, 180), ("Ben", 0, 1, 0)]

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"from": "2030-01-01"},
            {"from": "2030-01-10", "to": "2030-01-01"},
            {"from": "2030-02-30", "to": "2030-03-01"},
            {"from": "01/01/2030", "to": "2030-03-01"},
        ],
    )
    def test_needs_a_valid_range(self, api, make, params):
        assert_error(api.get("/api/attendance/summary", make.supervisor(), params=params), 422,
                     detail="Choose a valid date range.")

    @pytest.mark.parametrize("params", [{"from": "2030-01-01", "to": "2030-01-31"}, {"from": "bad"}])
    def test_peer_educators_get_403(self, api, make, params):
        assert_error(api.get("/api/attendance/summary", make.user(), params=params), 403)


# ---------- Database rules ----------

class TestAttendanceTable:
    def insert(self, make, registration_id, status, minutes):
        return make.one(
            """
            INSERT INTO public.attendance (registration_id, participation_status, credited_minutes)
            VALUES (%s, %s, %s) RETURNING attendance_id
            """,
            (registration_id, status, minutes),
        )

    def test_one_record_per_registration(self, make):
        registration_id = make.registration(make.user(), make.shift())
        self.insert(make, registration_id, "attended", 60)
        with pytest.raises(psycopg.errors.UniqueViolation):
            self.insert(make, registration_id, "absent", 0)

    @pytest.mark.parametrize("status,minutes", [("absent", 15), ("attended", -1), ("present", 0)])
    def test_check_constraints(self, make, status, minutes):
        registration_id = make.registration(make.user(), make.shift())
        with pytest.raises(psycopg.errors.CheckViolation):
            self.insert(make, registration_id, status, minutes)

    @pytest.mark.parametrize("table,key", [("registrations", "registration_id"), ("shifts", "shift_id"),
                                           ("events", "event_id"), ("users", "user_id")])
    def test_records_with_attendance_cant_be_deleted(self, make, table, key):
        """Deleting the registration, or anything it cascades from, is refused."""
        user, event = make.user(), make.event()
        shift = make.shift(event)
        registration_id = make.registration(user, shift)
        self.insert(make, registration_id, "attended", 60)
        ids = {"registration_id": registration_id, "shift_id": shift, "event_id": event, "user_id": user}

        with pytest.raises((psycopg.errors.ForeignKeyViolation, psycopg.errors.RestrictViolation)):
            make.one(f"DELETE FROM public.{table} WHERE {key} = %s RETURNING 1", (ids[key],))

        assert make.one("SELECT COUNT(*) AS n FROM public.attendance")["n"] == 1
        assert make.one("SELECT COUNT(*) AS n FROM public.registrations")["n"] == 1

    def test_registrations_without_attendance_still_cascade(self, make):
        shift = make.shift()
        make.registration(make.user(), shift, status="cancelled")
        make.one("DELETE FROM public.shifts WHERE shift_id = %s RETURNING 1", (shift,))
        assert make.one("SELECT COUNT(*) AS n FROM public.registrations")["n"] == 0
