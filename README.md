# Wedding Studio Desk

A small standalone booking assistant for the wedding studio assignment.

It loads the supplied booking CSV and provides:

- a WhatsApp-style customer chat
- answers grounded only in the current CSV
- a simple operating dashboard
- safe escalation when the CSV cannot support an answer
- 24-hour date holds with duplicate protection
- owner upload of a replacement booking sheet

No external model, API key, or database server is required for the deterministic path.

## Optional OpenRouter assistance

For more natural questions and replies, the app can optionally call OpenRouter to classify the question into a small intent schema. Only the question text and visible column names are sent for intent classification; booking rows, credentials, and answers are not sent. The model never computes booking facts. The deterministic engine reads the CSV, enforces privacy, calculates the result, and remains the fallback if the key is missing, the provider fails, or validation rejects the response.

For a one-off process, set the key only in the local environment; do not put it in Git or the CSV:

```powershell
$env:OPENROUTER_API_KEY = Get-Clipboard
$env:OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
py -3 app.py
```

For a persistent local setup, create `.env.local` once. It is ignored by Git and loaded automatically on every local start. You can copy the three-key value from the clipboard without typing or printing it:

```powershell
$pool = ((Get-Clipboard).Trim() -replace "\s+", ",")
Set-Content .env.local ("OPENROUTER_API_KEYS=" + $pool)
Add-Content .env.local "OPENROUTER_MODELS=google/gemma-4-31b-it:free,google/gemma-4-31b-it:free,google/gemma-4-31b-it:free"
Add-Content .env.local "OPENROUTER_ALLOW_GROUNDED_DATA=1"
py -3 app.py
```

The tracked `.env.local.example` shows the expected shape. Real keys stay only in `.env.local`; the app never prints them. Configured key/model pairs rotate round-robin for successive calls, and a failed pair falls through to the remaining pairs. Rotation distributes requests but cannot bypass a shared provider account or free-tier quota. The LLM may classify wording and rewrite a verified answer, but the CSV engine remains authoritative for facts, calculations, and privacy.

For a local fallback pool, provide comma-separated values. These are read only from the process environment; do not commit them to `.env` or Git:

```powershell
$env:OPENROUTER_API_KEYS = "key-one,key-two"
$env:OPENROUTER_MODELS = "openai/gpt-4o-mini,google/gemini-2.0-flash"
```

The app tries each configured key/model pair after provider failures such as rate limits, then returns to the deterministic engine. This improves availability but does not bypass provider quotas or guarantee free usage.

The customer UI shows only the conversational answer. OpenRouter is optional: it can classify natural language into a small intent shape, while the local deterministic engine remains authoritative for booking facts and privacy.

The prose rewrite path is disabled by default because it would send the verified answer (which may contain booking facts) to OpenRouter. Enable it only if that disclosure is acceptable:

```powershell
$env:OPENROUTER_ALLOW_GROUNDED_DATA = "1"
```

The intent call is constrained to `date_availability`, `package_price`, `count`, `most_common`, `personal_lookup`, or `unsupported`. Its output is validated before it can influence routing; it cannot introduce a new field or value into an answer.

## Pull and run

```powershell
git clone https://github.com/ram15x/wedding-studio-desk.git
cd wedding-studio-desk
py -3 app.py
```

For a hosted process, bind the same app to the platform-provided host and port:

```powershell
$env:ASSIGNMENT_HOST = "0.0.0.0"
$env:ASSIGNMENT_PORT = "10000"
py -3 app.py
```

Open this address in a browser:

```text
http://127.0.0.1:8787
```

The default file is `data/studio_bookings.csv`. To use another CSV, upload it from **Owner desk**. The file must contain at least `booking_id` and `event_date` columns.

## Questions to demonstrate

Supported examples:

```text
Which event type is most common?
What packages are listed?
What is the average package price?
How many bookings are confirmed?
Is 14 December booked?
How much is the Full Package?
What is my balance for SS-2043?
Where is my album? SS-2043
```

Owner reports retain the source file and customer answers use only the uploaded rows; the customer view omits internal provenance labels for readability.

Customer chat does not expose totals, averages, or other customers' bookings. Personal questions require the booking ID. Questions that require information absent from the CSV are escalated instead of guessed:

```text
Why did bookings decline?
Which marketing campaign should we run?
Will bookings increase next month?
```

## Demo flow

Use the customer page like a WhatsApp conversation:

1. Ask `Is 20 December available?` (the next upcoming occurrence is used when the year is omitted).
2. If it is free, the chat offers an in-chat hold form; enter a name and phone number and choose **Request hold**.
3. Ask `What is my balance for SS-2043?` to retrieve a booking-specific value.
4. Ask an unsupported question such as `Why did bookings decline?`; it is escalated to the owner.
5. Open **Owner desk**, reply to the escalation, then return to **Customer chat** to see the owner reply in the same conversation.

The owner inbox shows current open escalations. Historical local demo rows can be cleared by removing only the ignored `assignment.db`; this does not change the supplied CSV.

## Date holds

Ask for a date in the customer chat. A free date is held for 24 hours after the customer enters a name and phone in the inline chat form. The same date cannot be held twice while the first hold is active, and an active hold is reported as unavailable in chat. Dates already present in the CSV cannot be held. The owner can confirm or release an active hold from `/owner`.

## Owner desk

The customer page keeps owner tools hidden. Local `127.0.0.1` runs open the owner desk without a browser login prompt. Non-local requests require HTTP Basic Auth; configure a password before exposing the app:

```powershell
$env:OWNER_PASSWORD = "choose-a-local-owner-password"
py -3 app.py
```

Open `http://127.0.0.1:8787/owner` directly. The owner desk can upload a replacement CSV, review escalations, see active holds, and reply to an escalated customer conversation. Do not expose this demo server publicly without real deployment authentication and durable storage; localhost bypass is intentional for this assignment demo.

## Owner dashboard

The operating picture shows row and field counts, categorical distributions, numeric totals and averages, and past/future dates. It is descriptive only; it does not infer causes, forecasts, policy, or business decisions.

The demo is intentionally bounded: it does not send WhatsApp messages, connect to a live calendar, authenticate real customers, or answer unsupported business questions. A real deployment would need those controls and a hosted service.

## Tests

From the project folder:

```powershell
py -3 -m unittest -q test_app.py
```

The suite covers natural customer phrasing, privacy boundaries, grounded calculations, date holds, escalation, owner replies, CSV replacement, and provider-pool rotation. Provider calls are optional in tests; provider failures must fall back to deterministic answers.

The local SQLite file `assignment.db` and Python caches are intentionally ignored by Git.

## Railway deployment

The current hosted demo runs on Railway:

- Customer chat: https://wedding-studio-desk-production.up.railway.app/
- Owner desk: https://wedding-studio-desk-production.up.railway.app/owner
- Source repository: https://github.com/ram15x/wedding-studio-desk
- Branch: `main`

The service runs the standard-library Python server with:

```text
ASSIGNMENT_HOST=0.0.0.0
ASSIGNMENT_PORT=8787
```

Set these variables privately in Railway before deploying:

```text
OWNER_PASSWORD=<private owner password>
OPENROUTER_API_KEYS=<private comma-separated keys>
OPENROUTER_MODELS=google/gemma-4-31b-it:free
OPENROUTER_ALLOW_GROUNDED_DATA=1
```

Never commit secret values. OpenRouter is optional; deterministic CSV answers remain the safety fallback when the provider is unavailable or rate-limited.

Railway's free trial/free allowance is suitable for a review demo, but it is not a production storage guarantee. The SQLite database, uploaded replacements, holds, and owner replies are stored on ephemeral service storage and may be lost after a redeploy or service reset. A production deployment needs durable storage, customer authentication, backups, and a paid or otherwise persistent hosting plan.

The local tunnel command remains useful for a temporary local review only:

```powershell
py -3 app.py
npx localtunnel --port 8787
```

The laptop and process must remain running while that tunnel is in use.
