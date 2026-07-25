# ruff: noqa: ERA001
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns the public prompt contract for the single Catalog Intelligence
# MCP prompt.
# split: Move prompt ingestion assertions into a focused catalog prompt contract
# file.
# validation: Focused pytest contract plus pancakes.mcp.smoke.
# review: Operator-requested Catalog Intelligence ingestion command update.

"""Tests for retired Make UI import/export review MCP Markdown.

Boundary contract:
- Owns: absence of retired Make UI review Markdown from the MCP source tree.
- Must not: log in, call Make.com, open browsers, or execute provider mutations.
- Allows: prompt registry assertions.
- Split when: browser automation becomes an executable MCP tool.
- Merge when: MCP context-resource tests own this exact resource contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from mcp import (
    CATALOG_INTELLIGENCE_PROMPT_ALIASES,
    CATALOG_INTELLIGENCE_PROMPT_NAME,
    get_mcp_prompt,
    mcp_prompt_registry,
    mcp_resource_registry,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_MCP_CONTEXT_ROOT = REPO_ROOT / "src/mcp/old"


def test_make_ui_review_markdown_is_removed_from_public_mcp_context() -> None:
    """Retired Make UI review Markdown is not a public MCP resource or tracked.

    source.
    """
    resources = {resource.uri: resource for resource in mcp_resource_registry()}
    prompts = {prompt.name: prompt for prompt in mcp_prompt_registry()}

    assert resources == {}, (
        f"Retired Markdown resources must not be listed: {resources}"
    )
    assert tuple(prompts) == (CATALOG_INTELLIGENCE_PROMPT_NAME,), (
        f"Only the catalog prompt should remain public: {prompts}"
    )
    assert not LEGACY_MCP_CONTEXT_ROOT.exists(), (
        f"Retired MCP Markdown folder must stay removed: "
        f"{LEGACY_MCP_CONTEXT_ROOT}"
    )


def test_catalog_intelligence_prompt_is_ingestion_652158b9() -> None:
    """The prompt is the explicit local catalog ingestion worker protocol.

    Raises:
        AssertionError: If the operation cannot complete.
    """
    prompt = get_mcp_prompt(
        repo_root=REPO_ROOT, name=CATALOG_INTELLIGENCE_PROMPT_NAME
    )
    alias_prompt = get_mcp_prompt(repo_root=REPO_ROOT, name="Catalog Work")
    messages = cast("Sequence[Mapping[str, object]]", prompt["messages"])
    first_message = messages[0]
    content = cast("Mapping[str, object]", first_message["content"])
    text = cast("str", content["text"])
    index_lookup = cast(
        "Mapping[str, object]", prompt["canonical_index_lookup"]
    )

    assert prompt["canonical_prompt_trigger"] == "Catalog Intelligence"
    assert alias_prompt["canonical_prompt_trigger"] == "Catalog Intelligence"
    assert "Catalog Work" in CATALOG_INTELLIGENCE_PROMPT_ALIASES
    assert "Catallog Inteligence" not in CATALOG_INTELLIGENCE_PROMPT_ALIASES
    accepted_aliases = cast("Sequence[str]", prompt["accepted_aliases"])
    assert "Catalog Work" in accepted_aliases
    assert "Catallog Inteligence" not in accepted_aliases
    try:
        _ = get_mcp_prompt(repo_root=REPO_ROOT, name="Catallog Inteligence")
    except ValueError as exc:
        assert "Unknown MCP prompt" in str(exc)
    else:
        msg = "Misspelled Catalog Intelligence alias must stay unsupported."
        raise AssertionError(msg)
    assert "canonical_placeholder_index" not in prompt
    assert "canonical_value_index" not in prompt
    assert index_lookup["tool_name"] == "catalog.index"
    assert index_lookup["operation_mode"] == "read_only_local_catalog_index"
    assert index_lookup["full_index_payload_embedded_in_prompt"] is False
    assert cast("int", index_lookup["placeholder_index_row_count"]) > 1
    assert cast("int", index_lookup["value_index_row_count"]) > 1
    required_fragments = (
        "Catalog Intelligence ",
        "Canonical prompt trigger: `Catalog Intelligence`.",
        "Accepted legacy alias: `Catalog Work`.",
        "Use Pancakes MCP only.",
        "Call `catalog.work.next` with a stable worker_id",
        (
            "Use `catalog.graph.search` and `catalog.semantic.preview` before "
            "saving"
        ),
        "Save the entire leased batch atomically with `catalog.work.save`",
        "`lease_handle`",
        "Never save partial leased batches.",
        "no provider calls ",
        "no live Make.com calls ",
        "no credential values ",
        "no public reset tool",
    )
    for fragment in required_fragments:
        assert fragment in text
    forbidden_fragments = (
        "Loop forever:",
        "`CATALOG INTELLIGENCE DO 100, DO NOT SIMPLIFY PAYLOAD`",
        "Immediately call `catalog.work.next` again.",
        "`[PERSON_FULL_NAME_FORMAT_1]`: Names such as John Doe or Jane Smith",
        "`catalog_runs.run_status`:",
        "Accepted alias for old chats",
    )
    for fragment in forbidden_fragments:
        assert fragment not in text
