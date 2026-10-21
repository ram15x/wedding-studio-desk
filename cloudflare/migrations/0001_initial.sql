CREATE TABLE IF NOT EXISTS wedding_guests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT NOT NULL UNIQUE,
  side TEXT NOT NULL DEFAULT '',
  functions_json TEXT NOT NULL,
  invited_count INTEGER NOT NULL,
  rsvp_status TEXT NOT NULL DEFAULT 'pending',
  party_size INTEGER,
  arrival_date TEXT,
  arrival_mode TEXT,
  arrival_time TEXT,
  needs_room INTEGER NOT NULL DEFAULT 0,
  needs_pickup INTEGER NOT NULL DEFAULT 0,
  function_responses_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wedding_facts (
  fact_key TEXT PRIMARY KEY,
  fact_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guest_sessions (
  session_id TEXT PRIMARY KEY,
  guest_id INTEGER NOT NULL REFERENCES wedding_guests(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guest_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS family_inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  guest_id INTEGER NOT NULL REFERENCES wedding_guests(id),
  question TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  reply TEXT,
  replied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON guest_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON family_inbox(status, id DESC);
