"""
NexusFlow AI · Real MCP Client
==============================
Connects to the NexusFlow MCP server as a genuine MCP client using the
official `mcp` SDK: spawns the server as a subprocess over stdio,
performs the MCP initialize handshake, lists tools, and calls tools
via the JSON-RPC `tools/call` method.

If the subprocess transport cannot start (restricted sandbox, missing
binary, etc.) the client degrades gracefully to an in-process direct
call so workflows remain runnable — but the transport actually used is
always reported for transparency in traces and telemetry.
"""
import os
import sys
from typing import Any, Dict, List, Optional

from app.agents.mcp_hub import mcp_hub

TRANSPORT_STDIO = "MCP_STDIO"
TRANSPORT_LOCAL_FALLBACK = "LOCAL_FALLBACK"


class MCPClient:
    """Async MCP client over the stdio transport with local fallback."""

    def __init__(self):
        self._session = None
        self._stdio_cm = None
        self._session_cm = None
        self._loop = None  # event loop the session is bound to
        self.transport: str = TRANSPORT_LOCAL_FALLBACK
        self.server_info: Optional[str] = None
        self._server_tools: List[Dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return self._session is not None

    async def connect(self, timeout_sec: float = 20.0) -> bool:
        """
        Spawn the MCP server subprocess and complete the MCP initialize handshake.
        Returns True when a real MCP session is established.

        A session is only valid on the event loop that created it; if the
        caller runs on a different loop (e.g. a new `asyncio.run` in tests),
        the stale session is abandoned and re-established.
        """
        import asyncio
        current_loop = asyncio.get_running_loop()
        if self.connected:
            if self._loop is current_loop:
                return True
            # Stale session from a dead event loop — abandon it (the orphaned
            # subprocess exits when this parent process closes its stdin).
            self._session = None
            self._stdio_cm = None
            self._session_cm = None
            self.transport = TRANSPORT_LOCAL_FALLBACK
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            env = dict(os.environ)
            # Ensure the spawned server can import the `app` package.
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

            server_params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp.server"],
                env=env,
                cwd=project_root,
            )

            self._stdio_cm = stdio_client(server_params)
            read_stream, write_stream = await self._stdio_cm.__aenter__()
            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()
            init_result = await self._session.initialize()

            info = getattr(init_result, "serverInfo", None)
            self.server_info = getattr(info, "name", "nexusflow-ai") if info else "nexusflow-ai"

            tools_result = await self._session.list_tools()
            self._server_tools = [
                {"name": t.name, "description": t.description}
                for t in tools_result.tools
            ]

            self.transport = TRANSPORT_STDIO
            self._loop = current_loop
            return True
        except Exception:
            # Graceful degradation: keep workflows runnable without MCP subprocess.
            await self.close()
            self.transport = TRANSPORT_LOCAL_FALLBACK
            return False

    def _session_usable(self) -> bool:
        """True only when a session exists AND belongs to the running loop."""
        if self._session is None:
            return False
        try:
            import asyncio
            return self._loop is asyncio.get_running_loop()
        except Exception:
            return False

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List tools from the MCP server when connected, else from the local hub."""
        if self._session_usable():
            try:
                result = await self._session.list_tools()
                return [
                    {"name": t.name, "description": t.description or ""}
                    for t in result.tools
                ]
            except Exception:
                pass
        return [{"name": d["name"], "description": d.get("description", "")}
                for d in mcp_hub.list_mcp_tools()]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool via MCP `tools/call` when connected; otherwise invoke the
        local hub directly. Adds a `_transport` field so traces record which
        path was taken.
        """
        if self._session_usable():
            try:
                result = await self._session.call_tool(name, arguments or {})
                payload = self._extract_payload(result)
                if isinstance(payload, dict):
                    payload.setdefault("_transport", TRANSPORT_STDIO)
                    return payload
                return {"result": payload, "_transport": TRANSPORT_STDIO}
            except Exception:
                # Fall through to local execution for resilience.
                self.transport = TRANSPORT_LOCAL_FALLBACK

        out = mcp_hub.execute_tool(name, arguments or {})
        if isinstance(out, dict):
            out.setdefault("_transport", TRANSPORT_LOCAL_FALLBACK)
            return out
        return {"result": out, "_transport": TRANSPORT_LOCAL_FALLBACK}

    @staticmethod
    def _extract_payload(result: Any) -> Any:
        """Normalize MCP CallToolResult into a plain Python payload."""
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
                return structured["result"]
            return structured
        content = getattr(result, "content", None) or []
        texts = [c.text for c in content if getattr(c, "type", None) == "text" and c.text]
        if not texts:
            return {"success": True}
        if len(texts) == 1:
            try:
                import json
                return json.loads(texts[0])
            except Exception:
                return {"text": texts[0]}
        return {"texts": texts}

    async def close(self) -> None:
        for cm_attr in ("_session_cm", "_stdio_cm"):
            cm = getattr(self, cm_attr, None)
            if cm is not None:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass
                setattr(self, cm_attr, None)
        self._session = None
        self._loop = None


mcp_client = MCPClient()
