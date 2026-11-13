from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection

router = APIRouter(prefix="/api", tags=["Events"])

class EventCreate(BaseModel):
    title: str
    description: str

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

@router.get("/events")
def get_events():
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT events.event_id, events.title, events.description, events.organizer_id, users.name AS organizer_name
                FROM public.events
                JOIN public.users ON events.organizer_id = users.user_id
                ORDER BY events.event_id
                """
            )
            
            events = cursor.fetchall()
    
    return events

@router.get("/events/{event_id}")
def get_event(event_id: int):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT events.event_id, events.title, events.description, events.organizer_id, users.name AS organizer_name
                FROM public.events
                JOIN public.users ON events.organizer_id = users.user_id
                WHERE events.event_id = %s
                """, (event_id,),
            )
            
            event = cursor.fetchone()

            if event is None:
                raise HTTPException(status_code=404, detail="Event not found")
    
    return event

@router.post("/events")
def create_event(event: EventCreate, user_id: UUID = Depends(get_authenticated_user_id)):
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
                raise HTTPException(status_code=403, detail="Only supervisors can create events")

            cursor.execute(
                """
                INSERT INTO public.events (title, description, organizer_id)
                VALUES (%s, %s, %s)
                """, (event.title, event.description, user_id),
            )

    return {"message": "Event created successfully"}

@router.patch("/events/{event_id}")
def update_event(event_id: int, event: EventUpdate, user_id: UUID = Depends(get_authenticated_user_id)):
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
                raise HTTPException(status_code=403, detail="Only supervisors can update events")

            cursor.execute(
                """
                SELECT event_id, title, description, organizer_id
                FROM public.events
                WHERE event_id = %s
                """,
                (event_id,),
            )

            existing_event = cursor.fetchone()

            if existing_event is None:
                raise HTTPException(status_code=404, detail="Event not found")

            updates = event.model_dump(exclude_unset=True)

            if not updates:
                raise HTTPException(status_code=400, detail="No fields provided to update")

            new_title = updates.get("title", existing_event["title"])
            new_description = updates.get("description", existing_event["description"])

            cursor.execute(
                """
                UPDATE public.events
                SET title = %s, description = %s
                WHERE event_id = %s
                """,
                (new_title, new_description, event_id),
            )

            cursor.execute(
                """
                SELECT *
                FROM public.events
                WHERE event_id = %s
                """,
                (event_id,),
            )

            updated_event = cursor.fetchone()

    return updated_event

@router.delete("/events/{event_id}")
def delete_event(event_id: int, user_id: UUID= Depends(get_authenticated_user_id)):
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
                raise HTTPException(status_code=403, detail="Only supervisors can delete events")

            cursor.execute(
                """
                SELECT event_id
                FROM public.events
                WHERE event_id = %s
                """,
                (event_id,),
            )

            existing_event = cursor.fetchone()

            if existing_event is None:
                raise HTTPException(status_code=404, detail="Event not found")
            
            cursor.execute(
                """
                DELETE FROM public.events
                WHERE event_id = %s
                """,
                (event_id,),
            )

    return {"message": "Event deleted successfully"}
