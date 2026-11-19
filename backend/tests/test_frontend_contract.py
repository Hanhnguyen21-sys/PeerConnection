"""The frontend's HTTP client calls the registration endpoints this backend serves.

Reads frontend/src/services/events/httpEventService.js and checks that each
registration function's method and path match a route in the FastAPI app.
"""
import re

import pytest

from app.main import app
from pg import REPO_ROOT

HTTP_SERVICE = REPO_ROOT / "frontend" / "src" / "services" / "events" / "httpEventService.js"
CALL = re.compile(
    r"export const (?P<name>\w+) = \([^)]*\) =>\s*request\(\s*[`\"](?P<path>[^`\"]+)[`\"]\s*,\s*ctx"
    r"(?:\s*,\s*\{(?P<options>[^}]*)\})?"
)


def frontend_calls():
    calls = {}
    for match in CALL.finditer(HTTP_SERVICE.read_text()):
        method = re.search(r'method:\s*"(\w+)"', match["options"] or "")
        path = re.sub(r"\$\{\w+\}", "{}", match["path"])
        calls[match["name"]] = (method[1] if method else "GET", path)
    return calls


def backend_routes():
    return {
        (method, re.sub(r"\{\w+\}", "{}", route.path))
        for route in app.routes
        for method in getattr(route, "methods", ())
    }


def test_the_client_file_parses():
    calls = frontend_calls()
    assert len(calls) >= 16, calls


@pytest.mark.parametrize("function", ["registerForShift", "cancelRegistration", "getMyRegistrations"])
def test_registration_functions_have_a_backend_route(function):
    assert frontend_calls()[function] in backend_routes()


def test_expected_paths():
    calls = frontend_calls()
    assert calls["registerForShift"] == ("POST", "/api/shifts/{}/registrations")
    assert calls["cancelRegistration"] == ("POST", "/api/registrations/{}/cancel")
    assert calls["getMyRegistrations"] == ("GET", "/api/me/registrations")
