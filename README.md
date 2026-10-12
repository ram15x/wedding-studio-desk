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

Set the key only in the local process environment; do not put it in Git or the CSV:

```powershell
$env:OPENROUTER_API_KEY = Get-Clipboard
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
py -3 app.py
```

For a local fallback pool, provide comma-separated values. These are read only from the process environment; do not commit them to `.env` or Git:

```powershell
$env:OPENROUTER_API_KEYS = "key-one,key-two"
$env:OPENROUTER_MODELS = "openai/gpt-4o-mini,google/gemini-2.0-flash"
```

The app tries each configured key/model pair after provider failures such as rate limits, then returns to the deterministic engine. This improves availability but does not bypass provider quotas or guarantee free usage.

The UI labels an intent-assisted response as **OpenRouter grounded rewrite** only when a separately accepted prose rewrite is enabled. The default fallback label is **Deterministic grounded answer**. A key is not required to run the demo safely.

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

## Date holds

Choose a date, customer name, and phone, then select **Request hold**. A free date is held for 24 hours. The same date cannot be held twice while the first hold is active. Dates already present in the CSV cannot be held. The owner can confirm or release an active hold from `/owner`.

## Owner desk

The customer page keeps owner tools hidden. Set a local owner password before starting the app:

```powershell
$env:OWNER_PASSWORD = "choose-a-local-demo-password"
py -3 app.py
```

Open `http://127.0.0.1:8787/owner` and sign in with username `owner`. The owner desk can upload a replacement CSV, review escalations, see active holds, and reply to an escalated customer conversation. Replies are returned to the same browser conversation; the customer page does not expose the owner APIs without authentication.

## Owner dashboard

The operating picture shows row and field counts, categorical distributions, numeric totals and averages, and past/future dates. It is descriptive only; it does not infer causes, forecasts, policy, or business decisions.

The demo is intentionally bounded: it does not send WhatsApp messages, connect to a live calendar, authenticate real customers, or answer unsupported business questions. A real deployment would need those controls and a hosted service.

## Tests

From the project folder:

```powershell
py -3 -m unittest -q test_app.py
```

The local SQLite file `assignment.db` and Python caches are intentionally ignored by Git.

## Free Render deployment

Create a new Render Web Service from this repository and choose **Blueprint**; Render will read `render.yaml`. Set `OWNER_PASSWORD` and `OPENROUTER_API_KEY` as secret environment values in Render. Do not commit either value. The service uses the supplied CSV and the standard-library Python server, so no Docker or paid dependency is required.

This free deployment is a review/demo environment: its local filesystem is ephemeral, so uploaded replacement files, holds, and owner replies can be lost when the service restarts. A production deployment needs durable storage and real customer authentication.

