# ruff: noqa: ERA001
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001067#repo.mcp.client-routing.native-gpt-latency-and-output
# - docs/adr/catalog-semantic-graph-preview-policy.md
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns public MCP prompt text and accepted operator aliases.
# split: Move worker orchestration prompts into a dedicated prompt module when
# more prompts exist.
# validation: pancakes.mcp.smoke and focused prompt contract tests.
# review: Operator-requested Catalog Intelligence ingestion command update.

"""MCP prompt registry for Pancakes IDE clients.

Boundary contract:
- Owns: MCP prompt definitions for Catalog Intelligence worker routing.
- Must not: execute tools, mutate project drafts, call providers, or expose
secrets.
- Allows: exposing a single explicit Catalog Intelligence prompt for local
catalog ingestion.
- Split when: catalog semantic-worker orchestration becomes a separate transport
surface.
- Merge when: another module exposes the same prompt payload.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from mcp.catalog_index import catalog_index_lookup_summary_payload
from mcp.models import McpPromptDefinition, McpResourceDefinition

if TYPE_CHECKING:
    from mcp.models import JsonObject

CATALOG_INTELLIGENCE_PROMPT_NAME: Final = "Catalog Intelligence"
CATALOG_INTELLIGENCE_PROMPT_ALIASES: Final[tuple[str, ...]] = ("Catalog Work",)
CATALOG_INTELLIGENCE_PROMPT_RELATIVE_PATH: Final = Path(
    "docs/operations/catalog-intelligence-prompt.md"
)
CATALOG_INTELLIGENCE_PROMPT_BODY_MARKER: Final = "## Prompt Body"


def mcp_resource_registry() -> tuple[McpResourceDefinition, ...]:
    """Return public MCP resources.

    Markdown resources were retired from public discovery and from tracked
    source.
    """
    return ()


def read_mcp_resource(*, repo_root: Path, uri: str) -> JsonObject:
    """Reject public MCP resource reads after Markdown resource retirement.

    Raises:
        ValueError: Always raised because public Markdown resources are retired.
    """
    del repo_root
    message = f"MCP Markdown resources are retired from public discovery: {uri}"
    raise ValueError(message)


def mcp_prompt_registry() -> tuple[McpPromptDefinition, ...]:
    """Return the computed result for the caller."""
    return (
        McpPromptDefinition(
            name=CATALOG_INTELLIGENCE_PROMPT_NAME,
            description=(
                "Catalog ingestion worker protocol backed by local SQLite "
                "leases and "
                "atomic saves; no provider or live Make.com calls."
            ),
        ),
    )


def get_mcp_prompt(*, repo_root: Path, name: str) -> JsonObject:
    """Return one MCP prompt payload loaded from the repository prompt.

    authority.
    """
    prompt = _prompt_definition(name)
    prompt_text = _catalog_intelligence_prompt_text(repo_root=repo_root)
    return {
        "canonical_prompt_trigger": CATALOG_INTELLIGENCE_PROMPT_NAME,
        "accepted_aliases": list(CATALOG_INTELLIGENCE_PROMPT_ALIASES),
        "canonical_index_lookup": catalog_index_lookup_summary_payload(),
        "description": prompt.description,
        "messages": (
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": prompt_text,
                },
            },
        ),
    }


def _prompt_definition(name: str) -> McpPromptDefinition:
    for prompt in mcp_prompt_registry():
        if prompt.name == name or name in CATALOG_INTELLIGENCE_PROMPT_ALIASES:
            return prompt
    message = f"Unknown MCP prompt: {name}"
    raise ValueError(message)


def _catalog_intelligence_prompt_text(*, repo_root: Path) -> str:
    """Return the catalog ingestion prompt body from its repository authority.

    file.

    Raises:
        ValueError: If the prompt authority file is missing the body marker.
    """
    prompt_path = repo_root / CATALOG_INTELLIGENCE_PROMPT_RELATIVE_PATH
    text = prompt_path.read_text(encoding="utf-8")
    marker = f"{CATALOG_INTELLIGENCE_PROMPT_BODY_MARKER}\n\n"
    if marker not in text:
        message = (
            "Catalog Intelligence prompt authority is missing the Prompt Body "
            "marker: "
            f"{CATALOG_INTELLIGENCE_PROMPT_RELATIVE_PATH}"
        )
        raise ValueError(message)
    return text.split(marker, maxsplit=1)[1].strip() + "\n"
