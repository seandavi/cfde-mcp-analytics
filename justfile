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

traffic URL="http://127.0.0.1:8000/mcp" N="10":
    uv run cfde-traffic {{URL}} {{N}}

# Floor metrics (PyPI/npm/Docker Hub/MCP Registry). `just collect-downloads --dry-run` prints JSON;
# without it, upserts into raw.mcp_downloads at $DATABASE_URL.
collect-downloads *ARGS:
    uv run --directory ../collectors cfde-collect-downloads {{ARGS}}
