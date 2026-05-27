from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
SSE_BACKEND_CONFIG = str(ROOT / "examples" / "config" / "sse-backend.json")
STREAMABLE_BACKEND_CONFIG = str(ROOT / "examples" / "config" / "streamable-http-backend.json")
SANDBOX_BLOCKS_STDIO = os.name == "nt"


async def wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for port {port}")


async def safe_kill(process: asyncio.subprocess.Process | None) -> None:
    if process is None:
        return
    if process.returncode is None:
        process.kill()
    await process.wait()


async def initialize_and_call_ping(session: ClientSession, message: str) -> tuple[set[str], str]:
    await session.initialize()
    tools = await session.list_tools()
    result = await session.call_tool("remote-echo.ping", {"message": message})
    return {tool.name for tool in tools.tools}, result.content[0].text


@pytest.mark.asyncio
@pytest.mark.skipif(SANDBOX_BLOCKS_STDIO, reason="Windows sandbox blocks stdio named pipes")
async def test_gateway_stdio_transport() -> None:
    backend = await asyncio.create_subprocess_exec(
        sys.executable,
        "tests/tools/echo_server.py",
        "--name",
        "remote-sse",
        "--transport",
        "sse",
        "--port",
        "9090",
        cwd=str(ROOT),
    )
    try:
        await wait_for_port(9090)
        params = StdioServerParameters(
            command=sys.executable,
            args=["main.py", "--config", SSE_BACKEND_CONFIG],
            cwd=str(ROOT),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                tool_names, text = await initialize_and_call_ping(session, "stdio")
    finally:
        await safe_kill(backend)

    assert "remote-echo.ping" in tool_names
    assert text == "remote-sse:stdio"


@pytest.mark.asyncio
async def test_gateway_sse_transport() -> None:
    backend = await asyncio.create_subprocess_exec(
        sys.executable,
        "tests/tools/echo_server.py",
        "--name",
        "remote-sse",
        "--transport",
        "sse",
        "--port",
        "9090",
        cwd=str(ROOT),
    )
    gateway = None
    try:
        await wait_for_port(9090)
        gateway = await asyncio.create_subprocess_exec(
            sys.executable,
            "main.py",
            "--config",
            SSE_BACKEND_CONFIG,
            "--transport",
            "sse",
            cwd=str(ROOT),
        )
        await wait_for_port(8080)
        async with sse_client("http://127.0.0.1:8080/sse") as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                tool_names, text = await initialize_and_call_ping(session, "sse")
    finally:
        await safe_kill(gateway)
        await safe_kill(backend)

    assert "remote-echo.ping" in tool_names
    assert text == "remote-sse:sse"


@pytest.mark.asyncio
async def test_gateway_streamable_http_transport() -> None:
    backend = await asyncio.create_subprocess_exec(
        sys.executable,
        "tests/tools/echo_server.py",
        "--name",
        "remote-stream",
        "--transport",
        "streamable-http",
        "--port",
        "9091",
        cwd=str(ROOT),
    )
    gateway = None
    try:
        await wait_for_port(9091)
        gateway = await asyncio.create_subprocess_exec(
            sys.executable,
            "main.py",
            "--config",
            STREAMABLE_BACKEND_CONFIG,
            "--transport",
            "streamable-http",
            cwd=str(ROOT),
        )
        await wait_for_port(8080)
        async with streamable_http_client("http://127.0.0.1:8080/mcp") as transport:
            read_stream, write_stream, _ = transport
            async with ClientSession(read_stream, write_stream) as session:
                tool_names, text = await initialize_and_call_ping(session, "streamable")
    finally:
        await safe_kill(gateway)
        await safe_kill(backend)

    assert "remote-echo.ping" in tool_names
    assert text == "remote-stream:streamable"

