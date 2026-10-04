from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from http import HTTPStatus

from .db import Database


@dataclass(slots=True)
class HealthState:
    version: str
    db: Database | None = None
    migrations_ready: bool = False
    telegram_ready: bool = False
    shutting_down: bool = False

    def ready(self) -> bool:
        return bool(
            not self.shutting_down
            and self.db
            and self.migrations_ready
            and self.telegram_ready
            and self.db.check()
        )


async def start_health_server(state: HealthState, port: int) -> asyncio.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2)
            parts = request_line.decode("ascii", errors="replace").split()
            method, path = (parts[0], parts[1].split("?", 1)[0]) if len(parts) >= 2 else ("", "")
            if method != "GET":
                status, payload = HTTPStatus.METHOD_NOT_ALLOWED, {"status": "method_not_allowed"}
            elif path == "/healthz":
                status, payload = HTTPStatus.OK, {"status": "alive"}
            elif path == "/readyz":
                ready = state.ready()
                status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
                payload = {"status": "ready" if ready else "not_ready"}
            elif path == "/version":
                status, payload = HTTPStatus.OK, {"version": state.version}
            else:
                status, payload = HTTPStatus.NOT_FOUND, {"status": "not_found"}
            body = json.dumps(payload, separators=(",", ":")).encode()
            writer.write(
                f"HTTP/1.1 {status.value} {status.phrase}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + body
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    return await asyncio.start_server(handle, "0.0.0.0", port)
