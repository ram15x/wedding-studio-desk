# Cloudflare Worker deployment

The wedding guest desk runs as a Cloudflare Worker and stores data in Supabase PostgreSQL through Cloudflare Hyperdrive.

## Live URLs

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health

Family username is owner. Password is the encrypted Cloudflare Worker secret OWNER_PASSWORD.

## Deployment status

The Worker uses Hyperdrive config `3504b16dd1514ef68e00565261f62698`. Binding HYPERDRIVE and its ID are in `wrangler.toml`. Hyperdrive uses encrypted PostgreSQL connections with query caching disabled.

The active Worker version is `d194601a` (100% traffic), with source commit `ddcb57f` and model setting `google/gemma-4-31b-it:free`. The family page still shows 20 synthetic guests and their RSVP/travel data. This confirms the observed deployments retained the rows; it is not a guarantee about every future deployment.

Live checks: the founder’s mixed Hinglish RSVP and count-only example update the dashboard correctly, including an over-invite flag. The exact natural-English mixed RSVP that previously failed now updates Mehendi and Wedding as coming, Sangeet as not coming, and party size 2. A different “You can count us in for the wedding” statement still escalated. Two local OpenRouter keys authenticate; one received HTTP 429 and one returned valid JSON using Gemma. The encrypted Worker key secret could not be updated with the expired/rejected deployment token, so production LLM use remains unverified. A physical-phone retest was not performed in this audit. Replacing the guest list clears sessions, messages, and inbox items. The current data is synthetic; Railway and old D1 records were not migrated or deleted.

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

Run npm test for 24 focused parser and PostgreSQL adapter tests. The parser suite includes a 15-message realistic RSVP matrix plus natural English mixed RSVP, natural month-name, ambiguous-date, room/pickup wording, multi-key failover, and RSVP/fact misclassification regressions. These unit tests do not prove production database persistence. Run npx wrangler deploy --dry-run for a build check. These do not replace production end-to-end acceptance tests.

For local PostgreSQL testing, set SUPABASE_DB_URL privately and verify TLS with the Supabase CA certificate. Do not disable certificate verification. Use synthetic data.

## Limits

- Guest login matches a listed phone number; it does not send SMS OTP.
- Guest access is web chat, not WhatsApp.
- OpenRouter classifies intent; RSVP and wedding facts come from PostgreSQL.
- Replacing a guest list clears sessions, messages, and inbox entries.
- The deployed dataset is synthetic. No Railway or old D1 data was copied.
- Family routes use Basic Auth. Set and rotate a strong private password.
