# Wedding Studio Desk

Standalone assignment project. It is intentionally separate from the main ZERO platform.

It loads a booking CSV, answers only from the loaded rows, escalates questions that the sheet cannot support, and protects 24-hour date holds with a SQLite transaction and a unique active-date constraint. The customer view is a small WhatsApp-style desk; the owner view also exposes a grounded operating dashboard and downloadable brief.

The assignment does not require an API key or a hosted model. Its intelligence layer is a deterministic, schema-aware interpreter over the currently uploaded sheet. It discovers the visible columns at runtime and can answer supported orientation, grouped-count, total, average, comparison, date, and upcoming-schedule questions. It refuses unsupported causes, recommendations, policy claims, and facts absent from the sheet, then places those questions in the owner inbox. This is intentional: a generic LLM would make the demo sound more fluent while weakening the sheet-only guarantee.

### Optional grounded prose synthesis

For a clearer owner-facing explanation, an OpenRouter model can be enabled without making it the source of truth. Set these variables in the process that runs the app (never commit them):

```powershell
$env:OPENROUTER_API_KEY = '<set locally; do not paste into source>'
$env:OPENROUTER_MODEL = 'openai/gpt-4o-mini'
python assignment/app.py
```

The app first computes the answer deterministically from the uploaded rows. The optional model receives only that verified answer and the question, and may rewrite it in plain language. The response is accepted only if every numeric/date anchor is preserved; missing configuration, timeout, provider error, malformed output, or changed anchors automatically returns the deterministic answer. Unsupported or escalated questions never call the model. The API key is read from the environment, never stored in SQLite, returned to the browser, or logged. A live key/model is required to test this path; the repository tests use a mocked provider.

## Run

] run from its extracted folder:

```powershell
py -3 app.py
```

Open `http://127.0.0.1:8787`.

The Owner desk includes a CSV upload control. Uploading a new valid sheet replaces the active source for this local demo; the required columns are `booking_id` and `event_date`.

Docker is also supported:

```powershell
docker compose -f assignment/docker-compose.yml up --build
```

For a free Render deployment from the broader ZERO repository, use `assignment/render.yaml`. If you publish the contents of this directory as a standalone repository, rename `render.standalone.yaml` to `render.yaml` before creating the Render service. The service is a demo deployment with local SQLite storage; do not use it for real customer data without a persistent database and authentication.

To publish safely without pushing the broader ZERO repository, run from PowerShell in the extracted assignment directory:

```powershell
.\publish_standalone.ps1 -RepositoryUrl https://github.com/<your-account>/wedding-studio-desk.git
```

Use `RECORDING_SCRIPT.md` for the short acceptance recording.

Optional configuration:

```powershell
$env:ASSIGNMENT_CSV = 'C:\path\to\another.csv'
$env:ASSIGNMENT_PORT = '8787'
```

The default CSV is `assignment/data/studio_bookings.csv` in the broader repository, or `data/studio_bookings.csv` in the standalone package. No model or external API is required to run the demo; answers are generated from the loaded records and every answer shows its source and limits.

## Read-only reporting APIs

- `GET /api/dashboard` returns row/column counts, grouped booking fields, numeric totals/averages, and past/future row counts.
- `GET /api/report` returns the structured operating brief.
- `GET /api/report.md` returns a downloadable Markdown brief with observations, a conservative operating SOP, and explicit limitations.

These reports are deterministic and source-grounded. They do not infer causes, policy, capacity, or demand forecasts. An external model/API can be added later behind a reviewed adapter, but it is not required for this assignment and no key is stored in the project.

## Demo flows

- Ask about packages, prices, dates, status, album stage, cities, or availability.
- Ask what the data represents, which category is most common, totals/averages, comparisons by a visible category, exact dates, or upcoming schedule rows.
- Ask for a date hold with `Hold 2026-11-22 for Riya Sharma`.
- Repeat the same hold to see the conflict response.
- Use the Owner inbox to review escalated questions.
- Review the Operating picture card and download the grounded brief.

This is an assignment demo, not a production WhatsApp integration. Real WhatsApp Business webhooks, authentication, payments, and deployment are out of scope.

## Deliberate boundaries

- Charts are lightweight HTML bar views generated from the uploaded categorical columns; this is a compact reporting view, not Tableau.
- Future planning means reporting future-dated rows in the file. It does not forecast demand, infer capacity, or promise availability.
- A model/API adapter can be added later if a reviewed provider and budget are available. It is not used in this assignment, so there is no key to configure and no external service failure to hide.
