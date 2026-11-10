from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app.auth import get_authenticated_user_id
from app.db import get_connection

router = APIRouter(prefix="/api", tags=["Users"])


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