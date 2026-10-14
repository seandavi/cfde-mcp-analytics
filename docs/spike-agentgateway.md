# Spike: agentgateway in front of GlyGen, PWB and PerturbSeqr

Status: done, 2026-10-14. Phase 1 of the [POC plan](poc-plan.md). Issues #5–#11.
**Recommendation: GO on agentgateway (D1).** Every Phase 1 question has a working answer.
There are three config workarounds, all in [`gateway/config.yaml`](../gateway/config.yaml).

## Setup

- **Gateway.** agentgateway **v1.6.0**, the latest release (2026-10-02). I used the static
  `agentgateway-linux-amd64` binary and checked it against its `.sha256`.
- **Config.** I checked the schema against `schema/config.md` and `schema/cel.md` in the v1.6.0
  source tag and validated the config with `--validate-only`. The config uses the current
  top-level `gateways:` / `routes:` / `frontendPolicies:` layout. Older docs use `binds:`, which
  still works.
- **Routes.** One route per server, each with a single MCP target: `/glygen`, `/pwb` and
  `/perturbseqr`.
- **Clients.** I used the official Python SDK through `uv run --with`, in two versions:

| SDK | Speaks | How it connects | User-Agent sent |
|---|---|---|---|
| `mcp==1.30.0` (latest 1.x) | up to **2025-11-25** (`SUPPORTED_PROTOCOL_VERSIONS` ends there) | `initialize` + `Mcp-Session-Id` | `python-httpx/0.28.1` |
| `mcp==2.3.0` (latest) | **2026-07-28** (`LATEST_PROTOCOL_VERSION`) | `Client(mode="auto")`: `server/discover`, falling back to `initialize` on `-32601`; `mode="2026-07-28"` forces stateless | `python-httpx2/2.13.1` |

- **Upstream protocol support** (as observed). GlyGen speaks **2026-07-28**, because its
  `server/discover` succeeds. PerturbSeqr speaks 2025-11-25. PWB negotiates **2025-06-18**.
- **Local test server.** For cases that public servers can't produce on demand, I added a
  spike-only route `/local` to a 15-line `mcp==2.3.0` `MCPServer` on localhost. It has tools
  `echo`, `fail` (raises, so it returns `isError`) and `rpcfail` (raises a JSON-RPC `-32602`
  whose message echoes the argument). That route is not in the committed config. Phase 2's
  reference server replaces it.
- **Tracing.** For #10, spike runs also exported OTLP/HTTP traces (`randomSampling: true`) to a
  local sink that wrote the raw protobuf to disk.
- **Production load.** All runs together sent at most 46 HTTP requests per production server,
  and 5–9 of them were `tools/call`. All tools I called were read-only (`get_release_info`,
  `get_organism_list`, `get_protein_summary`, `search_published`, `view`, `list_datasets`,
  `single_gene_set_search`, `get_gene_set_genes`, `term_search`), plus calls to a nonexistent
  tool.

## Findings

### #5 Routes work from an MCP client: yes

Both SDKs listed tools and called them on all three routes. A 2.3.0 client reached GlyGen at
2026-07-28 and fell back to legacy on PWB and PerturbSeqr. There is one gap: **agentgateway's
default upstream timeout for MCP backends is 10 s** (`BackendRequestTimeout(10s)` in
`proxy/httpproxy.rs`). A 2026-07-28 `get_protein_summary` on GlyGen took 12.6 s and failed
with `http.status: 500`, `error: "...upstream call timeout"`. The same call over the legacy
path took 12.7 s and succeeded. I haven't verified why the legacy path escapes the timeout; my
guess is that its streamed response headers arrive early. **Fix:** set
`policies: {http: {requestTimeout: 120s}}` on each target. After that, the same call succeeded
in 12.6 s.

### #6 Per-tool counts: the access log and the metric agree exactly

- **Access log.** Every MCP request carries `route`, `mcp.method.name`, `mcp.target` and
  `gen_ai.tool.name`, and `mcp.resource.type` is `tool` on `tools/call`.
- **Metric.** It is named **`agentgateway_mcp_requests_total`**, not `mcp_requests_total` as the
  research doc says. Its labels are `method`, `resource_type`, `server`, `resource` (the tool
  name) and `route`. For anything other than `tools/call`, `server` and `resource` are
  `"unknown"`, so use `route` to get the server.
- **Comparison.** I counted (route, method, tool) from the log and from the counter. They match
  on every key in every run: 24/24, 5/5, 12/12 and 7/7 `tools/call`, and the same for
  `initialize`, `tools/list` and `server/discover`. An excerpt from the main run:

```
route                  method                     tool                      log metric
default/glygen         tools/call                 get_protein_summary         3      3
default/glygen         tools/call                 get_release_info            3      3
default/glygen         tools/call                 no_such_tool                1      1
default/perturbseqr    tools/call                 list_datasets               2      2
default/pwb            tools/call                 search_published            2      2
...
tools/call totals: log 24 metric 24
```
```
agentgateway_mcp_requests_total{method="tools/call",resource_type="tool",server="glygen",resource="get_release_info",bind="bind/3311",gateway="default/default",listener="default",route="default/glygen",route_rule="unknown"} 3
```

- **Caveats:**
  - The counter has **no outcome label**. Errors are visible only in the log, which matches D4:
    the log is the source of truth.
  - Nonexistent tool names a client sends become label values, so cardinality is unbounded but
    small in practice.

### #7 clientInfo name/version: captured for both generations with CEL

Log-only CEL can read `request.body`. The gateway records the body as it streams through and
does not buffer it ahead of time (see `schema/cel-functions.md`, "Body Variables"). Two fields
cover both shapes:

```yaml
mcp.client.name:    'coalesce(json(request.body).params.clientInfo.name, json(request.body).params._meta["io.modelcontextprotocol/clientInfo"].name)'
mcp.client.version: 'coalesce(json(request.body).params.clientInfo.version, json(request.body).params._meta["io.modelcontextprotocol/clientInfo"].version)'
```

- **2026-07-28 clients** send clientInfo in `_meta` on every request, so the name and version
  appear on every line, including `tools/call`:
  ```json
  {"route":"default/glygen","mcp.method.name":"tools/call","gen_ai.tool.name":"get_release_info","mcp.protocol.version":"2026-07-28","user_agent":"python-httpx2/2.13.1","mcp.client.name":"cfde-spike-modern","mcp.client.version":"2.3.0","mcp.tool.is_error":false}
  ```
- **Legacy clients** send clientInfo only in `initialize`, so a later `tools/call` must be
  joined back to its session. **Gotcha:** the built-in `mcp.session.id` on the `initialize`
  line is an internal UUID. It is not the `Mcp-Session-Id` token the client reuses afterwards.
  I added `mcp.client.session` = response `mcp-session-id` header, falling back to the request
  header. That value is identical on `initialize` and on every later request in the session:
  ```json
  {"route":"default/local","mcp.method.name":"initialize","mcp.protocol.version":"2025-11-25","mcp.client.session":"eyJ0IjoibWNw…","user_agent":"python-httpx/0.28.1","mcp.client.name":"cfde-spike-legacy","mcp.client.version":"1.30.0"}
  {"route":"default/local","mcp.method.name":"tools/call","gen_ai.tool.name":"echo","mcp.protocol.version":"2025-11-25","mcp.client.session":"eyJ0IjoibWNw…","user_agent":"python-httpx/0.28.1","mcp.tool.is_error":false}
  ```
- **Attribution coverage** (checked with a script over the logs): **100% of `tools/call`**.
  Main run: 24 calls, 7 attributed on the line itself and 17 through the session join.
  Other runs: 5 (3 + 2) and 12 (5 + 7). The join belongs in the Phase 4 pipeline, either in
  Vector or in ClickHouse, keyed by `mcp.client.session`. The token is opaque but stable. It
  is the gateway's own encoding of target and upstream session, not the upstream's raw ID.
- **User-Agent** is useless for attribution with the Python SDK, because it is just the HTTP
  library: `python-httpx/0.28.1` or `python-httpx2/2.13.1`. **[unverified]** I did not test
  what Claude, Cursor, VS Code or MCP Inspector send. I couldn't drive those clients from this
  host. Log `user_agent` anyway, as a fallback and for the distinct-client hash (D6).

### #8 Tool errors vs JSON-RPC errors: distinguishable

There are three error shapes. Each has its own field:

| Case | HTTP | Log field |
|---|---|---|
| Tool error (`result.isError: true`) | 200 | `mcp.tool.is_error: true` (CEL `mcp.tool.result.isError`) |
| JSON-RPC error, legacy session | 200 | `mcp.error.code` (built in, e.g. `-32602`) |
| JSON-RPC error, 2026-07-28 | **400** | `mcp.rpc_error.code` (CEL `json(response.body).error.code`). The built-in `mcp.error.code` is **not** set here. |
| Gateway or upstream failure (timeout, 5xx) | 5xx | `http.status`, `error`, `reason` |

```json
{"route":"default/local","http.status":200,"mcp.method.name":"tools/call","gen_ai.tool.name":"fail","mcp.protocol.version":"2026-07-28","mcp.tool.is_error":true}
{"route":"default/local","http.status":200,"mcp.method.name":"tools/call","gen_ai.tool.name":"rpcfail","mcp.error.code":-32602,"mcp.protocol.version":"2025-11-25"}
{"route":"default/local","http.status":400,"mcp.method.name":"tools/call","gen_ai.tool.name":"rpcfail","error":"mcp: upstream error: 400 Bad Request","mcp.protocol.version":"2026-07-28","mcp.rpc_error.code":-32602}
```

Notes for the Phase 4 outcome column:
- **Outcome rule:** `http_error` if status ≥ 500, else `rpc_error` if
  `mcp.error.code` or `mcp.rpc_error.code` is set, else `tool_error` if `mcp.tool.is_error`,
  else `ok`.
- **Missing `isError` means ok.** PWB and PerturbSeqr omit `isError` on success, so the field
  is absent from their success lines.
- **Unknown tools and bad arguments come back as `isError`, not JSON-RPC errors,** on all three
  production servers. Examples: GlyGen `Unknown tool`, PerturbSeqr `-32602 Input validation
  error`. These count as tool errors. GlyGen also reports an upstream API 500 *inside a
  successful result*, with `isError: false`. No gateway can detect that.
- **Expected noise to exclude from error rates:**
  - A 2026-07-28 client probing a legacy server logs one `server/discover` with
    `mcp.error.code: -32601` per connection.
  - Legacy clients log their `GET` stream as `405`, at `level: error`, on GlyGen and
    PerturbSeqr.

### #9 Both protocol generations: both work

- **2025-11-25 (`mcp==1.30.0`):** `initialize`, then calls in a session on all three routes and
  `/local`.
- **2026-07-28 (`mcp==2.3.0`):**
  - Stateless (`server/discover`, `_meta` on each request, no session) end to end on **GlyGen**
    (production) and `/local`, in both `auto` and forced `2026-07-28` mode.
  - On PWB and PerturbSeqr the client falls back to `initialize`, as agentgateway documents.
    For a single target the gateway passes `server/discover` straight through and does not
    translate versions (`merge_discover` in `mcp/handler.rs`).
- **Version header.** `mcp.protocol.version` (the header, or the `initialize` body) records
  which generation each line used.

### #10 No arguments or results in any output: confirmed, after one fix

- **Method.** Every call carried the sentinel `CFDESENTINEL7f3a9c` as an argument:
  - a plain string argument;
  - a nested-object argument that triggers a validation error which echoes it;
  - an argument to a nonexistent tool;
  - the argument of a tool whose result echoes it (`echo`);
  - an argument that the server echoes in a JSON-RPC error message (`rpcfail`);
  - production calls with the sentinel to GlyGen, PWB and PerturbSeqr.

  I then ran `grep -a -c` over the JSON log, `/metrics` and the raw OTLP trace export, at log
  levels `info` and `debug`.
- **Found:** the built-in access-log field **`mcp.error.message`** carries the upstream's
  JSON-RPC error message verbatim, and it does so **by default**. The same attribute is on
  trace spans. A server that echoes input, as many validators do, leaks arguments through it:
  ```json
  {"gen_ai.tool.name":"rpcfail","mcp.error.code":-32602,"mcp.error.message":"bad input: CFDESENTINEL7f3a9c"}
  ```
- **Fix:** `frontendPolicies.accessLog.remove: [mcp.error.message]`, and
  `frontendPolicies.tracing.remove: [mcp.error.message]` if tracing is ever enabled.
- **After the fix:** 0 hits in the log, `/metrics` and traces, at both `info` (50 lines) and
  `debug` (553 lines). Before the fix, a sentinel echoed in tool *results* never appeared
  either.
- **What still holds data in memory.** The CEL fields read `request.body` and `response.body`,
  so the gateway records bodies in memory, up to 2 MiB per request, while a request is in
  flight. Only the extracted scalars are written out. `src.addr` (the client IP and port) is
  logged by default. D6 says to hash it in the Vector transform, not to store it raw. Behind
  Traefik it will be Traefik's address, so take the client IP from `X-Forwarded-For`
  **[unverified on onclappc02]**.
- **Not tested:** the admin UI's database log store and its "Include prompts and completions"
  toggle. That store is off unless `config.logging.database` is set, and this config does not
  set it.

## Working config

This is a verbatim copy of [`gateway/config.yaml`](../gateway/config.yaml). The spike runs
also appended the `/local` route and a `tracing:` block.

```yaml
# yaml-language-server: $schema=https://agentgateway.dev/schema/config
# agentgateway v1.6.0 — Phase 1 spike. See docs/spike-agentgateway.md.
config:
  statsAddr: 127.0.0.1:15020      # Prometheus /metrics
  adminAddr: 127.0.0.1:15000
  logging:
    format: json
gateways:
  default:
    port: 3311
frontendPolicies:
  accessLog:
    # Built-in field, logged by default: the upstream's JSON-RPC error message verbatim.
    # Servers can echo argument values into it (verified in the spike), so drop it.
    # mcp.error.code stays. If tracing is enabled, add `remove: [mcp.error.message]` there too.
    remove: [mcp.error.message]
    add:
      # Privacy (D6): every field below extracts a scalar. Never log mcp.tool.arguments,
      # mcp.tool.result, request.body or response.body whole.
      mcp.protocol.version: 'coalesce(request.headers["mcp-protocol-version"], json(request.body).params.protocolVersion)'
      # Client-facing session token (legacy only). Join key from `initialize` to later calls;
      # the built-in mcp.session.id on the initialize line is NOT the token the client reuses.
      mcp.client.session: 'coalesce(response.headers["mcp-session-id"], request.headers["mcp-session-id"])'
      user_agent: 'request.headers["user-agent"]'
      # clientInfo: legacy clients send it only in `initialize`; 2026-07-28 clients in every _meta.
      mcp.client.name: 'coalesce(json(request.body).params.clientInfo.name, json(request.body).params._meta["io.modelcontextprotocol/clientInfo"].name)'
      mcp.client.version: 'coalesce(json(request.body).params.clientInfo.version, json(request.body).params._meta["io.modelcontextprotocol/clientInfo"].version)'
      # Tool-level error (HTTP 200, result.isError). Absent when the server omits isError (= ok).
      # Legacy JSON-RPC errors (HTTP 200) are built in as mcp.error.code.
      mcp.tool.is_error: 'mcp.tool.result.isError'
      # 2026-07-28 upstreams return JSON-RPC errors as HTTP 4xx, where mcp.error.code is not set.
      mcp.rpc_error.code: 'json(response.body).error.code'
routes:
- name: glygen
  matches: [{path: {pathPrefix: /glygen}}]
  backends:
  - mcp:
      targets:
      - name: glygen
        mcp: {host: https://mcp.glygen.org/mcp}
        policies: {http: {requestTimeout: 120s}}  # default upstream timeout is 10s
- name: pwb
  matches: [{path: {pathPrefix: /pwb}}]
  backends:
  - mcp:
      targets:
      - name: pwb
        mcp: {host: https://playbook-workflow-builder.cloud/api/mcp}
        policies: {http: {requestTimeout: 120s}}  # default upstream timeout is 10s
- name: perturbseqr
  matches: [{path: {pathPrefix: /perturbseqr}}]
  backends:
  - mcp:
      targets:
      - name: perturbseqr
        mcp: {host: https://perturbseqr.maayanlab.cloud/mcp}
        policies: {http: {requestTimeout: 120s}}  # default upstream timeout is 10s
```

The port is 3311 because 3000 was taken on the spike host. Any free port works.

## Gaps and workarounds

| Gap | Workaround | Severity |
|---|---|---|
| `mcp.error.message` logs and traces argument echoes by default | `remove: [mcp.error.message]` (in config) | High: privacy. Fixed. |
| Default 10 s upstream timeout breaks slow 2026-07-28 calls | Per-target `policies.http.requestTimeout` | Medium. Fixed. |
| No built-in clientInfo field | CEL over `request.body` (in config) | Fixed. |
| Legacy clientInfo appears only on `initialize`; `mcp.session.id` there doesn't match later lines | Log `mcp.client.session`; join in the pipeline (Phase 4) | Low: pipeline work |
| 2026-07-28 JSON-RPC errors arrive as HTTP 400 without `mcp.error.code` | CEL `json(response.body).error.code` | Fixed. |
| Counter has no outcome or client labels | Use the log (D4). `config.metrics.fields.add` could add labels **[unverified]** | Low |
| Research doc metric name and labels are out of date | Name is `agentgateway_mcp_requests_total`; `server`/`resource` are `unknown` off `tools/call` | Doc only |
| Real-client User-Agent values | Test with Claude, Cursor, VS Code and Inspector in Phase 3 **[unverified]** | Low (clientInfo covers it) |
| Body capture memory cost (≤2 MiB per in-flight request) | Acceptable at POC scale **[unverified under load]** | Low |
| Python SDK prints `Session termination failed: 202` on legacy close | Cosmetic. The gateway returns 202 to `DELETE` | None |

## Recommendation (D1)

**GO on agentgateway.** It answered every Phase 1 question:

- per-server and per-tool counts, with an exact log/metric match;
- client name and version for both protocol generations, with 100% attribution after the
  session join;
- a three-way error split;
- transparent handling of 2025-06-18, 2025-11-25 and 2026-07-28 traffic;
- no argument or result data in any output once one default field is removed.

It is one static binary and one YAML file. Nothing essential is blocked, so I did not evaluate
the IBM ContextForge fallback. ContextForge remains the option if CFDE later wants a catalog and
admin UI more than a lean proxy ([gateways §5](research/mcp-gateways.md)).

Carry into Phase 3 and 4:
1. **Pin v1.6.0** and re-check `mcp.error.message` and the timeout default on every upgrade.
   Both are defaults that could change.
2. **Phase 4 Vector transform:**
   - allowlist fields (D6 guard);
   - do the session join;
   - derive the outcome with the rule in #8;
   - drop the `server/discover -32601` and `GET 405` noise from error rates.
3. **Phase 3:** record the User-Agent and clientInfo that real clients send through Traefik,
   and take the client IP from `X-Forwarded-For`.
