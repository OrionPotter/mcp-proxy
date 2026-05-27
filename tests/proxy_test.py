from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from mcp import types
from mcp.server.lowlevel.server import Server
from mcp.shared.memory import create_connected_server_and_client_session

from src.mcp_gateway.clients import MCPClientManager
from src.mcp_gateway.proxy import MCPGatewayProxy


@asynccontextmanager
async def connected_proxy(*servers: Server):
    sessions = []
    try:
        for server in servers:
            session_context = create_connected_server_and_client_session(server)
            session = await session_context.__aenter__()
            sessions.append((server.name, session, session_context))

        manager = MCPClientManager()
        manager.clients = {name: session for name, session, _ in sessions}
        proxy = await MCPGatewayProxy.create(manager)

        proxy_context = create_connected_server_and_client_session(proxy)
        proxy_session = await proxy_context.__aenter__()
        try:
            yield proxy_session
        finally:
            await proxy_context.__aexit__(None, None, None)
    finally:
        for _, _, context in reversed(sessions):
            await context.__aexit__(None, None, None)


@pytest.fixture
async def alpha_server() -> Server:
    server = Server("alpha")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="echo",
                description="Echo text",
                inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, str] | None) -> list[types.TextContent]:
        assert name == "echo"
        return [types.TextContent(type="text", text=f"alpha:{arguments['message']}")]

    return server


@pytest.fixture
async def beta_server() -> Server:
    server = Server("beta")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="echo",
                description="Echo text",
                inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, str] | None) -> list[types.TextContent]:
        assert name == "echo"
        return [types.TextContent(type="text", text=f"beta:{arguments['message']}")]

    return server


@pytest.mark.asyncio
async def test_proxy_namespaces_tools(alpha_server: Server, beta_server: Server) -> None:
    async with connected_proxy(alpha_server, beta_server) as session:
        await session.initialize()
        tools = await session.list_tools()
        tool_names = {tool.name for tool in tools.tools}

    assert tool_names == {"alpha.echo", "beta.echo"}


@pytest.mark.asyncio
async def test_proxy_routes_tool_calls(alpha_server: Server, beta_server: Server) -> None:
    async with connected_proxy(alpha_server, beta_server) as session:
        await session.initialize()
        alpha_result = await session.call_tool("alpha.echo", {"message": "hello"})
        beta_result = await session.call_tool("beta.echo", {"message": "hello"})

    assert alpha_result.content[0].text == "alpha:hello"
    assert beta_result.content[0].text == "beta:hello"
