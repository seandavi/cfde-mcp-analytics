# cfde-mcp-analytics

Usage metrics for MCP (Model Context Protocol) servers across the NIH Common Fund
Data Ecosystem (CFDE) — a "Google Analytics for MCP". Goal: consolidated usage
(tool calls, distinct clients, client apps, trends) across servers built by many
independent teams. Operational metrics (latency etc.) are secondary.

## Docs

### Research

| Doc | Status | Summary |
|-----|--------|---------|
| [MCP usage metrics: approaches](docs/research/mcp-usage-metrics.md) | done | Spec signals (2026-07-28 stateless MCP, `Mcp-Method`/`Mcp-Name` headers), OTel MCP semconv, analytics products, privacy, download/registry stats; recommends a gateway for remote servers, shared OTel schema, and download counts as a floor. |
| CFDE MCP server inventory (`docs/research/cfde-mcp-inventory.md`) | in progress | Existing CFDE / Common Fund MCP servers, remote vs. stdio, SDK, owners. |
| MCP gateways/proxies (`docs/research/mcp-gateways.md`) | in progress | Gateway comparison and POC recommendation. |

## Next

- POC: gateway fronting CFDE remote servers, with metrics, dashboard, and logging
  (no tool-argument logging by default).
