"""Test setup: a throwaway local PostgreSQL cluster loaded with database/*.sql.

The tests never connect to Supabase. They start their own Postgres server in a
temporary directory (initdb and pg_ctl from PG_BIN, PATH, or the usual install
locations), point the app at it, and delete it afterwards. If no Postgres
binaries are found, the database tests are skipped.

Auth is replaced by a stand-in that reads the user id straight from the bearer
token, so ``Authorization: Bearer <user uuid>`` signs in as that user.
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

# Point the app at the test cluster before anything imports it. Every DB_*
# variable is assigned (never defaulted), and load_dotenv doesn't override
# variables that are already set, so a backend/.env with real Supabase
# credentials can't be picked up by the tests.
TEST_DB_HOST = "127.0.0.1"
TEST_DB_NAME = "peerconn_test"
os.environ["DB_HOST"] = TEST_DB_HOST
os.environ["DB_PORT"] = "1"  # set to the real port once the cluster is running
os.environ["DB_NAME"] = TEST_DB_NAME
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "unused"
os.environ["DB_SSLMODE"] = "disable"
os.environ["SUPABASE_URL"] = "http://supabase.invalid"
os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-key"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi import Depends, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app import campus_time  # noqa: E402
from app.auth import bearer_scheme, get_authenticated_user_id  # noqa: E402
from app.main import app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = REPO_ROOT / "database"
TESTS_DIR = Path(__file__).resolve().parent

# Files in the order the README runs them in the Supabase SQL Editor.
SETUP_FILES = [
    "schema.sql",
    "create_user_trigger.sql",
    "add_location_details.sql",
    "add_event_status_and_registrations.sql",
    "add_registration_rules_and_attendance.sql",
]

# The bits of Supabase's auth schema that schema.sql and the trigger rely on.
SUPABASE_AUTH_STUB = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY,
    email TEXT,
    raw_user_meta_data JSONB
);
"""

# A fixed "now" in campus time: Tuesday, Jan 15, 2030, 9:00 AM.
DEFAULT_NOW = datetime(2030, 1, 15, 9, 0)


# ---------- Postgres cluster ----------

def find_pg_bin():
    candidates = [os.environ.get("PG_BIN")]
    initdb = shutil.which("initdb")
    if initdb:
        candidates.append(str(Path(initdb).parent))
    for pattern in (
        "/opt/homebrew/opt/postgresql@*/bin",
        "/usr/local/opt/postgresql@*/bin",
        "/usr/lib/postgresql/*/bin",
        "/Applications/Postgres.app/Contents/Versions/latest/bin",
    ):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        if candidate and (Path(candidate) / "initdb").exists() and (Path(candidate) / "pg_ctl").exists():
            return Path(candidate)
    return None


def free_port():
    with socket.socket() as sock:
        sock.bind((TEST_DB_HOST, 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def pg_cluster():
    pg_bin = find_pg_bin()
    if pg_bin is None:
        pytest.skip("PostgreSQL (initdb/pg_ctl) not found. Install PostgreSQL or set PG_BIN.")

    workdir = Path(tempfile.mkdtemp(prefix="peerconn-pg-"))
    data_dir = workdir / "data"
    port = free_port()
    subprocess.run(
        [pg_bin / "initdb", "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "--no-locale"],
        check=True,
        capture_output=True,
    )
    options = (
        f"-p {port} -c listen_addresses={TEST_DB_HOST} -c unix_socket_directories='' "
        "-c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200"
    )
    subprocess.run(
        [pg_bin / "pg_ctl", "-D", data_dir, "-l", workdir / "postgres.log", "-w", "-o", options, "start"],
        check=True,
        capture_output=True,
    )
    os.environ["DB_PORT"] = str(port)
    try:
        yield {"host": TEST_DB_HOST, "port": port, "user": "postgres", "workdir": workdir}
    finally:
        subprocess.run([pg_bin / "pg_ctl", "-D", data_dir, "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(workdir, ignore_errors=True)


def connect(cluster, dbname, autocommit=True):
    return psycopg.connect(
        host=cluster["host"],
        port=cluster["port"],
        user=cluster["user"],
        dbname=dbname,
        autocommit=autocommit,
        row_factory=dict_row,
    )


def run_sql_file(conn, path):
    conn.execute(Path(path).read_text())


def create_database(cluster, name, files=(), sql_dir=DATABASE_DIR):
    """Creates (or recreates) a database with the Supabase auth stub and the given SQL files."""
    with connect(cluster, "postgres") as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    with connect(cluster, name) as conn:
        conn.execute(SUPABASE_AUTH_STUB)
        for file in files:
            run_sql_file(conn, Path(sql_dir) / file)


@pytest.fixture(scope="session")
def database(pg_cluster):
    create_database(pg_cluster, TEST_DB_NAME, SETUP_FILES)
    return pg_cluster


@pytest.fixture
def db(database):
    """A connection to the (emptied) test database, for setting up and inspecting rows."""
    # Belt and braces: only ever wipe the throwaway local database.
    assert os.environ["DB_HOST"] == TEST_DB_HOST
    assert os.environ["DB_NAME"] == TEST_DB_NAME
    assert os.environ["DB_PORT"] == str(database["port"])

    with connect(database, TEST_DB_NAME) as conn:
        conn.execute(
            """
            TRUNCATE public.attendance, public.registrations, public.shifts, public.events,
                     public.locations, public.users, auth.users
            RESTART IDENTITY CASCADE
            """
        )
        yield conn


# ---------- Clock ----------

class Clock:
    def __init__(self, now):
        self.now = now

    def set(self, *args):
        self.now = args[0] if isinstance(args[0], datetime) else datetime(*args)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Freezes campus time for the registration and attendance code."""
    frozen = Clock(DEFAULT_NOW)
    monkeypatch.setattr(campus_time, "campus_now", lambda: frozen.now)
    return frozen


# ---------- Data factory ----------

class Factory:
    def __init__(self, conn):
        self.conn = conn
        self._counter = 0

    def _next(self):
        self._counter += 1
        return self._counter

    def user(self, role="peer_educator", name=None, email=None) -> UUID:
        """Creates an auth user; the Supabase trigger creates the public.users row."""
        number = self._next()
        user_id = uuid4()
        name = name or f"{role.replace('_', ' ').title()} {number}"
        self.conn.execute(
            "INSERT INTO auth.users (id, email, raw_user_meta_data) VALUES (%s, %s, %s)",
            (user_id, email or f"user{number}@sjsu.edu", json.dumps({"name": name})),
        )
        if role != "peer_educator":
            self.conn.execute("UPDATE public.users SET role = %s WHERE user_id = %s", (role, user_id))
        return user_id

    def supervisor(self, **kwargs) -> UUID:
        return self.user(role="supervisor", **kwargs)

    def location(self, building="Student Union", room_or_area=None, directions=None, map_url=None) -> int:
        return self.conn.execute(
            """
            INSERT INTO public.locations (building, room_or_area, directions, map_url)
            VALUES (%s, %s, %s, %s) RETURNING location_id
            """,
            (building, room_or_area or f"Room {self._next()}", directions, map_url),
        ).fetchone()["location_id"]

    def event(self, organizer=None, title=None, status="published", is_urgent=False) -> int:
        organizer = organizer or self.supervisor()
        return self.conn.execute(
            """
            INSERT INTO public.events (title, description, is_urgent, status, organizer_id, cancelled_at)
            VALUES (%s, 'About this event', %s, %s, %s, CASE WHEN %s = 'cancelled' THEN now() END)
            RETURNING event_id
            """,
            (title or f"Event {self._next()}", is_urgent, status, organizer, status),
        ).fetchone()["event_id"]

    def shift(self, event_id=None, day="2030-01-20", start="10:00", end="12:00", capacity=5, location=None) -> int:
        event_id = event_id or self.event()
        location = location or self.location()
        return self.conn.execute(
            """
            INSERT INTO public.shifts (event_id, location_id, shift_date, start_time, end_time, capacity)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING shift_id
            """,
            (event_id, location, day, start, end, capacity),
        ).fetchone()["shift_id"]

    def registration(self, user_id, shift_id, status="active") -> int:
        """Inserts a registration directly, bypassing the API's rules."""
        return self.conn.execute(
            """
            INSERT INTO public.registrations (shift_id, event_id, user_id, status, cancelled_at)
            SELECT shift_id, event_id, %s, %s, CASE WHEN %s = 'cancelled' THEN now() END
            FROM public.shifts WHERE shift_id = %s
            RETURNING registration_id
            """,
            (user_id, status, status, shift_id),
        ).fetchone()["registration_id"]

    def cancel_event(self, event_id):
        self.conn.execute(
            "UPDATE public.events SET status = 'cancelled', cancelled_at = now() WHERE event_id = %s",
            (event_id,),
        )

    def one(self, query, params=()):
        return self.conn.execute(query, params).fetchone()

    def all(self, query, params=()):
        return self.conn.execute(query, params).fetchall()


@pytest.fixture
def make(db):
    return Factory(db)


# ---------- API client ----------

def fake_authenticated_user_id(credentials=Depends(bearer_scheme)) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        return UUID(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")


class Api:
    def __init__(self, client):
        self.client = client

    def _call(self, method, path, user=None, **kwargs):
        headers = kwargs.pop("headers", {})
        if user is not None:
            headers["Authorization"] = f"Bearer {user}"
        return self.client.request(method, path, headers=headers, **kwargs)

    def get(self, path, user=None, **kwargs):
        return self._call("GET", path, user, **kwargs)

    def post(self, path, user=None, **kwargs):
        return self._call("POST", path, user, **kwargs)

    def put(self, path, user=None, **kwargs):
        return self._call("PUT", path, user, **kwargs)

    def delete(self, path, user=None, **kwargs):
        return self._call("DELETE", path, user, **kwargs)

    # Shortcuts for the endpoints under test.
    def register(self, user, shift_id):
        return self.post(f"/api/shifts/{shift_id}/registrations", user)

    def cancel(self, user, registration_id):
        return self.post(f"/api/registrations/{registration_id}/cancel", user)

    def my_registrations(self, user):
        return self.get("/api/me/registrations", user)

    def mark(self, user, registration_id, **body):
        return self.put(f"/api/registrations/{registration_id}/attendance", user, json=body)


@pytest.fixture
def api(db):
    app.dependency_overrides[get_authenticated_user_id] = fake_authenticated_user_id
    try:
        with TestClient(app) as client:
            yield Api(client)
    finally:
        app.dependency_overrides.pop(get_authenticated_user_id, None)
