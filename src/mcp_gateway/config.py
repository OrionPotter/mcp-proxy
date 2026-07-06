from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ServerTransport = Literal["stdio", "sse", "streamable-http"]
GatewayTransport = Literal["stdio", "sse", "streamable-http"]


class RemoteServerConfig(BaseModel):
    transport: ServerTransport | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    encoding: str = "utf-8"
    encoding_error_handler: Literal["strict", "ignore", "replace"] = "strict"

    @model_validator(mode="after")
    def validate_transport(self) -> "RemoteServerConfig":
        if self.transport is None:
            if self.command:
                self.transport = "stdio"
            elif self.url:
                self.transport = "sse"
            else:
                raise ValueError("Server config must define either 'command' or 'url'.")

        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio transport requires 'command'.")

        if self.transport in {"sse", "streamable-http"} and not self.url:
            raise ValueError(f"{self.transport} transport requires 'url'.")

        return self

    def resolve_relative_paths(self, base_dir: Path) -> "RemoteServerConfig":
        if self.transport != "stdio":
            return self

        if self.command is not None and _looks_like_path(self.command):
            self.command = str((base_dir / self.command).resolve())

        if self.cwd is not None and not Path(self.cwd).is_absolute():
            self.cwd = str((base_dir / self.cwd).resolve())

        self.args = [
            str((base_dir / arg).resolve()) if _looks_like_path(arg) else arg for arg in self.args
        ]
        return self


class GatewayConfig(BaseModel):
    mcpServers: dict[str, RemoteServerConfig] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "GatewayConfig":
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        config = cls.model_validate(json.loads(config_path.read_text(encoding="utf-8")))
        base_dir = config_path.resolve().parent
        for server_config in config.mcpServers.values():
            server_config.resolve_relative_paths(base_dir)
        return config


def _looks_like_path(value: str) -> bool:
    path = Path(value)
    return path.is_absolute() or value.startswith(".") or "/" in value or "\\" in value
