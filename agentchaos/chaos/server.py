"""Run a :class:`ChaosProxy` as an in-process ASGI server on a loopback port.

The server binds port 0 (OS-assigned) and serves in the SAME event loop as a
background task (no thread). ``start()`` does not return until the socket is
accepting connections, so the first tool call cannot race the bind.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any

import uvicorn

from agentchaos.chaos.proxy import ChaosProxy


def _build_asgi_app(proxy: ChaosProxy) -> Callable[..., Awaitable[None]]:
    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        # Drain the request body.
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)

        headers = {
            k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        path = scope["path"]
        if scope.get("query_string"):
            path = f"{path}?{scope['query_string'].decode('latin-1')}"

        result = await proxy.handle(scope["method"], path, headers, body)

        await send(
            {
                "type": "http.response.start",
                "status": result.status,
                "headers": [
                    (k.encode("latin-1"), v.encode("latin-1"))
                    for k, v in result.headers.items()
                ],
            }
        )
        await send({"type": "http.response.body", "body": result.body})

    return app


class ChaosProxyServer:
    """In-process uvicorn server fronting a :class:`ChaosProxy`."""

    def __init__(self, proxy: ChaosProxy, *, host: str = "127.0.0.1") -> None:
        self._proxy = proxy
        self._host = host
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None
        self._port: int | None = None

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("server not started")
        return f"http://{self._host}:{self._port}"

    async def start(self) -> str:
        """Start serving in the background; return base_url once accepting."""
        config = uvicorn.Config(
            _build_asgi_app(self._proxy),
            host=self._host,
            port=0,
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)
        server.config.load()
        self._server = server
        self._task = asyncio.create_task(server.serve())

        # Wait for uvicorn to bind and publish its socket(s).
        while not server.started:
            if self._task.done():
                # Surface a startup failure instead of hanging.
                self._task.result()
                raise RuntimeError("chaos proxy server exited during startup")
            await asyncio.sleep(0.005)

        sockets = server.servers[0].sockets if server.servers else []
        if not sockets:
            raise RuntimeError("chaos proxy server bound no sockets")
        self._port = sockets[0].getsockname()[1]
        return self.base_url

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
        await self._proxy.aclose()

    async def __aenter__(self) -> ChaosProxyServer:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()
