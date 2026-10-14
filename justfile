set working-directory := "reference-server"

lint:
    uv run ruff check .
    uv run ruff format --check .

typecheck:
    uv run pyright

test:
    uv run pytest -q

serve:
    uv run cfde-reference-mcp

# MODE: auto (2026-07-28 when the server supports it) or legacy (2025-11-25 initialize + session).
traffic URL="http://127.0.0.1:8000/mcp" N="10" MODE="auto":
    uv run cfde-traffic {{URL}} {{N}} {{MODE}}

# Floor metrics (PyPI/npm/Docker Hub/MCP Registry). `just collect-downloads --dry-run` prints JSON;
# without it, upserts into raw.mcp_downloads at $DATABASE_URL.
collect-downloads *ARGS:
    uv run --directory ../collectors cfde-collect-downloads {{ARGS}}

# Daily gateway rollup: ClickHouse mcp_requests -> Postgres raw.mcp_daily_calls / raw.mcp_clients_monthly.
# Needs CLICKHOUSE_URL/USER/PASSWORD and DATABASE_URL; `--dry-run` prints rows instead of writing.
rollup-mcp *ARGS:
    uv run --directory ../collectors cfde-rollup-mcp {{ARGS}}

# Vector transform unit tests (privacy guard, outcome mapping) in the pinned Vector image.
vector-test:
    docker run --rm --network none -e CFDE_MCP_HMAC_SALT=test-salt-not-secret -e CLICKHOUSE_DB=default \
      -e CLICKHOUSE_USER=x -e CLICKHOUSE_PASSWORD=x -v "{{justfile_directory()}}/pipeline/vector:/etc/vector:ro,z" \
      timberio/vector:0.45.0-debian test /etc/vector/cfde-mcp.yaml
