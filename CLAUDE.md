# mcp-proxy-filter

Python MCP proxy. Filters tools from an upstream MCP server (HTTP or stdio) and exposes them via stdio.

- Entry point: `mcp_proxy/main.py`
- Config loader: `mcp_proxy/config.py` — YAML config from `MCP_PROXY_CONFIG` env var
- Proxy logic: `mcp_proxy/proxy.py` — upstream client + filtered stdio server
- OAuth: `mcp_proxy/oauth.py` — token storage + browser redirect flow
- Example config: `config.example.yaml` — Atlassian Rovo Jira-only whitelist

## Development

- Use `uv` as package manager, never `pip` directly
- Install dev deps: `uv pip install -e ".[dev]"`
- Run tests: `uv run pytest tests/ -v`
