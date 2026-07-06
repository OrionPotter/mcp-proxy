from __future__ import annotations

import json
from pathlib import Path

from src.mcp_gateway.config import GatewayConfig


def test_load_resolves_stdio_relative_paths_against_config_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "servers.json"
    payload = {
        "mcpServers": {
            "echo": {
                "transport": "stdio",
                "command": "./bin/python",
                "args": ["./tools/echo_server.py", "--name", "echo"],
                "cwd": "./workspace",
            }
        }
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = GatewayConfig.load(config_path)
    server = config.mcpServers["echo"]

    assert Path(server.command) == (config_dir / "bin" / "python").resolve()
    assert Path(server.args[0]) == (config_dir / "tools" / "echo_server.py").resolve()
    assert server.args[1:] == ["--name", "echo"]
    assert Path(server.cwd) == (config_dir / "workspace").resolve()
