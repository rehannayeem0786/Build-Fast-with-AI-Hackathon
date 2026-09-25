"""
NexusFlow AI · Model Context Protocol (MCP) integration subpackage.

This package implements a genuine MCP client/server pair using the
official ``mcp`` Python SDK (JSON-RPC over stdio or streamable HTTP):

- :mod:`app.mcp.server` — exposes the 12 NexusFlow tools (CRM, billing,
  sheets, email) as MCP tools. Run standalone with::

      python -m app.mcp.server              # stdio transport
      python -m app.mcp.server --http 8765  # streamable HTTP

- :mod:`app.mcp.client` — spawns the server as a subprocess, completes the
  MCP ``initialize`` handshake, and executes tools via ``tools/call``.
  Falls back to the in-process tool hub when the transport is unavailable,
  always reporting which path was used (``_transport`` field).

Why this file exists at all: ``__init__.py`` marks ``app.mcp`` as a regular
Python package (instead of an implicit namespace package). An *empty* file
is the standard convention — the marker alone is its job. The exports below
are convenience aliases so ``from app.mcp import mcp_client`` also works;
existing import paths (``app.mcp.client``, ``app.mcp.server``) are unchanged.
"""
from app.mcp.client import (
    MCPClient,
    mcp_client,
    TRANSPORT_LOCAL_FALLBACK,
    TRANSPORT_STDIO,
)

__all__ = [
    "MCPClient",
    "mcp_client",
    "TRANSPORT_STDIO",
    "TRANSPORT_LOCAL_FALLBACK",
]

