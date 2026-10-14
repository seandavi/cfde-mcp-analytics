"""Floor-metrics collector: public download / pull counts for tracked MCP packages.

Fetches PyPI (pypistats), npm, Docker Hub and the official MCP Registry, and lands one
row per (date, registry, package, metric) into raw.mcp_downloads, following the
cfde-atlas-etl ELT convention (natural key + `source` jsonb + `fetched_at`, upserted).

    cfde-collect-downloads --dry-run          # print rows as JSON, no DB
    DATABASE_URL=postgresql://... cfde-collect-downloads
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

Row = dict[str, Any]

DEFAULT_PACKAGES = Path(__file__).resolve().parents[2] / "packages.toml"


def _row(date: str, registry: str, package: str, metric: str, value: int, source: Any, fetched_at: str) -> Row:
    return {
        "date": date,
        "registry": registry,
        "package": package,
        "metric": metric,
        "value": value,
        "source": source,
        "fetched_at": fetched_at,
    }


# --- parsers: pure, one per registry, tested against recorded fixtures ---------------


def parse_pypi(package: str, payload: dict[str, Any], fetched_at: str) -> list[Row]:
    # ponytail: pypistats omits zero-download days; the view treats a missing day as no row, not 0.
    return [
        _row(d["date"], "pypi", package, "downloads", d["downloads"], d, fetched_at)
        for d in payload["data"]
        if d["category"] == "without_mirrors"
    ]


def parse_npm(package: str, payload: dict[str, Any], fetched_at: str) -> list[Row]:
    return [_row(d["day"], "npm", package, "downloads", d["downloads"], d, fetched_at) for d in payload["downloads"]]


def parse_dockerhub(package: str, payload: dict[str, Any], fetched_at: str) -> list[Row]:
    keep = {k: payload.get(k) for k in ("namespace", "name", "pull_count", "star_count", "last_updated")}
    return [_row(fetched_at[:10], "dockerhub", package, "pull_count", payload["pull_count"], keep, fetched_at)]


def parse_mcp_registry(package: str, payload: dict[str, Any], fetched_at: str) -> list[Row]:
    # search= is a substring match, so keep only exact-name entries (one per published version).
    entries = [s for s in payload["servers"] if s["server"]["name"] == package]
    source = [{"version": s["server"].get("version"), "_meta": s.get("_meta")} for s in entries]
    return [_row(fetched_at[:10], "mcp_registry", package, "versions_published", len(entries), source, fetched_at)]


SOURCES: dict[str, tuple[Callable[[str], str], Callable[[str, dict[str, Any], str], list[Row]]]] = {
    "pypi": (lambda p: f"https://pypistats.org/api/packages/{p}/overall?mirrors=false", parse_pypi),
    "npm": (lambda p: f"https://api.npmjs.org/downloads/range/last-month/{p}", parse_npm),
    "dockerhub": (lambda p: f"https://hub.docker.com/v2/repositories/{p}", parse_dockerhub),
    "mcp_registry": (
        lambda p: (
            "https://registry.modelcontextprotocol.io/v0.1/servers?"
            + urllib.parse.urlencode({"search": p, "limit": 100})
        ),
        parse_mcp_registry,
    ),
}


def fetch_json(url: str, attempts: int = 3) -> dict[str, Any]:
    # pypistats intermittently returns 502; a couple of retries clears it.
    req = urllib.request.Request(url, headers={"User-Agent": "cfde-mcp-analytics collector"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(2**i)
    raise AssertionError("unreachable")


def collect(
    packages: dict[str, list[str]], fetch: Callable[[str], dict[str, Any]] = fetch_json
) -> tuple[list[Row], list[str]]:
    """Return (rows, failed "registry:package" names)."""
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    rows: list[Row] = []
    failed: list[str] = []
    for registry, names in packages.items():
        url_for, parse = SOURCES[registry]
        for name in names:
            try:
                rows += parse(name, fetch(url_for(name)), fetched_at)
            except Exception as e:  # one bad package must not drop the others
                print(f"WARN {registry}:{name}: {e}", file=sys.stderr)
                failed.append(f"{registry}:{name}")
    return rows, failed


UPSERT = """
INSERT INTO raw.mcp_downloads (date, registry, package, metric, value, source, fetched_at)
VALUES (%(date)s, %(registry)s, %(package)s, %(metric)s, %(value)s, %(source)s, %(fetched_at)s)
ON CONFLICT (date, registry, package, metric) DO UPDATE SET
    value = EXCLUDED.value,
    source = EXCLUDED.source,
    fetched_at = EXCLUDED.fetched_at;
"""


def write(rows: list[Row], database_url: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.executemany(UPSERT, [{**r, "source": json.dumps(r["source"])} for r in rows])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packages", type=Path, default=DEFAULT_PACKAGES)
    ap.add_argument("--dry-run", action="store_true", help="print rows as JSON instead of writing to Postgres")
    args = ap.parse_args()

    rows, failed = collect(tomllib.loads(args.packages.read_text()))
    if args.dry_run:
        json.dump(rows, sys.stdout, indent=1)
        print()
    else:
        if not (url := os.environ.get("DATABASE_URL")):
            sys.exit("DATABASE_URL is not set (use --dry-run to print rows instead)")
        write(rows, url)
        print(f"upserted {len(rows)} rows into raw.mcp_downloads", file=sys.stderr)
    if failed:  # rows that did fetch are kept; non-zero exit lets the scheduler's OnFailure alert fire
        sys.exit(f"failed: {', '.join(failed)}")
