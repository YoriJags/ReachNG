"""Thin MCP *client* — lets EYO talk to a client's registered MCP server.

Two operations only:
  list_tools(conn)                 — discover what the connected server can do
                                     (for building an action proposal / showing
                                     the owner what's available).
  call_tool(conn, name, arguments) — execute ONE tool call. Deterministic,
                                     code-driven: this runs an action the owner
                                     ALREADY approved, never a Claude decision.
                                     Keeping execution out of the model is the
                                     safety property — a prompt-injected customer
                                     message can never trigger a real side-effect.

Direction note: ReachNG already runs an MCP *server* (mcp_server/) that exposes
OUR tools to an outside Claude. This module is the opposite — EYO as a client
calling OUT to the client's own tools.

Dormant by design: the MCP client lib is imported lazily, so its absence can
never break app boot. ``available()`` returns False and calls raise a clear,
catchable error. MCP is async; ``call_tool_sync`` bridges to the sync approval
flow.

``conn`` is the resolved dict from services.connections.resolve_connection:
``{client_name, provider, url, auth_type, token}``.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Optional

import structlog

log = structlog.get_logger()


class McpClientUnavailable(RuntimeError):
    """The MCP client library isn't importable in this environment."""


def _import_client():
    """Lazy import of the fastmcp client. Returns (Client, transport_factory) or
    raises McpClientUnavailable. transport_factory(url, headers) builds an HTTP
    transport with optional auth headers; falls back to a bare URL if the
    transport class isn't importable in this version."""
    try:
        from fastmcp import Client
    except Exception as e:  # pragma: no cover - depends on env
        raise McpClientUnavailable(f"fastmcp client not available: {e}")

    def transport_factory(url: str, headers: Optional[dict]):
        if not headers:
            return url
        try:
            from fastmcp.client.transports import StreamableHttpTransport
            return StreamableHttpTransport(url, headers=headers)
        except Exception:
            # Version without a headers-capable transport — fall back to URL.
            # No-auth servers still work; bearer servers will be rejected by the
            # remote, surfaced as a normal call error rather than a crash.
            log.warning("mcp_transport_headers_unsupported")
            return url

    return Client, transport_factory


def available() -> bool:
    try:
        _import_client()
        return True
    except McpClientUnavailable:
        return False


def _headers_for(conn: dict) -> Optional[dict]:
    if conn.get("auth_type") == "bearer" and conn.get("token"):
        return {"Authorization": f"Bearer {conn['token']}"}
    return None


def _open(conn: dict):
    Client, transport_factory = _import_client()
    url = conn.get("url")
    if not url:
        raise ValueError("connection has no url")
    return Client(transport_factory(url, _headers_for(conn)))


def _extract(result: Any) -> Any:
    """Normalise a fastmcp CallToolResult into a JSON-safe payload, tolerant of
    version differences (.data on newer, .content blocks on older)."""
    data = getattr(result, "data", None)
    if data is not None:
        return data
    content = getattr(result, "content", None)
    if content is None:
        return result
    out = []
    for block in content:
        text = getattr(block, "text", None)
        out.append(text if text is not None else str(block))
    return out if len(out) != 1 else out[0]


# ─── Async API ────────────────────────────────────────────────────────────────

async def list_tools(conn: dict) -> list[dict]:
    """Discover the server's tools: [{name, description, input_schema}]."""
    async with _open(conn) as client:
        tools = await client.list_tools()
    out = []
    for t in tools:
        out.append({
            "name":         getattr(t, "name", None),
            "description":  getattr(t, "description", "") or "",
            "input_schema": getattr(t, "inputSchema", None) or getattr(t, "input_schema", None),
        })
    return out


async def call_tool(conn: dict, name: str, arguments: dict) -> dict:
    """Execute one approved tool call. Returns {ok, result} or {ok: False, error}.
    Never logs arguments (may carry PII)."""
    try:
        async with _open(conn) as client:
            result = await client.call_tool(name, arguments or {})
        log.info("mcp_tool_called", provider=conn.get("provider"), tool=name)
        return {"ok": True, "result": _extract(result)}
    except McpClientUnavailable as e:
        log.warning("mcp_tool_unavailable", tool=name, error=str(e))
        return {"ok": False, "error": str(e)}
    except Exception as e:
        log.error("mcp_tool_failed", provider=conn.get("provider"), tool=name, error=str(e))
        return {"ok": False, "error": str(e)}


# ─── Sync bridge (for the approval flow / sync callers) ──────────────────────

def _run_async(coro):
    """Run a coroutine from sync code whether or not a loop is already running."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        return asyncio.run(coro)


def call_tool_sync(conn: dict, name: str, arguments: dict) -> dict:
    return _run_async(call_tool(conn, name, arguments))


def list_tools_sync(conn: dict) -> list[dict]:
    return _run_async(list_tools(conn))
