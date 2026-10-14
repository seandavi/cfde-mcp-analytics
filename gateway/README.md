# gateway

[agentgateway](https://github.com/agentgateway/agentgateway) config fronting GlyGen, Playbook
Workflow Builder and PerturbSeqr. Findings: [docs/spike-agentgateway.md](../docs/spike-agentgateway.md).

## Run locally

```bash
# Linux x86_64 binary, v1.6.0 (verify the .sha256 next to it on the release page)
curl -fsSLO https://github.com/agentgateway/agentgateway/releases/download/v1.6.0/agentgateway-linux-amd64
chmod +x agentgateway-linux-amd64
./agentgateway-linux-amd64 -f gateway/config.yaml --validate-only
./agentgateway-linux-amd64 -f gateway/config.yaml > gateway.log   # JSON access log on stdout
```

| URL | Upstream |
|---|---|
| `http://127.0.0.1:3311/glygen/mcp` | `https://mcp.glygen.org/mcp` |
| `http://127.0.0.1:3311/pwb/mcp` | `https://playbook-workflow-builder.cloud/api/mcp` |
| `http://127.0.0.1:3311/perturbseqr/mcp` | `https://perturbseqr.maayanlab.cloud/mcp` |

- Metrics: `curl -s 127.0.0.1:15020/metrics | grep agentgateway_mcp_requests_total`
- Admin UI: `http://127.0.0.1:15000/ui`
- Access log lines are the ones with `"scope":"request"`.

Quick client check (official Python SDK):

```bash
uv run --no-project --with 'mcp==2.3.0' python -c '
import asyncio
from mcp.client.client import Client
async def main():
    async with Client("http://127.0.0.1:3311/glygen/mcp") as c:
        print(c.session.protocol_version, [t.name for t in (await c.list_tools()).tools][:5])
asyncio.run(main())'
```

The upstreams are other teams' production servers: keep test traffic light and read-only.
