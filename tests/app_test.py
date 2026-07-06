from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.testclient import TestClient

from src.mcp_gateway.app import MCPGatewayApp


def create_http_client() -> TestClient:
    gateway = MCPGatewayApp(transport="sse")
    gateway.proxy = SimpleNamespace(register_client=AsyncMock(), list_server_tools=AsyncMock(return_value={}))
    return TestClient(gateway._build_http_app())


def test_servers_endpoint_rejects_invalid_json() -> None:
    with create_http_client() as client:
        response = client.post(
            "/servers",
            content="{",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid JSON payload: Expecting property name enclosed in double quotes."


def test_servers_endpoint_rejects_invalid_schema() -> None:
    with create_http_client() as client:
        response = client.post("/servers", json={"servers": {}})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "Invalid server configuration."
    assert body["details"] == ["At least one server must be provided in 'mcpServers'."]
