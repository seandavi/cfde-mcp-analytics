# Applying the onclappc02 deployment

Everything in this directory is prepared but **not applied**. The steps below touch shared
resources (DNS, GCP, GSM, monode, `/etc`, the `proxy` network), so run them by hand, in order.
Paths assume the repo is checked out at `~/Documents/git/cfde-mcp-analytics` on onclappc02 and
monode at `~/Documents/git/monode`.

| File | What it is |
|---|---|
| `docker-compose.yml` | agentgateway (v1.6.0) + reference server; Traefik labels for `cfde-mcp.cancerdatasci.org` |
| `gateway.yaml` | Production routes `/reference`, `/glygen`, `/pwb`, `/perturbseqr`, `/cfde-mcp`, plus `/health` |
| `gateway/Dockerfile` | Official v1.6.0 image + static busybox, so stdout can be appended to `/logs/gateway.log` |
| `logrotate.d/cfde-mcp` | Daily copytruncate rotation of the gateway log, 14 days |
| `compose.local.yml` | Overlay for local validation: no Traefik labels, no `proxy` network, loopback port |
| `systemd/` | `cfde-rollup-mcp` and `cfde-collect-downloads` service + timer units (SCHEDULING.md) |
| `verify_counts.py` | The #22 check: gateway counts in ClickHouse vs the reference server's own log |
| `../../pipeline/clickhouse/mcp_requests.sql` | ClickHouse `mcp_requests` (90-day TTL) + `mcp_requests_attributed` view |
| `../../pipeline/vector/cfde-mcp.yaml` | Vector source/transform/sink + `vector test` unit tests (privacy guard) |
| `../../collectors/migrations/0003*, 0004*` | Postgres `raw.mcp_daily_calls`, `raw.mcp_clients_monthly`, `analytics.mcp_daily`, `analytics.mcp_clients_monthly` |

## Phase 3: deploy (issues #14–#18)

### 1. HMAC salt in GSM (#18)

Name per monode `terraform/README.md` (`<scope>-<subject>-<credential-type>`):
**`cfde-mcp-client-hash-signing-key`**. HMAC keys are the closest member of the closed
credential-type set (`signing-key`).

```bash
gcloud secrets create cfde-mcp-client-hash-signing-key --project=cdsci-infra \
  --replication-policy=automatic \
  --labels=type=signing-key,subject=client-hash,scope=cfde-mcp,managed-by=manual \
  --update-annotations="purpose=HMAC-SHA256 key for the distinct-client hash (IP + User-Agent) and session-token hash in the cfde-mcp gateway log pipeline (D6). Rotated monthly.,consumed-by=monode/infrastructure compose/vector (.env CFDE_MCP_HMAC_SALT) via cfde-mcp-analytics pipeline/vector/cfde-mcp.yaml,rotated=$(date +%F)"
openssl rand -base64 48 | tr -d '\n' | gcloud secrets versions add cfde-mcp-client-hash-signing-key \
  --data-file=- --project=cdsci-infra
```

Monthly rotation (D6; **open**: NIH/privacy sign-off on monthly vs daily): on the 1st (UTC),
add a new version as above, update `CFDE_MCP_HMAC_SALT` in monode `compose/vector/.env`, and
`docker compose -f ~/Documents/git/monode/infrastructure/compose/vector/docker-compose.yml up -d vector`.
Rotating mid-month splits that month's distinct-client count in two.

### 2. Log directory and rotation

```bash
mkdir -p /data/davsean/cfde_mcp_logs
sudo install -m 0644 deploy/onclappc02/logrotate.d/cfde-mcp /etc/logrotate.d/cfde-mcp
sudo logrotate -d /etc/logrotate.d/cfde-mcp
```

### 3. DNS record (monode PR, part 1 of #16)

Add `terraform/apps/cfde_mcp/` (draft below) and the `module "cfde_mcp"` block to
`terraform/apps.tf`. Apply **only the DNS record first**, so Let's Encrypt (TLS-ALPN-01) can
issue when the router appears, and the uptime alert is not created while the service is down:

```bash
cd ~/Documents/git/monode/infrastructure/terraform
tofu plan  -target=module.cfde_mcp.cloudflare_dns_record.cfde_mcp
tofu apply -target=module.cfde_mcp.cloudflare_dns_record.cfde_mcp
dig +short cfde-mcp.cancerdatasci.org A   # expect 140.226.4.71 (grey cloud)
```

### 4. Bring the stack up (#14, #15)

```bash
cd ~/Documents/git/cfde-mcp-analytics
docker compose -f deploy/onclappc02/docker-compose.yml up -d --build
docker compose -f deploy/onclappc02/docker-compose.yml ps
curl -sS https://cfde-mcp.cancerdatasci.org/health          # Healthy (first call may wait for the LE cert)
tail -n 3 /data/davsean/cfde_mcp_logs/gateway.log
```

Route checks (keep production traffic light and read-only):

```bash
for r in reference glygen pwb perturbseqr; do
  uv run --no-project --with 'mcp==2.3.0' python -c "
import asyncio, sys
from mcp.client.client import Client
async def main():
    async with Client(sys.argv[1]) as c:
        print(sys.argv[1], c.session.protocol_version, len((await c.list_tools()).tools), 'tools')
asyncio.run(main())" "https://cfde-mcp.cancerdatasci.org/$r/mcp"
done
# cfde-mcp needs a DRC API key (bearer pass-through; verified locally with a header-recording upstream):
curl -sS -X POST https://cfde-mcp.cancerdatasci.org/cfde-mcp/mcp \
  -H "Authorization: Bearer $DRC_API_KEY" -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 300
```

Then add each URL in Claude (and one other client, e.g. MCP Inspector or VS Code) and record the
`user_agent` and `mcp.client.name` they log (spike gap: real-client User-Agents are unverified):

```bash
grep '"mcp.method.name":"initialize"' /data/davsean/cfde_mcp_logs/gateway.log | tail -n 5
```

### 5. Uptime check (monode PR, part 2 of #16)

Once `/health` answers `Healthy` publicly:

```bash
cd ~/Documents/git/monode/infrastructure/terraform && tofu plan && tofu apply
```

Draft `terraform/apps/cfde_mcp/main.tf` (copied from `apps/cfde_atlas/`, grey cloud):

```hcl
# DNS + uptime monitoring for cfde-mcp — the CFDE MCP gateway (agentgateway) POC.
# Application source: github.com/seandavi/cfde-mcp-analytics (deploy/onclappc02/).
# Grey cloud: Traefik terminates TLS with an LE cert (tls.certresolver=cloudflare). MCP
# Streamable HTTP holds long-lived SSE responses; keeping Cloudflare's proxy out avoids its
# 100s idle timeout and keeps the client IP in X-Forwarded-For.
terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
    google     = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

resource "cloudflare_dns_record" "cfde_mcp" {
  zone_id = var.cancerdatasci_zone_id
  name    = "cfde-mcp"
  type    = "A"
  content = var.onclappc02_public_ip
  proxied = false # grey cloud: LE TLS-ALPN-01 must reach origin
  ttl     = 1
  comment = "cfde-mcp gateway on onclappc02 — grey cloud, LE cert via Traefik"
}

resource "google_monitoring_uptime_check_config" "health" {
  project      = var.gcp_project_id
  display_name = "cfde-mcp /health"
  timeout      = "10s"
  period       = "${var.check_period_seconds}s"

  http_check {
    path           = "/health"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"
    accepted_response_status_codes { status_value = 200 }
  }
  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.gcp_project_id, host = var.monitored_host }
  }
  selected_regions = ["USA_OREGON", "USA_IOWA", "USA_VIRGINIA", "EUROPE", "ASIA_PACIFIC"]
  # /health is a static agentgateway directResponse ("Healthy"): it proves DNS -> Traefik ->
  # gateway, not the team-hosted upstreams.
  content_matchers {
    content = "Healthy"
    matcher = "CONTAINS_STRING"
  }
}

resource "google_monitoring_alert_policy" "uptime_failure" {
  project      = var.gcp_project_id
  display_name = "cfde-mcp /health uptime failing"
  combiner     = "OR"
  conditions {
    display_name = "Failure of uptime check (any region)"
    condition_threshold {
      filter = join(" AND ", [
        "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\"",
        "metric.label.check_id=\"${google_monitoring_uptime_check_config.health.uptime_check_id}\"",
        "resource.type=\"uptime_url\"",
      ])
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
      trigger { count = 1 }
    }
  }
  notification_channels = var.notification_channel_ids
  alert_strategy { auto_close = "3600s" }
  documentation {
    mime_type = "text/markdown"
    content   = <<-MD
      The uptime check for `${var.monitored_host}/health` is failing.

      **First debug steps:**
      1. Region breakdown on the [uptime check page](https://console.cloud.google.com/monitoring/uptime?project=${var.gcp_project_id}); one region is usually a prober blip.
      2. `curl -sS https://${var.monitored_host}/health` should print `Healthy`.
      3. On onclappc02: `docker compose -f ~/Documents/git/cfde-mcp-analytics/deploy/onclappc02/docker-compose.yml ps` and `docker logs cfde-mcp-gateway`.
      4. TLS errors: the LE cert for this host lives in Traefik's `acme.json`; check `docker logs traefik | grep cfde-mcp`.
    MD
  }
}
```

`variables.tf`: copy `apps/cfde_atlas/variables.tf` and change the `monitored_host` default to
`"cfde-mcp.cancerdatasci.org"`. `outputs.tf`: copy `apps/cfde_atlas/outputs.tf` with
`cfde_atlas` → `cfde_mcp`. In `terraform/apps.tf`:

```hcl
# cfde-mcp gateway POC (github.com/seandavi/cfde-mcp-analytics, deploy/onclappc02/).
module "cfde_mcp" {
  source = "./apps/cfde_mcp"

  gcp_project_id           = var.gcp_project_id
  cancerdatasci_zone_id    = var.cancerdatasci_zone_id
  notification_channel_ids = values(module.nf_telemetry.notification_channel_ids)

  depends_on = [google_project_service.monitoring]
}
```

### 6. monode INDEX.md rows (#17, same monode PR)

Public services table:

```markdown
| `cfde-mcp.cancerdatasci.org` | `cfde-mcp-gateway` (agentgateway v1.6.0; `cfde-mcp-reference` behind it, internal only) | 3000 | grey | LE | `deploy/onclappc02/docker-compose.yml` (**cfde-mcp-analytics**) |
```

Repos that contribute services:

```markdown
| `cfde-mcp-analytics` | `~/Documents/git/cfde-mcp-analytics/deploy/onclappc02/` | `cfde-mcp-gateway`, `cfde-mcp-reference`; gateway log at `/data/davsean/cfde_mcp_logs/` (Vector → ClickHouse `mcp_requests`) |
```

Also add `/data/davsean/cfde_mcp_logs` + `/etc/logrotate.d/cfde-mcp` to the "Infrastructure
plumbing" row for Vector once Phase 4 below is applied.

### Phase 3 exit

All five routes work from Claude and one other client; the GCP uptime check is green.

## Phase 4: logging pipeline (issues #19–#22)

### 7. ClickHouse table (#19, monode PR)

Copy the migration into monode's numbered migrations (platform convention: Vector does not
create tables) and apply it:

```bash
cd ~/Documents/git/monode/infrastructure/compose/clickhouse
cp ~/Documents/git/cfde-mcp-analytics/pipeline/clickhouse/mcp_requests.sql migrations/004_mcp_requests.sql
docker exec -i clickhouse clickhouse-client \
  --user="$(grep ^CLICKHOUSE_USER .env | cut -d= -f2)" --password="$(grep ^CLICKHOUSE_PASSWORD .env | cut -d= -f2)" \
  --multiquery < migrations/004_mcp_requests.sql
```

### 8. Vector source + transform (#20, same monode PR)

In `infrastructure/compose/vector/`:

1. `vector.yaml`: copy the `cfde_mcp_gateway` source, `parse_cfde_mcp` transform and
   `clickhouse_cfde_mcp` sink from `pipeline/vector/cfde-mcp.yaml` into the matching sections.
   That file stays the source of truth: its `tests:` run in this repo's CI (`just vector-test`).
2. `docker-compose.yml`:
   ```diff
          - /data/davsean/cfde_atlas_logs:/var/log/cfde-atlas:ro
   +      # cfde-mcp gateway access log (cfde-mcp-analytics deploy/onclappc02). Read-only.
   +      - /data/davsean/cfde_mcp_logs:/var/log/cfde-mcp:ro
   ...
          CLICKHOUSE_DB: ${CLICKHOUSE_DB:-default}
   +      # HMAC key for the cfde-mcp client/session hashes (GSM cfde-mcp-client-hash-signing-key).
   +      CFDE_MCP_HMAC_SALT: ${CFDE_MCP_HMAC_SALT:?CFDE_MCP_HMAC_SALT must be set in .env}
   ```
3. Salt into Vector's `.env`, then restart and check:
   ```bash
   cd ~/Documents/git/monode/infrastructure/compose/vector
   echo "CFDE_MCP_HMAC_SALT=$(gcloud secrets versions access latest --secret=cfde-mcp-client-hash-signing-key --project=cdsci-infra)" >> .env
   docker compose up -d vector && docker compose logs --tail 20 vector
   docker exec clickhouse clickhouse-client --user=... --password=... \
     -q "SELECT server, method, outcome, count() FROM mcp_requests WHERE timestamp > now() - INTERVAL 1 HOUR GROUP BY ALL"
   ```

If the salt is missing or empty, the transform drops every event (it never forwards a raw line),
and Vector logs `CFDE_MCP_HMAC_SALT is empty`.

### 9. Traefik MCP headers, the header-only control (#21, separate monode PR)

`infrastructure/compose/traefik/traefik.yml`:

```diff
       names:
         User-Agent: keep
         X-Forwarded-For: keep
         X-Real-Ip: keep
         Cf-Connecting-Ip: keep
         Cf-Ipcountry: keep
         Cf-Ray: keep
+        # MCP 2026-07-28 request headers: what a plain reverse proxy can see without an
+        # MCP-aware gateway (cfde-mcp-analytics D8). Mcp-Name is the tool name, never arguments.
+        Mcp-Method: keep
+        Mcp-Name: keep
+        Mcp-Protocol-Version: keep
```

This is static config, so it needs `docker compose -f compose/traefik/docker-compose.yml up -d traefik`
(a few seconds of downtime for every hostname; pick a quiet moment). No ClickHouse or Vector change
is needed: `traefik_access_log.raw` keeps the whole line, so the control is a query:

```sql
SELECT JSONExtractString(raw, 'request_Mcp-Method') AS method, JSONExtractString(raw, 'request_Mcp-Name') AS tool, count()
FROM traefik_access_log WHERE request_host = 'cfde-mcp.cancerdatasci.org' AND timestamp > now() - INTERVAL 1 DAY
GROUP BY ALL ORDER BY 3 DESC;
```

Only 2026-07-28 clients send these headers; legacy clients put the method in the body, which
Traefik cannot see. That gap is the point of the comparison.

### 10. Verify counts within 5% (#22)

```bash
cd ~/Documents/git/cfde-mcp-analytics
set -a; . collectors/.env; set +a        # CLICKHOUSE_URL/USER/PASSWORD, see step 12
uv run --directory reference-server python ../deploy/onclappc02/verify_counts.py 25
```

The script sends 25 calls per reference tool in each protocol generation (200 in total) through
`https://cfde-mcp.cancerdatasci.org/reference/mcp`. It then prints sent / server log / ClickHouse
per (tool, outcome) and exits 0 when the gateway total is within 5% of the server's own count and
at least 80% of calls are attributed to a client app.

## Phase 5: daily jobs (issue #23, plus the downloads collector)

### 11. Postgres tables and views

```bash
cd ~/Documents/git/cfde-mcp-analytics/collectors
export DATABASE_URL="postgresql://cfde_atlas_dev:$(gcloud secrets versions access latest --secret=cfde-atlas-dev-db-password-onclappc02 --project=cdsci-infra)@127.0.0.1:5432/cfde_atlas_dev"
for f in migrations/000*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done   # all idempotent
```

### 12. Job environment

`collectors/.env` (gitignored, `chmod 600`), read by both units:

```bash
DATABASE_URL=postgresql://cfde_atlas_dev:<password>@127.0.0.1:5432/cfde_atlas_dev
CLICKHOUSE_URL=https://clickhouse.cancerdatasci.org
CLICKHOUSE_USER=<from monode compose/clickhouse/.env>
CLICKHOUSE_PASSWORD=<from monode compose/clickhouse/.env>
```

Dry runs first: `just rollup-mcp --dry-run` and `just collect-downloads --dry-run`.

### 13. Install the timers (copy, don't symlink)

```bash
cp deploy/onclappc02/systemd/cfde-{rollup-mcp,collect-downloads}.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cfde-rollup-mcp.timer cfde-collect-downloads.timer
systemctl --user start cfde-rollup-mcp.service cfde-collect-downloads.service   # once by hand
journalctl --user -u cfde-rollup-mcp.service -n 5
psql "$DATABASE_URL" -c "SELECT server, client_name, SUM(calls) FROM analytics.mcp_daily WHERE date > CURRENT_DATE - 30 GROUP BY 1, 2"
```

`ntfy-notify@.service` is already installed (shared). Failures post to `cdsci-lake-ops`, and the
units' output lands in ClickHouse `systemd_user_jobs`.

### 14. INDEX.md plumbing (monode, with step 8)

Extend the Vector row in "Infrastructure plumbing": "… also tails the cfde-mcp gateway log
(`/data/davsean/cfde_mcp_logs/gateway.log`, rotated by `/etc/logrotate.d/cfde-mcp`) → ClickHouse
`mcp_requests` (90-day TTL, `004_mcp_requests.sql`)." Add the same table to the ClickHouse rows.

## Local validation (done before the PR, no shared resources)

```bash
CFDE_MCP_LOG_DIR=/data/davsean/tmp/cfde-mcp-test/logs docker compose -p cfde-mcp-test \
  -f deploy/onclappc02/docker-compose.yml -f deploy/onclappc02/compose.local.yml up -d --build
curl -s http://127.0.0.1:13311/health                                  # Healthy
just traffic http://127.0.0.1:13311/reference/mcp 5                    # 2026-07-28 client
just traffic http://127.0.0.1:13311/reference/mcp 3 legacy             # 2025-11-25 session
grep -c '"mcp.method.name":"tools/call"' /data/davsean/tmp/cfde-mcp-test/logs/gateway.log
docker logs cfde-mcp-test-reference | grep -c '"event": "tools/call"'  # same number
docker compose -p cfde-mcp-test -f deploy/onclappc02/docker-compose.yml -f deploy/onclappc02/compose.local.yml down
```

Result on 2026-10-14: `/health` 200 `Healthy` and not logged; 20 calls from a 2026-07-28 client
plus 12 from a legacy 2025-11-25 client gave 32 `tools/call` lines in the gateway log and 32 in
the reference server's log. Every line had `route`, `mcp.method.name`, `gen_ai.tool.name`,
`mcp.protocol.version`, `user_agent`, `http.status` and `mcp.tool.is_error`; 2026-07-28 lines
carried `mcp.client.name`, legacy lines carried `mcp.client.session` (with clientInfo on their
`initialize`). Bearer pass-through: the `/cfde-mcp` route pointed at a local upstream that
records headers received `Authorization: Bearer <key>` unchanged, and the key did not appear in
the gateway log.

Pipeline (Phase 4/5) on 2026-10-14, on a throwaway docker network with throwaway ClickHouse,
Postgres and `timberio/vector:0.45.0-debian` containers (the shared ones were not touched). The
chain was the test gateway's log file → Vector with `pipeline/vector/cfde-mcp.yaml` → `mcp_requests`.
- `verify_counts.py 10` (with `GATEWAY_URL`, `REFERENCE_CONTAINER`, `CLICKHOUSE_URL` pointed at the
  test stack) reported sent 80, server 80, gateway 80 (0.0%) and 100% attributed. Legacy-session
  calls were attributed through `mcp_requests_attributed`.
- Calls carrying `CFDESENTINEL7f3a9c` as arguments (including an unknown tool and a bad argument
  type) left 0 hits in the gateway log and in ClickHouse.
- `cfde-rollup-mcp` wrote `raw.mcp_daily_calls` and `raw.mcp_clients_monthly`. Running it twice
  gave the same rows. `analytics.mcp_daily` and `analytics.mcp_clients_monthly` returned 4 and 2
  rows, and every view column has a comment.
- `vector test`: 9/9 pass. With an empty salt every event is dropped.
- `systemd-analyze --user verify` reported nothing on the units.
