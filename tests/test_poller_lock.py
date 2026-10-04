from __future__ import annotations

import asyncio
import unittest

from app.__main__ import acquire_poller_lock_with_wait


class FakeLockDatabase:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def acquire_poller_lock(self):
        self.calls += 1
        return next(self.outcomes, False)


class PollerLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_deploy_waits_until_previous_deploy_releases_lock(self):
        db = FakeLockDatabase([False, False, True])
        acquired = await acquire_poller_lock_with_wait(
            db,
            asyncio.Event(),
            timeout=0.1,
            retry_interval=0.001,
        )
        self.assertTrue(acquired)
        self.assertEqual(db.calls, 3)

    async def test_lock_wait_has_a_bounded_timeout(self):
        db = FakeLockDatabase([False])
        acquired = await acquire_poller_lock_with_wait(
            db,
            asyncio.Event(),
            timeout=0.005,
            retry_interval=0.001,
        )
        self.assertFalse(acquired)
