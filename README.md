# MCP Gateway

`MCP Gateway` 是一个精简版 MCP 聚合代理。它把多个后端 MCP Server 合并成一个统一入口，对外暴露单一的 MCP 服务，同时保留工具名空间隔离，避免同名工具冲突。

当前项目只保留核心能力：

- 聚合多个后端 MCP Server
- 支持后端 `stdio` / `sse` / `streamable-http`
- 支持网关自身以 `stdio` / `sse` / `streamable-http` 运行
- 提供基础 HTTP 管理接口：`/health`、`/servers`、`/tools`
- 使用 `uv` 管理虚拟环境和依赖

## 项目名称

原项目已重构并重新命名为 `MCP Gateway`。

这个名字比 `multi-mcp` 更直观，也更符合它的职责：作为多个 MCP 服务的统一网关。

## 安装

```bash
uv sync --extra dev
```

这会：

- 创建 `.venv`
- 安装开发依赖
- 解析并锁定当前依赖版本

当前锁定的 MCP Python SDK 版本为 `mcp==1.27.1`。

## 启动方式

### 1. 以 stdio 方式运行网关

```bash
uv run python main.py --config ./examples/config/servers.json
```

### 2. 以 SSE 方式运行网关

```bash
uv run python main.py --transport sse --config ./examples/config/sse-backend.json
```

默认监听：`http://127.0.0.1:8080/sse`

### 3. 以 Streamable HTTP 方式运行网关

```bash
uv run python main.py --transport streamable-http --config ./examples/config/streamable-http-backend.json
```

默认监听：`http://127.0.0.1:8080/mcp`

## 配置格式

配置文件统一使用：

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

### stdio 后端示例

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

见：[examples/config/servers.json](/D:/Git仓库/multi-mcp/examples/config/servers.json)

### SSE 后端示例

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

见：[examples/config/sse-backend.json](/D:/Git仓库/multi-mcp/examples/config/sse-backend.json)

### Streamable HTTP 后端示例

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

见：[examples/config/streamable-http-backend.json](/D:/Git仓库/multi-mcp/examples/config/streamable-http-backend.json)

## 工具名空间规则

网关会把工具名改写为：

```text
<server_name>.<tool_name>
```

例如：

- `calculator.add`
- `calculator.multiply`
- `remote-echo.ping`

这样可以安全聚合多个存在同名工具的后端。

## HTTP 管理接口

当网关以 `sse` 或 `streamable-http` 方式运行时，会额外提供：

- `GET /health`
- `GET /servers`
- `POST /servers`
- `DELETE /servers/{name}`
- `GET /tools`

`POST /servers` 的请求体与主配置文件格式一致。

## 目录结构

```text
main.py
src/mcp_gateway/
examples/config/
tests/
```

其中：

- [main.py](/D:/Git仓库/multi-mcp/main.py) 是统一入口
- [src/mcp_gateway/app.py](/D:/Git仓库/multi-mcp/src/mcp_gateway/app.py) 负责网关生命周期和 HTTP 服务
- [src/mcp_gateway/clients.py](/D:/Git仓库/multi-mcp/src/mcp_gateway/clients.py) 负责后端连接管理
- [src/mcp_gateway/proxy.py](/D:/Git仓库/multi-mcp/src/mcp_gateway/proxy.py) 负责 MCP 请求路由与聚合

## 测试

```bash
uv run pytest -q
```

当前测试覆盖：

- 代理工具聚合与路由
- SSE 网关传输
- Streamable HTTP 网关传输
- Streamable HTTP 后端接入

说明：Windows 沙箱环境下，进程级 `stdio` 端到端测试会受到命名管道权限限制，因此测试中会自动跳过该场景；逻辑层仍通过单元测试覆盖。
