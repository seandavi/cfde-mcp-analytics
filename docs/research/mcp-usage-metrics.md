# Usage metrics for distributed MCP servers ("Google Analytics for MCP")

*Researched 2026-10-14 against primary sources. Unverified items are marked **[unverified]**.*

## TL;DR

- **The protocol changed under us.** The current MCP revision, **2026-07-28**, removed the `initialize` handshake and protocol-level sessions (`Mcp-Session-Id`). Client identity now arrives on *every request* as `_meta["io.modelcontextprotocol/clientInfo"]`, and Streamable HTTP requests carry `Mcp-Method`/`Mcp-Name` headers that are meant for gateways and observability tools ([versioning](https://modelcontextprotocol.io/specification/versioning), [basic/_meta](https://modelcontextprotocol.io/specification/2026-07-28/basic/index), [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)). Older clients still use 2025-11-25 sessions, so for now any design has to handle both.
- **OTel has MCP semantic conventions**, but their status is **Development**. They cover `mcp.method.name`, `gen_ai.tool.name`, `mcp.session.id`, `error.type` and related attributes. They have **no attribute for the client application name/version**, which is exactly the "Claude vs Cursor vs VS Code" dimension we need ([semconv-genai mcp.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md)).
- **SDKs now emit these spans natively.** That includes the Python `mcp` SDK v2.x and FastMCP. Both default to no-op unless an OTel SDK and exporter are installed ([python-sdk docs](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/opentelemetry.md), [FastMCP telemetry](https://gofastmcp.com/servers/telemetry)). I found no native span emission in the TypeScript SDK.
- **Recommendation:** a small CFDE event schema that is a *subset of OTel MCP semconv plus two `cfde.*` attributes*, delivered as OTLP to one central collector. A ~50-line drop-in for FastMCP/Python and TypeScript adds client name and an anonymised client hash, ships with an opt-out env var, and sends no arguments. Teams that can't phone home export daily aggregates in the same schema. Package download stats and registry stats are the floor for every server.

---

## 1. What the MCP spec gives you

| Signal | 2025-11-25 (handshake era) | 2026-07-28 (current, stateless) |
|---|---|---|
| Client app name/version | `clientInfo` (`name`, `title`, `version`, …) in the `initialize` request, sent once ([lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)) | `_meta["io.modelcontextprotocol/clientInfo"]` on every request. Clients **SHOULD** include it "unless specifically configured not to" ([basic](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)) |
| Session | Server **MAY** mint `MCP-Session-Id` (Streamable HTTP only) ([transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)) | Removed. Servers should ignore the header and not mint one ([Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http); [SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2567-sessionless-mcp.md), [SEP-2575](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2575-stateless-mcp.md)) |
| Method / tool name visible to proxies | Only by parsing the JSON body | `Mcp-Method` and `Mcp-Name` headers are **required**, and servers must check them against the body ([SEP-2243](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2243-http-standardization.md)) |
| Trace context | Convention via SEP-414 | `traceparent`/`tracestate`/`baggage` are reserved `_meta` keys ([basic](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)) |

Points that matter for metrics:

- **`clientInfo` is self-reported and unverified.** The spec says it is "intended for display, logging, and debugging" ([basic](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)). That is fine for coarse client-mix charts and useless for security.
- **"Sessions" were never a reliable user proxy.** SEP-2567 notes that clients scoped sessions "per tool call, … per application launch, … per page load". Under the current spec a stdio connection "is not a conversation or session" ([SEP-2567](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2567-sessionless-mcp.md), [basic](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)). **Don't build "sessions" or "active users" metrics on `Mcp-Session-Id`.** For distinct clients, use a privacy-preserving hash (§5).
- **stdio vs remote.** With stdio, "the client launches the MCP server as a subprocess" and talks over stdin/stdout ([transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)). Three things follow:
  1. Nothing crosses the network, so no gateway or proxy can observe it.
  2. Data leaves the machine only if the server process itself phones home.
  3. Each install is on a user's laptop, so phoning home is "telemetry in a locally-installed package", with the consent norms covered in §5.

  Remote Streamable HTTP servers run on infrastructure the team controls. They can log everything server-side, and with the new headers a reverse proxy can count tool calls without parsing bodies.
- **Spec-level telemetry work.** No SEP defines a usage-telemetry *reporting* channel. The relevant spec work is SEP-414 (trace context in `_meta`), SEP-2243 (headers for intermediaries), and the deprecation of MCP protocol logging in favour of stderr/OTel (SEP-2577, referenced in the [TS SDK docs](https://github.com/modelcontextprotocol/typescript-sdk/tree/main/docs)). A search of spec-repo issues for "telemetry" turned up only closed, tangential items ([search](https://github.com/modelcontextprotocol/modelcontextprotocol/issues?q=telemetry)).

## 2. OpenTelemetry

**MCP semconv.** These now live in [open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai); the old opentelemetry.io page says they "have moved" ([old page](https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/)). The status is **Development** for the document and every `mcp.*` attribute ([mcp.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md), [registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/registry/attributes/mcp.md)). The repo publishes no releases yet.

- **Spans:** `mcp.client` and `mcp.server` spans are named `{mcp.method.name} {target}`, for example `tools/call get_weather`.
- **Required attributes:** `mcp.method.name`.
- **Conditionally required:** `gen_ai.tool.name`, `gen_ai.prompt.name`, `mcp.resource.uri`, `error.type`, `rpc.response.status_code`, `jsonrpc.request.id`.
- **Recommended:** `mcp.protocol.version`, `mcp.session.id`, `gen_ai.operation.name=execute_tool`, `network.transport` (`pipe` for stdio), `client.address`, `server.address`.
- **Opt-In:** `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`. Arguments are therefore off by default *by spec*.
- **Errors:** `error.type="tool_error"` when `CallToolResult.isError` is true.
- **Metrics:** histograms `mcp.{client,server}.operation.duration` and `mcp.{client,server}.session.duration`. A count of calls can be derived from the duration histogram.
- **Gap:** there is no attribute for the MCP client implementation name/version (from `clientInfo`). I found no open issue proposing one in either semconv repo ([search](https://github.com/open-telemetry/semantic-conventions-genai/issues?q=clientInfo)). We need a custom attribute.

**SDKs.**

- **Python `mcp` SDK v2.x:** "Every server you create emits an OpenTelemetry span for every message it handles". It depends only on `opentelemetry-api`, so spans are no-ops until an SDK and exporter are configured. Attributes are `mcp.method.name`, `mcp.protocol.version`, `jsonrpc.request.id`, `gen_ai.tool.name`, `gen_ai.operation.name`, and `error.type`. Client name is not recorded ([docs](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/opentelemetry.md), [src/mcp/server/_otel.py](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/_otel.py)). This is new in v2: `_otel.py` doesn't exist at tag v1.30.0. Latest is v2.3.0 (2026-10-02) ([releases](https://github.com/modelcontextprotocol/python-sdk/releases)).
- **TypeScript SDK:** the code search found only pass-through of `traceparent` in `_meta`, with no span creation ([constants.ts](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/packages/core/src/constants.ts)). **[unverified that no tracing exists anywhere]** TypeScript instrumentation comes from third parties: Sentry, Shinzo, Datadog, and OpenInference.
- **FastMCP (PrefectHQ, Apache-2.0):**
  - Native OTel traces for tools, resources, prompts and tasks, with semconv span names.
  - Attributes include `mcp.session.id`, `enduser.id`, and `fastmcp.*` keys. No metrics are documented. Client name is not listed.
  - Configured with `FASTMCP_TELEMETRY_MODE=native|propagation_only|off`. The telemetry modes are new in 4.0.0 ([telemetry](https://gofastmcp.com/servers/telemetry)).
  - Middleware hooks include `on_message`, `on_request`, `on_call_tool`, and `on_initialize` (where `client_info.name` is accessible), plus `get_http_headers()` ([middleware](https://gofastmcp.com/servers/middleware)). That is the natural place for a CFDE drop-in.

## 3. Existing "analytics for MCP" products

| Product | Model | Self-host | License | Captures | Privacy posture |
|---|---|---|---|---|---|
| **AgentCat (ex-MCPcat)** | SDK wrapper (Py/TS) → hosted dashboard; can also forward to any OTel collector, Datadog, Sentry | Dashboard: not stated **[unverified]**. SDK can target your own OTLP endpoint | MIT (SDK) | Tool calls, an agent-supplied "context/intent" field, sessions, user identity via an `identify` callback | Redaction hooks; vendor says it "redacts all data… encrypts at rest" ([repo](https://github.com/MCPCat/mcpcat-python-sdk)) |
| **Shinzo Labs** | OTel-based SDK wrapper (TS) → any OTLP endpoint or Shinzo cloud | Collector side yes (any OTLP) | MIT | Traces and metrics; `mcp.tool.name`; arguments only if enabled | **Argument collection off by default**; PII sanitisation on by default ([repo](https://github.com/shinzo-labs/shinzo-ts)) |
| **Sentry MCP monitoring** | Sentry SDK integration (JS auto from 11.1.0; Python `MCPIntegration`, SDK ≥2.43) | Sentry is self-hostable (separate licence) | SaaS / FSL **[licence unverified]** | Tool executions, resource access, prompts, errors, client connections | Arguments/results only with `send_default_pii` (Py) or `recordInputs`/`recordOutputs` (JS) ([setup](https://docs.sentry.io/product/insights/ai/mcp/getting-started/)) |
| **PostHog MCP analytics** | SDK wrapper → PostHog events (`$mcp_tool_call`, `$mcp_initialize`) | PostHog self-host exists | **[unverified]** | Tool name, client, latency, errors, session; params and response per the tutorial | Web app is Beta; SDK alpha ([docs](https://posthog.com/docs/mcp-analytics), [tutorial](https://posthog.com/tutorials/mcp-analytics)) |
| **Datadog** | Auto-instrumentation of official Py/JS MCP SDKs in LLM Observability (client side) | No | Proprietary | Session setup, tool list/call spans, per-tool errors | n/a ([MCP clients](https://docs.datadoghq.com/llm_observability/monitoring/mcp_client)) |
| **Arize Phoenix / OpenInference** | OTel context propagation only (`openinference-instrumentation-mcp`) | Phoenix yes | Apache-2.0 **[licence unverified]** | Links client and server traces; no spans of its own | n/a ([PyPI](https://pypi.org/project/openinference-instrumentation-mcp/), [Phoenix](https://arize.com/docs/phoenix/integrations/typescript/mcp/mcp-tracing-typescript)) |
| **Langfuse** | Docs on `_meta` trace propagation into Langfuse (OTel) | Yes | MIT core **[unverified]** | Traces | ([docs](https://langfuse.com/docs/observability/features/mcp-tracing)) |
| **Grafana** | Community dashboard over OTel/Prometheus metrics | Yes | — | Tool calls, error rates | ([dashboard 25252](https://grafana.com/grafana/dashboards/25252-mcp-server-observability/)) |
| **Moesif** | API-analytics proxy/SDK, positioned for MCP observability and monetisation | No | Proprietary | API-level traffic | Marketing pages only; no MCP-specific product docs found ([blog](https://www.moesif.com/blog/monitoring/model-context-protocol/How-to-Setup-Observability-For-Your-MCP-Server-with-Moesif/)) |
| **Cloudflare Agents SDK** | Diagnostics channels: `agents:mcp` emits `mcp:client:connect`/`discover`… (client side) | Platform | — | Connection lifecycle; no documented per-MCP-tool-call event | ([diagnostics channels](https://developers.cloudflare.com/agents/runtime/operations/observability/diagnostics-channels/)) |
| **Smithery** | Hosting/registry; API exposes `useCount` per server | No | — | A single popularity number; definition undocumented **[unverified]** | (`GET registry.smithery.ai/servers` returned `useCount`, tested 2026-10-14) |

Takeaway: every serious option is either **OTel-native** or can **export to OTel**. Products differ mainly in their dashboards and in whether they capture arguments or "intent" (AgentCat, PostHog). For academic research tools we don't want argument capture.

## 4. Gateway / proxy approach

| Gateway | License | MCP observability |
|---|---|---|
| IBM ContextForge (`mcp-context-forge`) | Apache-2.0 | OTLP tracing of tools, prompts and resources; wraps stdio servers as HTTP (`mcpgateway.translate`) ([repo](https://github.com/IBM/mcp-context-forge)) |
| agentgateway (Linux Foundation) | Apache-2.0 | Prometheus `agentgateway_mcp_requests_total` ([metrics](https://github.com/agentgateway/agentgateway/blob/main/schema/metrics.md)) |
| Microsoft `mcp-gateway` | MIT | Kubernetes reverse proxy with session-aware routing; observability not documented ([repo](https://github.com/microsoft/mcp-gateway)) |
| Docker MCP Gateway | MIT | Runs on the *user's* machine (Docker Desktop); "logging and call tracing", nothing central ([repo](https://github.com/docker/mcp-gateway)) |
| Kong AI Gateway | Enterprise | OTel policy on AI MCP Server entities: tool-call counts, durations, errors ([docs](https://developer.konghq.com/ai-gateway/monitor-mcp-traffic-with-otel/)) |

Assessment:

- **A central gateway is the most accurate and lowest-burden option, but only for remote servers.** With 2026-07-28 clients it can be as simple as an nginx/Cloudflare log of the `Mcp-Method` and `Mcp-Name` headers, without parsing the body ([SEP-2243](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2243-http-standardization.md)).
- **The costs are political and operational.** Teams must route their URL through CFDE infrastructure (for example a shared `mcp.cfde.…` domain), and that becomes a shared availability dependency.
- **It sees nothing from stdio installs**, which is likely the majority for pip/npm-installed academic servers.

## 5. Privacy and consent

- **Arguments are sensitive.** Research queries can name unpublished genes, patient cohorts, and so on. OTel already treats arguments and results as **Opt-In** ([mcp.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md)). Sentry gates them behind PII flags and Shinzo defaults them off (§3). **The CFDE default should be: never send arguments or results.**
- **Norms for locally installed packages:**
  - *Homebrew* is opt-out: a notice is shown before the first event, and `HOMEBREW_NO_ANALYTICS=1` turns it off. The payload has **no user identifier and no IP field**, raw events are retained 365 days, and only aggregates are published ([Homebrew](https://docs.brew.sh/Analytics)).
  - *Go* is the conservative end. Telemetry is **local-only by default**, uploading is opt-in (`go telemetry on`), it covers weekly aggregated counters only, every counter is publicly approved, and the data is published ([go.dev/doc/telemetry](https://go.dev/doc/telemetry)).
  - The often-cited `DO_NOT_TRACK=1` convention site (consoledonottrack.com) now serves unrelated content, so I could not verify it as a living standard **[unverified]**. Honour it anyway; it's cheap.
- **Distinct users without PII:**
  - *Remote servers:* use the Plausible pattern `hash(daily_salt + site + ip + user_agent)`, where the salt is "rotated and deleted every 24 hours" and raw IP and user agent are never stored ([Plausible](https://plausible.io/data-policy)). This gives daily-unique counts that can't be linked across days.
  - *Local installs:* use a random install ID generated on first run and stored locally (no hardware or user data). Better still, drop the ID and report only per-install daily aggregates, as Go does.
- **NIH/US-gov context:** the obligations for federally funded tool telemetry (privacy notice, OMB guidance on web measurement) have **not been researched here [unverified]**. Check with the CFDE/NIH privacy office before turning on any default-on phone-home.

## 6. Proxy signals with no instrumentation (the "floor")

| Source | What you get | Notes |
|---|---|---|
| PyPI | `pypistats.org/api/packages/{pkg}/recent`, daily series; mirrors excluded by default; **180-day retention** ([pypistats API](https://pypistats.org/api/)). Full history via BigQuery `bigquery-public-data.pypi.file_downloads` ([PyPI docs](https://docs.pypi.org/api/bigquery/)) | CI and mirrors inflate the counts. BigQuery allows country/installer breakdowns ([guide](https://packaging.python.org/guides/analyzing-pypi-package-downloads/)) |
| npm | `api.npmjs.org/downloads/point/last-week/{pkg}` (verified live) | Counts include CI |
| Docker Hub | `hub.docker.com/v2/repositories/{ns}/{repo}` → `pull_count` (verified live) | Cumulative only, so snapshot it daily |
| MCP Registry | `registry.modelcontextprotocol.io/v0.1/servers` gives name, version, `packages[].registryType/identifier` (npm/pypi/oci), `remotes[].url`, publish dates. **No usage stats.** The API is v0.1, frozen, and still pre-GA ([README](https://github.com/modelcontextprotocol/registry)) | Useful as the **join key**: registry entry → package names → download stats |
| Smithery | `useCount` per server | Undefined metric **[unverified]** |
| GitHub | stars, forks, clones/views (already collected) | — |

These fit the existing CFDE pipeline (GitHub stats, Google Analytics), so collect them for every server regardless of instrumentation.

## 7. Recommendation

**Tier 0: everyone, zero burden (do now).**
- Keep a CFDE list of servers, linked to MCP Registry entries.
- Pull PyPI, npm and Docker Hub counts and registry metadata daily into the existing metrics store.
- This yields "adoption" but not "usage".

**Tier 1: standard event schema (the contract).** One record per MCP request, using OTel MCP semconv names wherever they exist:

| Field | Source | Notes |
|---|---|---|
| `service.name` / `service.version` | OTel resource | CFDE-assigned server ID = registry name |
| `mcp.method.name` | semconv | Required |
| `gen_ai.tool.name` / `gen_ai.prompt.name` | semconv | Conditionally required |
| `error.type` | semconv | Includes `tool_error` |
| `mcp.protocol.version` | semconv | |
| `network.transport` | semconv | `pipe` = stdio, `tcp` = HTTP |
| `cfde.mcp.client.name` / `.version` | `clientInfo` (handshake or per-request `_meta`) | **Custom: the semconv gap.** Rename if OTel adds one |
| `cfde.client.hash` | daily-salted hash (remote) or random install ID (local) | For distinct counts only |
| timestamp, duration | span | Latency is free but low priority |

Explicitly excluded: arguments, results, resource URIs (they can embed identifiers), IPs, and `enduser.id`.

**Tier 2: delivery, two paths with the same schema.**

1. **Push (default for hosted/remote servers).** Ship a thin drop-in, roughly 50 lines per language:
   - **FastMCP / Python SDK v2:** both already emit semconv spans, so the drop-in only (a) configures an OTLP/HTTP exporter to the CFDE collector, (b) adds the two `cfde.*` attributes from `clientInfo`, and (c) honours `CFDE_TELEMETRY=off` and `DO_NOT_TRACK`.
   - **TypeScript:** a small wrapper over `McpServer` handlers, or Shinzo's MIT OTel SDK pointed at our collector, with argument collection left off (its default).
   - **Central side:** a stock OpenTelemetry Collector that drops any `gen_ai.tool.call.*` attributes as defence in depth, then lands the data in the existing lake. Metrics are SQL over spans.
2. **Pull/aggregate (for teams that can't or won't push, and for stdio-only installs if consent is a concern).**
   - The team runs the same instrumentation with a local file or collector exporter.
   - A scheduled job uploads **daily aggregates**: `date, server, tool, client.name, transport, calls, errors, distinct_clients`. The upload is a CSV/Parquet file or a POST of the same JSON.
   - This mirrors Go's "aggregate locally, upload counters" model.

**Remote vs local tradeoffs.**
- *Remote servers:*
  - Server-side instrumentation or a gateway gives near-complete counts.
  - Treat it like web analytics: disclose in a privacy notice, with no per-user consent prompt.
  - Strongly encourage teams to host a remote endpoint. Distinct users via the daily hash.
- *Local stdio servers:*
  - Data leaves the machine only through phone-home from the package. Use **opt-out with a first-run notice** (the Homebrew model) at most, or **opt-in** (the Go model) if NIH guidance requires it.
  - Expect large undercounting: firewalls, people who opt out, and offline HPC nodes. Report these numbers as a lower bound next to download counts, never as totals.

**Not recommended:**
- A mandatory central gateway for all servers: it's blind to stdio and creates a shared outage risk. Offer it as an *optional* hosting convenience.
- Adopting a SaaS such as AgentCat or PostHog as the system of record: it locks in the vendor and those tools collect arguments or intent by default. Teams can still use them locally, because both can export to OTel.
- Session-based metrics: sessions are gone in 2026-07-28.

**Open decisions for CFDE:** (1) Opt-out vs opt-in for local packages; this needs NIH privacy input. (2) Whether to run the optional shared gateway/domain. (3) Collector hosting and retention. (4) Re-check OTel MCP semconv before freezing the schema, since it is still Development and attribute names may change.

---

## Sources

- MCP versioning: https://modelcontextprotocol.io/specification/versioning
- MCP 2026-07-28 base protocol / `_meta`: https://modelcontextprotocol.io/specification/2026-07-28/basic/index
- MCP 2026-07-28 Streamable HTTP: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- MCP 2025-11-25 lifecycle: https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- MCP 2025-11-25 transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- SEP-2567 Sessionless MCP: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2567-sessionless-mcp.md
- SEP-2575 Stateless MCP: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2575-stateless-mcp.md
- SEP-2243 HTTP header standardization: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2243-http-standardization.md
- SEP-414 request `_meta`: https://modelcontextprotocol.io/community/seps/414-request-meta
- OTel GenAI semconv repo: https://github.com/open-telemetry/semantic-conventions-genai
- OTel MCP semconv: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md
- OTel MCP attribute registry: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/registry/attributes/mcp.md
- OTel old (moved) page: https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/
- MCP Python SDK OTel docs: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/opentelemetry.md
- MCP Python SDK releases: https://github.com/modelcontextprotocol/python-sdk/releases
- MCP TypeScript SDK: https://github.com/modelcontextprotocol/typescript-sdk
- FastMCP telemetry: https://gofastmcp.com/servers/telemetry
- FastMCP middleware: https://gofastmcp.com/servers/middleware
- AgentCat/MCPcat Python SDK: https://github.com/MCPCat/mcpcat-python-sdk
- Shinzo TS SDK: https://github.com/shinzo-labs/shinzo-ts
- Sentry MCP monitoring: https://docs.sentry.io/product/insights/ai/mcp/ and https://docs.sentry.io/product/insights/ai/mcp/getting-started/
- PostHog MCP analytics: https://posthog.com/docs/mcp-analytics , https://posthog.com/tutorials/mcp-analytics
- Datadog MCP clients: https://docs.datadoghq.com/llm_observability/monitoring/mcp_client
- OpenInference MCP: https://pypi.org/project/openinference-instrumentation-mcp/ ; Phoenix: https://arize.com/docs/phoenix/integrations/typescript/mcp/mcp-tracing-typescript
- Langfuse MCP tracing: https://langfuse.com/docs/observability/features/mcp-tracing
- Grafana MCP dashboard: https://grafana.com/grafana/dashboards/25252-mcp-server-observability/
- Moesif MCP blog: https://www.moesif.com/blog/monitoring/model-context-protocol/How-to-Setup-Observability-For-Your-MCP-Server-with-Moesif/
- Cloudflare Agents diagnostics channels: https://developers.cloudflare.com/agents/runtime/operations/observability/diagnostics-channels/
- IBM ContextForge: https://github.com/IBM/mcp-context-forge
- agentgateway metrics: https://github.com/agentgateway/agentgateway/blob/main/schema/metrics.md
- Microsoft mcp-gateway: https://github.com/microsoft/mcp-gateway
- Docker MCP Gateway: https://github.com/docker/mcp-gateway
- Kong MCP + OTel: https://developer.konghq.com/ai-gateway/monitor-mcp-traffic-with-otel/
- Homebrew analytics: https://docs.brew.sh/Analytics
- Go telemetry: https://go.dev/doc/telemetry
- Plausible data policy: https://plausible.io/data-policy
- pypistats API: https://pypistats.org/api/
- PyPI BigQuery: https://docs.pypi.org/api/bigquery/ ; https://packaging.python.org/guides/analyzing-pypi-package-downloads/
- npm downloads API: https://api.npmjs.org/downloads/point/last-week/@modelcontextprotocol/sdk
- MCP Registry: https://github.com/modelcontextprotocol/registry ; API https://registry.modelcontextprotocol.io/v0.1/servers
- Smithery registry API: https://registry.smithery.ai/servers
