# Salesforce MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes Salesforce Case operations as tools. Built with Python 3.12, [`mcp[cli]`](https://github.com/modelcontextprotocol/python-sdk), and [`simple-salesforce`](https://github.com/simple-salesforce/simple-salesforce).

## Tools

| Tool | Description |
|------|-------------|
| `create_case` | Create a new Salesforce Case with subject, description, priority, status, origin, type, contact, and account |
| `get_case` | Retrieve a Case by its Case Number (auto zero-pads, e.g. `1042` -> `00001042`) |

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Install dependencies

```bash
uv sync
```

### Salesforce Authentication

The server supports two auth modes, configured via environment variables:

**Option 1: Connected App (OAuth Client Credentials)** (recommended)

```bash
SF_CONSUMER_KEY=your_consumer_key
SF_CONSUMER_SECRET=your_consumer_secret
SF_DOMAIN=login              # or "test" for sandbox
```

**Option 2: Username / Password**

```bash
SF_USERNAME=your_username
SF_PASSWORD=your_password
SF_SECURITY_TOKEN=your_token
SF_DOMAIN=login              # or "test" for sandbox
```

## Running the Server

### Streamable HTTP (default, for VAPI and other cloud clients)

```bash
uv run server.py
```

The server starts on `http://0.0.0.0:8000` with:
- `POST /mcp` -- Streamable HTTP endpoint (MCP protocol)
- `GET /health` -- Health check

### stdio (for Claude Desktop and local MCP clients)

```bash
MCP_TRANSPORT=stdio uv run server.py
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `sse` | Transport mode: `sse` (starts HTTP server) or `stdio` |
| `MCP_HOST` | `0.0.0.0` | HTTP server bind address |
| `MCP_PORT` | `8000` | HTTP server port |
| `MCP_API_KEY` | _(none)_ | Bearer token for API authentication. If unset, auth is disabled |
| `SF_DOMAIN` | `login` | Salesforce domain (`login` for production, `test` for sandbox) |

## Authentication

When `MCP_API_KEY` is set, all requests (except `/health` and CORS preflight) require a Bearer token:

```
Authorization: Bearer <your_mcp_api_key>
```

## Client Configuration

### VAPI

Set the MCP server URL to:

```
https://your-deployment-url/mcp
```

Add your `MCP_API_KEY` as a custom header in VAPI's MCP server configuration.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "salesforce-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/salesforce-mcp", "server.py"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "SF_CONSUMER_KEY": "your_key",
        "SF_CONSUMER_SECRET": "your_secret"
      }
    }
  }
}
```

## Deployment (Railway)

The server is designed to deploy on Railway or similar platforms. Set all required environment variables in your deployment configuration.

## Testing

```bash
uv run pytest test_server.py -v
```

Tests cover:
- Health check endpoint
- CORS preflight handling
- Bearer token authentication (valid, invalid, missing, disabled)
- Streamable HTTP endpoint (`/mcp`)
- Salesforce client factory (both auth modes, error handling)
- MCP tools (`create_case`, `get_case`) with mocked Salesforce
