from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.models import Profile, SendJob
from app.sender import Sender


class FakeDatabase:
    def __init__(self):
        self.finished = []
        self.profile_value = Profile(1, "test", "ON", 0)
        self.global_wait_requests = []
        self.global_wait_value = 0.0

    def profile(self, profile_id):
        return self.profile_value

    def in_cooldown(self, profile_id, sender_id, seconds):
        return False

    def is_opted_out(self, sender_id):
        return False

    def global_send_wait(self, minimum_interval):
        self.global_wait_requests.append(minimum_interval)
        return self.global_wait_value

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


async def ignore_sent_notice(text):
    return None


class SenderTests(unittest.IsolatedAsyncioTestCase):
    def job(self):
        return SendJob(1, 1, -1001, 42, 99, "group message", "reply", 1, datetime.now(UTC))

    async def test_success_is_recorded_once(self):
        db = FakeDatabase()
        client = FakeClient()
        notify_sent = AsyncMock()
        sender = Sender(client, db, 5, 0.01, ignore_notice, notify_sent)
        await sender._send(self.job())
        self.assertEqual(client.messages, [(99, "reply")])
        self.assertEqual(db.finished, [("sent", None)])
        self.assertEqual(db.global_wait_requests, [5])
        notify_sent.assert_awaited_once_with("group message", "reply")

    async def test_notification_failure_does_not_change_success_or_retry_send(self):
        db = FakeDatabase()
        client = FakeClient()
        notify_sent = AsyncMock(side_effect=RuntimeError("private notification failed"))
        sender = Sender(client, db, 0, 0.01, ignore_notice, notify_sent)

        await sender._send(self.job())

        self.assertEqual(client.messages, [(99, "reply")])
        self.assertEqual(db.finished, [("sent", None)])
        notify_sent.assert_awaited_once_with("group message", "reply")

    async def test_unknown_error_becomes_ambiguous_without_retry(self):
        db = FakeDatabase()
        client = FakeClient(TimeoutError("unknown result"))
        sender = Sender(client, db, 0, 0.01, ignore_notice, ignore_sent_notice)
        await sender._send(self.job())
        self.assertEqual(db.finished, [("ambiguous", "TimeoutError")])
        self.assertEqual(client.messages, [])

    async def test_persisted_global_wait_is_applied_before_send(self):
        db = FakeDatabase()
        db.global_wait_value = 7.5
        client = FakeClient()
        sender = Sender(client, db, 10, 0.01, ignore_notice, ignore_sent_notice)
        with patch("app.sender.asyncio.sleep", new=AsyncMock()) as sleep:
            await sender._send(self.job())
        sleep.assert_awaited_once_with(7.5)
        self.assertEqual(client.messages, [(99, "reply")])

    async def test_off_profile_cancels_pending_job(self):
        db = FakeDatabase()
        db.profile_value.mode = "OFF"
        client = FakeClient()
        sender = Sender(client, db, 0, 0.01, ignore_notice, ignore_sent_notice)
        await sender._send(self.job())
        self.assertEqual(db.finished, [("cancelled", "ProfileInactive")])
        self.assertEqual(client.messages, [])
