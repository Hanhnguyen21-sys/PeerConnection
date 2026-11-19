from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error the frontend can show: a message plus optional per-field messages
    and an optional machine-readable code (for example "full" or "conflict")."""

    def __init__(
        self,
        status_code: int,
        message: str,
        field_errors: Optional[dict] = None,
        code: Optional[str] = None,
    ):
        self.status_code = status_code
        self.message = message
        self.field_errors = field_errors
        self.code = code


async def api_error_handler(request: Request, error: ApiError):
    content = {"detail": error.message}
    if error.field_errors is not None:
        content["field_errors"] = error.field_errors
    if error.code is not None:
        content["code"] = error.code
    return JSONResponse(status_code=error.status_code, content=content)
