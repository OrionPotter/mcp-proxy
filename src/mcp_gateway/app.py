from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from src.mcp_gateway.clients import MCPClientManager
from src.mcp_gateway.config import GatewayConfig, GatewayTransport
from src.mcp_gateway.logging import configure_logging, get_logger
from src.mcp_gateway.proxy import MCPGatewayProxy


class GatewaySettings(BaseModel):
    config: str = "./examples/config/servers.json"
    transport: GatewayTransport = "stdio"
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "INFO"
    name: str = "mcp-gateway"
    sse_path: str = "/sse"
    sse_message_path: str = "/messages/"
    streamable_http_path: str = "/mcp"


class StreamableHTTPRoute:
    def __init__(self, session_manager: StreamableHTTPSessionManager) -> None:
        self.session_manager = session_manager

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        await self.session_manager.handle_request(scope, receive, send)


class MCPGatewayApp:
    def __init__(self, **settings: Any) -> None:
        self.settings = GatewaySettings(**settings)
        configure_logging(self.settings.log_level)
        self.logger = get_logger("app")
        self.client_manager = MCPClientManager()
        self.proxy: MCPGatewayProxy | None = None

    async def run(self) -> None:
        config = GatewayConfig.load(self.settings.config)
        await self.client_manager.add_from_config(config.mcpServers)
        self.proxy = await MCPGatewayProxy.create(
            client_manager=self.client_manager,
            name=self.settings.name,
        )

        try:
            await self._serve()
        finally:
            await self.client_manager.close()

    async def _serve(self) -> None:
        if self.proxy is None:
            raise RuntimeError("Proxy is not initialized.")

        if self.settings.transport == "stdio":
            async with stdio_server() as (read_stream, write_stream):
                await self.proxy.run(
                    read_stream,
                    write_stream,
                    self.proxy.create_initialization_options(),
                )
            return

        app = self._build_http_app()
        config = uvicorn.Config(
            app=app,
            host=self.settings.host,
            port=self.settings.port,
            log_level=self.settings.log_level.lower(),
        )
        await uvicorn.Server(config).serve()

    def _build_http_app(self) -> Starlette:
        if self.proxy is None:
            raise RuntimeError("Proxy is not initialized.")

        if self.settings.transport == "sse":
            sse_transport = SseServerTransport(self.settings.sse_message_path)

            async def handle_sse(request: Request) -> None:
                async with sse_transport.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,
                ) as (read_stream, write_stream):
                    await self.proxy.run(
                        read_stream,
                        write_stream,
                        self.proxy.create_initialization_options(),
                    )

            return Starlette(
                routes=[
                    Route(self.settings.sse_path, endpoint=handle_sse),
                    Mount(self.settings.sse_message_path, app=sse_transport.handle_post_message),
                    Route("/health", endpoint=self.handle_health),
                    Route("/servers", endpoint=self.handle_servers, methods=["GET", "POST"]),
                    Route("/servers/{name}", endpoint=self.handle_server_delete, methods=["DELETE"]),
                    Route("/tools", endpoint=self.handle_tools, methods=["GET"]),
                ]
            )

        session_manager = StreamableHTTPSessionManager(app=self.proxy)

        @asynccontextmanager
        async def lifespan(_: Starlette):
            async with session_manager.run():
                yield

        return Starlette(
            routes=[
                Route(self.settings.streamable_http_path, endpoint=StreamableHTTPRoute(session_manager)),
                Route("/health", endpoint=self.handle_health),
                Route("/servers", endpoint=self.handle_servers, methods=["GET", "POST"]),
                Route("/servers/{name}", endpoint=self.handle_server_delete, methods=["DELETE"]),
                Route("/tools", endpoint=self.handle_tools, methods=["GET"]),
            ],
            lifespan=lifespan,
        )

    async def handle_health(self, _: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "transport": self.settings.transport,
                "servers": sorted(self.client_manager.clients),
            }
        )

    async def handle_servers(self, request: Request) -> JSONResponse:
        if self.proxy is None:
            return JSONResponse({"error": "Proxy not initialized."}, status_code=500)

        if request.method == "GET":
            return JSONResponse({"servers": sorted(self.client_manager.clients)})

        payload = await request.json()
        config = GatewayConfig.model_validate(payload)
        await self.client_manager.add_from_config(config.mcpServers)
        for name in config.mcpServers:
            await self.proxy.register_client(name, self.client_manager.clients[name])

        return JSONResponse({"added": sorted(config.mcpServers)})

    async def handle_server_delete(self, request: Request) -> JSONResponse:
        if self.proxy is None:
            return JSONResponse({"error": "Proxy not initialized."}, status_code=500)

        name = request.path_params["name"]
        if name not in self.client_manager.clients:
            return JSONResponse({"error": f"Unknown server '{name}'."}, status_code=404)

        await self.proxy.unregister_client(name)
        await self.client_manager.remove(name)
        return JSONResponse({"removed": name})

    async def handle_tools(self, _: Request) -> JSONResponse:
        if self.proxy is None:
            return JSONResponse({"error": "Proxy not initialized."}, status_code=500)

        return JSONResponse({"tools": await self.proxy.list_server_tools()})
