"""Peer educator registrations: sign up for a shift, cancel, and list your own.

Rules (API_CONTRACT.md, "Registration rules"), same as mockEventService.js:
1. Registration is immediate. There is no approval step.
2. One active registration per user per event. The database also enforces this
   with the registrations_one_active_per_event index.
3. No overlapping active registrations across events. Registrations on
   cancelled events don't count.
4. Active registrations never exceed the shift's capacity.
5. Cancelling keeps the row (status 'cancelled' plus cancelled_at) and frees
   the spot. Registering again creates a new row.
6. Drafts are hidden from peer educators.
Registration closes when the shift starts, and so does cancelling.

Concurrency: a sign-up is one transaction that takes these locks, in this order:
- the user's row, so one person's sign-ups run one at a time (rules 2 and 3);
- the event row FOR SHARE, so a cancel or edit of the event waits.
  update_event also locks the event before its shifts, so the two can't deadlock;
- the shift row FOR UPDATE, so sign-ups for the same shift run one at a
  time (rule 4).
Active registrations are counted only after those locks are held.
"""
from datetime import date, time
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app import campus_time
from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_peer_educator

router = APIRouter(prefix="/api", tags=["Registrations"])

ELIGIBILITY_MESSAGES = {
    "registered": "You're already registered for this shift.",
    "registered_other_shift": (
        "You're already registered for another shift in this event. "
        "Cancel that registration first to switch shifts."
    ),
    "full": "This shift is full.",
    "event_cancelled": "This event was cancelled, so registration is closed.",
    "closed": "Registration for this shift is closed because it has already started.",
}

# Everything a MyRegistration response needs, one row per registration.
REGISTRATION_SELECT = """
    SELECT registrations.registration_id, registrations.user_id, registrations.status,
           registrations.created_at, registrations.cancelled_at,
           events.event_id, events.title, events.status AS event_status,
           events.is_urgent, events.cancelled_at AS event_cancelled_at,
           shifts.shift_id, shifts.shift_date, shifts.start_time, shifts.end_time,
           locations.location_id, locations.building, locations.room_or_area,
           locations.directions, locations.map_url,
           attendance.attendance_id, attendance.participation_status,
           attendance.credited_minutes
    FROM public.registrations
    JOIN public.shifts ON shifts.shift_id = registrations.shift_id
    JOIN public.events ON events.event_id = shifts.event_id
    LEFT JOIN public.locations ON locations.location_id = shifts.location_id
    LEFT JOIN public.attendance ON attendance.registration_id = registrations.registration_id
"""


# ---------- Eligibility ----------

def active_registrations_for_user(cursor, user_id):
    """The user's active registrations on events that aren't cancelled.

    Registrations on cancelled events stay as history but never block new sign-ups.
    """
    cursor.execute(
        """
        SELECT registrations.registration_id, registrations.shift_id,
               shifts.event_id, shifts.shift_date, shifts.start_time, shifts.end_time,
               events.title
        FROM public.registrations
        JOIN public.shifts ON shifts.shift_id = registrations.shift_id
        JOIN public.events ON events.event_id = shifts.event_id
        WHERE registrations.user_id = %s
          AND registrations.status = 'active'
          AND events.status <> 'cancelled'
        ORDER BY shifts.shift_date, shifts.start_time, registrations.registration_id
        """,
        (user_id,),
    )
    return cursor.fetchall()


def shift_eligibility(event, shift, active_count, mine, now):
    """Whether a user may register for a shift, as {"code": ...}.

    Same codes and precedence as shiftEligibility in mockEventService.js.
    ``mine`` is active_registrations_for_user(...). The peer educator event
    endpoints can call this to fill in each shift's ``eligibility``.
    """
    own = next((item for item in mine if item["shift_id"] == shift["shift_id"]), None)
    if own:
        return {"code": "registered", "registration_id": own["registration_id"]}
    if event["status"] == "cancelled":
        return {"code": "event_cancelled"}
    if event["status"] != "published" or campus_time.has_shift_started(shift, now):
        return {"code": "closed"}
    if any(item["event_id"] == event["event_id"] for item in mine):
        return {"code": "registered_other_shift"}
    if active_count >= shift["capacity"]:
        return {"code": "full"}
    conflict = next((item for item in mine if campus_time.shifts_overlap(shift, item)), None)
    if conflict:
        return {
            "code": "conflict",
            "conflict": {
                "event_id": conflict["event_id"],
                "title": conflict["title"],
                "shift_date": campus_time.iso_date(conflict["shift_date"]),
                "start_time": campus_time.hh_mm(conflict["start_time"]),
                "end_time": campus_time.hh_mm(conflict["end_time"]),
            },
        }
    return {"code": "open"}


def eligibility_error(eligibility):
    code = eligibility["code"]
    if code == "conflict":
        conflict = eligibility["conflict"]
        start = time.fromisoformat(conflict["start_time"])
        end = time.fromisoformat(conflict["end_time"])
        message = (
            f"This shift overlaps your registration for {conflict['title']} on "
            f"{campus_time.format_date(date.fromisoformat(conflict['shift_date']))}, "
            f"{campus_time.format_time_range(start, end)}."
        )
    else:
        message = ELIGIBILITY_MESSAGES[code]
    return ApiError(409, message, code=code)


# ---------- Formatting ----------

def registration_category(row, now):
    if row["status"] == "cancelled":
        return "cancelled_by_user"
    if row["event_status"] == "cancelled":
        return "event_cancelled"
    if campus_time.has_shift_ended(row, now):
        return "past"
    if campus_time.has_shift_started(row, now):
        return "in_progress"
    return "upcoming"


def format_location(row):
    if row.get("location_id") is None:
        return None
    return {
        "location_id": row["location_id"],
        "building": row["building"],
        "room_or_area": row["room_or_area"],
        "directions": row["directions"],
        "map_url": row["map_url"],
    }


def format_attendance(row):
    if row.get("attendance_id") is None:
        return None
    return {
        "attendance_id": row["attendance_id"],
        "participation_status": row["participation_status"],
        "credited_minutes": row["credited_minutes"],
    }


def format_registration(row, now):
    """MyRegistration from API_CONTRACT.md, plus the attendance record (or null)."""
    category = registration_category(row, now)
    return {
        "registration_id": row["registration_id"],
        "status": row["status"],
        "category": category,
        "can_cancel": category == "upcoming",
        "created_at": row["created_at"].isoformat(),
        "cancelled_at": row["cancelled_at"].isoformat() if row["cancelled_at"] else None,
        "event": {
            "event_id": row["event_id"],
            "title": row["title"],
            "status": row["event_status"],
            "is_urgent": row["is_urgent"],
            "cancelled_at": row["event_cancelled_at"].isoformat() if row["event_cancelled_at"] else None,
        },
        "shift": {
            "shift_id": row["shift_id"],
            "shift_date": campus_time.iso_date(row["shift_date"]),
            "start_time": campus_time.hh_mm(row["start_time"]),
            "end_time": campus_time.hh_mm(row["end_time"]),
        },
        "location": format_location(row),
        "attendance": format_attendance(row),
    }


def fetch_registration(cursor, registration_id):
    cursor.execute(REGISTRATION_SELECT + " WHERE registrations.registration_id = %s", (registration_id,))
    return format_registration(cursor.fetchone(), campus_time.campus_now())


# ---------- Endpoints ----------

@router.get("/me/registrations")
def get_my_registrations(user_id: UUID = Depends(get_authenticated_user_id)):
    """Every registration the user has made, active or cancelled, oldest shift first."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id, "view their registrations")
            cursor.execute(
                REGISTRATION_SELECT
                + """
                WHERE registrations.user_id = %s
                ORDER BY shifts.shift_date, shifts.start_time, shifts.end_time,
                         registrations.created_at, registrations.registration_id
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

    now = campus_time.campus_now()
    return [format_registration(row, now) for row in rows]


@router.post("/shifts/{shift_id}/registrations", status_code=201)
def register_for_shift(shift_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id)

            # Lock 1: this user's sign-ups run one at a time (one per event, no overlaps).
            cursor.execute(
                "SELECT user_id FROM public.users WHERE user_id = %s FOR NO KEY UPDATE",
                (user_id,),
            )

            cursor.execute("SELECT event_id FROM public.shifts WHERE shift_id = %s", (shift_id,))
            found = cursor.fetchone()
            if found is None:
                raise ApiError(404, "Shift not found.")

            # Lock 2: the event, shared. Cancelling or editing it waits for this sign-up.
            cursor.execute(
                """
                SELECT event_id, title, status
                FROM public.events
                WHERE event_id = %s
                FOR SHARE
                """,
                (found["event_id"],),
            )
            event = cursor.fetchone()
            # Drafts are hidden from peer educators.
            if event is None or event["status"] == "draft":
                raise ApiError(404, "Shift not found.")

            # Lock 3: the shift. Sign-ups for it run one at a time, so capacity can't be exceeded.
            cursor.execute(
                """
                SELECT shift_id, event_id, shift_date, start_time, end_time, capacity
                FROM public.shifts
                WHERE shift_id = %s AND event_id = %s
                FOR UPDATE
                """,
                (shift_id, event["event_id"]),
            )
            shift = cursor.fetchone()
            if shift is None:
                raise ApiError(404, "Shift not found.")

            # Counted after the locks, so no other sign-up can change it before we insert.
            cursor.execute(
                """
                SELECT COUNT(*)::int AS active
                FROM public.registrations
                WHERE shift_id = %s AND status = 'active'
                """,
                (shift_id,),
            )
            active_count = cursor.fetchone()["active"]
            mine = active_registrations_for_user(cursor, user_id)

            eligibility = shift_eligibility(event, shift, active_count, mine, campus_time.campus_now())
            if eligibility["code"] != "open":
                raise eligibility_error(eligibility)

            try:
                # Always a new row: a cancelled registration is never reactivated.
                cursor.execute(
                    """
                    INSERT INTO public.registrations (shift_id, event_id, user_id)
                    VALUES (%s, %s, %s)
                    RETURNING registration_id
                    """,
                    (shift_id, event["event_id"], user_id),
                )
            except psycopg.errors.UniqueViolation:
                # The partial unique indexes back up the rules above; with the locks
                # held this shouldn't happen, but never turn it into a 500.
                raise ApiError(409, ELIGIBILITY_MESSAGES["registered_other_shift"], code="registered_other_shift")

            registration_id = cursor.fetchone()["registration_id"]
            return fetch_registration(cursor, registration_id)


@router.post("/registrations/{registration_id}/cancel")
def cancel_registration(registration_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id, "cancel registrations")

            cursor.execute(
                """
                SELECT registrations.registration_id, registrations.user_id, registrations.status,
                       events.status AS event_status,
                       shifts.shift_date, shifts.start_time, shifts.end_time
                FROM public.registrations
                JOIN public.shifts ON shifts.shift_id = registrations.shift_id
                JOIN public.events ON events.event_id = shifts.event_id
                WHERE registrations.registration_id = %s
                FOR UPDATE OF registrations
                """,
                (registration_id,),
            )
            registration = cursor.fetchone()

            # Someone else's registration looks the same as a missing one.
            if registration is None or registration["user_id"] != user_id:
                raise ApiError(404, "Registration not found.")
            if registration["status"] != "active":
                raise ApiError(409, "This registration is already cancelled.")
            if registration["event_status"] == "cancelled":
                raise ApiError(409, "This event was cancelled, so there's nothing to cancel.")
            if campus_time.has_shift_started(registration, campus_time.campus_now()):
                raise ApiError(409, "This shift has already started, so it can't be cancelled here.")

            # The row is kept as history; changing the status frees the spot.
            cursor.execute(
                """
                UPDATE public.registrations
                SET status = 'cancelled', cancelled_at = now()
                WHERE registration_id = %s
                """,
                (registration_id,),
            )

            return fetch_registration(cursor, registration_id)
