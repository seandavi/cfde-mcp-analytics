# cfde-mcp-analytics

Usage metrics for MCP (Model Context Protocol) servers across the NIH Common Fund
Data Ecosystem (CFDE) — a "Google Analytics for MCP". Goal: consolidated usage
(tool calls, distinct clients, client apps, trends) across servers built by many
independent teams. Operational metrics (latency etc.) are secondary.

## Components

- [`reference-server/`](reference-server/): `cfde-reference-mcp`, a trivial MCP server with a ground-truth
  per-call log, plus the `cfde-traffic` generator. `just lint | typecheck | test | serve | traffic URL N`.
- [`gateway/`](gateway/): agentgateway v1.6.0 config fronting GlyGen, PWB and PerturbSeqr, with JSON access
  log fields for tool, clientInfo, protocol version and errors. How to run it: [gateway/README.md](gateway/README.md).

## Docs

### Research

| Doc | Status | Summary |
|-----|--------|---------|
| [MCP usage metrics: approaches](docs/research/mcp-usage-metrics.md) | done | Spec signals (2026-07-28 stateless MCP, `Mcp-Method`/`Mcp-Name` headers), OTel MCP semconv, analytics products, privacy, download/registry stats; recommends a gateway for remote servers, shared OTel schema, and download counts as a floor. |
| [CFDE MCP server inventory](docs/research/cfde-mcp-inventory.md) | done | As of 2026-10-14: 4 live official/affiliated servers, all remote (cfde-mcp, GlyGen, Playbook Workflow Builder, PerturbSeqr); plus GenSeCo (KC, Broad; remote-capable, hosted URL unknown); 1 stdio-only (Bridge2AI Standards Explorer); DDKG in development. 3 of 4 live are Ma'ayan Lab TypeScript. None has usage telemetry. Most DCC data over MCP flows through third-party wrappers. |
| [MCP gateways/proxies](docs/research/mcp-gateways.md) | done | Compares ~15 gateways. POC pick: agentgateway (Prometheus `mcp_requests_total` by server/tool, OTel, stdio hosting); runner-up IBM ContextForge (built-in dashboard); plain Caddy/nginx header logging as a control. Per-server routes, no aggregated endpoint for OAuth servers. |

### Spikes

| Doc | Status | Summary |
|-----|--------|---------|
| [agentgateway spike (Phase 1)](docs/spike-agentgateway.md) | done | **GO on agentgateway (D1).** Per-tool counts in the log match `agentgateway_mcp_requests_total` exactly; clientInfo name/version is logged through CEL for both 2025-11-25 (via a session join) and 2026-07-28 clients (100% of calls attributed); `isError` and JSON-RPC errors each get their own field. Both protocol generations work. No arguments or results appear in logs, metrics or traces once the default `mcp.error.message` field is removed (it leaks argument echoes). |

### Plan

- [POC plan: CFDE MCP gateway with usage metrics](docs/poc-plan.md): design,
  decisions, phases (GitHub milestones), success criteria.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). License: [MIT](LICENSE).
