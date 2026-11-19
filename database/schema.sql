-- Users
CREATE TABLE public.users (
    user_id UUID PRIMARY KEY
        REFERENCES auth.users(id) ON DELETE CASCADE,

    name TEXT NOT NULL,

    email TEXT NOT NULL UNIQUE,

    role TEXT NOT NULL DEFAULT 'peer_educator'
        CHECK (role IN ('supervisor', 'peer_educator'))
);

-- Block Data API access
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;


-- Locations 
CREATE TABLE public.locations (
    location_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building TEXT NOT NULL,
    room_or_area TEXT NOT NULL,
    directions TEXT,
    map_url TEXT,

    UNIQUE (building, room_or_area)
);

ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;

-- Events
CREATE TABLE public.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_urgent BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'published'
        CONSTRAINT events_status_check
        CHECK (status IN ('draft', 'published', 'cancelled')),
    organizer_id UUID NOT NULL
        REFERENCES public.users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at TIMESTAMPTZ
);

ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

-- Shifts
CREATE TABLE public.shifts (
    shift_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL
        REFERENCES public.events(event_id) ON DELETE CASCADE,
    location_id BIGINT NOT NULL
        REFERENCES public.locations(location_id),
    shift_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity INTEGER NOT NULL,

    CHECK (end_time > start_time),
    CHECK (capacity > 0)
);

ALTER TABLE public.shifts ENABLE ROW LEVEL SECURITY;

-- Registrations
-- shift_id alone is already unique; naming the pair lets a registration
-- reference its shift and that shift's event together.
ALTER TABLE public.shifts
    ADD CONSTRAINT shifts_shift_id_event_id_key UNIQUE (shift_id, event_id);

CREATE TABLE public.registrations (
    registration_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shift_id BIGINT NOT NULL
        REFERENCES public.shifts(shift_id) ON DELETE CASCADE,
    event_id BIGINT NOT NULL,
    user_id UUID NOT NULL
        REFERENCES public.users(user_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at TIMESTAMPTZ,

    -- A registration's event_id always matches its shift's event.
    CONSTRAINT registrations_shift_event_fkey
        FOREIGN KEY (shift_id, event_id)
        REFERENCES public.shifts (shift_id, event_id) ON DELETE CASCADE,
    -- Active registrations have no cancellation time.
    CONSTRAINT registrations_cancelled_at_check
        CHECK (status = 'cancelled' OR cancelled_at IS NULL)
);

-- One active registration per user per shift
CREATE UNIQUE INDEX registrations_one_active
    ON public.registrations (shift_id, user_id) WHERE status = 'active';

-- One active registration per user per event (on any one of its shifts)
CREATE UNIQUE INDEX registrations_one_active_per_event
    ON public.registrations (user_id, event_id) WHERE status = 'active';

CREATE INDEX registrations_user_id_idx
    ON public.registrations (user_id);

ALTER TABLE public.registrations ENABLE ROW LEVEL SECURITY;

-- Attendance: at most one record per registration
CREATE TABLE public.attendance (
    attendance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registration_id BIGINT NOT NULL
        CONSTRAINT attendance_registration_id_key UNIQUE
        REFERENCES public.registrations(registration_id) ON DELETE CASCADE,
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
