import os
from pathlib import Path
from uuid import UUID
from typing import Optional
import httpx
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]

bearer_scheme = HTTPBearer(auto_error=False)

def get_authenticated_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UUID:
    # 1. check request having token or not
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. send token to supabase auth to verify
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {credentials.credentials}",
            },
            timeout=10.0,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        )

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        )

    # 3. get id when supabase successfully authenticates
    try:
        return UUID(response.json()["id"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Invalid response from authentication service",
        )