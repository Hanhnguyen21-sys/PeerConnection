from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_supervisor
from app.routes.services import events_service, shifts_service

router = APIRouter(prefix="/api", tags=["Events"])

# Compatibility exports for routes that already depend on these helpers.
format_shift = shifts_service.format_shift
fetch_shifts = shifts_service.fetch_shifts
is_valid_date = shifts_service.is_valid_date
campus_now = events_service.campus_now
has_shift_ended = events_service.has_shift_ended
fetch_event_row = events_service.fetch_event_row
event_detail = events_service.event_detail


# Fields are loosely typed so bad values come back as per-field messages the
# form can show, instead of FastAPI's generic validation error.
class EventInput(BaseModel):
    title: Optional[str] = ""
    description: Optional[str] = ""
    is_urgent: bool = False
    shifts: List[shifts_service.ShiftInput] = []


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
            shifts_by_event = shifts_service.fetch_shifts(
                cursor,
                [event["event_id"] for event in events],
            )

    now = events_service.campus_now()
    results = []
    for event in events:
        shifts = shifts_by_event[event["event_id"]]
        if (from_date or to_date) and not any(
            (not from_date or shift["shift_date"] >= from_date)
            and (not to_date or shift["shift_date"] <= to_date)
            for shift in shifts
        ):
            continue
        summary = events_service.summarize_event(event, shifts, now)
        if events_service.matches_status(summary, status):
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
            return events_service.event_detail(cursor, event_id)


@router.post("/events", status_code=201)
def create_event(event: EventInput, user_id: UUID = Depends(get_authenticated_user_id)):
    cleaned = events_service.clean_event(event)
    for shift in cleaned["shifts"]:
        shift["shift_id"] = None

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            events_service.validate_event(cursor, cleaned)

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
                shifts_service.insert_shift(cursor, event_id, shift)

            return events_service.event_detail(cursor, event_id)


@router.put("/events/{event_id}")
def update_event(event_id: int, event: EventInput, user_id: UUID = Depends(get_authenticated_user_id)):
    cleaned = events_service.clean_event(event)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)

            # Lock the event so two edits can't interleave.
            existing_event = events_service.fetch_event_row(
                cursor,
                event_id,
                for_update=True,
            )
            if existing_event["status"] == "cancelled":
                raise ApiError(409, "Cancelled events can't be edited.")

            existing_shifts = shifts_service.fetch_shifts(cursor, [event_id])[event_id]
            locked_shifts = {shift["shift_id"]: shift for shift in existing_shifts}

            for shift in cleaned["shifts"]:
                if shift["shift_id"] is not None and shift["shift_id"] not in locked_shifts:
                    raise ApiError(422, "One of the shifts doesn't belong to this event.")

            kept_ids = {shift["shift_id"] for shift in cleaned["shifts"] if shift["shift_id"] is not None}
            removed = [shift for shift in existing_shifts if shift["shift_id"] not in kept_ids]
            if any(shift["active_registrations"] > 0 for shift in removed):
                raise ApiError(409, "Shifts with active registrations can't be removed.")

            events_service.validate_event(cursor, cleaned, locked_shifts)

            cursor.execute(
                """
                UPDATE public.events
                SET title = %s, description = %s, is_urgent = %s, updated_at = now()
                WHERE event_id = %s
                """,
                (cleaned["title"], cleaned["description"], cleaned["is_urgent"], event_id),
            )

            if removed:
                shifts_service.delete_shifts(
                    cursor,
                    [shift["shift_id"] for shift in removed],
                )

            for shift in cleaned["shifts"]:
                if shift["shift_id"] is None:
                    shifts_service.insert_shift(cursor, event_id, shift)
                else:
                    shifts_service.update_shift(
                        cursor,
                        shift["shift_id"],
                        shift,
                    )

            return events_service.event_detail(cursor, event_id)


@router.post("/events/{event_id}/cancel")
def cancel_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            events_service.fetch_event_row(cursor, event_id)

            # Shifts and registrations are kept; cancelling only blocks new sign-ups.
            cursor.execute(
                """
                UPDATE public.events
                SET status = 'cancelled', cancelled_at = now(), updated_at = now()
                WHERE event_id = %s AND status <> 'cancelled'
                """,
                (event_id,),
            )

            return events_service.event_detail(cursor, event_id)


@router.delete("/events/{event_id}", status_code=204)
def delete_draft_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id)
            event = events_service.event_detail(cursor, event_id)

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
            events_service.fetch_event_row(cursor, event_id)

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
            "shift": shifts_service.format_shift(
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
