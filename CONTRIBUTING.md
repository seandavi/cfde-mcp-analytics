# Contributing

- Work is tracked as GitHub issues, grouped into milestones by phase of the
  [POC plan](docs/poc-plan.md).
- One branch and pull request per issue; reference it with `Closes #N`.
- PRs merge when CI is green.
- Python: `uv` for packaging, `ruff` for linting, `pyright` for types,
  `pytest` for tests. Tasks run through `just`.
- Privacy rule: never log or store MCP tool arguments, results, or raw client
  IPs. Any change to what is logged needs a test proving that.
