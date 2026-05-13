# mcp-proxy-filter

A stdio MCP proxy that filters tools from upstream MCP servers. Reduces context token usage by whitelisting/blacklisting tools and optionally overriding descriptions.

## Why

MCP servers like Atlassian Rovo expose 39+ tools (~12k tokens). Most sessions only need a subset. This proxy sits between your MCP client (e.g. Claude Code) and the upstream server, exposing only the tools you configure.

## Install

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). No clone needed — `uvx` fetches and caches the tool automatically:

```bash
uvx --from git+https://github.com/patjlm/mcp-proxy mcp-proxy
```

For development, clone and use `uv run`:

```bash
git clone https://github.com/patjlm/mcp-proxy.git
cd mcp-proxy
uv sync
uv run mcp-proxy
```

## Configuration

Set `MCP_PROXY_CONFIG` to a YAML config file:

```yaml
upstream:
  type: http
  url: https://mcp.atlassian.com/v1/mcp/authv2

tools:
  whitelist:
    - getJiraIssue
    - searchJiraIssuesUsingJql
    - createJiraIssue
    # ...

  overrides:
    getAccessibleAtlassianResources:
      description: "Get cloudId for API calls."
```

See [config.example.yaml](config.example.yaml) for a full example filtering Atlassian Rovo to Jira-only tools.

### Upstream types

- **HTTP** (`type: http`): Connects to a remote MCP server. OAuth is auto-discovered. Static auth via `headers:`.
- **stdio** (`type: stdio`): Spawns a local MCP server process. Set `command:` and `args:`.

### Tool filtering

Use **one** of:
- `whitelist`: Only expose listed tools (recommended for maximum token savings)
- `blacklist`: Expose everything except listed tools

### Description overrides

Shorten verbose tool descriptions to save additional tokens:

```yaml
overrides:
  toolName:
    description: "Shorter description"
```

### Parameter stripping

Remove optional parameters from tool schemas to save additional tokens:

```yaml
overrides:
  transitionJiraIssue:
    disabled_parameters: [historyMetadata]
```

Required parameters are never removed (a warning is logged instead). You can combine `description` and `disabled_parameters` on the same tool.

## Usage with Claude Code

In `~/.claude.json`:

```json
{
  "mcpServers": {
    "atlassian-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/patjlm/mcp-proxy", "mcp-proxy"],
      "env": {
        "MCP_PROXY_CONFIG": "/path/to/config.yaml"
      }
    }
  }
}
```

### OAuth

OAuth is handled automatically by the proxy, not by Claude Code. When the proxy first connects to an OAuth-enabled upstream (e.g. Atlassian Rovo), it **silently opens a browser window** for authentication. Claude Code is not aware this is happening — from its perspective, the MCP server is just slow to start. This can be surprising: a browser tab will appear unprompted asking you to log in. Once authenticated, tokens are cached in `~/.cache/mcp-proxy-filter/` and subsequent sessions connect silently.

## Results

With the example Atlassian Rovo config (Jira-only whitelist):

| | Tools | Tokens |
|---|---|---|
| Direct (atlassian-rovo) | 39 | ~12,500 |
| Proxied (atlassian-proxy) | 17 | ~3,800 |
| **Savings** | | **~70%** |
