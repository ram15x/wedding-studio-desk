# Cloudflare Worker deployment

The wedding guest desk runs as a Cloudflare Worker and stores data in Supabase PostgreSQL through Cloudflare Hyperdrive.

## Live URLs

- Guest chat: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/
- Family desk: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/family
- Health: https://ishqweds-guest-desk.ramnarayanan155-68f.workers.dev/health

Family username is owner. Password is the encrypted Cloudflare Worker secret OWNER_PASSWORD.

## Deployment status

The Worker uses Hyperdrive config `3504b16dd1514ef68e00565261f62698`. Binding HYPERDRIVE and its ID are in `wrangler.toml`. Hyperdrive uses encrypted PostgreSQL connections with query caching disabled.

The active Worker version is `d80e1b65-2417-4be6-87d1-5fa517625078`. After deployment, the family page still showed all 20 guests and their RSVP/travel data, and all 8 wedding facts; this verified that this deploy did not wipe the current records. This is one observed deployment, not a guarantee about every future deployment.

The synthetic 20-guest CSV was freshly imported and verified in Supabase. The upload cleared old sessions/messages/inbox and retained all 8 wedding facts. After live tests, the family page showed 20 guests and 3 sessions; 2 family-inbox items remained (1 open). Live checks passed for mixed RSVP updates, count-only RSVP plus over-invite flag, thanks without escalation, and an unsupported question followed by a family reply visible in the guest chat. After deploying version `d80e1b65-2417-4be6-87d1-5fa517625078`, “Arranging 21 Nov train, need a room and pickup please” saved the arrival, room, and pickup; the refreshed family page showed Asha in the arrival, room, and pickup lists. A third guest (Meena) submitted a separate RSVP/arrival through the live guest API, and the refreshed family page showed the changed headcount and her room request; that third session was not tested through a separate browser UI. Physical-phone retest was not performed in this audit. Replacing the guest list clears sessions, messages, and inbox items. Data is synthetic; Railway and old D1 records were not migrated or deleted.

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

Run npm test for 19 focused parser and PostgreSQL adapter tests. The parser suite includes a 15-message realistic RSVP matrix plus natural month-name, ambiguous-date, and room/pickup wording regressions. These unit tests do not prove production database persistence. Run npx wrangler deploy --dry-run for a build check. These do not replace production end-to-end acceptance tests.

For local PostgreSQL testing, set SUPABASE_DB_URL privately and verify TLS with the Supabase CA certificate. Do not disable certificate verification. Use synthetic data.

## Limits

- Guest login matches a listed phone number; it does not send SMS OTP.
- Guest access is web chat, not WhatsApp.
- OpenRouter classifies intent; RSVP and wedding facts come from PostgreSQL.
- Replacing a guest list clears sessions, messages, and inbox entries.
- The deployed dataset is synthetic. No Railway or old D1 data was copied.
- Family routes use Basic Auth. Set and rotate a strong private password.
