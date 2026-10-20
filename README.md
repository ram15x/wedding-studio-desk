# Wedding Guest Desk

A small, phone-friendly guest desk for one wedding. Guests confirm attendance or send travel needs in ordinary English or Hinglish. The family sees RSVP counts, arrivals, pickup and room requests, and can answer messages the desk cannot safely resolve.

## How answers and OpenRouter work

When OpenRouter is configured, the guest chat can send a guest message to an LLM for **intent parsing only**. The model returns a constrained JSON classification (RSVP, wedding-detail question, greeting, or unsupported) and extracted fields. The app validates that output against the guest's invited functions and the keys in the uploaded wedding details.

The model does **not** write customer-facing answers, decide wedding facts, update the database directly, or receive guest-list rows or wedding-detail values. Before sending a message, the app attempts to redact phone numbers and names found in the uploaded guest list. The message text itself is still sent to OpenRouter, so do not use real guest data unless the family accepts that disclosure. The model receives the allowed function names and wedding-detail **key names** to help classify the question. Answers are looked up locally from the uploaded sheets. If OpenRouter is missing, rate-limited, malformed, or uncertain, deterministic parsing continues and unclear requests go to the family inbox.

Configure OpenRouter in `.env.local` for local use or as Railway service variables. Set a comma-separated pool of keys and model IDs; keys are paired with model IDs by position, and a failing pair falls through to the others:

```text
OPENROUTER_API_KEYS=<key-1>,<key-2>,<key-3>
OPENROUTER_MODELS=<model-1>,<model-2>,<model-3>
```

Keep real keys private. Never commit them. If the variables are absent, the app works with deterministic parsing and local, sheet-grounded answers.

## What it does

- Family uploads a guest CSV with `name`, `phone`, `side`, `functions`, and `people` columns.
- Family uploads a second CSV with `item,value` rows for the venue and function dates/times.
- A guest enters the phone number listed in the guest sheet and replies in chat. Examples include `haan aa rahe hain, 4 log, 21 ko train se`, `nahi aa payenge`, `need pickup`, and `room chahiye`.
- RSVP, group size, arrival day/mode, room and pickup requests are saved to SQLite.
- The family desk shows coming, not coming, and awaiting counts for each function, plus guest and arrival lists.
- Questions absent from or unclear in the details go to the family inbox. A family reply appears in that guest's chat.
- SQLite chooses `/data/wedding_guest_desk.db` automatically when a writable `/data` volume is mounted; locally it uses ignored `assignment.db`.

The prototype identifies a guest by matching the entered phone number to the uploaded list. It does **not** verify ownership with SMS or WhatsApp OTP. Do not use real guest contact data on a public link without verified sign-in and appropriate privacy controls.

## Run locally

Requires Python 3.10 or later. There are no third-party Python dependencies.

```powershell
cd C:\Users\ramna\OneDrive\Desktop\wedding-studio-desk
Copy-Item .env.local.example .env.local
```

Edit `.env.local` and set a private family password. Then start the server:

```powershell
py -3 app.py
```

Open the guest chat at `http://127.0.0.1:8787/`. Open the password-protected family desk at `http://127.0.0.1:8787/owner` (username `owner`, password from `.env.local`). The same links work on a phone connected to the same network if the server is started with `ASSIGNMENT_HOST=0.0.0.0`; a public deployment is needed for guests outside that network. For LAN testing, set the host before starting:

```powershell
$env:ASSIGNMENT_HOST = "0.0.0.0"
py -3 app.py
```

## Upload the demo wedding

The repository includes a clearly fictional 20-person sample:

- `data/demo_guest_list.csv`
- `data/demo_wedding_details.csv`

In the family desk, upload the first file as the guest list and the second as wedding details. Sample phone numbers are `9000000001` through `9000000020`.

Try these messages from the guest chat:

```text
Haan aa rahe hain, 4 log, 21 ko train se
Hum dono aa rahe hain, flight se 20 Nov ko. Room chahiye.
Nahi aa payenge, sorry
We are coming, 3 people, flight on 21 Nov 2026, need pickup
Room chahiye
Venue kahan hai?
Mehendi kab hai?
Can we bring our dog to the venue?
```

The last question should appear in the family inbox. Reply from the family desk; the reply will show in that guest’s chat.

## Persistence and deployment

The guest list, family details, guest sessions, chat history, replies, and RSVP/travel changes are written to SQLite. On Railway, mount a volume at `/data`. The app detects this path and stores its database there, so deploys that reuse the volume retain state. If the volume is not mounted, local SQLite files in the app container can be lost on redeploy.

**Render note:** the included `render.yaml` is only a free preview configuration. Render Free web services have ephemeral filesystems, so this app's SQLite database can be erased by a restart, spin-down, or redeploy. Render's persistent disk requires a paid web-service plan; a free Render Postgres database is temporary and expires after 30 days. Therefore the free Render configuration does **not** meet the family's “data survives deploys” requirement. Use a durable mounted volume (for example, Railway `/data`) or implement and configure an external database before treating a public deployment as ready for family data. See [Render's free instance limits](https://render.com/docs/free) and [persistent disk docs](https://render.com/docs/disks).

To publish an update, push the tested commit to the connected GitHub branch, then deploy that commit from the Railway service if automatic deployment is not enabled. Confirm the deployment is active before sharing the updated behavior. Keep the Railway volume mounted at `/data` across deploys.

Set these Railway variables:

```text
ASSIGNMENT_HOST=0.0.0.0
ASSIGNMENT_PORT=8787
OWNER_PASSWORD=<private family password>
```

Do not set `ASSIGNMENT_DB_PATH` unless the volume is mounted somewhere other than `/data`. Never commit `.env.local` or real family data. The demo records are synthetic and should remain the first upload used for review.

## Data formats

Guest list header names can use common alternatives such as `guest_name`, `mobile`, `family_side`, `events`, or `number_of_people`. Separate multiple functions with semicolons, commas, or `|`.

Wedding details use two columns named `item` and `value`; one fact per row. For example:

```csv
item,value
Venue,"Lotus Convention Centre, 12 Park Road, Coimbatore"
Mehendi Date,2026-11-19
Mehendi Time,2026-11-19 16:00
```

Only facts in this file are used to answer venue and schedule questions. If a day-only arrival such as `21 ko` matches exactly one date in the uploaded schedule, the app records that date. If it cannot match uniquely, it leaves the date unset and asks the family to confirm.

## Tests

Run the regression suite from the project folder:

```powershell
py -3 -m unittest -v test_app.py
```

The guest desk tests include 15 natural English/Hinglish messages, upload validation, per-function headcounts, persistent database writes, unsupported-question escalation, and the family-reply-to-guest flow. Regression cases also cover natural RSVP declines (including “I can't make it”), requests for one function's date or time in English and Hinglish, group phrases such as `hum dono`, and unsupported questions mentioning the venue. Existing booking-specific helper tests remain in the suite for the earlier Studio Desk code; they are not part of the guest workflow.

## Current limits

- The app is for one wedding workspace at a time. Uploading a new guest list replaces the previous list and its guest conversations.
- Guest phone matching is a convenience for this demo, not strong authentication.
- CSV is the supported upload format. Convert an Excel sheet to CSV before upload.
- RSVP phrases cover common English and Hinglish patterns; anything that does not map cleanly to supported fields is escalated instead of guessed.
- The app does not send WhatsApp messages, SMS codes, calendar invites, or transport bookings.
