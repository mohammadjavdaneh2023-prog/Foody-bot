from __future__ import annotations

import os
import unittest

import psycopg

from app.db import Database
from app.migrations import migrate


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not configured")
class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ["TEST_DATABASE_URL"]
        migrate(cls.database_url)

    def setUp(self):
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                TRUNCATE event_logs,outbound_jobs,recipient_opt_outs,contact_history,service_runtime,
                    telegram_updates,schedule_windows,
                    reply_messages,not_terms,rule_terms,rule_groups,profiles RESTART IDENTITY CASCADE
                """
            )
            conn.execute("INSERT INTO service_runtime(singleton,last_successful_send_at) VALUES (TRUE,NULL)")
        self.db = Database(self.database_url)

    def tearDown(self):
        self.db.close()

    def test_profile_rules_and_cascade(self):
        profile_id = self.db.create_profile("test", 900)
        self.db.add_group(profile_id, ["عباسپور", "دانشگاه عباسپور"])
        self.db.add_not_terms(profile_id, ["واگذار شد"])
        self.db.add_reply(profile_id, "سلام")
        self.db.add_window(profile_id, 0, 630, 810)
        profile = self.db.profile(profile_id)
        self.assertEqual(profile.rule_groups[0][0], "عباسپور")
        self.assertEqual(profile.not_terms, ["واگذار شد"])
        self.db.delete_profile(profile_id)
        self.assertEqual(self.db.profiles(), [])

    def test_durable_deduplicated_outbound_job(self):
        profile_id = self.db.create_profile("lunch", 900)
        self.db.add_reply(profile_id, "سلام")
        self.db.update_profile(profile_id, mode="ON")
        profile = self.db.profile(profile_id)
        self.assertEqual(self.db.enqueue_match(profile, -1001, 42, 99, "پیام ورودی"), "queued")
        self.assertEqual(self.db.enqueue_match(profile, -1001, 42, 99, "پیام ورودی"), "duplicate")
        job = self.db.claim_next_job()
        self.assertIsNotNone(job)
        self.assertEqual(job.source_text, "پیام ورودی")
        self.db.finish_job(job, "sent")
        self.assertTrue(self.db.in_cooldown(profile_id, 99, 900))
        self.assertEqual(self.db.queue_counts(), {"sent": 1})

    def test_restart_marks_uncertain_send_ambiguous(self):
        profile_id = self.db.create_profile("lunch", 0)
        self.db.add_reply(profile_id, "سلام")
        profile = self.db.profile(profile_id)
        self.db.enqueue_match(profile, -1001, 43, 100, "پیام ورودی")
        job = self.db.claim_next_job()
        self.assertIsNotNone(job)
        self.assertEqual(self.db.recover_inflight(), 1)
        self.assertEqual(self.db.queue_counts(), {"ambiguous": 1})
        with psycopg.connect(self.database_url) as conn:
            stored = conn.execute("SELECT source_text FROM outbound_jobs WHERE id=%s", (job.id,)).fetchone()
        self.assertEqual(stored[0], "")

    def test_recipient_opt_out_is_persistent(self):
        self.assertFalse(self.db.is_opted_out(99))
        self.db.opt_out(99)
        self.assertTrue(self.db.is_opted_out(99))
        self.db.opt_in(99)
        self.assertFalse(self.db.is_opted_out(99))

    def test_global_send_interval_survives_database_client_restart(self):
        profile_id = self.db.create_profile("lunch", 0)
        self.db.add_reply(profile_id, "سلام")
        profile = self.db.profile(profile_id)
        self.db.enqueue_match(profile, -1001, 44, 101, "پیام ورودی")
        job = self.db.claim_next_job()
        self.db.finish_job(job, "sent")
        first_wait = self.db.global_send_wait(60)
        self.assertGreater(first_wait, 55)

        self.db.close()
        self.db = Database(self.database_url)
        second_wait = self.db.global_send_wait(60)
        self.assertGreater(second_wait, 55)
        self.assertLessEqual(second_wait, first_wait)

    def test_source_text_is_cleared_when_job_reaches_terminal_state(self):
        profile_id = self.db.create_profile("test", 0)
        self.db.add_reply(profile_id, "پاسخ")
        profile = self.db.profile(profile_id)
        self.db.enqueue_match(profile, -1001, 45, 102, "متن پیام گروه")
        job = self.db.claim_next_job()
        self.assertEqual(job.source_text, "متن پیام گروه")

        with psycopg.connect(self.database_url) as conn:
            stored = conn.execute("SELECT source_text FROM outbound_jobs WHERE id=%s", (job.id,)).fetchone()
        self.assertEqual(stored[0], "متن پیام گروه")

        self.db.finish_job(job, "sent")

        with psycopg.connect(self.database_url) as conn:
            stored = conn.execute("SELECT source_text FROM outbound_jobs WHERE id=%s", (job.id,)).fetchone()
        self.assertEqual(stored[0], "")
