# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for the minimal Pancakes MCP public surface.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from mcp import (
    MCP_CANONICAL_URL,
    MCP_SERVER_NAME,
    REQUIRED_TOOL_NAMES,
    build_public_tool_annotation_matrix,
    execute_mcp_tool,
    mcp_tool_registry,
    start_mcp_test_server,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_TOOL_NAMES = (
    "mcp.session.start ",
    "catalog.index ",
    "catalog.search ",
    "catalog.inspect ",
    "catalog.graph.search ",
    "catalog.semantic.preview ",
    "catalog.work.next ",
    "catalog.work.save ",
    "catalog.modify ",
    "catalog.node.modify ",
    "catalog.edge.propose ",
    "catalog.edge.apply ",
    "catalog.review.add ",
    "project.search ",
    "project.draft.stage ",
    "project.draft.import ",
    "project.create ",
    "project.health ",
    "project.view ",
    "project.edit ",
    "project.verify ",
    "project.capabilities.inspect ",
    "project.make ",
    "project.package.inspect ",
    "project.next ",
    "project.modules.view ",
    "project.modules.add ",
    "project.modules.modify ",
    "project.modules.delete ",
    "project.links.view ",
    "project.filters.view ",
    "project.filters.add ",
    "project.filters.modify ",
    "project.filters.delete ",
    "project.error_handlers.view ",
    "project.error_handlers.add ",
    "project.error_handlers.modify ",
    "project.error_handlers.delete ",
    "documentation.generate ",
    "documentation.validate ",
    "onboarding.validate ",
    "linter.quarantine.write ",
    "linter.rule.next ",
    "linter.rule.inspect ",
    "linter.rule.implement ",
    "linter.rule.merge_canonical ",
    "linter.rule.reject_invalid ",
    "linter.rule.edit ",
    "linter.rule.status ",
    "linter.rule.rollback ",
    "backlog.add ",
    "backlog.list ",
    "backlog.end",
)
REMOVED_TOOL_NAMES = (
    ("project", "list"),
    ("project", "blueprint_query"),
    ("project", "inspect"),
    ("project", "tests", "run"),
    ("project", "tests", "template"),
    ("project", "tests", "write"),
    ("scraper", "refresh_status"),
    ("catalog", "status"),
    ("catalog", "plan"),
    ("catalog", "generation_audit"),
    ("catalog", "next_unit"),
    ("catalog", "save_unit"),
    ("catalog", "checkpoint_unit"),
    ("catalog", "autosave_unit"),
)


def test_mcp_server_exports_only_minimal_public_tools() -> None:
    """The public MCP tool list is intentionally small and ordered."""
    server = start_mcp_test_server()

    assert server.started is True
    assert server.config.server_name == MCP_SERVER_NAME == "blueprint-mcp"
    assert (
        server.config.canonical_url
        == MCP_CANONICAL_URL
        == "repo://blueprint/mcp"
    )
    assert REQUIRED_TOOL_NAMES == EXPECTED_TOOL_NAMES
    assert tuple(tool.name for tool in server.tools) == EXPECTED_TOOL_NAMES
    assert (
        tuple(tool.name for tool in mcp_tool_registry()) == EXPECTED_TOOL_NAMES
    )


def test_removed_mcp_tools_are_not_dispatchable(tmp_path: Path) -> None:
    """Deleted MCP tools fail as unknown tools instead of keeping hidden.

    routes.
    """
    for removed_parts in REMOVED_TOOL_NAMES:
        tool_name = ".".join(removed_parts)
        result = execute_mcp_tool(
            tool_name=tool_name, arguments={}, repo_root=tmp_path
        )
        assert not result.ok, f"{tool_name} unexpectedly dispatched: {result}"
        assert result.error == f"Unknown MCP tool: {tool_name}"


def test_annotations_match_minimal_surface_and_local_boundary() -> None:
    """Tool annotations keep the public surface local and technical."""
    descriptions = {tool.name: tool.description for tool in mcp_tool_registry()}
    schemas = {tool.name: tool.input_schema() for tool in mcp_tool_registry()}
    matrix = build_public_tool_annotation_matrix(tool_descriptions=descriptions)
    tools = cast("dict[str, object]", matrix["tools"])

    assert matrix["tool_count"] == len(EXPECTED_TOOL_NAMES)
    assert tuple(tools) == EXPECTED_TOOL_NAMES
    assert (
        "repository-local Make scenario drafts"
        in descriptions["project.search"]
    )
    assert "external business database" in descriptions["project.search"]
    assert "canonical placeholder" in descriptions["catalog.index"]
    assert "Pancakes Core SQLite SSOT" in descriptions["catalog.search"]
    assert "Pancakes Core SQLite SSOT" in descriptions["catalog.inspect"]
    assert "no raw sql" in descriptions["catalog.modify"].casefold()
    assert (
        "dry_run validates locally without writing"
        in descriptions["catalog.modify"]
    )
    assert "no raw sql" in descriptions["catalog.node.modify"].casefold()
    assert "no raw sql" in descriptions["catalog.edge.propose"].casefold()
    assert (
        "approved catalog edge proposal"
        in descriptions["catalog.edge.apply"].casefold()
    )
    assert (
        "dry_run validates locally without writing"
        in descriptions["catalog.review.add"]
    )
    assert (
        "documentation base"
        in descriptions["documentation.generate"].casefold()
    )
    assert (
        "send only placeholder names"
        in descriptions["onboarding.validate"].casefold()
    )
    search_properties = cast(
        "dict[str, object]", schemas["project.search"]["properties"]
    )
    create_properties = cast(
        "dict[str, object]", schemas["project.create"]["properties"]
    )
    module_delete_properties = cast(
        "dict[str, object]",
        schemas["project.modules.delete"]["properties"],
    )
    documentation_generate_properties = cast(
        "dict[str, object]",
        schemas["documentation.generate"]["properties"],
    )
    documentation_validate_properties = cast(
        "dict[str, object]",
        schemas["documentation.validate"]["properties"],
    )
    onboarding_properties = cast(
        "dict[str, object]", schemas["onboarding.validate"]["properties"]
    )
    backlog_list_properties = cast(
        "dict[str, object]", schemas["backlog.list"]["properties"]
    )
    backlog_end_properties = cast(
        "dict[str, object]", schemas["backlog.end"]["properties"]
    )
    assert "lifecycle_status" not in search_properties
    assert "include_deleted" not in search_properties
    for absent_create_field in (
        "customer_number ",
        "customer_key ",
        "customer_folder_key ",
        "intent ",
        "customer_intent ",
        "blueprint_json ",
        "make_blueprint_json ",
        "blueprint_artifact_path ",
        "make_blueprint_artifact_path ",
        "blueprint_artifact_sha256",
    ):
        assert absent_create_field not in create_properties
    assert "staged_draft_path" in create_properties
    assert "staged_draft_sha256" in create_properties
    assert "workspace_folder_key" in create_properties
    assert "confirm" not in module_delete_properties
    assert "confirm_module_id" not in module_delete_properties
    assert "output_mode" in documentation_generate_properties
    assert "dry_run" in documentation_generate_properties
    assert "output_mode" in documentation_validate_properties
    assert "project_id" in onboarding_properties
    assert "provided_placeholders_json" in onboarding_properties
    assert "onboarding_json" not in onboarding_properties
    assert "output_mode" in onboarding_properties
    assert "include_closed" not in backlog_list_properties
    assert "include_payload" in backlog_list_properties
    assert "source_ref" in backlog_end_properties


def test_project_draft_tool_schemas_avoid_raw_json_arguments() -> None:
    """Project draft intake tools expose staged path contracts, not raw JSON.

    payloads.
    """
    schemas = {tool.name: tool.input_schema() for tool in mcp_tool_registry()}
    stage_properties = cast(
        "dict[str, object]", schemas["project.draft.stage"]["properties"]
    )
    import_properties = cast(
        "dict[str, object]", schemas["project.draft.import"]["properties"]
    )

    assert "scenario_summary" in stage_properties
    assert "blueprint_json" not in stage_properties
    assert "make_blueprint_json" not in stage_properties
    assert "source_artifact_path" in import_properties
    assert "source_artifact_sha256" in import_properties
    assert "blueprint_json" not in import_properties
    assert "make_blueprint_json" not in import_properties
