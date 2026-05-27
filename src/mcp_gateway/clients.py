from __future__ import annotations

import os
from contextlib import AsyncExitStack
from dataclasses import dataclass

import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from src.mcp_gateway.config import RemoteServerConfig
from src.mcp_gateway.logging import get_logger


@dataclass
class ManagedClient:
    session: ClientSession
    stack: AsyncExitStack
    config: RemoteServerConfig


class MCPClientManager:
    def __init__(self) -> None:
        self.clients: dict[str, ClientSession] = {}
        self._managed: dict[str, ManagedClient] = {}
        self.logger = get_logger("clients")

    async def add_from_config(
        self,
        servers: dict[str, RemoteServerConfig],
    ) -> dict[str, ClientSession]:
        created: dict[str, ClientSession] = {}

        for name, server_config in servers.items():
            created[name] = await self.add(name, server_config)

        return created

    async def add(self, name: str, server_config: RemoteServerConfig) -> ClientSession:
        if name in self._managed:
            await self.remove(name)

        managed = await self._open_client(server_config)
        self._managed[name] = managed
        self.clients[name] = managed.session
        self.logger.info("Connected backend '%s' via %s", name, server_config.transport)
        return managed.session

    async def remove(self, name: str) -> None:
        managed = self._managed.pop(name, None)
        self.clients.pop(name, None)

        if managed is not None:
            await managed.stack.aclose()
            self.logger.info("Closed backend '%s'", name)

    async def close(self) -> None:
        for name in list(self._managed):
            await self.remove(name)

    async def _open_client(self, server_config: RemoteServerConfig) -> ManagedClient:
        stack = AsyncExitStack()
        await stack.__aenter__()

        try:
            if server_config.transport == "stdio":
                env = os.environ.copy()
                env.update(server_config.env)
                parameters = StdioServerParameters(
                    command=server_config.command or "",
                    args=server_config.args,
                    env=env,
                    cwd=server_config.cwd,
                    encoding=server_config.encoding,
                    encoding_error_handler=server_config.encoding_error_handler,
                )
                read_stream, write_stream = await stack.enter_async_context(stdio_client(parameters))
            elif server_config.transport == "sse":
                read_stream, write_stream = await stack.enter_async_context(
                    sse_client(
                        url=server_config.url or "",
                        headers=server_config.headers or None,
                    )
                )
            elif server_config.transport == "streamable-http":
                http_client = None
                if server_config.headers:
                    http_client = await stack.enter_async_context(
                        httpx.AsyncClient(headers=server_config.headers)
                    )

                read_stream, write_stream, _ = await stack.enter_async_context(
                    streamable_http_client(
                        url=server_config.url or "",
                        http_client=http_client,
                    )
                )
            else:
                raise ValueError(f"Unsupported backend transport: {server_config.transport}")

            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            return ManagedClient(session=session, stack=stack, config=server_config)
        except Exception:
            await stack.aclose()
            raise
