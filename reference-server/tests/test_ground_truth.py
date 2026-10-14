import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections import Counter

import pytest

from cfde_reference_mcp.traffic import CALLS, run

SENTINEL = "SENTINEL-arg-7f3c9e"
N = 5


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_traffic_counts_match_server_log(mode: str) -> None:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1"}
    proc = subprocess.Popen(
        [sys.executable, "-c", "import cfde_reference_mcp as m; m.main()"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"{base}/health") as r:
                    assert r.status == 200
                    assert "Healthy" in r.read().decode()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("server did not become healthy")

        calls = {**CALLS, "echo_upper": {"text": SENTINEL}, "gene_symbol_lookup": {"symbol": SENTINEL}}
        client_counts = asyncio.run(run(f"{base}/mcp", N, calls, mode))
    finally:
        proc.terminate()
        out, err = proc.communicate(timeout=10)

    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert all(line["event"] == "tools/call" for line in lines)
    assert all(line["client_name"] == "cfde-traffic" for line in lines)
    server_counts: dict[str, Counter[str]] = {}
    for line in lines:
        server_counts.setdefault(line["tool"], Counter())[line["outcome"]] += 1

    assert client_counts == {tool: dict(c) for tool, c in server_counts.items()}
    assert client_counts["always_fail"] == {"tool_error": N}
    assert client_counts["add"] == {"ok": N}
    assert SENTINEL.lower() not in (out + err).lower()  # neither args nor echo_upper's result
