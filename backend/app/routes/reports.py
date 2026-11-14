from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_supervisor
from app.routes.events import is_valid_date

router = APIRouter(prefix="/api", tags=["Reports"])


def fill_rate(active, capacity):
    return active / capacity * 100 if capacity > 0 else None


@router.get("/reports/staffing")
def get_staffing_report(
    # "from" is a Python keyword, so the parameters are renamed here.
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user_id: UUID = Depends(get_authenticated_user_id),
):
    if not from_date or not to_date or not is_valid_date(from_date) or not is_valid_date(to_date) \
            or from_date > to_date:
        raise ApiError(422, "Choose a valid date range.")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "view reports")

            # Only published events count; cancelled and draft events are excluded.
            cursor.execute(
                """
                SELECT shifts.shift_id, shifts.event_id, events.title, shifts.shift_date, shifts.capacity,
                       (
                           SELECT COUNT(*)::int
                           FROM public.registrations
                           WHERE registrations.shift_id = shifts.shift_id
                             AND registrations.status = 'active'
                       ) AS active_registrations
                FROM public.shifts
                JOIN public.events ON events.event_id = shifts.event_id
                WHERE events.status = 'published'
                  AND shifts.shift_date BETWEEN %s AND %s
                ORDER BY shifts.shift_date, shifts.start_time, shifts.end_time
                """,
                (from_date, to_date),
            )
            shifts = cursor.fetchall()

            cursor.execute(
                """
                SELECT COUNT(DISTINCT registrations.user_id)::int AS educators
                FROM public.registrations
                WHERE registrations.status = 'active'
                  AND registrations.shift_id = ANY(%s)
                """,
                ([shift["shift_id"] for shift in shifts],),
            )
            unique_educators = cursor.fetchone()["educators"]

    rows_by_event = {}
    totals = {"active": 0, "capacity": 0, "open": 0, "understaffed": 0}

    for shift in shifts:
        active = shift["active_registrations"]
        open_spots = max(shift["capacity"] - active, 0)
        totals["active"] += active
        totals["capacity"] += shift["capacity"]
        totals["open"] += open_spots
        if active < shift["capacity"]:
            totals["understaffed"] += 1

        row = rows_by_event.setdefault(
            shift["event_id"],
            {
                "event_id": shift["event_id"],
                "title": shift["title"],
                "first_shift_date": shift["shift_date"].isoformat(),
                "shifts_in_range": 0,
                "active_registrations": 0,
                "capacity": 0,
                "open_spots": 0,
            },
        )
        row["shifts_in_range"] += 1
        row["active_registrations"] += active
        row["capacity"] += shift["capacity"]
        row["open_spots"] += open_spots

    return {
        "range": {"from": from_date, "to": to_date},
        "summary": {
            "events_scheduled": len(rows_by_event),
            "active_registrations": totals["active"],
            "unique_peer_educators": unique_educators,
            "open_spots": totals["open"],
            "total_capacity": totals["capacity"],
            "fill_rate": fill_rate(totals["active"], totals["capacity"]),
            "understaffed_shifts": totals["understaffed"],
        },
        "rows": [
            {**row, "fill_rate": fill_rate(row["active_registrations"], row["capacity"])}
            for row in rows_by_event.values()
        ],
    }
