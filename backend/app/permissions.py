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


def require_peer_educator(cursor, user_id, action="register for shifts", lock=False):
    """Checks the role. With lock=True the user's row stays locked until the
    transaction ends, so one person's sign-ups are checked one at a time.

    FOR NO KEY UPDATE (rather than FOR UPDATE) still serializes sign-ups but
    doesn't block foreign-key checks that reference the user.
    """
    cursor.execute(
        """
        SELECT role
        FROM public.users
        WHERE user_id = %s
        """ + (" FOR NO KEY UPDATE" if lock else ""),
        (user_id,),
    )

    user = cursor.fetchone()

    if user is None or user["role"] != "peer_educator":
        raise HTTPException(status_code=403, detail=f"Only peer educators can {action}")
