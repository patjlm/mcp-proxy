from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class HttpUpstream:
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class StdioUpstream:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class ToolOverride:
    description: str | None = None
    disabled_parameters: list[str] = field(default_factory=list)


@dataclass
class ToolsConfig:
    blacklist: list[str] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)
    overrides: dict[str, ToolOverride] = field(default_factory=dict)


@dataclass
class Config:
    upstream: HttpUpstream | StdioUpstream
    tools: ToolsConfig = field(default_factory=ToolsConfig)


_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    def replace(match: re.Match) -> str:
        var = match.group(1)
        result = os.environ.get(var)
        if result is None:
            raise ValueError(f"Environment variable '{var}' referenced in config is not set")
        return result

    return _ENV_VAR_RE.sub(replace, value)


def _expand_env_in_dict(d: dict[str, str]) -> dict[str, str]:
    return {k: _expand_env(v) for k, v in d.items()}


def _parse_upstream(raw: dict) -> HttpUpstream | StdioUpstream:
    upstream_type = raw.get("type")
    if upstream_type == "http":
        url = raw.get("url")
        if not url:
            raise ValueError("upstream.url is required for http upstream")
        headers = _expand_env_in_dict(raw.get("headers") or {})
        return HttpUpstream(url=url, headers=headers)

    if upstream_type == "stdio":
        command = raw.get("command")
        if not command:
            raise ValueError("upstream.command is required for stdio upstream")
        args = raw.get("args") or []
        if not isinstance(args, list):
            raise ValueError("upstream.args must be a list")
        env = raw.get("env") or {}
        if not isinstance(env, dict):
            raise ValueError("upstream.env must be a mapping")
        return StdioUpstream(command=command, args=args, env=env)

    raise ValueError(f"upstream.type must be 'http' or 'stdio', got {upstream_type!r}")


def _parse_tools(raw: dict | None) -> ToolsConfig:
    if not raw:
        return ToolsConfig()

    blacklist = raw.get("blacklist") or []
    whitelist = raw.get("whitelist") or []

    if blacklist and whitelist:
        raise ValueError("tools.blacklist and tools.whitelist are mutually exclusive")

    if not isinstance(blacklist, list) or not all(isinstance(x, str) for x in blacklist):
        raise ValueError("tools.blacklist must be a list of strings")
    if not isinstance(whitelist, list) or not all(isinstance(x, str) for x in whitelist):
        raise ValueError("tools.whitelist must be a list of strings")

    raw_overrides = raw.get("overrides") or {}
    if not isinstance(raw_overrides, dict):
        raise ValueError("tools.overrides must be a mapping")

    overrides: dict[str, ToolOverride] = {}
    for tool_name, override_raw in raw_overrides.items():
        if not isinstance(override_raw, dict):
            raise ValueError(f"tools.overrides.{tool_name} must be a mapping")

        description = override_raw.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError(f"tools.overrides.{tool_name}.description must be a string")

        disabled_parameters = override_raw.get("disabled_parameters") or []
        if not isinstance(disabled_parameters, list) or not all(
            isinstance(p, str) for p in disabled_parameters
        ):
            raise ValueError(
                f"tools.overrides.{tool_name}.disabled_parameters must be a list of strings"
            )

        if description is None and not disabled_parameters:
            raise ValueError(
                f"tools.overrides.{tool_name} must have at least 'description' or 'disabled_parameters'"
            )

        overrides[tool_name] = ToolOverride(
            description=description, disabled_parameters=disabled_parameters
        )

    return ToolsConfig(blacklist=blacklist, whitelist=whitelist, overrides=overrides)


def load_config() -> Config:
    config_path = os.environ.get("MCP_PROXY_CONFIG")
    if not config_path:
        raise ValueError("MCP_PROXY_CONFIG environment variable is not set")

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ValueError(f"Config file not found: {config_path}")
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse config YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Config file must be a YAML mapping at the top level")

    upstream_raw = raw.get("upstream")
    if not upstream_raw:
        raise ValueError("'upstream' section is required in config")
    if not isinstance(upstream_raw, dict):
        raise ValueError("'upstream' must be a mapping")

    upstream = _parse_upstream(upstream_raw)
    tools = _parse_tools(raw.get("tools"))

    return Config(upstream=upstream, tools=tools)
