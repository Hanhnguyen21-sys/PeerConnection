-- Registration rules and attendance. Run once in the Supabase SQL Editor, after
-- add_event_status_and_registrations.sql. Safe to run more than once, and safe
-- on databases created from the current schema.sql.
--
-- Everything runs in one transaction: if any step fails, nothing is changed.

BEGIN;

-- Stop before changing anything if existing data breaks the new rule
-- "one active registration per user per event".
DO $$
DECLARE
    conflicts TEXT;
BEGIN
    SELECT string_agg(
               format('user %s in event %s (registrations %s)', user_id, event_id, registration_ids),
               '; ')
    INTO conflicts
    FROM (
        SELECT registrations.user_id, shifts.event_id,
               string_agg(registrations.registration_id::text, ', '
                          ORDER BY registrations.registration_id) AS registration_ids
        FROM public.registrations
        JOIN public.shifts ON shifts.shift_id = registrations.shift_id
        WHERE registrations.status = 'active'
        GROUP BY registrations.user_id, shifts.event_id
        HAVING COUNT(*) > 1
    ) AS duplicates;

    IF conflicts IS NOT NULL THEN
        RAISE EXCEPTION 'Nothing was changed: some people have more than one active registration in the same event: %. Keep one per event, cancel the others with UPDATE public.registrations SET status = ''cancelled'' WHERE registration_id IN (...), then run this file again.', conflicts;
    END IF;
END $$;

-- Registrations: each one records its event, so the database itself enforces
-- "one active registration per user per event". cancelled_at records when a
-- peer educator cancelled.
ALTER TABLE public.registrations
    ADD COLUMN IF NOT EXISTS event_id BIGINT,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- Fill in event_id for registrations made before this change.
UPDATE public.registrations
SET event_id = shifts.event_id
FROM public.shifts
WHERE shifts.shift_id = registrations.shift_id
  AND registrations.event_id IS DISTINCT FROM shifts.event_id;

ALTER TABLE public.registrations ALTER COLUMN event_id SET NOT NULL;

DO $$
BEGIN
    -- shift_id alone is already unique; naming the pair lets a registration
    -- reference its shift and that shift's event together.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.shifts'::regclass AND conname = 'shifts_shift_id_event_id_key'
    ) THEN
        ALTER TABLE public.shifts
            ADD CONSTRAINT shifts_shift_id_event_id_key UNIQUE (shift_id, event_id);
    END IF;

    -- A registration's event_id always matches its shift's event.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.registrations'::regclass AND conname = 'registrations_shift_event_fkey'
    ) THEN
        ALTER TABLE public.registrations
            ADD CONSTRAINT registrations_shift_event_fkey
            FOREIGN KEY (shift_id, event_id)
            REFERENCES public.shifts (shift_id, event_id) ON DELETE CASCADE;
    END IF;

    -- Active registrations have no cancellation time.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.registrations'::regclass AND conname = 'registrations_cancelled_at_check'
    ) THEN
        ALTER TABLE public.registrations
            ADD CONSTRAINT registrations_cancelled_at_check
            CHECK (status = 'cancelled' OR cancelled_at IS NULL);
    END IF;
END $$;

-- One active registration per user per event (it can be on any one of the event's shifts).
CREATE UNIQUE INDEX IF NOT EXISTS registrations_one_active_per_event
    ON public.registrations (user_id, event_id) WHERE status = 'active';

-- "My registrations" looks registrations up by user.
CREATE INDEX IF NOT EXISTS registrations_user_id_idx
    ON public.registrations (user_id);

-- Attendance: at most one record per registration.
CREATE TABLE IF NOT EXISTS public.attendance (
    attendance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: a registration with attendance can't be deleted (nor its shift
    -- or user), so participation history is never lost by accident.
    registration_id BIGINT NOT NULL
        CONSTRAINT attendance_registration_id_key UNIQUE
        REFERENCES public.registrations(registration_id) ON DELETE RESTRICT,
    participation_status TEXT NOT NULL
        CONSTRAINT attendance_participation_status_check
        CHECK (participation_status IN ('attended', 'absent')),
    credited_minutes INTEGER NOT NULL DEFAULT 0
        CONSTRAINT attendance_credited_minutes_check
        CHECK (credited_minutes >= 0),

    -- Absent participants aren't credited any minutes.
    CONSTRAINT attendance_absent_no_minutes_check
        CHECK (participation_status = 'attended' OR credited_minutes = 0)
);

ALTER TABLE public.attendance ENABLE ROW LEVEL SECURITY;

COMMIT;
