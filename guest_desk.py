"""Guest desk domain logic for one wedding.

The module deliberately keeps interpretation local and deterministic. Uploaded
rows and family-provided facts are the only source of answers; uncertain text
is placed in the persistent family inbox.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone


GUEST_ALIASES = {
    "name": ("name", "guest_name", "full_name", "guest name"),
    "phone": ("phone", "phone_number", "mobile", "contact", "whatsapp", "phone number"),
    "side": ("side", "family_side", "guest_side", "family", "side of family"),
    "functions": ("functions", "events", "functions_invited", "event_functions", "functions invited"),
    "people": ("people", "party_size", "guest_count", "number_of_people", "number of people", "how many people"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {normalize_header(item): item for item in headers}
    for alias in aliases:
        if normalize_header(alias) in normalized:
            return normalized[normalize_header(alias)]
    return None


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wedding_guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            side TEXT NOT NULL DEFAULT '',
            functions_json TEXT NOT NULL DEFAULT '[]',
            function_responses_json TEXT NOT NULL DEFAULT '{}',
            invited_count INTEGER NOT NULL DEFAULT 1,
            rsvp_status TEXT NOT NULL DEFAULT 'pending' CHECK(rsvp_status IN ('pending','coming','not_coming')),
            party_size INTEGER,
            arrival_date TEXT,
            arrival_mode TEXT,
            arrival_time TEXT,
            needs_room INTEGER NOT NULL DEFAULT 0,
            needs_pickup INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
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
            session_id TEXT NOT NULL REFERENCES guest_sessions(session_id),
            role TEXT NOT NULL CHECK(role IN ('guest','desk','family')),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS family_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES guest_sessions(session_id),
            guest_id INTEGER NOT NULL REFERENCES wedding_guests(id),
            question TEXT NOT NULL,
            reason TEXT NOT NULL,
            reply TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','replied')),
            created_at TEXT NOT NULL,
            replied_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_guest_messages_session ON guest_messages(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_family_inbox_status ON family_inbox(status, id DESC);
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(wedding_guests)")}
    if "function_responses_json" not in columns:
        conn.execute("ALTER TABLE wedding_guests ADD COLUMN function_responses_json TEXT NOT NULL DEFAULT '{}'")
    conn.commit()


def upload_guests(conn: sqlite3.Connection, content: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".csv"):
        raise ValueError("Upload a CSV guest list. Save the sheet as CSV and try again.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The guest list must be a UTF-8 CSV file.") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    columns = {key: _find_column(headers, aliases) for key, aliases in GUEST_ALIASES.items()}
    missing = [key for key in ("name", "phone", "side", "functions", "people") if not columns[key]]
    if missing:
        raise ValueError("Guest list needs columns for name, phone, side, functions, and how many people.")
    parsed = []
    for line_no, raw in enumerate(reader, start=2):
        name = (raw.get(columns["name"]) or "").strip()
        phone = normalize_phone(raw.get(columns["phone"]) or "")
        side = (raw.get(columns["side"]) or "").strip()
        functions_text = (raw.get(columns["functions"]) or "").strip()
        count_text = (raw.get(columns["people"]) or "").strip()
        if not name and not phone and not functions_text:
            continue
        if not name or len(phone) < 10 or not functions_text:
            raise ValueError(f"Row {line_no}: name, a valid 10-digit phone number, and at least one function are required.")
        try:
            count = int(count_text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {line_no}: number of people must be a whole number.") from exc
        if count < 1 or count > 30:
            raise ValueError(f"Row {line_no}: number of people must be between 1 and 30.")
        functions = [part.strip() for part in re.split(r"[;,|]", functions_text) if part.strip()]
        parsed.append((name, phone, side, json.dumps(functions, ensure_ascii=False), count))
    if not parsed:
        raise ValueError("The CSV has no guest rows.")
    if len({row[1] for row in parsed}) != len(parsed):
        raise ValueError("The guest list has duplicate phone numbers. Each guest needs a unique phone number.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM wedding_guests")
        conn.execute("DELETE FROM guest_sessions")
        conn.execute("DELETE FROM guest_messages")
        conn.execute("DELETE FROM family_inbox")
        conn.executemany("""INSERT INTO wedding_guests(name,phone,side,functions_json,invited_count)
                          VALUES(?,?,?,?,?)""", parsed)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"filename": filename, "guests": len(parsed), "functions": sorted({f for row in parsed for f in json.loads(row[3])})}


def upload_facts(conn: sqlite3.Connection, content: bytes, filename: str) -> dict:
    if not filename.lower().endswith(".csv"):
        raise ValueError("Upload wedding details as a CSV with columns item and value.")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise ValueError("Wedding details must be a UTF-8 CSV file.") from exc
    headers = reader.fieldnames or []
    key_col = _find_column(headers, ("item", "key", "detail", "question", "function"))
    value_col = _find_column(headers, ("value", "answer", "details", "information", "date_time_location"))
    if not key_col or not value_col:
        raise ValueError("Wedding details CSV needs two columns: item and value.")
    facts = []
    for row in reader:
        key = (row.get(key_col) or "").strip()
        value = (row.get(value_col) or "").strip()
        if key and value:
            facts.append((normalize_header(key), value, utc_now()))
    if not facts:
        raise ValueError("No wedding details were found in the CSV.")
    conn.executemany("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES(?,?,?) ON CONFLICT(fact_key) DO UPDATE SET fact_value=excluded.fact_value,updated_at=excluded.updated_at", facts)
    conn.commit()
    return {"filename": filename, "details": len(facts)}


def start_guest_session(conn: sqlite3.Connection, phone: str, session_id: str) -> dict:
    normalized = normalize_phone(phone)
    row = conn.execute("SELECT id,name FROM wedding_guests WHERE phone=?", (normalized,)).fetchone()
    if not row:
        return {"success": False, "message": "I couldn't match that number to the guest list. Please check the number or contact the family."}
    conn.execute("INSERT INTO guest_sessions(session_id,guest_id,created_at) VALUES(?,?,?) ON CONFLICT(session_id) DO UPDATE SET guest_id=excluded.guest_id", (session_id, row["id"], utc_now()))
    conn.commit()
    return {"success": True, "guest": {"name": row["name"]}}


def session_guest(conn: sqlite3.Connection, session_id: str):
    return conn.execute("SELECT g.* FROM guest_sessions s JOIN wedding_guests g ON g.id=s.guest_id WHERE s.session_id=?", (session_id,)).fetchone()


def _facts(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["fact_key"]: row["fact_value"] for row in conn.execute("SELECT fact_key,fact_value FROM wedding_facts")}


def _resolve_arrival_date(text: str, facts: dict[str, str]) -> str | None:
    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).isoformat()
        except ValueError:
            return None
    month_names = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    dm = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})(?:\s+(20\d{{2}}))?\b", text, re.I)
    if dm:
        try:
            month = datetime.strptime(dm.group(2)[:3].title(), "%b").month
            year = int(dm.group(3)) if dm.group(3) else None
            day_value = int(dm.group(1))
            if year:
                return date(year, month, day_value).isoformat()
            candidates = _scheduled_dates(facts)
            matches = [d for d in candidates if d.month == month and d.day == day_value]
            return matches[0].isoformat() if len(matches) == 1 else None
        except ValueError:
            return None
    day = re.search(r"\b(\d{1,2})\s*(?:ko|tarikh)\b", text.lower())
    if not day:
        day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", text.lower())
    if not day:
        return None
    target_day = int(day.group(1))
    if not 1 <= target_day <= 31:
        return None
    candidates = [d for d in _scheduled_dates(facts) if d.day == target_day]
    return candidates[0].isoformat() if len({d.isoformat() for d in candidates}) == 1 else None


def _scheduled_dates(facts: dict[str, str]) -> list[date]:
    candidates = []
    for key, value in facts.items():
        if any(token in key for token in ("date", "schedule", "function", "wedding")):
            for match in re.finditer(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", value):
                try:
                    candidate = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                    candidates.append(candidate)
                except ValueError:
                    pass
    return candidates


def _extract_updates(text: str, guest) -> tuple[dict, list[str]]:
    low = text.lower()
    updates = {}
    notes = []
    yes = re.search(r"\b(?:haan|han|yes|yep|yeah|coming|aa\s*rahe|aa\s*rahi|will attend|attending|count us in|we'll come|we will come)\b", low)
    no = re.search(r"\b(?:nahi|nahin|no|not coming|can't come|cannot come|won't (?:make it|come)|not attending|unable to come)\b", low)
    if yes and no and yes.start() < no.start():
        yes = None
    if no:
        updates["rsvp_status"] = "not_coming"
        updates["party_size"] = 0
        notes.append("not_coming")
    elif yes:
        updates["rsvp_status"] = "coming"
        notes.append("coming")
    count_match = re.search(r"\b(\d{1,2})\s*(?:log|people|persons|members|of us|jan(?:e)?|hum|family members)\b|\b(?:we are|hum|family of)\s*(\d{1,2})\b", low)
    count = int(count_match.group(1) or count_match.group(2)) if count_match else None
    if count is None and re.search(r"\b(?:hum\s+dono|dono\s+(?:log|people)|both\s+of\s+us|we\s+both|the\s+two\s+of\s+us)\b", low):
        count = 2
    if count is not None and 1 <= count <= 30:
        updates["party_size"] = count
        notes.append("count")
    mode = None
    if re.search(r"\b(?:train|rail|railway|tren)\b", low): mode = "train"
    if re.search(r"\b(?:flight|plane|airplane|aeroplane|by air|flight se)\b", low): mode = "flight"
    if mode:
        updates["arrival_mode"] = mode
        notes.append("arrival_mode")
    if re.search(r"\b(?:hotel|room|stay|accommodation|rukne|kamra)\b", low):
        if re.search(r"\b(?:don't|dont|no|not|nahi|nahin)\s+(?:need|want)?\s*(?:a\s+)?(?:room|hotel|stay)\b", low):
            updates["needs_room"] = 0
        elif re.search(r"\b(?:need|want|chahiye|chaahiye|book|reserve)\b", low) or "room chahiye" in low:
            updates["needs_room"] = 1
        if "needs_room" in updates: notes.append("needs_room")
    if re.search(r"\b(?:pickup|pick up|pick-up|drop|airport pickup|station pickup|gaadi)\b", low):
        if re.search(r"\b(?:don't|dont|no|not|nahi|nahin)\s+(?:need|want)?\s*(?:a\s+)?(?:pickup|pick up|drop)\b", low):
            updates["needs_pickup"] = 0
        elif re.search(r"\b(?:need|want|chahiye|chaahiye|arrange)\b", low):
            updates["needs_pickup"] = 1
        if "needs_pickup" in updates: notes.append("needs_pickup")
    return updates, notes


def _function_updates(text: str, guest, updates: dict) -> tuple[dict, list[str]]:
    status = updates.get("rsvp_status")
    if status not in {"coming", "not_coming"}:
        return updates, []
    low = text.lower()
    try:
        functions = json.loads(guest["functions_json"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return updates, []
    matched = [name for name in functions if re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", low)]
    if not matched:
        return updates, []
    previous = {}
    try:
        previous = json.loads(guest["function_responses_json"] or "{}")
    except (KeyError, TypeError, json.JSONDecodeError):
        pass
    previous.update({name: status for name in matched})
    updates.pop("rsvp_status", None)
    updates["function_responses_json"] = json.dumps(previous, ensure_ascii=False)
    return updates, [status, ", ".join(matched)]


def _arrival_time(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
    if not match:
        match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            return f"{hour:02d}:{minute:02d}"
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    meridiem = match.group(3).lower()
    if hour < 1 or hour > 12:
        return None
    hour = hour % 12 + (12 if meridiem == "pm" else 0)
    return f"{hour:02d}:{minute:02d}"


def _answer_fact(question: str, facts: dict[str, str]) -> str | None:
    q = question.lower()
    if re.search(r"\b(?:venue|location|address|kahan|where)\b", q):
        keys = [k for k in facts if any(x in k for x in ("venue", "location", "address"))]
    elif re.search(r"\b(?:when|date|time|kab|kitne baje|schedule|timing)\b", q):
        tokens = re.findall(r"[a-z0-9]+", q)
        keys = [k for k in facts if any(token in k for token in tokens if len(token) > 2) and any(x in k for x in ("date", "time", "schedule", "function", "mehendi", "haldi", "sangeet", "wedding"))]
        if not keys:
            keys = [k for k in facts if any(x in k for x in ("schedule", "date", "time"))]
    else:
        # A function name (for example, "Sangeet" or "wedding") is context,
        # not a request for its date. Only return schedule facts when the
        # question explicitly asks when/what time; otherwise match the
        # requested attribute against non-schedule facts.
        schedule_words = {"date", "time", "schedule", "timing"}
        stop_words = {
            "what", "when", "where", "which", "there", "about", "does",
            "have", "this", "that", "with", "from", "your", "will",
            "can", "could", "would", "please", "tell", "know", "for",
            "the", "and", "are", "is", "any",
        }
        tokens = [
            token for token in re.findall(r"[a-z0-9]+", q)
            if len(token) > 2 and token not in stop_words
        ]
        keys = [
            key for key in facts
            if not any(word in key.lower().split("_") for word in schedule_words)
            and any(token in key.lower().replace("_", " ").split() for token in tokens)
        ]
    keys = list(dict.fromkeys(keys))
    if len(keys) == 1:
        return f"{keys[0].replace('_',' ').title()}: {_format_fact(keys[0], facts[keys[0]])}"
    if len(keys) > 1:
        return "; ".join(f"{key.replace('_',' ').title()}: {_format_fact(key, facts[key])}" for key in keys[:5])
    return None


def _format_fact(key: str, value: str) -> str:
    if "time" in key:
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", value)
        if time_match:
            try:
                return datetime.strptime(f"{int(time_match.group(1)):02d}:{time_match.group(2)}", "%H:%M").strftime("%I:%M %p").lstrip("0")
            except ValueError:
                pass
    match = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})(?:[ T](\d{1,2}:\d{2}))?", value.strip())
    if not match:
        return value
    day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    rendered = day.strftime("%d %B %Y").lstrip("0")
    return rendered + (" at " + match.group(4) if match.group(4) else "")


def _log_message(conn: sqlite3.Connection, session_id: str, role: str, body: str) -> None:
    conn.execute("INSERT INTO guest_messages(session_id,role,body,created_at) VALUES(?,?,?,?)", (session_id, role, body, utc_now()))


def guest_chat(conn: sqlite3.Connection, session_id: str, text: str) -> dict:
    guest = session_guest(conn, session_id)
    if not guest:
        return {"error": "Start by entering the phone number from your invitation."}
    text = re.sub(r"\s+", " ", text).strip()[:1000]
    if not text:
        return {"error": "Type a message first."}
    _log_message(conn, session_id, "guest", text)
    updates, notes = _extract_updates(text, guest)
    updates, function_update = _function_updates(text, guest, updates)
    if function_update:
        notes = [note for note in notes if note not in {"coming", "not_coming"}]
        notes.append("function_rsvp")
    # Resolve day-only dates only against dates the family uploaded.
    has_date = bool(re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}\s*(?:ko|tarikh)\b|\b\d{1,2}(?:st|nd|rd|th)\b|\b\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", text.lower()))
    if has_date and re.search(r"\b(?:arriv|land|train|flight|pahunch|aaunga|aaungi|aunga|aungi|aayenge|aa\s*rahe|aa\s*rahi|coming)\b", text.lower()):
        arrival = _resolve_arrival_date(text.lower(), _facts(conn))
        if arrival:
            updates["arrival_date"] = arrival
            notes.append("arrival_date")
        else:
            notes.append("ambiguous_arrival_date")
        arrival_time = _arrival_time(text)
        if arrival_time:
            updates["arrival_time"] = arrival_time
            notes.append("arrival_time")
    if updates:
        assignments = ",".join(f"{key}=?" for key in updates)
        conn.execute(f"UPDATE wedding_guests SET {assignments},updated_at=? WHERE id=?", (*updates.values(), utc_now(), guest["id"]))
    if "ambiguous_arrival_date" in notes:
        conn.execute("INSERT INTO family_inbox(session_id,guest_id,question,reason,created_at) VALUES(?,?,?,?,?)", (session_id, guest["id"], text, "The arrival day could not be matched to exactly one date in the uploaded family schedule.", utc_now()))
    facts_answer = _answer_fact(text, _facts(conn))
    if notes:
        parts = []
        first_name = guest["name"].split()[0]
        if "coming" in notes: parts.append(f"Thanks, {first_name}! I've marked your group as coming")
        if "not_coming" in notes: parts.append(f"Thanks, {first_name}. I've marked your group as unable to come")
        if function_update:
            parts.append(f"I've marked you as {'coming' if function_update[0] == 'coming' else 'unable to come'} for {function_update[1]}")
        if "count" in notes: parts.append(f"I've noted {updates['party_size']} people in your group")
        if "arrival_mode" in notes:
            arrival = f" by {updates['arrival_mode']}"
            if updates.get("arrival_date"):
                parsed_day = date.fromisoformat(updates["arrival_date"])
                arrival += " on " + parsed_day.strftime("%d %B %Y").lstrip("0")
            if updates.get("arrival_time"):
                arrival += " at " + updates["arrival_time"]
            parts.append("I've noted that you'll arrive" + arrival)
        elif "arrival_date" in notes:
            parsed_day = date.fromisoformat(updates["arrival_date"])
            parts.append("I've noted your arrival for " + parsed_day.strftime("%d %B %Y").lstrip("0"))
        if "needs_room" in notes: parts.append("I've noted that you need a room" if updates["needs_room"] else "I've noted that you don't need a room")
        if "needs_pickup" in notes: parts.append("I've noted that you need a pickup" if updates["needs_pickup"] else "I've noted that you don't need a pickup")
        if "ambiguous_arrival_date" in notes: parts.append("I couldn't match that arrival day to one date in the family's schedule, so I've asked them to confirm it")
        reply = ". ".join(parts) + "."
        if facts_answer:
            reply += " " + facts_answer
    elif re.search(r"\b(?:hi|hello|hey|hii|namaste|vanakkam|thanks|thank you)\b", text.lower()) and len(text.split()) <= 8:
        reply = f"Hi {guest['name'].split()[0]}! What would you like to know about the wedding?"
    elif facts_answer:
        reply = facts_answer
    else:
        reason = "The uploaded family details do not answer this clearly."
        conn.execute("INSERT INTO family_inbox(session_id,guest_id,question,reason,created_at) VALUES(?,?,?,?,?)", (session_id, guest["id"], text, reason, utc_now()))
        reply = "I couldn't confirm that from the family's details, so I've passed your message to them. They'll reply here."
    _log_message(conn, session_id, "desk", reply)
    conn.commit()
    return {"answer": reply, "updated": updates, "escalated": "ambiguous_arrival_date" in notes or bool(not notes and not facts_answer and not re.search(r"\b(?:hi|hello|hey|hii|namaste|vanakkam|thanks|thank you)\b", text.lower()))}


def conversation(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT role,body,created_at FROM guest_messages WHERE session_id=? ORDER BY id", (session_id,))]


def dashboard(conn: sqlite3.Connection) -> dict:
    guests = [dict(row) for row in conn.execute("SELECT * FROM wedding_guests ORDER BY side,name")]
    functions: dict[str, dict[str, int]] = defaultdict(lambda: {"coming": 0, "not_coming": 0, "pending": 0, "headcount": 0})
    for guest in guests:
        responses = json.loads(guest.get("function_responses_json") or "{}")
        guest["function_responses"] = responses
        for function in json.loads(guest["functions_json"]):
            item = functions[function]
            status = responses.get(function, guest["rsvp_status"])
            item[status] += 1
            if status == "coming":
                item["headcount"] += int(guest["party_size"] or guest["invited_count"])
    arrivals = [g for g in guests if g["arrival_date"] or g["arrival_mode"] or g["needs_room"] or g["needs_pickup"]]
    for guest in guests:
        guest["functions"] = json.loads(guest.pop("functions_json"))
    return {
        "guests": guests,
        "guest_count": len(guests),
        "functions": dict(functions),
        "arrivals": arrivals,
        "pickup_list": [g for g in arrivals if g["needs_pickup"]],
        "room_list": [g for g in arrivals if g["needs_room"]],
        "facts": _facts(conn),
    }


def family_inbox(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute("""SELECT i.*,g.name AS guest_name,g.phone AS guest_phone
        FROM family_inbox i JOIN wedding_guests g ON g.id=i.guest_id
        ORDER BY CASE i.status WHEN 'open' THEN 0 ELSE 1 END,i.id DESC""")]


def family_reply(conn: sqlite3.Connection, item_id: int, reply: str) -> bool:
    row = conn.execute("SELECT session_id FROM family_inbox WHERE id=? AND status='open'", (item_id,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE family_inbox SET reply=?,status='replied',replied_at=? WHERE id=?", (reply, utc_now(), item_id))
    _log_message(conn, row["session_id"], "family", reply)
    conn.commit()
    return True


def guest_page() -> str:
    return GUEST_HTML


def family_page() -> str:
    return FAMILY_HTML


GUEST_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Wedding Guest Desk</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f3f0;color:#252a35;font:16px system-ui,sans-serif}.wrap{max-width:760px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.brand{font-weight:800;font-size:21px}.card{background:#fff;border:1px solid #e7e2dc;border-radius:18px;padding:18px;margin:12px 0;box-shadow:0 4px 16px #1b17100a}.muted{color:#707786;font-size:14px}input,textarea,button{font:inherit}input,textarea{width:100%;padding:13px;border:1px solid #d7dce4;border-radius:12px;margin:8px 0}button{border:0;border-radius:12px;background:#594338;color:white;font-weight:700;padding:12px 17px;cursor:pointer}.chat{height:min(58vh,520px);overflow:auto;background:#f4f1ed;border-radius:14px;padding:12px}.bubble{max-width:88%;padding:11px 14px;border-radius:16px;margin:9px 0;white-space:pre-wrap;line-height:1.4}.guest{background:#d9efde;margin-left:auto}.desk,.family{background:white}.family{border-left:4px solid #7853a5}.row{display:flex;gap:8px}.row input{flex:1}.row button{align-self:center;white-space:nowrap}.hidden{display:none}.error{color:#a53030}.link{color:#675044}@media(max-width:520px){.wrap{padding:10px}.card{padding:14px}.row{display:block}.row button{width:100%}.chat{height:55vh}}
</style></head><body><main class='wrap'><div class='top'><div class='brand'>Wedding Guest Desk</div><a class='link' href='/family'>Family</a></div><section class='card'><h2>Welcome to the wedding chat</h2><p class='muted'>Reply to the invitation or ask about the venue and functions. The family desk will help if something isn't in the details.</p><div id='login'><label for='phone'>Phone number from your invitation</label><div class='row'><input id='phone' inputmode='tel' placeholder='Your phone number'><button onclick='join()'>Continue</button></div><p id='loginError' class='error'></p><p class='muted'>This demo matches the number you enter to the uploaded guest list. It does not send an SMS code.</p></div><div id='chatPane' class='hidden'><p id='welcome' class='muted'></p><div id='chat' class='chat'></div><div class='row'><input id='message' placeholder='Type a message…' onkeydown='if(event.key==="Enter")send()'><button onclick='send()'>Send</button></div></div></section><p class='muted'>Only details shared by the family are used to answer wedding questions.</p></main><script>
const esc=s=>String(s||'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));let sid='';async function initialize(){let d=await(await fetch('/api/guest/session')).json();sid=d.session_id;if(d.guest){show(d.guest.name);load()}}function show(name){document.getElementById('login').classList.add('hidden');document.getElementById('chatPane').classList.remove('hidden');document.getElementById('welcome').textContent='You are chatting as '+name+'.'}async function join(){let phone=document.getElementById('phone').value.trim(),r=await fetch('/api/guest/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})}),d=await r.json();if(!d.success){document.getElementById('loginError').textContent=d.message||d.error;return}show(d.guest.name);load()}function bubble(role,text){let el=document.createElement('div');el.className='bubble '+role;el.textContent=text;let c=document.getElementById('chat');c.appendChild(el);c.scrollTop=c.scrollHeight}async function load(){let d=await(await fetch('/api/guest/conversation?session_id='+encodeURIComponent(sid))).json();document.getElementById('chat').innerHTML='';for(const m of d.messages||[])bubble(m.role==='guest'?'guest':m.role==='family'?'family':'desk',m.body)}async function send(){let el=document.getElementById('message'),text=el.value.trim();if(!text)return;el.value='';let r=await fetch('/api/guest/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid,message:text})}),d=await r.json();if(d.error){bubble('desk',d.error);return}await load()}initialize();setInterval(()=>{if(!document.getElementById('chatPane').classList.contains('hidden'))load()},5000);
</script></body></html>"""


FAMILY_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Family Guest Desk</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f8;color:#20293a;font:15px system-ui,sans-serif}.wrap{max-width:1200px;margin:auto;padding:22px}.top{display:flex;align-items:center;justify-content:space-between}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{background:#fff;border:1px solid #e1e5eb;border-radius:16px;padding:18px;margin:12px 0;overflow:auto}.wide{grid-column:1/-1}.muted{color:#707a8b;font-size:13px}.metric{font-size:26px;font-weight:800}.stat{display:inline-block;margin:5px 12px 5px 0}.item{padding:12px 0;border-bottom:1px solid #edf0f4}input,button{font:inherit}input{padding:10px;border:1px solid #ccd3df;border-radius:9px}button{padding:10px 14px;border:0;border-radius:9px;background:#315da8;color:white;font-weight:700;cursor:pointer}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:9px;border-bottom:1px solid #edf0f4;vertical-align:top}.pill{padding:3px 8px;border-radius:20px;background:#edf1f7}.error{color:#a53030}.file{margin:8px 0}@media(max-width:760px){.wrap{padding:12px}.grid{grid-template-columns:1fr}.wide{grid-column:auto}.top{align-items:flex-start}table{font-size:12px}td,th{padding:7px}}
</style></head><body><main class='wrap'><div class='top'><div><h1>Family guest desk</h1><p class='muted'>One wedding · guest replies, arrivals, rooms and pickups</p></div><a href='/'>Guest chat</a></div><section class='card'><h2>Upload the family sheets</h2><p class='muted'>Guest list columns: name, phone, side, functions, how many people. Wedding details CSV: item,value. Data is stored in the app database.</p><form id='guestForm'><label>Guest list CSV <input class='file' id='guests' type='file' accept='.csv' required></label><button>Upload guest list</button></form><p id='guestResult' class='muted'></p><form id='factsForm'><label>Wedding details CSV <input class='file' id='facts' type='file' accept='.csv' required></label><button>Upload details</button></form><p id='factsResult' class='muted'></p></section><div class='grid'><section class='card wide'><h2>Head count by function</h2><div id='functions'>Loading…</div></section><section class='card wide'><h2>Guests and RSVP</h2><div id='guestsTable'>Loading…</div></section><section class='card'><h2>Arrivals</h2><div id='arrivals'>Loading…</div></section><section class='card'><h2>Pickup list</h2><div id='pickups'>Loading…</div></section><section class='card'><h2>Room requests</h2><div id='rooms'>Loading…</div></section><section class='card'><h2>Family inbox</h2><div id='inbox'>Loading…</div></section></div></main><script>
const esc=s=>String(s||'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));async function load(){let d=await(await fetch('/api/family/dashboard')).json();document.getElementById('functions').innerHTML=Object.keys(d.functions||{}).length?Object.entries(d.functions).map(([f,s])=>'<div class="item"><b>'+esc(f)+'</b><div><span class="stat">Coming: '+s.coming+'</span><span class="stat">People: '+s.headcount+'</span><span class="stat">No: '+s.not_coming+'</span><span class="stat">Awaiting: '+s.pending+'</span></div></div>').join(''):'No guests uploaded yet.';document.getElementById('guestsTable').innerHTML=d.guests.length?'<table><thead><tr><th>Name / side</th><th>Functions</th><th>Reply</th><th>People</th><th>Arrival</th><th>Room / pickup</th></tr></thead><tbody>'+d.guests.map(g=>{const replies=g.functions.map(f=>f+': '+((g.function_responses||{})[f]||g.rsvp_status).replace('_',' ')).join(' · ');return '<tr><td>'+esc(g.name)+'<br><span class="muted">'+esc(g.side)+'</span></td><td>'+esc(g.functions.join(', '))+'</td><td>'+esc(replies)+'</td><td>'+esc(g.party_size!==null&&g.party_size!==undefined?g.party_size:(g.rsvp_status==='coming'?g.invited_count:'—'))+'</td><td>'+esc(g.arrival_date||'')+' '+esc(g.arrival_mode||'')+' '+esc(g.arrival_time||'')+'</td><td>'+(g.needs_room?'Room ':'')+(g.needs_pickup?'Pickup':'')+'</td></tr>'}).join('')+'</tbody></table>':'Upload the guest list to begin.';document.getElementById('arrivals').innerHTML=list(d.arrivals,g=>[g.name,g.arrival_date,g.arrival_mode,g.arrival_time].filter(Boolean).join(' · '));document.getElementById('pickups').innerHTML=list(d.pickup_list,g=>[g.name,g.arrival_date,g.arrival_mode,g.arrival_time].filter(Boolean).join(' · '));document.getElementById('rooms').innerHTML=list(d.room_list,g=>g.name+' · '+g.side);let inbox=await(await fetch('/api/family/inbox')).json();document.getElementById('inbox').innerHTML=inbox.items.length?inbox.items.map(i=>'<div class="item"><b>'+esc(i.guest_name)+'</b><div>'+esc(i.question)+'</div><div class="muted">'+esc(i.reason)+'</div>'+(i.reply?'<p>Reply: '+esc(i.reply)+'</p>':'<input id="reply-'+i.id+'" placeholder="Reply to guest"><button onclick="reply('+i.id+')">Send reply</button>')+'</div>').join(''):'No messages waiting for the family.'}function list(items,fmt){return items.length?items.map(g=>'<div class="item">'+esc(fmt(g))+'</div>').join(''):'None yet.'}async function reply(id){let input=document.getElementById('reply-'+id),text=input.value.trim();if(!text)return;await fetch('/api/family/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,reply:text})});load()}async function upload(formId,fileId,resultId,url){document.getElementById(formId).addEventListener('submit',async e=>{e.preventDefault();let f=document.getElementById(fileId).files[0],fd=new FormData();fd.append('file',f);let r=await fetch(url,{method:'POST',body:fd}),d=await r.json();document.getElementById(resultId).textContent=d.error||'Saved '+(d.guests||d.details)+' records to the database.';load()})}upload('guestForm','guests','guestResult','/api/family/upload-guests');upload('factsForm','facts','factsResult','/api/family/upload-facts');load();setInterval(load,7000);
</script></body></html>"""
