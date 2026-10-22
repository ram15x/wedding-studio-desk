# Wedding Guest Desk

A phone-friendly web chat and password-protected family desk for one wedding. Guests RSVP, update party size and travel needs, and ask about venue or function details. Unsupported facts go to the family instead of being guessed.

## Live demo

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health
- Source: https://github.com/ram15x/wedding-studio-desk

On 22 October 2026, Worker version `d80e1b65-2417-4be6-87d1-5fa517625078` was deployed with Supabase PostgreSQL through Cloudflare Hyperdrive. A fresh import of the synthetic 20-guest CSV was verified directly in Supabase; it cleared prior QA sessions, messages, and inbox entries while preserving all 8 wedding facts. After the live QA and deployment, the family page still showed all 20 guests and 8 facts, with 3 guest sessions and 2 inbox items. The data is synthetic; Railway and old D1 data were not migrated.

Live checks after the import: Asha’s mixed Hinglish reply updated Wedding to coming for 2 people and Reception to not coming; Karthik’s “Hum 6 log aayenge” marked his invited functions as coming and flagged the count above his invitation; “Thanks!” got a reply without escalation; an unsupported pet question went to the family, and the family reply appeared in Asha’s chat. Asha’s train and 21 November 2026 arrival date saved. After deploying version `d80e1b65-2417-4be6-87d1-5fa517625078`, “Arranging 21 Nov train, need a room and pickup please” saved the arrival, room, and pickup; the refreshed family dashboard showed those details. A third guest (Meena) submitted a separate RSVP/arrival through the live guest API, and the refreshed family page showed the changed headcount and her room request. That third session was not tested through a separate browser UI. A physical-phone retest was not performed in this audit. Replacing the guest list clears sessions, messages, and inbox entries.

Additional audit on 22 October: an unfamiliar RSVP sentence mentioning “wedding” was incorrectly answered with the wedding schedule and did not update the RSVP. The latest source limits fact answers to question-like requests and strengthens intent classification; it is not yet deployed. A new OpenRouter key was copied into the Worker’s encrypted `OPENROUTER_API_KEYS` secret, and Cloudflare created a ready Worker version for that secret update. This proves the secret is stored, not that OpenRouter accepted it or that intent classification is reliable. In a live chat after the update, a mixed Hinglish RSVP updated Wedding and Reception separately, but a different natural English RSVP was still answered with the wedding schedule. The active source therefore still needs deployment and another live test.

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

OpenRouter intent parsing is configured as an optional classifier. It receives redacted message text and allowed function/fact-key names. RSVP values and wedding facts come from PostgreSQL; the model does not write records or supply facts. The Worker currently has one encrypted OpenRouter key configured; the secret value cannot be read back from Cloudflare, and a secret being present does not confirm that the provider accepts it. The latest live tests showed one mixed Hinglish RSVP updating correctly and one natural English RSVP being mishandled by the still-active Worker code. If no valid key is configured, the app falls back to deterministic parsing and escalates unsupported wording. It is not a general-purpose answer bot. Multiple keys from one account do not multiply its quota. Redaction is best-effort.

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

From cloudflare/: npm test — 22 parser and PostgreSQL adapter tests passed, including a 15-message realistic RSVP matrix, model-key failover, natural room/pickup wording, and arrival-date regressions. These parser tests do not replace a production database round-trip. npx wrangler deploy --dry-run checks build and bindings.

The natural pickup/room wording fix is deployed as Worker version `d80e1b65-2417-4be6-87d1-5fa517625078`. Cloudflare later created version `a20ca8e2` for the `OPENROUTER_API_KEYS` secret update; that version did not include the latest source. The source fix for RSVP/fact misclassification and OpenRouter fallback is still awaiting deployment. The local suites pass (22 Cloudflare tests and 80 Python tests), but they do not prove every wording or language; the failed live English RSVP remains a release blocker.

The requested two-minute recording is being handled by the owner.
