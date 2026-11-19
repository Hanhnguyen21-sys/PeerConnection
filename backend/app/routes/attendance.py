"""Attendance: supervisors record whether each signed-up peer educator attended a shift.

Follows the project proposal's table:
Attendance(AttendanceID, RegistrationID, ParticipationStatus, CreditedMinutes).
- Each registration has at most one attendance record (registration_id is unique).
- participation_status is "attended" or "absent".
- credited_minutes is 0 or more, and always 0 when absent.

Proposed rules (see API_CONTRACT.md, "Attendance"):
- Only supervisors record attendance. Peer educators read their own history.
- Attendance can only be recorded for active registrations on published
  events, once the shift has started.
- credited_minutes defaults to the shift's length and can't exceed it.
"""
import re
from datetime import date
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from psycopg.rows import dict_row

from app import campus_time
from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_peer_educator, require_supervisor
from app.routes.registrations import format_location

router = APIRouter(prefix="/api", tags=["Attendance"])

PARTICIPATION_STATUSES = ("attended", "absent")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# Values are loosely typed so bad input comes back as per-field messages
# instead of FastAPI's generic validation error, like EventInput.
class AttendanceInput(BaseModel):
    participation_status: Any = None
    credited_minutes: Any = None


class RosterRecordInput(AttendanceInput):
    registration_id: Any = None


class RosterInput(BaseModel):
    records: List[RosterRecordInput] = []


# ---------- Validation ----------

def parse_whole_number(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None


def clean_attendance(entry: AttendanceInput, max_minutes: int):
    """Returns (cleaned, field_errors)."""
    errors = {}

    status = entry.participation_status.strip().lower() if isinstance(entry.participation_status, str) else None
    if status not in PARTICIPATION_STATUSES:
        errors["participation_status"] = 'Choose "attended" or "absent".'

    minutes_given = entry.credited_minutes is not None and str(entry.credited_minutes).strip() != ""
    minutes = parse_whole_number(entry.credited_minutes) if minutes_given else None
    if minutes_given and minutes is None:
        errors["credited_minutes"] = "Enter a whole number of minutes, 0 or more."
    elif minutes is not None and minutes > max_minutes:
        errors["credited_minutes"] = f"Credited minutes can't be more than the shift's {max_minutes} minutes."
    elif status == "absent" and minutes:
        errors["credited_minutes"] = "Absent participants can't be credited minutes."

    if status == "absent":
        minutes = 0
    elif minutes is None:
        minutes = max_minutes

    return {"participation_status": status, "credited_minutes": minutes}, errors


def recording_blocked_reason(event_status, shift, now) -> Optional[str]:
    """Why attendance can't be recorded for this shift right now, or None."""
    if event_status == "cancelled":
        return "This event was cancelled, so attendance can't be changed."
    if event_status != "published":
        return "Attendance can only be recorded for published events."
    if not campus_time.has_shift_started(shift, now):
        return "Attendance can be recorded once the shift starts."
    return None


def is_valid_date(value) -> bool:
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


# ---------- Reading ----------

def fetch_shift_with_event(cursor, shift_id, for_update=False):
    cursor.execute(
        """
        SELECT shifts.shift_id, shifts.event_id, shifts.shift_date, shifts.start_time,
               shifts.end_time, shifts.capacity,
               events.title, events.status AS event_status,
               locations.location_id, locations.building, locations.room_or_area,
               locations.directions, locations.map_url
        FROM public.shifts
        JOIN public.events ON events.event_id = shifts.event_id
        LEFT JOIN public.locations ON locations.location_id = shifts.location_id
        WHERE shifts.shift_id = %s
        """ + (" FOR SHARE OF shifts, events" if for_update else ""),
        (shift_id,),
    )
    shift = cursor.fetchone()
    if shift is None:
        raise ApiError(404, "Shift not found.")
    return shift


def fetch_registration_for_attendance(cursor, registration_id):
    cursor.execute(
        """
        SELECT registrations.registration_id, registrations.status,
               shifts.shift_id, shifts.shift_date, shifts.start_time, shifts.end_time,
               events.status AS event_status
        FROM public.registrations
        JOIN public.shifts ON shifts.shift_id = registrations.shift_id
        JOIN public.events ON events.event_id = shifts.event_id
        WHERE registrations.registration_id = %s
        FOR UPDATE OF registrations
        """,
        (registration_id,),
    )
    registration = cursor.fetchone()
    if registration is None:
        raise ApiError(404, "Registration not found.")
    return registration


def shift_roster(cursor, shift_id):
    """The shift, its active registrations, and each one's attendance record (or null)."""
    shift = fetch_shift_with_event(cursor, shift_id)
    now = campus_time.campus_now()

    cursor.execute(
        """
        SELECT registrations.registration_id, registrations.created_at,
               users.user_id, users.name, users.email,
               attendance.attendance_id, attendance.participation_status,
               attendance.credited_minutes
        FROM public.registrations
        JOIN public.users ON users.user_id = registrations.user_id
        LEFT JOIN public.attendance ON attendance.registration_id = registrations.registration_id
        WHERE registrations.shift_id = %s AND registrations.status = 'active'
        ORDER BY users.name, registrations.registration_id
        """,
        (shift_id,),
    )
    rows = cursor.fetchall()

    roster = [
        {
            "registration_id": row["registration_id"],
            "registered_at": row["created_at"].isoformat(),
            "user": {"user_id": str(row["user_id"]), "name": row["name"], "email": row["email"]},
            "attendance": None
            if row["attendance_id"] is None
            else {
                "attendance_id": row["attendance_id"],
                "participation_status": row["participation_status"],
                "credited_minutes": row["credited_minutes"],
            },
        }
        for row in rows
    ]
    marked = [entry["attendance"] for entry in roster if entry["attendance"]]
    blocked = recording_blocked_reason(shift["event_status"], shift, now)

    return {
        "shift": {
            "shift_id": shift["shift_id"],
            "shift_date": campus_time.iso_date(shift["shift_date"]),
            "start_time": campus_time.hh_mm(shift["start_time"]),
            "end_time": campus_time.hh_mm(shift["end_time"]),
            "capacity": shift["capacity"],
            "duration_minutes": campus_time.shift_minutes(shift),
            "has_started": campus_time.has_shift_started(shift, now),
            "has_ended": campus_time.has_shift_ended(shift, now),
            "location": format_location(shift),
        },
        "event": {"event_id": shift["event_id"], "title": shift["title"], "status": shift["event_status"]},
        "can_record": blocked is None,
        "blocked_reason": blocked,
        "summary": {
            "registered": len(roster),
            "attended": sum(1 for record in marked if record["participation_status"] == "attended"),
            "absent": sum(1 for record in marked if record["participation_status"] == "absent"),
            "unmarked": len(roster) - len(marked),
            "credited_minutes": sum(record["credited_minutes"] for record in marked),
        },
        "roster": roster,
    }


def upsert_attendance(cursor, registration_id, cleaned):
    cursor.execute(
        """
        INSERT INTO public.attendance (registration_id, participation_status, credited_minutes)
        VALUES (%s, %s, %s)
        ON CONFLICT (registration_id) DO UPDATE
        SET participation_status = EXCLUDED.participation_status,
            credited_minutes = EXCLUDED.credited_minutes
        RETURNING attendance_id, registration_id, participation_status, credited_minutes
        """,
        (registration_id, cleaned["participation_status"], cleaned["credited_minutes"]),
    )
    return cursor.fetchone()


# ---------- Supervisor endpoints ----------

@router.get("/shifts/{shift_id}/attendance")
def get_shift_attendance(shift_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "view attendance")
            return shift_roster(cursor, shift_id)


@router.put("/shifts/{shift_id}/attendance")
def record_shift_attendance(
    shift_id: int,
    body: RosterInput,
    user_id: UUID = Depends(get_authenticated_user_id),
):
    """Records attendance for several registrations on one shift. All or nothing.

    Registrations that aren't listed are left as they are.
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "record attendance")
            shift = fetch_shift_with_event(cursor, shift_id, for_update=True)

            blocked = recording_blocked_reason(shift["event_status"], shift, campus_time.campus_now())
            if blocked:
                raise ApiError(409, blocked)
            if not body.records:
                raise ApiError(422, "Add at least one attendance record.", {"records": "Add at least one attendance record."})

            cursor.execute(
                """
                SELECT registration_id, status
                FROM public.registrations
                WHERE shift_id = %s
                FOR UPDATE
                """,
                (shift_id,),
            )
            registrations = {row["registration_id"]: row for row in cursor.fetchall()}
            max_minutes = campus_time.shift_minutes(shift)

            record_errors = {}
            cleaned_records = []
            seen = set()
            for index, record in enumerate(body.records):
                errors = {}
                registration_id = parse_whole_number(record.registration_id)
                if registration_id is None or registration_id not in registrations:
                    errors["registration_id"] = "This registration isn't on this shift."
                elif registration_id in seen:
                    errors["registration_id"] = "This registration is listed more than once."
                elif registrations[registration_id]["status"] != "active":
                    errors["registration_id"] = "Cancelled registrations can't have attendance."
                seen.add(registration_id)

                cleaned, field_errors = clean_attendance(record, max_minutes)
                errors.update(field_errors)
                if errors:
                    record_errors[str(index)] = errors
                else:
                    cleaned_records.append((registration_id, cleaned))

            if record_errors:
                raise ApiError(422, "Please fix the highlighted fields.", {"records": record_errors})

            for registration_id, cleaned in cleaned_records:
                upsert_attendance(cursor, registration_id, cleaned)

            return shift_roster(cursor, shift_id)


@router.put("/registrations/{registration_id}/attendance")
def record_attendance(
    registration_id: int,
    body: AttendanceInput,
    user_id: UUID = Depends(get_authenticated_user_id),
):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "record attendance")
            registration = fetch_registration_for_attendance(cursor, registration_id)

            if registration["status"] != "active":
                raise ApiError(409, "Cancelled registrations can't have attendance.")
            blocked = recording_blocked_reason(
                registration["event_status"], registration, campus_time.campus_now()
            )
            if blocked:
                raise ApiError(409, blocked)

            cleaned, errors = clean_attendance(body, campus_time.shift_minutes(registration))
            if errors:
                raise ApiError(422, "Please fix the highlighted fields.", errors)

            return upsert_attendance(cursor, registration_id, cleaned)


@router.delete("/registrations/{registration_id}/attendance", status_code=204)
def clear_attendance(registration_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    """Removes a registration's attendance record, so it shows as unmarked again."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "record attendance")
            registration = fetch_registration_for_attendance(cursor, registration_id)
            if registration["event_status"] == "cancelled":
                raise ApiError(409, "This event was cancelled, so attendance can't be changed.")

            cursor.execute(
                "DELETE FROM public.attendance WHERE registration_id = %s",
                (registration_id,),
            )

    return Response(status_code=204)


@router.get("/attendance/summary")
def get_attendance_summary(
    # "from" is a Python keyword, so the parameters are renamed here.
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user_id: UUID = Depends(get_authenticated_user_id),
):
    """Attendance totals per peer educator for shifts dated in [from, to]."""
    if not is_valid_date(from_date) or not is_valid_date(to_date) or from_date > to_date:
        raise ApiError(422, "Choose a valid date range.")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "view attendance")
            cursor.execute(
                """
                SELECT users.user_id, users.name, users.email,
                       COUNT(*) FILTER (WHERE attendance.participation_status = 'attended')::int
                           AS shifts_attended,
                       COUNT(*) FILTER (WHERE attendance.participation_status = 'absent')::int
                           AS shifts_absent,
                       COALESCE(SUM(attendance.credited_minutes), 0)::int AS credited_minutes
                FROM public.attendance
                JOIN public.registrations
                    ON registrations.registration_id = attendance.registration_id
                JOIN public.shifts ON shifts.shift_id = registrations.shift_id
                JOIN public.users ON users.user_id = registrations.user_id
                WHERE shifts.shift_date BETWEEN %s AND %s
                GROUP BY users.user_id, users.name, users.email
                ORDER BY credited_minutes DESC, users.name, users.user_id
                """,
                (from_date, to_date),
            )
            rows = cursor.fetchall()

    return {
        "range": {"from": from_date, "to": to_date},
        "totals": {
            "peer_educators": len(rows),
            "shifts_attended": sum(row["shifts_attended"] for row in rows),
            "shifts_absent": sum(row["shifts_absent"] for row in rows),
            "credited_minutes": sum(row["credited_minutes"] for row in rows),
        },
        "rows": [
            {
                "user": {"user_id": str(row["user_id"]), "name": row["name"], "email": row["email"]},
                "shifts_attended": row["shifts_attended"],
                "shifts_absent": row["shifts_absent"],
                "credited_minutes": row["credited_minutes"],
            }
            for row in rows
        ],
    }


# ---------- Peer educator endpoint ----------

@router.get("/me/attendance")
def get_my_attendance(user_id: UUID = Depends(get_authenticated_user_id)):
    """The user's participation history: every attendance record, newest shift first."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id, "view their participation history")
            cursor.execute(
                """
                SELECT attendance.attendance_id, attendance.participation_status,
                       attendance.credited_minutes, registrations.registration_id,
                       events.event_id, events.title,
                       shifts.shift_id, shifts.shift_date, shifts.start_time, shifts.end_time,
                       locations.location_id, locations.building, locations.room_or_area,
                       locations.directions, locations.map_url
                FROM public.attendance
                JOIN public.registrations
                    ON registrations.registration_id = attendance.registration_id
                JOIN public.shifts ON shifts.shift_id = registrations.shift_id
                JOIN public.events ON events.event_id = shifts.event_id
                LEFT JOIN public.locations ON locations.location_id = shifts.location_id
                WHERE registrations.user_id = %s
                ORDER BY shifts.shift_date DESC, shifts.start_time DESC, attendance.attendance_id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

    return {
        "summary": {
            "shifts_attended": sum(1 for row in rows if row["participation_status"] == "attended"),
            "shifts_absent": sum(1 for row in rows if row["participation_status"] == "absent"),
            "credited_minutes": sum(row["credited_minutes"] for row in rows),
        },
        "records": [
            {
                "attendance_id": row["attendance_id"],
                "registration_id": row["registration_id"],
                "participation_status": row["participation_status"],
                "credited_minutes": row["credited_minutes"],
                "event": {"event_id": row["event_id"], "title": row["title"]},
                "shift": {
                    "shift_id": row["shift_id"],
                    "shift_date": campus_time.iso_date(row["shift_date"]),
                    "start_time": campus_time.hh_mm(row["start_time"]),
                    "end_time": campus_time.hh_mm(row["end_time"]),
                },
                "location": format_location(row),
            }
            for row in rows
        ],
    }
