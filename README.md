# Wedding Guest Desk

A phone-friendly web chat and password-protected family desk for one wedding. Guests RSVP, update party size and travel needs, and ask about venue or function details. Unsupported facts go to the family instead of being guessed.

## Live demo

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health
- Source: https://github.com/ram15x/wedding-studio-desk

On 22 October 2026, the Worker was updated to source commit `ddcb57f` and the active version is `d194601a` (100% traffic). It uses Supabase PostgreSQL through Cloudflare Hyperdrive and the `google/gemma-4-31b-it:free` intent model setting. The family dashboard currently shows the 20 synthetic guests and their RSVP/travel rows. This audit did not freshly upload a guest list; replacing it clears sessions, messages, and inbox entries. The data is synthetic; Railway and old D1 data were not migrated.

Live checks: Asha’s mixed Hinglish reply updates Wedding/Mehendi as coming, Sangeet/Reception as not coming, and records 2 people; the family dashboard shows those per-function states. The founder’s count-only example and over-invite warning are visible for Karthik. The exact previously failing English statement (“We're planning to come for the mehendi and wedding, just 2 of us, but we can't make it to the sangeet.”) now updates correctly in production. A different natural phrase (“You can count us in for the wedding.”) still escalated instead of being understood. A minimal test with the two local OpenRouter keys showed one key rate-limited and the other returned valid JSON using the configured Gemma model. The encrypted Cloudflare OpenRouter secret could not be updated with the expired/rejected deployment token, so live LLM intent handling is not yet proven. A physical-phone retest was not performed in this audit. Replacing the guest list clears sessions, messages, and inbox entries.

The local OpenRouter file has two API keys that authenticate successfully. One received HTTP 429 from the free model route; the other produced a valid RSVP JSON response from `google/gemma-4-31b-it:free`. The Worker’s existing encrypted secret is still the older value; the latest deployment token was rejected when updating it. Do not treat the model setting or a valid local key as proof that production LLM classification works.

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

OpenRouter classifies intents; it receives redacted message text and allowed function/fact-key names. RSVP values and wedding facts come from PostgreSQL; the model does not write records or supply facts. The active Worker’s model setting is Gemma 4 31B IT Free. Production still has an older encrypted key value that could not be verified or replaced during this pass. One novel RSVP phrase escalated live, so do not claim the model is working reliably until the encrypted secret is updated and that test passes. Deterministic parsing handles supported patterns; unclear messages should escalate. It is not a general-purpose answer bot, and multiple keys from one account do not multiply its quota. Redaction is best-effort.

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

From cloudflare/: npm test — 24 parser and PostgreSQL adapter tests passed, including a 15-message realistic RSVP matrix, natural English mixed RSVP parsing, model-key failover, natural room/pickup wording, and arrival-date regressions. These parser tests do not replace a production database round-trip. npx wrangler deploy --dry-run checks build and bindings.

Worker version `d194601a` is active at 100% and includes the Gemma model setting. The deterministic RSVP fix is live and the reported English mixed-RSVP example now passes. The novel “count us in” example still escalates, and the encrypted OpenRouter key secret is not verified. The local suites pass (24 Cloudflare tests and 80 Python tests), but they do not prove every wording or language. Updating the encrypted Worker secret with a valid Cloudflare token and retesting that novel phrasing remain release checks.

The requested two-minute recording is being handled by the owner.
