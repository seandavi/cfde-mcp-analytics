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
| [CFDE MCP server inventory](docs/research/cfde-mcp-inventory.md) | done | As of 2026-10-14: 4 live official/affiliated servers, all remote (cfde-mcp, GlyGen, Playbook Workflow Builder, PerturbSeqr); 1 stdio-only (Bridge2AI Standards Explorer); DDKG in development. 3 of 4 live are Ma'ayan Lab TypeScript. None has usage telemetry. Most DCC data over MCP flows through third-party wrappers. |
| [MCP gateways/proxies](docs/research/mcp-gateways.md) | done | Compares ~15 gateways. POC pick: agentgateway (Prometheus `mcp_requests_total` by server/tool, OTel, stdio hosting); runner-up IBM ContextForge (built-in dashboard); plain Caddy/nginx header logging as a control. Per-server routes, no aggregated endpoint for OAuth servers. |

## Next

- POC: gateway fronting CFDE remote servers, with metrics, dashboard, and logging
  (no tool-argument logging by default).
