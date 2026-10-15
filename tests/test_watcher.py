from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telethon.errors import FloodWaitError
from telethon.tl.types import User

from app.models import Profile
from app.watcher import HistoryPoller


class HistoryPollerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stop = asyncio.Event()
        self.profile = Profile(1, "test", "ON", 0, rule_groups=[["food"]])
        self.db = Mock()
        self.db.profiles.return_value = [self.profile]
        self.db.enqueue_match.return_value = "queued"
        self.client = SimpleNamespace(get_messages=AsyncMock(return_value=[]))
        self.poller = HistoryPoller(self.client, self.db, AsyncMock(), -1001, UTC, self.stop, 0.01)
        self.poller.active_since[1] = datetime.now(UTC) - timedelta(seconds=10)

    def message(self, mid=42, text="food"):
        return SimpleNamespace(
            id=mid,
            raw_text=text,
            date=datetime.now(UTC),
            out=False,
            get_sender=AsyncMock(return_value=User(id=99)),
        )

    async def test_all_off_never_fetches_or_records_messages(self):
        self.profile.mode = "OFF"
        await self.poller.poll_once()
        self.client.get_messages.assert_not_awaited()
        self.db.enqueue_match.assert_not_called()
        self.db.record_ignored.assert_not_called()

    async def test_three_messages_oldest_first_and_no_duplicate_jobs(self):
        self.client.get_messages.return_value = [self.message(3), self.message(2), self.message(1)]
        await self.poller.poll_once()
        await self.poller.poll_once()
        self.assertEqual([call.args[2] for call in self.db.enqueue_match.call_args_list], [1, 2, 3])
        self.client.get_messages.assert_awaited_with(-1001, limit=3)

    async def test_first_matching_profile_wins_even_if_an_earlier_profile_does_not_match(self):
        earlier = Profile(0, "earlier", "ON", 0, rule_groups=[["other"]])
        later = Profile(2, "later", "ON", 0, rule_groups=[["food"]])
        self.db.profiles.return_value = [later, self.profile, earlier]
        self.client.get_messages.return_value = [self.message()]
        await self.poller.poll_once()
        self.assertEqual(self.db.enqueue_match.call_args.args[0].id, 1)

    async def test_profile_disabled_during_fetch_does_not_enqueue(self):
        async def fetch(*args, **kwargs):
            self.profile.mode = "OFF"
            return [self.message()]

        self.client.get_messages.side_effect = fetch
        await self.poller.poll_once()
        self.db.enqueue_match.assert_not_called()

    async def test_old_messages_are_not_replied_to_on_activation(self):
        self.poller.active_since.clear()
        msg = self.message()
        msg.date -= timedelta(minutes=1)
        self.client.get_messages.return_value = [msg]
        await self.poller.poll_once()
        self.db.enqueue_match.assert_not_called()

    async def test_inactive_schedule_never_fetches(self):
        self.profile.mode = "SCHEDULE"
        await self.poller.poll_once()
        self.client.get_messages.assert_not_awaited()

    async def test_slow_request_never_overlaps_and_does_not_block_other_work(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_fetch(*args, **kwargs):
            entered.set()
            await release.wait()
            return []

        self.client.get_messages.side_effect = slow_fetch
        task = asyncio.create_task(self.poller.run())
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            await asyncio.sleep(0.05)  # Five polling intervals pass while the request stays pending.
            self.assertEqual(self.client.get_messages.await_count, 1)
            self.stop.set()
            release.set()
            await asyncio.wait_for(task, timeout=1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_flood_wait_is_respected_without_additional_fetches(self):
        self.client.get_messages.side_effect = FloodWaitError(request=None, capture=17)

        async def wait(seconds):
            self.assertEqual(seconds, 17)
            self.stop.set()

        self.poller.wait = wait
        await self.poller.run()
        self.assertEqual(self.client.get_messages.await_count, 1)

    async def test_transient_failure_retries_without_marking_message_seen(self):
        msg = self.message()
        msg.get_sender.side_effect = [TimeoutError(), User(id=99)]
        self.client.get_messages.return_value = [msg]
        with self.assertRaises(TimeoutError):
            await self.poller.poll_once()
        await self.poller.poll_once()
        self.db.enqueue_match.assert_called_once()
