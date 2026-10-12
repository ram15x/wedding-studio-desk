# Wedding Studio Desk

A small standalone booking assistant for the wedding studio assignment.

It loads the supplied booking CSV and provides:

- a WhatsApp-style customer chat
- answers grounded only in the current CSV
- a simple operating dashboard
- safe escalation when the CSV cannot support an answer
- 24-hour date holds with duplicate protection
- owner upload of a replacement booking sheet

No external model, API key, or database server is required.

## Optional OpenRouter assistance

For more natural replies, the app can send the already-grounded deterministic answer to OpenRouter for rewriting. The model is an editor and explanation assistant; it is not allowed to supply booking facts. If the key is missing, the provider fails, or the response drops a verified fact, the app automatically uses the deterministic answer.

Set the key only in the local process environment; do not put it in Git or the CSV:

```powershell
$env:OPENROUTER_API_KEY = Get-Clipboard
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
py -3 app.py
```

The UI labels an accepted rewrite as **OpenRouter grounded rewrite**. The fallback label is **Deterministic grounded answer**. A key is not required to run the demo safely.

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

Choose a date and customer name, then select **Request hold**. A free date is held for 24 hours. The same date cannot be held twice while the first hold is active. Dates already present in the CSV cannot be held.

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

