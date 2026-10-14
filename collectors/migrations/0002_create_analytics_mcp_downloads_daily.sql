-- 0002 — Analytics view over raw.mcp_downloads.
--
-- Daily metrics (pypi/npm downloads) pass through. Cumulative snapshots (dockerhub
-- pull_count) also get daily_delta = change since the previous snapshot.

CREATE OR REPLACE VIEW analytics.mcp_downloads_daily AS
SELECT
    date,
    registry,
    package,
    metric,
    value,
    CASE
        WHEN metric = 'downloads' THEN value
        WHEN metric = 'pull_count'
            THEN value - LAG(value) OVER (PARTITION BY registry, package, metric ORDER BY date)
    END                 AS daily_delta,
    fetched_at          AS data_refreshed_at
FROM raw.mcp_downloads;

COMMENT ON VIEW analytics.mcp_downloads_daily IS
    'Floor usage metrics for CFDE-related MCP servers: package downloads and image pulls, '
    'one row per (date, registry, package, metric). These count installs, not MCP calls, '
    'and include CI and mirror noise; treat them as a lower-bound proxy for local (stdio) '
    'server usage. PyPI days with zero downloads have no row.';

COMMENT ON COLUMN analytics.mcp_downloads_daily.date IS
    'UTC calendar date. For downloads, the day counted; for snapshots, the day the snapshot was taken.';
COMMENT ON COLUMN analytics.mcp_downloads_daily.registry IS
    'Where the count comes from: pypi (pypistats.org, mirrors excluded), npm (api.npmjs.org), '
    'dockerhub (hub.docker.com pull_count) or mcp_registry (registry.modelcontextprotocol.io).';
COMMENT ON COLUMN analytics.mcp_downloads_daily.package IS
    'Package name as published: PyPI project, npm package (may be @scoped), Docker Hub namespace/repo, '
    'or MCP Registry server name.';
COMMENT ON COLUMN analytics.mcp_downloads_daily.metric IS
    'downloads = downloads on that day; pull_count = cumulative all-time Docker pulls at snapshot time; '
    'versions_published = number of versions of the server in the MCP Registry (no usage stats exist there).';
COMMENT ON COLUMN analytics.mcp_downloads_daily.value IS
    'Raw value of the metric. Do not SUM pull_count or versions_published across dates; they are cumulative.';
COMMENT ON COLUMN analytics.mcp_downloads_daily.daily_delta IS
    'Per-day count: equals value for downloads; change since the previous snapshot for pull_count '
    '(NULL on the first snapshot; after missed days it carries the whole gap''s pulls); NULL for versions_published. '
    'Safe to SUM over a date range.';
COMMENT ON COLUMN analytics.mcp_downloads_daily.data_refreshed_at IS
    'Timestamp of the most recent collector run that wrote this row.';
