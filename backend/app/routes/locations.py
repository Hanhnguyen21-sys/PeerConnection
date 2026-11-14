import re
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_supervisor

router = APIRouter(prefix="/api", tags=["Locations"])

DUPLICATE_MESSAGE = "A location with this building and room or area already exists."

# shift_count tells the UI how many shifts use each location.
LOCATION_SELECT = """
    SELECT locations.location_id, locations.building, locations.room_or_area,
           locations.directions, locations.map_url,
           COUNT(shifts.shift_id)::int AS shift_count
    FROM public.locations
    LEFT JOIN public.shifts ON shifts.location_id = locations.location_id
"""
LOCATION_GROUP_BY = " GROUP BY locations.location_id"


class LocationInput(BaseModel):
    building: str
    room_or_area: str
    directions: Optional[str] = None
    map_url: Optional[str] = None


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def clean_location(location: LocationInput):
    return {
        "building": normalize_text(location.building),
        "room_or_area": normalize_text(location.room_or_area),
        "directions": (location.directions or "").strip() or None,
        "map_url": (location.map_url or "").strip() or None,
    }


def is_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_location(cursor, cleaned, current_id=None):
    errors = {}
    if not cleaned["building"]:
        errors["building"] = "Enter a building."
    if not cleaned["room_or_area"]:
        errors["room_or_area"] = "Enter a room or area."
    if cleaned["map_url"] and not is_http_url(cleaned["map_url"]):
        errors["map_url"] = "Enter a full link that starts with http:// or https://."
    if errors:
        raise ApiError(422, "Please fix the highlighted fields.", errors)

    # Duplicates ignore case and extra whitespace.
    cursor.execute(
        """
        SELECT location_id
        FROM public.locations
        WHERE lower(regexp_replace(btrim(building), '\\s+', ' ', 'g')) = lower(%s)
          AND lower(regexp_replace(btrim(room_or_area), '\\s+', ' ', 'g')) = lower(%s)
          AND location_id IS DISTINCT FROM %s
        """,
        (cleaned["building"], cleaned["room_or_area"], current_id),
    )

    if cursor.fetchone() is not None:
        raise ApiError(409, DUPLICATE_MESSAGE, {"room_or_area": DUPLICATE_MESSAGE})


def fetch_location(cursor, location_id):
    cursor.execute(
        LOCATION_SELECT + " WHERE locations.location_id = %s" + LOCATION_GROUP_BY,
        (location_id,),
    )
    return cursor.fetchone()


@router.get("/locations")
def get_locations(search: str = "", user_id: UUID = Depends(get_authenticated_user_id)):
    term = f"%{search.strip()}%"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "manage locations")

            cursor.execute(
                LOCATION_SELECT
                + " WHERE locations.building ILIKE %s OR locations.room_or_area ILIKE %s"
                + LOCATION_GROUP_BY
                + " ORDER BY locations.building, locations.room_or_area",
                (term, term),
            )

            locations = cursor.fetchall()

    return locations


@router.post("/locations", status_code=201)
def create_location(location: LocationInput, user_id: UUID = Depends(get_authenticated_user_id)):
    cleaned = clean_location(location)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "manage locations")

            validate_location(cursor, cleaned)

            try:
                cursor.execute(
                    """
                    INSERT INTO public.locations (building, room_or_area, directions, map_url)
                    VALUES (%(building)s, %(room_or_area)s, %(directions)s, %(map_url)s)
                    RETURNING location_id
                    """,
                    cleaned,
                )
            except psycopg.errors.UniqueViolation:
                raise ApiError(409, DUPLICATE_MESSAGE, {"room_or_area": DUPLICATE_MESSAGE})

            created = fetch_location(cursor, cursor.fetchone()["location_id"])

    return created


@router.put("/locations/{location_id}")
def update_location(
    location_id: int,
    location: LocationInput,
    user_id: UUID = Depends(get_authenticated_user_id),
):
    cleaned = clean_location(location)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "manage locations")

            if fetch_location(cursor, location_id) is None:
                raise HTTPException(status_code=404, detail="Location not found")

            validate_location(cursor, cleaned, location_id)

            try:
                cursor.execute(
                    """
                    UPDATE public.locations
                    SET building = %(building)s, room_or_area = %(room_or_area)s,
                        directions = %(directions)s, map_url = %(map_url)s
                    WHERE location_id = %(location_id)s
                    """,
                    {**cleaned, "location_id": location_id},
                )
            except psycopg.errors.UniqueViolation:
                raise ApiError(409, DUPLICATE_MESSAGE, {"room_or_area": DUPLICATE_MESSAGE})

            updated = fetch_location(cursor, location_id)

    return updated
