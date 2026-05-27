from __future__ import annotations

import argparse
import asyncio

from src.mcp_gateway.app import MCPGatewayApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MCP Gateway proxy server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport used by the gateway server itself.",
    )
    parser.add_argument(
        "--config",
        default="./examples/config/servers.json",
        help="Path to the backend MCP server config JSON file.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host for SSE/streamable-http.")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port for SSE/streamable-http.")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level.",
    )
    parser.add_argument("--name", default="MCP Gateway", help="Gateway server name shown to clients.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = MCPGatewayApp(
        transport=args.transport,
        config=args.config,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        name=args.name,
    )
    asyncio.run(app.run())
