# MCP Client Routing Policy

## Status

Accepted

## Scope

repository/mcp-client-routing

## Decision

## File Boundary

This ADR is a canonical policy record. It owns repository-safe MCP client routing posture. It must
not track private client configuration, personal remote hosts, credentials, or tool-specific AI
editor setup.

## repo.mcp.client-routing.no-tracked-external-client-config

```json strict-policy
{
  "anchor": "repo.mcp.client-routing.no-tracked-external-client-config",
  "rule": "External MCP client configuration is operator-local and must not be committed to this product repository.",
  "forbidden_tracked_paths": [".cursor/mcp.json", ".cursor/rules/**", ".codex/**", "codex/**"],
  "allowed_repository_surfaces": [
    "src/mcp/**",
    "src/mcp/README.md",
    "tests/mcp/**",
    "docs/adr/mcp-*.md"
  ]
}
```
## repo.mcp.client-routing.local-product-surface

```json strict-policy
{
  "anchor": "repo.mcp.client-routing.local-product-surface",
  "rule": "The repository-owned MCP surface is local product functionality, not a committed external-client setup.",
  "default_transport": "stdio",
  "http_posture": [
    "loopback by default",
    "operator-provided public base URL when explicitly launched",
    "no committed client registration, bearer token, password, or remote host configuration"
  ],
  "required_posture": [
    "keep offline scenario drafting and validation local by default",
    "document runtime setup as operator environment configuration",
    "separate Make import readiness from client handoff readiness in compact tool output",
    "do not commit personal MCP client files"
  ]
}
```
## repo.mcp.client-routing.live-mutation-consent

```json strict-policy
{
  "anchor": "repo.mcp.client-routing.live-mutation-consent",
  "rule": "Live Make.com or third-party mutations remain explicitly gated and must not be hidden inside repository-local MCP defaults.",
  "required_posture": [
    "local catalog-backed planning may run without live credentials",
    "external live operations require explicit operator approval and configured credentials",
    "missing live account connections are runtime setup notes, not blockers for offline validation",
    "missing handoff notes are client handoff blockers, not Make import blockers"
  ]
}
```
## Rationale

The product repository can expose local MCP-compatible functionality while still remaining
client-ready. Personal MCP client files and remote endpoint bindings belong outside the repository
or in the private operator control plane.

## Consequences

- `.cursor/mcp.json` is retired from the tracked repository.
- MCP docs describe local product commands and leave external client setup to the
operator environment.
- Tests verify absence of committed private client configuration.

## Validation

- No tracked `.cursor/mcp.json` may exist.
- MCP docs must distinguish local repository commands from external client
configuration.
- Repository validation or focused documentation checks must report blockers.

## Related Material

- Former ADR ID: `001067`.
- Decision ID: `repo.mcp.client-routing-native-gpt-integration`.
- Previous numeric filename was removed during the common Markdown ADR migration.
