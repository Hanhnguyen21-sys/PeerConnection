"""Helpers for the throwaway PostgreSQL cluster the tests run against."""
import glob
import os
import shutil
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

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
