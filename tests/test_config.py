import pytest
import yaml

from mcp_proxy.config import (
    Config,
    HttpUpstream,
    StdioUpstream,
    ToolOverride,
    ToolsConfig,
    _expand_env,
    _expand_env_in_dict,
    _parse_tools,
    _parse_upstream,
    load_config,
)


# --- _expand_env ---


def test_expand_env_simple(monkeypatch):
    monkeypatch.setenv("TEST_VAR_ABC", "hello")
    assert _expand_env("${TEST_VAR_ABC}") == "hello"


def test_expand_env_multiple_vars(monkeypatch):
    monkeypatch.setenv("A_VAR", "foo")
    monkeypatch.setenv("B_VAR", "bar")
    assert _expand_env("${A_VAR}-${B_VAR}") == "foo-bar"


def test_expand_env_no_vars():
    assert _expand_env("plain string") == "plain string"


def test_expand_env_missing_var_raises(monkeypatch):
    monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
    with pytest.raises(ValueError, match="NONEXISTENT_VAR_XYZ"):
        _expand_env("${NONEXISTENT_VAR_XYZ}")


# --- _expand_env_in_dict ---


def test_expand_env_in_dict(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret")
    result = _expand_env_in_dict({"auth": "${MY_TOKEN}", "plain": "value"})
    assert result == {"auth": "secret", "plain": "value"}


# --- _parse_upstream ---


def test_parse_http_upstream():
    result = _parse_upstream({"type": "http", "url": "https://example.com"})
    assert isinstance(result, HttpUpstream)
    assert result.url == "https://example.com"
    assert result.headers == {}


def test_parse_http_upstream_with_headers(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "bearer-xyz")
    result = _parse_upstream({
        "type": "http",
        "url": "https://example.com",
        "headers": {"Authorization": "${AUTH_TOKEN}"},
    })
    assert result.headers == {"Authorization": "bearer-xyz"}


def test_parse_http_upstream_missing_url():
    with pytest.raises(ValueError, match="url"):
        _parse_upstream({"type": "http"})


def test_parse_stdio_upstream():
    result = _parse_upstream({"type": "stdio", "command": "node", "args": ["server.js"]})
    assert isinstance(result, StdioUpstream)
    assert result.command == "node"
    assert result.args == ["server.js"]


def test_parse_stdio_upstream_missing_command():
    with pytest.raises(ValueError, match="command"):
        _parse_upstream({"type": "stdio"})


def test_parse_upstream_invalid_type():
    with pytest.raises(ValueError, match="grpc"):
        _parse_upstream({"type": "grpc"})


def test_parse_upstream_no_type():
    with pytest.raises(ValueError, match="None"):
        _parse_upstream({})


def test_parse_stdio_upstream_args_not_list():
    with pytest.raises(ValueError, match="args must be a list"):
        _parse_upstream({"type": "stdio", "command": "x", "args": "bad"})


def test_parse_stdio_upstream_env_not_dict():
    with pytest.raises(ValueError, match="env must be a mapping"):
        _parse_upstream({"type": "stdio", "command": "x", "env": "bad"})


# --- _parse_tools ---


def test_parse_tools_none():
    result = _parse_tools(None)
    assert result.blacklist == []
    assert result.whitelist == []
    assert result.overrides == {}


def test_parse_tools_empty_dict():
    result = _parse_tools({})
    assert result.blacklist == []
    assert result.whitelist == []


def test_parse_tools_blacklist():
    result = _parse_tools({"blacklist": ["a", "b"]})
    assert result.blacklist == ["a", "b"]
    assert result.whitelist == []


def test_parse_tools_whitelist():
    result = _parse_tools({"whitelist": ["x"]})
    assert result.whitelist == ["x"]
    assert result.blacklist == []


def test_parse_tools_mutual_exclusion():
    with pytest.raises(ValueError, match="mutually exclusive"):
        _parse_tools({"blacklist": ["a"], "whitelist": ["b"]})


def test_parse_tools_overrides():
    result = _parse_tools({
        "overrides": {
            "myTool": {
                "description": "Short desc",
                "disabled_parameters": ["verbose"],
            }
        }
    })
    assert "myTool" in result.overrides
    assert result.overrides["myTool"].description == "Short desc"
    assert result.overrides["myTool"].disabled_parameters == ["verbose"]


def test_parse_tools_override_empty_raises():
    with pytest.raises(ValueError, match="at least"):
        _parse_tools({"overrides": {"myTool": {}}})


def test_parse_tools_blacklist_not_strings():
    with pytest.raises(ValueError, match="list of strings"):
        _parse_tools({"blacklist": [1, 2]})


# --- load_config ---


def test_load_config_success(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "upstream": {"type": "http", "url": "https://example.com"},
        "tools": {"whitelist": ["getThing"]},
    }))
    monkeypatch.setenv("MCP_PROXY_CONFIG", str(config_file))
    cfg = load_config()
    assert isinstance(cfg.upstream, HttpUpstream)
    assert cfg.upstream.url == "https://example.com"
    assert cfg.tools.whitelist == ["getThing"]


def test_load_config_env_not_set(monkeypatch):
    monkeypatch.delenv("MCP_PROXY_CONFIG", raising=False)
    with pytest.raises(ValueError, match="MCP_PROXY_CONFIG"):
        load_config()


def test_load_config_file_not_found(monkeypatch):
    monkeypatch.setenv("MCP_PROXY_CONFIG", "/nonexistent/path.yaml")
    with pytest.raises(ValueError, match="not found"):
        load_config()


def test_load_config_invalid_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "bad.yaml"
    config_file.write_text(": : : bad")
    monkeypatch.setenv("MCP_PROXY_CONFIG", str(config_file))
    with pytest.raises(ValueError, match="parse"):
        load_config()


def test_load_config_not_a_mapping(tmp_path, monkeypatch):
    config_file = tmp_path / "list.yaml"
    config_file.write_text("- item\n- item2\n")
    monkeypatch.setenv("MCP_PROXY_CONFIG", str(config_file))
    with pytest.raises(ValueError, match="mapping"):
        load_config()


def test_load_config_missing_upstream(tmp_path, monkeypatch):
    config_file = tmp_path / "no_upstream.yaml"
    config_file.write_text(yaml.dump({"tools": {"blacklist": []}}))
    monkeypatch.setenv("MCP_PROXY_CONFIG", str(config_file))
    with pytest.raises(ValueError, match="upstream"):
        load_config()
