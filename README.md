# Ishqweds Wedding Guest Desk

A phone-friendly web chat for wedding guests, with a password-protected family desk. Guests can RSVP, share arrival details, ask about facts in the family sheet, and get a family reply when the sheet cannot answer. The desk does not invent wedding details.

## Live demo

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health
- Source: https://github.com/ram15x/wedding-studio-desk

The family desk uses HTTP Basic Auth. Username: `owner`; password is the encrypted Cloudflare `OWNER_PASSWORD` secret. Guest login matches a listed phone number; it does not send an SMS code.

## What I checked on 22 October 2026

The active Cloudflare Worker version is `3d67a6c8-218a-44f6-bac4-08ff3008a225`. It uses Supabase PostgreSQL through Cloudflare Hyperdrive. I uploaded the repository's synthetic 20-guest CSV and wedding-details CSV to the live import endpoints, then ran the RSVP and reply checks below. The CSV upload endpoint accepted all 20 rows; the browser's file chooser could not be used because the Chrome extension blocks local-file access, so a fresh upload through the visible file picker is still unverified.

| Guest message | Observed result |
| --- | --- |
| “Hum 2 log aayenge shaadi mein, reception nahi aa paayenge” | Asha's Wedding response became coming, Reception became not coming, and the party size became 2. The family dashboard showed those separate answers. |
| “Hum 6 log aayenge” | Karthik was marked coming for his invited functions and the party size became 6. Because his invitation listed 2, the family inbox flagged the difference. |
| “Hum 2 log aa rahe hain, flight se 20 Nov ko. Room chahiye aur pickup bhi.” | Meena's row showed 2 people, a 20 November 2026 flight, a room request, and a pickup request. The dashboard headcount and pickup list reflected the update. |
| “Venue kahan hai?” | The chat answered from the uploaded sheet: Lotus Convention Centre, 12 Park Road, Coimbatore. |
| “Can we bring our dog to the wedding?” | The chat did not guess. It sent the question to the family inbox. A family reply sent from the family desk appeared in Karthik's guest conversation; a separate reply round-trip was also checked through the live API. |

I redeployed the Worker after those updates. The health endpoint still reported 20 guests, and the RSVP counts, travel details, inbox items, and family reply remained in Supabase afterward. That verifies this deployment did not reset the database.

## What still needs checking

- A real phone retest is still needed. The owner previously reported that the site works on their phone; I did not independently use a physical phone in this QA run.
- The OpenRouter key secret is stored in Cloudflare and the Worker is configured for `google/gemma-4-31b-it:free`. Recent model requests hit rate limits, and three natural RSVP paraphrases escalated instead of being understood. The code now skips model calls for greetings, acknowledgements, clear deterministic RSVPs, and facts it can answer directly. Ambiguous wording still depends on OpenRouter, so model-assisted intent handling is not yet reliable enough to call complete.
- After the latest deployment, “We are all set for the wedding” still escalated to the family. That wording is not covered by the deterministic parser, so this live check did not pass the OpenRouter intent-classification gate.
- The Worker test suite includes a 15-message realistic RSVP/fact matrix. It passes locally, but not all 15 messages have been manually entered in the live chat.

The demo roster and wedding details are fictional. The app handles supported wedding questions and RSVP updates; it cannot promise to answer every possible message. When the available details do not support an answer, it sends the question to the family.

## Run and test the Worker

Install Node.js, then from `cloudflare/` run:

```powershell
npm install
npm test
npx wrangler deploy --dry-run
```

For a real deploy, configure `HYPERDRIVE`, `OWNER_PASSWORD`, and `OPENROUTER_API_KEYS` in Cloudflare. `cloudflare/wrangler.toml` contains the Worker name, Hyperdrive binding, and non-secret settings. Apply `cloudflare/supabase_schema.sql` to the intended Supabase project before the first deployment. Never commit `.env.local`, passwords, API keys, or real guest data.

The repository also retains the earlier local Studio Desk prototype (`app.py` and `test_app.py`). The hosted Ishqweds guest desk runs from `cloudflare/`.

## Scope

- Guest chat is a web page, not WhatsApp Business.
- Phone-number matching is not OTP verification.
- Supabase holds guest rows, wedding facts, sessions, messages, and family inbox items.
- Replacing the guest CSV clears guest sessions, messages, inbox entries, and RSVP updates.
- The requested two-minute recording is being handled by the owner.
