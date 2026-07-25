# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for repository-safe MCP client guidance.

Boundary contract:
- Owns: static checks that external MCP client configuration stays out of the
  client-ready product repository.
- Must not: start MCP transports, call servers, or validate OAuth flows.
- Allows: static path and documentation checks.
- Split when: live MCP client smoke tests become separately automated.
- Merge when: another MCP contract duplicates client routing policy checks.
"""

from __future__ import annotations

from pathlib import Path

MCP_CLIENT_CONFIG = Path(".cursor/mcp.json")
MCP_CLIENT_POLICY_ADR = Path(
    "docs/adr/mcp-client-routing-and-native-gpt-integration-policy.md"
)
MCP_README = Path("src/mcp/README.md")


def test_external_mcp_client_config_is_not_tracked() -> None:
    """External MCP client configuration must stay operator-local."""
    assert not MCP_CLIENT_CONFIG.exists(), (
        f"Tracked MCP client config must be absent: {MCP_CLIENT_CONFIG}"
    )
    assert not Path(".cursor/rules").exists(), (
        "Cursor rule folders must not be tracked."
    )
    assert not Path(".codex").exists(), (
        "Codex private config folders must not be tracked."
    )


def test_mcp_client_policy_documents_local_product_boundary() -> None:
    """ADR and README describe local MCP product commands, not client setup."""
    adr_text = " ".join(
        MCP_CLIENT_POLICY_ADR.read_text(encoding="utf-8").split()
    )
    readme_text = " ".join(MCP_README.read_text(encoding="utf-8").split())

    required_adr_fragments = (
        "repo.mcp.client-routing.no-tracked-external-client-config",
        "repo.mcp.client-routing.local-product-surface",
        "repo.mcp.client-routing.live-mutation-consent",
        ".cursor/mcp.json",
        "operator-local",
    )
    missing_adr_fragments = [
        fragment
        for fragment in required_adr_fragments
        if fragment not in adr_text
    ]
    assert not missing_adr_fragments, (
        f"MCP client routing ADR is missing fragments: {missing_adr_fragments}"
    )

    required_readme_fragments = (
        "does not track external MCP client configuration",
        "repository-local startup contract",
        "operator-provided public base URL",
        "must stay local",
    )
    missing_readme_fragments = [
        fragment
        for fragment in required_readme_fragments
        if fragment not in readme_text
    ]
    assert not missing_readme_fragments, (
        f"MCP README is missing operating guidance: {missing_readme_fragments}"
    )
