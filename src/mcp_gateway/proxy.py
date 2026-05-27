from __future__ import annotations

from dataclasses import dataclass

from mcp import server, types
from mcp.client.session import ClientSession

from src.mcp_gateway.clients import MCPClientManager
from src.mcp_gateway.logging import get_logger


@dataclass
class ToolRoute:
    server_name: str
    remote_name: str
    client: ClientSession
    tool: types.Tool


@dataclass
class PromptRoute:
    server_name: str
    remote_name: str
    client: ClientSession


class MCPGatewayProxy(server.Server):
    def __init__(self, client_manager: MCPClientManager, name: str = "MCP Gateway") -> None:
        super().__init__(name)
        self.client_manager = client_manager
        self.logger = get_logger("proxy")
        self.capabilities: dict[str, types.ServerCapabilities] = {}
        self.tool_routes: dict[str, ToolRoute] = {}
        self.prompt_routes: dict[str, PromptRoute] = {}
        self.resource_routes: dict[str, ClientSession] = {}
        self.resource_template_routes: dict[str, ClientSession] = {}
        self._register_handlers()

    @classmethod
    async def create(
        cls,
        client_manager: MCPClientManager,
        name: str = "MCP Gateway",
    ) -> "MCPGatewayProxy":
        proxy = cls(client_manager=client_manager, name=name)
        await proxy.refresh_all_clients()
        return proxy

    async def refresh_all_clients(self) -> None:
        self.tool_routes.clear()
        self.prompt_routes.clear()
        self.resource_routes.clear()
        self.resource_template_routes.clear()
        self.capabilities.clear()

        for server_name, client in self.client_manager.clients.items():
            await self.register_client(server_name, client)

    async def register_client(self, server_name: str, client: ClientSession) -> None:
        result = await client.initialize()
        self.capabilities[server_name] = result.capabilities
        await self._refresh_routes_for_client(server_name, client)

    async def unregister_client(self, server_name: str) -> None:
        self.capabilities.pop(server_name, None)
        self.tool_routes = {
            key: value
            for key, value in self.tool_routes.items()
            if value.server_name != server_name
        }
        self.prompt_routes = {
            key: value
            for key, value in self.prompt_routes.items()
            if value.server_name != server_name
        }
        self.resource_routes = {
            key: value
            for key, value in self.resource_routes.items()
            if self._client_name(value) != server_name
        }
        self.resource_template_routes = {
            key: value
            for key, value in self.resource_template_routes.items()
            if self._client_name(value) != server_name
        }

    async def list_server_tools(self) -> dict[str, list[str]]:
        tools_by_server: dict[str, list[str]] = {}
        for server_name, client in self.client_manager.clients.items():
            tools = await client.list_tools()
            tools_by_server[server_name] = [
                self.scoped_name(server_name, tool.name) for tool in tools.tools
            ]
        return tools_by_server

    async def _refresh_routes_for_client(self, server_name: str, client: ClientSession) -> None:
        self.tool_routes = {
            key: value
            for key, value in self.tool_routes.items()
            if value.server_name != server_name
        }
        self.prompt_routes = {
            key: value
            for key, value in self.prompt_routes.items()
            if value.server_name != server_name
        }
        self.resource_routes = {
            key: value
            for key, value in self.resource_routes.items()
            if self._client_name(value) != server_name
        }
        self.resource_template_routes = {
            key: value
            for key, value in self.resource_template_routes.items()
            if self._client_name(value) != server_name
        }

        capabilities = self.capabilities.get(server_name)
        if capabilities is None:
            return

        if capabilities.tools is not None:
            await self._load_tool_routes(server_name, client)
        if capabilities.prompts is not None:
            await self._load_prompt_routes(server_name, client)
        if capabilities.resources is not None:
            await self._load_resource_routes(server_name, client)

    async def _load_tool_routes(self, server_name: str, client: ClientSession) -> None:
        result = await client.list_tools()
        for tool in result.tools:
            scoped_name = self.scoped_name(server_name, tool.name)
            scoped_tool = tool.model_copy(deep=True)
            scoped_tool.name = scoped_name
            self.tool_routes[scoped_name] = ToolRoute(
                server_name=server_name,
                remote_name=tool.name,
                client=client,
                tool=scoped_tool,
            )

    async def _load_prompt_routes(self, server_name: str, client: ClientSession) -> None:
        result = await client.list_prompts()
        for prompt in result.prompts:
            self.prompt_routes[self.scoped_name(server_name, prompt.name)] = PromptRoute(
                server_name=server_name,
                remote_name=prompt.name,
                client=client,
            )

    async def _load_resource_routes(self, server_name: str, client: ClientSession) -> None:
        resources = await client.list_resources()
        for resource in resources.resources:
            self.resource_routes[str(resource.uri)] = client

        try:
            templates = await client.list_resource_templates()
        except Exception as exc:
            self.logger.debug("Backend '%s' has no resource templates: %s", server_name, exc)
            return

        for template in templates.resourceTemplates:
            self.resource_template_routes[template.uriTemplate] = client

    async def _list_tools(self, _: types.ListToolsRequest) -> types.ServerResult:
        tools: list[types.Tool] = []

        for server_name, client in self.client_manager.clients.items():
            capabilities = self.capabilities.get(server_name)
            if capabilities is None or capabilities.tools is None:
                continue
            await self._load_tool_routes(server_name, client)

        for route in self.tool_routes.values():
            tools.append(route.tool)

        return types.ServerResult(
            types.ListToolsResult(tools=sorted(tools, key=lambda tool: tool.name))
        )

    async def _call_tool(self, request: types.CallToolRequest) -> types.ServerResult:
        route = self.tool_routes.get(request.params.name)
        if route is None:
            return self._make_error_result(f"Unknown tool '{request.params.name}'.")

        result = await route.client.call_tool(
            route.remote_name,
            request.params.arguments or {},
            meta=request.params.meta.model_dump(by_alias=True) if request.params.meta else None,
        )
        return types.ServerResult(result)

    async def _list_prompts(self, _: types.ListPromptsRequest) -> types.ServerResult:
        prompts: list[types.Prompt] = []

        for server_name, client in self.client_manager.clients.items():
            capabilities = self.capabilities.get(server_name)
            if capabilities is None or capabilities.prompts is None:
                continue

            result = await client.list_prompts()
            for prompt in result.prompts:
                scoped_prompt = prompt.model_copy(deep=True)
                scoped_prompt.name = self.scoped_name(server_name, prompt.name)
                prompts.append(scoped_prompt)
                self.prompt_routes[scoped_prompt.name] = PromptRoute(
                    server_name=server_name,
                    remote_name=prompt.name,
                    client=client,
                )

        return types.ServerResult(
            types.ListPromptsResult(prompts=sorted(prompts, key=lambda prompt: prompt.name))
        )

    async def _get_prompt(self, request: types.GetPromptRequest) -> types.ServerResult:
        route = self.prompt_routes.get(request.params.name)
        if route is None:
            return types.ServerResult(
                types.GetPromptResult(
                    description=f"Unknown prompt '{request.params.name}'.",
                    messages=[],
                )
            )

        result = await route.client.get_prompt(
            route.remote_name,
            arguments=request.params.arguments,
        )
        return types.ServerResult(result)

    async def _complete(self, request: types.CompleteRequest) -> types.ServerResult:
        ref = request.params.ref

        if isinstance(ref, types.PromptReference):
            route = self.prompt_routes.get(ref.name)
            if route is None:
                return types.ServerResult(
                    types.CompleteResult(
                        completion=types.Completion(values=[], total=None, hasMore=False)
                    )
                )

            remote_ref = types.PromptReference(type="ref/prompt", name=route.remote_name)
            result = await route.client.complete(
                remote_ref,
                request.params.argument.model_dump(),
                context_arguments=request.params.context.arguments if request.params.context else None,
            )
            return types.ServerResult(result)

        client = self.resource_routes.get(str(ref.uri)) or self.resource_template_routes.get(
            str(ref.uri)
        )
        if client is None:
            return types.ServerResult(
                types.CompleteResult(
                    completion=types.Completion(values=[], total=None, hasMore=False)
                )
            )

        result = await client.complete(
            ref,
            request.params.argument.model_dump(),
            context_arguments=request.params.context.arguments if request.params.context else None,
        )
        return types.ServerResult(result)

    async def _list_resources(self, _: types.ListResourcesRequest) -> types.ServerResult:
        resources: list[types.Resource] = []

        for server_name, client in self.client_manager.clients.items():
            capabilities = self.capabilities.get(server_name)
            if capabilities is None or capabilities.resources is None:
                continue

            result = await client.list_resources()
            for resource in result.resources:
                scoped_resource = resource.model_copy(deep=True)
                scoped_resource.name = self.scoped_name(server_name, resource.name)
                resources.append(scoped_resource)
                self.resource_routes[str(resource.uri)] = client

        return types.ServerResult(types.ListResourcesResult(resources=resources))

    async def _list_resource_templates(
        self,
        _: types.ListResourceTemplatesRequest,
    ) -> types.ServerResult:
        templates: list[types.ResourceTemplate] = []

        for server_name, client in self.client_manager.clients.items():
            capabilities = self.capabilities.get(server_name)
            if capabilities is None or capabilities.resources is None:
                continue

            try:
                result = await client.list_resource_templates()
            except Exception:
                continue

            for template in result.resourceTemplates:
                scoped_template = template.model_copy(deep=True)
                scoped_template.name = self.scoped_name(server_name, template.name)
                templates.append(scoped_template)
                self.resource_template_routes[template.uriTemplate] = client

        return types.ServerResult(
            types.ListResourceTemplatesResult(resourceTemplates=templates)
        )

    async def _read_resource(self, request: types.ReadResourceRequest) -> types.ServerResult:
        client = self.resource_routes.get(str(request.params.uri))
        if client is None:
            return types.ServerResult(types.ReadResourceResult(contents=[]))

        result = await client.read_resource(request.params.uri)
        return types.ServerResult(result)

    async def _subscribe_resource(self, request: types.SubscribeRequest) -> types.ServerResult:
        client = self.resource_routes.get(str(request.params.uri))
        if client is None:
            return types.ServerResult(types.EmptyResult())

        result = await client.subscribe_resource(request.params.uri)
        return types.ServerResult(result)

    async def _unsubscribe_resource(self, request: types.UnsubscribeRequest) -> types.ServerResult:
        client = self.resource_routes.get(str(request.params.uri))
        if client is None:
            return types.ServerResult(types.EmptyResult())

        result = await client.unsubscribe_resource(request.params.uri)
        return types.ServerResult(result)

    async def _set_logging_level(self, request: types.SetLevelRequest) -> types.ServerResult:
        for client in self.client_manager.clients.values():
            try:
                await client.set_logging_level(request.params.level)
            except Exception as exc:
                self.logger.warning("Failed to propagate log level: %s", exc)

        return types.ServerResult(types.EmptyResult())

    async def _send_progress_notification(self, request: types.ProgressNotification) -> None:
        for client in self.client_manager.clients.values():
            try:
                await client.send_progress_notification(
                    request.params.progressToken,
                    request.params.progress,
                    request.params.total,
                )
            except Exception as exc:
                self.logger.warning("Failed to forward progress notification: %s", exc)

    def _register_handlers(self) -> None:
        self.request_handlers[types.ListToolsRequest] = self._list_tools
        self.request_handlers[types.CallToolRequest] = self._call_tool
        self.request_handlers[types.ListPromptsRequest] = self._list_prompts
        self.request_handlers[types.GetPromptRequest] = self._get_prompt
        self.request_handlers[types.CompleteRequest] = self._complete
        self.request_handlers[types.ListResourcesRequest] = self._list_resources
        self.request_handlers[types.ListResourceTemplatesRequest] = self._list_resource_templates
        self.request_handlers[types.ReadResourceRequest] = self._read_resource
        self.request_handlers[types.SubscribeRequest] = self._subscribe_resource
        self.request_handlers[types.UnsubscribeRequest] = self._unsubscribe_resource
        self.request_handlers[types.SetLevelRequest] = self._set_logging_level
        self.notification_handlers[types.ProgressNotification] = self._send_progress_notification

    @staticmethod
    def scoped_name(server_name: str, item_name: str) -> str:
        return f"{server_name}.{item_name}"

    def _client_name(self, client: ClientSession) -> str | None:
        for server_name, session in self.client_manager.clients.items():
            if session is client:
                return server_name
        return None
