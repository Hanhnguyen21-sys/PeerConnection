"""The signed-in user's profile, and supervisors managing who is a supervisor.

Roles:
- Everyone signs up as a peer educator (database/create_user_trigger.sql).
  Sign-up never takes a role.
- Supervisors can make another user a supervisor or a peer educator.
- Nobody can change their own role, so a supervisor can't lock themselves out,
  and two supervisors demoting each other at once can't leave zero supervisors
  (see set_user_role).
- The very first supervisor is set once in the Supabase SQL Editor (README).
"""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg.rows import dict_row

from app import campus_time
from app.auth import get_authenticated_user_id
from app.db import get_connection
from app.errors import ApiError
from app.permissions import require_supervisor

router = APIRouter(prefix="/api", tags=["Users"])

ROLES = ("supervisor", "peer_educator")

# Active registrations for shifts that haven't ended yet. A supervisor can't
# cancel a registration (only peer educators can), so promoting someone who has
# these would leave them holding spots they can't release.
UPCOMING_REGISTRATIONS_SQL = """
    SELECT COUNT(*)::int
    FROM public.registrations
    JOIN public.shifts ON shifts.shift_id = registrations.shift_id
    JOIN public.events ON events.event_id = shifts.event_id
    WHERE registrations.user_id = {user}
      AND registrations.status = 'active'
      AND events.status <> 'cancelled'
      AND shifts.shift_date + shifts.end_time > %(now)s
"""


class RoleInput(BaseModel):
    # Loosely typed so a bad value comes back as a field message, like EventInput.
    role: Any = None


@router.get("/me")
def get_me(
    user_id: UUID = Depends(get_authenticated_user_id),
):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT user_id, name, email, role
                FROM public.users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            user = cursor.fetchone()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User profile not found",
        )

    return user


@router.get("/users")
def list_users(
    search: Optional[str] = Query(None),
    user_id: UUID = Depends(get_authenticated_user_id),
):
    """Everyone with an account, for the supervisor's People page."""
    term = (search or "").strip()
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            require_supervisor(cursor, user_id, "view people")
            cursor.execute(
                """
                SELECT users.user_id, users.name, users.email, users.role,
                       ("""
                + UPCOMING_REGISTRATIONS_SQL.format(user="users.user_id")
                + """) AS upcoming_registrations
                FROM public.users
                WHERE %(term)s = ''
                   OR users.name ILIKE %(pattern)s
                   OR users.email ILIKE %(pattern)s
                ORDER BY lower(users.name), users.email
                """,
                {
                    "now": campus_time.campus_now(),
                    "term": term,
                    # Escape LIKE wildcards so "%" and "_" match themselves.
                    "pattern": "%"
                    + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    + "%",
                },
            )
            users = cursor.fetchall()

    for user in users:
        user["is_you"] = user["user_id"] == user_id
    return users


@router.put("/users/{target_id}/role")
def set_user_role(
    target_id: UUID,
    body: RoleInput,
    user_id: UUID = Depends(get_authenticated_user_id),
):
    role = body.role.strip().lower() if isinstance(body.role, str) else None
    if role not in ROLES:
        raise ApiError(
            422,
            "Please fix the highlighted fields.",
            {"role": 'Choose "supervisor" or "peer_educator".'},
        )

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            # Lock the caller's and the target's rows together, always in user_id
            # order, before checking anything. Two supervisors demoting each other
            # at once then run one after the other: the second sees that it is no
            # longer a supervisor and gets a 403, so one supervisor always remains.
            # A fixed order means they can't deadlock. NO KEY UPDATE (not UPDATE)
            # doesn't block foreign-key checks on registrations and events, and it
            # matches the lock register_for_shift takes on the user's row, so a
            # sign-up and a promotion of the same person also run one at a time.
            cursor.execute(
                """
                SELECT user_id, name, email, role
                FROM public.users
                WHERE user_id = ANY(%s)
                ORDER BY user_id
                FOR NO KEY UPDATE
                """,
                ([user_id, target_id],),
            )
            rows = {row["user_id"]: row for row in cursor.fetchall()}
            now = campus_time.campus_now()

            actor = rows.get(user_id)
            if actor is None or actor["role"] != "supervisor":
                raise ApiError(403, "Only supervisors can change roles.", code="forbidden")
            if target_id == user_id:
                raise ApiError(
                    409,
                    "You can't change your own role. Ask another supervisor to do it.",
                    code="own_role",
                )
            target = rows.get(target_id)
            if target is None:
                raise ApiError(404, "User not found.")
            if target["role"] == role:
                return {**target, "is_you": False}

            if role == "supervisor":
                cursor.execute(
                    "SELECT (" + UPCOMING_REGISTRATIONS_SQL.format(user="%(user)s") + ") AS n",
                    {"user": target_id, "now": now},
                )
                upcoming = cursor.fetchone()["n"]
                if upcoming:
                    plural = "registration" if upcoming == 1 else "registrations"
                    raise ApiError(
                        409,
                        f"{target['name'] or target['email']} has {upcoming} upcoming shift {plural}. "
                        "They need to cancel them before becoming a supervisor.",
                        code="has_registrations",
                    )

            cursor.execute(
                """
                UPDATE public.users
                SET role = %s
                WHERE user_id = %s
                RETURNING user_id, name, email, role
                """,
                (role, target_id),
            )
            updated = cursor.fetchone()

    return {**updated, "is_you": False}
