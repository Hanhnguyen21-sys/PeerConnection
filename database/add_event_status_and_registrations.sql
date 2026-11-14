-- Brings events and shifts up to the shape the supervisor dashboard uses and
-- adds registrations. Run once in the Supabase SQL Editor on databases created
-- before this change. Safe to run more than once.

-- Events: urgency, publish status, and timestamps.
ALTER TABLE public.events
    ALTER COLUMN description SET DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_urgent BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'published',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

ALTER TABLE public.events DROP CONSTRAINT IF EXISTS events_status_check;
ALTER TABLE public.events
    ADD CONSTRAINT events_status_check CHECK (status IN ('draft', 'published', 'cancelled'));

ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

-- Shifts: deleting an event deletes its shifts.
ALTER TABLE public.shifts DROP CONSTRAINT IF EXISTS shifts_event_id_fkey;
ALTER TABLE public.shifts
    ADD CONSTRAINT shifts_event_id_fkey
    FOREIGN KEY (event_id) REFERENCES public.events(event_id) ON DELETE CASCADE;

ALTER TABLE public.shifts ENABLE ROW LEVEL SECURITY;

-- Registrations: a peer educator signing up for a shift.
CREATE TABLE IF NOT EXISTS public.registrations (
    registration_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shift_id BIGINT NOT NULL
        REFERENCES public.shifts(shift_id) ON DELETE CASCADE,
    user_id UUID NOT NULL
        REFERENCES public.users(user_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One active registration per user per shift.
CREATE UNIQUE INDEX IF NOT EXISTS registrations_one_active
    ON public.registrations (shift_id, user_id) WHERE status = 'active';

ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;
