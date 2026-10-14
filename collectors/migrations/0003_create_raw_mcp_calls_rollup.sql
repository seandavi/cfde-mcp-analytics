-- 0003 — Raw layer for gateway call aggregates, rolled up daily from ClickHouse mcp_requests.
--
-- Written by collectors/src/cfde_collectors/mcp_rollup.py (cfde-rollup-mcp). Each run replaces
-- whole days (and the month containing them) in one transaction, so re-running is idempotent.
-- No client IPs, hashes, arguments or results are stored here; only counts. ClickHouse keeps the
-- raw rows for 90 days; these aggregates are kept (D6). Assumes the `raw` schema exists.
-- Apply with: psql "$DATABASE_URL" -f <this file>

CREATE TABLE IF NOT EXISTS raw.mcp_daily_calls (
    date              DATE        NOT NULL,
    server            TEXT        NOT NULL,
    method            TEXT        NOT NULL,
    tool              TEXT        NOT NULL,
    client_name       TEXT        NOT NULL,
    client_version    TEXT        NOT NULL,
    outcome           TEXT        NOT NULL,
    calls             BIGINT      NOT NULL,
    distinct_clients  BIGINT      NOT NULL,
    rolled_up_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, server, method, tool, client_name, client_version, outcome)
);

COMMENT ON TABLE raw.mcp_daily_calls IS
    'MCP JSON-RPC requests through the CFDE gateway per UTC day, one row per (date, server, method, '
    'tool, client_name, client_version, outcome). Use analytics.mcp_daily for queries.';
COMMENT ON COLUMN raw.mcp_daily_calls.client_name IS
    'clientInfo.name, back-filled for legacy sessions from their initialize; empty when unattributed.';
COMMENT ON COLUMN raw.mcp_daily_calls.distinct_clients IS
    'Distinct (IP + User-Agent) HMACs in this row on this day. Not additive across rows or days.';

CREATE TABLE IF NOT EXISTS raw.mcp_clients_monthly (
    month             DATE        NOT NULL,
    server            TEXT        NOT NULL,
    client_name       TEXT        NOT NULL,
    tool_calls        BIGINT      NOT NULL,
    distinct_clients  BIGINT      NOT NULL,
    rolled_up_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (month, server, client_name)
);

COMMENT ON TABLE raw.mcp_clients_monthly IS
    'Per calendar month (UTC) and server: tool calls and distinct clients, per client app and in '
    'total (client_name = ''*''). Month to date until the month ends. Use analytics.mcp_clients_monthly.';
