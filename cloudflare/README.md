# Cloudflare guest desk

The hosted Ishqweds app runs as a Cloudflare Worker and stores wedding data in Supabase PostgreSQL through Cloudflare Hyperdrive.

## Live service

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health
- Active Worker version seen in the Cloudflare dashboard (22 Oct 2026): `815f06ee` (configuration-only; it still runs the prior app code).
- Latest application source commit pushed to GitHub (22 Oct 2026): `bfd586f` — it is **not deployed to the Worker yet**.

The family desk uses HTTP Basic Auth with username `owner` and the encrypted Cloudflare secret `OWNER_PASSWORD`. Guest login matches the submitted phone number to the guest list; it does not send an SMS or OTP.

## Database

`wrangler.toml` binds `HYPERDRIVE` to the configured Cloudflare Hyperdrive connection. Hyperdrive connects to Supabase PostgreSQL. Apply `supabase_schema.sql` to the intended Supabase project before deploying. The schema creates dedicated `ishqweds_*` tables.

The live synthetic guest list was freshly imported through the Worker upload endpoint, then three RSVP/travel cases and the family reply flow were exercised. A deployment afterward retained 20 guest rows, updated RSVP/headcount/travel values, inbox entries, and a family reply. The import endpoint is verified; a fresh file selection through the Chrome upload control was blocked by the browser extension's local-file permission.

## OpenRouter

`OPENROUTER_API_KEYS` is stored as an encrypted Worker secret. `OPENROUTER_MODELS` is a non-secret variable currently set to `google/gemma-4-31b-it:free`. The Worker sends the message text after best-effort removal of phone numbers and guest-name parts, plus the allowed function and fact keys. The model returns intent JSON only. RSVP records and factual answers are still validated against the guest row and family sheet.

Recent model requests returned rate-limit errors. The Worker now avoids calling OpenRouter for clear greetings, acknowledgements, deterministic RSVP updates, and directly answerable wedding facts. Ambiguous messages still rely on the model and safely escalate when classification fails. Do not describe free-tier model handling as reliable until live paraphrase tests pass without rate-limit failures.

The latest live check (“We are all set for the wedding”) still escalated to the family. It is not recognized by the deterministic parser, so the model-assisted classification gate has not passed.

The Cloudflare settings page confirms that `OPENROUTER_API_KEYS` is present as an encrypted secret and `OPENROUTER_MODELS` is set to `google/gemma-4-31b-it:free`. That confirms configuration exists, not that the key is valid or that the provider returns usable intent. On 22 Oct, the live message “You can count our family in for the big day” still went to the family inbox. The model-assisted paraphrase test therefore **failed live**; local tests use mocked OpenRouter responses.

A separate synthetic request to OpenRouter's `openrouter/free` router returned HTTP 200 from MiniMax M3.1 Flash, but a simple check did not find the expected `kind` and `attendance` fields. That router was not enabled in production.

## Deploy

Requires Node.js, Wrangler authentication, a Supabase PostgreSQL project, and a Hyperdrive configuration.

```powershell
npm install
npm test
npx wrangler deploy --dry-run
npx wrangler deploy
```

Set `OWNER_PASSWORD` and `OPENROUTER_API_KEYS` as Cloudflare Worker secrets. Keep credentials out of `wrangler.toml`, source control, and terminal transcripts. The Hyperdrive ID is a non-secret binding identifier; its database credential is managed by Cloudflare.

## Tests and current limits

`npm test` runs 30 Cloudflare tests, including PostgreSQL adapter checks and a 15-message realistic RSVP/fact matrix. All 30 pass locally. The matrix is automated; it is not proof that every message was manually entered in production. Live checks confirmed the mixed RSVP, count-only/over-invite warning, arrival/flight/room/pickup update, grounded venue answer, unknown-question escalation, family reply in the guest chat, and survival across one redeployment.

The latest source makes RSVP confirmations more specific and conversational, and turns wedding facts into natural sentences such as “The Sangeet is on 20 November 2026 at 6:30 PM.” The wording changes are covered by local tests but remain **unverified on the live Worker** until a new deployment is made.

The two-minute recording is handled by the owner. No WhatsApp integration or SMS OTP is configured. A physical-phone test and fresh file selection through the browser remain to be repeated.
