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