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
