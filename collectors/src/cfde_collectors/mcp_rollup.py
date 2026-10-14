"""Daily rollup: ClickHouse mcp_requests -> Postgres raw.mcp_daily_calls and raw.mcp_clients_monthly.

Aggregation happens in ClickHouse (over the mcp_requests_attributed view, which back-fills the
client name of legacy sessions); this module only moves the aggregate rows. Each run re-rolls the
last --days complete UTC days (default 3, which covers late log delivery and a host that was off)
and the month containing each, replacing them in one transaction, so re-runs are idempotent.

    cfde-rollup-mcp --dry-run                  # print rows as JSON, no Postgres
    cfde-rollup-mcp --date 2026-10-13          # one specific day
    env: CLICKHOUSE_URL (e.g. https://clickhouse.cancerdatasci.org), CLICKHOUSE_USER,
         CLICKHOUSE_PASSWORD, CLICKHOUSE_DB (default "default"), DATABASE_URL
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

Row = dict[str, Any]
Query = Callable[[str, dict[str, str]], list[Row]]
MAX_AGE_DAYS = 85

DAILY_SQL = """
SELECT toString(toDate(timestamp)) AS date, server, method, tool, client_name, client_version,
       toString(outcome) AS outcome, count() AS calls, uniqExact(client_hash) AS distinct_clients
FROM mcp_requests_attributed
WHERE toDate(timestamp) = {day:Date}
GROUP BY date, server, method, tool, client_name, client_version, outcome
ORDER BY ALL
FORMAT JSONEachRow
"""

# Month to date, up to and including {day}. client_name '*' is the per-server total.
MONTHLY_SQL = """
SELECT toString(toStartOfMonth({day:Date})) AS month, server, if(all_clients = 1, '*', name) AS client_name,
       tool_calls, distinct_clients
FROM (
    SELECT server, client_name AS name, grouping(client_name) AS all_clients,
           count() AS tool_calls, uniqExact(client_hash) AS distinct_clients
    FROM mcp_requests_attributed
    WHERE method = 'tools/call'
      AND toDate(timestamp) BETWEEN toStartOfMonth({day:Date}) AND {day:Date}
    GROUP BY GROUPING SETS ((server, client_name), (server))
)
ORDER BY ALL
FORMAT JSONEachRow
"""


def clickhouse_query(sql: str, params: dict[str, str]) -> list[Row]:
    base = os.environ["CLICKHOUSE_URL"].rstrip("/")
    qs = urllib.parse.urlencode(
        {"database": os.environ.get("CLICKHOUSE_DB", "default"), **{f"param_{k}": v for k, v in params.items()}}
    )
    auth = f"{os.environ['CLICKHOUSE_USER']}:{os.environ['CLICKHOUSE_PASSWORD']}".encode()
    req = urllib.request.Request(
        f"{base}/?{qs}",
        data=sql.encode(),
        headers={"Authorization": "Basic " + base64.b64encode(auth).decode(), "User-Agent": "cfde-rollup-mcp"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return [json.loads(line) for line in r.read().decode().splitlines() if line]
    except urllib.error.HTTPError as e:  # ClickHouse puts the reason in the body
        raise RuntimeError(f"ClickHouse {e.code}: {e.read().decode()[:500]}") from None


def rollup(day: date, query: Query = clickhouse_query) -> tuple[list[Row], list[Row]]:
    """Return (daily rows for `day`, month-to-date rows for `day`'s month)."""
    params = {"day": day.isoformat()}
    # ClickHouse returns UInt64 as JSON strings; normalize counts to int.
    daily = [
        {**r, "calls": int(r["calls"]), "distinct_clients": int(r["distinct_clients"])}
        for r in query(DAILY_SQL, params)
    ]
    monthly = [
        {**r, "tool_calls": int(r["tool_calls"]), "distinct_clients": int(r["distinct_clients"])}
        for r in query(MONTHLY_SQL, params)
    ]
    return daily, monthly


def days_to_roll(end: date, n: int) -> list[date]:
    """The n days ending at `end`, oldest first (so the last write of a month is its newest total)."""
    return [end - timedelta(days=i) for i in reversed(range(n))]


INSERT_DAILY = """
INSERT INTO raw.mcp_daily_calls
    (date, server, method, tool, client_name, client_version, outcome, calls, distinct_clients)
VALUES (%(date)s, %(server)s, %(method)s, %(tool)s, %(client_name)s, %(client_version)s, %(outcome)s,
        %(calls)s, %(distinct_clients)s)
"""
INSERT_MONTHLY = """
INSERT INTO raw.mcp_clients_monthly (month, server, client_name, tool_calls, distinct_clients)
VALUES (%(month)s, %(server)s, %(client_name)s, %(tool_calls)s, %(distinct_clients)s)
"""


def write(results: dict[date, tuple[list[Row], list[Row]]], database_url: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:  # one transaction
        for day, (daily, monthly) in sorted(results.items()):
            cur.execute("DELETE FROM raw.mcp_daily_calls WHERE date = %s", (day,))
            cur.executemany(INSERT_DAILY, daily)
            cur.execute("DELETE FROM raw.mcp_clients_monthly WHERE month = %s", (day.replace(day=1),))
            cur.executemany(INSERT_MONTHLY, monthly)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat, help="last UTC day to roll up (default: yesterday)")
    ap.add_argument("--days", type=int, default=3, help="number of days ending at --date (default 3)")
    ap.add_argument("--dry-run", action="store_true", help="print rows as JSON instead of writing to Postgres")
    args = ap.parse_args()

    end = args.date or datetime.now(UTC).date() - timedelta(days=1)
    days = days_to_roll(end, args.days)
    # ClickHouse drops raw rows after 90 days; re-rolling an expired day would replace its kept
    # aggregates with nothing.
    if days[0] < datetime.now(UTC).date() - timedelta(days=MAX_AGE_DAYS):
        sys.exit(f"refusing to roll up {days[0]}: older than {MAX_AGE_DAYS} days (ClickHouse TTL is 90)")
    results = {day: rollup(day) for day in days}
    if args.dry_run:
        json.dump({d.isoformat(): {"daily": dl, "monthly": m} for d, (dl, m) in results.items()}, sys.stdout, indent=1)
        print()
        return
    if not (url := os.environ.get("DATABASE_URL")):
        sys.exit("DATABASE_URL is not set (use --dry-run to print rows instead)")
    write(results, url)
    n = sum(len(dl) for dl, _ in results.values())
    print(f"rolled up {', '.join(d.isoformat() for d in results)}: {n} daily rows", file=sys.stderr)
