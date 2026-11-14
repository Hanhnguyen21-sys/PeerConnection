-- Adds optional directions and map link to locations.
-- Run once in the Supabase SQL Editor on databases created before this change.
ALTER TABLE public.locations
    ADD COLUMN IF NOT EXISTS directions TEXT,
    ADD COLUMN IF NOT EXISTS map_url TEXT;
