from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.models import Profile, SendJob
from app.sender import Sender


class FakeDatabase:
    def __init__(self):
        self.finished = []
        self.profile_value = Profile(1, "test", "ON", 0)

    def profile(self, profile_id):
        return self.profile_value

    def in_cooldown(self, profile_id, sender_id, seconds):
        return False

    def is_opted_out(self, sender_id):
        return False

    def finish_job(self, job, status, error_class=None):
        self.finished.append((status, error_class))

    def defer_job(self, job_id, seconds, error_class):
        raise AssertionError("not expected")


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    async def send_message(self, recipient, text):
        if self.error:
            raise self.error
        self.messages.append((recipient, text))


async def ignore_notice(text):
    return None


class SenderTests(unittest.IsolatedAsyncioTestCase):
    def job(self):
        return SendJob(1, 1, -1001, 42, 99, "reply", 1, datetime.now(UTC))

    async def test_success_is_recorded_once(self):
        db = FakeDatabase()
        client = FakeClient()
        sender = Sender(client, db, 0, 0.01, ignore_notice)
        await sender._send(self.job())
        self.assertEqual(client.messages, [(99, "reply")])
        self.assertEqual(db.finished, [("sent", None)])

    async def test_unknown_error_becomes_ambiguous_without_retry(self):
        db = FakeDatabase()
        client = FakeClient(TimeoutError("unknown result"))
        sender = Sender(client, db, 0, 0.01, ignore_notice)
        await sender._send(self.job())
        self.assertEqual(db.finished, [("ambiguous", "TimeoutError")])
        self.assertEqual(client.messages, [])

    async def test_off_profile_cancels_pending_job(self):
        db = FakeDatabase()
        db.profile_value.mode = "OFF"
        client = FakeClient()
        sender = Sender(client, db, 0, 0.01, ignore_notice)
        await sender._send(self.job())
        self.assertEqual(db.finished, [("cancelled", "ProfileInactive")])
        self.assertEqual(client.messages, [])
