import re

import pytest
from mcp import types

from mcp_proxy.config import ToolOverride, ToolsConfig
from mcp_proxy.proxy import _apply_overrides, _is_tool_allowed, _token_file_for_url


def _make_tool(name="myTool", description="A tool", properties=None, required=None):
    props = properties or {"id": {"type": "string"}}
    req = required or ["id"]
    return types.Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": props, "required": req},
    )


# --- _is_tool_allowed ---


def test_allowed_default_config():
    cfg = ToolsConfig()
    assert _is_tool_allowed("anything", cfg) is True


def test_blacklist_blocks_listed():
    cfg = ToolsConfig(blacklist=["secret_tool"])
    assert _is_tool_allowed("secret_tool", cfg) is False


def test_blacklist_allows_unlisted():
    cfg = ToolsConfig(blacklist=["secret_tool"])
    assert _is_tool_allowed("public_tool", cfg) is True


def test_whitelist_allows_listed():
    cfg = ToolsConfig(whitelist=["allowed"])
    assert _is_tool_allowed("allowed", cfg) is True


def test_whitelist_blocks_unlisted():
    cfg = ToolsConfig(whitelist=["allowed"])
    assert _is_tool_allowed("other", cfg) is False


# --- _apply_overrides ---


def test_no_override_returns_unchanged():
    tool = _make_tool()
    cfg = ToolsConfig()
    result = _apply_overrides(tool, cfg)
    assert result is tool


def test_description_override():
    tool = _make_tool(description="Original")
    cfg = ToolsConfig(overrides={"myTool": ToolOverride(description="Overridden")})
    result = _apply_overrides(tool, cfg)
    assert result.description == "Overridden"
    assert result.inputSchema == tool.inputSchema


def test_disabled_parameters_removes_optional():
    tool = _make_tool(
        properties={"id": {"type": "string"}, "verbose": {"type": "boolean"}},
        required=["id"],
    )
    cfg = ToolsConfig(overrides={"myTool": ToolOverride(disabled_parameters=["verbose"])})
    result = _apply_overrides(tool, cfg)
    assert "verbose" not in result.inputSchema["properties"]
    assert "id" in result.inputSchema["properties"]


def test_disabled_parameters_skips_required():
    tool = _make_tool(
        properties={"id": {"type": "string"}, "name": {"type": "string"}},
        required=["id", "name"],
    )
    cfg = ToolsConfig(overrides={"myTool": ToolOverride(disabled_parameters=["name"])})
    result = _apply_overrides(tool, cfg)
    assert "name" in result.inputSchema["properties"]


def test_disabled_parameters_with_description():
    tool = _make_tool(
        description="Original",
        properties={"id": {"type": "string"}, "debug": {"type": "boolean"}},
        required=["id"],
    )
    cfg = ToolsConfig(
        overrides={"myTool": ToolOverride(description="Overridden", disabled_parameters=["debug"])}
    )
    result = _apply_overrides(tool, cfg)
    assert result.description == "Overridden"
    assert "debug" not in result.inputSchema["properties"]


def test_disabled_parameters_nonexistent_param(caplog):
    tool = _make_tool()
    cfg = ToolsConfig(overrides={"myTool": ToolOverride(disabled_parameters=["nosuch"])})
    result = _apply_overrides(tool, cfg)
    assert "id" in result.inputSchema["properties"]
    assert "does not exist" in caplog.text


# --- _token_file_for_url ---


def test_token_file_deterministic():
    a = _token_file_for_url("https://example.com")
    b = _token_file_for_url("https://example.com")
    assert a == b


def test_token_file_different_urls_differ():
    a = _token_file_for_url("https://example.com")
    b = _token_file_for_url("https://other.com")
    assert a != b


def test_token_file_path_structure():
    path = _token_file_for_url("https://example.com")
    assert path.parent.name == "mcp-proxy-filter"
    assert re.match(r"oauth-[0-9a-f]{12}\.json", path.name)
