"""database/*.sql: a fresh install and an upgraded database end up identical.

tests/sql/ holds earlier versions of database/schema.sql, standing in for
Supabase databases created before each migration existed:
- schema_v1_before_event_status.sql: users, locations, events, shifts
  (before add_event_status_and_registrations.sql)
- schema_v2_before_registration_rules.sql: adds registrations without
  event_id/cancelled_at, and no attendance table
  (before add_registration_rules_and_attendance.sql)
"""
import json
import subprocess
from uuid import uuid4

import psycopg
import pytest

from pg import DATABASE_DIR, SETUP_FILES, TESTS_DIR, connect, create_database, run_sql_file

MIGRATION = DATABASE_DIR / "add_registration_rules_and_attendance.sql"
LEGACY_V1 = TESTS_DIR / "sql" / "schema_v1_before_event_status.sql"
LEGACY_V2 = TESTS_DIR / "sql" / "schema_v2_before_registration_rules.sql"
UPGRADE_FILES = ["create_user_trigger.sql", "add_location_details.sql", "add_event_status_and_registrations.sql"]
TABLES = ["users", "locations", "events", "shifts", "registrations", "attendance"]


def catalog(conn, tables=TABLES):
    """Columns, constraints, indexes and row-level security for the given tables, order-insensitive."""
    columns = conn.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default, is_identity
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        """,
        (tables,),
    ).fetchall()
    constraints = conn.execute(
        """
        SELECT conrelid::regclass::text AS table_name, conname, contype,
               pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace
          AND conrelid::regclass::text = ANY(%s)
        """,
        ([f"{table}" for table in tables],),
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = ANY(%s)",
        (tables,),
    ).fetchall()
    security = conn.execute(
        """
        SELECT relname, relrowsecurity
        FROM pg_class
        WHERE relnamespace = 'public'::regnamespace AND relname = ANY(%s) AND relkind = 'r'
        """,
        (tables,),
    ).fetchall()
    as_set = lambda rows: {tuple(sorted(row.items())) for row in rows}  # noqa: E731
    return {
        "columns": as_set(columns),
        "constraints": as_set(constraints),
        "indexes": as_set(indexes),
        "row_level_security": as_set(security),
    }


def assert_same_schema(actual, expected):
    for part in expected:
        missing = expected[part] - actual[part]
        extra = actual[part] - expected[part]
        assert not missing and not extra, f"{part} differ:\n  missing: {missing}\n  extra: {extra}"


@pytest.fixture(scope="module")
def fresh_catalog(database):
    create_database(database, "fresh_install", SETUP_FILES)
    with connect(database, "fresh_install") as conn:
        return catalog(conn)


def seed_legacy_data(conn):
    """Rows created before the migration: registrations without event_id."""
    supervisor, educator, other = uuid4(), uuid4(), uuid4()
    for user_id, name in [(supervisor, "Sam"), (educator, "Eve"), (other, "Oli")]:
        conn.execute(
            "INSERT INTO auth.users (id, email, raw_user_meta_data) VALUES (%s, %s, %s)",
            (user_id, f"{name.lower()}@sjsu.edu", json.dumps({"name": name})),
        )
    conn.execute("UPDATE public.users SET role = 'supervisor' WHERE user_id = %s", (supervisor,))
    location = conn.execute(
        "INSERT INTO public.locations (building, room_or_area) VALUES ('SU', '1A') RETURNING location_id"
    ).fetchone()["location_id"]
    events = [
        conn.execute(
            "INSERT INTO public.events (title, description, organizer_id) VALUES (%s, '', %s) RETURNING event_id",
            (title, supervisor),
        ).fetchone()["event_id"]
        for title in ("Fair", "Tabling")
    ]
    shifts = [
        conn.execute(
            """
            INSERT INTO public.shifts (event_id, location_id, shift_date, start_time, end_time, capacity)
            VALUES (%s, %s, '2030-01-20', %s, %s, 5) RETURNING shift_id
            """,
            (event_id, location, start, end),
        ).fetchone()["shift_id"]
        for event_id, start, end in [(events[0], "09:00", "10:00"), (events[0], "13:00", "14:00"), (events[1], "15:00", "16:00")]
    ]
    rows = [(shifts[0], educator, "active"), (shifts[1], educator, "cancelled"), (shifts[2], other, "active")]
    for shift_id, user_id, status in rows:
        conn.execute(
            "INSERT INTO public.registrations (shift_id, user_id, status) VALUES (%s, %s, %s)",
            (shift_id, user_id, status),
        )
    return {"events": events, "shifts": shifts, "educator": educator}


def build_legacy(cluster, name, schema_file, seed=True):
    create_database(cluster, name, [schema_file], sql_dir=schema_file.parent)
    with connect(cluster, name) as conn:
        for file in UPGRADE_FILES:
            run_sql_file(conn, DATABASE_DIR / file)
        return seed_legacy_data(conn) if seed else None


# ---------- Fresh installs ----------

def test_fresh_install_has_the_new_columns_and_tables(fresh_catalog):
    columns = {(dict(row)["table_name"], dict(row)["column_name"]) for row in fresh_catalog["columns"]}
    assert ("registrations", "event_id") in columns
    assert ("registrations", "cancelled_at") in columns
    assert {column for table, column in columns if table == "attendance"} == {
        "attendance_id", "registration_id", "participation_status", "credited_minutes",
    }


def test_every_migration_can_run_again_on_a_fresh_install(database, fresh_catalog):
    with connect(database, "fresh_install") as conn:
        for _ in range(2):
            for file in SETUP_FILES[1:]:
                run_sql_file(conn, DATABASE_DIR / file)
        assert_same_schema(catalog(conn), fresh_catalog)


# ---------- Upgrades ----------

@pytest.mark.parametrize("legacy_schema", [LEGACY_V1, LEGACY_V2], ids=["from_v1", "from_v2"])
def test_upgraded_database_matches_a_fresh_install(database, fresh_catalog, legacy_schema):
    name = f"upgrade_{legacy_schema.stem}"
    build_legacy(database, name, legacy_schema)
    with connect(database, name) as conn:
        for _ in range(3):  # safe to run more than once
            run_sql_file(conn, MIGRATION)
        assert_same_schema(catalog(conn), fresh_catalog)


def test_upgrade_fills_in_event_ids_and_keeps_history(database):
    seeded = build_legacy(database, "upgrade_backfill", LEGACY_V2)
    with connect(database, "upgrade_backfill") as conn:
        run_sql_file(conn, MIGRATION)
        rows = conn.execute(
            """
            SELECT registrations.shift_id, registrations.event_id, registrations.status,
                   registrations.cancelled_at, shifts.event_id AS shift_event_id
            FROM public.registrations JOIN public.shifts USING (shift_id)
            ORDER BY registration_id
            """
        ).fetchall()

        assert len(rows) == 3
        assert all(row["event_id"] == row["shift_event_id"] for row in rows)
        assert [row["status"] for row in rows] == ["active", "cancelled", "active"]
        # Old cancellations have no recorded time; that's allowed.
        assert all(row["cancelled_at"] is None for row in rows)

        # The new rules apply straight away to the old data.
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                """
                INSERT INTO public.registrations (shift_id, event_id, user_id)
                VALUES (%s, %s, %s)
                """,
                (seeded["shifts"][1], seeded["events"][0], seeded["educator"]),
            )


def add_conflicting_registration(conn, seeded):
    """Makes the old data break the new rule: two active registrations, one person, one event."""
    conn.execute(
        "UPDATE public.registrations SET status = 'active' WHERE shift_id = %s",
        (seeded["shifts"][1],),
    )


def test_upgrade_with_conflicting_old_data_fails_without_changing_anything(database):
    """The file runs as one transaction and checks the data first, so it stops
    with a message listing the conflicts and leaves the database as it was.
    (Run here as one batch, like pasting it into an SQL editor; not verified on
    Supabase itself.)"""
    seeded = build_legacy(database, "upgrade_conflict", LEGACY_V2)
    with connect(database, "upgrade_conflict") as conn:
        add_conflicting_registration(conn, seeded)
        before = catalog(conn)

        with pytest.raises(psycopg.errors.RaiseException) as error:
            run_sql_file(conn, MIGRATION)
        conn.execute("ROLLBACK")  # close the failed transaction before inspecting

        assert "Nothing was changed" in str(error.value)
        assert "registrations 1, 2" in str(error.value)
        assert_same_schema(catalog(conn), before)


def run_psql(cluster, dbname, path):
    """Runs a file the way `psql -f` does: one statement at a time, carrying on after errors."""
    return subprocess.run(
        [cluster["bin"] / "psql", "-h", cluster["host"], "-p", str(cluster["port"]), "-U", cluster["user"],
         "-d", dbname, "-X", "-q", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


def test_psql_upgrade_matches_a_fresh_install(database, fresh_catalog):
    build_legacy(database, "upgrade_psql", LEGACY_V2)
    for _ in range(2):
        result = run_psql(database, "upgrade_psql", MIGRATION)
        assert result.returncode == 0 and "ERROR" not in result.stderr, result.stderr
    with connect(database, "upgrade_psql") as conn:
        assert_same_schema(catalog(conn), fresh_catalog)


def test_psql_upgrade_with_conflicting_old_data_changes_nothing(database):
    """psql keeps going after an error, so only the transaction keeps this all-or-nothing."""
    seeded = build_legacy(database, "upgrade_psql_conflict", LEGACY_V2)
    with connect(database, "upgrade_psql_conflict") as conn:
        add_conflicting_registration(conn, seeded)
        before = catalog(conn)

    result = run_psql(database, "upgrade_psql_conflict", MIGRATION)

    assert "Nothing was changed" in result.stderr
    with connect(database, "upgrade_psql_conflict") as conn:
        assert_same_schema(catalog(conn), before)
