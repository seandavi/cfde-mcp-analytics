FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY README.md ./
COPY src ./src
# non-editable: the package is installed into the venv, readable by `nobody`
RUN uv sync --locked --no-editable
ENV HOST=0.0.0.0 PORT=8000 PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
USER nobody
CMD ["cfde-reference-mcp"]
