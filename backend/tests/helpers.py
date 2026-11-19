"""Shared constants and helpers for the tests (conftest.py sets up the database first)."""
import socket
from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException

from app.auth import bearer_scheme

TEST_DB_HOST = "127.0.0.1"

# A fixed "now" in campus time: Tuesday, Jan 15, 2030, 9:00 AM.
DEFAULT_NOW = datetime(2030, 1, 15, 9, 0)


def free_port():
    with socket.socket() as sock:
        sock.bind((TEST_DB_HOST, 0))
        return sock.getsockname()[1]


def fake_authenticated_user_id(credentials=Depends(bearer_scheme)) -> UUID:
    """Stands in for Supabase: the bearer token is the user's id."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        return UUID(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")


def assert_error(response, status, code=None, detail=None):
    """Asserts an error response's status (and optionally its code and detail); returns the body."""
    assert response.status_code == status, response.text
    body = response.json()
    if code is not None:
        assert body.get("code") == code, body
    if detail is not None:
        assert body["detail"] == detail, body
    return body
