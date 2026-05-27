from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Echo")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    return parser.parse_args()


args = parse_args()
mcp = FastMCP(args.name, host=args.host, port=args.port)


@mcp.tool()
def ping(message: str) -> str:
    return f"{args.name}:{message}"


@mcp.tool()
def server_name() -> str:
    return args.name


if __name__ == "__main__":
    mcp.run(transport=args.transport)
