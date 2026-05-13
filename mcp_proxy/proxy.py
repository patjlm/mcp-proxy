from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import mcp.server.stdio
from mcp import ClientSession, McpError, types
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import Server

from .config import Config, HttpUpstream, StdioUpstream, ToolsConfig
from .oauth import create_oauth_provider


def _is_tool_allowed(name: str, tools_config: ToolsConfig) -> bool:
    if tools_config.whitelist:
        return name in tools_config.whitelist
    if tools_config.blacklist:
        return name not in tools_config.blacklist
    return True


def _apply_overrides(tool: types.Tool, tools_config: ToolsConfig) -> types.Tool:
    override = tools_config.overrides.get(tool.name)
    if override:
        tool = tool.model_copy(update={"description": override.description})
    return tool


def _build_server(upstream: ClientSession, config: Config) -> Server:
    app = Server(name="mcp-proxy-filter")

    async def _list_tools(_: Any) -> types.ServerResult:
        result = await upstream.list_tools()
        filtered = [
            _apply_overrides(t, config.tools)
            for t in result.tools
            if _is_tool_allowed(t.name, config.tools)
        ]
        return types.ServerResult(types.ListToolsResult(tools=filtered))

    async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
        if not _is_tool_allowed(req.params.name, config.tools):
            raise McpError(
                error=types.ErrorData(
                    code=types.INVALID_PARAMS,
                    message=f"Tool '{req.params.name}' is not available",
                )
            )
        result = await upstream.call_tool(req.params.name, req.params.arguments or {})
        return types.ServerResult(result)

    app.request_handlers[types.ListToolsRequest] = _list_tools
    app.request_handlers[types.CallToolRequest] = _call_tool

    async def _list_prompts(_: Any) -> types.ServerResult:
        result = await upstream.list_prompts()
        return types.ServerResult(result)

    async def _get_prompt(req: types.GetPromptRequest) -> types.ServerResult:
        result = await upstream.get_prompt(req.params.name, req.params.arguments)
        return types.ServerResult(result)

    app.request_handlers[types.ListPromptsRequest] = _list_prompts
    app.request_handlers[types.GetPromptRequest] = _get_prompt

    async def _list_resources(_: Any) -> types.ServerResult:
        result = await upstream.list_resources()
        return types.ServerResult(result)

    async def _read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
        result = await upstream.read_resource(req.params.uri)
        return types.ServerResult(result)

    async def _list_resource_templates(_: Any) -> types.ServerResult:
        result = await upstream.list_resource_templates()
        return types.ServerResult(result)

    app.request_handlers[types.ListResourcesRequest] = _list_resources
    app.request_handlers[types.ReadResourceRequest] = _read_resource
    app.request_handlers[types.ListResourceTemplatesRequest] = _list_resource_templates

    return app


def _token_file_for_url(url: str) -> Path:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return Path.home() / ".cache" / "mcp-proxy-filter" / f"oauth-{url_hash}.json"


@asynccontextmanager
async def _connect_upstream(config: Config):
    if isinstance(config.upstream, HttpUpstream):
        if config.upstream.headers:
            auth = None
            headers = config.upstream.headers
        else:
            auth = create_oauth_provider(
                config.upstream.url, _token_file_for_url(config.upstream.url)
            )
            headers = {}

        http_client = httpx.AsyncClient(headers=headers, auth=auth)
        async with http_client:
            async with streamable_http_client(
                config.upstream.url, http_client=http_client
            ) as (read, write, _get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    elif isinstance(config.upstream, StdioUpstream):
        params = StdioServerParameters(
            command=config.upstream.command,
            args=config.upstream.args,
            env=config.upstream.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        raise ValueError(f"Unknown upstream type: {type(config.upstream)}")


async def run_proxy(config: Config) -> None:
    async with _connect_upstream(config) as upstream_session:
        app = _build_server(upstream_session, config)
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
