import os
import tempfile
import time
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

DATA_DIR = tempfile.mkdtemp()

os.environ["DATA_DIR"] = DATA_DIR
os.environ["DAILY_LIMIT"] = "2"
os.environ["GAP_MINUTES"] = "30"
os.environ["SEND_START_HOUR"] = "0"
os.environ["SEND_END_HOUR"] = "24"

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


class TestCredsSecurity(unittest.TestCase):
    def test_legacy_creds_migrated_to_memory_and_scrubbed(self):
        core.set_json("settings", {"host": "smtp.x.com", "user": "old@x.com", "pass": "secret"})
        core.set_smtp_creds("", "")
        core.migrate_old_creds()
        settings = core.get_json("settings")
        self.assertNotIn("user", settings)
        self.assertNotIn("pass", settings)
        self.assertEqual(core.get_smtp_creds()["user"], "old@x.com")
        self.assertEqual(core.get_smtp_creds()["pass"], "secret")


class TestTemplate(unittest.TestCase):
    def test_replace_name(self):
        self.assertEqual(core.replace_name("Hi {name}!", "Priya"), "Hi Priya!")

    def test_is_html(self):
        self.assertTrue(core.is_html("<p>Hello</p>"))
        self.assertFalse(core.is_html("plain text"))


class TestSpamCheck(unittest.TestCase):
    def test_clean_message_scores_low(self):
        r = core.spam_check("Project update", "Hi {name}, the API you asked about is ready. Here are the details and docs.")
        self.assertLess(r["score"], 30)

    def test_spammy_message_scores_high(self):
        r = core.spam_check("FREE MONEY NOW!!!", "CLICK HERE!!! WIN A PRIZE!!! BUY NOW!!! CASH!!!")
        self.assertGreaterEqual(r["score"], 50)
        self.assertTrue(r["issues"])

    def test_html_stripped_for_scoring(self):
        r = core.spam_check("Hi", "<p>Free prize offer</p>")
        self.assertGreaterEqual(r["score"], 10)


class TestDomainAndWindow(unittest.TestCase):
    def test_domain_of(self):
        self.assertEqual(core.domain_of("a@Gmail.COM"), "gmail.com")
        self.assertEqual(core.domain_of("nodomain"), "")

    def test_outside_window(self):
        night = datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("UTC"))
        noon = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
        with mock.patch.object(core, "SEND_START_HOUR", 8), mock.patch.object(core, "SEND_END_HOUR", 21):
            self.assertTrue(core.outside_window(night))
            self.assertFalse(core.outside_window(noon))

    def test_timezone_aware_now(self):
        with mock.patch.object(core, "TIMEZONE", "Europe/Brussels"):
            now = core._now_tz()
            self.assertEqual(now.tzinfo, ZoneInfo("Europe/Brussels"))


class TestPersistCreds(unittest.TestCase):
    def test_roundtrip_encrypted(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        creds_file = os.path.join(core.DATA_DIR, "creds.enc")
        try:
            with mock.patch.object(core, "PERSIST_CREDS", True), mock.patch.object(core, "CREDS_KEY", key):
                core.set_smtp_creds("u@x.com", "pw123")
                self.assertTrue(os.path.exists(creds_file))
                with open(creds_file, "rb") as f:
                    raw = f.read()
                self.assertNotIn(b"pw123", raw)
                self.assertNotIn(b"u@x.com", raw)

                core.set_smtp_creds("", "")
                self.assertFalse(os.path.exists(creds_file))
                self.assertEqual(core.get_smtp_creds()["user"], "")

                core.set_smtp_creds("u@x.com", "pw123")
                core._SMTP_CREDS["user"] = ""
                core._SMTP_CREDS["pass"] = ""
                core._load_persisted_creds()
                self.assertEqual(core.get_smtp_creds()["user"], "u@x.com")
                self.assertEqual(core.get_smtp_creds()["pass"], "pw123")
        finally:
            core.set_smtp_creds("", "")
            core.set_smtp_creds("me@x.com", "pw")


@mock.patch.object(core, "send_mail")
class TestSendOnce(unittest.TestCase):
    def setUp(self):
        core.set_json("lock", None)
        core.set_smtp_creds("me@x.com", "pw")
        core.set_json("settings", {"host": "smtp.x.com", "port": 465, "secure": True,
                                   "fromName": "", "subject": "Hi {name}", "body": "Hello {name}"})
        core.set_json("queue", {"items": [
            {"name": "A", "email": "a@x.com", "status": "pending", "error": "", "sentAt": ""},
            {"name": "B", "email": "b@x.com", "status": "pending", "error": "", "sentAt": ""},
        ], "paused": False})
        core.set_json("daily", {"date": core.today_key(), "count": 0, "lastSentAt": "", "domains": {}})

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
        core.set_json("daily", {"date": core.today_key(), "count": 2, "lastSentAt": 0})
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

    def test_creds_needed(self, send):
        core.set_smtp_creds("", "")
        r = core.run_send_once()
        self.assertEqual(r["status"], "creds-needed")
        send.assert_not_called()

    def test_creds_never_persisted(self, send):
        core.run_send_once()
        settings = core.get_json("settings")
        self.assertNotIn("user", settings)
        self.assertNotIn("pass", settings)

    def test_failed_marked(self, send):
        send.side_effect = Exception("boom")
        r = core.run_send_once()
        self.assertEqual(r["status"], "failed")
        self.assertEqual(core.get_json("queue")["items"][0]["status"], "failed")

    def test_domain_cap(self, send):
        with mock.patch.object(core, "DOMAIN_DAILY_LIMIT", 1), mock.patch.object(core, "GAP_MINUTES", 0):
            r = core.run_send_once()
            self.assertEqual(r["status"], "sent")
            core.set_json("lock", None)
            r = core.run_send_once()
            self.assertEqual(r["status"], "domain-limit")
            self.assertEqual(send.call_count, 1)

    def test_outside_window_blocks(self, send):
        night = datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("UTC"))
        with mock.patch.object(core, "SEND_START_HOUR", 8), mock.patch.object(core, "SEND_END_HOUR", 21):
            with mock.patch.object(core, "_now_tz", return_value=night):
                r = core.run_send_once()
        self.assertEqual(r["status"], "outside-window")
        send.assert_not_called()

    def test_send_tracks_domain(self, send):
        core.run_send_once()
        daily = core.get_json("daily")
        self.assertEqual(daily["domains"].get("x.com"), 1)


@mock.patch("email_automator.core.smtplib.SMTP_SSL")
class TestSendMailParts(unittest.TestCase):
    def test_html_message_has_text_and_html_parts(self, SMTP):
        SMTP.return_value.__enter__.return_value.send_message.return_value = None
        core.send_mail(
            {"host": "smtp.x.com", "port": 465, "secure": True, "user": "me@x.com", "pass": "pw", "fromName": ""},
            "a@x.com", "Subject", "<p>Hello <b>world</b></p>",
        )
        ctx = SMTP.return_value.__enter__.return_value
        msg = ctx.send_message.call_args[0][0]
        self.assertTrue(msg.is_multipart())
        self.assertIn("Hello world", msg.get_payload()[0].get_content())
        self.assertEqual(msg.get_payload()[1].get_content_type(), "text/html")

    def test_plain_message_stays_single(self, SMTP):
        core.send_mail(
            {"host": "smtp.x.com", "port": 465, "secure": True, "user": "me@x.com", "pass": "pw", "fromName": ""},
            "a@x.com", "Subject", "plain text body",
        )
        ctx = SMTP.return_value.__enter__.return_value
        msg = ctx.send_message.call_args[0][0]
        self.assertFalse(msg.is_multipart())
        self.assertEqual(msg.get_content().rstrip(), "plain text body")


if __name__ == "__main__":
    unittest.main()
