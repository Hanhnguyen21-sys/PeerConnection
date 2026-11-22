import re
from datetime import date
from typing import List, Optional, Union

from pydantic import BaseModel


MAX_CAPACITY = 500
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ShiftInput(BaseModel):
    shift_id: Optional[int] = None
    shift_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location_id: Optional[Union[int, str]] = None
    capacity: Optional[Union[int, str]] = None


# converts database dates and times into JSON strings
def format_shift(row):
    return {
        **row,
        "shift_date": row["shift_date"].isoformat(),
        "start_time": row["start_time"].strftime("%H:%M"),
        "end_time": row["end_time"].strftime("%H:%M"),
    }


# retrieves shifts for event ids
def fetch_shifts(cursor, event_ids):
    """Return shifts grouped by event ID, sorted and with active registration counts."""
    shifts_by_event = {event_id: [] for event_id in event_ids}
    if not event_ids:
        return shifts_by_event

    cursor.execute(
        """
        SELECT shifts.shift_id, shifts.event_id, shifts.shift_date,
               shifts.start_time, shifts.end_time, shifts.capacity,
               shifts.location_id, COUNT(registrations.registration_id) AS active_registrations
        FROM public.shifts
        LEFT JOIN public.registrations
          ON registrations.shift_id = shifts.shift_id
         AND registrations.status = 'active'
        WHERE shifts.event_id = ANY(%s)
        GROUP BY shifts.shift_id, shifts.event_id, shifts.shift_date,
                 shifts.start_time, shifts.end_time, shifts.capacity,
                 shifts.location_id
        ORDER BY shifts.shift_date, shifts.start_time, shifts.end_time, shifts.shift_id
        """,
        (list(event_ids),),
    )

    for row in cursor.fetchall():
        shifts_by_event[row["event_id"]].append(format_shift(row))

    return shifts_by_event

# converts a value into a positive integer
def parse_whole_number(value):
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None

# converts shift input objects into dictionary
def clean_shifts(shifts: List[ShiftInput]):
    return [
        {
            "shift_id": shift.shift_id,
            "shift_date": (shift.shift_date or "").strip(),
            "start_time": (shift.start_time or "").strip(),
            "end_time": (shift.end_time or "").strip(),
            "location_id": parse_whole_number(shift.location_id),
            "location_given": str(
                shift.location_id if shift.location_id is not None else ""
            ).strip() != "",
            "capacity": parse_whole_number(shift.capacity),
        }
        for shift in shifts
    ]


# checks that a date is valid
def is_valid_date(value):
    if not DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False

# performs shift validation
def get_shift_validation_errors(cursor, shifts, locked_shifts=None):
    """Return shift field errors without raising, for event-level error aggregation."""
    locked_shifts = locked_shifts or {}
    errors = {}

    cursor.execute("SELECT location_id FROM public.locations")
    location_ids = {row["location_id"] for row in cursor.fetchall()}

    for index, shift in enumerate(shifts):
        field_errors = {}
        locked = (
            locked_shifts.get(shift["shift_id"])
            if shift["shift_id"] is not None
            else None
        )
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
            field_errors["end_time"] = (
                "End time must be after the start time on the same day."
            )

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
                f"Capacity can't be lower than the "
                f"{active_registrations} active registrations."
            )

        if locked and active_registrations > 0:
            moved = (
                shift["shift_date"] != locked["shift_date"]
                or shift["start_time"] != locked["start_time"]
                or shift["end_time"] != locked["end_time"]
            )
            if moved:
                field_errors["shift_date"] = (
                    "This shift has active registrations, so its date and time "
                    "can't change yet."
                )

        if field_errors:
            errors[str(index)] = field_errors

    return errors

# inserts a shift for an event
def insert_shift(cursor, event_id, shift):
    cursor.execute(
        """
        INSERT INTO public.shifts (
            event_id, location_id, shift_date, start_time, end_time, capacity
        )
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

# updates a shift
def update_shift(cursor, shift_id, shift):
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
            shift_id,
        ),
    )

# deletes shifts by id
def delete_shifts(cursor, shift_ids):
    if not shift_ids:
        return

    cursor.execute(
        "DELETE FROM public.shifts WHERE shift_id = ANY(%s)",
        (list(shift_ids),),
    )