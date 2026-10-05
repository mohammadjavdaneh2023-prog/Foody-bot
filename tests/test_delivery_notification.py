from __future__ import annotations

import unittest

from app.control_bot import ControlBot


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    async def send_message(self, peer, text, **kwargs):
        if self.error:
            raise self.error
        self.messages.append((peer, text, kwargs))


class DeliveryNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_is_sent_to_control_bot_and_saved_messages(self):
        bot = FakeClient()
        user = FakeClient()
        control = ControlBot(bot, user, db=None, admin_id=12345, config=None)

        await control.notify_sent("پیام ورودی", "پاسخ نمونه")

        self.assertEqual(len(bot.messages), 1)
        self.assertEqual(bot.messages[0][0], 12345)
        self.assertEqual(user.messages[0][0], "me")
        self.assertEqual(bot.messages[0][1], user.messages[0][1])
        self.assertIn("به یک نفر پیام دادم", bot.messages[0][1])
        self.assertIn("پیامی که فرستاده بود:\nپیام ورودی", bot.messages[0][1])
        self.assertIn("پیامی که بهش دادم:\nپاسخ نمونه", bot.messages[0][1])
        self.assertEqual(bot.messages[0][2], {"parse_mode": None})

    async def test_bot_notification_failure_does_not_skip_saved_messages(self):
        bot = FakeClient(error=RuntimeError("bot unavailable"))
        user = FakeClient()
        control = ControlBot(bot, user, db=None, admin_id=12345, config=None)

        await control.notify_sent("پیام ورودی", "پاسخ نمونه")

        self.assertEqual(bot.messages, [])
        self.assertEqual(len(user.messages), 1)

    async def test_legacy_job_without_source_text_is_explained(self):
        bot = FakeClient()
        user = FakeClient()
        control = ControlBot(bot, user, db=None, admin_id=12345, config=None)

        await control.notify_sent("", "پاسخ نمونه")

        self.assertIn("متن پیام اولیه در صف قدیمی ذخیره نشده بود", bot.messages[0][1])

    async def test_long_text_is_split_without_losing_content(self):
        bot = FakeClient()
        user = FakeClient()
        control = ControlBot(bot, user, db=None, admin_id=12345, config=None)
        sent_text = "آ" * 9000

        await control.notify_sent(sent_text, "پاسخ")

        self.assertGreater(len(bot.messages), 1)
        self.assertTrue(all(len(item[1]) <= 3500 for item in bot.messages))
        joined = "".join(item[1] for item in bot.messages).replace("ادامهٔ متن پیام:\n\n", "")
        self.assertIn(sent_text, joined)
