"""People and roles: supervisors list users and make others supervisors or peer educators.

The clock is frozen at Tue, Jan 15, 2030, 9:00 AM; factory shifts default to
Sun, Jan 20, 2030, so they are upcoming.
"""
from uuid import uuid4

import pytest

from helpers import assert_error


def set_role(api, actor, target, role):
    return api.put(f"/api/users/{target}/role", actor, json={"role": role})


# ---------- Listing ----------

class TestListUsers:
    def test_supervisor_sees_everyone_sorted_by_name(self, api, make):
        supervisor = make.supervisor(name="Zoe Boss", email="zoe@sjsu.edu")
        make.user(name="ana lee", email="ana@sjsu.edu")
        make.user(name="Ben Ng", email="ben@sjsu.edu")

        response = api.get("/api/users", supervisor)

        assert response.status_code == 200, response.text
        body = response.json()
        assert [user["name"] for user in body] == ["ana lee", "Ben Ng", "Zoe Boss"]
        assert set(body[0]) == {"user_id", "name", "email", "role", "upcoming_registrations", "is_you"}
        assert [user["is_you"] for user in body] == [False, False, True]
        assert body[2]["role"] == "supervisor"

    def test_counts_only_upcoming_active_registrations(self, api, make, clock):
        supervisor = make.supervisor()
        educator = make.user(name="Ana")
        make.registration(educator, make.shift(day="2030-01-20"))  # upcoming
        make.registration(educator, make.shift(day="2030-01-10"))  # past
        make.registration(educator, make.shift(day="2030-01-21"), status="cancelled")
        cancelled_event = make.event()
        make.registration(educator, make.shift(cancelled_event, day="2030-01-22"))
        make.cancel_event(cancelled_event)

        body = api.get("/api/users", supervisor).json()

        assert {user["name"]: user["upcoming_registrations"] for user in body}["Ana"] == 1

    def test_search_matches_name_or_email_and_treats_wildcards_literally(self, api, make):
        supervisor = make.supervisor(name="Sam", email="sam@sjsu.edu")
        make.user(name="Ana Lee", email="ana@sjsu.edu")
        make.user(name="Ben", email="ben_100%@sjsu.edu")

        assert [u["name"] for u in api.get("/api/users", supervisor, params={"search": "lee"}).json()] == ["Ana Lee"]
        assert [u["name"] for u in api.get("/api/users", supervisor, params={"search": "BEN_"}).json()] == ["Ben"]
        assert [u["name"] for u in api.get("/api/users", supervisor, params={"search": "100%"}).json()] == ["Ben"]
        assert api.get("/api/users", supervisor, params={"search": "a_a"}).json() == []

    def test_peer_educators_cannot_list_people(self, api, make):
        educator = make.user()
        assert_error(api.get("/api/users", educator), 403, detail="Only supervisors can view people")

    def test_needs_a_token(self, api, db):
        assert_error(api.get("/api/users"), 401)


# ---------- Changing roles ----------

class TestSetRole:
    def test_supervisor_promotes_a_peer_educator(self, api, make):
        supervisor, educator = make.supervisor(), make.user(name="Ana", email="ana@sjsu.edu")

        response = set_role(api, supervisor, educator, "supervisor")

        assert response.status_code == 200, response.text
        assert response.json() == {
            "user_id": str(educator),
            "name": "Ana",
            "email": "ana@sjsu.edu",
            "role": "supervisor",
            "is_you": False,
        }
        assert api.get("/api/me", educator).json()["role"] == "supervisor"
        # The new supervisor can now use supervisor routes.
        assert api.get("/api/users", educator).status_code == 200

    def test_supervisor_demotes_another_supervisor(self, api, make):
        first, second = make.supervisor(), make.supervisor()

        response = set_role(api, first, second, "peer_educator")

        assert response.status_code == 200, response.text
        assert make.one("SELECT role FROM public.users WHERE user_id = %s", (second,))["role"] == "peer_educator"

    def test_role_is_trimmed_and_case_insensitive(self, api, make):
        supervisor, educator = make.supervisor(), make.user()
        assert set_role(api, supervisor, educator, "  Supervisor ").json()["role"] == "supervisor"

    def test_setting_the_same_role_changes_nothing(self, api, make):
        supervisor, educator = make.supervisor(), make.user()
        response = set_role(api, supervisor, educator, "peer_educator")
        assert response.status_code == 200, response.text
        assert response.json()["role"] == "peer_educator"

    def test_nobody_changes_their_own_role(self, api, make):
        supervisor = make.supervisor()
        assert_error(set_role(api, supervisor, supervisor, "peer_educator"), 409, code="own_role")
        assert make.one("SELECT role FROM public.users WHERE user_id = %s", (supervisor,))["role"] == "supervisor"

    def test_peer_educators_cannot_change_roles(self, api, make):
        educator, other = make.user(), make.user()
        assert_error(set_role(api, educator, other, "supervisor"), 403, code="forbidden")
        # Not even their own, so sign-up can never lead to a supervisor account.
        assert_error(set_role(api, educator, educator, "supervisor"), 403, code="forbidden")
        assert make.one("SELECT role FROM public.users WHERE user_id = %s", (educator,))["role"] == "peer_educator"

    def test_needs_a_token(self, api, make):
        assert_error(set_role(api, None, make.user(), "supervisor"), 401)

    @pytest.mark.parametrize("role", ["admin", "", None, 1, True, ["supervisor"]])
    def test_rejects_unknown_roles(self, api, make, role):
        supervisor, educator = make.supervisor(), make.user()
        body = assert_error(set_role(api, supervisor, educator, role), 422)
        assert set(body["field_errors"]) == {"role"}

    def test_unknown_user(self, api, make):
        assert_error(set_role(api, make.supervisor(), uuid4(), "supervisor"), 404, detail="User not found.")

    def test_bad_user_id(self, api, make):
        response = api.put("/api/users/not-a-uuid/role", make.supervisor(), json={"role": "supervisor"})
        assert response.status_code == 422


class TestPromotingSomeoneWithSignUps:
    def test_refused_while_they_hold_upcoming_spots(self, api, make):
        supervisor, educator = make.supervisor(), make.user(name="Ana")
        shift = make.shift()
        registration = api.register(educator, shift).json()["registration_id"]

        body = assert_error(set_role(api, supervisor, educator, "supervisor"), 409, code="has_registrations")
        assert body["detail"] == (
            "Ana has 1 upcoming shift registration. They need to cancel them before becoming a supervisor."
        )

        # Once they cancel, the promotion goes through.
        api.cancel(educator, registration)
        assert set_role(api, supervisor, educator, "supervisor").status_code == 200

    def test_past_and_cancelled_sign_ups_dont_block_it(self, api, make):
        supervisor, educator = make.supervisor(), make.user()
        make.registration(educator, make.shift(day="2030-01-10"))
        make.registration(educator, make.shift(day="2030-01-21"), status="cancelled")
        assert set_role(api, supervisor, educator, "supervisor").status_code == 200

    def test_attendance_history_is_kept(self, api, make):
        supervisor, educator = make.supervisor(), make.user()
        registration = make.registration(educator, make.shift(day="2030-01-10"))
        make.conn.execute(
            "INSERT INTO public.attendance (registration_id, participation_status, credited_minutes)"
            " VALUES (%s, 'attended', 120)",
            (registration,),
        )

        assert set_role(api, supervisor, educator, "supervisor").status_code == 200
        assert make.one("SELECT COUNT(*)::int AS n FROM public.attendance")["n"] == 1
