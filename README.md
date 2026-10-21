# Wedding Guest Desk

A phone-friendly web chat and password-protected family desk for one wedding. Guests can RSVP, update party size and travel needs, and ask about venue or function details. The family sees per-function headcounts, arrivals, and a reply inbox. Unsupported facts are sent to the family instead of guessed.

## Live demo

- Guest chat: [wedding-studio-desk-production.up.railway.app](https://wedding-studio-desk-production.up.railway.app/)
- Family desk: [wedding-studio-desk-production.up.railway.app/family](https://wedding-studio-desk-production.up.railway.app/family) (also `/owner`)
- Source: [ram15x/wedding-studio-desk](https://github.com/ram15x/wedding-studio-desk)

The family desk uses HTTP Basic Authentication: username `owner`, password from `OWNER_PASSWORD`. Railway currently uses SQLite on a volume mounted at `/data`; the Supabase Postgres option is prepared in code but is not connected or migrated yet.

## What it does

- Imports a guest list (`name`, `phone`, `side`, `functions`, `people`) and wedding facts (`item,value`).
- Matches guests to the list by phone number. This is not SMS or WhatsApp OTP verification and is not strong identity proof.
- Records RSVP status, party size, arrival date and mode, room requests, and pickup requests.
- Shows coming, not coming, and awaiting counts for each function, plus arrivals, pickup, and room lists.
- Answers venue and schedule questions from uploaded facts; unknown facts go to the family inbox, where a reply appears in the same guest chat.
- Updates functions independently in a mixed RSVP. A reported party size above the invitation count is recorded and visibly flagged to the family for confirmation.
- Treats short acknowledgements such as “ok” and “thanks” as conversation. English and common Latin-script Hinglish replies use matching wording. Schedule answers include the uploaded date when available, even if the guest asks only for the time. Other languages have not been validated.

This is a single-wedding prototype. Uploading another guest list replaces the current list and guest conversations; do that only when the reset is intended.

## How OpenRouter is used

OpenRouter is optional. When configured, it classifies guest messages and extracts constrained intent such as RSVP, function, or arrival details. The app validates that output against the guest’s invited functions and wedding-fact keys. The model does not write facts or update the database; answers and updates come from the app and uploaded records. If the model fails or is uncertain, deterministic parsing is used and unsupported questions go to the family.

The app attempts to redact guest names and phone numbers before sending the message, but redaction is best-effort. Message text, allowed function names, and wedding-fact key names may be sent to OpenRouter; guest-list rows and fact values are not sent. Do not use real guest information with an external provider unless the family has approved that disclosure.

Keys and model IDs are paired by position. Add them to `.env.local` locally or Railway service variables. Never commit keys or put them in screenshots, source files, or chat.

```text
OPENROUTER_API_KEYS=<key-1>,<key-2>,<key-3>
OPENROUTER_MODELS=<model-1>,<model-2>,<model-3>
OPENROUTER_TIMEOUT_SECONDS=20
```

## Run locally on Windows

Requires Python 3.10 or newer. SQLite mode uses only the standard library. Supabase mode requires the optional `psycopg` dependency from `requirements.txt`.

```powershell
cd C:\Users\ramna\OneDrive\Desktop\wedding-studio-desk
Copy-Item .env.local.example .env.local
```

Edit `.env.local` and set a private `OWNER_PASSWORD`. Then start:

```powershell
py -3 app.py
```

Open:

- Guest chat: `http://127.0.0.1:8787/`
- Family desk: `http://127.0.0.1:8787/family` or `/owner`
- Login username: `owner`; password: `OWNER_PASSWORD`

Keep the terminal running. For phone testing on the same Wi-Fi, set `$env:ASSIGNMENT_HOST = "0.0.0.0"` before starting, then open `http://<computer-LAN-IP>:8787/` on the phone. Local access ends when the computer or server stops.

To use Supabase locally, install the optional driver with `py -3 -m pip install -r requirements.txt` and set `SUPABASE_DB_URL` in `.env.local`.

## Try the fictional demo wedding

The repository includes a synthetic 20-guest list and wedding facts:

- `data/demo_guest_list.csv`
- `data/demo_wedding_details.csv`

Upload the guest list and then the wedding details in the family desk. Demo numbers are `9000000001` through `9000000020`; no OTP is sent.

```text
Haan aa rahe hain, 4 log, 21 ko train se
Hum 2 log aayenge shaadi mein, reception nahi aa paayenge
Hum 6 log aayenge
Hum dono aa rahe hain, flight se 20 Nov ko. Room chahiye.
Nahi aa payenge, sorry
Sorry, I can't make it to the wedding.
We are coming, 3 people, flight on 21 Nov 2026, need pickup
Venue kahan hai?
Mehendi kab hai?
Sangeet ka time kya hai?
ok
thanks
Can we bring our dog to the venue?
```

The unsupported pet-policy question should appear in the family inbox. Reply there and verify that the reply shows in the same guest chat.

## Data formats

Guest-list columns are `name`, `phone`, `side`, `functions`, and `people`. Common aliases such as `guest_name`, `mobile`, `family_side`, `events`, and `number_of_people` are accepted. Separate functions with semicolons, commas, or `|`.

Wedding facts use `item,value`, one fact per row:

```csv
item,value
Venue,"Lotus Convention Centre, 12 Park Road, Coimbatore"
Mehendi Date,2026-11-19
Mehendi Time,2026-11-19 16:00
Sangeet Date,2026-11-20
Sangeet Time,2026-11-20 18:30
```

Only uploaded facts answer venue and schedule questions. A day-only arrival such as `21 ko` is saved only if it matches a unique date in the uploaded schedule; otherwise, the family is asked to confirm.

## Database and deployment

By default, the app stores guest rows, family facts, RSVP and travel updates, sessions, chats, family replies, holds, and owner inbox entries in SQLite. Railway currently mounts `/data` and stores the database there. The code also supports Supabase Postgres: set `SUPABASE_DB_URL` (or `DATABASE_URL`) to a Supabase Postgres connection string. If configured, Postgres is used and connection failures do not silently fall back to SQLite.

### Moving Railway data to Supabase

Supabase is **not connected yet**: there is no Supabase connection setting in the local environment and the Railway SQLite export has not been obtained. Safe migration steps:

1. Create a Supabase project and copy its Postgres connection string from **Project → Connect**. Keep the password private.
2. Export/download the current Railway `/data/wedding_guest_desk.db`. Keep the Railway volume attached until migration is verified.
3. Set `SUPABASE_DB_URL` locally and run `python migrate_sqlite_to_supabase.py <path-to-exported-db>`. The script refuses to write if any destination table already contains data.
4. Verify guest rows, family facts, RSVP counts, conversations, inbox items, holds, and replies.
5. Set `SUPABASE_DB_URL` in Railway Variables and deploy. Re-test before removing the old volume.

The migration needs both the connection string and the SQLite export. Setting the new variable without migrating would start with empty Postgres tables. PostgreSQL has not yet been tested against a live Supabase project.

Moving the database does not move the web server. Railway’s current trial terms state Trial volumes are deleted 30 days after trial credits expire; after that the Free plan provides $1 monthly credit. Supabase Free projects can also pause after low activity over seven days and have a database quota. Therefore, moving the database alone does not guarantee that the hosted app stays online through wedding season. Check [Railway trial terms](https://docs.railway.com/pricing/free-trial), [Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), and [Supabase database limits](https://supabase.com/docs/guides/platform/database-size).

The connected Railway service deploys from this repository’s `main` branch. After a push, verify the deployment is **Active** before relying on the new behavior. If Railway builds are paused, wait until they resume and deploy the latest commit. The optional `render.yaml` is only for preview; Render Free filesystems are ephemeral and do not satisfy the persistence requirement.

Set a strong private `OWNER_PASSWORD` in Railway Variables. Do not commit `.env.local`, passwords, API keys, or real family data. Phone-number matching does not authenticate ownership.

## Tests

Run the local suite:

```powershell
py -3 -m unittest -v test_app.py
```

The current suite has **78 passing tests**, including 15 natural English/Hinglish message scenarios and focused cases for mixed per-function RSVP, count-only attendance, over-invite flags, acknowledgements, schedule answers, upload validation, persistence, safe escalation, and family replies. The total also includes tests for the older Studio Desk booking helpers and a small Supabase SQL-adapter unit test; it is not 78 separate production workflows. The suite does not validate a live Postgres connection, every possible phrase, or every language.

## Two-minute walkthrough

Use [`RECORDING_SCRIPT.md`](RECORDING_SCRIPT.md) for the live demo sequence. It is a script only; no video has been recorded.
