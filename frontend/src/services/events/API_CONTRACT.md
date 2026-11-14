# Events API contract

The **supervisor endpoints** below are implemented in FastAPI
(`backend/app/routes/events.py`, `locations.py`, `reports.py`). Set
`VITE_SUPERVISOR_DATA_SOURCE=api` to use them. The **peer educator endpoints**
further down are still proposals; those screens run on demo data
(`mockEventService.js`), which returns exactly these shapes. Once they exist,
set `VITE_EVENTS_DATA_SOURCE=api` to use the backend for everything.
`httpEventService.js` never falls back to demo data if a request fails.

## Conventions

- Every request sends `Authorization: Bearer <Supabase access token>`, the
  same as `GET /api/me`. The backend must verify the token and require
  `role = 'supervisor'` for every endpoint below (403 otherwise). The frontend
  role check only controls what's shown.
- The organizer is the authenticated user. It is never read from the request body.
- Dates are `YYYY-MM-DD` strings and times are `HH:MM` 24-hour strings. They are
  wall-clock campus time in `America/Los_Angeles`. Shifts start and end on the same day.
  Suggested columns: `shift_date DATE`, `start_time TIME`, `end_time TIME`,
  `CHECK (end_time > start_time)`.
- Only registrations with `status = 'active'` count toward staffing numbers.
  Cancelled registrations remain as history.
- Errors use `{ "detail": "Readable message", "field_errors": { ... } }`.
  `field_errors` is optional and follows the validation shape below.
  Status codes: 401 (bad token), 403 (not a supervisor), 404 (unknown id),
  409 (conflict, e.g. duplicate location or locked shift), 422 (validation).

## Data shapes

```js
Location = {
  location_id: number,
  building: string,          // required, trimmed
  room_or_area: string,      // required, trimmed; (building, room_or_area) unique, case-insensitive
  directions: string | null, // NEW column (optional)
  map_url: string | null,    // NEW column (optional, http/https only)
  shift_count: number,       // computed: shifts that reference this location
}

EventSummary = {
  event_id: number,
  title: string,
  description: string,
  is_urgent: boolean,
  status: "draft" | "published" | "cancelled",
  schedule_status: "upcoming" | "past", // upcoming if any shift hasn't ended (campus time)
  first_shift_date: string | null,
  last_shift_date: string | null,
  next_shift_date: string | null,       // first shift that hasn't ended
  shift_count: number,
  active_registrations: number,
  total_capacity: number,
  understaffed_shifts: number,          // shifts with active registrations < capacity
  created_at: string, updated_at: string, cancelled_at: string | null, // ISO timestamps
}

EventDetail = EventSummary & {
  organizer: { user_id: string, name: string } | null,
  has_registration_history: boolean,    // any registration, active or cancelled
  shifts: Array<{
    shift_id: number,
    shift_date: string, start_time: string, end_time: string,
    capacity: number,
    location_id: number,
    location: Location | null,
    active_registrations: number,
    remaining_spots: number,             // max(capacity - active_registrations, 0)
  }>,
}

EventInput = {
  title: string,             // required, max 120 chars
  description: string,
  is_urgent: boolean,        // default false
  shifts: Array<{            // at least one
    shift_id?: number,       // present = update existing shift; omitted = new shift
    shift_date: string, start_time: string, end_time: string,
    location_id: number,
    capacity: number,        // integer 1–500
  }>,
}

Participant = {
  registration_id: number,
  registered_at: string,
  user: { user_id: string, name: string, email: string },
  shift: { shift_id: number, shift_date: string, start_time: string, end_time: string },
}

StaffingReport = {
  range: { from: string, to: string },
  summary: {
    events_scheduled: number,       // distinct published events with a shift in range
    active_registrations: number,
    unique_peer_educators: number,  // distinct user_id among those registrations
    open_spots: number,             // Σ max(capacity - active, 0) per shift
    total_capacity: number,
    fill_rate: number | null,       // active / capacity × 100; null when capacity is 0
    understaffed_shifts: number,
  },
  rows: Array<{
    event_id: number, title: string, first_shift_date: string,
    shifts_in_range: number, active_registrations: number,
    capacity: number, open_spots: number, fill_rate: number | null,
  }>,
}
```

Validation errors (`field_errors`) mirror `validateEventInput` in
`src/lib/validation.js`:
`{ title?, shifts?, shiftFields: { "<shift index>": { shift_date?, start_time?, end_time?, location_id?, capacity? } } }`.
For locations, the shape is `{ building?, room_or_area?, map_url? }`.

## Endpoints

| Service function | Method & path | Body / query | Returns |
| --- | --- | --- | --- |
| `getEvents` | `GET /api/events` | `?search=&status=all\|upcoming\|past\|cancelled&from=&to=` | `EventSummary[]` |
| `getEvent` | `GET /api/events/{id}` | | `EventDetail` |
| `createEvent` | `POST /api/events` | `EventInput` | `EventDetail` (status `published`) |
| `updateEvent` | `PUT /api/events/{id}` | `EventInput` | `EventDetail` |
| `cancelEvent` | `POST /api/events/{id}/cancel` | | `EventDetail` |
| `deleteDraftEvent` | `DELETE /api/events/{id}` | | `204` |
| `getParticipants` | `GET /api/events/{id}/participants` | `?shift_id=` | `Participant[]` (active only) |
| `getLocations` | `GET /api/locations` | `?search=` | `Location[]` |
| `createLocation` | `POST /api/locations` | `{ building, room_or_area, directions, map_url }` | `Location` |
| `updateLocation` | `PUT /api/locations/{id}` | same as create | `Location` |
| `getReport` | `GET /api/reports/staffing` | `?from=YYYY-MM-DD&to=YYYY-MM-DD` | `StaffingReport` |

## Business rules the backend must enforce

- **Filters:** `from`/`to` match events with at least one shift dated in the
  range. `upcoming` and `past` exclude cancelled events.
- **Update:** cancelled events can't be edited (409). For a shift with active
  registrations:
  - capacity can't go below the active count;
  - date and time can't change, and the shift can't be removed, until conflict
    checks exist (409).

  Removing a shift that has no active registrations is allowed.
- **Cancel:** sets `status = 'cancelled'` and `cancelled_at`. It keeps shifts
  and registrations and blocks new registrations. It sends no notifications.
- **Delete:** only `status = 'draft'` events with no registrations at all,
  active or cancelled (otherwise 409). Drafts can exist, but this UI only
  creates published events.
- **Locations:** reject duplicates after trimming, collapsing whitespace and
  case-folding (409). `map_url` must be `http` or `https`. There is no delete
  endpoint in this phase.
- **Report:** filter by `shift_date` in `[from, to]` (inclusive). Include only
  `published` events, so cancelled and draft events are excluded. An event
  spanning several weeks counts only the shifts inside the range.
  "This week" is Monday–Sunday in `America/Los_Angeles`. Registrations are
  sign-ups, not attendance.

## Suggested tables (beyond the existing `users` and `locations`)

```sql
ALTER TABLE public.locations ADD COLUMN directions TEXT, ADD COLUMN map_url TEXT;

CREATE TABLE public.events (
  event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  is_urgent BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published', 'cancelled')),
  organizer_id UUID NOT NULL REFERENCES public.users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  cancelled_at TIMESTAMPTZ
);

CREATE TABLE public.shifts (
  shift_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
  shift_date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL CHECK (end_time > start_time),
  location_id BIGINT NOT NULL REFERENCES public.locations(location_id),
  capacity INTEGER NOT NULL CHECK (capacity > 0)
);

CREATE TABLE public.registrations (
  registration_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  shift_id BIGINT NOT NULL REFERENCES public.shifts(shift_id),
  user_id UUID NOT NULL REFERENCES public.users(user_id),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One active registration per user per shift:
CREATE UNIQUE INDEX registrations_one_active
  ON public.registrations (shift_id, user_id) WHERE status = 'active';
```

These tables are now in `database/schema.sql`; older databases get them from
`database/add_event_status_and_registrations.sql`.

---

# Peer educator endpoints (proposed, not implemented)

All require a valid Bearer token and `role = 'peer_educator'` (403 otherwise).
The user is always the authenticated user: no endpoint accepts a `user_id`.
The demo implementation is in `mockEventService.js`, and `httpEventService.js`
holds the draft client.

| Service function | Method & path | Body / query | Returns |
| --- | --- | --- | --- |
| `getAvailableEvents` | `GET /api/educator/events` | `?search=&from=&to=&availability=all\|open` | `AvailableEvent[]` |
| `getEducatorEvent` | `GET /api/educator/events/{id}` | | `EducatorEventDetail` (404 for drafts/unknown) |
| `getMyRegistrations` | `GET /api/me/registrations` | | `MyRegistration[]` (active and cancelled) |
| `registerForShift` | `POST /api/shifts/{shift_id}/registrations` | | `MyRegistration` (201) |
| `cancelRegistration` | `POST /api/registrations/{id}/cancel` | | `MyRegistration` |

```js
AvailableEvent = {
  event_id, title, description, is_urgent, status: "published",
  upcoming_shift_count: number,   // shifts that haven't started
  open_shift_count: number,       // ...of those, shifts with a remaining spot
  remaining_spots: number,        // Σ remaining over shifts that haven't started
  next_shift_date, next_shift_start_time, last_shift_date,
  location_summary: string | null, // "Building · Room" or "Multiple locations"
  my_registration: { registration_id, shift_id, shift_date, start_time, end_time } | null,
}

EducatorEventDetail = {
  event_id, title, description, is_urgent,
  status: "published" | "cancelled", cancelled_at,
  schedule_status: "upcoming" | "past",
  first_shift_date, last_shift_date,
  my_registration: { registration_id, shift_id } | null,   // active, on this event
  shifts: Array<{
    shift_id, shift_date, start_time, end_time, capacity,
    location: Location | null,
    active_registrations, remaining_spots,
    has_started: boolean, has_ended: boolean,
    eligibility: {
      code: "open" | "registered" | "registered_other_shift" | "full"
          | "conflict" | "closed" | "event_cancelled",
      registration_id?,   // when code = "registered"
      conflict?: { event_id, title, shift_date, start_time, end_time },
    },
  }>,
}

MyRegistration = {
  registration_id, status: "active" | "cancelled", created_at, cancelled_at,
  category: "upcoming" | "in_progress" | "past" | "cancelled_by_user" | "event_cancelled",
  can_cancel: boolean,
  event: { event_id, title, status, is_urgent, cancelled_at },
  shift: { shift_id, shift_date, start_time, end_time },
  location: Location | null,
}
```

Registration errors return 409 with
`{ "detail": "<readable message>", "code": "<eligibility code>" }`. The UI
shows `detail` as-is and treats the server's answer as authoritative.

## Registration rules (the backend must enforce these inside one transaction)

1. Registration is immediate, with no approval step.
2. A user can have only one active registration per event.
3. A user can't hold overlapping active registrations across events. Shifts
   overlap when `new_start < existing_end AND new_end > existing_start` on the
   same date, so back-to-back shifts are allowed. Registrations on cancelled
   events don't count.
4. Active registrations can't exceed the shift's capacity. Lock the shift row
   or use a guarded `INSERT … SELECT` so two sign-ups can't both take the
   last spot.
5. Cancelling sets `status = 'cancelled'` and `cancelled_at`. The row is
   never deleted, which frees the spot. Registering again creates a new row;
   a cancelled row is never reactivated.
6. Every peer educator can register for every published event. Drafts are
   hidden from peer educators.

## Proposed rules that need team confirmation

- **Registration closes when a shift starts.** The demo uses
  `shift_date + start_time <= now` in campus time.
- **Cancellation is allowed until the shift starts.** Is a cutoff such as
  24 hours before needed instead?
- **A supervisor cancelling an event leaves its registrations `active`.** The
  event status explains them, and "My Events" lists them under Cancelled as
  "Event cancelled", separate from cancellations the user made. Alternatively,
  should the backend mark these registrations as cancelled, with a reason?
- **No attendance tracking.** Past registrations are labelled "Past
  registration". Attendance, absences and credited minutes are not inferred.
