# MCP gateways and proxies for CFDE usage metrics

Research date: 2026-10-14. Repo stats come from the GitHub API on that date. Every claim is cited; anything not verified against a primary source is marked **[unverified]**.

## 1. The spec change that shapes the design (MCP 2026-07-28)

The current MCP revision, 2026-07-28, changes what a gateway can and needs to see ([changelog][spec-changelog]):

- **No sessions and no handshake.** The revision drops `Mcp-Session-Id` and the `initialize`/`initialized` handshake. Each request now carries `_meta["io.modelcontextprotocol/protocolVersion"]` and client capabilities. Clients SHOULD send `io.modelcontextprotocol/clientInfo` on every request (SEP-2567, SEP-2575). A new `server/discover` RPC replaces the handshake for capability probing ([changelog][spec-changelog]).
- **Routing headers.** Every Streamable HTTP POST MUST carry `MCP-Protocol-Version` and `Mcp-Method`. `tools/call`, `resources/read` and `prompts/get` must also carry `Mcp-Name` (the tool name or resource URI). The spec says it mirrors these fields into headers "so that intermediaries (load balancers, gateways, observability tooling) can route and inspect requests without parsing the body." Servers MUST reject a request whose headers and body disagree, with `-32020 HeaderMismatch`. Non-ASCII names are sent as `=?base64?…?=` ([Streamable HTTP][spec-http]).
- **clientInfo is not a header.** It lives only in the JSON body `_meta` ([Streamable HTTP][spec-http] examples).
- **Other transport changes.** SSE resumability (`Last-Event-ID`) and the GET stream are removed. The old HTTP+SSE transport is formally Deprecated ([changelog][spec-changelog]). OpenTelemetry `traceparent` propagation in `_meta` is now documented (SEP-414) ([changelog][spec-changelog]).

What this means for CFDE metrics:
- **Sticky sessions.** These are only needed for legacy clients (2025-11-25 and earlier), which will remain common for a while.
- **"Distinct sessions" stops being a protocol concept.** Distinct clients have to be approximated by authenticated subject, or by a hashed (IP, User-Agent, clientInfo) tuple.
- **Errors are not visible in headers.** Tool execution errors come back as HTTP 200 with `result.isError: true`. JSON-RPC errors are also usually HTTP 200. Only validation, version and method-not-found failures use 400 or 404 ([Streamable HTTP][spec-http]; [agentgateway spec-compat][agw-speccompat]).

### Is header-only logging at nginx, Caddy or Cloudflare enough?

Only partly. Here is what a plain reverse proxy logging request headers and status can and cannot capture.

| Need | Header-only reverse proxy |
|---|---|
| Calls per server | Yes, when each server has its own path (`/srv-a/mcp`) |
| Calls per tool (`Mcp-Name`) | **Only 2026-07-28 clients.** Older clients send no `Mcp-Method` or `Mcp-Name`, since SEP-2243 is new in this revision ([changelog][spec-changelog]) |
| Client app | Only via `User-Agent` **[unverified that clients set a meaningful UA]**. `clientInfo` is in the body |
| Error rate | Only HTTP/transport errors. `isError` and JSON-RPC errors are in 200 bodies |
| Sessions | Legacy `Mcp-Session-Id` only. None for 2026-07-28 |

The verdict: header logging is a valid zero-dependency baseline, and it will improve as clients upgrade. A POC still needs body-aware parsing to get clientInfo, tool names from legacy clients, and error rates. That means an MCP-aware gateway, or a reverse proxy with body inspection (nginx njs, Lua, or a Caddy plugin) **[unverified effort]**.

## 2. Candidates

### Open source and self-hostable

**agentgateway** ([repo][agw-repo]). Apache-2.0, Rust, 5.3k stars. v1.6.0 shipped 2026-10-02, after v1.5.0 on 2026-08-27, with alphas and RCs in between, so releases come roughly monthly. It is a Linux Foundation project ([README][agw-repo]).
- **Deployment.** Runs as a standalone binary with YAML config, or on Kubernetes with a Gateway API controller ([README][agw-repo]).
- **Transports.** Supports stdio, HTTP, SSE and Streamable HTTP targets, so it can wrap stdio servers. Its docs have an `stdio: {cmd: npx …}` target example ([README][agw-repo]; [MCP observability][agw-obs]).
- **Topology.** You choose per backend. Several targets in one backend gives a federated endpoint, with tool names prefixed by target name by default (`prefixMode`). One backend per route gives separate paths ([configuration modes][agw-modes]).
- **Auth.** Supports JWT, API keys and OAuth, MCP authn, and CEL-based tool authz ([README][agw-repo]). The docs say that if users hold their own upstream OAuth credentials, you should **not** multiplex, because a federated client "has no way to run a separate authorization flow for every upstream server". Expose separate paths instead, or use ID-JAG token exchange ([configuration modes][agw-modes]).
- **Spec support.** 2026-07-28 is supported by default, with automatic translation to and from legacy servers and clients. A federated endpoint negotiates the intersection of versions across its targets ([spec-compat][agw-speccompat]). `statefulMode` and `sessionRouting` control legacy session handling ([spec-compat][agw-speccompat]).
- **Observability.** This is the best fit for CFDE:
  - Prometheus exposes `mcp_requests_total{server,method,resource,resource_type}` on `:15020/metrics`.
  - OTLP traces.
  - Structured access logs include `mcp.method.name`, `mcp.target`, `gen_ai.tool.name` and `mcp.session.id`.
  - **Tool arguments and results are not logged by default.** You must add them explicitly with CEL (`mcp.tool.arguments`) ([MCP observability][agw-obs]).
  - Access logs can go to SQLite or Postgres, which powers the built-in UI analytics ([log DB][agw-logdb]).
  - A pre-built Grafana dashboard covers MCP traffic on Kubernetes. Binary deployments get PromQL examples instead ([Grafana][agw-grafana]).
- **Gap.** No documented `clientInfo` label or CEL variable, so client app attribution needs User-Agent or a custom CEL field **[unverified]** ([CEL variables][agw-cel]).

**IBM ContextForge** ([repo][cf-repo]). Apache-2.0, Python, 4.6k stars. v1.0.11 shipped 2026-09-28 and v1.0.7 through v1.0.10 shipped August to September, so patches arrive every 1–3 weeks ([changelog][cf-changelog]).
- **What it is.** A registry and federation proxy for MCP, A2A and REST/gRPC ([README][cf-repo]).
- **Transports.** HTTP, JSON-RPC, WebSocket, SSE and Streamable HTTP. A `mcpgateway.translate` utility wraps stdio servers and exposes them as SSE or Streamable HTTP ([README][cf-repo]).
- **Multiplexing.** Upstream "gateways" are federated into "virtual servers" (`/servers/<UUID>/mcp`). Tool names become `<gateway-slug><sep><tool>` to avoid collisions ([ADR-011][cf-adr11]).
- **Observability:**
  - Prometheus at `/metrics/prometheus`, which needs a JWT for scraping ([Prometheus doc][cf-prom]).
  - OTel/OTLP tracing ([README][cf-repo]).
  - An admin UI with a Tools dashboard (most used, slowest, most error-prone), backed by DB execution metrics (`DB_METRICS_RECORDING_ENABLED`, default true) ([internal observability][cf-internal]).
- **Auth.** Supports user-scoped OAuth tokens and an `X-Upstream-Authorization` passthrough ([README][cf-repo]). Full 2026-07-28 authorization is still an open issue ([#6639][cf-6639]).
- **Spec support.** In v1.0.11, 2026-07-28 is opt-in (`MCP_INBOUND_PROTOCOL_MODE=auto`). It becomes default-on in Unreleased ([changelog][cf-changelog]).
- **Sessions.** Has Redis-backed session affinity for legacy stateful sessions ([changelog][cf-changelog]).
- **Caveats.** It is heavy: the compose stack is Postgres ("55+ tables") plus Redis ([README][cf-repo]). Rewritten tool names change what clients see.

**sparfenyuk/mcp-proxy** ([repo][mcpproxy-repo]). MIT, Python, 2.8k stars, v0.13.0 shipped 2026-10-10.
- A transport bridge. It turns stdio into SSE or Streamable HTTP (`--named-server` gives `/servers/<name>/`, one route per server, no aggregation), and SSE back into stdio. It supports `--stateless` ([README][mcpproxy-repo]).
- No metrics. It is useful only as a stdio wrapper behind a metrics gateway.

**FastMCP proxy** ([repo][fastmcp-repo]; [docs][fastmcp-proxy]). Apache-2.0, Python, 28k stars, v4.1.0 shipped 2026-10-08.
- `create_proxy()` bridges stdio, SSE and HTTP in any direction, and gives each request a fresh backend session by default. A multi-server config prefixes tools as `{prefix}_{name}`, and `server.mount()` composes servers ([proxy docs][fastmcp-proxy]).
- It forwards incoming `Authorization` to HTTP backends by default ([proxy docs][fastmcp-proxy]).
- It is a library, not a gateway product. You would have to write your own metrics middleware.

**MetaMCP** ([repo][metamcp-repo]). MIT, TypeScript, 2.7k stars.
- The last release was v2.4.22 on 2025-12-19 and the last push was 2026-06, so it is slowing.
- It aggregates servers into namespaces and endpoints (SSE, Streamable HTTP, OpenAPI), wraps stdio, and offers API-key or MCP OAuth (2025-06-18) ([README][metamcp-repo]).
- No documented Prometheus or OTel. No 2026-07-28 issues found.

**Unla** ([repo][unla-repo]). MIT, 2.2k stars, v0.10.0 shipped 2026-08-04.
- It converts REST to MCP and proxies MCP servers over SSE and Streamable HTTP.
- Aggregation is an **unchecked** roadmap item ([README][unla-repo]).
- 2026 stateless support was merged on 2026-08-04 ([PR #324][unla-324]).
- No documented metrics export.

**Docker MCP Gateway** ([repo][docker-repo]). MIT, Go, 1.6k stars, tag v0.44.1.
- It runs catalog servers as containers and serves them over stdio, SSE or streaming. It needs Docker Desktop 4.59+ with MCP Toolkit ([README][docker-repo]).
- "Built-in logging and call tracing" ([README][docker-repo]), but no documented Prometheus support **[unverified]**.
- It is aimed at a developer's desktop, not a central service.

**Microsoft MCP Gateway** ([repo][ms-repo]). MIT, C#, 878 stars, no tagged releases.
- A Kubernetes-native reverse proxy with `/adapters/{name}/mcp` routes, one per server, plus a tool router at `/mcp` ([README][ms-repo]).
- **It now requires 2026-07-28 clients and drops legacy initialization and sessions entirely** ([README][ms-repo]). That would break today's mixed client population.
- Telemetry is described only as "integration points" ([README][ms-repo]).

**Lasso MCP Gateway** ([repo][lasso-repo]). MIT, Python, 396 stars.
- Last release v1.2.0 on 2026-01-21. It is security-focused, with guardrail plugins and risk scoring ([README][lasso-repo]).
- Effectively stale. No 2026-07-28 activity found.

**tbxark/mcp-proxy** ([repo][tbxark-repo]). MIT, Go, 737 stars, v1.1.0.
- It aggregates stdio, SSE and HTTP servers, and can hold upstream OAuth on behalf of callers ([README][tbxark-repo]).
- No documented metrics.

**Pomerium** ([repo][pom-repo]; [MCP docs][pom-mcp]). Apache-2.0, Go, 5.0k stars, v0.33.4.
- An identity-aware proxy with MCP support. Clients see only Pomerium-issued tokens, and Pomerium runs the upstream OAuth itself (static, or auto-discovered via Protected Resource Metadata or CIMD/DCR) ([MCP docs][pom-mcp]; [changelog][pom-changelog]).
- Per-tool-call metrics **[unverified]**.

**LiteLLM** ([repo][litellm-repo]; [MCP docs][litellm-mcp]). 61k stars. GitHub reports the license as "NOASSERTION": the core is MIT, with a separate enterprise directory **[unverified]**.
- It is an LLM gateway that also offers an MCP gateway, with stdio, SSE and HTTP upstreams behind one fixed endpoint ([MCP docs][litellm-mcp]).
- Stateless 2026-07-28 support is still in open PRs ([#46264][litellm-46264]).
- No MCP-specific Prometheus metrics found **[unverified]**. It is overkill if no LLM routing is needed.

**Agent Router (formerly Envoy AI Gateway)** ([repo][ar-repo]). Apache-2.0, Go, v1.2.0. The repo moved from `envoyproxy/ai-gateway` to the Agentic AI Foundation ([README][ar-repo]).
- It routes LLM and MCP traffic on top of Envoy Gateway and requires Kubernetes ([README][ar-repo]).
- MCP metric details were not reviewed **[unverified]**.

### Commercial or hosted (not a fit for an OSS self-hosted POC)

- **Kong AI MCP Proxy.** "Only available as part of our AI Gateway Enterprise offering", Kong 3.12+. Its `passthrough-listener` mode fronts an existing MCP server and emits MCP metrics ([plugin docs][kong-plugin]). The metrics include `kong_ai_mcp_latency_ms` with `method` and `tool_name` labels ([Kong MCP observe][kong-observe]).
- **Cloudflare MCP server portals.** One endpoint (`https://<sub>.<domain>/mcp`) in front of up to 80 remote HTTP servers. Stdio must be self-hosted behind HTTP. Upstream OAuth works via DCR or manual credentials, and can be per-user ("Require user auth"). Logs record Time, Status, Server, Capability (tool) and Duration. Logpush export is Enterprise-only, and OTel is not mentioned ([portal docs][cf-portals]).
- **Traefik Hub MCP Gateway.** A Hub feature (`hub.mcpgateway.enabled`) with JWT, tool filtering, OAuth resource discovery and OTel ([getting started][traefik-mcp]). Paid status comes only from a competitor page **[unverified]**.
- **Azure API Management.** Can "expose and govern an existing MCP server", as long as it is 2025-06-18 or later. Tools and resources only, no prompts ([APIM existing server][apim-existing]; [overview][apim-overview]).
- **Apigee.** Exposes *existing REST APIs* as MCP tools (`tools/list`, `tools/call`). It is not a proxy for existing MCP servers per the overview ([Apigee MCP overview][apigee-mcp]).
- **AWS AgentCore Gateway.** Managed, with MCP-server targets plus Lambda and OpenAPI targets. The official observability docs were not reviewed **[unverified]** ([AWS blog repost][agentcore-blog]).

## 3. Comparison table

| Gateway | License / host | Language | Latest release | stdio wrap | Per-server routes | Aggregate (collision handling) | Prometheus / OTel | Per-call logs, args off by default | Admin UI | 2026-07-28 |
|---|---|---|---|---|---|---|---|---|---|---|
| agentgateway | Apache-2.0, self | Rust | v1.6.0, 2026-10-02 | Yes | Yes | Yes (target prefix) | Yes / Yes | Yes / Yes | Yes (+DB analytics) | Yes, bridges legacy |
| ContextForge | Apache-2.0, self | Python | v1.0.11, 2026-09-28 | Yes (translate) | Via virtual servers | Yes (slug prefix) | Yes / Yes | Yes / ? | Yes (tools dashboard) | Opt-in |
| sparfenyuk/mcp-proxy | MIT, self | Python | v0.13.0, 2026-10-10 | Yes | Yes | No | No | No | No | Unclear |
| FastMCP proxy | Apache-2.0, lib | Python | v4.1.0, 2026-10-08 | Yes | DIY | Yes (`prefix_`) | DIY | DIY | No | In progress |
| MetaMCP | MIT, self | TS | v2.4.22, 2025-12 | Yes | Per endpoint | Yes (namespaces) | No | ? | Yes | No |
| Unla | MIT, self | (GitHub reports TS) | v0.10.0, 2026-08 | ? | Yes | Roadmap | No | ? | Yes | Yes |
| Docker MCP GW | MIT, self | Go | v0.44.1 tag | Yes (containers) | No | Yes | ? | Logs | Desktop | ? |
| Microsoft MCP GW | MIT, self (K8s) | C# | none | No | Yes | Tool router | "integration points" | ? | No | **Only** |
| Pomerium | Apache-2.0, self | Go | v0.33.4 | No | Yes | No | ? | ? | No | ? |
| Kong AI MCP Proxy | Enterprise | Lua | 3.12+ | No | Yes | Yes (listener) | Yes / Konnect | Audit log | Konnect | ? |
| Cloudflare portals | SaaS | — | — | No | No (1 URL) | Yes | No / No (Logpush Ent.) | Yes | Yes | ? |

`?` means not documented or not verified.

## 4. Architectural questions for CFDE

**(a) Fronting servers that teams already host.** A reverse proxy at `mcp.cfde.example/<server>/mcp` that forwards the client's `Authorization` header unchanged keeps each team's OAuth intact, with one caveat. MCP OAuth binds tokens to the resource URL through Protected Resource Metadata, and clients key credentials by issuer ([changelog][spec-changelog]). The proxied URL is a *different resource*, so the upstream server's `WWW-Authenticate` and PRM `resource` value must match the gateway URL, or the audience check fails **[unverified per server; test with each team]**. agentgateway's guidance is to use separate paths, not multiplexing, for user-held OAuth ([configuration modes][agw-modes]). Unauthenticated public servers, likely most CFDE data APIs, carry no such risk. The gateway only measures traffic that uses the CFDE URL, so teams must publish the CFDE URL as canonical. Traffic to their original URL stays invisible.

**(b) Local stdio servers.** agentgateway `stdio` targets, ContextForge `translate`, `mcp-proxy --named-server` or FastMCP can each run these centrally as remote servers. CFDE then becomes the operator: compute, secrets, uptime, and per-user data isolation. Servers that read local files or user credentials cannot move this way. Usage of stdio installs that users run locally stays invisible to any gateway.

**(c) One aggregated endpoint or per-server routes.** One endpoint is simpler for users, but it has costs:
- It breaks per-user upstream OAuth ([configuration modes][agw-modes]).
- It renames tools (`server_tool`).
- It puts every tool in one `tools/list`, which uses up client context ([configuration modes][agw-modes]).
- It negotiates only the lowest common protocol version ([spec-compat][agw-speccompat]).

Attribution survives either way in agentgateway, because the `server`/`mcp.target` label identifies the upstream ([MCP observability][agw-obs]). Per-server routes additionally give attribution by URL path at plain HTTP level. **Recommendation:** use per-server routes as the canonical surface, and optionally add an aggregated `/all/mcp` over the unauthenticated servers.

## 5. POC recommendation

Ranked for a small academic team that wants self-hosted OSS, native OTel/Prometheus, Grafana and request logs, with privacy-safe defaults.

1. **agentgateway.** A single static binary and a YAML file. It is the only candidate with a documented per-tool Prometheus counter labeled by server and tool. Arguments are off by default. It handles legacy and 2026-07-28 clients and servers transparently, has stdio targets, and supports per-path or federated topologies. The gap is clientInfo attribution; add a CEL log field, or fall back to User-Agent.
2. **IBM ContextForge.** The richest built-in dashboard and registry. Choose it if CFDE wants a catalog and admin UI more than a lean proxy. It needs Postgres and Redis, the modern spec is opt-in, and federation rewrites tool names.
3. **Baseline control: Caddy or nginx header logging,** with `mcp-proxy` for any stdio servers. Run it alongside one of the above to quantify what an MCP-aware gateway adds. It is free once all clients reach 2026-07-28.

### POC architecture

```
 MCP clients (Claude, Cursor, VS Code, custom agents)
        |  https://mcp.cfde.example/<server>/mcp   (+ optional /all/mcp)
        v
 +------------------------------+     OTLP traces     +------------------+
 | agentgateway (1 replica)     |-------------------->| OTel Collector    |
 |  routes: 1 per CFDE server   |                     |  -> Tempo/Jaeger |
 |  access log -> Postgres/JSON |---- logs ---------->|  -> Loki/DuckLake |
 |  :15020/metrics              |                     +------------------+
 +--+-----------+-----------+---+          ^ scrape
    |           |           |         +----+------+    +---------+
    v           v           v         | Prometheus |--->| Grafana |
 remote A    remote B    stdio C      +-----------+    +---------+
 (team-     (team-      (run by
  hosted)    hosted)     gateway)
```

- Run a single replica, so legacy `Mcp-Session-Id` affinity is not an issue (`statefulMode` at defaults).
- Pass through upstream auth on per-server routes. Do not enable argument or result logging.
- Hash client IPs in the log pipeline. Keep raw logs for a short window, for example 30 days, and keep aggregates long term.
- Land logs in the platform DuckLake per `infrastructure/DUCKLAKE.md`, and register the gateway with the always-on observability convention (`OBSERVABILITY.md`).

**Metrics and dimensions:**
- `mcp_requests_total` by server, method, tool (`resource`) and `resource_type` ([MCP observability][agw-obs]).
- Plus derived:
  - Status class
  - Tool error (`isError`, needs a CEL field **[unverified]**)
  - Protocol version (`MCP-Protocol-Version` header)
  - Client app (clientInfo `name`/`version`, falling back to User-Agent)
  - Distinct clients per day (hashed IP+UA, or auth subject)
  - Legacy session count
  - Day/week for trends

**Success criteria:**
- At least 3 CFDE servers (at least 1 OAuth-protected, at least 1 stdio-hosted) reachable via stable CFDE URLs, with zero client-visible breakage.
- Per-server and per-tool call counts in Grafana that agree within 5% with a server-side count from one cooperating team.
- Client app attributed for at least 80% of calls.
- No tool arguments stored anywhere.
- Gateway overhead not noticeable to users (latency is low priority, so this is a sanity check only).
- At least one team agrees to publish the CFDE URL as canonical.

## Sources

[spec-changelog]: https://modelcontextprotocol.io/specification/2026-07-28/changelog
[spec-http]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
[agw-repo]: https://github.com/agentgateway/agentgateway
[agw-obs]: https://github.com/agentgateway/website/blob/main/content/docs/standalone/1.5.x/documentation/mcp/mcp-observability.md
[agw-modes]: https://github.com/agentgateway/website/blob/main/content/docs/standalone/1.5.x/documentation/mcp/configuration-modes.md
[agw-speccompat]: https://github.com/agentgateway/website/blob/main/assets/agw-docs/pages/agentgateway/mcp/spec-compatibility.md
[agw-logdb]: https://github.com/agentgateway/website/blob/main/content/docs/standalone/1.5.x/documentation/observability/access-logs/database.md
[agw-grafana]: https://github.com/agentgateway/website/blob/main/content/docs/standalone/1.5.x/documentation/observability/metrics/grafana.md
[agw-cel]: https://github.com/agentgateway/website/blob/main/content/docs/standalone/1.5.x/reference/cel/variables.md
[cf-repo]: https://github.com/IBM/mcp-context-forge
[cf-changelog]: https://github.com/IBM/mcp-context-forge/blob/main/CHANGELOG.md
[cf-adr11]: https://github.com/IBM/mcp-context-forge/blob/main/docs/docs/architecture/adr/011-tool-federation.md
[cf-prom]: https://github.com/IBM/mcp-context-forge/blob/main/docs/docs/manage/observability/prometheus.md
[cf-internal]: https://github.com/IBM/mcp-context-forge/blob/main/docs/docs/manage/observability/internal-observability.md
[cf-6639]: https://github.com/IBM/mcp-context-forge/issues/6639
[mcpproxy-repo]: https://github.com/sparfenyuk/mcp-proxy
[fastmcp-repo]: https://github.com/PrefectHQ/fastmcp
[fastmcp-proxy]: https://gofastmcp.com/servers/providers/proxy
[metamcp-repo]: https://github.com/metatool-ai/metamcp
[unla-repo]: https://github.com/AmoyLab/Unla
[unla-324]: https://github.com/AmoyLab/Unla/pull/324
[docker-repo]: https://github.com/docker/mcp-gateway
[ms-repo]: https://github.com/microsoft/mcp-gateway
[lasso-repo]: https://github.com/lasso-security/mcp-gateway
[tbxark-repo]: https://github.com/tbxark/mcp-proxy
[pom-repo]: https://github.com/pomerium/pomerium
[pom-mcp]: https://docs.pomerium.com/docs/capabilities/mcp
[pom-changelog]: https://www.pomerium.com/changelog/mcp-upstream-oauth-dynamic-client-registration-route-discovery
[litellm-repo]: https://github.com/BerriAI/litellm
[litellm-mcp]: https://docs.litellm.ai/docs/mcp
[litellm-46264]: https://github.com/BerriAI/litellm/pull/46264
[ar-repo]: https://github.com/theagentrouter/agent-router
[kong-plugin]: https://developer.konghq.com/plugins/ai-mcp-proxy/
[kong-observe]: https://developer.konghq.com/mcp/observe-traffic-for-mcp-tools/
[cf-portals]: https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/
[traefik-mcp]: https://doc.traefik.io/traefik-hub/mcp-gateway/guides/getting-started
[apim-existing]: https://learn.microsoft.com/azure/api-management/expose-existing-mcp-server
[apim-overview]: https://learn.microsoft.com/azure/api-management/mcp-server-overview
[apigee-mcp]: https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-overview
[agentcore-blog]: https://aihub.hkuspace.hku.hk/2026/06/02/extending-mcp-support-for-amazon-bedrock-agentcore-gateway/

- MCP spec 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- MCP Streamable HTTP (2026-07-28): https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- agentgateway: https://github.com/agentgateway/agentgateway. Docs source: https://github.com/agentgateway/website (pages linked above)
- IBM ContextForge: https://github.com/IBM/mcp-context-forge (README, CHANGELOG, ADR-011, Prometheus and internal observability docs)
- sparfenyuk/mcp-proxy: https://github.com/sparfenyuk/mcp-proxy
- FastMCP: https://github.com/PrefectHQ/fastmcp, https://gofastmcp.com/servers/providers/proxy
- MetaMCP: https://github.com/metatool-ai/metamcp
- Unla: https://github.com/AmoyLab/Unla, PR https://github.com/AmoyLab/Unla/pull/324
- Docker MCP Gateway: https://github.com/docker/mcp-gateway
- Microsoft MCP Gateway: https://github.com/microsoft/mcp-gateway
- Lasso MCP Gateway: https://github.com/lasso-security/mcp-gateway
- tbxark/mcp-proxy: https://github.com/tbxark/mcp-proxy
- Pomerium: https://github.com/pomerium/pomerium, https://docs.pomerium.com/docs/capabilities/mcp, https://www.pomerium.com/changelog/mcp-upstream-oauth-dynamic-client-registration-route-discovery
- LiteLLM: https://github.com/BerriAI/litellm, https://docs.litellm.ai/docs/mcp, https://github.com/BerriAI/litellm/pull/46264
- Agent Router (formerly Envoy AI Gateway): https://github.com/theagentrouter/agent-router
- Kong: https://developer.konghq.com/plugins/ai-mcp-proxy/, https://developer.konghq.com/mcp/observe-traffic-for-mcp-tools/
- Cloudflare MCP portals: https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/
- Traefik Hub: https://doc.traefik.io/traefik-hub/mcp-gateway/guides/getting-started
- Azure APIM: https://learn.microsoft.com/azure/api-management/expose-existing-mcp-server, https://learn.microsoft.com/azure/api-management/mcp-server-overview
- Apigee: https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-overview
- AWS AgentCore (secondary repost, not official docs): https://aihub.hkuspace.hku.hk/2026/06/02/extending-mcp-support-for-amazon-bedrock-agentcore-gateway/
