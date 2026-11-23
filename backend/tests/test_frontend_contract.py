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


@pytest.mark.parametrize(
    "function",
    ["getAvailableEvents", "getEducatorEvent", "registerForShift", "cancelRegistration", "getMyRegistrations"],
)
def test_peer_educator_functions_have_a_backend_route(function):
    assert frontend_calls()[function] in backend_routes()


def test_expected_paths():
    calls = frontend_calls()
    assert calls["registerForShift"] == ("POST", "/api/shifts/{}/registrations")
    assert calls["cancelRegistration"] == ("POST", "/api/registrations/{}/cancel")
    assert calls["getMyRegistrations"] == ("GET", "/api/me/registrations")


@pytest.mark.parametrize(
    "function, expected",
    [
        ("getShiftAttendance", ("GET", "/api/shifts/{}/attendance")),
        ("saveShiftAttendance", ("PUT", "/api/shifts/{}/attendance")),
        ("clearAttendance", ("DELETE", "/api/registrations/{}/attendance")),
        ("getUsers", ("GET", "/api/users")),
        ("setUserRole", ("PUT", "/api/users/{}/role")),
    ],
)
def test_attendance_and_people_functions_have_a_backend_route(function, expected):
    assert frontend_calls()[function] == expected
    assert expected in backend_routes()


def test_every_supervisor_function_is_switched_to_the_api():
    """index.js only sends functions listed in SUPERVISOR_FUNCTIONS to the backend
    when the supervisor dashboard is on the API, so a missing name would quietly
    use demo data with real ids."""
    index = (HTTP_SERVICE.parent / "index.js").read_text()
    listed = set(re.findall(r'"(\w+)"', index.split("SUPERVISOR_FUNCTIONS = [", 1)[1].split("]", 1)[0]))
    for name in ("getShiftAttendance", "saveShiftAttendance", "clearAttendance", "getUsers", "setUserRole"):
        assert name in listed, name


def test_no_route_is_defined_twice():
    """Two routers serving the same method and path means one silently wins."""
    seen = {}
    for route in app.routes:
        for method in getattr(route, "methods", ()):
            key = (method, route.path)
            assert key not in seen, f"{method} {route.path} is defined twice"
            seen[key] = route
