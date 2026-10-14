"""cfde-reference-mcp: trivial deterministic MCP server with a ground-truth call log.

Every tools/call writes exactly one JSON line to stdout:
{"ts", "event": "tools/call", "tool", "outcome", "client_name", "client_version", "protocol_version"}.
Tool arguments and results are never logged.
"""

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import PlainTextResponse

GENES = {
    "TP53": "tumor protein p53",
    "BRCA1": "BRCA1 DNA repair associated",
    "EGFR": "epidermal growth factor receptor",
}


def _outcome(result: HandlerResult) -> str:
    is_error = getattr(result, "is_error", None)
    if isinstance(result, dict):
        is_error = result.get("isError", result.get("is_error"))
    return "tool_error" if is_error else "ok"


async def call_log(ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
    if ctx.method != "tools/call":
        return await call_next(ctx)
    outcome = "rpc_error"
    try:
        result = await call_next(ctx)
        outcome = _outcome(result)
        return result
    finally:
        info = ctx.session.client_params.client_info if ctx.session.client_params else None
        line = {
            "ts": datetime.now(UTC).isoformat(),
            "event": "tools/call",
            "tool": (ctx.params or {}).get("name"),
            "outcome": outcome,
            "client_name": info.name if info else None,
            "client_version": info.version if info else None,
            "protocol_version": ctx.protocol_version,
        }
        print(json.dumps(line), flush=True)


mcp = MCPServer("cfde-reference-mcp", version="0.1.0", log_level="WARNING", middleware=[call_log])


@mcp.tool()
def echo_upper(text: str) -> str:
    """Return text upper-cased."""
    return text.upper()


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def gene_symbol_lookup(symbol: str) -> str:
    """Look up a gene name by HGNC symbol (tiny fixed table)."""
    return GENES.get(symbol.upper(), "unknown")


@mcp.tool()
def always_fail() -> str:
    """Always fails (isError=true); for testing error accounting."""
    raise ToolError("always_fail always fails")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Healthy")


def app(host: str = "127.0.0.1"):
    return mcp.streamable_http_app(host=host)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"cfde-reference-mcp on http://{host}:{port}/mcp", file=sys.stderr)
    uvicorn.run(app(host), host=host, port=port, log_level="warning")
