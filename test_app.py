import sys
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app


class AssignmentDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.tmp.name) / "desk.db"
        app.CSV_PATH = Path(__file__).parent / "data" / "studio_bookings.csv"
        app.SOURCE_DISPLAY_NAME = app.CSV_PATH.name

    def tearDown(self):
        self.tmp.cleanup()

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
            ("how much is full package", "185,000"),
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
            ("how much is full package", "185,000"),
            ("what does wedding day cost", "120,000"),
            ("what is my balance for SS-2043", "80,000"),
            ("where is my album SS-2043", "not started"),
            ("what is the status of SS-2043", "tentative"),
            ("what city is SS-2043 in", "Delhi"),
            ("what package do I have SS-2043", "Wedding Day"),
            ("what date is SS-2048", "2027-01-17"),
            ("what is the event for SS-2031", "wedding"),
            ("what is the customer name for SS-2043", "Ananya Gupta"),
            ("which city has the most bookings", "Owner analytics"),
            ("how many bookings are confirmed", "Owner analytics"),
            ("what is my balance", "Please share your booking ID"),
            ("will bookings increase next month", "owner for review"),
            ("can I get a refund", "owner for review"),
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
        self.assertIn("₹120,000", wedding_day["answer"])
        natural = app.grounded_answer("What is the Wedding Day price?", app.load_bookings())
        self.assertFalse(natural["escalated"])
        self.assertIn("₹120,000", natural["answer"])

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
        for question, expected in (("full package kitne ka hai", "185,000"), ("pre wedding shoot price", "45,000"), ("haldi mehndi ka rate", "55,000")):
            with self.subTest(question=question):
                result = app.grounded_answer(question, rows)
                self.assertFalse(result["escalated"])
                self.assertIn(expected, result["answer"])

    def test_customer_natural_variants_are_not_escalated(self):
        rows = app.load_bookings()
        cases = {
            "How much do you charge for pre-wedding photography?": "45,000",
            "What do you charge for pre-wedding photos?": "45,000",
            "What’s the cost for the full wedding package?": "185,000",
            "Can I book the 20th of December?": "20 December 2026",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                result = app.customer_answer(question, rows)
                self.assertFalse(result["escalated"])
                self.assertIn(expected, result["answer"])

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

if __name__ == "__main__":
    unittest.main()
