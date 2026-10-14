-- 0004 — Analytics views over the gateway call rollups (raw.mcp_daily_calls, raw.mcp_clients_monthly).

CREATE OR REPLACE VIEW analytics.mcp_daily AS
SELECT
    date,
    server,
    tool,
    COALESCE(NULLIF(client_name, ''), '(unattributed)') AS client_name,
    client_version,
    outcome,
    calls,
    distinct_clients,
    rolled_up_at AS data_refreshed_at
FROM raw.mcp_daily_calls
WHERE method = 'tools/call';

COMMENT ON VIEW analytics.mcp_daily IS
    'MCP tool calls made through the CFDE MCP gateway (cfde-mcp.cancerdatasci.org), per UTC day, '
    'one row per (date, server, tool, client_name, client_version, outcome). Counts only traffic '
    'that uses the gateway URLs; calls to a server''s own URL and local (stdio) installs are not '
    'visible here (see analytics.mcp_downloads_daily for the download floor). '
    'Answers "MCP calls by server and client app, last 30 days": '
    'SELECT server, client_name, SUM(calls) FROM analytics.mcp_daily '
    'WHERE date > CURRENT_DATE - 30 GROUP BY 1, 2.';

COMMENT ON COLUMN analytics.mcp_daily.date IS 'UTC calendar date of the calls.';
COMMENT ON COLUMN analytics.mcp_daily.server IS
    'Which MCP server, by gateway route: cfde-mcp (DRC), glygen, pwb (Playbook Workflow Builder), '
    'perturbseqr, or reference (the POC''s own test server; exclude it from usage reporting).';
COMMENT ON COLUMN analytics.mcp_daily.tool IS
    'Tool name the client called, as sent. Misspelled or nonexistent tool names appear too (they '
    'come back as tool errors).';
COMMENT ON COLUMN analytics.mcp_daily.client_name IS
    'The client application''s self-reported name (MCP clientInfo.name, e.g. claude-ai, cursor-vscode). '
    'For older-protocol clients it is taken from the session''s initialize request. '
    '(unattributed) when the client sent none.';
COMMENT ON COLUMN analytics.mcp_daily.client_version IS 'Self-reported client version (clientInfo.version); empty if none.';
COMMENT ON COLUMN analytics.mcp_daily.outcome IS
    'ok; tool_error (the tool ran and reported an error, including unknown tools and bad arguments); '
    'rpc_error (JSON-RPC protocol error); http_error (HTTP failure: upstream 5xx or timeout, or 4xx '
    'such as a missing cfde-mcp API key). Upstreams can also report failures inside an ok result, '
    'which no gateway can see.';
COMMENT ON COLUMN analytics.mcp_daily.calls IS 'Number of tools/call requests. Safe to SUM.';
COMMENT ON COLUMN analytics.mcp_daily.distinct_clients IS
    'Distinct clients (hashed IP + User-Agent) in this row on this day. Do NOT SUM across rows or '
    'days; use analytics.mcp_clients_monthly for distinct clients over a month.';
COMMENT ON COLUMN analytics.mcp_daily.data_refreshed_at IS 'When the rollup job last wrote this row.';

CREATE OR REPLACE VIEW analytics.mcp_clients_monthly AS
SELECT
    month,
    server,
    CASE client_name WHEN '*' THEN '(all clients)' WHEN '' THEN '(unattributed)' ELSE client_name END AS client_name,
    tool_calls,
    distinct_clients,
    rolled_up_at AS data_refreshed_at
FROM raw.mcp_clients_monthly;

COMMENT ON VIEW analytics.mcp_clients_monthly IS
    'Per calendar month (UTC) and MCP server: tool calls and distinct clients through the CFDE MCP '
    'gateway, broken down by client application, plus one (all clients) row per server. The current '
    'month is month-to-date and is rewritten daily.';
COMMENT ON COLUMN analytics.mcp_clients_monthly.month IS 'First day of the UTC calendar month.';
COMMENT ON COLUMN analytics.mcp_clients_monthly.server IS 'MCP server by gateway route (see analytics.mcp_daily.server).';
COMMENT ON COLUMN analytics.mcp_clients_monthly.client_name IS
    'Client application (clientInfo.name), (unattributed), or (all clients) for the server total. '
    'Use the (all clients) row for a server''s distinct clients; per-client rows do not add up to it.';
COMMENT ON COLUMN analytics.mcp_clients_monthly.tool_calls IS 'tools/call requests in the month.';
COMMENT ON COLUMN analytics.mcp_clients_monthly.distinct_clients IS
    'Distinct clients in the month, where a client is HMAC(IP + User-Agent) under a salt rotated '
    'monthly. Approximate: several users behind one NAT with the same client count once, and one '
    'user on two networks counts twice. Not comparable across months as the same people.';
COMMENT ON COLUMN analytics.mcp_clients_monthly.data_refreshed_at IS 'When the rollup job last wrote this row.';
