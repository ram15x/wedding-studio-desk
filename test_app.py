import sys
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
    def test_unsupported_cause_escalates(self):
        result = app.grounded_answer("Why are wedding packages expensive?", app.load_bookings())
        self.assertTrue(result["escalated"])
        self.assertIn("owner", result["answer"])

    def test_date_hold_is_unique(self):
        first = app.create_hold("2028-11-22", "First customer")
        second = app.create_hold("2028-11-22", "Second customer")
        self.assertTrue(first["success"])
        self.assertFalse(second["success"])

    def test_existing_booking_cannot_be_held(self):
        result = app.create_hold("2026-11-22", "Another customer")
        self.assertFalse(result["success"])
        self.assertIn("uploaded booking sheet", result["error"])

    def test_booked_date_answer_is_explicitly_unavailable(self):
        result = app.grounded_answer("Is 2026-11-22 available?", app.load_bookings())
        self.assertFalse(result["escalated"])
        self.assertIn("not available", result["answer"])

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

    def test_synthesis_must_preserve_verified_numeric_anchors(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b'{"choices":[{"message":{"content":"Wedding is most common."}}]}'
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model"}, clear=True):
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
        with mock.patch.dict(app.os.environ, {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "test/model"}, clear=True):
            with mock.patch("app.urllib.request.urlopen", return_value=Response()):
                result = app.answer_with_optional_synthesis("Which event type is most common?", app.load_bookings())
        self.assertEqual(result["synthesis"], "openrouter")
        self.assertIn("Source: studio_bookings.csv", result["answer"])


if __name__ == "__main__":
    unittest.main()
