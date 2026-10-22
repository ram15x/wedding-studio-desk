# Cloudflare Worker deployment

The wedding guest desk runs as a Cloudflare Worker and stores data in Supabase PostgreSQL through Cloudflare Hyperdrive.

## Live URLs

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health

Family username is owner. Password is the encrypted Cloudflare Worker secret OWNER_PASSWORD.

## Deployment status

On 22 October 2026, Worker version 074f917a-fc1c-4f4a-b642-1620a2284d65 was deployed with Hyperdrive config 3504b16dd1514ef68e00565261f62698. Binding HYPERDRIVE and its ID are in wrangler.toml. Hyperdrive uses encrypted PostgreSQL connections with query caching disabled.

Live read checks returned HTTP 200 for the guest page and /health; health reported 20 guests. Unauthenticated /family returned HTTP 401. Authenticated dashboard reads showed 20 guests, Wedding/Reception/Mehendi/Sangeet groups, two arrivals, two pickups, and two room requests. The inbox had four existing synthetic entries, three open.

This confirms the Worker reads Supabase. No new guest message was sent during this deployment check, so a live RSVP update and unknown-question → family-reply → guest-chat cycle still need an end-to-end run. Phone layout was not retested. Data is synthetic; Railway and old D1 records were not migrated or deleted.

## Deploy

Requirements: Node.js, a Cloudflare API token, and a Supabase PostgreSQL connection.

1. Run npm install in this directory.
2. Apply supabase_schema.sql to the intended Supabase project. It creates only public.ishqweds_* tables.
3. Hyperdrive config ID and binding are in wrangler.toml; the connection credential is stored in Cloudflare Hyperdrive, not this repository.
4. Store OpenRouter keys and the family password as Worker secrets. Secret names are OPENROUTER_API_KEYS and OWNER_PASSWORD. OPENROUTER_MODELS is a non-secret variable. Never print or commit secret values.
5. Run npm test and npx wrangler deploy --dry-run.
6. Deploy with npx wrangler deploy.
7. Verify /health, guest login and chat, RSVP write, dashboard, unknown-question escalation, family reply, and guest conversation.

Check current Cloudflare and Supabase free-plan limits before relying on them for an event. The Worker does not depend on the developer's computer staying on, but quotas and free-plan availability can change.

## Local tests

Run npm test for 13 focused parser and PostgreSQL adapter tests. Run npx wrangler deploy --dry-run for a build check. These do not replace production end-to-end acceptance tests.

For local PostgreSQL testing, set SUPABASE_DB_URL privately and verify TLS with the Supabase CA certificate. Do not disable certificate verification. Use synthetic data.

## Limits

- Guest login matches a listed phone number; it does not send SMS OTP.
- Guest access is web chat, not WhatsApp.
- OpenRouter classifies intent; RSVP and wedding facts come from PostgreSQL.
- Replacing a guest list clears sessions, messages, and inbox entries.
- The deployed dataset is synthetic. No Railway or old D1 data was copied.
- Family routes use Basic Auth. Set and rotate a strong private password.
