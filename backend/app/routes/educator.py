"""Peer educator endpoints for browsing events: the list of events you can sign
up for, and one event with each shift's eligibility. The signed-in user is
always the one browsing; no endpoint accepts a user_id.

Signing up, cancelling and listing your registrations are in
registrations.py, which re-checks the same eligibility rules inside the
sign-up transaction.

Proposed rule (needs team confirmation): registration and cancellation close
when a shift starts.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.permissions import require_peer_educator
from app.routes.events import campus_now, fetch_shifts, format_shift, has_shift_ended

router = APIRouter(prefix="/api", tags=["Peer educators"])


# ---------- Helpers ----------

def has_shift_started(shift, now):
    today, time_now = now
    return shift["shift_date"] < today or (
        shift["shift_date"] == today and shift["start_time"] <= time_now
    )


def shifts_overlap(a, b):
    # Same-day intervals overlap when new_start < existing_end and
    # new_end > existing_start, so back-to-back shifts don't overlap.
    return (
        a["shift_date"] == b["shift_date"]
        and a["start_time"] < b["end_time"]
        and a["end_time"] > b["start_time"]
    )


def location_label(location):
    if location is None:
        return None
    return f"{location['building']} · {location['room_or_area']}"


def fetch_locations(cursor, location_ids):
    if not location_ids:
        return {}
    cursor.execute(
        """
        SELECT location_id, building, room_or_area, directions, map_url
        FROM public.locations
        WHERE location_id = ANY(%s)
        """,
        (list(location_ids),),
    )
    return {row["location_id"]: row for row in cursor.fetchall()}


def fetch_my_active(cursor, user_id):
    """The user's active registrations on events that aren't cancelled.
    Registrations on cancelled events stay as history but never block sign-ups."""
    cursor.execute(
        """
        SELECT registrations.registration_id, shifts.shift_id, shifts.event_id,
               shifts.shift_date, shifts.start_time, shifts.end_time, events.title
        FROM public.registrations
        JOIN public.shifts ON shifts.shift_id = registrations.shift_id
        JOIN public.events ON events.event_id = shifts.event_id
        WHERE registrations.user_id = %s
          AND registrations.status = 'active'
          AND events.status <> 'cancelled'
        """,
        (user_id,),
    )
    return [format_shift(row) for row in cursor.fetchall()]


def shift_eligibility(event, shift, mine, now):
    """Single source of truth for whether the user may register for a shift.
    Used to label buttons and re-checked inside the register transaction."""
    own = next((item for item in mine if item["shift_id"] == shift["shift_id"]), None)
    if own:
        return {"code": "registered", "registration_id": own["registration_id"]}
    if event["status"] == "cancelled":
        return {"code": "event_cancelled"}
    if event["status"] != "published" or has_shift_started(shift, now):
        return {"code": "closed"}
    if any(item["event_id"] == event["event_id"] for item in mine):
        return {"code": "registered_other_shift"}
    if shift["active_registrations"] >= shift["capacity"]:
        return {"code": "full"}
    conflict = next((item for item in mine if shifts_overlap(shift, item)), None)
    if conflict:
        return {
            "code": "conflict",
            "conflict": {
                "event_id": conflict["event_id"],
                "title": conflict["title"],
                "shift_date": conflict["shift_date"],
                "start_time": conflict["start_time"],
                "end_time": conflict["end_time"],
            },
        }
    return {"code": "open"}


# ---------- Browsing ----------

@router.get("/educator/events")
def get_available_events(
    search: str = "",
    availability: str = "all",
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user_id: UUID = Depends(get_authenticated_user_id),
):
    """Published events with at least one shift that hasn't started yet."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id)

            cursor.execute(
                """
                SELECT event_id, title, description, is_urgent, status
                FROM public.events
                WHERE status = 'published' AND title ILIKE %s
                """,
                (f"%{search.strip()}%",),
            )
            events = cursor.fetchall()
            shifts_by_event = fetch_shifts(cursor, [event["event_id"] for event in events])
            locations = fetch_locations(
                cursor,
                {shift["location_id"] for shifts in shifts_by_event.values() for shift in shifts},
            )
            mine = fetch_my_active(cursor, user_id)

    now = campus_now()
    results = []
    for event in events:
        shifts = shifts_by_event[event["event_id"]]
        openable = [shift for shift in shifts if not has_shift_started(shift, now)]
        if not openable:
            continue
        if (from_date or to_date) and not any(
            (not from_date or shift["shift_date"] >= from_date)
            and (not to_date or shift["shift_date"] <= to_date)
            for shift in openable
        ):
            continue

        spots = [max(shift["capacity"] - shift["active_registrations"], 0) for shift in openable]
        open_shift_count = sum(1 for remaining in spots if remaining > 0)
        if availability == "open" and open_shift_count == 0:
            continue

        location_ids = {shift["location_id"] for shift in openable}
        mine_here = next((item for item in mine if item["event_id"] == event["event_id"]), None)

        results.append(
            {
                "event_id": event["event_id"],
                "title": event["title"],
                "description": event["description"],
                "is_urgent": event["is_urgent"],
                "status": event["status"],
                "upcoming_shift_count": len(openable),
                "open_shift_count": open_shift_count,
                "remaining_spots": sum(spots),
                "next_shift_date": openable[0]["shift_date"],
                "next_shift_start_time": openable[0]["start_time"],
                "last_shift_date": shifts[-1]["shift_date"],
                "location_summary": "Multiple locations"
                if len(location_ids) > 1
                else location_label(locations.get(next(iter(location_ids)))),
                "my_registration": {
                    "registration_id": mine_here["registration_id"],
                    "shift_id": mine_here["shift_id"],
                    "shift_date": mine_here["shift_date"],
                    "start_time": mine_here["start_time"],
                    "end_time": mine_here["end_time"],
                }
                if mine_here
                else None,
            }
        )

    results.sort(
        key=lambda item: (item["next_shift_date"], item["next_shift_start_time"], item["title"])
    )
    return results


@router.get("/educator/events/{event_id}")
def get_educator_event(event_id: int, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_peer_educator(cursor, user_id)

            cursor.execute(
                """
                SELECT event_id, title, description, is_urgent, status, cancelled_at
                FROM public.events
                WHERE event_id = %s
                """,
                (event_id,),
            )
            event = cursor.fetchone()
            # Drafts aren't visible to peer educators.
            if event is None or event["status"] == "draft":
                raise HTTPException(status_code=404, detail="Event not found")

            shifts = fetch_shifts(cursor, [event_id])[event_id]
            locations = fetch_locations(cursor, {shift["location_id"] for shift in shifts})
            mine = fetch_my_active(cursor, user_id)

            cursor.execute(
                """
                SELECT registrations.registration_id, registrations.shift_id
                FROM public.registrations
                JOIN public.shifts ON shifts.shift_id = registrations.shift_id
                WHERE shifts.event_id = %s
                  AND registrations.user_id = %s
                  AND registrations.status = 'active'
                LIMIT 1
                """,
                (event_id, user_id),
            )
            my_registration = cursor.fetchone()

    now = campus_now()
    return {
        "event_id": event["event_id"],
        "title": event["title"],
        "description": event["description"],
        "is_urgent": event["is_urgent"],
        "status": event["status"],
        "cancelled_at": event["cancelled_at"].isoformat() if event["cancelled_at"] else None,
        "schedule_status": "upcoming"
        if any(not has_shift_ended(shift, now) for shift in shifts)
        else "past",
        "first_shift_date": shifts[0]["shift_date"] if shifts else None,
        "last_shift_date": shifts[-1]["shift_date"] if shifts else None,
        "my_registration": my_registration,
        "shifts": [
            {
                "shift_id": shift["shift_id"],
                "shift_date": shift["shift_date"],
                "start_time": shift["start_time"],
                "end_time": shift["end_time"],
                "capacity": shift["capacity"],
                "location": locations.get(shift["location_id"]),
                "active_registrations": shift["active_registrations"],
                "remaining_spots": max(shift["capacity"] - shift["active_registrations"], 0),
                "has_started": has_shift_started(shift, now),
                "has_ended": has_shift_ended(shift, now),
                "eligibility": shift_eligibility(event, shift, mine, now),
            }
            for shift in shifts
        ],
    }
