-- Ishqweds guest desk schema for Supabase PostgreSQL.
-- Uses dedicated table names so existing Supabase project data is untouched.
CREATE TABLE IF NOT EXISTS public.ishqweds_guests (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  phone TEXT NOT NULL UNIQUE,
  side TEXT NOT NULL DEFAULT '',
  functions_json TEXT NOT NULL DEFAULT '[]',
  invited_count INTEGER NOT NULL CHECK (invited_count BETWEEN 1 AND 30),
  rsvp_status TEXT NOT NULL DEFAULT 'pending' CHECK (rsvp_status IN ('pending','coming','not_coming')),
  party_size INTEGER,
  arrival_date TEXT,
  arrival_mode TEXT,
  arrival_time TEXT,
  needs_room INTEGER NOT NULL DEFAULT 0,
  needs_pickup INTEGER NOT NULL DEFAULT 0,
  function_responses_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ishqweds_facts (
  fact_key TEXT PRIMARY KEY,
  fact_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ishqweds_sessions (
  session_id TEXT PRIMARY KEY,
  guest_id BIGINT NOT NULL REFERENCES public.ishqweds_guests(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ishqweds_messages (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES public.ishqweds_sessions(session_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('guest','desk','family')),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ishqweds_family_inbox (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES public.ishqweds_sessions(session_id) ON DELETE CASCADE,
  guest_id BIGINT NOT NULL REFERENCES public.ishqweds_guests(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  reason TEXT NOT NULL,
  reply TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','replied')),
  created_at TEXT NOT NULL,
  replied_at TEXT
);
CREATE INDEX IF NOT EXISTS ishqweds_messages_session_idx ON public.ishqweds_messages(session_id, id);
CREATE INDEX IF NOT EXISTS ishqweds_inbox_status_idx ON public.ishqweds_family_inbox(status, id DESC);
