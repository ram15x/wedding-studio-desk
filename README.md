# Wedding Guest Desk

A phone-friendly web chat and password-protected family desk for one wedding. Guests can RSVP, update party size and travel needs, and ask about venue or function details. The family sees per-function headcounts, arrivals, and a reply inbox. Unsupported facts are sent to the family instead of guessed.

## Live demo

- Cloudflare guest chat: [ishqweds-guest-desk.ramnarayanan155-68f.workers.dev](https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/)
- Cloudflare family desk: add `/family` to the Cloudflare URL; sign in with username `owner` and the Cloudflare `OWNER_PASSWORD` secret.
- Cloudflare health: append `/health`.
- Legacy Railway app (kept temporarily as a fallback while its database is not migrated): [guest chat](https://wedding-studio-desk-production.up.railway.app/) · [family desk](https://wedding-studio-desk-production.up.railway.app/family)
- Source: [ram15x/wedding-studio-desk](https://github.com/ram15x/wedding-studio-desk)

**Deployment note (21 October 2026):** the `af827af` source fixes are pushed to GitHub but are not yet live on Cloudflare. The public Worker remains available on its previous deployment. A narrowly scoped Cloudflare API token is needed to deploy the update.

The Cloudflare deployment is a prototype with a synthetic 20-guest dataset in D1. It has been exercised for venue lookup, schedule answers, RSVP updates, over-invite escalation, and a D1-backed chat that survived a Worker redeploy. It is not a production-data migration: the Railway SQLite database, chat history, and inbox have not been copied to Cloudflare. Do not upload real guest details or send the Cloudflare URL to wedding guests until data migration and the acceptance flow are verified.

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

OpenRouter is configured on the Cloudflare Worker as an optional intent parser. It receives a redacted message plus allowed function names and fact-key names, and returns a classification. The Worker validates the result; actual RSVP records and wedding facts come from D1. The model does not write records or provide the wedding answer. If the provider times out, returns invalid JSON, or is rate-limited, deterministic parsing is used and unsupported questions go to the family. The Worker uses OpenRouter's free router, whose provider availability and quota can change; one key is used per request. The three configured keys are stored as encrypted Cloudflare Worker secrets, but multiple keys on the same OpenRouter account do not multiply its account-level free quota.

The app attempts to redact guest names and phone numbers before sending the message, but redaction is best-effort. Message text, allowed function names, and wedding-fact key names may be sent to OpenRouter; guest-list rows and fact values are not sent. Do not use real guest information with an external provider unless the family has approved that disclosure.

For the Python app, keys and model IDs are paired by position in `.env.local` or the Railway service variables. For Cloudflare, `OPENROUTER_API_KEYS` is a Worker secret and `OPENROUTER_MODELS` is a non-secret Worker variable. Never commit keys or put them in screenshots, source files, or chat.

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

The Python app stores guest rows, family facts, RSVP/travel updates, sessions, chats, family replies, holds, and owner inbox entries in SQLite by default. The legacy Railway service mounts `/data`. The Python code has a Supabase Postgres adapter, but the Railway data and this app are not currently connected to Supabase.

The Cloudflare Worker stores its corresponding demo records in D1. Cloudflare D1 is a separate database, not a connection to Railway SQLite or Supabase. The current D1 database contains only the synthetic demo list and facts. No live Railway records were migrated.

### Before removing the legacy Railway service

The Railway volume download previously failed with an SFTP timeout. Its production database has not been exported, imported, or compared with the D1 database. Keep the Railway service and volume until the data is confirmed disposable or a verified export exists. The old local Supabase migration path is not used by the Cloudflare Worker.

The current Cloudflare release uses Worker `ishqweds-guest-desk` and D1 database `ishqweds-guest-desk`. Deploy from `cloudflare/` with `npm install`, `npm test`, and `npx wrangler deploy`. Apply future schema migrations with `npm run db:remote`. Do not upload a replacement guest list to a live event without exporting current sessions and inbox items first; the replacement import clears those records.

Cloudflare is request-driven and keeps state in D1, so it does not depend on the development computer staying on. This deployment is subject to Cloudflare Worker and D1 plan quotas. Check current plan limits before relying on it for a real wedding.

Phone-number matching is not identity verification. There is no SMS or OTP. Owner routes are protected by Basic Auth. OpenRouter intent parsing is an external request; message text is redacted best-effort, and function/fact-key names are sent, but wedding facts and guest rows are not. Do not put real data in the demo until the event owner has approved the external processing.

Set a strong private `OWNER_PASSWORD` in Railway Variables. Do not commit `.env.local`, passwords, API keys, or real family data. Phone-number matching does not authenticate ownership.

## Tests

Run the Python suite:

```powershell
py -3 -m unittest -v test_app.py
```

The current Python suite has **80 passing tests**, including 15 natural English/Hinglish message scenarios and focused cases for mixed per-function RSVP, count-only attendance, over-invite flags, acknowledgements, schedule answers, upload validation, persistence, safe escalation, and family replies. The test setup explicitly clears database URL variables so tests use their temporary SQLite database and cannot write to Supabase. The total also includes tests for the older Studio Desk booking helpers and a small Supabase SQL-adapter unit test; it is not 80 separate production workflows. The suite does not validate a live Postgres connection, every possible phrase, or every language.

Run the Cloudflare Worker unit checks from `cloudflare/` with `npm test`. The eight checks cover count-only RSVP, function-specific mixed RSVP, preserving a function decline during a later travel update, greeting fallback, language-aware venue wording, and schedule formatting. They are focused unit tests, not a full two-device/mobile production acceptance suite.

The Cloudflare flow was also exercised locally against an isolated D1 database using only the repository's synthetic 20-guest list and wedding facts: 15 guest messages covered greetings, acknowledgements, mixed/count-only/declined/over-limit RSVPs, arrival and pickup needs, venue and schedule questions, and unsupported questions. The owner dashboard reflected the test RSVPs and pickup; an unsupported question was escalated, and an owner reply appeared in that guest's conversation. This local check did not change the hosted D1 database. It does not replace a fresh deployed run on a phone.

## Two-minute walkthrough

Use [`RECORDING_SCRIPT.md`](RECORDING_SCRIPT.md) for the live demo sequence. It is a script only; no video has been recorded.
