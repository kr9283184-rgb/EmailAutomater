import os
import tempfile
import unittest
from unittest import mock

DATA_DIR = tempfile.mkdtemp()

os.environ["DATA_DIR"] = DATA_DIR
os.environ["DAILY_LIMIT"] = "2"
os.environ["GAP_MINUTES"] = "30"

from email_automator import core


class TestCsv(unittest.TestCase):
    def test_parses_and_deduplicates(self):
        items, err = core.parse_csv("name,email\nA,a@x.com\nB,b@x.com\na@x.com\nbad-email\n")
        self.assertEqual(err, "")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "A")
        self.assertEqual(items[0]["email"], "a@x.com")
        self.assertEqual(items[0]["status"], "pending")

    def test_rejects_invalid(self):
        items, err = core.parse_csv("name,email\nOnlyName\n")
        self.assertEqual(items, [])
        self.assertIn("No valid", err)

    def test_rejects_empty(self):
        items, err = core.parse_csv("")
        self.assertEqual(items, [])
        self.assertEqual(err, "CSV is empty")

    def test_quoted_fields(self):
        items, err = core.parse_csv('name,email\n"Doe, John",john@x.com\n')
        self.assertEqual(items[0]["name"], "Doe, John")


class TestPin(unittest.TestCase):
    def test_roundtrip(self):
        core.set_json("meta", core.create_pin_meta("1234"))
        self.assertTrue(core.check_pin("1234"))
        self.assertFalse(core.check_pin("wrong"))

    def test_no_meta_fails(self):
        core.set_json("meta", None)
        self.assertFalse(core.check_pin("1234"))


class TestTemplate(unittest.TestCase):
    def test_replace_name(self):
        self.assertEqual(core.replace_name("Hi {name}!", "Priya"), "Hi Priya!")

    def test_is_html(self):
        self.assertTrue(core.is_html("<p>Hello</p>"))
        self.assertFalse(core.is_html("plain text"))


@mock.patch.object(core, "send_mail")
class TestSendOnce(unittest.TestCase):
    def setUp(self):
        core.set_json("lock", None)
        core.set_json("settings", {"user": "me@x.com", "pass": "pw", "host": "smtp.x.com", "port": 465,
                                   "secure": True, "fromName": "", "subject": "Hi {name}", "body": "Hello {name}"})
        core.set_json("queue", {"items": [
            {"name": "A", "email": "a@x.com", "status": "pending", "error": "", "sentAt": ""},
            {"name": "B", "email": "b@x.com", "status": "pending", "error": "", "sentAt": ""},
        ], "paused": False})
        core.set_json("daily", {"date": core.today_utc(), "count": 0, "lastSentAt": ""})

    def test_sends_one_and_marks_sent(self, send):
        r = core.run_send_once()
        self.assertEqual(r["status"], "sent")
        send.assert_called_once()
        args = send.call_args[0]
        self.assertEqual(args[1], "a@x.com")
        self.assertIn("A", args[2])
        queue = core.get_json("queue")
        self.assertEqual(queue["items"][0]["status"], "sent")

    def test_gap_respected(self, send):
        core.run_send_once()
        core.set_json("lock", None)
        r = core.run_send_once()
        self.assertEqual(r["status"], "gap")
        self.assertEqual(send.call_count, 1)

    def test_daily_limit(self, send):
        core.set_json("daily", {"date": core.today_utc(), "count": 2, "lastSentAt": 0})
        r = core.run_send_once()
        self.assertEqual(r["status"], "daily-limit")
        send.assert_not_called()

    def test_paused(self, send):
        core.set_json("queue", {"items": [{"email": "a@x.com", "status": "pending"}], "paused": True})
        r = core.run_send_once()
        self.assertEqual(r["status"], "paused")
        send.assert_not_called()

    def test_no_settings(self, send):
        core.set_json("settings", None)
        r = core.run_send_once()
        self.assertEqual(r["status"], "no-settings")

    def test_failed_marked(self, send):
        send.side_effect = Exception("boom")
        r = core.run_send_once()
        self.assertEqual(r["status"], "failed")
        self.assertEqual(core.get_json("queue")["items"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
