import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.errors import ApiError
from app.routes.services import shifts_service


CAMPUS_TIME_ZONE = ZoneInfo("America/Los_Angeles")
MAX_TITLE_LENGTH = 120

# gets current campus date and time
def campus_now():
    now = datetime.now(CAMPUS_TIME_ZONE)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")

# returns true when shift has ended
def has_shift_ended(shift, now):
    today, time_now = now
    return shift["shift_date"] < today or (
        shift["shift_date"] == today and shift["end_time"] <= time_now
    )

# returns a summary of the event
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
            1
            for shift in shifts
            if shift["active_registrations"] < shift["capacity"]
        ),
        "created_at": event["created_at"].isoformat(),
        "updated_at": event["updated_at"].isoformat(),
        "cancelled_at": (
            event["cancelled_at"].isoformat()
            if event["cancelled_at"]
            else None
        ),
    }

# filters event summary by requested status
def matches_status(summary, status):
    if status == "cancelled":
        return summary["status"] == "cancelled"
    if status in ("upcoming", "past"):
        return (
            summary["status"] != "cancelled"
            and summary["schedule_status"] == status
        )
    return True

# queries one event by id
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

# builds event response
def event_detail(cursor, event_id):
    event = fetch_event_row(cursor, event_id)
    shifts = shifts_service.fetch_shifts(cursor, [event_id])[event_id]

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
        "organizer": (
            {"user_id": str(organizer["user_id"]), "name": organizer["name"]}
            if organizer
            else None
        ),
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
                "remaining_spots": max(
                    shift["capacity"] - shift["active_registrations"],
                    0,
                ),
            }
            for shift in shifts
        ],
    }

# cleans event title
def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())

# cleans event input
def clean_event(event):
    return {
        "title": normalize_text(event.title),
        "description": (event.description or "").strip(),
        "is_urgent": bool(event.is_urgent),
        "shifts": shifts_service.clean_shifts(event.shifts),
    }

# validates event
def validate_event(cursor, cleaned, locked_shifts=None):
    errors = {}

    if not cleaned["title"]:
        errors["title"] = "Enter an event title."
    elif len(cleaned["title"]) > MAX_TITLE_LENGTH:
        errors["title"] = f"Keep the title under {MAX_TITLE_LENGTH} characters."

    if not cleaned["shifts"]:
        errors["shifts"] = "Add at least one shift."
    else:
        shift_errors = shifts_service.get_shift_validation_errors(
            cursor,
            cleaned["shifts"],
            locked_shifts,
        )
        if shift_errors:
            errors["shiftFields"] = shift_errors

    if errors:
        raise ApiError(422, "Please fix the highlighted fields.", errors)