"""Standalone grounded wedding-studio desk for the assignment."""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import threading
import base64
import uuid
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Load developer-only settings without overwriting the shell environment.

    Secrets belong in the ignored ``.env.local`` file or the process
    environment; this loader never logs, persists, or commits their values.
    """
    local_env = ROOT / ".env.local"
    if not local_env.is_file():
        return
    try:
        lines = local_env.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or key not in {"OPENROUTER_API_KEYS", "OPENROUTER_API_KEY", "OPENROUTER_MODELS", "OPENROUTER_MODEL", "OPENROUTER_ALLOW_GROUNDED_DATA", "OPENROUTER_TIMEOUT_SECONDS", "OWNER_PASSWORD"}:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_local_env()
CSV_PATH = Path(os.environ.get("ASSIGNMENT_CSV", ROOT / "data" / "studio_bookings.csv"))
SOURCE_DISPLAY_NAME = CSV_PATH.name
DB_PATH = ROOT / "assignment.db"
PORT = int(os.environ.get("ASSIGNMENT_PORT", "8787"))
HOST = os.environ.get("ASSIGNMENT_HOST", "127.0.0.1")
DB_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()
SESSIONS: dict[str, set[str]] = {}
OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_TIMEOUT = max(3, min(int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "20")), 60))
OPENROUTER_CURSOR_LOCK = threading.Lock()
OPENROUTER_CURSOR = 0
INTENT_KINDS = {"date_availability", "package_price", "count", "most_common", "personal_lookup", "unsupported"}
INTENT_FIELDS = {"event_type", "package", "city", "status", "album_stage", "package_price", "advance_paid", "balance_due", ""}


def _openrouter_options() -> list[tuple[str, str]]:
    """Read a local provider pool without ever logging or persisting secrets."""
    keys = [item.strip() for item in os.environ.get("OPENROUTER_API_KEYS", "").replace(";", ",").split(",") if item.strip()]
    if not keys and os.environ.get("OPENROUTER_API_KEY", "").strip():
        keys = [os.environ["OPENROUTER_API_KEY"].strip()]
    models = [item.strip() for item in os.environ.get("OPENROUTER_MODELS", "").replace(";", ",").split(",") if item.strip()]
    if not models and os.environ.get("OPENROUTER_MODEL", "").strip():
        models = [os.environ["OPENROUTER_MODEL"].strip()]
    if not keys or not models:
        return []
    return [(key, models[index % len(models)]) for index, key in enumerate(keys)]


def _openrouter_call(messages: list[dict], max_tokens: int) -> dict | None:
    """Rotate configured key/model pairs and fall back after provider failures."""
    options = _openrouter_options()
    if not options:
        return None
    global OPENROUTER_CURSOR
    with OPENROUTER_CURSOR_LOCK:
        start = OPENROUTER_CURSOR % len(options)
        OPENROUTER_CURSOR = (OPENROUTER_CURSOR + 1) % len(options)
    ordered_options = options[start:] + options[:start]
    for api_key, model in ordered_options:
        request_body = json.dumps({"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": messages}).encode("utf-8")
        request = urllib.request.Request(OPENROUTER_URL, data=request_body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "http://localhost", "X-Title": "Wedding Studio Desk"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=OPENROUTER_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
    return None


def load_bookings() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def replace_uploaded_csv(content: bytes, filename: str) -> dict:
    global CSV_PATH, SOURCE_DISPLAY_NAME
    if not filename.lower().endswith(".csv"):
        raise ValueError("Only CSV files are supported for this assignment.")
    text = content.decode("utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows or not {"booking_id", "event_date"}.issubset(rows[0]):
        raise ValueError("The CSV must include booking_id and event_date columns.")
    destination = ROOT / "data" / "uploaded.csv"
    destination.write_bytes(content)
    CSV_PATH = destination
    SOURCE_DISPLAY_NAME = filename
    return {"filename": filename, "rows": len(rows), "columns": list(rows[0].keys())}


def parse_uploaded_file(handler: BaseHTTPRequestHandler) -> tuple[bytes, str]:
    """Parse the single CSV multipart field without the removed cgi module."""
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length)
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=policy.default).parsebytes(header + body)
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            payload = part.get_payload(decode=True)
            if payload is None:
                raise ValueError("Uploaded file was empty.")
            return payload, filename
    raise ValueError("No CSV file was uploaded.")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS holds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_date TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL DEFAULT '',
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        UNIQUE(event_date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS escalations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        conversation_id TEXT NOT NULL DEFAULT '',
        reply TEXT,
        reply_created_at TEXT
    )""")
    hold_columns = {row[1] for row in conn.execute("PRAGMA table_info(holds)")}
    if "customer_phone" not in hold_columns:
        conn.execute("ALTER TABLE holds ADD COLUMN customer_phone TEXT NOT NULL DEFAULT ''")
    if "status" not in hold_columns:
        conn.execute("ALTER TABLE holds ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    escalation_columns = {row[1] for row in conn.execute("PRAGMA table_info(escalations)")}
    if "conversation_id" not in escalation_columns:
        conn.execute("ALTER TABLE escalations ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''")
    if "reply" not in escalation_columns:
        conn.execute("ALTER TABLE escalations ADD COLUMN reply TEXT")
    if "reply_created_at" not in escalation_columns:
        conn.execute("ALTER TABLE escalations ADD COLUMN reply_created_at TEXT")
    conn.commit()
    return conn


def money(value: str) -> str:
    return f"₹{float(value):,.0f}"


def display_number(field: str, value: float) -> str:
    label = field.lower()
    if any(token in label for token in ("price", "amount", "paid", "due", "cost", "revenue", "fee", "inr", "usd", "eur")):
        return money(str(value))
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def source_note() -> str:
    return f"Source: {SOURCE_DISPLAY_NAME}. This answer uses only the uploaded booking rows."


def _model_intent(question: str, columns: list[str]) -> dict | None:
    """Classify a question into a small validated shape; never compute answers."""
    if not _openrouter_options():
        return None
    schema = {"kind": "date_availability|package_price|count|most_common|personal_lookup|unsupported", "field": "column or empty", "value": "category/status/package or empty", "date": "YYYY-MM-DD or empty", "booking_id": "SS-#### or empty", "name": "customer name from the question or empty"}
    prompt = (
        "Classify this customer question for a booking-sheet assistant. Return JSON only with exactly "
        "kind, field, value, date, booking_id, name. Do not answer, infer facts, or invent values. "
        "Use unsupported for causes, recommendations, forecasts, or policy questions.\n"
        f"VISIBLE COLUMNS: {', '.join(columns)}\nOUTPUT SHAPE: {json.dumps(schema)}\nQUESTION: {question}"
    )
    try:
        body = _openrouter_call([{"role": "system", "content": "You classify only; output strict JSON."}, {"role": "user", "content": prompt}], 160)
        if body is None:
            return None
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return None
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        if not isinstance(parsed, dict) or parsed.get("kind") not in INTENT_KINDS:
            return None
        result = {key: str(parsed.get(key, "") or "").strip() for key in ("kind", "field", "value", "date", "booking_id", "name")}
        if result["field"] and result["field"] not in columns and result["field"] not in INTENT_FIELDS:
            return None
        if result["date"] and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", result["date"]):
            return None
        if result["booking_id"] and not re.fullmatch(r"SS-\d+", result["booking_id"], re.IGNORECASE):
            return None
        return result
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def _intent_query(intent: dict) -> str | None:
    kind, field = intent.get("kind"), intent.get("field", "")
    if kind == "date_availability" and intent.get("date"):
        return f"is {intent['date']} available"
    if kind == "package_price" and intent.get("value"):
        return f"how much is {intent['value']}"
    if kind == "most_common" and field:
        return f"which {field.replace('_', ' ')} has the most bookings"
    if kind == "count" and field and intent.get("value"):
        return f"how many bookings are {intent['value']}"
    if kind == "personal_lookup" and intent.get("booking_id"):
        return f"{field or 'status'} for {intent['booking_id']}"
    return None


def _model_synthesis(question: str, grounded: dict) -> str | None:
    """Use OpenRouter as a grounded communication/decision assistant.

    The provider is deliberately opt-in. A response is accepted only when it
    preserves every factual anchor from the deterministic answer. Any
    missing configuration, network error, malformed response, or changed fact
    falls back to the deterministic answer.
    """
    has_provider = bool(_openrouter_options())
    allow_grounded_data = os.environ.get("OPENROUTER_ALLOW_GROUNDED_DATA", "").lower() in {"1", "true", "yes"}
    if not has_provider or not allow_grounded_data or grounded.get("escalated"):
        return None
    baseline = str(grounded.get("answer", ""))
    prompt = (
        "Act as the customer-facing assistant for a wedding studio. "
        "Turn the VERIFIED ANSWER into a warm, clear WhatsApp-style reply. "
        "You may explain what the verified result means and give a practical next step "
        "only when that next step follows directly from the verified answer. "
        "Never invent availability, causes, policies, forecasts, customer details, "
        "prices, dates, or decisions. Never reveal another customer's information. "
        "If the verified answer asks for owner review, preserve that escalation. "
        "Keep every factual anchor exactly, including booking IDs, dates, numbers, and amounts. "
        "Return only the reply text.\n\n"
        f"QUESTION:\n{question}\n\nVERIFIED ANSWER:\n{baseline}"
    )
    try:
        body = _openrouter_call([{ "role": "system", "content": "You are a grounded editor. Never invent."}, {"role": "user", "content": prompt}], 500)
        if body is None:
            return None
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            return None
        # Preserve factual anchors. This is intentionally conservative.
        anchors = re.findall(r"\bSS-\d+\b|20\d{2}-\d{2}-\d{2}|₹?\d+(?:[.,]\d+)*%?", baseline)
        for token in anchors:
            if token not in content:
                return None
        baseline_lower, content_lower = baseline.lower(), content.lower()
        # Numeric anchors alone cannot protect semantic polarity: a model can
        # repeat a date/amount while reversing a booked/free decision. Keep
        # the deterministic answer whenever availability polarity changes.
        baseline_booked = any(phrase in baseline_lower for phrase in ("already booked", "not available", "unavailable"))
        baseline_free = "looks free" in baseline_lower or ("available for a new hold" in baseline_lower and "not available" not in baseline_lower)
        content_booked = any(phrase in content_lower for phrase in ("booked", "not available", "unavailable"))
        content_free = any(phrase in content_lower for phrase in ("looks free", "available", "hold it", "hold it for"))
        if (baseline_booked and not content_booked) or (baseline_free and not content_free) or (baseline_booked and content_free and not content_booked):
            return None
        # The editor must not turn a public catalogue answer into a claim about
        # the current customer's booking. Ownership/inclusion claims require a
        # verified booking-specific baseline.
        if not re.search(r"\bSS-\d+\b", baseline_lower) and re.search(r"\b(?:your|my) (?:current )?booking\b|\bincluded in your\b", content_lower):
            return None
        if source_note() not in content:
            content = content.rstrip() + "\n\n" + source_note()
        return content.strip()
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def answer_with_optional_synthesis(question: str, rows: list[dict[str, str]], conversation_id: str = "") -> dict:
    # Intent classification can improve natural phrasing, but the deterministic
    # engine still owns all row access, calculations, privacy checks, and facts.
    columns = list(rows[0].keys()) if rows else []
    intent = _model_intent(question, columns)
    routed_question = _intent_query(intent) if intent else None
    # Explicit booking-field questions are already precise. Do not let a
    # probabilistic intent label replace the field named by the customer.
    if re.search(r"\bSS-\d+\b", question, re.IGNORECASE) and re.search(r"\b(?:balance|album|status|booking|package|event|city|location|customer|name|date|when|price|cost)\b", question.lower()):
        routed_question = None
    # Do not let a model invent a year for a day/month question. The local
    # resolver is authoritative and only accepts a unique matching date.
    if intent and intent.get("kind") == "date_availability" and intent.get("date"):
        deterministic_date = _question_date(question, rows)
        explicit_year = re.search(r"\b20\d{2}\b", question.lower())
        if not explicit_year and deterministic_date != intent.get("date"):
            routed_question = None
        elif explicit_year and deterministic_date and deterministic_date != intent.get("date"):
            routed_question = None
    grounded = grounded_answer(routed_question or question, rows, conversation_id)
    if routed_question:
        grounded = {**grounded, "intent_assisted": True}
    synthesized = _model_synthesis(question, grounded)
    if synthesized:
        grounded = {**grounded, "answer": synthesized, "synthesis": "openrouter"}
    else:
        grounded = {**grounded, "synthesis": "deterministic"}
    return grounded


def customer_answer(question: str, rows: list[dict[str, str]], conversation_id: str = "") -> dict:
    """Return a customer-safe answer; aggregate owner analytics stay private."""
    lowered = question.lower()
    # Customers get dates, package prices, and their own booking details. Keep
    # owner analytics and workspace-wide schedule/schema questions off this path.
    owner_analytics = (
        "average" in lowered or "most common" in lowered or "most bookings" in lowered
        or "which city has" in lowered or "compare" in lowered or "versus" in lowered
        or "total" in lowered or "how many" in lowered or "upcoming" in lowered
        or "future" in lowered or "schedule" in lowered or "what data" in lowered
        or "what does this data" in lowered or "what does the data" in lowered
    )
    if not re.search(r"\bSS-\d+\b", question, re.IGNORECASE) and owner_analytics:
        return {"answer": "I can help with a date, package, price, availability, or a specific booking. Owner analytics are available in the owner desk.", "escalated": False, "synthesis": "deterministic"}
    return answer_with_optional_synthesis(question, rows, conversation_id)


def dataset_dashboard(rows: list[dict[str, str]]) -> dict:
    """Return deterministic, source-grounded metrics for the dashboard/report."""
    columns = list(rows[0].keys()) if rows else []
    grouped = {}
    for field in ("event_type", "package", "city", "status", "album_stage"):
        if field in columns:
            grouped[field] = dict(Counter(row.get(field, "") for row in rows if row.get(field)))
    numeric = {}
    numeric_fields = []
    for field in columns:
        values = []
        for row in rows:
            try:
                if row.get(field, "").strip() != "":
                    values.append(float(row[field]))
            except (TypeError, ValueError):
                values = []
                break
        if values:
            numeric_fields.append(field)
            numeric[field] = {"total": round(sum(values), 2), "average": round(sum(values) / len(values), 2), "count": len(values)}
    dated = []
    for row in rows:
        try:
            dated.append(datetime.strptime(row.get("event_date", ""), "%Y-%m-%d").date().isoformat())
        except ValueError:
            continue
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "source": SOURCE_DISPLAY_NAME,
        "rows": len(rows),
        "columns": columns,
        "grouped": grouped,
        "numeric": numeric,
        "numeric_fields": numeric_fields,
        "charts": {field: sorted(values.items(), key=lambda item: (-item[1], item[0]))[:8] for field, values in grouped.items()},
        "timeline": {"past_or_today": sum(value <= today for value in dated), "future": sum(value > today for value in dated)},
        "limitations": ["This view describes the uploaded rows only; it does not establish causes, policy, capacity, or future demand.", "Dates outside the uploaded sheet are unknown."]
    }


def _numeric_values(rows: list[dict[str, str]], field: str) -> list[float]:
    values = []
    for row in rows:
        try:
            if row.get(field, "").strip() != "":
                values.append(float(row[field]))
        except (TypeError, ValueError):
            continue
    return values


def _field_match(question: str, columns: list[str], preferred: tuple[str, ...] = ()) -> str | None:
    q = question.lower().replace("_", " ")
    ordered = list(preferred) + [c for c in columns if c not in preferred]
    for field in ordered:
        label = field.lower().replace("_", " ")
        if field.lower() in question.lower() or label in q:
            return field
    return None


def _date_field(columns: list[str]) -> str | None:
    return next((field for field in columns if "date" in field.lower()), None)


_MONTHS = {name.lower(): index for index, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1
)}
_MONTHS.update({name[:3]: index for name, index in list(_MONTHS.items()) if len(name) > 3})


def _question_date(question: str, rows: list[dict[str, str]]) -> str | None:
    explicit = re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", question.lower())
    if explicit:
        parts = explicit.group(0).split("-")
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\b", question.lower())
    if not match:
        return None
    month = _MONTHS.get(match.group(2))
    if not month:
        return None
    day = int(match.group(1))
    candidates = sorted({row.get("event_date", "") for row in rows if row.get("event_date", "").endswith(f"-{month:02d}-{day:02d}")})
    year = re.search(r"\b(20\d{2})\b", question.lower())
    if year:
        try:
            return datetime(int(year.group(1)), month, day).date().isoformat()
        except ValueError:
            return None
    today = datetime.now(timezone.utc).date()
    upcoming = [candidate for candidate in candidates if candidate >= today.isoformat()]
    if upcoming:
        return upcoming[0]
    # A day/month query with no matching row still needs a concrete upcoming
    # occurrence so availability can be answered instead of escalated.
    try:
        candidate = datetime(today.year, month, day).date()
        if candidate < today:
            candidate = datetime(today.year + 1, month, day).date()
        return candidate.isoformat()
    except ValueError:
        return None


def _display_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y").lstrip("0")
    except (TypeError, ValueError):
        return value


def _active_hold(event_date: str) -> bool:
    if not event_date:
        return False
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM holds WHERE event_date = ? AND status = 'active' AND expires_at > ? LIMIT 1",
        (event_date, datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    conn.close()
    return bool(row)


def _package_match(package: str, question: str) -> bool:
    normalized_package = re.sub(r"[^a-z0-9]+", "", package.lower())
    normalized_question = re.sub(r"[^a-z0-9]+", "", question.lower())
    return bool(normalized_package and normalized_package in normalized_question)


def build_operating_brief(rows: list[dict[str, str]]) -> dict:
    profile = dataset_dashboard(rows)
    grouped, numeric = profile["grouped"], profile["numeric"]
    observations = [f"The uploaded source contains {profile['rows']} booking records and {len(profile['columns'])} visible fields."]
    if grouped.get("event_type"):
        event, count = max(grouped["event_type"].items(), key=lambda item: item[1])
        observations.append(f"The most frequent event type is {event} ({count} records).")
    if grouped.get("city"):
        city, count = max(grouped["city"].items(), key=lambda item: item[1])
        observations.append(f"The most frequent city is {city} ({count} records).")
    if numeric.get("package_price"):
        observations.append(f"Total package price visible in the sheet is {money(str(numeric['package_price']['total']))}; this is a record total, not a forecast.")
    if numeric.get("balance_due"):
        observations.append(f"Visible balance due totals {money(str(numeric['balance_due']['total']))}; payment status should be confirmed with the owner before collection decisions.")
    sop = [
        "1. Ask for the requested event date, event type, package, and city.",
        "2. Check the uploaded sheet before promising availability or price.",
        "3. Use the date-hold control only for a date not already present in the sheet.",
        "4. Treat missing policy, causes, and capacity information as unknown.",
        "5. Escalate questions the sheet cannot support to the studio owner."
    ]
    return {"title": "Studio booking operating brief", "source": SOURCE_DISPLAY_NAME, "summary": "A deterministic operating view generated from the uploaded booking rows.", "observations": observations, "past_present_future": {"past_or_today_records": profile["timeline"]["past_or_today"], "future_records": profile["timeline"]["future"], "future_note": "Future bookings are scheduled rows in this file, not a forecast."}, "sop": sop, "limitations": profile["limitations"]}


def brief_markdown(rows: list[dict[str, str]]) -> str:
    brief = build_operating_brief(rows)
    lines = [f"# {brief['title']}", "", f"Source: `{brief['source']}`", "", brief["summary"], "", "## Observations"]
    lines.extend(f"- {item}" for item in brief["observations"])
    lines.extend(["", "## Past and present", f"- Records dated today or earlier: {brief['past_present_future']['past_or_today_records']}", f"- Future-dated records: {brief['past_present_future']['future_records']}", f"- {brief['past_present_future']['future_note']}", "", "## Ready-to-use operating SOP"])
    lines.extend(brief["sop"])
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in brief["limitations"])
    return "\n".join(lines) + "\n"


def grounded_answer(question: str, rows: list[dict[str, str]], conversation_id: str = "") -> dict:
    q = question.lower().strip()
    columns = list(rows[0].keys()) if rows else []
    if not q:
        return {"answer": "Ask a question about bookings, dates, packages, prices, status, or album stage.", "escalated": False}
    # Keep short social greetings in the conversation instead of escalating
    # them, while requiring the whole message to be a greeting so a message
    # such as "hi, is 20 dec free" still follows normal question routing.
    if re.fullmatch(
        r"(?:hi|hello|hey|hii|namaste|good morning|good afternoon|good evening)"
        r"(?:[\s,!.]*(?:there|how(?: are| r| u)?(?: you| u)?(?: doing| going)?))?"
        r"[!. ]*",
        q,
    ):
        return {"answer": "Hi! How can I help with your date, package, price, or booking?", "escalated": False}
    if any(word in q for word in ("why", "cause", "reason", "should we", "recommend", "forecast", "will bookings", "bookings increase", "bookings decrease", "bookings decline")):
        return escalate(question, "The CSV contains booking records but does not establish causes or business decisions.", conversation_id)
    if ("what does" in q or "represent" in q or "business" in q or "what data" in q or "what's in" in q or "whats in" in q) and not any(term in q for term in ("cost", "price", "package")):
        labels = ", ".join(field.replace("_", " ") for field in columns)
        return {"answer": f"The uploaded sheet contains {len(rows)} records with these visible fields: {labels}. It can support descriptive counts, numeric summaries, comparisons, and date lookups where those fields are populated. It does not by itself establish business policies, causes, capacity, or forecasts.\n\n{source_note()}", "escalated": False}
    booking_match = re.search(r"\bSS-\d+\b", question, re.IGNORECASE)
    booking_id = booking_match.group(0).upper() if booking_match else None
    personal = (booking_id is not None and any(term in q for term in ("balance", "album", "status", "booking", "package", "event", "city", "location", "customer", "name", "date", "when", "price", "cost"))) or any(term in q for term in ("my balance", "my album", "my booking", "my status", "my package", "my event", "my city", "my location", "where is my", "what city am i", "what is my"))
    if personal:
        if not booking_id:
            return {"answer": "Please share your booking ID (for example, SS-2043) so I can look up your booking securely.", "escalated": False}
        row = next((item for item in rows if item.get("booking_id", "").upper() == booking_id), None)
        if not row:
            return {"answer": f"I could not find booking {booking_id} in the current booking sheet. Please check the ID or contact the studio owner.", "escalated": False}
        if "balance" in q or "amount due" in q:
            return {"answer": f"Booking {booking_id} has a balance of {display_number('balance_due', float(row.get('balance_due', 0)))} due.", "escalated": False}
        if "album" in q:
            return {"answer": f"Booking {booking_id}'s album is currently at: {row.get('album_stage', 'not available').replace('_', ' ')}.", "escalated": False}
        if "city" in q or "location" in q:
            return {"answer": f"Booking {booking_id} is listed in {row.get('city', 'an unknown city')}.", "escalated": False}
        if "customer" in q or "name" in q:
            return {"answer": f"The customer name on booking {booking_id} is {row.get('customer_name', 'not available')}.", "escalated": False}
        if "package" in q or "price" in q or "cost" in q:
            package = row.get('package', 'not available')
            package_label = package if package.lower().endswith("package") else f"{package} package"
            price = display_number('package_price', float(row.get('package_price', 0))) if row.get('package_price') else 'not available'
            return {"answer": f"Booking {booking_id} is for the {package_label}, listed at {price}.", "escalated": False}
        if "date" in q or "when" in q:
            return {"answer": f"Booking {booking_id} is scheduled for {row.get('event_date', 'an unknown date')}.", "escalated": False}
        if "status" in q or "booking" in q:
            return {"answer": f"Booking {booking_id} is {row.get('status', 'not available')}. It is scheduled for {row.get('event_date', 'an unknown date')}.", "escalated": False}
        return {"answer": f"Booking {booking_id} is for a {row.get('event_type', 'recorded event')} on {row.get('event_date', 'an unknown date')}.", "escalated": False}
    if booking_id is None and ("package" in q or "service" in q or "photograph" in q or "shoot" in q) and any(term in q for term in ("offer", "have", "available", "listed", "options", "provide", "do you")):
        packages = sorted({row.get("package", "").strip() for row in rows if row.get("package", "").strip()})
        requested = None
        for package in packages:
            tokens = [token for token in re.findall(r"[a-z0-9]+", package.lower()) if token not in {"package", "only", "and"}]
            if _package_match(package, q) or (tokens and any(token in q for token in tokens)):
                requested = package
                break
        if requested:
            return {"answer": f"Yes, {requested} appears in the current booking sheet. Ask me for its recorded price if you would like to check it.", "escalated": False}
        if packages:
            return {"answer": "The current booking sheet lists these packages: " + ", ".join(packages) + ". Ask me about the price of any one.", "escalated": False}

    # Accept natural package-price phrasing such as "What is the Wedding Day
    # price?". The package name is still matched against uploaded rows.
    package_price_question = (
        any(term in q for term in ("how much is", "price of", "price for", "package price", " cost", "cost of", "kitne ka", "kitne ki", "ka rate", "ki rate", "rate of", "rate for"))
        or ("price" in q and any(_package_match(row.get("package", ""), q) for row in rows if row.get("package", "").strip()))
        or ("cost" in q and any(_package_match(row.get("package", ""), q) for row in rows if row.get("package", "").strip()))
        or ("rate" in q and any(_package_match(row.get("package", ""), q) for row in rows if row.get("package", "").strip()))
    )
    if not any(term in q for term in ("compare", "versus", " vs ")) and package_price_question:
        package = next((row.get("package") for row in rows if row.get("package") and _package_match(row.get("package", ""), q)), None)
        if package:
            values = {row.get("package_price") for row in rows if row.get("package", "").lower() == package.lower() and row.get("package_price")}
            if len(values) == 1:
                return {"answer": f"{package} is listed at {display_number('package_price', float(next(iter(values))))} in the current booking sheet.", "escalated": False}
            if values:
                ordered = sorted(float(value) for value in values)
                return {"answer": f"{package} has recorded prices from {display_number('package_price', ordered[0])} to {display_number('package_price', ordered[-1])}. Please confirm the price for your booking with the studio owner.", "escalated": False}
        field = _field_match(q, columns, ("package_price",))
        if field:
            values = _numeric_values(rows, field)
            if values:
                return {"answer": f"The recorded {field.replace('_', ' ')} values range from {display_number(field, min(values))} to {display_number(field, max(values))}. Please specify the package.", "escalated": False}
    if any(phrase in q for phrase in ("most common", "most bookings", "most records", "highest number", "largest", "top")):
        field = _field_match(q, columns, ("event_type", "package", "city", "status", "album_stage"))
        if not field:
            return escalate(question, "The question does not identify a categorical field to group.", conversation_id)
        counts = Counter(row.get(field, "") for row in rows if row.get(field, ""))
        if not counts:
            return escalate(question, f"The uploaded sheet has no usable values for {field}.", conversation_id)
        value, count = max(counts.items(), key=lambda item: item[1])
        return {"answer": f"The most common {field.replace('_', ' ')} is '{value}', with {count} of {len(rows)} records ({count / len(rows):.2%}).\n\n{source_note()}", "escalated": False}
    if re.search(r"\bhow many\b", q):
        categorical = ("event_type", "package", "city", "status", "album_stage")
        for field in categorical:
            if field not in columns:
                continue
            counts = Counter(row.get(field, "") for row in rows if row.get(field, ""))
            for value, count in counts.items():
                if value.lower() in q:
                    label = field.replace("_", " ")
                    return {"answer": f"There are {count} bookings with {label} '{value}' ({count / len(rows):.2%} of {len(rows)} records).\n\n{source_note()}", "escalated": False}
    if "average" in q or "avg" in q or "mean" in q:
        field = _field_match(q, columns, ("package_price", "advance_paid", "balance_due"))
        if not field:
            return escalate(question, "The sheet has several numeric fields; name the field to average.", conversation_id)
        values = _numeric_values(rows, field)
        if not values:
            return escalate(question, f"{field} is not a usable numeric field in the uploaded sheet.", conversation_id)
        avg = sum(values) / len(values)
        return {"answer": f"Average {field.replace('_', ' ')} is {display_number(field, avg)} across {len(values)} records.\n\n{source_note()}", "escalated": False}
    if any(word in q for word in ("total", "sum", "how much")):
        field = _field_match(q, columns, ("package_price", "advance_paid", "balance_due"))
        if field:
            values = _numeric_values(rows, field)
            if values:
                return {"answer": f"The uploaded rows total {display_number(field, sum(values))} for {field.replace('_', ' ')} across {len(values)} records. This is a total of visible rows, not a forecast.\n\n{source_note()}", "escalated": False}
    if "compare" in q or "versus" in q or " vs " in f" {q} ":
        numeric_field = _field_match(q, columns, ("package_price", "advance_paid", "balance_due"))
        group_field = None
        by_match = re.search(r"\b(?:by|per|across)\s+([a-z_ ]+)", q)
        if by_match:
            group_field = _field_match(by_match.group(1).strip(), columns, ("event_type", "package", "city", "status", "album_stage"))
        group_field = group_field or _field_match(q, columns, ("event_type", "package", "city", "status", "album_stage"))
        if numeric_field and group_field and numeric_field != group_field:
            groups = {}
            for row in rows:
                group = row.get(group_field, "")
                if group:
                    try:
                        groups.setdefault(group, []).append(float(row[numeric_field]))
                    except (TypeError, ValueError):
                        pass
            if len(groups) >= 2:
                detail = "; ".join(f"{key}: {display_number(numeric_field, sum(values) / len(values))} average ({len(values)} records)" for key, values in sorted(groups.items()))
                return {"answer": f"For {numeric_field.replace('_', ' ')} by {group_field.replace('_', ' ')}, the visible averages are: {detail}. This describes the uploaded rows and does not establish a cause.\n\n{source_note()}", "escalated": False}
    date_field = _date_field(columns)
    date_target = _question_date(question, rows)
    date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", q)
    if date_match or date_target or "available" in q or "booked" in q or "hold" in q or "can i book" in q or "can we book" in q:
        target = date_target or (date_match.group(0) if date_match else None)
        matches = [row for row in rows if target and date_field and row.get(date_field) == target]
        if target and matches:
            row = matches[0]
            status = row.get("status", "recorded")
            availability = "not available for a new hold"
            details = ", ".join(f"{field.replace('_', ' ')}: {row.get(field, '')}" for field in ("event_type", "package", "city", "status", "album_stage") if row.get(field))
            return {"answer": f"That date is already booked, so it is not available for a new hold. I can't share another customer's booking details. If this is your booking, share your booking ID and I can check your details securely.\n\n{source_note()}", "escalated": False}
        if target:
            if _active_hold(target):
                return {"answer": f"{_display_date(target)} is currently on hold for another customer, so it is not available for a new hold yet.", "escalated": False}
            return {"answer": f"{_display_date(target)} looks free in the current booking sheet. If you'd like it, I can hold it for 24 hours.", "escalated": False, "hold_offer": target}
    if "future" in q or "upcoming" in q or "schedule" in q:
        if date_field:
            today = datetime.now(timezone.utc).date().isoformat()
            upcoming = [row for row in rows if row.get(date_field, "") > today]
            preview = "; ".join(f"{row.get(date_field)} ({row.get('event_type', 'event')}, {row.get('status', 'status')})" for row in sorted(upcoming, key=lambda item: item.get(date_field, ""))[:8])
            return {"answer": f"The sheet contains {len(upcoming)} future-dated rows. Upcoming examples: {preview or 'none visible'}. This is a schedule in the uploaded file, not a demand forecast.\n\n{source_note()}", "escalated": False}
    return escalate(question, "No matching supported fact was found in the uploaded booking sheet.", conversation_id)


def escalate(question: str, reason: str, conversation_id: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with DB_LOCK:
        conn = db()
        existing = conn.execute(
            "SELECT id FROM escalations WHERE question = ? AND conversation_id = ? AND status = 'open' LIMIT 1",
            (question, conversation_id),
        ).fetchone()
        if not existing:
            conn.execute("INSERT INTO escalations(question, reason, created_at, conversation_id) VALUES (?, ?, ?, ?)", (question, reason, now, conversation_id))
        conn.commit(); conn.close()
    return {"answer": "I don't have enough evidence in the booking sheet to answer that safely. I sent this question to the studio owner for review.", "reason": reason, "escalated": True}


def create_hold(event_date: str, customer_name: str, customer_phone: str = "") -> dict:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=24)
    booked = next((row for row in load_bookings() if row.get("event_date") == event_date), None)
    if booked:
        return {"success": False, "error": "That date already appears in the uploaded booking sheet and cannot be held."}
    with DB_LOCK:
        conn = db(); conn.execute("DELETE FROM holds WHERE expires_at <= ? AND status = 'active'", (now.isoformat(),))
        try:
            conn.execute("INSERT INTO holds(event_date, customer_name, customer_phone, expires_at, created_at, status) VALUES (?, ?, ?, ?, ?, 'active')", (event_date, customer_name, customer_phone, expires.isoformat(), now.isoformat()))
            conn.commit(); result = {"success": True, "event_date": event_date, "customer_name": customer_name, "expires_at": expires.isoformat()}
        except sqlite3.IntegrityError:
            conn.rollback(); result = {"success": False, "error": "That date is already held by another customer."}
        conn.close()
    return result


HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Studio Desk</title><style>
body{font-family:Inter,system-ui,sans-serif;background:#f5f7fb;margin:0;color:#172033}.wrap{max-width:980px;margin:0 auto;padding:28px}.brand{font-size:25px;font-weight:800}.muted{color:#68738a}.grid{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-top:20px}.card{background:white;border:1px solid #e1e6ef;border-radius:16px;padding:20px;box-shadow:0 5px 18px #1720330b}textarea,input,button{font:inherit}textarea,input{width:100%;box-sizing:border-box;border:1px solid #cad2df;border-radius:10px;padding:12px;margin:7px 0 12px}button{border:0;border-radius:10px;padding:11px 15px;background:#2463eb;color:#fff;font-weight:700;cursor:pointer}.secondary{background:#e9eef9;color:#24416f}.answer{white-space:pre-wrap;background:#f7f9fc;border-left:4px solid #2463eb;padding:14px;border-radius:8px;margin-top:16px}.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;background:#e8f7ed;color:#176b37}.warn{background:#fff4df;color:#805300}.item{padding:10px 0;border-bottom:1px solid #edf0f5}.small{font-size:13px}.chart-row{display:grid;grid-template-columns:150px 1fr 34px;gap:8px;align-items:center;font-size:13px;margin:6px 0}.bar{display:block;height:10px;border-radius:5px;background:#2463eb;min-width:4px}.chat{height:360px;overflow:auto;background:#e6edf5;border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:10px;margin:12px 0}.bubble{max-width:82%;padding:11px 13px;border-radius:14px;white-space:pre-wrap;line-height:1.45}.bubble.user{align-self:flex-end;background:#d9fdd3;border-bottom-right-radius:4px}.bubble.bot{align-self:flex-start;background:#fff;border-bottom-left-radius:4px;box-shadow:0 1px 2px #17203318}.bubble.flag{border-left:4px solid #d28b00;background:#fff7e6}.empty{margin:auto;color:#68738a;text-align:center}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body><main class='wrap'><div class='brand'>Studio Desk <span class='badge'>Your Business AI</span></div><p class='muted'>A WhatsApp-style customer desk. Answers come only from the uploaded booking sheet.</p><div class='grid'><section class='card'><h2>Customer chat</h2><div id='chat' class='chat'><div class='empty'>Ask about dates, packages, prices, or booking status.</div></div><textarea id='q' rows='2' placeholder='Type a customer question...' onkeydown='if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();ask()}'></textarea><button onclick='ask()'>Send</button></section><aside class='card'><h2>Owner desk</h2><form id='uploadForm'><input id='csv' type='file' accept='.csv,text/csv' required><button type='submit' class='secondary'>Upload booking sheet</button></form><div id='uploadResult' class='small muted'></div><h3>Escalations</h3><p class='muted small'>Questions the sheet could not answer safely.</p><div id='inbox'>Loading…</div></aside></div><section class='card' id='dashboard'><h2>Operating picture</h2><p class='muted small'>Generated from the uploaded sheet; no outside facts are added.</p><div id='dashboardContent'>Loading...</div><p><a href='/api/report.md' target='_blank'>Download grounded operating brief</a></p></section></main><script>
function loadDashboard(){fetch('/api/dashboard').then(r=>r.json()).then(d=>{let sections=Object.entries(d.charts||{}).map(([field,items])=>{let max=Math.max(...items.map(x=>x[1]),1);return '<h3>'+esc(field.replaceAll('_',' '))+'</h3>'+items.map(x=>'<div class="chart-row"><span>'+esc(x[0])+'</span><span class="bar" style="width:'+Math.max(4,Math.round(x[1]/max*100))+'%"></span><b>'+x[1]+'</b></div>').join('')}).join('');let nums=Object.entries(d.numeric||{}).map(([field,n])=>'<div class="item"><b>'+esc(field.replaceAll('_',' '))+'</b><div class="muted small">total '+Number(n.total).toLocaleString('en-IN')+' · average '+Number(n.average).toLocaleString('en-IN')+'</div></div>').join('');document.getElementById('dashboardContent').innerHTML='<p><b>'+d.rows+'</b> records across <b>'+d.columns.length+'</b> fields.</p>'+sections+'<h3>Visible numeric measures</h3>'+ (nums||'<p class="muted">No numeric measures detected.</p>')+'<h3>Schedule</h3><p>'+d.timeline.past_or_today+' past/today · '+d.timeline.future+' future-dated rows</p><p class="muted small">'+d.limitations.join(' ')+'</p>'}).catch(()=>{document.getElementById('dashboardContent').textContent='Dashboard unavailable.'})} function addMessage(role,text,flag){let chat=document.getElementById('chat');let empty=chat.querySelector('.empty');if(empty)empty.remove();let el=document.createElement('div');el.className='bubble '+role+(flag?' flag':'');el.textContent=text;chat.appendChild(el);chat.scrollTop=chat.scrollHeight}
function addInlineHold(date){let chat=document.getElementById('chat');let wrap=document.createElement('div');wrap.className='inline-hold';wrap.innerHTML='<b>Want me to hold '+esc(date)+' for 24 hours?</b><input class="inline-name" placeholder="Your name"><input class="inline-phone" placeholder="Phone number"><button class="secondary">Request hold</button><div class="inline-result small"></div>';let button=wrap.querySelector('button');button.onclick=async()=>{let name=wrap.querySelector('.inline-name').value.trim(),phone=wrap.querySelector('.inline-phone').value.trim(),result=wrap.querySelector('.inline-result');let r=await fetch('/api/hold',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_date:date,customer_name:name,customer_phone:phone})});let d=await r.json();result.textContent=d.success?'Your date is held for 24 hours.':d.error;result.className='inline-result small '+(d.success?'':'warn');button.disabled=true};chat.appendChild(wrap);chat.scrollTop=chat.scrollHeight} let conversationId='';let lastReplyId=0;fetch('/api/session').then(r=>r.json()).then(d=>conversationId=d.conversation_id);async function loadReply(){if(!conversationId)return;let d=await (await fetch('/api/conversation?conversation_id='+encodeURIComponent(conversationId))).json();if(d.id&&d.id!==lastReplyId){lastReplyId=d.id;addMessage('bot','Owner: '+d.reply,false)}} async function ask(){let input=document.getElementById('q');let q=input.value.trim();if(!q)return;if(!conversationId)conversationId=(await (await fetch('/api/session')).json()).conversation_id;addMessage('user',q);input.value='';let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,conversation_id:conversationId})});let d=await r.json();addMessage('bot',d.answer,Boolean(d.escalated));if(d.hold_offer)addInlineHold(d.hold_offer);if(d.escalated)addMessage('bot','Owner review requested.');loadReply()} async function loadInbox(){let d=await (await fetch('/api/owner/inbox')).json();document.getElementById('inbox').innerHTML=d.items.length?d.items.map(x=>'<div class="item"><b>'+esc(x.question)+'</b><div class="muted small">'+esc(x.reason)+'</div></div>').join(''):'<p class="muted">No escalations yet.</p>'} document.getElementById('uploadForm').addEventListener('submit',async e=>{e.preventDefault();let f=document.getElementById('csv').files[0];let fd=new FormData();fd.append('file',f);let r=await fetch('/api/upload',{method:'POST',body:fd});let d=await r.json();document.getElementById('uploadResult').textContent=d.error||('Loaded '+d.rows+' rows from '+d.filename);loadDashboard()}); function esc(s){return String(s||'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]))} loadInbox(); loadDashboard(); setInterval(loadReply,3000);
</script></body></html>"""


def customer_page() -> str:
    """Customer view; owner tools are hidden here and protected at the API."""
    page = HTML.replace("<aside class='card'>", "<aside class='card' style='display:none'>", 1)
    page = page.replace("<section class='card' id='dashboard'>", "<section class='card' id='dashboard' style='display:none'>", 1)
    marker = "<p class='muted'>A WhatsApp-style customer desk. Answers come only from the uploaded booking sheet.</p>"
    return page.replace(marker, marker + "<p class='small'><a href='/'>Customer chat</a> · <a href='/owner'>Owner desk</a></p>", 1)


OWNER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Studio Desk Owner</title><style>
body{font-family:Inter,system-ui,sans-serif;background:#f5f7fb;margin:0;color:#172033}.wrap{max-width:900px;margin:0 auto;padding:28px}.card{background:#fff;border:1px solid #e1e6ef;border-radius:16px;padding:20px;margin:16px 0}.muted{color:#68738a}.item{padding:12px 0;border-bottom:1px solid #edf0f5}input,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #cad2df}button{background:#2463eb;color:#fff;border:0;font-weight:700;cursor:pointer}.reply{display:flex;gap:8px;margin-top:8px}.reply input{flex:1}.small{font-size:13px}
</style></head><body><main class='wrap'><p><a href='/'>Customer chat</a> · <a href='/owner'>Owner desk</a></p><h1>Studio Desk owner</h1><div class='card'><h2>Operating picture</h2><p class='muted small'>Owner-only descriptive view of the uploaded booking sheet.</p><div id='dashboardContent'>Loading...</div><p><a href='/api/report.md' target='_blank'>Download operating brief</a></p></div><div class='card'><h2>Upload booking sheet</h2><form id='uploadForm'><input id='csv' type='file' accept='.csv,text/csv' required><button>Upload</button></form><p id='uploadResult' class='muted small'></p></div><div class='card'><h2>Customer escalations</h2><div id='inbox'>Loading…</div></div><div class='card'><h2>Active holds</h2><div id='holds'>Loading…</div></div></main><script>
const esc=s=>String(s||'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));
async function loadDashboard(){let response=await fetch('/api/dashboard');if(!response.ok)return;let d=await response.json();let sections=Object.entries(d.charts||{}).map(([field,items])=>'<h3>'+esc(field.replaceAll('_',' '))+'</h3>'+items.map(x=>'<div>'+esc(x[0])+' · <b>'+x[1]+'</b></div>').join('')).join('');let nums=Object.entries(d.numeric||{}).map(([field,n])=>'<div><b>'+esc(field.replaceAll('_',' '))+'</b>: total '+Number(n.total).toLocaleString('en-IN')+' · average '+Number(n.average).toLocaleString('en-IN')+'</div>').join('');document.getElementById('dashboardContent').innerHTML='<p><b>'+d.rows+'</b> records across <b>'+d.columns.length+'</b> fields.</p>'+sections+'<h3>Numeric measures</h3>'+ (nums||'<p class="muted">No numeric measures detected.</p>')+'<h3>Schedule</h3><p>'+d.timeline.past_or_today+' past/today · '+d.timeline.future+' future-dated rows</p>'}
async function load(){loadDashboard();let inbox=await (await fetch('/api/owner/inbox')).json();document.getElementById('inbox').innerHTML=inbox.items.length?inbox.items.map(x=>'<div class="item"><b>'+esc(x.question)+'</b><div class="muted small">'+esc(x.reason)+'</div><div class="reply"><input id="reply-'+x.id+'" placeholder="Reply to customer"><button onclick="reply(this.dataset.conversation,this.dataset.id)" data-conversation="'+esc(x.conversation_id)+'" data-id="'+x.id+'">Send reply</button></div>'+(x.reply?'<div class="small">Sent: '+esc(x.reply)+'</div>':'')+'</div>').join(''):'<p class="muted">No open escalations.</p>';let holds=await (await fetch('/api/owner/holds')).json();document.getElementById('holds').innerHTML=holds.items.length?holds.items.map(x=>'<div class="item"><b>'+esc(x.event_date)+'</b> · '+esc(x.customer_name)+' · '+esc(x.customer_phone)+'<div class="muted small">expires '+esc(x.expires_at)+' · '+esc(x.status)+'</div><button onclick="holdAction('+x.id+',&quot;confirmed&quot;)">Confirm</button> <button onclick="holdAction('+x.id+',&quot;released&quot;)">Release</button></div>').join(''):'<p class="muted">No active holds.</p>'}
async function reply(conversationId,id){let text=document.getElementById('reply-'+id).value.trim();if(!text)return;await fetch('/api/owner/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:conversationId,reply:text})});load()}
async function holdAction(id,status){await fetch('/api/owner/hold-action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,status:status})});load()}
document.getElementById('uploadForm').addEventListener('submit',async e=>{e.preventDefault();let f=document.getElementById('csv').files[0],fd=new FormData();fd.append('file',f);let d=await (await fetch('/api/upload',{method:'POST',body:fd})).json();document.getElementById('uploadResult').textContent=d.error||('Loaded '+d.rows+' rows from '+d.filename)});load();setInterval(load,5000);
</script></body></html>"""


def owner_authorized(handler: BaseHTTPRequestHandler) -> bool:
    expected = os.environ.get("OWNER_PASSWORD", "")
    header = handler.headers.get("Authorization", "")
    if not expected or not header.startswith("Basic "):
        return False
    try:
        username, password = base64.b64decode(header[6:]).decode("utf-8").split(":", 1)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return False
    return username == "owner" and password == expected


def require_owner(handler: BaseHTTPRequestHandler) -> bool:
    # Local assignment users should not get a browser Basic Auth prompt. Keep
    # protection for non-loopback callers so a hosted/public deployment is not
    # silently exposed.
    if handler.client_address and handler.client_address[0] in {"127.0.0.1", "::1", "localhost"}:
        return True
    if owner_authorized(handler):
        return True
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", 'Basic realm="Studio Desk owner"')
    handler.end_headers()
    return False


def latest_reply(conversation_id: str) -> dict:
    if not conversation_id:
        return {}
    conn = db()
    row = conn.execute("SELECT id, reply, reply_created_at FROM escalations WHERE conversation_id = ? AND reply IS NOT NULL ORDER BY id DESC LIMIT 1", (conversation_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def browser_session(handler: BaseHTTPRequestHandler) -> tuple[str, bool]:
    cookies = {}
    for item in handler.headers.get("Cookie", "").split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            cookies[key] = value
    session_id = cookies.get("desk_session", "")
    created = False
    if not re.fullmatch(r"[0-9a-f-]{36}", session_id):
        session_id = str(uuid.uuid4())
        created = True
    with SESSION_LOCK:
        SESSIONS.setdefault(session_id, set())
    return session_id, created


def session_conversation(session_id: str) -> str:
    with SESSION_LOCK:
        values = SESSIONS.setdefault(session_id, set())
        if not values:
            values.add(str(uuid.uuid4()))
        return sorted(values)[0]


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: dict, status=200):
        body = json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def send_text(self, body: str, content_type='text/plain; charset=utf-8', status=200):
        encoded = body.encode('utf-8'); self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health': return self.send_json({'status':'ok','rows':len(load_bookings())})
        if path == '/api/dashboard':
            if not require_owner(self): return
            return self.send_json(dataset_dashboard(load_bookings()))
        if path == '/api/report':
            if not require_owner(self): return
            return self.send_json(build_operating_brief(load_bookings()))
        if path == '/api/report.md':
            if not require_owner(self): return
            return self.send_text(brief_markdown(load_bookings()), 'text/markdown; charset=utf-8')
        if path == '/api/owner/inbox':
            if not require_owner(self): return
            conn = db()
            items = [
                dict(row)
                for row in conn.execute(
                    """SELECT e.*
                       FROM escalations e
                       WHERE e.status = 'open'
                         AND e.id = (
                             SELECT MAX(e2.id)
                             FROM escalations e2
                             WHERE e2.status = 'open'
                               AND e2.question = e.question
                               AND e2.conversation_id = e.conversation_id
                         )
                       ORDER BY e.id DESC"""
                )
            ]
            conn.close()
            return self.send_json({'items': items})
        if path == '/api/owner/holds':
            if not require_owner(self): return
            conn=db(); items=[dict(x) for x in conn.execute("SELECT * FROM holds WHERE expires_at > ? AND status = 'active' ORDER BY event_date", (datetime.now(timezone.utc).isoformat(),))]; conn.close(); return self.send_json({'items':items})
        if path == '/api/session':
            session_id, _ = browser_session(self)
            return self.send_json({'conversation_id': session_conversation(session_id)})
        if path == '/api/conversation':
            query = parse_qs(urlparse(self.path).query)
            session_id, _ = browser_session(self)
            conversation_id = str(query.get('conversation_id', [''])[0])[:100]
            with SESSION_LOCK:
                allowed = conversation_id in SESSIONS.get(session_id, set())
            if not allowed:
                return self.send_json({'error': 'Conversation not found.'}, 404)
            return self.send_json(latest_reply(conversation_id))
        if path == '/owner':
            if not require_owner(self): return
            return self.send_text(OWNER_HTML, 'text/html; charset=utf-8')
        if path == '/':
            body=customer_page().encode(); session_id, created = browser_session(self); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8');
            if created: self.send_header('Set-Cookie', f'desk_session={session_id}; HttpOnly; SameSite=Lax')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_error(404)
    def do_POST(self):
        path=urlparse(self.path).path
        if path == '/api/upload':
            if not require_owner(self): return
            try:
                content, filename = parse_uploaded_file(self)
                return self.send_json(replace_uploaded_csv(content, filename))
            except (KeyError, ValueError, UnicodeDecodeError) as exc:
                return self.send_json({'error': str(exc)}, 400)
        length=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(length) or '{}')
        if path == '/api/chat':
            session_id, _ = browser_session(self)
            conversation_id = str(data.get('conversation_id', '')).strip()[:100] or session_conversation(session_id)
            with SESSION_LOCK:
                allowed = conversation_id in SESSIONS.get(session_id, set())
            if not allowed:
                return self.send_json({'error': 'A customer session is required.'}, 400)
            result = customer_answer(str(data.get('question', '')), load_bookings(), conversation_id)
            # Provenance is retained internally and in owner reports, but customer replies stay conversational.
            result['answer'] = re.sub(r"\n\nSource:.*$", "", result.get('answer', ''), flags=re.DOTALL).strip()
            return self.send_json(result)
        if path == '/api/owner/reply':
            if not require_owner(self): return
            conversation_id = str(data.get('conversation_id', '')).strip()[:100]
            reply = str(data.get('reply', '')).strip()[:2000]
            if not conversation_id or not reply:
                return self.send_json({'error': 'Conversation and reply are required.'}, 400)
            now = datetime.now(timezone.utc).isoformat()
            with DB_LOCK:
                conn = db(); cur = conn.execute('UPDATE escalations SET reply = ?, reply_created_at = ?, status = "replied" WHERE conversation_id = ? AND status = "open"', (reply, now, conversation_id)); conn.commit(); conn.close()
            return self.send_json({'success': cur.rowcount > 0})
        if path == '/api/owner/hold-action':
            if not require_owner(self): return
            hold_id = int(data.get('id', 0) or 0)
            status = str(data.get('status', ''))
            if status not in {'confirmed', 'released'}:
                return self.send_json({'error': 'Status must be confirmed or released.'}, 400)
            with DB_LOCK:
                conn = db(); cur = conn.execute('UPDATE holds SET status = ? WHERE id = ? AND status = "active"', (status, hold_id)); conn.commit(); conn.close()
            return self.send_json({'success': cur.rowcount > 0})
        if path == '/api/hold':
            if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', str(data.get('event_date',''))) or not str(data.get('customer_name','')).strip() or not str(data.get('customer_phone','')).strip(): return self.send_json({'success':False,'error':'Enter a valid date, customer name, and phone number.'},400)
            return self.send_json(create_hold(data['event_date'], data['customer_name'], data['customer_phone']))
        self.send_error(404)
    def log_message(self, *_): pass


if __name__ == '__main__':
    (ROOT / 'data').mkdir(exist_ok=True)
    if not CSV_PATH.exists(): raise SystemExit(f'CSV not found: {CSV_PATH}')
    db().close()
    print(f'Studio Desk using {CSV_PATH.name} ({len(load_bookings())} rows)')
    print(f'Open http://127.0.0.1:{PORT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
