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

    UNIQUE (building, room_or_area)
);

ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;

-- Events
CREATE TABLE public.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    organizer_id UUID NOT NULL
        REFERENCES public.users(user_id)
);

-- Shifts
CREATE TABLE public.shifts (
    shift_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL
        REFERENCES public.events(event_id),
    location_id BIGINT NOT NULL
        REFERENCES public.locations(location_id),
    shift_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity INTEGER NOT NULL,

    CHECK (end_time > start_time),
    CHECK (capacity > 0)
);