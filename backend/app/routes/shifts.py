from uuid import UUID
from typing import Optional
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection

router = APIRouter(prefix="/api", tags=["Shifts"])

class ShiftCreate(BaseModel):
    event_id: int
    location_id: int
    shift_date: date
    start_time: time
    end_time: time
    capacity: int

class ShiftUpdate(BaseModel):
    location_id: Optional[int] = None
    shift_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    capacity: Optional[int] = None

@router.get("/shifts")
def get_shifts():
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT shifts.shift_id, shifts.event_id, events.title AS event_title, shifts.location_id, locations.building, locations.room_or_area, shifts.shift_date, shifts.start_time, shifts.end_time, shifts.capacity
                FROM public.shifts
                JOIN public.events ON shifts.event_id = events.event_id
                JOIN public.locations ON shifts.location_id = locations.location_id
                ORDER BY shifts.shift_date, shifts.start_time
                """
            )

            shifts = cursor.fetchall()

    return shifts


@router.get("/events/{event_id}/shifts")
def get_event_shifts(event_id: int):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT shifts.shift_id, shifts.event_id, events.title AS event_title, shifts.location_id, locations.building, locations.room_or_area, shifts.shift_date, shifts.start_time, shifts.end_time, shifts.capacity
                FROM public.shifts
                JOIN public.events ON shifts.event_id = events.event_id
                JOIN public.locations ON shifts.location_id = locations.location_id
                WHERE shifts.event_id = %s
                ORDER BY shifts.shift_date, shifts.start_time
                """, (event_id,),
            )

            shifts = cursor.fetchall()

    return shifts

@router.post("/shifts")
def create_shift(shift: ShiftCreate, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT role
                FROM public.users
                WHERE user_id = %s
                """, (user_id,),
            )

            user = cursor.fetchone()

            if user is None or user["role"] != "supervisor":
                raise HTTPException(status_code=403, detail="Only supervisors can create shifts")

            cursor.execute(
                """
                INSERT INTO public.shifts (event_id, location_id, shift_date, start_time, end_time, capacity)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (shift.event_id, shift.location_id, shift.shift_date, shift.start_time, shift.end_time, shift.capacity),
            )

    return {"message": "Shift created successfully"}

@router.patch("/shifts/{shift_id}")
def update_shift(shift_id: int, shift: ShiftUpdate, user_id: UUID = Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT role
                FROM public.users
                WHERE user_id = %s
                """, (user_id,),
            )

            user = cursor.fetchone()

            if user is None or user["role"] != "supervisor":
                raise HTTPException(status_code=403, detail="Only supervisors can update shifts")

            cursor.execute(
                """
                SELECT *
                FROM public.shifts
                WHERE shift_id = %s
                """,
                (shift_id,),
            )

            existing_shift = cursor.fetchone()

            if existing_shift is None:
                raise HTTPException(status_code=404, detail="Shift not found")

            updates = shift.model_dump(exclude_unset=True)

            if not updates:
                raise HTTPException(status_code=400, detail="No fields provided to update")

            new_location = updates.get("location_id", existing_shift["location_id"])
            new_shift_date = updates.get("shift_date", existing_shift["shift_date"])
            new_start_time = updates.get("start_time", existing_shift["start_time"])
            new_end_time = updates.get("end_time", existing_shift["end_time"])
            new_capacity = updates.get("capacity", existing_shift["capacity"])

            cursor.execute(
                """
                UPDATE public.shifts
                SET 
                    location_id = %s,
                    shift_date = %s,
                    start_time = %s,
                    end_time = %s,
                    capacity = %s
                WHERE shift_id = %s
                """,
                (new_location, new_shift_date, new_start_time, new_end_time, new_capacity, shift_id,),)

            cursor.execute(
                """
                SELECT *
                FROM public.shifts
                WHERE shift_id = %s
                """,
                (shift_id,),
            )

            updated_shift = cursor.fetchone()

    return updated_shift

@router.delete("/shifts/{shift_id}")
def delete_shift(shift_id: int, user_id: UUID= Depends(get_authenticated_user_id)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT role
                FROM public.users
                WHERE user_id = %s
                """, (user_id,),
            )

            user = cursor.fetchone()

            if user is None or user["role"] != "supervisor":
                raise HTTPException(status_code=403, detail="Only supervisors can delete shifts")

            cursor.execute(
                """
                SELECT shift_id
                FROM public.shifts
                WHERE shift_id = %s
                """,
                (shift_id,),
            )

            existing_shift = cursor.fetchone()

            if existing_shift is None:
                raise HTTPException(status_code=404, detail="Shift not found")
            
            cursor.execute(
                """
                DELETE FROM public.shifts
                WHERE shift_id = %s
                """,
                (shift_id,),
            )

    return {"message": "Shift deleted successfully"}
