from __future__ import annotations

import unittest

from app.watcher import NewMessageReconciler


class FakeMessage:
    def __init__(self, message_id: int):
        self.id = message_id


class FakeClient:
    def __init__(self, messages: list[FakeMessage] | None = None):
        self.messages = messages or []

    async def get_messages(self, chat_id: int, limit: int):
        del chat_id, limit
        return sorted(self.messages, key=lambda message: message.id, reverse=True)[:1]

    async def iter_messages(self, chat_id: int, min_id: int, reverse: bool):
        del chat_id
        self.assert_reverse = reverse
        for message in sorted(self.messages, key=lambda item: item.id):
            if message.id > min_id:
                yield message


class MessageReconcilerTests(unittest.IsolatedAsyncioTestCase):
    async def test_initializes_at_latest_message_and_processes_only_new_messages_in_order(self):
        client = FakeClient([FakeMessage(2), FakeMessage(1)])
        processed: list[int] = []

        async def handler(message):
            processed.append(message.id)
            return True

        reconciler = NewMessageReconciler(client, -1001, handler)
        await reconciler.initialize()
        self.assertEqual(reconciler.last_message_id, 2)

        client.messages.extend([FakeMessage(4), FakeMessage(3)])
        count = await reconciler.scan_once()

        self.assertEqual(count, 2)
        self.assertEqual(processed, [3, 4])
        self.assertEqual(reconciler.last_message_id, 4)
        self.assertTrue(client.assert_reverse)

    async def test_retries_from_failed_message_without_skipping_later_messages(self):
        client = FakeClient([FakeMessage(1)])
        processed: list[int] = []

        async def handler(message):
            processed.append(message.id)
            return len(processed) > 1

        reconciler = NewMessageReconciler(client, -1001, handler)
        await reconciler.initialize()
        reconciler.last_message_id = 0

        client.messages.extend([FakeMessage(2), FakeMessage(3)])
        self.assertEqual(await reconciler.scan_once(), 0)
        self.assertEqual(reconciler.last_message_id, 0)

        self.assertEqual(await reconciler.scan_once(), 3)
        self.assertEqual(reconciler.last_message_id, 3)
        self.assertEqual(processed, [1, 1, 2, 3])

    async def test_empty_chat_starts_at_zero(self):
        client = FakeClient()
        reconciler = NewMessageReconciler(client, -1001, lambda _: None)

        await reconciler.initialize()

        self.assertEqual(reconciler.last_message_id, 0)


if __name__ == "__main__":
    unittest.main()
