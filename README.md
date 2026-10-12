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

## Pull and run

```powershell
git clone https://github.com/ram15x/wedding-studio-desk.git
cd wedding-studio-desk
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

The answer includes the source file and uses only the uploaded rows.

Customer chat does not expose totals, averages, or other customers' bookings. Personal questions require the booking ID. Questions that require information absent from the CSV are escalated instead of guessed:

```text
Why did bookings decline?
Which marketing campaign should we run?
Will bookings increase next month?
```

## Date holds

Choose a date and customer name, then select **Request hold**. A free date is held for 24 hours. The same date cannot be held twice while the first hold is active. Dates already present in the CSV cannot be held.

## Owner dashboard

The operating picture shows row and field counts, categorical distributions, numeric totals and averages, and past/future dates. It is descriptive only; it does not infer causes, forecasts, policy, or business decisions.

## Tests

From the project folder:

```powershell
py -3 -m unittest -q test_app.py
```

The local SQLite file `assignment.db` and Python caches are intentionally ignored by Git.

