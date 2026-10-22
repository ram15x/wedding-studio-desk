# Wedding Guest Desk

A phone-friendly web chat and password-protected family desk for one wedding. Guests RSVP, update party size and travel needs, and ask about venue or function details. Unsupported facts go to the family instead of being guessed.

## Live demo

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health
- Source: https://github.com/ram15x/wedding-studio-desk

On 22 October 2026, Worker version 074f917a-fc1c-4f4a-b642-1620a2284d65 was deployed with Supabase PostgreSQL through Cloudflare Hyperdrive. Read-only live checks passed: guest page HTTP 200; /health HTTP 200 with 20 guests; unauthenticated /family HTTP 401; authenticated dashboard with 20 guest rows and four function groups. It showed two arrivals, two pickup entries, and two room requests. The existing synthetic inbox had four items, three open; it was not clean.

This deployment check did not send a new guest message. A live RSVP write and the unsupported-question → family-reply → guest-chat cycle remain unverified after the database cutover. Phone layout was not retested. Data is synthetic; Railway and old D1 data were not migrated or deleted.

## Features and limits

- Imports guest rows (name, phone, side, functions, invited people) and wedding facts (item,value).
- Phone matching does not send or verify SMS. There is no WhatsApp integration.
- Records RSVP, party size, arrival date/mode, room requests, and pickup requests.
- Shows per-function coming, not coming, and pending counts, plus arrivals, pickups, and room requests.
- Answers venue and schedule questions from uploaded facts. Unknown questions go to the family inbox; family replies can appear in the same guest chat.
- Mixed RSVP updates functions separately; party size above the invitation count is flagged for family review.
- “ok” and “thanks” are handled conversationally. Common English and Latin-script Hinglish are tested, not every phrase or language.
- Replacing the guest list clears sessions, messages, and inbox entries.

## OpenRouter

OpenRouter intent parsing is configured as an optional classifier. It receives redacted message text and allowed function/fact-key names. RSVP values and wedding facts come from PostgreSQL; the model does not write records or supply facts. The free model router, provider availability, quotas, quality, and latency can vary. Multiple keys from one account do not multiply its quota. Redaction is best-effort.

## Run locally on Windows

Requires Python 3.10 or newer. Local mode uses SQLite.

    cd C:/Users/ramna/OneDrive/Desktop/wedding-studio-desk
    py -3 app.py

Open http://127.0.0.1:8787/ for guests and http://127.0.0.1:8787/family for the family desk. Family username is owner; set OWNER_PASSWORD in ignored .env.local. Keep the terminal running.

For phone testing on the same Wi-Fi, set ASSIGNMENT_HOST to 0.0.0.0 before starting and open http://<computer-LAN-IP>:8787/ on the phone.

## Fictional demo data

Upload data/demo_guest_list.csv and data/demo_wedding_details.csv from the family desk. Demo numbers are 9000000001 through 9000000020; no OTP is sent.

    Haan aa rahe hain, 4 log, 21 ko train se
    Hum 2 log aayenge shaadi mein, reception nahi aa paayenge
    Hum 6 log aayenge
    Hum dono aa rahe hain, flight se 20 Nov ko. Room chahiye.
    Nahi aa payenge, sorry
    Venue kahan hai?
    Mehendi kab hai?
    Sangeet ka time kya hai?
    ok
    thanks
    Can we bring our dog to the venue?

The pet-policy question should reach the family inbox. Reply from the family desk and check the same guest chat.

## Database and deploy

The Worker uses Supabase PostgreSQL through the HYPERDRIVE binding. cloudflare/supabase_schema.sql creates only public.ishqweds_* tables. Hyperdrive uses encrypted connections with query caching disabled. Deployment steps are in cloudflare/README.md. The Worker does not depend on the developer's computer staying on. Free-plan quotas and availability can change.

Do not commit .env.local, API keys, passwords, or real guest data. Owner routes use Basic Auth and the Cloudflare OWNER_PASSWORD secret.

## Tests

Python: py -3 -m unittest -v test_app.py — 80 tests passed on 22 October 2026, including 15 realistic English/Hinglish message cases.

From cloudflare/: npm test — 13 parser and PostgreSQL adapter tests passed. npx wrangler deploy --dry-run checks build and bindings.

The live smoke test checked Worker startup, Supabase-backed health, guest page, and family authentication/dashboard reads. It did not exercise live guest writes or the family-reply round trip. Tests do not prove every wording or language.

The requested two-minute recording is being handled by the owner.
