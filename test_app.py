import sys
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app
import database


class AssignmentDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.tmp.name) / "desk.db"
        app.CSV_PATH = Path(__file__).parent / "data" / "studio_bookings.csv"
        app.SOURCE_DISPLAY_NAME = app.CSV_PATH.name
        self.provider_env = mock.patch.dict(app.os.environ, {
            "OPENROUTER_API_KEYS": "", "OPENROUTER_API_KEY": "",
            "OPENROUTER_MODELS": "", "OPENROUTER_MODEL": "",
            # Tests must use the temporary SQLite database above. app.db()
            # prefers these production connection variables over DB_PATH.
            "SUPABASE_DB_URL": "", "DATABASE_URL": "",
        })
        self.provider_env.start()

    def tearDown(self):
        self.provider_env.stop()
        self.tmp.cleanup()

    def test_supabase_adapter_translates_placeholders_and_sqlite_transaction_keyword(self):
        self.assertEqual(database.PostgresCompatConnection._sql("SELECT * FROM people WHERE phone=?"), "SELECT * FROM people WHERE phone=%s")
        self.assertEqual(database.PostgresCompatConnection._sql("BEGIN IMMEDIATE"), "BEGIN")
        self.assertEqual(database.PostgresCompatConnection._sql('UPDATE holds SET status = "active" WHERE id = ?'), "UPDATE holds SET status = 'active' WHERE id = %s")

    def test_answers_from_uploaded_rows(self):
        result = app.grounded_answer("Which event type is most common?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("wedding", result["answer"])
        self.assertIn("7 of 12", result["answer"])

    def test_city_most_bookings_uses_grouped_counts(self):
        result = app.grounded_answer("Which city has the most bookings?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("Delhi", result["answer"])
        self.assertIn("7 of 12", result["answer"])

    def test_confirmed_booking_count_uses_status_values(self):
        result = app.grounded_answer("How many bookings are confirmed?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("6 bookings", result["answer"])
        self.assertIn("status", result["answer"])

    def test_customer_language_examples_are_routed_without_leaking_other_rows(self):
        rows = app.load_bookings()
        cases = [
            ("is 14 december booked", "not available"),
            ("how much is full package", "₹1,85,000"),
            ("my balance for SS-2043", "80,000"),
            ("where is my album SS-2043", "not started"),
            ("what is the status of SS-2043", "tentative"),
            ("which city has the most bookings", "Delhi"),
            ("how many bookings are confirmed", "6 bookings"),
        ]
        for question, expected in cases:
            with self.subTest(question=question):
                result = app.grounded_answer(question, rows)
                self.assertFalse(result["escalated"])
                self.assertIn(expected, result["answer"])
        personal = app.grounded_answer("what is my balance?", rows)
        self.assertIn("booking ID", personal["answer"])

    def test_customer_chat_does_not_expose_owner_aggregates(self):
        result = app.customer_answer("What is the total balance due?", app.load_bookings())
        self.assertIn("specific booking", result["answer"])

    def test_customer_chat_keeps_owner_analytics_private(self):
        rows = app.load_bookings()
        for question in ("How many bookings are confirmed?", "Which city has the most bookings?", "Which event type is most common?", "What upcoming bookings are there?", "What data is in the sheet?"):
            with self.subTest(question=question):
                self.assertIn("Owner analytics", app.customer_answer(question, rows)["answer"])
        self.assertIn("6 bookings", app.grounded_answer("How many bookings are confirmed?", rows)["answer"])

    def test_customer_questions_cover_twenty_realistic_phrasings(self):
        rows = app.load_bookings()
        cases = [
            ("is 14 december booked", "not available"),
            ("is 2026-11-22 available", "not available"),
            ("can I book 20 December 2026", "looks free"),
            ("hold 20 December 2026", "looks free"),
            ("how much is full package", "₹1,85,000"),
            ("what does wedding day cost", "₹1,20,000"),
            ("what is my balance for SS-2043", "80,000"),
            ("where is my album SS-2043", "not started"),
            ("what is the status of SS-2043", "tentative"),
            ("what city is SS-2043 in", "Delhi"),
            ("what package do I have SS-2043", "Wedding Day"),
            ("what date is SS-2048", "17 january 2027"),
            ("what is the event for SS-2031", "wedding"),
            ("what is the customer name for SS-2043", "Ananya Gupta"),
            ("which city has the most bookings", "Owner analytics"),
            ("how many bookings are confirmed", "Owner analytics"),
            ("what is my balance", "Please share your booking ID"),
            ("will bookings increase next month", "studio owner to review"),
            ("can I get a refund", "studio owner to review"),
            ("what services do you offer", "Full Package"),
        ]
        for question, expected in cases:
            with self.subTest(question=question):
                result = app.customer_answer(question, rows)
                self.assertIn(expected.lower(), result["answer"].lower())

    def test_personal_booking_fields_are_scoped_to_booking_id(self):
        rows = app.load_bookings()
        self.assertIn("Delhi", app.customer_answer("what city is SS-2043 in", rows)["answer"])
        self.assertIn("Wedding Day", app.customer_answer("what package do I have SS-2043", rows)["answer"])
        self.assertIn("booking ID", app.customer_answer("what city am I in", rows)["answer"])

    def test_owner_reply_is_available_to_same_customer_conversation(self):
        conversation_id = "demo-conversation"
        app.escalate("Can you make an exception?", "The sheet cannot establish exceptions.", conversation_id)
        now = "2026-01-01T00:00:00+00:00"
        conn = app.db()
        conn.execute("UPDATE escalations SET reply = ?, reply_created_at = ?, status = 'replied' WHERE conversation_id = ?", ("I will review this with you.", now, conversation_id))
        conn.commit(); conn.close()
        reply = app.latest_reply(conversation_id)
        self.assertEqual(reply["reply"], "I will review this with you.")
        self.assertEqual(reply["reply_created_at"], now)

    def test_escalations_keep_conversation_and_reply_fields(self):
        connection = app.db()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(escalations)")}
        connection.close()
        self.assertTrue({"conversation_id", "reply", "reply_created_at"}.issubset(columns))

    def test_repeated_open_escalation_is_idempotent(self):
        app.escalate("Why did bookings decline?", "The sheet cannot establish causes.", "same-session")
        app.escalate("Why did bookings decline?", "The sheet cannot establish causes.", "same-session")
        connection = app.db()
        count = connection.execute(
            "SELECT COUNT(*) FROM escalations WHERE question = ? AND conversation_id = ? AND status = 'open'",
            ("Why did bookings decline?", "same-session"),
        ).fetchone()[0]
        connection.close()
        self.assertEqual(count, 1)

    def test_unsupported_customer_question_escalates_without_column_dump(self):
        result = app.customer_answer("Tell me about the album workflow", app.load_bookings())
        self.assertTrue(result["escalated"])
        self.assertNotIn("Available columns", result["answer"])
        self.assertIn("owner", result["answer"])

    def test_unsupported_cause_escalates(self):
        result = app.grounded_answer("Why are wedding packages expensive?", app.load_bookings())
        self.assertTrue(result["escalated"])
        self.assertIn("owner", result["answer"])

    def test_date_hold_is_unique(self):
        first = app.create_hold("2028-11-22", "First customer")
        second = app.create_hold("2028-11-22", "Second customer")
        self.assertTrue(first["success"])
        self.assertFalse(second["success"])

    def test_hold_has_owner_lifecycle_status(self):
        result = app.create_hold("2028-12-01", "First customer", "+911234567890")
        self.assertTrue(result["success"])
        conn = app.db()
        row = conn.execute("SELECT status, customer_phone FROM holds WHERE event_date = ?", ("2028-12-01",)).fetchone()
        conn.close()
        self.assertEqual(row[0], "active")
        self.assertEqual(row[1], "+911234567890")

    def test_existing_booking_cannot_be_held(self):
        result = app.create_hold("2026-11-22", "Another customer")
        self.assertFalse(result["success"])
        self.assertIn("uploaded booking sheet", result["error"])

    def test_booked_date_answer_is_explicitly_unavailable(self):
        result = app.grounded_answer("Is 2026-11-22 available?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("not available", result["answer"])
        self.assertNotIn("package:", result["answer"])
        self.assertIn("can't share", result["answer"])

    def test_dashboard_is_grounded_in_uploaded_rows(self):
        dashboard = app.dataset_dashboard(app.load_bookings())
        self.assertEqual(dashboard["rows"], 12)
        self.assertEqual(dashboard["grouped"]["event_type"]["wedding"], 7)
        self.assertEqual(dashboard["numeric"]["package_price"]["count"], 12)

    def test_operating_brief_contains_sop_and_limits(self):
        report = app.build_operating_brief(app.load_bookings())
        self.assertIn("SOP", app.brief_markdown(app.load_bookings()))
        self.assertTrue(report["limitations"])
        self.assertIn("not a forecast", report["past_present_future"]["future_note"])

    def test_dashboard_exposes_generic_chart_and_numeric_metadata(self):
        dashboard = app.dataset_dashboard(app.load_bookings())
        self.assertIn("city", dashboard["charts"])
        self.assertIn("package_price", dashboard["numeric_fields"])

    def test_customer_surface_hides_owner_tools_and_internal_mode_labels(self):
        customer = app.customer_page()
        self.assertIn("href='/owner'", customer)
        self.assertIn("style='display:none'", customer)
        self.assertNotIn('OpenRouter grounded rewrite', customer)
        self.assertNotIn('Deterministic grounded answer', customer)

    def test_owner_page_contains_owner_dashboard(self):
        self.assertIn("id='dashboardContent'", app.OWNER_HTML)
        self.assertIn("/api/dashboard", app.OWNER_HTML)
        self.assertIn("id='ownerQuestion'", app.OWNER_HTML)
        self.assertIn("/api/owner/ask", app.OWNER_HTML)

    def test_customer_and_owner_pages_link_to_each_other(self):
        customer = app.customer_page()
        self.assertIn("href='/owner'", customer)
        self.assertIn("href='/'", customer)
        self.assertIn("href='/owner'", app.OWNER_HTML)

    def test_package_catalogue_matches_requested_service_terms(self):
        rows = app.load_bookings()
        maternity = app.customer_answer("Do you have maternity photography?", rows)
        self.assertFalse(maternity["escalated"])
        self.assertIn("Maternity Shoot", maternity["answer"])
        booking = app.customer_answer("What is the price for SS-2031?", rows)
        self.assertIn("Full Package,", booking["answer"])
        self.assertNotIn("Full Package package", booking["answer"])

    def test_package_catalogue_answers_customer_availability(self):
        rows = app.load_bookings()
        listed = app.customer_answer("What packages are available?", rows)
        self.assertFalse(listed["escalated"])
        self.assertIn("Full Package", listed["answer"])
        reception = app.customer_answer("Do you have a reception package?", rows)
        self.assertFalse(reception["escalated"])
        self.assertIn("Reception Only", reception["answer"])
        haldi = app.customer_answer("Do you provide a haldi shoot?", rows)
        self.assertFalse(haldi["escalated"])
        self.assertIn("Haldi + Mehndi", haldi["answer"])

    def test_customer_schema_question_stays_on_owner_desk(self):
        result = app.customer_answer("What data is in the sheet?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("Owner analytics", result["answer"])

    def test_package_price_reply_is_natural(self):
        result = app.grounded_answer("How much is the Full Package?", app.load_bookings())
        self.assertIn("Full Package has recorded prices", result["answer"])
        self.assertNotIn("Full Package package", result["answer"])
        wedding_day = app.grounded_answer("What is the price for Wedding Day?", app.load_bookings())
        self.assertFalse(wedding_day["escalated"])
        self.assertIn("₹1,20,000", wedding_day["answer"])
        natural = app.grounded_answer("What is the Wedding Day price?", app.load_bookings())
        self.assertFalse(natural["escalated"])
        self.assertIn("₹1,20,000", natural["answer"])

    def test_generic_numeric_total_and_future_schedule_questions(self):
        total = app.grounded_answer("What is the total advance paid?", app.load_bookings())
        self.assertFalse(total["escalated"])
        self.assertIn("advance paid", total["answer"])
        future = app.grounded_answer("What upcoming bookings are in the schedule?", app.load_bookings())
        self.assertFalse(future["escalated"])
        self.assertIn("future-dated rows", future["answer"])

    def test_comparison_uses_the_requested_group_dimension(self):
        result = app.grounded_answer("Compare package price by city", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("by city", result["answer"])

    def test_optional_synthesis_is_disabled_without_provider_configuration(self):
        with mock.patch.dict(app.os.environ, {}, clear=True):
            result = app.answer_with_optional_synthesis("Which event type is most common?", app.load_bookings())
        self.assertEqual(result["synthesis"], "deterministic")
        self.assertIn("7 of 12", result["answer"])

    def test_local_env_loader_reads_ignored_provider_pool_without_overwriting_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            local_root = Path(directory)
            (local_root / ".env.local").write_text(
                "OPENROUTER_API_KEYS=key-a,key-b\nOPENROUTER_MODELS=model-a,model-b\n",
                encoding="utf-8",
            )
            with mock.patch.object(app, "ROOT", local_root), mock.patch.dict(app.os.environ, {}, clear=True):
                app._load_local_env()
                self.assertEqual(app.os.environ["OPENROUTER_API_KEYS"], "key-a,key-b")
                self.assertEqual(app.os.environ["OPENROUTER_MODELS"], "model-a,model-b")

    def test_synthesis_must_preserve_verified_numeric_anchors(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'{"choices":[{"message":{"content":"Wedding is most common."}}]}'
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model", "OPENROUTER_ALLOW_GROUNDED_DATA": "1"}, clear=True):
            with mock.patch("app.urllib.request.urlopen", return_value=Response()):
                result = app.answer_with_optional_synthesis("Which event type is most common?", app.load_bookings())
        self.assertEqual(result["synthesis"], "deterministic")
        self.assertIn("7 of 12", result["answer"])

    def test_synthesis_accepts_grounded_rewrite_and_appends_source(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'{"choices":[{"message":{"content":"The most common event type is wedding, with 7 of 12 records (58.33%)."}}]}'
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model", "OPENROUTER_ALLOW_GROUNDED_DATA": "1"}, clear=True):
            with mock.patch("app.urllib.request.urlopen", return_value=Response()):
                result = app.answer_with_optional_synthesis("Which event type is most common?", app.load_bookings())
        self.assertEqual(result["synthesis"], "openrouter")
        self.assertIn("Source: studio_bookings.csv", result["answer"])

    def test_synthesis_rejects_availability_polarity_flip(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'{"choices":[{"message":{"content":"December 14 is currently available for a new booking."}}]}'
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model", "OPENROUTER_ALLOW_GROUNDED_DATA": "1"}, clear=True):
            with mock.patch("app.urllib.request.urlopen", return_value=Response()):
                result = app.answer_with_optional_synthesis("is 14 december booked", app.load_bookings())
        self.assertEqual(result["synthesis"], "deterministic")
        self.assertIn("already booked", result["answer"])

    def test_model_cannot_invent_year_for_day_month_question(self):
        intent = {"kind": "date_availability", "field": "", "value": "", "date": "2023-12-14", "booking_id": "", "name": ""}
        with mock.patch("app._model_intent", return_value=intent), mock.patch("app._model_synthesis", return_value=None):
            result = app.answer_with_optional_synthesis("is 14 december booked", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("already booked", result["answer"])
        self.assertNotIn("2023-12-14", result["answer"])

    def test_model_intent_is_strict_and_receives_schema_not_rows(self):
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'{"choices":[{"message":{"content":"{\\"kind\\":\\"count\\",\\"field\\":\\"status\\",\\"value\\":\\"confirmed\\",\\"date\\":\\"\\",\\"booking_id\\":\\"\\",\\"name\\":\\"\\"}"}}]}'
        def fake_urlopen(request, timeout):
            captured["body"] = request.data.decode("utf-8")
            return Response()
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model"}, clear=True):
            with mock.patch("app.urllib.request.urlopen", side_effect=fake_urlopen):
                result = app._model_intent("How many bookings are confirmed?", ["booking_id", "status", "customer_name"])
        self.assertEqual(result["kind"], "count")
        self.assertIn("How many bookings are confirmed?", captured["body"])
        self.assertNotIn("Ananya Gupta", captured["body"])

    def test_intent_assisted_routing_still_uses_deterministic_rows(self):
        intent = {"kind": "count", "field": "status", "value": "confirmed", "date": "", "booking_id": ""}
        with mock.patch("app._model_intent", return_value=intent), mock.patch("app._model_synthesis", return_value=None):
            result = app.answer_with_optional_synthesis("Could you tell me how many are locked in?", app.load_bookings())
        self.assertTrue(result["intent_assisted"])
        self.assertIn("6 bookings", result["answer"])

    def test_openrouter_pool_rotates_key_and_model_on_provider_failure(self):
        app.OPENROUTER_CURSOR = 0
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEYS": "key-a,key-b", "OPENROUTER_MODELS": "model-a,model-b"}, clear=True):
            self.assertEqual(app._openrouter_options(), [("key-a", "model-a"), ("key-b", "model-b")])
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b'{"ok": true}'
            calls = []
            def fake_urlopen(request, timeout):
                calls.append(request.headers["Authorization"])
                if len(calls) == 1:
                    raise app.urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, None)
                return Response()
            with mock.patch("app.urllib.request.urlopen", side_effect=fake_urlopen):
                result = app._openrouter_call([], 10)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, ["Bearer key-a", "Bearer key-b"])

    def test_openrouter_pool_starts_next_request_with_next_key(self):
        app.OPENROUTER_CURSOR = 0
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEYS": "key-a,key-b", "OPENROUTER_MODELS": "model-a,model-b"}, clear=True):
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b'{"ok": true}'
            calls = []
            def fake_urlopen(request, timeout):
                calls.append(request.headers["Authorization"])
                return Response()
            with mock.patch("app.urllib.request.urlopen", side_effect=fake_urlopen):
                self.assertEqual(app._openrouter_call([], 10), {"ok": True})
                self.assertEqual(app._openrouter_call([], 10), {"ok": True})
        self.assertEqual(calls, ["Bearer key-a", "Bearer key-b"])


    def test_model_cannot_add_customer_ownership_to_public_package_answer(self):
        grounded = {"answer": "Yes, Haldi + Mehndi appears in the current booking sheet. Ask me for its recorded price if you would like to check it.", "escalated": False}
        body = {"choices": [{"message": {"content": "Yes, Haldi + Mehndi is included in your current booking."}}]}
        with mock.patch.object(app, "_openrouter_options", return_value=[("key", "model")]), mock.patch.object(app, "_openrouter_call", return_value=body), mock.patch.dict(app.os.environ, {"OPENROUTER_ALLOW_GROUNDED_DATA": "1"}):
            self.assertIsNone(app._model_synthesis("Do you provide a haldi shoot?", grounded))

    def test_customer_page_has_inline_hold_flow(self):
        page = app.customer_page()
        self.assertIn("function addInlineHold", page)
        self.assertIn("if(d.hold_offer)addInlineHold", page)
        self.assertNotIn("id='date' type='date'", page)
        self.assertNotIn("Request hold</button><div id='holdResult'", page)

    def test_natural_language_dates_use_next_upcoming_occurrence(self):
        result = app.grounded_answer("is 20 dec free", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertEqual(result.get("hold_offer"), "2026-12-20")
        self.assertIn("20 December 2026", result["answer"])

    def test_natural_language_package_prices(self):
        rows = app.load_bookings()
        for question, expected in (("full package kitne ka hai", "₹1,85,000"), ("pre wedding shoot price", "45,000"), ("haldi mehndi ka rate", "55,000")):
            with self.subTest(question=question):
                result = app.grounded_answer(question, rows)
                self.assertFalse(result["escalated"])
                self.assertIn(expected, result["answer"])

    def test_customer_natural_variants_are_not_escalated(self):
        rows = app.load_bookings()
        cases = {
            "How much do you charge for pre-wedding photography?": "45,000",
            "What do you charge for pre-wedding photos?": "45,000",
            "What’s the cost for the full wedding package?": "₹1,85,000",
            "Can I book the 20th of December?": "20 December 2026",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                result = app.customer_answer(question, rows)
                self.assertFalse(result["escalated"])
                self.assertIn(expected, result["answer"])

    def test_service_and_package_extremes_use_recorded_prices(self):
        rows = app.load_bookings()
        service = app.customer_answer("Do you do maternity shoots?", rows)
        self.assertFalse(service["escalated"])
        self.assertIn("Maternity Shoot", service["answer"])
        self.assertIn("₹", service["answer"])
        highest = app.owner_answer("What is the most expensive package?", rows)
        self.assertFalse(highest["escalated"])
        self.assertIn("highest-priced", highest["answer"])

    def test_customer_copy_uses_human_currency_dates_and_album_language(self):
        rows = app.load_bookings()
        price = app.customer_answer("What is the package price for SS-2043?", rows)
        self.assertIn("₹1,20,000", price["answer"])
        date = app.customer_answer("When is SS-2031?", rows)
        self.assertIn("22 November 2026", date["answer"])
        album = app.customer_answer("Where is my album SS-2043?", rows)
        self.assertIn("Your album is", album["answer"])

    def test_escalation_copy_is_human(self):
        result = app.customer_answer("Can you guarantee my date?", app.load_bookings())
        self.assertTrue(result["escalated"])
        self.assertIn("sent it to the studio owner", result["answer"])

    def test_owner_unsupported_question_is_natural_and_grounded(self):
        result = app.owner_answer("Why did bookings decline?", app.load_bookings())
        self.assertTrue(result["escalated"])
        self.assertIn("does not contain enough evidence", result["answer"])

    def test_month_first_and_ambiguous_dates_are_handled(self):
        rows = app.load_bookings()
        result = app.customer_answer("Is December 20 booked?", rows)
        self.assertFalse(result["escalated"])
        self.assertIn("20 December 2026", result["answer"])
        clarification = app.customer_answer("Is the 19th free?", rows)
        self.assertFalse(clarification["escalated"])
        self.assertIn("day and month", clarification["answer"])

    def test_generic_booking_question_requests_id(self):
        result = app.customer_answer("Can you tell me about this booking?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("booking ID", result["answer"])

    def test_greeting_is_not_escalated(self):
        for question in ("hi", "hi, how u doing", "hello there"):
            with self.subTest(question=question):
                result = app.customer_answer(question, app.load_bookings())
                self.assertFalse(result["escalated"])
                self.assertIn("How can I help", result["answer"])

    def test_conversational_messages_do_not_escalate(self):
        for question in ("hi, how u doing", "how are you?", "thanks for your help"):
            with self.subTest(question=question):
                result = app.customer_answer(question, app.load_bookings())
                self.assertFalse(result["escalated"])
                self.assertTrue(result["answer"])

    def test_small_talk_model_receives_no_booking_rows(self):
        captured = {}
        def fake_call(messages, max_tokens):
            captured["prompt"] = json.dumps(messages)
            return {"choices": [{"message": {"content": "I’m doing well — how can I help?"}}]}
        with mock.patch.object(app, "_openrouter_options", return_value=[("key", "model")]), mock.patch.object(app, "_openrouter_call", side_effect=fake_call):
            result = app.customer_answer("hi, how u doing", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertEqual(result["synthesis"], "openrouter")
        self.assertNotIn("Ananya Gupta", captured["prompt"])

    def test_held_date_is_not_reported_as_free(self):
        self.assertTrue(app.create_hold("2026-12-20", "First customer")["success"])
        result = app.grounded_answer("is 20 dec free", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertNotIn("hold_offer", result)
        self.assertIn("on hold", result["answer"])

    def test_free_date_returns_hold_offer(self):
        result = app.customer_answer("Can I book 20 December 2026?", app.load_bookings())
        self.assertEqual(result.get("hold_offer"), "2026-12-20")

    def test_owner_auth_parser_still_rejects_missing_credentials(self):
        class Handler:
            client_address = ("127.0.0.1", 1)
            headers = {}
        with mock.patch.dict(app.os.environ, {"OWNER_PASSWORD": "secret"}, clear=True):
            self.assertFalse(app.owner_authorized(Handler()))

    def test_explicit_booking_field_beats_model_intent_label(self):
        rows = app.load_bookings()
        intent = {"kind": "personal_lookup", "field": "status", "value": "", "date": "", "booking_id": "SS-2043", "name": ""}
        with mock.patch.object(app, "_model_intent", return_value=intent), mock.patch.object(app, "_model_synthesis", return_value=None):
            result = app.answer_with_optional_synthesis("What is my customer name SS-2043?", rows)
        self.assertIn("Ananya Gupta", result["answer"])
        self.assertNotIn("tentative", result["answer"])

    def _guest_session(self, conn, phone, name="Guest"):
        conn.execute("INSERT INTO wedding_guests(name,phone,side,functions_json,invited_count) VALUES(?,?,?,?,?)", (name, phone, "Bride", '["Mehendi","Wedding"]', 2))
        session_id = f"test-session-{phone}"
        result = app.guest_desk.start_guest_session(conn, phone, session_id)
        self.assertTrue(result["success"])
        return session_id

    def test_fifteen_natural_guest_messages_update_or_escalate_correctly(self):
        conn = app.db()
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('wedding_date','2026-11-21', 'now')")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('mehendi_date','2026-11-19', 'now')")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('venue','Lotus Convention Centre, Coimbatore', 'now')")
        conn.commit()
        cases = [
            ("Haan aa rahe hain, 4 log, 21 ko train se", {"rsvp_status": "coming", "party_size": 4, "arrival_date": "2026-11-21", "arrival_mode": "train"}, "aane wala"),
            ("Hum nahi aa payenge, sorry", {"rsvp_status": "not_coming", "party_size": 0}, "nahi aa raha"),
            ("We are coming, 3 people, flight on 21 Nov 2026, need pickup", {"rsvp_status": "coming", "party_size": 3, "arrival_date": "2026-11-21", "arrival_mode": "flight", "needs_pickup": 1}, "pickup"),
            ("We need a room for our stay", {"needs_room": 1}, "room"),
            ("We don't need pickup", {"needs_pickup": 0}, "don't need a pickup"),
            ("Venue kahan hai?", {}, "Lotus Convention Centre"),
            ("Mehendi kab hai?", {}, "19 november 2026"),
            ("We are 2 people and coming", {"rsvp_status": "coming", "party_size": 2}, "2 people"),
            ("No, we aren't attending", {"rsvp_status": "not_coming", "party_size": 0}, "unable to come"),
            ("Train se 21 ko aayenge", {"arrival_date": "2026-11-21", "arrival_mode": "train"}, "aayenge"),
            ("Please reserve a room", {"needs_room": 1}, "need a room"),
            ("Pickup chahiye for 2 people", {"needs_pickup": 1, "party_size": 2}, "pickup"),
            ("What is the venue?", {}, "Lotus Convention Centre"),
            ("Can I bring my dog?", {}, "passed your message to them"),
            ("Thanks anna", {}, "you're welcome"),
        ]
        for index, (message, expected, answer_fragment) in enumerate(cases, start=1):
            with self.subTest(message=message):
                phone = f"90000000{index:02d}"
                session_id = self._guest_session(conn, phone)
                result = app.guest_desk.guest_chat(conn, session_id, message)
                self.assertIn(answer_fragment.lower(), result.get("answer", "").lower())
                saved = conn.execute("SELECT * FROM wedding_guests WHERE phone=?", (phone,)).fetchone()
                for field, value in expected.items():
                    self.assertEqual(saved[field], value, f"{message}: {field}")
        conn.close()

    def test_hinglish_both_of_us_reply_records_party_size_two(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000088", "Meena")
        result = app.guest_desk.guest_chat(conn, session_id, "Hum dono aa rahe hain, flight se")
        saved = conn.execute("SELECT party_size FROM wedding_guests WHERE phone='9000000088'").fetchone()
        self.assertEqual(saved["party_size"], 2)
        self.assertIn("2 log", result["answer"])
        conn.close()

    def test_guest_upload_validation_and_guest_count(self):
        conn = app.db()
        good = b"name,phone,side,functions,people\nAsha,9876543210,Bride,Mehendi;Wedding,3\n"
        result = app.guest_desk.upload_guests(conn, good, "guest-list.csv")
        self.assertEqual(result["guests"], 1)
        self.assertIn("Mehendi", result["functions"])
        bad = b"name,phone\nAsha,9876543210\n"
        with self.assertRaisesRegex(ValueError, "needs columns"):
            app.guest_desk.upload_guests(conn, bad, "bad.csv")
        conn.close()

    def test_function_schedule_answer_is_readable_and_comes_from_uploaded_details(self):
        conn = app.db()
        app.guest_desk.upload_facts(conn, b"item,value\nMehendi Date,2026-11-19\nMehendi Time,2026-11-19 16:00\n", "details.csv")
        answer = app.guest_desk._answer_fact("Mehendi kab hai?", app.guest_desk._facts(conn))
        self.assertEqual(answer, "Mehendi 19 November 2026 ko 4:00 PM par hai.")
        conn.close()

    def test_function_schedule_questions_return_only_requested_event_and_detail(self):
        facts = {
            "mehendi_date": "2026-11-19",
            "mehendi_time": "2026-11-19 16:00",
            "sangeet_date": "2026-11-20",
            "sangeet_time": "2026-11-20 19:00",
            "reception_date": "2026-11-22",
            "reception_time": "2026-11-22 19:00",
        }
        self.assertEqual(
            app.guest_desk._answer_fact("Sangeet kis din hai?", facts),
            "Sangeet 20 November 2026 ko 7:00 PM par hai.",
        )
        self.assertEqual(
            app.guest_desk._answer_fact("What date is the Reception?", facts),
            "Reception is on 22 November 2026 at 7:00 PM.",
        )
        self.assertEqual(
            app.guest_desk._answer_fact("What time does the Reception start?", facts),
            "Reception is on 22 November 2026 at 7:00 PM.",
        )

    def test_natural_english_decline_phrase_updates_rsvp(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000098", "Asha")
        result = app.guest_desk.guest_chat(conn, session_id, "Sorry, I can't make it to the wedding.")
        saved = conn.execute(
            "SELECT rsvp_status,party_size,function_responses_json FROM wedding_guests WHERE phone='9000000098'"
        ).fetchone()
        self.assertEqual(saved["rsvp_status"], "pending")
        self.assertEqual(saved["party_size"], 0)
        self.assertEqual(json.loads(saved["function_responses_json"]), {"Wedding": "not_coming"})
        self.assertFalse(result["escalated"])
        self.assertIn("unable to come", result["answer"].lower())
        conn.close()

    def test_openrouter_guest_interpreter_returns_validated_intent_and_redacts_guest_data(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "intent": "rsvp", "attendance": "coming", "functions": ["Wedding"],
            "party_size": 4, "arrival_mode": "train", "needs_room": True,
            "needs_pickup": False, "fact_key": "", "confidence": 0.98,
        })}}]}
        captured = {}
        def fake_call(messages, max_tokens):
            captured["prompt"] = messages[-1]["content"]
            return response
        with mock.patch.object(app, "_openrouter_options", return_value=[("fake", "test/model")]), mock.patch.object(app, "_openrouter_call", side_effect=fake_call):
            result = app._model_guest_intent(
                "Ananya Iyer, 9000000001: chaar log pakka aayenge train se, room chahiye",
                ["Wedding"], ["venue", "wedding_date"], "Ananya Iyer", "9000000001", ["Ananya Iyer", "Karthik Raman"],
            )
        self.assertEqual(result["party_size"], 4)
        self.assertEqual(result["functions"], ["Wedding"])
        self.assertNotIn("Ananya Iyer", captured["prompt"])
        self.assertNotIn("Karthik Raman", captured["prompt"])
        self.assertNotIn("9000000001", captured["prompt"])
        self.assertNotIn("Lotus Convention Centre", captured["prompt"])

    def test_model_interpreted_rsvp_fills_only_unparsed_fields(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000087", "Asha")
        parsed = {"intent": "rsvp", "attendance": "coming", "functions": [], "party_size": 4,
                  "arrival_mode": "train", "needs_room": True, "needs_pickup": False,
                  "fact_key": "", "confidence": 0.96}
        result = app.guest_desk.guest_chat(conn, session_id, "Pakka hum aayenge, chaar log rail se, room chahiye", parsed)
        saved = conn.execute("SELECT rsvp_status,party_size,arrival_mode,needs_room,needs_pickup FROM wedding_guests WHERE phone='9000000087'").fetchone()
        self.assertEqual(tuple(saved), ("coming", 4, "train", 1, 0))
        self.assertTrue(result["escalated"])
        conn.close()

    def test_model_fact_key_still_reads_value_from_uploaded_family_sheet(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000086", "Asha")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('venue','Lotus Hall','now')")
        conn.commit()
        parsed = {"intent": "wedding_fact", "attendance": "unknown", "functions": [], "party_size": None,
                  "arrival_mode": "unknown", "needs_room": None, "needs_pickup": None,
                  "fact_key": "venue", "confidence": 0.97}
        result = app.guest_desk.guest_chat(conn, session_id, "Where do we gather?", parsed)
        self.assertEqual(result["answer"], "The venue is Lotus Hall.")
        self.assertFalse(result["escalated"])
        conn.close()

    def test_model_maps_unseen_wording_to_multiple_uploaded_facts(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000085", "Asha")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('venue','Lotus Hall','now')")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('dress_code','Traditional attire','now')")
        conn.execute("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES('parking','Available beside the hall','now')")
        conn.commit()
        response = {"choices": [{"message": {"content": json.dumps({
            "intent": "wedding_fact", "attendance": "unknown", "functions": [],
            "party_size": None, "arrival_mode": "unknown", "needs_room": None,
            "needs_pickup": None, "fact_keys": ["venue", "dress_code"],
            "fact_key": "", "confidence": 0.97,
        })}}]}
        captured = {}
        def fake_call(messages, max_tokens):
            captured["prompt"] = messages[-1]["content"]
            return response
        with mock.patch.object(app, "_openrouter_options", return_value=[("fake", "test/model")]), mock.patch.object(app, "_openrouter_call", side_effect=fake_call):
            intent = app._model_guest_intent("What should I wear, and where do we meet?", ["Wedding"], ["venue", "dress_code", "parking"])
        self.assertEqual(intent["fact_keys"], ["venue", "dress_code"])
        self.assertIn("Match the meaning of the question, not its exact wording", captured["prompt"])
        self.assertNotIn("Lotus Hall", captured["prompt"])
        result = app.guest_desk.guest_chat(conn, session_id, "What should I wear, and where do we meet?", intent)
        self.assertIn("Lotus Hall", result["answer"])
        self.assertIn("Traditional attire", result["answer"])
        self.assertNotIn("Available beside the hall", result["answer"])
        self.assertFalse(result["escalated"])
        conn.close()

    def test_model_classified_general_small_talk_does_not_escalate(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000084", "Asha")
        intent = {"intent": "small_talk", "attendance": "unknown", "functions": [],
                  "party_size": None, "arrival_mode": "unknown", "needs_room": None,
                  "needs_pickup": None, "fact_key": "", "fact_keys": [], "confidence": 0.96}
        result = app.guest_desk.guest_chat(conn, session_id, "Hope you're doing well today", intent)
        self.assertIn("doing well", result["answer"].lower())
        self.assertFalse(result["escalated"])
        self.assertEqual(len(app.guest_desk.family_inbox(conn)), 0)
        conn.close()

    def test_unknown_question_escalates_and_family_reply_reaches_guest(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000099", "Asha")
        result = app.guest_desk.guest_chat(conn, session_id, "Can we bring our dog to the venue?")
        self.assertTrue(result["escalated"])
        inbox = app.guest_desk.family_inbox(conn)
        self.assertEqual(len(inbox), 1)
        self.assertTrue(app.guest_desk.family_reply(conn, inbox[0]["id"], "Please leave pets at home."))
        messages = app.guest_desk.conversation(conn, session_id)
        self.assertEqual(messages[-1]["role"], "family")
        self.assertEqual(messages[-1]["body"], "Please leave pets at home.")
        conn.close()

    def test_event_name_alone_does_not_answer_unrelated_wedding_detail(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000098", "Asha")
        app.guest_desk.upload_facts(
            conn,
            b"item,value\nSangeet Date,2026-11-20\nSangeet Time,2026-11-20 18:30\nWedding Date,2026-11-21\nVenue,Lotus Hall\n",
            "details.csv",
        )
        for question in (
            "Is there a dress code for Sangeet?",
            "Can I bring a dog to the wedding?",
            "Can we bring our dog to the venue?",
        ):
            with self.subTest(question=question):
                result = app.guest_desk.guest_chat(conn, session_id, question)
                self.assertTrue(result["escalated"])
                self.assertIn("passed your message to them", result["answer"])
        schedule = app.guest_desk._answer_fact("Sangeet kab hai?", app.guest_desk._facts(conn))
        self.assertIn("20 November 2026", schedule)
        self.assertIn("6:30 PM", schedule)
        conn.close()

    def test_dashboard_counts_coming_no_and_pending_per_function(self):
        conn = app.db()
        one = self._guest_session(conn, "9000000091", "Coming Guest")
        two = self._guest_session(conn, "9000000092", "No Guest")
        self._guest_session(conn, "9000000093", "Pending Guest")
        app.guest_desk.guest_chat(conn, one, "Haan, 4 log aa rahe hain")
        app.guest_desk.guest_chat(conn, two, "Nahi aa payenge")
        data = app.guest_desk.dashboard(conn)
        self.assertEqual(data["functions"]["Wedding"], {"coming": 1, "not_coming": 1, "pending": 1, "headcount": 4})
        conn.close()

    def test_guest_can_rsvp_to_a_specific_function_without_marking_all_functions(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000094", "Function Guest")
        result = app.guest_desk.guest_chat(conn, session_id, "Mehendi aa rahe hain")
        self.assertIn("Mehendi ke liye", result["answer"])
        data = app.guest_desk.dashboard(conn)
        self.assertEqual(data["functions"]["Mehendi"]["coming"], 1)
        self.assertEqual(data["functions"]["Wedding"]["pending"], 1)
        conn.close()

    def test_mixed_hinglish_function_rsvp_updates_wedding_and_reception_separately(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000081", "Arjun")
        conn.execute("UPDATE wedding_guests SET functions_json='[\"Wedding\",\"Reception\"]', invited_count=3 WHERE phone='9000000081'")
        result = app.guest_desk.guest_chat(conn, session_id, "Hum 2 log aayenge shaadi mein, reception nahi aa paayenge")
        saved = conn.execute("SELECT function_responses_json,party_size FROM wedding_guests WHERE phone='9000000081'").fetchone()
        responses = json.loads(saved["function_responses_json"])
        self.assertEqual(responses, {"Wedding": "coming", "Reception": "not_coming"})
        self.assertEqual(saved["party_size"], 2)
        self.assertIn("Wedding (aayenge)", result["answer"])
        self.assertIn("Reception (nahi aa payenge)", result["answer"])
        dashboard = app.guest_desk.dashboard(conn)
        self.assertEqual(dashboard["functions"]["Wedding"], {"coming": 1, "not_coming": 0, "pending": 0, "headcount": 2})
        self.assertEqual(dashboard["functions"]["Reception"], {"coming": 0, "not_coming": 1, "pending": 0, "headcount": 0})
        self.assertFalse(result["escalated"])
        conn.close()

    def test_party_count_alone_marks_guest_coming(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000080", "Meena")
        result = app.guest_desk.guest_chat(conn, session_id, "Hum 6 log aayenge")
        saved = conn.execute("SELECT rsvp_status,party_size FROM wedding_guests WHERE phone='9000000080'").fetchone()
        self.assertEqual(tuple(saved), ("coming", 6))
        self.assertIn("aane wala mark", result["answer"])
        conn.close()

    def test_party_size_over_invitation_is_saved_and_flagged_for_family(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000079", "Divya")
        result = app.guest_desk.guest_chat(conn, session_id, "Hum 4 log aayenge")
        saved = conn.execute("SELECT rsvp_status,party_size FROM wedding_guests WHERE phone='9000000079'").fetchone()
        inbox = app.guest_desk.family_inbox(conn)
        self.assertEqual(tuple(saved), ("coming", 4))
        self.assertTrue(result["escalated"])
        self.assertEqual(len(inbox), 1)
        self.assertIn("lists 2", inbox[0]["reason"])
        self.assertIn("flag", result["answer"].lower())
        conn.close()

    def test_ok_and_thanks_are_acknowledged_without_family_escalation(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000078", "Nila")
        for message in ("ok", "thanks"):
            result = app.guest_desk.guest_chat(conn, session_id, message)
            self.assertFalse(result["escalated"], message)
            self.assertEqual(app.guest_desk.family_inbox(conn), [])
        conn.close()

    def test_hinglish_schedule_answer_is_conversational_and_includes_date(self):
        facts = {"sangeet_date": "2026-11-20", "sangeet_time": "2026-11-20 18:30"}
        self.assertEqual(app.guest_desk._answer_fact("Sangeet ka time kya hai?", facts), "Sangeet 20 November 2026 ko 6:30 PM par hai.")
        self.assertEqual(app.guest_desk._answer_fact("Tell me what time Sangeet starts", facts), "Sangeet is on 20 November 2026 at 6:30 PM.")

    def test_ambiguous_day_only_arrival_is_not_saved_and_goes_to_family(self):
        conn = app.db()
        session_id = self._guest_session(conn, "9000000095", "Ambiguous Guest")
        result = app.guest_desk.guest_chat(conn, session_id, "Train se 21 ko aa rahe hain")
        saved = conn.execute("SELECT arrival_date FROM wedding_guests WHERE phone='9000000095'").fetchone()
        self.assertTrue(result["escalated"])
        self.assertIsNone(saved["arrival_date"])
        self.assertEqual(len(app.guest_desk.family_inbox(conn)), 1)
        conn.close()

    def test_uploaded_guest_list_and_facts_are_database_persistent(self):
        conn = app.db()
        app.guest_desk.upload_guests(conn, b"name,phone,side,functions,people\nAsha,9876543210,Bride,Wedding,2\n", "guests.csv")
        app.guest_desk.upload_facts(conn, b"item,value\nVenue,Lotus Hall\n", "details.csv")
        conn.close()
        conn = app.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM wedding_guests").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT fact_value FROM wedding_facts WHERE fact_key='venue'").fetchone()[0], "Lotus Hall")
        conn.close()

if __name__ == "__main__":
    unittest.main()
