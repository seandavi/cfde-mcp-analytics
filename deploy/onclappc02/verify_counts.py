"""#22 check: gateway counts in ClickHouse within 5% of the reference server's own count.

Sends N calls per reference tool through the gateway in both protocol generations (2026-07-28
stateless, then a legacy 2025-11-25 session), waits for Vector, then compares tools/call counts per
(tool, outcome): traffic script (sent), reference server log (ground truth), ClickHouse
mcp_requests_attributed (measured). Also checks client attribution (>= 80%). Exit 0 = pass.

On onclappc02, once deployed (APPLY.md Phase 4):
    set -a; . collectors/.env; set +a
    uv run --directory reference-server python ../deploy/onclappc02/verify_counts.py 25

env: CLICKHOUSE_URL, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, [CLICKHOUSE_DB], [GATEWAY_URL],
     [REFERENCE_CONTAINER] (default cfde-mcp-reference)
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime

from cfde_reference_mcp.traffic import run

GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://cfde-mcp.cancerdatasci.org/reference/mcp")
CONTAINER = os.environ.get("REFERENCE_CONTAINER", "cfde-mcp-reference")


def clickhouse(sql: str) -> list[dict]:
    qs = urllib.parse.urlencode({"database": os.environ.get("CLICKHOUSE_DB", "default")})
    auth = base64.b64encode(f"{os.environ['CLICKHOUSE_USER']}:{os.environ['CLICKHOUSE_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(
        f"{os.environ['CLICKHOUSE_URL'].rstrip('/')}/?{qs}",
        data=(sql + " FORMAT JSONEachRow").encode(),
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return [json.loads(line) for line in r.read().decode().splitlines() if line]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    start = datetime.now(UTC).replace(microsecond=0)
    time.sleep(1)  # second-resolution start: keep earlier traffic out

    sent: Counter[tuple[str, str]] = Counter()
    for mode in ("auto", "legacy"):
        for tool, outcomes in asyncio.run(run(GATEWAY_URL, n, mode=mode)).items():
            for outcome, count in outcomes.items():
                sent[(tool, outcome)] += count
    time.sleep(20)  # Vector: file poll + 2 s batch flush

    logs = subprocess.run(
        ["docker", "logs", "--since", start.isoformat(), CONTAINER], capture_output=True, text=True, check=True
    ).stdout
    truth: Counter[tuple[str, str]] = Counter()
    for line in logs.splitlines():
        if line.startswith("{") and '"event": "tools/call"' in line:
            d = json.loads(line)
            truth[(d["tool"], d["outcome"])] += 1

    rows = clickhouse(
        "SELECT tool, toString(outcome) AS outcome, count() AS n, countIf(attribution != 'none') AS attributed "
        "FROM mcp_requests_attributed WHERE server = 'reference' AND method = 'tools/call' "
        f"AND timestamp >= '{start:%Y-%m-%d %H:%M:%S}' GROUP BY tool, outcome"
    )
    measured = Counter({(r["tool"], r["outcome"]): int(r["n"]) for r in rows})
    attributed = sum(int(r["attributed"]) for r in rows)

    print(f"{'tool':<20} {'outcome':<11} {'sent':>6} {'server':>7} {'gateway':>8}")
    for key in sorted(sent.keys() | truth.keys() | measured.keys()):
        print(f"{key[0]:<20} {key[1]:<11} {sent[key]:>6} {truth[key]:>7} {measured[key]:>8}")
    t, g = sum(truth.values()), sum(measured.values())
    diff = abs(g - t) / t if t else 1.0
    share = attributed / g if g else 0.0
    print(f"total: sent {sum(sent.values())}, server {t}, gateway {g}; diff {diff:.1%} (<= 5%); attributed {share:.0%} (>= 80%)")
    sys.exit(0 if t and diff <= 0.05 and share >= 0.8 else 1)


if __name__ == "__main__":
    main()
