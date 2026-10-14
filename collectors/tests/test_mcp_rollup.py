"""Rollup tests against ClickHouse responses recorded from a local run (32 reference-server calls:
20 from a 2026-07-28 client, 12 from a legacy-session client; see deploy/onclappc02/APPLY.md)."""

import json
from datetime import date
from pathlib import Path

from cfde_collectors.mcp_rollup import DAILY_SQL, MONTHLY_SQL, days_to_roll, rollup

FIXTURES = Path(__file__).parent / "fixtures"


def recorded(sql: str, params: dict[str, str]) -> list[dict]:
    assert params == {"day": "2026-10-14"}
    name = {DAILY_SQL: "ch_daily", MONTHLY_SQL: "ch_monthly"}[sql]
    return [json.loads(line) for line in (FIXTURES / f"{name}.jsonl").read_text().splitlines()]


def test_rollup_daily_and_monthly_agree():
    daily, monthly = rollup(date(2026, 10, 14), query=recorded)
    calls = {r["tool"]: (r["outcome"], r["calls"]) for r in daily if r["method"] == "tools/call"}
    assert calls == {
        "add": ("ok", 8),
        "always_fail": ("tool_error", 8),
        "echo_upper": ("ok", 8),
        "gene_symbol_lookup": ("ok", 8),
    }
    # Legacy-session rows are attributed through the session join, so every row has a client.
    assert {r["client_name"] for r in daily} == {"cfde-traffic"}
    total = next(r for r in monthly if r["client_name"] == "*")
    assert (total["month"], total["tool_calls"], total["distinct_clients"]) == ("2026-10-01", 32, 1)


def test_counts_normalized_when_clickhouse_quotes_uint64():
    def quoted(sql: str, params: dict[str, str]) -> list[dict]:
        return [
            {k: str(v) if k in ("calls", "tool_calls", "distinct_clients") else v for k, v in r.items()}
            for r in recorded(sql, params)
        ]

    daily, monthly = rollup(date(2026, 10, 14), query=quoted)
    assert all(isinstance(r["calls"], int) for r in daily)
    assert all(isinstance(r["tool_calls"], int) for r in monthly)


def test_days_oldest_first_across_month_boundary():
    # Oldest first: the month's last write is its newest month-to-date total.
    assert days_to_roll(date(2026, 10, 1), 3) == [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
