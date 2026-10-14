-- Schema for cfde-mcp gateway (agentgateway) access-log rows shipped by Vector.
--
-- Source of truth: cfde-mcp-analytics pipeline/clickhouse/mcp_requests.sql. Copied into monode
-- as infrastructure/compose/clickhouse/migrations/004_mcp_requests.sql (platform convention:
-- numbered migrations there, applied by hand; Vector does not create tables).
--
-- Apply:
--   docker exec -i clickhouse clickhouse-client \
--     --user=${CLICKHOUSE_USER} --password=${CLICKHOUSE_PASSWORD} \
--     --multiquery < migrations/004_mcp_requests.sql
--
-- One row per MCP JSON-RPC request through the gateway (cfde-mcp.cancerdatasci.org). Written by
-- the Vector transform in pipeline/vector/cfde-mcp.yaml, which keeps only these columns: no tool
-- arguments, results, error messages or raw IPs (D6). Column names follow the OTel MCP semconv
-- where one exists (mcp.method.name -> method, gen_ai.tool.name -> tool, mcp.protocol.version ->
-- protocol_version); the semconv is still in Development, so renames are cheap and expected.
-- Rows expire after 90 days; the daily rollup to Postgres analytics.mcp_* keeps aggregates.

CREATE TABLE IF NOT EXISTS mcp_requests (
    -- Gateway log time for the request (agentgateway `time`), UTC.
    `timestamp`          DateTime64(3, 'UTC'),
    -- Gateway route = which MCP server: reference, glygen, pwb, perturbseqr, cfde-mcp.
    `server`             LowCardinality(String),
    -- JSON-RPC method: initialize, tools/list, tools/call, server/discover, notifications/...
    `method`             LowCardinality(String),
    -- Tool name on tools/call, '' otherwise. Client-supplied, so unknown names appear too.
    `tool`               LowCardinality(String),
    -- http_error: HTTP >= 500, or >= 400 with no JSON-RPC error code (e.g. 401 missing key);
    -- rpc_error: JSON-RPC error (legacy: 200 + error; 2026-07-28: HTTP 400 + error);
    -- tool_error: result.isError = true; ok: everything else (isError absent counts as ok).
    `outcome`            Enum8('ok' = 1, 'tool_error' = 2, 'rpc_error' = 3, 'http_error' = 4),
    `http_status`        UInt16,
    -- JSON-RPC error code when outcome = rpc_error. -32601 on server/discover is a 2026-07-28
    -- client probing a legacy server: exclude it from error rates.
    `rpc_error_code`     Nullable(Int32),
    -- MCP-Protocol-Version header, or protocolVersion from the initialize body.
    `protocol_version`   LowCardinality(String),
    -- clientInfo.name/version. 2026-07-28 clients send it on every request; legacy clients only
    -- on initialize ('' on their later rows; use mcp_requests_attributed for the session join).
    `client_name`        LowCardinality(String),
    `client_version`     LowCardinality(String),
    -- HTTP User-Agent as sent (often just the HTTP library, e.g. python-httpx/0.28.1).
    `user_agent`         String,
    -- hex HMAC-SHA256(salt, client IP + '|' + User-Agent). Salt rotates monthly (GSM
    -- cfde-mcp-client-hash-signing-key), so this identifies a client within a month only.
    `client_hash`        FixedString(64),
    -- hex HMAC-SHA256(salt, 'session|' + Mcp-Session-Id token); '' for stateless 2026-07-28.
    -- Join key from a legacy session's initialize (which has clientInfo) to its later calls.
    `session_token_hash` String,
    -- Legacy (2025-11-25 and earlier) session traffic.
    `legacy_session`     Bool MATERIALIZED session_token_hash != '',
    `vector_received_at` DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (server, timestamp)
TTL toDate(timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- mcp_requests with client_name/version back-filled for legacy sessions from the session's
-- initialize row. attribution: 'request' (on the row itself), 'session' (from initialize via
-- session_token_hash) or 'none'. Success criterion: >= 80% of tools/call not 'none'.
CREATE OR REPLACE VIEW mcp_requests_attributed AS
SELECT
    r.timestamp, r.server, r.method, r.tool, r.outcome, r.http_status, r.rpc_error_code,
    r.protocol_version, r.user_agent, r.client_hash, r.session_token_hash, r.legacy_session,
    if(r.client_name != '', r.client_name, s.init_client_name)       AS client_name,
    if(r.client_name != '', r.client_version, s.init_client_version) AS client_version,
    multiIf(r.client_name != '', 'request', s.init_client_name != '', 'session', 'none') AS attribution
FROM mcp_requests AS r
LEFT JOIN
(
    SELECT
        session_token_hash,
        argMax(client_name, timestamp)    AS init_client_name,
        argMax(client_version, timestamp) AS init_client_version
    FROM mcp_requests
    WHERE method = 'initialize' AND session_token_hash != '' AND client_name != ''
    GROUP BY session_token_hash
) AS s ON r.session_token_hash = s.session_token_hash;
