-- 0001 — Raw layer for MCP package floor metrics (PyPI, npm, Docker Hub, MCP Registry).
--
-- Follows the cfde-atlas-etl convention: natural key + `source` jsonb exactly as fetched
-- + fetched_at, upserted ON CONFLICT so re-running a day is idempotent. Written by
-- collectors/src/cfde_collectors/downloads.py. Assumes the `raw` schema exists
-- (it does in cfde_atlas_dev). Apply with: psql "$DATABASE_URL" -f <this file>

CREATE TABLE IF NOT EXISTS raw.mcp_downloads (
    date        DATE        NOT NULL,
    registry    TEXT        NOT NULL,
    package     TEXT        NOT NULL,
    metric      TEXT        NOT NULL,
    value       BIGINT      NOT NULL,
    source      JSONB       NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, registry, package, metric)
);

COMMENT ON TABLE raw.mcp_downloads IS
    'Public download / pull counts for tracked MCP server packages, one row per '
    '(date, registry, package, metric). Use analytics.mcp_downloads_daily for queries.';

COMMENT ON COLUMN raw.mcp_downloads.registry IS 'pypi, npm, dockerhub or mcp_registry.';
COMMENT ON COLUMN raw.mcp_downloads.metric IS
    'downloads (pypi/npm, per day), pull_count (dockerhub, cumulative snapshot), '
    'versions_published (mcp_registry, snapshot).';
COMMENT ON COLUMN raw.mcp_downloads.source IS 'The upstream JSON fragment the value was read from.';
