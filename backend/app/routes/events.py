import re
from datetime import date, datetime
from typing import List, Optional, Union
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_supervisor

router = APIRouter(prefix="/api", tags=["Events"])

# Shift dates and times are campus wall-clock values, like the frontend.
CAMPUS_TIME_ZONE = ZoneInfo("America/Los_Angeles")
MAX_TITLE_LENGTH = 120
MAX_CAPACITY = 500
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# Fields are loosely typed so bad values come back as per-field messages the
# form can show, instead of FastAPI's generic validation error.
class ShiftInput(BaseModel):
    shift_id: Optional[int] = None
    shift_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location_id: Optional[Union[int, str]] = None
    capacity: Optional[Union[int, str]] = None


class EventInput(BaseModel):
    title: Optional[str] = ""
    description: Optional[str] = ""
    is_urgent: bool = False
    shifts: List[ShiftInput] = []


# ---------- Reading ----------

def campus_now():
    now = datetime.now(CAMPUS_TIME_ZONE)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


def format_shift(row):
    return {
        **row,
        "shift_date": row["shift_date"].isoformat(),
        "start_time": row["start_time"].strftime("%H:%M"),
        "end_time": row["end_time"].strftime("%H:%M"),
    }


def has_shift_ended(shift, now):
    today, time_now = now
    return shift["shift_date"] < today or (
        shift["shift_date"] == today and shift["end_time"] <= time_now
    )


def fetch_shifts(cursor, event_ids):
    """Returns {event_id: [shift, ...]} sorted by date and time, with active sign-up counts."""
    shifts_by_event = {event_id: [] for event_id in event_ids}
    if not event_ids:
        return shifts_by_event

    cursor.execute(
        """
        SELECT shifts.shift_id, shifts.event_id, shifts.shift_date, shifts.start_time,
               shifts.end_time, shifts.capacity, shifts.location_id,
               (
                   SELECT COUNT(*)::int
                   FROM public.registrations
                   WHERE registrations.shift_id = shifts.shift_id
                     AND registrations.status = 'active'
               ) AS active_registrations
        FROM public.shifts
        WHERE shifts.event_id = ANY(%s)
        ORDER BY shifts.shift_date, shifts.start_time, shifts.end_time, shifts.shift_id
        """,
        (list(event_ids),),
    )

    for row in cursor.fetchall():
        shifts_by_event[row["event_id"]].append(format_shift(row))

    return shifts_by_event


def summarize_event(event, shifts, now):
    upcoming = [shift for shift in shifts if not has_shift_ended(shift, now)]
    active_registrations = sum(shift["active_registrations"] for shift in shifts)

    return {
        "event_id": event["event_id"],
        "title": event["title"],
        "description": event["description"],
        "is_urgent": event["is_urgent"],
        "status": event["status"],
        "schedule_status": "upcoming" if upcoming else "past",
        "first_shift_date": shifts[0]["shift_date"] if shifts else None,
        "last_shift_date": shifts[-1]["shift_date"] if shifts else None,
        "next_shift_date": upcoming[0]["shift_date"] if upcoming else None,
        "shift_count": len(shifts),
        "active_registrations": active_registrations,
        "total_capacity": sum(shift["capacity"] for shift in shifts),
        "understaffed_shifts": sum(
            1 for shift in shifts if shift["active_registrations"] < shift["capacity"]
        ),
        "created_at": event["created_at"].isoformat(),
        "updated_at": event["updated_at"].isoformat(),
        "cancelled_at": event["cancelled_at"].isoformat() if event["cancelled_at"] else None,
    }


def matches_status(summary, status):
    if status == "cancelled":
        return summary["status"] == "cancelled"
    if status in ("upcoming", "past"):
        return summary["status"] != "cancelled" and summary["schedule_status"] == status
    return True


def fetch_event_row(cursor, event_id, for_update=False):
    cursor.execute(
        """
        SELECT event_id, title, description, is_urgent, status, organizer_id,
               created_at, updated_at, cancelled_at
        FROM public.events
        WHERE event_id = %s
        """ + (" FOR UPDATE" if for_update else ""),
        (event_id,),
    )

    event = cursor.fetchone()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


def event_detail(cursor, event_id):
    event = fetch_event_row(cursor, event_id)
    shifts = fetch_shifts(cursor, [event_id])[event_id]

    cursor.execute(
        """
        SELECT user_id, name
        FROM public.users
        WHERE user_id = %s
        """,
        (event["organizer_id"],),
    )
    organizer = cursor.fetchone()

    cursor.execute(
        """
        SELECT location_id, building, room_or_area, directions, map_url
        FROM public.locations
        WHERE location_id = ANY(%s)
        """,
        ([shift["location_id"] for shift in shifts],),
    )
    locations = {row["location_id"]: row for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM public.registrations
            JOIN public.shifts ON shifts.shift_id = registrations.shift_id
            WHERE shifts.event_id = %s
        ) AS has_history
        """,
        (event_id,),
    )
    has_history = cursor.fetchone()["has_history"]

    return {
        **summarize_event(event, shifts, campus_now()),
        "organizer": {"user_id": str(organizer["user_id"]), "name": organizer["name"]}
        if organizer
        else None,
        "has_registration_history": has_history,
        "shifts": [
            {
                "shift_id": shift["shift_id"],
                "shift_date": shift["shift_date"],
                "start_time": shift["start_time"],
                "end_time": shift["end_time"],
                "capacity": shift["capacity"],
                "location_id": shift["location_id"],
                "location": locations.get(shift["location_id"]),
                "active_registrations": shift["active_registrations"],
                "remaining_spots": max(shift["capacity"] - shift["active_registrations"], 0),
            }
            for shift in shifts
        ],
    }


# ---------- Validation (mirrors validateEventInput in frontend/src/lib/validation.js) ----------

def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def is_valid_date(value):
    if not DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def parse_whole_number(value):
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None


def clean_event(event: EventInput):
    return {
        "title": normalize_text(event.title),
        "description": (event.description or "").strip(),
        "is_urgent": bool(event.is_urgent),
        "shifts": [
            {
                "shift_id": shift.shift_id,
                "shift_date": (shift.shift_date or "").strip(),
                "start_time": (shift.start_time or "").strip(),
                "end_time": (shift.end_time or "").strip(),
                "location_id": parse_whole_number(shift.location_id),
                "location_given": str(shift.location_id if shift.location_id is not None else "").strip() != "",
                "capacity": parse_whole_number(shift.capacity),
            }
            for shift in event.shifts
        ],
    }


def validate_event(cursor, cleaned, locked_shifts=None):
    locked_shifts = locked_shifts or {}
    errors = {"shiftFields": {}}

    if not cleaned["title"]:
        errors["title"] = "Enter an event title."
    elif len(cleaned["title"]) > MAX_TITLE_LENGTH:
        errors["title"] = f"Keep the title under {MAX_TITLE_LENGTH} characters."

    if not cleaned["shifts"]:
        errors["shifts"] = "Add at least one shift."

    cursor.execute("SELECT location_id FROM public.locations")
    location_ids = {row["location_id"] for row in cursor.fetchall()}

    for index, shift in enumerate(cleaned["shifts"]):
        field_errors = {}
        locked = locked_shifts.get(shift["shift_id"]) if shift["shift_id"] is not None else None
        active_registrations = locked["active_registrations"] if locked else 0

        if not shift["shift_date"]:
            field_errors["shift_date"] = "Choose a date."
        elif not is_valid_date(shift["shift_date"]):
            field_errors["shift_date"] = "Enter a valid date."

        if not shift["start_time"]:
            field_errors["start_time"] = "Choose a start time."
        elif not TIME_PATTERN.match(shift["start_time"]):
            field_errors["start_time"] = "Enter a valid time."

        if not shift["end_time"]:
            field_errors["end_time"] = "Choose an end time."
        elif not TIME_PATTERN.match(shift["end_time"]):
            field_errors["end_time"] = "Enter a valid time."
        elif "start_time" not in field_errors and shift["end_time"] <= shift["start_time"]:
            field_errors["end_time"] = "End time must be after the start time on the same day."

        if not shift["location_given"]:
            field_errors["location_id"] = "Choose a location."
        elif shift["location_id"] not in location_ids:
            field_errors["location_id"] = "Choose a location from the list."

        capacity = shift["capacity"]
        if capacity is None or capacity < 1:
            field_errors["capacity"] = "Enter a whole number of 1 or more."
        elif capacity > MAX_CAPACITY:
            field_errors["capacity"] = f"Capacity can't be more than {MAX_CAPACITY}."
        elif capacity < active_registrations:
            field_errors["capacity"] = (
                f"Capacity can't be lower than the {active_registrations} active registrations."
            )

        if locked and active_registrations > 0:
            moved = (
                shift["shift_date"] != locked["shift_date"]
                or shift["start_time"] != locked["start_time"]
                or shift["end_time"] != locked["end_time"]
            )
            if moved:
                field_errors["shift_date"] = (
                    "This shift has active registrations, so its date and time can't change yet."
                )

        if field_errors:
            errors["shiftFields"][str(index)] = field_errors

    if errors.get("title") or errors.get("shifts") or errors["shiftFields"]:
        raise ApiError(422, "Please fix the highlighted fields.", errors)


def insert_shift(cursor, event_id, shift):
    cursor.execute(
        """
        INSERT INTO public.shifts (event_id, location_id, shift_date, start_time, end_time, capacity)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            event_id,
            shift["location_id"],
            shift["shift_date"],
            shift["start_time"],
            shift["end_time"],
            shift["capacity"],
        ),
    )


# ---------- Endpoints ----------

@router.get("/events")
def get_events(
    search: str = "",
    status: str = "all",
    # "from" is a Python keyword, so the parameters are renamed here.
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user_id: UUID = Depends(get_authenticated_user_id),
):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)

            cursor.execute(
                """
                SELECT event_id, title, description, is_urgent, status, organizer_id,
                       created_at, updated_at, cancelled_at
                FROM public.events
                WHERE title ILIKE %s
                """,
                (f"%{search.strip()}%",),
            )
            events = cursor.fetchall()
            shifts_by_event = fetch_shifts(cursor, [event["event_id"] for event in events])

    now = campus_now()
    results = []
    for event in events:
        shifts = shifts_by_event[event["event_id"]]
        if (from_date or to_date) and not any(
            (not from_date or shift["shift_date"] >= from_date)
            and (not to_date or shift["shift_date"] <= to_date)
            for shift in shifts
        ):
            continue
        summary = summarize_event(event, shifts, now)
        if matches_status(summary, status):
            results.append(summary)

    # Upcoming events first (soonest next shift), then everything else (most recent first).
    def is_upcoming(summary):
        return summary["status"] != "cancelled" and summary["schedule_status"] == "upcoming"

    upcoming = sorted(
        (summary for summary in results if is_upcoming(summary)),
        key=lambda summary: summary["next_shift_date"] or "",
    )
    others = sorted(
        (summary for summary in results if not is_upcoming(summary)),
        key=lambda summary: summary["last_shift_date"] or "",
        reverse=True,
    )
    return upcoming + others


@router.get("/events/{event_id}")
def get_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            return event_detail(cursor, event_id)


@router.post("/events", status_code=201)
def create_event(event: EventInput, user_id: UUID = Depends(get_authenticated_user_id)):
    cleaned = clean_event(event)
    for shift in cleaned["shifts"]:
        shift["shift_id"] = None

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            validate_event(cursor, cleaned)

            cursor.execute(
                """
                INSERT INTO public.events (title, description, is_urgent, status, organizer_id)
                VALUES (%s, %s, %s, 'published', %s)
                RETURNING event_id
                """,
                (cleaned["title"], cleaned["description"], cleaned["is_urgent"], user_id),
            )
            event_id = cursor.fetchone()["event_id"]

            for shift in cleaned["shifts"]:
                insert_shift(cursor, event_id, shift)

            return event_detail(cursor, event_id)


@router.put("/events/{event_id}")
def update_event(event_id: int, event: EventInput, user_id: UUID = Depends(get_authenticated_user_id)):
    cleaned = clean_event(event)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)

            # Lock the event so two edits can't interleave.
            existing_event = fetch_event_row(cursor, event_id, for_update=True)
            if existing_event["status"] == "cancelled":
                raise ApiError(409, "Cancelled events can't be edited.")

            existing_shifts = fetch_shifts(cursor, [event_id])[event_id]
            locked_shifts = {shift["shift_id"]: shift for shift in existing_shifts}

            for shift in cleaned["shifts"]:
                if shift["shift_id"] is not None and shift["shift_id"] not in locked_shifts:
                    raise ApiError(422, "One of the shifts doesn't belong to this event.")

            kept_ids = {shift["shift_id"] for shift in cleaned["shifts"] if shift["shift_id"] is not None}
            removed = [shift for shift in existing_shifts if shift["shift_id"] not in kept_ids]
            if any(shift["active_registrations"] > 0 for shift in removed):
                raise ApiError(409, "Shifts with active registrations can't be removed.")

            validate_event(cursor, cleaned, locked_shifts)

            cursor.execute(
                """
                UPDATE public.events
                SET title = %s, description = %s, is_urgent = %s, updated_at = now()
                WHERE event_id = %s
                """,
                (cleaned["title"], cleaned["description"], cleaned["is_urgent"], event_id),
            )

            if removed:
                cursor.execute(
                    "DELETE FROM public.shifts WHERE shift_id = ANY(%s)",
                    ([shift["shift_id"] for shift in removed],),
                )

            for shift in cleaned["shifts"]:
                if shift["shift_id"] is None:
                    insert_shift(cursor, event_id, shift)
                else:
                    cursor.execute(
                        """
                        UPDATE public.shifts
                        SET location_id = %s, shift_date = %s, start_time = %s,
                            end_time = %s, capacity = %s
                        WHERE shift_id = %s
                        """,
                        (
                            shift["location_id"],
                            shift["shift_date"],
                            shift["start_time"],
                            shift["end_time"],
                            shift["capacity"],
                            shift["shift_id"],
                        ),
                    )

            return event_detail(cursor, event_id)


@router.post("/events/{event_id}/cancel")
def cancel_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            fetch_event_row(cursor, event_id)

            # Shifts and registrations are kept; cancelling only blocks new sign-ups.
            cursor.execute(
                """
                UPDATE public.events
                SET status = 'cancelled', cancelled_at = now(), updated_at = now()
                WHERE event_id = %s AND status <> 'cancelled'
                """,
                (event_id,),
            )

            return event_detail(cursor, event_id)


@router.delete("/events/{event_id}", status_code=204)
def delete_draft_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            event = event_detail(cursor, event_id)

            if event["status"] != "draft" or event["has_registration_history"]:
                raise ApiError(409, "Only draft events with no registration history can be deleted.")

            # Shifts are removed by ON DELETE CASCADE.
            cursor.execute("DELETE FROM public.events WHERE event_id = %s", (event_id,))

    return Response(status_code=204)


@router.get("/events/{event_id}/participants")
def get_participants(
    event_id: int,
    shift_id: Optional[int] = None,
    user_id: UUID = Depends(get_authenticated_user_id),
):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            fetch_event_row(cursor, event_id)

            cursor.execute(
                """
                SELECT registrations.registration_id, registrations.created_at,
                       users.user_id, users.name, users.email,
                       shifts.shift_id, shifts.shift_date, shifts.start_time, shifts.end_time
                FROM public.registrations
                JOIN public.shifts ON shifts.shift_id = registrations.shift_id
                JOIN public.users ON users.user_id = registrations.user_id
                WHERE shifts.event_id = %s
                  AND registrations.status = 'active'
                  AND (%s::bigint IS NULL OR shifts.shift_id = %s::bigint)
                ORDER BY shifts.shift_date, shifts.start_time, shifts.end_time, users.name
                """,
                (event_id, shift_id, shift_id),
            )
            rows = cursor.fetchall()

    return [
        {
            "registration_id": row["registration_id"],
            "registered_at": row["created_at"].isoformat(),
            "user": {"user_id": str(row["user_id"]), "name": row["name"], "email": row["email"]},
            "shift": format_shift(
                {
                    "shift_id": row["shift_id"],
                    "shift_date": row["shift_date"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                }
            ),
        }
        for row in rows
    ]
