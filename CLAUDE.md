# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Model Context Protocol (MCP) server** named `salesforce-mcp`, built with Python 3.12 and the [`mcp[cli]`](https://github.com/modelcontextprotocol/python-sdk) package. The entry point is `server.py`.

## Package Management

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies
uv sync

# Add a dependency
uv add <package>

# Run the server directly
uv run server.py

# Run via MCP CLI (dev mode with inspector)
uv run mcp dev server.py

# Install the server for use with Claude Desktop
uv run mcp install server.py
```

## MCP Server Architecture

MCP servers expose **tools**, **resources**, and/or **prompts** to MCP clients (like Claude Desktop). The typical pattern using the `mcp` SDK:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("salesforce-mcp")

@mcp.tool()
def my_tool(param: str) -> str:
    """Tool description shown to the LLM."""
    ...

if __name__ == "__main__":
    mcp.run()
```

- Tools are Python functions decorated with `@mcp.tool()`
- Resources use `@mcp.resource("uri://template/{param}")`
- Prompts use `@mcp.prompt()`
- The server communicates over stdio by default (standard for MCP)

## MCP Client Configuration

To wire this server into Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "salesforce-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/salesforce-mcp", "server.py"]
    }
  }
}
```
