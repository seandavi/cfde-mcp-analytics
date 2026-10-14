import json
import tomllib
from pathlib import Path

from cfde_collectors.downloads import DEFAULT_PACKAGES, SOURCES, collect

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = "2026-10-14T12:00:00+00:00"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def parse(registry: str, package: str) -> list[dict]:
    return SOURCES[registry][1](package, load(registry), FETCHED_AT)


def test_pypi():
    rows = parse("pypi", "standards-explorer-mcp")
    assert [(r["date"], r["value"]) for r in rows] == [("2026-10-07", 2), ("2026-10-10", 2), ("2026-10-12", 2)]
    assert {r["metric"] for r in rows} == {"downloads"}


def test_npm():
    rows = parse("npm", "@pipeworx/mcp-gtex")
    assert [(r["date"], r["value"]) for r in rows] == [("2026-10-10", 2), ("2026-10-11", 3), ("2026-10-12", 2)]


def test_dockerhub():
    (row,) = parse("dockerhub", "johnkgardner/perturbseqr-mcp")
    assert (row["date"], row["metric"], row["value"]) == ("2026-10-14", "pull_count", 198)


def test_mcp_registry_counts_exact_name_only():
    (row,) = parse("mcp_registry", "io.github.pipeworx-io/gtex")
    assert (row["metric"], row["value"]) == ("versions_published", 3)
    (none,) = parse("mcp_registry", "io.github.pipeworx-io/gtex-other")
    assert none["value"] == 0


def test_row_keys_unique_and_rerun_stable():
    """(date, registry, package, metric) is the upsert key: no duplicates, and a rerun yields the same keys."""
    packages = tomllib.loads(DEFAULT_PACKAGES.read_text())
    urls = {SOURCES[reg][0](p): reg for reg, names in packages.items() for p in names}

    def fake_fetch(url: str) -> dict:
        return load(urls[url])

    def keys() -> list[tuple]:
        rows, failed = collect(packages, fetch=fake_fetch)
        assert not failed
        return [(r["date"], r["registry"], r["package"], r["metric"]) for r in rows]

    first = keys()
    assert len(first) == len(set(first))
    assert first == keys()


def test_failure_is_reported_not_fatal():
    def flaky(url: str) -> dict:
        if "npmjs" in url:
            raise OSError("boom")
        return load("pypi")

    rows, failed = collect({"pypi": ["standards-explorer-mcp"], "npm": ["x"]}, fetch=flaky)
    assert failed == ["npm:x"] and len(rows) == 3
