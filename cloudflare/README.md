# Cloudflare Worker deployment

This directory contains the Cloudflare Workers + D1 version of the Ishqweds wedding guest desk. D1 stores guest rows, wedding facts, RSVP/travel updates, sessions, chat messages, and family inbox/replies. The Worker is request-driven, so it does not rely on a local server staying awake.

## Current status

The public test URL is:

**https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev**

The Worker has a D1 database and synthetic 20-guest wedding data. The D1 database survived a Worker redeploy in an earlier check. OpenRouter is configured as an optional intent parser: it classifies the guest's message, while facts and guest records still come from D1. If the provider is unavailable or rate-limited, the Worker falls back to its deterministic parser. This is a prototype deployment; production parity with the Python app and migration of Railway data have not been completed or verified.

The three configured keys are stored as Cloudflare secrets. They belong to one OpenRouter account, so they do not multiply that account's free-tier quota. The `openrouter/free` model router chooses an available free model; free-provider availability, rate limits, output quality and latency can vary. Never treat a model classification as the source of guest or wedding facts.

## Deploy

1. Install Node.js, then from this directory run `npm install`.
2. Sign in with `npx wrangler login --device --scopes user:read account:read workers:write workers_scripts:write d1:write` (device login avoids the localhost callback issue in some environments).
3. Create the persistent D1 database: `npx wrangler d1 create ishqweds-guest-desk`.
4. Copy the returned database ID into `wrangler.toml`, replacing `REPLACE_WITH_D1_DATABASE_ID`.
5. Set an owner password as a Cloudflare secret: `npx wrangler secret put OWNER_PASSWORD`. The current deployment's generated password is kept in the ignored local file `.owner-password.local`; do not commit or share it publicly.
6. Apply the schema remotely: `npm run db:remote`.
7. Deploy: `npm run deploy`.
8. Test `/health`, `/`, and `/family`. The deployed D1 database contains synthetic demo data. A replacement guest-list upload clears guest sessions, chats, and inbox entries.

For local development, use `npm run db:local` and `npm run dev`. Wrangler creates a local D1 database under its local state directory; it is separate from the production database.

## Important boundaries

- Guest access currently matches a phone number from the uploaded list. It does not send an OTP.
- The URL is public. Anyone can open the guest page; family routes require the `owner` Basic Auth account and the `OWNER_PASSWORD` secret. The demo guest list uses synthetic phone numbers.
- Uploading a replacement guest list clears guest sessions, chat history, and family inbox, matching the current app behavior. Export anything that must be retained first.
- Cloudflare Workers and D1 have plan-specific request, CPU, storage, and database limits. Check the current Cloudflare plan terms before production use.
- D1 is a different database from Supabase and Railway. Existing records are not copied automatically. Only the synthetic demo CSVs are loaded. No production-data migration has been done.
- `workers_dev = true` exposes the production test URL; preview URLs are disabled. This deployment uses a public `workers.dev` address and has no custom domain.
- Do not delete the old Railway service or volume until its data is exported or confirmed disposable, and the Cloudflare app passes the same acceptance checks against migrated data. This repository does not have a verified Render production deployment.

## Verify and test

Run the Cloudflare unit checks:

```powershell
npm test
```

The current unit suite has eight checks for count-only RSVP, per-function mixed RSVP, preserving a function decline during a later travel update, greeting fallback, language-aware venue wording, and schedule formatting. A separate local D1 acceptance run used the synthetic 20-guest CSV and 8 wedding facts to exercise 15 realistic messages plus the family-reply round trip. It verified three different guest RSVP styles, an over-invitation flag, arrivals/pickup, schedule and venue answers, acknowledgement handling, and escalation. It did not alter the deployed database. Repeat the deployed flow and a phone check before using actual guest data; local tests do not prove the deployed build or physical-device behavior. Phone-number matching is not identity verification; there is no SMS or OTP.
