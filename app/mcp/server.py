"""
NexusFlow AI · Real MCP Server
==============================
Exposes the NexusFlow tool hub over the Model Context Protocol (MCP)
using the official `mcp` Python SDK (v2.x, MCPServer).

Transports:
  * stdio  (default) — used by the in-process MCP client (subprocess spawn)
  * streamable-http  — usable by external MCP clients (Claude Desktop, Cursor, etc.)

Run standalone:
    python -m app.mcp.server                 # stdio
    python -m app.mcp.server --http 8765     # streamable HTTP on port 8765
"""
import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from app.agents.mcp_hub import mcp_hub

SERVER_NAME = "nexusflow-ai"
SERVER_INSTRUCTIONS = (
    "NexusFlow AI enterprise operations MCP server. Exposes CRM, billing, "
    "spreadsheets and outbound email tools for autonomous multi-app workflows. "
    "All mutations are subject to SafeGuard risk classification on the client side."
)

mcp = MCPServer(
    name=SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    version="1.0.0",
)


def _build_tool_fn(tool_name: str, params_schema: Dict[str, Any]):
    """
    Dynamically build a tool function whose signature matches the JSON schema.
    The MCP SDK derives the tool input schema from the function signature,
    so each tool gets explicit typed parameters instead of a generic dict.
    """
    props: Dict[str, Dict[str, Any]] = params_schema.get("properties", {})
    required = set(params_schema.get("required", []))

    py_types = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "object": "Dict[str, Any]",
        "array": "List[Any]",
        "boolean": "bool",
    }

    params = []
    arg_entries = []
    for pname, pspec in props.items():
        base_type = py_types.get(pspec.get("type", "string"), "Any")
        if pname in required:
            params.append(f"{pname}: {base_type}")
        else:
            params.append(f"{pname}: Optional[{base_type}] = None")
        arg_entries.append(f'"{pname}": {pname}')

    sig = ", ".join(params)
    args_dict = "{" + ", ".join(arg_entries) + "}"

    src = (
        f"def {tool_name}({sig}):\n"
        f"    from app.agents.mcp_hub import mcp_hub as _hub\n"
        f"    _arguments = {args_dict}\n"
        f"    _arguments = {{k: v for k, v in _arguments.items() if v is not None}}\n"
        f"    return _hub.execute_tool({tool_name!r}, _arguments)\n"
    )

    namespace: Dict[str, Any] = {"Dict": Dict, "List": List, "Optional": Optional, "Any": Any}
    exec(src, namespace)
    fn = namespace[tool_name]
    return fn


def _register_tools() -> None:
    """Register every mcp_hub tool on the MCP server, preserving JSON schemas."""
    definitions: List[Dict[str, Any]] = mcp_hub.list_mcp_tools()

    for definition in definitions:
        tool_name = definition["name"]
        tool_description = definition.get("description", "")
        fn = _build_tool_fn(tool_name, definition.get("parameters", {}))
        fn.__doc__ = tool_description
        mcp.add_tool(fn, name=tool_name, description=tool_description)


_register_tools()


async def run_stdio() -> None:
    await mcp.run_stdio_async()


def main() -> None:
    parser = argparse.ArgumentParser(description="NexusFlow AI MCP Server")
    parser.add_argument("--http", type=int, default=None,
                        help="Serve over streamable HTTP on the given port instead of stdio.")
    args = parser.parse_args()

    if args.http:
        import uvicorn
        app = mcp.streamable_http_app()
        uvicorn.run(app, host="127.0.0.1", port=args.http, log_level="warning")
    else:
        import anyio
        anyio.run(run_stdio)


if __name__ == "__main__":
    main()
