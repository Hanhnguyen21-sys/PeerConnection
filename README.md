# Peer Connections

A web app for peer educators and supervisors. It has a **React + Vite** frontend, a **FastAPI** backend, and uses **Supabase** for authentication and the Postgres database.

```
PeerConnection/
├── backend/          FastAPI API (auth check + /api/me)
│   ├── app/
│   │   ├── main.py       App entry point, CORS, health check
│   │   ├── auth.py       Verifies Supabase access tokens
│   │   ├── db.py         Postgres connection (psycopg)
│   │   └── routes/       API routes
│   ├── requirements.txt
│   └── .env.example
├── frontend/         React app (sign in / sign up / home)
│   ├── src/
│   └── .env.example
└── database/         SQL to run in Supabase
    ├── schema.sql
    └── create_user_trigger.sql
```

## Prerequisites

- **Python** 3.9+
- **Node.js** 20.19+ (or 22.12+) and npm — required by Vite 8
- A **Supabase** project ([supabase.com](https://supabase.com))

## 1. Clone the repo

```bash
git clone <repo-url>
cd PeerConnection
```

## 2. Set up Supabase

1. Create a project in Supabase.
2. Open **SQL Editor** and run, in this order:
   1. [database/schema.sql](database/schema.sql) — creates the `users` and `locations` tables.
   2. [database/create_user_trigger.sql](database/create_user_trigger.sql) — automatically creates a `public.users` row whenever someone signs up.
   3. [database/add_location_details.sql](database/add_location_details.sql) — adds `directions` and `map_url` to `locations`. Only needed if your tables were created before these columns were added to `schema.sql`; it's safe to run either way.
   4. [database/add_event_status_and_registrations.sql](database/add_event_status_and_registrations.sql) — adds urgency, status and timestamps to `events`, and creates the `registrations` table. Same rule: only needed for older databases, safe to run either way.
3. Collect the values you'll need for the `.env` files:
   - **Project URL** and **publishable key**: Project Settings → API
   - **Database host, port, name, user, password**: Project Settings → Database (or the **Connect** button)

## 3. Backend setup

From the project root:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows, use `.venv\Scripts\activate` instead.

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Create the backend env file and fill in your Supabase values:

```bash
cp -n backend/.env.example backend/.env
```

| Variable | Description |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Supabase Postgres connection details |
| `DB_SSLMODE` | Defaults to `require` |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Your Supabase publishable (anon) key |

Run the API (from inside `backend/` so the `app` package resolves):

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Check it's running: <http://localhost:8000/api/health> should return `{"status": "ok"}`. Interactive API docs are at <http://localhost:8000/docs>.

## 4. Frontend setup

In a second terminal, from the project root:

```bash
cd frontend && npm install
```

Create the frontend env file:

```bash
cp -n .env.example .env
```

| Variable | Description |
| --- | --- |
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Your Supabase publishable (anon) key |
| `VITE_API_BASE_URL` | Backend URL (optional; defaults to `http://localhost:8000` in dev) |
| `VITE_SUPERVISOR_DATA_SOURCE` | `api` makes the supervisor dashboard (events, locations, reports) save to Supabase through the backend; otherwise it's demo data in the browser |
| `VITE_EVENTS_DATA_SOURCE` | `api` uses the backend for everything, including peer educator screens; leave unset until the educator endpoints exist |

Start the dev server:

```bash
npm run dev
```

Open <http://localhost:5173>. The backend only allows CORS requests from this origin, so keep the frontend on port 5173.

## Useful commands

| Where | Command | What it does |
| --- | --- | --- |
| `frontend/` | `npm run dev` | Start the Vite dev server |
| `frontend/` | `npm run build` | Production build into `frontend/dist` |
| `frontend/` | `npm run preview` | Serve the production build locally |
| `frontend/` | `npm run lint` | Run ESLint |
| `backend/` | `uvicorn app.main:app --reload` | Start the API with auto-reload |

## API endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/health` | None | Health check |
| GET | `/api/me` | `Authorization: Bearer <supabase access token>` | Current user's profile (`user_id`, `name`, `email`, `role`) |
| GET | `/api/events?search=&status=&from=&to=` | Supervisor | List events with schedule and staffing totals |
| POST | `/api/events` | Supervisor | Create an event with its shifts |
| GET | `/api/events/{id}` | Supervisor | Event with shifts, locations and sign-up counts |
| PUT | `/api/events/{id}` | Supervisor | Update an event and its shifts |
| POST | `/api/events/{id}/cancel` | Supervisor | Cancel an event (keeps shifts and sign-ups) |
| DELETE | `/api/events/{id}` | Supervisor | Delete a draft event with no sign-ups |
| GET | `/api/events/{id}/participants?shift_id=` | Supervisor | Active sign-ups for an event |
| GET | `/api/reports/staffing?from=&to=` | Supervisor | Staffing report for a date range |
| GET | `/api/locations?search=` | Supervisor | List locations with how many shifts use each |
| POST | `/api/locations` | Supervisor | Create a location (`building`, `room_or_area`, `directions`, `map_url`) |
| PUT | `/api/locations/{id}` | Supervisor | Update a location |

## Troubleshooting

- **`KeyError: 'SUPABASE_URL'` (or `DB_HOST`) on startup** — `backend/.env` is missing or incomplete.
- **`ModuleNotFoundError: No module named 'app'`** — run `uvicorn` from inside `backend/`.
- **Browser shows a CORS error** — make sure the frontend is on `http://localhost:5173`.
- **"We couldn't find your profile yet" after sign-up** — the trigger in `create_user_trigger.sql` hasn't been run, so no `public.users` row was created.
- **Never commit `.env` files** — they're git-ignored; only `.env.example` is tracked.
