# MCP Gateway

**English** | [简体中文](README.zh-CN.md)

MCP Gateway is a lightweight MCP aggregation proxy. It merges multiple backend MCP Servers into a single unified endpoint, exposing one MCP service externally while preserving tool namespace isolation to prevent name collisions across backends.

## Features

- Aggregate multiple backend MCP Servers behind one endpoint
- Backend transport support: `stdio` / `sse` / `streamable-http`
- Gateway transport support: `stdio` / `sse` / `streamable-http`
- Built-in HTTP management API: `/health`, `/servers`, `/tools`
- Managed with `uv` for virtual environments and dependencies

## Installation

```bash
uv sync --extra dev
```

This will:

- Create a `.venv` virtual environment
- Install development dependencies
- Resolve and lock dependency versions

Current pinned MCP Python SDK version: `mcp==1.27.1`.

## Usage

### 1. Run gateway in stdio mode

```bash
uv run python main.py --config ./examples/config/servers.json
```

### 2. Run gateway in SSE mode

```bash
uv run python main.py --transport sse --config ./examples/config/sse-backend.json
```

Default listen address: `http://127.0.0.1:8080/sse`

### 3. Run gateway in Streamable HTTP mode

```bash
uv run python main.py --transport streamable-http --config ./examples/config/streamable-http-backend.json
```

Default listen address: `http://127.0.0.1:8080/mcp`

## Configuration

Configuration files use a unified format:

```json
{
  "mcpServers": {
    "server-name": {
      "transport": "stdio | sse | streamable-http",
      "command": "python",
      "args": ["./server.py"],
      "url": "http://127.0.0.1:9000/sse",
      "headers": {
        "Authorization": "Bearer ..."
      }
    }
  }
}
```

### stdio backend example

```json
{
  "mcpServers": {
    "calculator": {
      "transport": "stdio",
      "command": "python",
      "args": ["./tests/tools/calculator.py"]
    },
    "echo": {
      "transport": "stdio",
      "command": "python",
      "args": ["./tests/tools/echo_server.py", "--name", "echo"]
    }
  }
}
```

See: [examples/config/servers.json](examples/config/servers.json)

### SSE backend example

```json
{
  "mcpServers": {
    "remote-echo": {
      "transport": "sse",
      "url": "http://127.0.0.1:9090/sse"
    }
  }
}
```

See: [examples/config/sse-backend.json](examples/config/sse-backend.json)

### Streamable HTTP backend example

```json
{
  "mcpServers": {
    "remote-echo": {
      "transport": "streamable-http",
      "url": "http://127.0.0.1:9091/mcp"
    }
  }
}
```

See: [examples/config/streamable-http-backend.json](examples/config/streamable-http-backend.json)

## Tool Namespace

The gateway rewrites tool names using the pattern:

```text
<server_name>.<tool_name>
```

For example:

- `calculator.add`
- `calculator.multiply`
- `remote-echo.ping`

This allows safe aggregation of multiple backends that may expose tools with identical names.

## HTTP Management API

When the gateway runs in `sse` or `streamable-http` mode, it additionally exposes:

- `GET /health`
- `GET /servers`
- `POST /servers`
- `DELETE /servers/{name}`
- `GET /tools`

The `POST /servers` request body follows the same format as the main configuration file.

## Project Structure

```text
main.py
src/mcp_gateway/
examples/config/
tests/
```

Where:

- [main.py](main.py) — unified entry point
- [src/mcp_gateway/app.py](src/mcp_gateway/app.py) — gateway lifecycle and HTTP service
- [src/mcp_gateway/clients.py](src/mcp_gateway/clients.py) — backend connection management
- [src/mcp_gateway/proxy.py](src/mcp_gateway/proxy.py) — MCP request routing and aggregation

## Testing

```bash
uv run pytest -q
```

Current test coverage:

- Proxy tool aggregation and routing
- SSE gateway transport
- Streamable HTTP gateway transport
- Streamable HTTP backend connectivity

> **Note:** On Windows sandbox environments, process-level `stdio` end-to-end tests are automatically skipped due to named pipe permission restrictions. The logic layer is still covered by unit tests.
