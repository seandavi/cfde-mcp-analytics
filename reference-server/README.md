# cfde-reference-mcp

Trivial, deterministic MCP server used as ground truth for gateway metrics.

- Tools: `echo_upper`, `add`, `gene_symbol_lookup` (3-gene table), `always_fail` (always `isError`).
- Streamable HTTP at `/mcp`; `GET /health` returns `Healthy`. `HOST`/`PORT` env (default `127.0.0.1:8000`).
- One JSON line per `tools/call` on stdout: `ts`, `tool`, `outcome` (`ok`/`tool_error`/`rpc_error`),
  `client_name`, `client_version`, `protocol_version`. Arguments and results are never logged.
- `cfde-traffic URL [N] [auto|legacy]`: N calls per tool (legacy forces the 2025-11-25 initialize + session path) with clientInfo `cfde-traffic/0.1.0`; prints counts per tool/outcome.

From the repo root: `just serve`, `just traffic http://127.0.0.1:8000/mcp 10`, `just test`.
Docker: `docker build -t cfde-reference-mcp reference-server && docker run -p 8000:8000 cfde-reference-mcp`.
