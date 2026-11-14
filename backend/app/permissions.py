from fastapi import HTTPException


def require_supervisor(cursor, user_id, action="manage events"):
    cursor.execute(
        """
        SELECT role
        FROM public.users
        WHERE user_id = %s
        """, (user_id,),
    )

    user = cursor.fetchone()

    if user is None or user["role"] != "supervisor":
        raise HTTPException(status_code=403, detail=f"Only supervisors can {action}")
