"""Traffic generator: N known calls per tool with a fixed clientInfo; prints counts as JSON.

Usage: cfde-traffic URL [N] [auto|legacy]
"""

import asyncio
import json
import sys
from collections import Counter

from mcp import Client
from mcp.types import Implementation

CLIENT_INFO = Implementation(name="cfde-traffic", version="0.1.0")

CALLS: dict[str, dict[str, object]] = {
    "echo_upper": {"text": "hello"},
    "add": {"a": 2, "b": 3},
    "gene_symbol_lookup": {"symbol": "TP53"},
    "always_fail": {},
}


async def run(
    url: str, n: int, calls: dict[str, dict[str, object]] = CALLS, mode: str = "auto"
) -> dict[str, dict[str, int]]:
    """mode: "auto" (2026-07-28 stateless if supported) or "legacy" (initialize handshake + session)."""
    counts: dict[str, Counter[str]] = {tool: Counter() for tool in calls}
    async with Client(url, client_info=CLIENT_INFO, mode=mode) as client:
        for tool, args in calls.items():
            for _ in range(n):
                try:
                    result = await client.call_tool(tool, args)
                    counts[tool]["tool_error" if result.is_error else "ok"] += 1
                except Exception:
                    counts[tool]["rpc_error"] += 1
    return {tool: dict(c) for tool, c in counts.items()}


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    mode = sys.argv[3] if len(sys.argv) > 3 else "auto"
    print(json.dumps(asyncio.run(run(url, n, mode=mode)), indent=2))
