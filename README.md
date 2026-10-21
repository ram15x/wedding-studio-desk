# Wedding Guest Desk

A phone-friendly guest chat and family desk for one wedding. Guests can RSVP, update party size and travel needs, and ask about wedding details. The family sees function-by-function headcounts and arrivals, and can reply to questions the desk cannot safely answer.

## Live demo

- Guest chat: [wedding-studio-desk-production.up.railway.app](https://wedding-studio-desk-production.up.railway.app/)
- Family desk: [wedding-studio-desk-production.up.railway.app/family](https://wedding-studio-desk-production.up.railway.app/family) (also available at `/owner`)
- Source: [ram15x/wedding-studio-desk](https://github.com/ram15x/wedding-studio-desk)

The family desk uses HTTP Basic Authentication: username `owner`, password set through `OWNER_PASSWORD`. The deployed service uses a Railway volume mounted at `/data`; SQLite is stored there so guest updates, family replies, and uploaded details persist across deployments that keep the same volume.

## What it does

- Imports a guest list with name, phone, family side, invited functions, and invited party size.
- Imports wedding facts as `item,value` rows, such as venue, function date, and function time.
- Matches a guest to the uploaded list by phone number. This is not SMS or WhatsApp verification and is not strong identity proof.
- Accepts common English and Hinglish RSVP messages, including attendance, party size, arrival date, train or flight, room, and pickup requests.
- Shows coming, not coming, and awaiting counts for each function, plus guest, arrival, pickup, and room lists.
- Answers venue and schedule questions from the uploaded wedding details.
- Sends unsupported or unclear questions to the family inbox. A family reply appears in that guest’s chat.
- Stores guest records, family facts, RSVP and travel updates, sessions, messages, and family replies in SQLite.

This is a single-wedding prototype. Uploading a replacement guest list replaces the current guest list and guest conversations. Do this only when that reset is intended.

## How OpenRouter is used

OpenRouter is optional. Without it, the app still runs using deterministic message parsing and answers from the uploaded records.

When configured, an OpenRouter model classifies a guest message and extracts constrained fields, such as RSVP intent, a function name, or an arrival date. The application validates the result against the guest’s invited functions and the uploaded wedding-detail keys. The model does not supply wedding facts, compose the final answer, or update the database. The application looks up facts and makes updates locally. If the model is unavailable, times out, or returns unusable output, deterministic parsing is used; unclear questions are escalated to the family.

The app attempts to redact guest names and phone numbers from the message before sending it. Redaction is best-effort: the message text itself is sent, along with allowed function names and wedding-detail key names. Guest-list rows and wedding-detail values are not sent. Do not use real guest information with an external provider unless the family has approved that disclosure.

Configure a comma-separated pool of keys and model IDs. Keys and models are paired by position; failed requests can fall through to another configured pair.

```text
OPENROUTER_API_KEYS=<key-1>,<key-2>,<key-3>
OPENROUTER_MODELS=<model-1>,<model-2>,<model-3>
OPENROUTER_TIMEOUT_SECONDS=20
```

Set these in `.env.local` for local use or as Railway service variables. Never commit real keys or put them in the browser or source files.

## Run locally on Windows

Requires Python 3.10 or newer. The app uses the Python standard library; no third-party packages are required.

```powershell
cd C:\Users\ramna\OneDrive\Desktop\wedding-studio-desk
Copy-Item .env.local.example .env.local
```

Edit `.env.local` and set a private family password:

```text
OWNER_PASSWORD=choose-a-private-password
ASSIGNMENT_HOST=127.0.0.1
ASSIGNMENT_PORT=8787
```

Optionally add the OpenRouter variables above. Then start the server:

```powershell
py -3 app.py
```

Open:

- Guest chat: `http://127.0.0.1:8787/`
- Family desk: `http://127.0.0.1:8787/family` (or `/owner`)
- Family login username: `owner`; password: the value of `OWNER_PASSWORD`

Keep the terminal running while using the local site. To test from a phone on the same Wi-Fi, set the host before starting:

```powershell
$env:ASSIGNMENT_HOST = "0.0.0.0"
py -3 app.py
```

Then open `http://<computer-LAN-IP>:8787/` on the phone. The computer and server must remain on and reachable. The public Railway link is needed for guests outside the local network.

The checked-in `.env.local.example` is a template. `.env.local`, credentials, and local databases are ignored by Git.

## Try the fictional demo wedding

The repository includes a synthetic 20-guest list and wedding details:

- `data/demo_guest_list.csv`
- `data/demo_wedding_details.csv`

In the family desk, upload the guest list and wedding details. The example phone numbers are `9000000001` through `9000000020`. This is a phone-list match only; it does not send an OTP.

Try messages in the guest chat:

```text
Haan aa rahe hain, 4 log, 21 ko train se
Hum dono aa rahe hain, flight se 20 Nov ko. Room chahiye.
Nahi aa payenge, sorry
Sorry, I can't make it to the wedding.
We are coming, 3 people, flight on 21 Nov 2026, need pickup
Room chahiye
Venue kahan hai?
Mehendi kab hai?
Sangeet kis din hai?
At what time does the Mehendi function start?
Can we bring our dog to the venue?
```

The RSVP and travel messages should update supported fields, and the venue and schedule answers should use the uploaded facts. The unsupported pet-policy question should go to the family inbox. Reply from the family desk and check that the reply appears in the guest conversation.

## Upload formats

Guest-list columns are `name`, `phone`, `side`, `functions`, and `people`. Common aliases such as `guest_name`, `mobile`, `family_side`, `events`, and `number_of_people` are also accepted. Separate multiple functions with semicolons, commas, or `|`.

Wedding details use two columns named `item` and `value`, one fact per row:

```csv
item,value
Venue,"Lotus Convention Centre, 12 Park Road, Coimbatore"
Mehendi Date,2026-11-19
Mehendi Time,2026-11-19 16:00
Sangeet Date,2026-11-20
Sangeet Time,2026-11-20 18:30
```

Only uploaded family facts answer venue and schedule questions. A day-only arrival such as `21 ko` is saved only when it matches a unique date in the uploaded schedule; if the date is ambiguous, the app asks the family to confirm.

## Persistence and deployment

The app uses SQLite. Railway is configured with a persistent volume mounted at `/data`; the app uses `/data/wedding_guest_desk.db` when that volume is available. Keep the volume attached at the same mount path across deployments. Without durable storage, a container’s local database may be lost on restart or redeploy.

The Railway service is connected to this repository’s `main` branch. After pushing a change, confirm the corresponding Railway deployment is **Active** before relying on the changed behavior. If automatic deployment is paused, trigger **Deploy latest commit**. Keep these service variables configured:

```text
ASSIGNMENT_HOST=0.0.0.0
ASSIGNMENT_PORT=8787
OWNER_PASSWORD=<private-family-password>
```

Do not set `ASSIGNMENT_DB_PATH` unless intentionally using another mounted location. Never commit `.env.local`, API keys, passwords, or real family data.

The included Render configuration is for preview only. Render Free services have ephemeral filesystems, so they do not satisfy the requirement that SQLite data survive redeploys. Use the Railway volume or configure a durable external database before storing real guest data. See [Render free instance limits](https://render.com/docs/free) and [persistent disk documentation](https://render.com/docs/disks).

## Tests and verified scope

Run the suite from the project folder:

```powershell
py -3 -m unittest -v test_app.py
```

The latest local regression run completed **72 tests successfully**. The suite includes 15 natural English/Hinglish guest-message scenarios and focused checks for RSVP declines, function-specific date/time answers, upload validation, headcounts, database persistence, safe escalation, and the family-reply-to-guest flow. The total also includes retained booking-helper tests from the earlier Studio Desk code; 72 is not a claim of 72 distinct guest-facing workflows.

These tests use synthetic/local data. They do not prove that every possible phrasing will be understood, that OpenRouter is always available, or that phone-number matching provides secure identity verification. Validate the exact deployment and intended data before a live event.

## Before a demo

- Confirm the guest list and wedding-details files are the intended ones.
- Check the family inbox; it may contain earlier QA messages under the synthetic Asha Raman account.
- Do not upload a replacement guest list unless replacing existing guest conversations is intended.
- Confirm the owner password is private and the Railway volume remains mounted at `/data`.
- Use synthetic records unless the family has approved storing real contact details and sending messages for intent parsing to an external provider.
