from __future__ import annotations

import asyncio
import json
import unittest

from app.health import HealthState, start_health_server


class FakeDatabase:
    def __init__(self, healthy=True):
        self.healthy = healthy

    def check(self):
        return self.healthy


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = HealthState("abc123")
        self.server = await start_health_server(self.state, 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def request(self, path):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
        await writer.drain()
        raw = await reader.read()
        writer.close()
        await writer.wait_closed()
        head, body = raw.split(b"\r\n\r\n", 1)
        return int(head.split()[1]), json.loads(body)

    async def test_liveness_and_version_do_not_expose_configuration(self):
        self.assertEqual(await self.request("/healthz"), (200, {"status": "alive"}))
        self.assertEqual(await self.request("/version"), (200, {"version": "abc123"}))

    async def test_readiness_requires_database_migrations_and_telegram(self):
        self.assertEqual((await self.request("/readyz"))[0], 503)
        self.state.db = FakeDatabase()
        self.state.migrations_ready = True
        self.state.telegram_ready = True
        self.assertEqual((await self.request("/readyz"))[0], 200)
        self.state.shutting_down = True
        self.assertEqual((await self.request("/readyz"))[0], 503)
