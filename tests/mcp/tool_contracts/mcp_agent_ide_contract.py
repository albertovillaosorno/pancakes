# ruff: noqa: E501, PLR0914, PLR0915
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Agent-IDE MCP contracts for local Make scenario work.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mcp import execute_mcp_tool, mcp_tool_registry

from tests.mcp.tool_contracts.mcp_compact_assertions import (
    assert_compact_response_bounded,
    assert_hidden_counts_when_truncated,
    assert_next_query_when_raw_omitted,
    assert_no_ambiguous_available_flags,
    assert_no_bare_ready_when_surfaces_differ,
    assert_no_duplicate_summary_payload,
    assert_no_empty_detail_arrays_in_compact,
    assert_no_orphan_capabilities,
    assert_no_raw_walls,
    assert_no_secret_or_credential_values,
    assert_safety_flags_false,
)

if TYPE_CHECKING:
    import pytest
    from mcp.models import McpToolCallReport

    from tests.support.json_payloads import JsonObject


def _assert_generated_project_path_report(
    record: JsonObject,
    *,
    logical_project_path: str,
    physical_artifact_path: str,
    scenario_path_text: str,
) -> None:
    assert record["logical_project_path"] == logical_project_path
    assert (
        record["logical_scenario_path"]
        == f"{logical_project_path}/scenario.json"
    )
    assert record["physical_artifact_path"] == physical_artifact_path
    assert record["physical_scenario_artifact_path"] == scenario_path_text
    assert record["artifact_policy_status"] == "approved_generated_state"
    assert record["generated_state_physical_path"] is True
    assert not str(record["physical_artifact_path"]).startswith("projects/")


def _assert_legacy_project_path_report(
    record: JsonObject, *, project_id: str
) -> None:
    assert record["logical_project_path"] == f"projects/{project_id}"
    assert (
        record["logical_scenario_path"]
        == f"projects/{project_id}/scenario.json"
    )
    assert record["physical_artifact_path"] == f"projects/{project_id}"
    assert (
        record["physical_scenario_artifact_path"]
        == f"projects/{project_id}/scenario.json"
    )
    assert record["artifact_policy_status"] == "legacy_repo_project_artifact"
    assert record["generated_state_physical_path"] is False
    plan = cast("JsonObject", record["legacy_migration_plan"])
    assert plan["status"] == "migration_recommended"
    assert (
        plan["source_scenario_path"] == f"projects/{project_id}/scenario.json"
    )
    assert (
        plan["target_generated_state_root"] == "temp/pancakes/project-artifacts"
    )
    assert "project.verify passes" in str(plan["cleanup_allowed_after"])


def _assert_template_library_path_report(record: JsonObject) -> None:
    assert record["logical_project_path"] == "projects/templates"
    assert record["logical_scenario_path"] == "projects/templates/scenario.json"
    assert record["physical_artifact_path"] == "projects/templates"
    assert (
        record["physical_scenario_artifact_path"]
        == "projects/templates/scenario.json"
    )
    assert record["artifact_policy_status"] == "approved_repo_template_library"
    assert record["generated_state_physical_path"] is False
    plan = cast("JsonObject", record["legacy_migration_plan"])
    assert plan["status"] == "not_required"


def _assert_binding_bridge_detail(
    detail: JsonObject,
    *,
    status: str,
    resource_kind: str,
    contract_status: str = "operator_bridge_ready",
) -> None:
    assert detail["status"] == status
    assert detail["owning_layer"] == "make_api_bridge"
    assert detail["fallback_strategy"] == "use_guarded_operator_live_bridge"
    contract = cast("JsonObject", detail["binding_bridge_contract"])
    assert contract["resource_kind"] == resource_kind
    assert contract["contract_status"] == contract_status
    observed = cast("JsonObject", contract["observed_binding_contract"])
    if resource_kind == "webhook":
        assert (
            observed["live_evidence"]
            == "make_mcp_webhook_bind_lifecycle_shapes"
        )
        assert (
            observed["bound_hook_id_path"]
            == "$.blueprint.flow[0].parameters.hook"
        )
        assert observed["hook_scenario_id_path"] == "$.scenarioId"
    elif resource_kind == "connection":
        assert (
            observed["live_evidence"]
            == "make_mcp_connection_bind_lifecycle_shapes"
        )
        assert (
            observed["bound_connection_id_path"]
            == "$.blueprint.flow[0].parameters.__IMTCONN__"
        )
        assert observed["module_connection_target"] == "__IMTCONN__"
    else:
        assert observed == {}
    assert contract["dry_run_first"] is True
    assert contract["requires_operator_approval"] is False
    assert contract["requires_session_scope"] is True
    assert contract["pancakes_executes_live_operations"] is True
    assert (
        contract["target_module_policy"]
        == "inactive_scratch_scenario_module_only"
    )
    forbidden = cast("tuple[str, ...]", contract["forbidden_input_fields"])
    assert "credential_value" in forbidden
    assert "secret" in forbidden
    assert detail["bridge_evidence_status"] == contract_status
    assert "missing_capability_error" not in detail


def _assert_projected_make_native_notes(
    projected_notes: list[JsonObject],
) -> None:
    assert len(projected_notes) >= 7
    assert all("content" in note for note in projected_notes)
    assert all("moduleIds" in note for note in projected_notes)
    assert (
        cast("JsonObject", projected_notes[0]["metadata"])["color"] == "#9138FE"
    )
    assert any(
        cast("JsonObject", note["metadata"])["color"] == "#22B8B8"
        for note in projected_notes
    )
    assert projected_notes[0]["moduleIds"] == [1]
    assert any(note["moduleIds"] == [1, 2] for note in projected_notes)
    projected_notes_json = json.dumps(projected_notes, sort_keys=True)
    assert "target_node_id" not in projected_notes_json
    assert "source_node_id" not in projected_notes_json
    assert "body" not in projected_notes_json
    assert "MOD-1" in projected_notes_json
    assert "PDF index" in projected_notes_json
    assert "NOTE-MOD-1" in projected_notes_json
    assert "NOTE-CONN-1-2" in projected_notes_json


def _assert_lead_alert_generated_scenario(scenario: JsonObject) -> None:
    flow = cast("list[JsonObject]", scenario["flow"])
    assert [module["module"] for module in flow] == [
        "gateway:CustomWebHook ",
        "builtin:BasicRouter ",
        "datastore:AddRecord",
    ]
    datastore = flow[2]
    break_handler = cast("list[JsonObject]", datastore["onerror"])[0]
    router = flow[1]
    route = cast("list[JsonObject]", router["routes"])[0]
    route_flow = cast("list[JsonObject]", route["flow"])
    assert route_flow[0]["module"] == "slack:ActionCreateMessage"
    assert break_handler["module"] == "builtin:Break"
    assert cast("JsonObject", break_handler["mapper"])["retry"] == "{{true}}"
    metadata = cast("JsonObject", scenario["metadata"])
    scenario_settings = cast("JsonObject", metadata["scenario"])
    assert scenario_settings["sequential"] is True
    assert scenario_settings["dlq"] is True
    assert scenario_settings["confidential"] is False
    imported_metadata = cast(
        "JsonObject", metadata["imported_blueprint_metadata"]
    )
    catalog_assist = cast("JsonObject", imported_metadata["catalog_assist"])
    selected_modules = cast(
        "tuple[str, ...]", catalog_assist["selected_modules"]
    )
    creation = cast("JsonObject", imported_metadata["creation"])
    assert "slack:ActionCreateMessage" in selected_modules
    assert creation["customer_deliverable"] == "make_blueprint_json"
    imported_notes = cast("list[JsonObject]", imported_metadata["notes"])
    imported_notes_json = json.dumps(imported_notes, sort_keys=True)
    break_handler_id = str(break_handler["id"])
    assert f"NOTE-MOD-{break_handler_id}" in imported_notes_json
    assert f"NOTE-CONN-3-{break_handler_id}" in imported_notes_json


def _assert_lead_alert_make_projection(payload: JsonObject) -> None:
    assert payload["artifact_format"] == "make_blueprint_json"
    assert payload["artifact_kind"] == "make_blueprint_projection"
    artifact = cast("JsonObject", payload["artifact_json"])
    projected_scenario = cast("JsonObject", artifact["scenario"])
    projected_metadata = cast("JsonObject", projected_scenario["metadata"])
    projected_settings = cast("JsonObject", projected_metadata["scenario"])
    assert projected_settings["sequential"] is True
    assert projected_settings["dlq"] is True
    assert projected_settings["confidential"] is False
    native_notes = cast("list[JsonObject]", projected_metadata["notes"])
    _assert_projected_make_native_notes(native_notes)
    projected_designer = cast("JsonObject", projected_metadata["designer"])
    designer_notes = cast("list[JsonObject]", projected_designer["notes"])
    assert designer_notes == native_notes
    projected_flow = cast("list[JsonObject]", projected_scenario["flow"])
    projected_datastore = projected_flow[2]
    projected_break = cast("list[JsonObject]", projected_datastore["onerror"])[
        0
    ]
    assert projected_break["module"] == "builtin:Break"
    assert projected_break["version"] == 1
    assert "flow" not in projected_break


def _assert_datastore_batch_plan(
    plan: JsonObject,
    *,
    dry_run_status: str,
    record_count: int,
) -> None:
    assert plan["contract_status"] == "schema_checked_batch_upsert_ready"
    assert plan["dry_run_status"] == dry_run_status
    assert plan["required_live_capability"] == "datastore_record_upsert_batch"
    assert plan["required_live_capability_status"] == "available"
    assert plan["record_count"] == record_count
    assert plan["max_batch_records"] == 100
    assert "schema_validation_status" in plan
    assert "unknown_record_field_count" in plan
    budget = cast("JsonObject", plan["operation_budget"])
    assert budget["live_operation_budget"] == record_count
    assert budget["apply_requires_operator_approval"] is False
    assert budget["requires_session_scope"] is True
    rollback = cast("JsonObject", plan["rollback_policy"])
    assert rollback["overwrite_customer_data_without_approval"] is False
    assert rollback["delete_created_records_only_with_session_scope"] is True


def _write_staged_draft(
    repo_root: Path,
    *,
    file_name: str,
    payload: JsonObject,
) -> str:
    path = repo_root / "temp" / "pancakes" / "project-intake" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return f"temp/pancakes/project-intake/{file_name}"


def _create_project_from_summary(
    repo_root: Path,
    *,
    project_id: str,
    summary: str,
    name: str | None = None,
) -> McpToolCallReport:
    stage_arguments: dict[str, object] = {
        "project_id": project_id,
        "scenario_summary": summary,
        "dry_run": False,
    }
    if name is not None:
        stage_arguments["name"] = name
    staged = execute_mcp_tool(
        tool_name="project.draft.stage",
        arguments=stage_arguments,
        repo_root=repo_root,
    )
    assert staged.ok, staged
    create_arguments: dict[str, object] = {
        "project_id": project_id,
        "staged_draft_path": staged.payload["staged_draft_path"],
        "staged_draft_sha256": staged.payload["staged_draft_sha256"],
        "dry_run": False,
    }
    return execute_mcp_tool(
        tool_name="project.create",
        arguments=create_arguments,
        repo_root=repo_root,
    )


def test_agent_ide_surface_exports_canonical_tools_with_catalog_work() -> None:
    """The MCP exposes canonical IDE tools including local catalog work."""
    tool_names = tuple(tool.name for tool in mcp_tool_registry())

    for tool_name in (
        "catalog.index ",
        "catalog.search ",
        "catalog.inspect ",
        "catalog.graph.search ",
        "catalog.semantic.preview",
        ("catalog.work.next"),
        ("catalog.work.save"),
        "project.draft.stage ",
        "project.draft.import ",
        "project.create ",
        "project.edit ",
        "project.verify ",
        "project.capabilities.inspect ",
        "project.make ",
        "project.package.inspect ",
        "project.next ",
        "documentation.generate ",
        "documentation.validate ",
        "onboarding.validate",
    ):
        assert tool_name in tool_names

    descriptions = {
        tool.name: tool.description.casefold() for tool in mcp_tool_registry()
    }
    assert "canonical placeholder" in descriptions["catalog.index"]
    assert "sqlite catalog graph" in descriptions["catalog.graph.search"]
    assert "preview proposed" in descriptions["catalog.semantic.preview"]
    assert "lease" in descriptions[("catalog.work.next")]
    assert "save" in descriptions[("catalog.work.save")]
    assert "workflow summary" in descriptions["project.draft.stage"]
    assert "local json artifact" in descriptions["project.draft.import"]
    assert "raw json" in descriptions["project.edit"]
    assert "offline local handoff" in descriptions["project.make"]
    assert "package" in descriptions["project.make"]
    assert "section" in descriptions["project.package.inspect"]
    assert "large package payload" in descriptions["project.package.inspect"]
    make_schema = {tool.name: tool for tool in mcp_tool_registry()}[
        "project.make"
    ].input_schema()
    make_properties = cast("dict[str, JsonObject]", make_schema["properties"])
    assert "profile" in make_properties
    assert "live_preflight" in str(make_properties["profile"])
    assert "package" in str(make_properties["action"])


def test_project_health_stress_fixture_counts(tmp_path: Path) -> None:
    """project.health summarizes the large local graph without external.

    commerce.

    state.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.health",
        arguments={"project_id": "stress"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["module_count"] == 302
    assert result.payload["link_count"] == 301
    assert (
        result.payload["link_count_semantics"]
        == "deduped_semantic_execution_links"
    )
    assert result.payload["raw_route_and_flow_edge_count"] == 331
    assert result.payload["filter_count"] == 30
    assert result.payload["error_handler_count"] == 0
    assert result.payload["provider_api_call"] is False
    assert result.payload["live_make_called"] is False
    assert result.payload["credential_value_transfer"] is False


def test_project_view_compact_is_grouped_bounded_and_expandable(
    tmp_path: Path,
) -> None:
    """project.view compact does not return hundreds of nodes or raw JSON.

    walls.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "stress ",
            "surface": "overview ",
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["response_schema_version"] == 2
    assert "graph_view" not in payload
    assert "nodes" not in payload
    assert "connections" not in payload
    assert payload["raw_graph_available"] is True
    groups = cast("tuple[JsonObject, ...]", payload["module_groups"])
    datastore = next(group for group in groups if group["group"] == "datastore")
    slack = next(group for group in groups if group["group"] == "slack")
    assert datastore["count"] == 270
    assert datastore["hidden_node_count"] == 267
    assert slack["count"] == 30
    assert slack["hidden_node_count"] == 27
    assert payload["next_queries"]
    assert all(
        isinstance(row, dict)
        for row in cast("tuple[object, ...]", payload["next_queries"])
    )
    assert_compact_response_bounded(payload)
    assert_no_raw_walls(payload)
    assert_hidden_counts_when_truncated(payload)
    assert_next_query_when_raw_omitted(payload)
    assert_no_secret_or_credential_values(payload)
    assert_safety_flags_false(payload)


def test_project_view_links_and_filters_support_focus(tmp_path: Path) -> None:
    """IDE surfaces can focus links by node and filters by route without raw.

    queries.
    """
    _write_stress_project(tmp_path)

    links = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "stress ",
            "surface": "links ",
            "node_id": "2 ",
            "output_mode": "compact",
            "limit": 5,
        },
        repo_root=tmp_path,
    )
    filters = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "stress ",
            "surface": "filters",
            "route_index": 0,
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )
    wrapper_links = execute_mcp_tool(
        tool_name="project.links.view",
        arguments={"project_id": "stress", "module_id": 2, "limit": 5},
        repo_root=tmp_path,
    )
    wrapper_filters = execute_mcp_tool(
        tool_name="project.filters.view",
        arguments={"project_id": "stress", "route_id": "0"},
        repo_root=tmp_path,
    )
    invalid_filter = execute_mcp_tool(
        tool_name="project.filters.view",
        arguments={"project_id": "stress", "route_id": "not-a-route"},
        repo_root=tmp_path,
    )

    assert links.ok, links
    assert filters.ok, filters
    assert wrapper_links.ok, wrapper_links
    assert wrapper_filters.ok, wrapper_filters
    assert invalid_filter.ok, invalid_filter
    link_rows = cast("tuple[JsonObject, ...]", links.payload["links"])
    assert len(link_rows) == 5
    assert all(
        "2" in {row["source_node_id"], row["target_node_id"]}
        for row in link_rows
    )
    assert cast("int", links.payload["hidden_link_count"]) > 0
    wrapper_link_rows = cast(
        "tuple[JsonObject, ...]", wrapper_links.payload["links"]
    )
    assert len(wrapper_link_rows) == 5
    assert wrapper_links.payload["canonical_tool"] == "project.view"
    assert filters.payload["filter_count"] == 1
    assert wrapper_filters.payload["filter_count"] == 1
    assert invalid_filter.payload["status"] == "invalid_filter"


def test_project_make_verify_next_and_edit_are_local_semantic_flows(
    tmp_path: Path,
) -> None:
    """The high-level IDE tools cover preview, verification, next-step, and.

    semantic edit.
    """
    _write_stress_project(tmp_path)

    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={"project_id": "stress", "action": "preview"},
        repo_root=tmp_path,
    )
    verified = execute_mcp_tool(
        tool_name="project.verify",
        arguments={"project_id": "stress", "profile": "import_test"},
        repo_root=tmp_path,
    )
    next_action = execute_mcp_tool(
        tool_name="project.next",
        arguments={
            "project_id": "stress ",
            "mode": "one ",
            "profile": "handoff_test",
        },
        repo_root=tmp_path,
    )
    import_next = execute_mcp_tool(
        tool_name="project.next",
        arguments={
            "project_id": "stress ",
            "mode": "one ",
            "profile": "import_test",
        },
        repo_root=tmp_path,
    )
    live_next = execute_mcp_tool(
        tool_name="project.next",
        arguments={
            "project_id": "stress ",
            "mode": "one ",
            "profile": "live_preflight",
        },
        repo_root=tmp_path,
    )
    edit = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "stress ",
            "surface": "modules ",
            "operation": "add",
            "target": {"parent_node_id": "2", "route_index": 0},
            "payload_json": json.dumps(
                {"id": 5000, "module": "slack:ActionCreateMessage"}
            ),
        },
        repo_root=tmp_path,
    )

    assert preview.ok, preview
    assert verified.ok, verified
    assert next_action.ok, next_action
    assert import_next.ok, import_next
    assert live_next.ok, live_next
    assert edit.ok, edit
    assert preview.payload["provider_api_call"] is False
    next_action_payload = cast("JsonObject", next_action.payload["next_action"])
    assert "preview" not in preview.payload
    assert preview.payload["response_schema_version"] == 3
    assert_no_duplicate_summary_payload(preview.payload)
    assert preview.payload["artifact_format"] == "make_blueprint_json"
    assert "artifact_would_include_raw_json" not in preview.payload
    assert preview.payload["response_includes_raw_json"] is False
    assert preview.payload["zero_trace_status"] == "passed"
    assert preview.payload["zero_trace_surface"] == "rendered_preview_artifact"
    assert cast("int", preview.payload["runtime_setup_occurrence_count"]) > 0
    translation_summary = cast(
        "JsonObject", preview.payload["module_translation_summary"]
    )
    binding_summary = cast(
        "JsonObject", preview.payload["connection_binding_summary"]
    )
    resource_summary = cast(
        "JsonObject", preview.payload["resource_binding_summary"]
    )
    assert translation_summary["groups"]
    assert binding_summary["groups"]
    assert resource_summary["groups"]
    assert preview.payload["pass_through_unknown_module_count"] == 0
    assert verified.payload["make_import_validation_status"] == "ready"
    assert cast("int", verified.payload["runtime_setup_occurrence_count"]) > 0
    assert "runtime_setup_count" not in verified.payload
    assert next_action_payload["tool"] == "project.view"
    assert next_action_payload["surface"] == "client_handoff"
    assert next_action_payload["owning_layer"] == "pancakes_mcp"
    assert next_action_payload["requires_operator_approval"] is False
    import_next_action = cast("JsonObject", import_next.payload["next_action"])
    assert import_next_action["surface"] == "runtime_setup"
    assert import_next_action["tool"] == "project.view"
    assert import_next_action["owning_layer"] == "pancakes_mcp"
    live_next_action = cast("JsonObject", live_next.payload["next_action"])
    assert live_next_action["surface"] == "live_preflight"
    assert live_next_action["tool"] == "project.make"
    assert live_next_action["owning_layer"] == "pancakes_mcp"
    assert live_next_action["requires_operator_approval"] is False
    assert (
        cast("JsonObject", live_next_action["arguments"])["output_mode"]
        == "full"
    )
    assert edit.payload["semantic_tool"] == "project.edit"
    assert edit.payload["wrapped_tool"] == "project.modules.add"
    assert edit.payload["status"] == "dry_run"


def test_project_verify_micro_compact_and_capability_inspect_are_bounded(
    tmp_path: Path,
) -> None:
    """project.verify keeps compact output small and links to capability detail.

    inspection.
    """
    _write_stress_project(tmp_path)

    micro = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "output_mode": "micro",
        },
        repo_root=tmp_path,
    )
    compact = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )
    full = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    capability_inspect = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    missing_capability = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "live_apply_package ",
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )
    available_capability = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "scenario_import ",
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert micro.ok, micro
    assert compact.ok, compact
    assert full.ok, full
    assert capability_inspect.ok, capability_inspect
    assert missing_capability.ok, missing_capability
    assert available_capability.ok, available_capability

    micro_payload = micro.payload
    compact_payload = compact.payload
    assert len(json.dumps(micro_payload, sort_keys=True)) < 6_000
    assert len(json.dumps(compact_payload, sort_keys=True)) < 14_000
    for payload in (micro_payload, compact_payload):
        assert "make_mcp_capabilities" not in payload
        assert "make_mcp_capability_details" not in payload
        assert "local_linter_findings" not in payload
        assert "runtime_setup_groups" not in payload
        assert "summary_counts" in payload
        assert "make_import_validation_status" in payload
        assert "top_blockers" in payload or "findings" in payload
        assert any(
            row["tool"] == "project.capabilities.inspect"
            for row in cast("tuple[JsonObject, ...]", payload["next_queries"])
        )

    assert "make_mcp_capabilities" in full.payload
    assert "make_mcp_capability_details" in full.payload
    assert "make_mcp_capabilities" in capability_inspect.payload
    assert "make_mcp_capability_details" in capability_inspect.payload
    assert missing_capability.payload["capability"] == "live_apply_package"
    assert missing_capability.payload["capability_status"] == "available"
    assert missing_capability.payload["requested_capability_available"] is True
    assert missing_capability.payload["missing_capabilities"] == ()
    assert "make_mcp_capabilities" not in missing_capability.payload
    live_apply_detail = cast(
        "JsonObject", missing_capability.payload["capability_detail"]
    )
    live_apply_contract = cast(
        "JsonObject", live_apply_detail["capability_contract"]
    )
    assert live_apply_contract["contract_status"] == "observed_live_apply_ready"
    assert (
        live_apply_contract["live_evidence"]
        == "make_mcp_live_apply_package_roundtrip_shapes"
    )
    assert (
        live_apply_contract["target_scenario_policy"]
        == "inactive_scratch_scenario_only"
    )
    assert live_apply_contract["dry_run_required_before_live_write"] is True
    assert (
        live_apply_contract["operator_approval_required_after_dry_run"] is False
    )
    assert live_apply_contract["runtime_api_token_required_for_apply"] is True
    assert live_apply_contract["pancakes_executes_live_operations"] is True
    assert available_capability.payload["capability"] == "scenario_import"
    assert available_capability.payload["capability_status"] == "available"
    assert (
        available_capability.payload["requested_capability_available"] is True
    )
    assert available_capability.payload["missing_capabilities"] == ()
    assert "make_mcp_capabilities" not in available_capability.payload
    assert_no_orphan_capabilities(capability_inspect.payload)
    assert_compact_response_bounded(compact_payload)


def test_project_capabilities_inspect_reports_binding_bridge_contracts(
    tmp_path: Path,
) -> None:
    """Connection and webhook binding expose typed contracts without secrets."""
    _write_stress_project(tmp_path)

    connection_bind = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "connection_bind_to_module",
        },
        repo_root=tmp_path,
    )
    webhook_bind = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "webhook_bind_to_module",
        },
        repo_root=tmp_path,
    )

    assert connection_bind.ok, connection_bind
    assert webhook_bind.ok, webhook_bind
    assert connection_bind.payload["capability_status"] == "available"
    assert webhook_bind.payload["capability_status"] == "available"
    _assert_binding_bridge_detail(
        cast("JsonObject", connection_bind.payload["capability_detail"]),
        status="available",
        resource_kind="connection",
        contract_status="observed_live_bind_ready",
    )
    _assert_binding_bridge_detail(
        cast("JsonObject", webhook_bind.payload["capability_detail"]),
        status="available",
        resource_kind="webhook",
        contract_status="observed_live_bind_ready",
    )


def test_project_capabilities_inspect_reports_datastore_batch_contract(
    tmp_path: Path,
) -> None:
    """The batch upsert bridge exposes a bounded schema-checked contract."""
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "datastore_record_upsert_batch",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    detail = cast("JsonObject", result.payload["capability_detail"])
    contract = cast("JsonObject", detail["orchestrator_contract"])
    assert result.payload["capability_status"] == "available"
    assert contract["contract_status"] == "schema_checked_batch_upsert_ready"
    assert contract["live_evidence"] == (
        "make_api_existing_store_record_probe_shapes ",
        "make_mcp_datastore_lifecycle_shapes ",
        "make_mcp_datastore_strict_schema_validation_shapes",
    )
    assert contract["dry_run_first"] is True
    assert contract["requires_operator_approval"] is False
    assert contract["requires_session_scope"] is True
    assert contract["pancakes_executes_live_operations"] is True
    assert contract["max_batch_records"] == 100
    lifecycle = cast("JsonObject", contract["disposable_lifecycle_contract"])
    assert (
        lifecycle["cleanup_invariant"]
        == "data_stores_count_0_and_data_structures_count_0"
    )
    typed_tools = cast("tuple[str, ...]", lifecycle["typed_tools"])
    assert "data_structures_create" in typed_tools
    assert "data_stores_delete" in typed_tools
    assert (
        lifecycle["record_delete_confirmation"] == "Records have been deleted."
    )
    assert "no_overwrite_customer_data_without_session_scope" in cast(
        "tuple[str, ...]",
        contract["session_boundaries"],
    )
    assert (
        detail["bridge_evidence_status"] == "schema_checked_batch_upsert_ready"
    )
    assert "missing_capability_error" not in detail


def test_project_capabilities_inspect_reports_datastore_strict_schema_contract(
    tmp_path: Path,
) -> None:
    """Data Store strict-schema validation is exposed before batch upsert."""
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "datastore_strict_schema_validation",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["capability_status"] == "available"
    detail = cast("JsonObject", result.payload["capability_detail"])
    assert detail["mapped_live_tool"] == "data_store_records_create"
    assert (
        detail["bridge_evidence_status"]
        == "observed_strict_schema_validation_ready"
    )
    contract = cast("JsonObject", detail["strict_schema_contract"])
    assert (
        contract["contract_status"] == "observed_strict_schema_validation_ready"
    )
    assert (
        contract["live_evidence"]
        == "make_mcp_datastore_strict_schema_validation_shapes"
    )
    assert "missing_required_request_id" in cast(
        "tuple[str, ...]", contract["observed_rejections"]
    )
    assert "invalid_number_amount" in cast(
        "tuple[str, ...]", contract["observed_rejections"]
    )
    assert contract["credential_value_transfer"] is False
    assert contract["secret_output"] is False


def test_project_capabilities_inspect_reports_module_configuration_contract(
    tmp_path: Path,
) -> None:
    """Typed module validation exposes required-field evidence without live.

    writes.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "module_configuration_validation",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["capability_status"] == "available"
    detail = cast("JsonObject", result.payload["capability_detail"])
    assert detail["mapped_live_tool"] == "validate_module_configuration"
    assert (
        detail["bridge_evidence_status"]
        == "observed_module_configuration_validation_ready"
    )
    contract = cast("JsonObject", detail["module_configuration_contract"])
    assert (
        contract["contract_status"]
        == "observed_module_configuration_validation_ready"
    )
    assert (
        contract["live_evidence"]
        == "make_mcp_module_configuration_validation_shapes"
    )
    assert contract["mapped_live_tool"] == "validate_module_configuration"
    assert contract["writes_performed"] is False
    assert contract["activation_allowed"] is False
    assert contract["run_once_allowed"] is False
    observed = cast("JsonObject", contract["observed_required_field"])
    assert observed["moduleName"] == "ParseJSON"
    assert observed["mapper_path"] == "json"
    assert observed["error_class"] == "field_is_mandatory"


def test_project_capabilities_inspect_reports_run_once_contract(
    tmp_path: Path,
) -> None:
    """Run-once live validation is explicit, scratch-scoped, and.

    cleanup-bound.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "scenario_run_once",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["capability_status"] == "available"
    detail = cast("JsonObject", result.payload["capability_detail"])
    assert detail["mapped_live_tool"] == "scenarios_run"
    assert (
        detail["bridge_evidence_status"] == "observed_run_once_execution_ready"
    )
    contract = cast("JsonObject", detail["run_once_contract"])
    assert contract["contract_status"] == "observed_run_once_execution_ready"
    assert contract["live_evidence"] == "make_mcp_scenario_run_once_shapes"
    assert contract["requires_operator_approval"] is True
    assert contract["activation_cleanup_required"] is True
    assert contract["scratch_scenario_only"] is True
    assert contract["live_provider_call_required"] is True
    assert contract["credential_value_transfer"] is False
    assert contract["secret_output"] is False


def test_project_capabilities_inspect_reports_webhook_configuration_contract(
    tmp_path: Path,
) -> None:
    """Webhook creation exposes typed config validation before live create."""
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.capabilities.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "capability": "webhook_configuration_validation",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["capability_status"] == "available"
    detail = cast("JsonObject", result.payload["capability_detail"])
    assert (
        detail["mapped_live_tool"]
        == "hook_config_get + validate_hook_configuration"
    )
    assert (
        detail["bridge_evidence_status"]
        == "observed_webhook_configuration_validation_ready"
    )
    contract = cast("JsonObject", detail["webhook_configuration_contract"])
    assert (
        contract["contract_status"]
        == "observed_webhook_configuration_validation_ready"
    )
    assert (
        contract["live_evidence"]
        == "make_mcp_hook_configuration_validation_shapes"
    )
    assert contract["type_name"] == "gateway-webhook"
    assert contract["required_default_fields"] == (
        "headers ",
        "method ",
        "stringify",
    )
    assert contract["writes_performed"] is False
    assert contract["activation_allowed"] is False
    assert contract["run_once_allowed"] is False


def test_project_verify_handoff_blocks_notes_without_import_block(
    tmp_path: Path,
) -> None:
    """Missing handoff notes block handoff but not local Make import.

    readiness.
    """
    _write_stress_project(tmp_path)

    import_test = execute_mcp_tool(
        tool_name="project.verify",
        arguments={"project_id": "stress", "profile": "import_test"},
        repo_root=tmp_path,
    )
    handoff = execute_mcp_tool(
        tool_name="project.verify",
        arguments={"project_id": "stress", "profile": "handoff_test"},
        repo_root=tmp_path,
    )
    notes = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "stress", "surface": "notes"},
        repo_root=tmp_path,
    )

    assert import_test.ok, import_test
    assert handoff.ok, handoff
    assert notes.ok, notes
    assert import_test.payload["make_import_validation_status"] == "ready"
    assert (
        import_test.payload["client_handoff_validation_status"]
        == "not_evaluated_for_profile"
    )
    import_handoff_risk = cast(
        "JsonObject", import_test.payload["handoff_risk_summary"]
    )
    assert import_handoff_risk["risk_level"] == "not_evaluated_for_profile"
    assert import_handoff_risk["finding_surface"] == "client_handoff"
    assert import_handoff_risk["blocking_error_count"] == 0
    assert handoff.payload["status"] == "blocked"
    assert handoff.payload["make_import_validation_status"] == "ready"
    assert handoff.payload["blocked_surface"] == "client_handoff"
    notes_summary = cast("JsonObject", notes.payload["scenario_notes_summary"])
    assert notes_summary["missing_module_note_count"] == 302
    assert notes_summary["missing_connection_note_count"] == 301
    assert "notes" not in notes.payload
    grouped = cast(
        "tuple[JsonObject, ...]", notes_summary["grouped_missing_notes"]
    )
    for group in grouped:
        examples = group.get("example_connections")
        if isinstance(examples, tuple | list):
            raw_examples = cast("list[object] | tuple[object, ...]", examples)
            example_rows = [str(example) for example in raw_examples]
            assert len(example_rows) == len(set(example_rows))
    assert notes.payload["batch_note_plan"]


def test_zero_trace_failure_blocks_handoff_preview_and_package_readiness(
    tmp_path: Path,
) -> None:
    """Zero-trace failure names its surface and blocks customer-facing.

    readiness.
    """
    created = _create_project_from_summary(
        tmp_path,
        project_id="zero-trace-private-marker",
        summary="Capture support requests, store them, and alert Slack.",
    )
    assert created.ok, created
    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-zero-trace-private-marker"
        / "scenario.json"
    )
    scenario = cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )
    flow = cast("list[JsonObject]", scenario["flow"])
    flow[0]["mapper"] = {"private_debug_marker": "local_project_scenario"}
    _ = scenario_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    zero_trace = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "zero-trace-private-marker ",
            "profile": "zero_trace",
        },
        repo_root=tmp_path,
    )
    handoff = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "zero-trace-private-marker ",
            "profile": "handoff_test",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "zero-trace-private-marker ",
            "action": "preview ",
            "profile": "client_handoff",
        },
        repo_root=tmp_path,
    )
    package = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "zero-trace-private-marker ",
            "action": "package ",
            "profile": "live_preflight",
        },
        repo_root=tmp_path,
    )

    assert zero_trace.ok, zero_trace
    assert handoff.ok, handoff
    assert preview.ok, preview
    assert package.ok, package
    assert zero_trace.payload["status"] == "blocked"
    assert zero_trace.payload["zero_trace_status"] == "failed"
    assert zero_trace.payload["blocked_surface"] == "zero_trace"
    assert "zero_trace" in cast(
        "list[str]", zero_trace.payload["blocked_surfaces"]
    )
    assert handoff.payload["status"] == "blocked"
    assert handoff.payload["client_handoff_validation_status"] == "blocked"
    assert handoff.payload["client_handoff_status"] == "blocked"
    assert "zero_trace" in cast(
        "list[str]", handoff.payload["blocked_surfaces"]
    )
    assert preview.payload["status"] == "blocked"
    assert preview.payload["client_handoff_status"] == "blocked"
    assert preview.payload["artifact_render_status"] == "blocked_by_zero_trace"
    assert preview.payload["zero_trace_status"] == "failed"
    assert package.payload["status"] == "package_blocked"
    assert package.payload["package_status"] == "blocked"
    assert package.payload["customer_delivery_package_status"] == "blocked"
    assert package.payload["blueprint_readiness_status"] == "blocked"
    blueprint = cast("JsonObject", package.payload["blueprint_artifact"])
    assert blueprint["status"] == "blocked"


def test_runtime_setup_uses_true_owner_paths_without_router_contamination(
    tmp_path: Path,
) -> None:
    """Runtime setup counts use concrete owner fields, not router child-flow.

    inheritance.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "stress ",
            "surface": "runtime ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    runtime = cast("JsonObject", result.payload["runtime"])
    assert runtime["runtime_setup_occurrence_count"] == 331
    assert runtime["runtime_setup_affected_node_count"] == 301
    assert runtime["runtime_setup_distinct_binding_count"] == 4
    groups = cast("tuple[JsonObject, ...]", runtime["groups"])
    for group in groups:
        examples = cast("list[str]", group["example_node_ids"])
        assert len(examples) == len(set(examples))
    datastore = next(
        group
        for group in groups
        if group["source"] == "{{runtime.datastore.stress_events}}"
    )
    slack_connection = next(
        group
        for group in groups
        if group["source"] == "{{runtime.connection.slack_ops}}"
    )
    slack_channel = next(
        group
        for group in groups
        if group["source"] == "{{runtime.slack.channel.ops_alerts}}"
    )
    webhook = next(
        group
        for group in groups
        if group["source"] == "{{runtime.webhook.stress_intake_hook}}"
    )
    assert cast("list[str]", datastore["example_field_paths"])[0].startswith(
        "flow[2]."
    )
    assert cast("list[str]", slack_connection["example_field_paths"])[
        0
    ].startswith("flow[1].routes[0].flow[0].")
    assert cast("list[str]", slack_channel["example_field_paths"])[
        0
    ].startswith("flow[1].routes[0].flow[0].")
    assert cast("list[str]", webhook["example_field_paths"])[0].startswith(
        "flow[0]."
    )
    assert "2" not in cast("list[str]", datastore["example_node_ids"])
    assert "2" not in cast("list[str]", slack_connection["example_node_ids"])
    assert "2" not in cast("list[str]", slack_channel["example_node_ids"])


def test_project_make_artifact_projection_classifies_connections_and_resources(
    tmp_path: Path,
) -> None:
    """Make projection fixes both summaries and the underlying projected.

    artifact.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "preview ",
            "output_mode": "debug",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    connection_summary = cast(
        "JsonObject", payload["connection_binding_summary"]
    )
    resource_summary = cast("JsonObject", payload["resource_binding_summary"])
    translation_summary = cast(
        "JsonObject", payload["module_translation_summary"]
    )
    assert connection_summary["binding_count"] == 30
    assert resource_summary["binding_count"] == 301
    assert all(
        group["projection_kind"] == "make_connection_placeholder"
        for group in cast(
            "tuple[JsonObject, ...]", connection_summary["groups"]
        )
    )
    assert all(
        group["projection"] != "__IMTCONN__"
        for group in cast("tuple[JsonObject, ...]", resource_summary["groups"])
    )
    gateway_group = next(
        group
        for group in cast(
            "tuple[JsonObject, ...]", translation_summary["groups"]
        )
        if group["from"] == "gateway:CustomWebHook"
    )
    assert gateway_group["change"] == "trigger_projected"
    assert gateway_group["version"] == 1
    assert payload["pass_through_unknown_module_count"] == 0
    assert payload["zero_trace_surface"] == "rendered_preview_artifact"
    artifact = cast("JsonObject", payload["artifact_json"])
    scenario = cast("JsonObject", artifact["scenario"])
    flow = cast("list[JsonObject]", scenario["flow"])
    gateway = flow[0]
    router = flow[1]
    datastore = flow[2]
    first_route = cast("list[JsonObject]", router["routes"])[0]
    second_route = cast("list[JsonObject]", router["routes"])[1]
    slack = cast("list[JsonObject]", first_route["flow"])[0]
    assert gateway["version"] == 1
    assert gateway["mapper"] == {}
    assert router["version"] == 1
    assert "filter" not in first_route
    assert slack["filter"] == {
        "conditions": [[{"a": "{{2.route_0.accepted}}", "o": "exist"}]],
        "name": "Route 0",
    }
    assert "filter" not in second_route
    assert cast("list[JsonObject]", second_route["flow"])[0]["filter"] == {
        "conditions": [[{"a": "{{2.route_1.accepted}}", "o": "exist"}]],
        "name": "Route 1",
    }
    assert datastore["version"] == 2
    assert slack["module"] == "slack:CreateMessage"
    assert slack["version"] == 4
    assert (
        cast("JsonObject", slack["parameters"])["__IMTCONN__"] == "__IMTCONN__"
    )
    assert cast("JsonObject", slack["mapper"])["channelWType"] == "manualy"
    assert (
        cast("JsonObject", slack["mapper"])["channel"]
        == "{{runtime.slack.channel.ops_alerts}}"
    )
    assert (
        cast("JsonObject", datastore["parameters"])["datastore"]
        == "{{runtime.datastore.stress_events}}"
    )
    assert set(
        cast("JsonObject", cast("JsonObject", datastore["mapper"])["data"])
    ) == {
        "company ",
        "email ",
        "module_index ",
        "record_kind ",
        "request_id ",
        "route_index ",
        "score",
    }
    assert cast("JsonObject", datastore["mapper"])["key"] == "{{1.request_id}}"
    assert cast("JsonObject", datastore["mapper"])["overwrite"] is False
    assert (
        cast("JsonObject", gateway["parameters"])["hook"]
        == "{{runtime.webhook.stress_intake_hook}}"
    )


def test_project_make_lowers_filtered_router_routes_to_first_make_module(
    tmp_path: Path,
) -> None:
    """Route filters are lowered to route modules so Make's import schema.

    accepts.

    them.
    """
    project_path = tmp_path / "projects" / "filtered" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Filtered",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": "{{runtime.webhook.filtered_intake}}"},
            },
            {
                "id": 2,
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "name": "Needs team notification ",
                            "condition": "{{1.priority}} = urgent",
                        },
                        "flow": [
                            {
                                "id": 3,
                                "module": "slack:ActionCreateMessage",
                                "parameters": {
                                    "account": (
                                        "{{runtime.connection.slack_ops}}"
                                    ),
                                    "channel": (
                                        "{{runtime.slack.channel.ops_alerts}}"
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "filter": {
                            "name": "Send customer email acknowledgement ",
                            "condition": "{{1.email}} exists",
                        },
                        "flow": [
                            {
                                "id": 4,
                                "module": "google-email:ActionSendEmail",
                                "parameters": {
                                    "account": (
                                        "{{runtime.connection.google_email_ops}}"
                                    ),
                                },
                                "mapper": {
                                    "to": "{{1.email}}",
                                    "subject": (
                                        "Request {{1.request_id}} received"
                                    ),
                                    "html": (
                                        "<p>Thanks for contacting us. We "
                                        "received request "
                                        "{{1.request_id}} and will follow "
                                        "up.</p>"
                                    ),
                                },
                            }
                        ],
                    },
                ],
            },
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "filtered ",
            "action": "preview ",
            "output_mode": "debug",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    artifact = cast("JsonObject", result.payload["artifact_json"])
    projected = cast("JsonObject", artifact["scenario"])
    root_metadata = cast("JsonObject", projected["metadata"])
    assert root_metadata["designer"] == {"orphans": []}
    flow = cast("list[JsonObject]", projected["flow"])
    router = flow[1]
    first_route = cast("list[JsonObject]", router["routes"])[0]
    second_route = cast("list[JsonObject]", router["routes"])[1]
    slack = cast("list[JsonObject]", first_route["flow"])[0]
    google_email = cast("list[JsonObject]", second_route["flow"])[0]
    positions = {
        "gateway": _designer_position(flow[0]),
        "router": _designer_position(router),
        "slack": _designer_position(slack),
        "google_email": _designer_position(google_email),
    }
    assert len(set(positions.values())) == len(positions)
    assert (
        positions["gateway"][0] < positions["router"][0] < positions["slack"][0]
    )
    assert positions["slack"][1] != positions["google_email"][1]
    assert "filter" not in first_route
    assert slack["filter"] == {
        "conditions": [
            [{"a": "{{1.priority}}", "o": "text:equal", "b": "urgent"}]
        ],
        "name": "Needs team notification",
    }
    assert "filter" not in second_route
    assert google_email["filter"] == {
        "conditions": [[{"a": "{{1.email}}", "o": "exist"}]],
        "name": "Send customer email acknowledgement",
    }
    assert google_email["module"] == "google-email:sendAnEmail"
    assert google_email["version"] == 4
    assert (
        cast("JsonObject", google_email["parameters"])["__IMTCONN__"]
        == "__IMTCONN__"
    )
    google_email_mapper = cast("JsonObject", google_email["mapper"])
    assert google_email_mapper["bodyType"] == "rawHtml"
    assert google_email_mapper["content"] == (
        "<p>Thanks for contacting us. We received request {{1.request_id}} and "
        "will follow up.</p>"
    )
    assert "html" not in google_email_mapper


def _designer_position(node: JsonObject) -> tuple[int, int]:
    metadata = cast("JsonObject", node["metadata"])
    designer = cast("JsonObject", metadata["designer"])
    x = designer["x"]
    y = designer["y"]
    assert isinstance(x, int)
    assert isinstance(y, int)
    return x, y


def test_project_make_client_handoff_blocks_only_handoff_surface(
    tmp_path: Path,
) -> None:
    """Client handoff can block while import-safe local artifact preview.

    remains.

    available.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "preview ",
            "profile": "client_handoff",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "blocked"
    assert payload["blocked_surface"] == "client_handoff"
    assert payload["import_status"] == "ready"
    assert payload["artifact_preview_status"] == "preview_ready"
    assert payload["artifact_render_status"] == "rendered"
    assert payload["zero_trace_status"] == "passed"
    assert payload["zero_trace_surface"] == "rendered_preview_artifact"


def test_project_make_package_prepares_local_make_mcp_handoff(
    tmp_path: Path,
) -> None:
    """project.make package emits a local handoff package without live Make.

    operations.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "package ",
            "profile": "live_preflight",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "package_ready"
    assert payload["status_surface"] == "local_package"
    assert "local Make import package is ready" in str(payload["status_reason"])
    assert "declared live validation capabilities" in str(
        payload["status_reason"]
    )
    assert payload["package_kind"] == "make_import_package"
    assert payload["package_profile"] == "live_preflight"
    assert payload["artifact_format"] == "make_blueprint_json"
    assert payload["customer_delivery_package_status"] == "ready"
    assert payload["blueprint_artifact_json_omitted_from_response"] is True
    assert payload["blueprint_artifact_json_would_be_included"] is True
    assert "blueprint_artifact_json_available_in_written_package" not in payload
    assert "blueprint_artifact_json" not in payload
    assert payload["minimal_import_package_status"] == "ready"
    assert payload["live_preflight_status"] == "ready"
    assert payload["full_live_validation_status"] == "ready"
    assert (
        payload["live_canary_status"]
        == "destructive_webhook_datastore_canary_passed_and_cleaned"
    )
    assert payload["live_resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    assert "absence in Make UI means cleanup passed" in str(
        payload["live_canary_cleanup_semantics"]
    )
    assert payload["zero_trace"] is True
    assert payload["zero_trace_status"] == "passed"
    assert payload["zero_trace_surface"] == "package_blueprint_artifact"
    assert payload["leak_count"] == 0
    assert payload["package_contains_secrets"] is False
    assert payload["package_contains_fake_provider_ids"] is False
    assert payload["customer_report_included"] is False
    assert payload["internal_report_status"] == "not_included"
    customer_package = cast("JsonObject", payload["customer_delivery_package"])
    assert (
        customer_package["package_kind"]
        == "customer_blueprint_delivery_package"
    )
    assert customer_package["delivery_boundary"] == "blueprint_import_only"
    assert re.fullmatch(
        r"stress_\d{4}\.\d{2}\.\d{2}\.blueprint\.json",
        str(customer_package["customer_artifact_name"]),
    )
    assert customer_package["customer_receives_internal_report"] is False
    assert customer_package["customer_receives_ast"] is False
    assert customer_package["customer_receives_graph"] is False
    assert customer_package["customer_receives_linter_logic"] is False
    assert customer_package["customer_receives_internal_prompts"] is False
    assert customer_package["customer_receives_scoring_logic"] is False
    assert customer_package["internal_artifacts_exported"] is False
    assert cast(
        "tuple[str, ...]", customer_package["included_customer_artifacts"]
    ) == (
        "make_blueprint_json ",
        "minimal_import_setup_guidance ",
        "non_technical_changelog",
    )
    excluded = cast(
        "tuple[str, ...]", customer_package["excluded_internal_artifacts"]
    )
    for internal_artifact in (
        "local_ast_json ",
        "graph_internals ",
        "linter_rules ",
        "internal_prompts ",
        "scoring_logic ",
        "industrial_logic",
    ):
        assert internal_artifact in excluded
    customer_files = cast("tuple[JsonObject, ...]", customer_package["files"])
    assert [file["artifact_role"] for file in customer_files] == [
        "make_blueprint_json ",
        "minimal_import_setup_guidance ",
        "non_technical_changelog",
    ]
    assert all(file["customer_visible"] is True for file in customer_files)
    blueprint = cast("JsonObject", payload["blueprint_artifact"])
    assert blueprint["status"] == "ready"
    assert blueprint["raw_artifact_available"] is True
    assert blueprint["response_includes_raw_json"] is False
    assert "datastore_manifest" not in payload
    assert "runtime_resource_requirements" not in payload
    assert "operator_checklist" not in payload
    package_summary = cast("JsonObject", payload["package_summary"])
    assert package_summary["datastore_resource_count"] == 1
    assert package_summary["connection_requirement_count"] == 1
    assert package_summary["runtime_resource_requirement_count"] == 3
    assert package_summary["operator_checklist_item_count"] == 6
    requirements = cast(
        "JsonObject", payload["make_mcp_live_requirements_summary"]
    )
    assert requirements["status"] == "available"
    assert requirements["minimal_import_required_missing_count"] == 0
    assert requirements["full_live_validation_required_missing_count"] == 0
    assert "critical_missing_count" not in requirements
    missing_compact = cast(
        "tuple[str, ...]", requirements["missing_for_full_live_validation"]
    )
    assert missing_compact == ()
    assert "webhook_list" not in missing_compact
    assert "webhook_create" not in missing_compact
    assert "webhook_delete_or_cleanup" not in missing_compact
    assert requirements["missing_for_minimal_import"] == ()
    assert requirements["status_reason"]
    assert requirements["raw_capability_matrix_available"] is True
    browser_boundary = cast(
        "JsonObject", payload["browser_validation_boundary"]
    )
    assert (
        payload["browser_validation_status"]
        == "offline_parity_no_browser_required"
    )
    assert (
        browser_boundary["browser_validation_status"]
        == "offline_parity_no_browser_required"
    )
    assert (
        browser_boundary["live_canary_status"]
        == "destructive_webhook_datastore_canary_passed_and_cleaned"
    )
    assert (
        browser_boundary["fully_automated_production_status"]
        == "local_mcp_ready_live_canary_passed"
    )
    assert browser_boundary["live_canary_resource_creation_order"] == [
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    ]
    assert "absence in Make UI means cleanup passed" in str(
        browser_boundary["live_canary_cleanup_semantics"]
    )
    assert browser_boundary["requires_operator_approval"] is False
    assert browser_boundary["pancakes_executes_browser_automation"] is False
    assert browser_boundary["pancakes_calls_make_live"] is False
    assert browser_boundary["operation_credit_budget"] == 0
    assert browser_boundary["browser_gated_capabilities"] == ()
    assert browser_boundary["offline_mirror_capabilities"] == (
        "scenario_auto_align ",
        "scenario_module_error_inspection",
    )
    assert (
        browser_boundary["smoke_plan_status"]
        == "retained_for_manual_live_review_only"
    )
    assert (
        browser_boundary["browser_visual_review_status"]
        == "proof_limitation_not_technical_blocker"
    )
    assert browser_boundary["browser_visual_review_blocks_package"] is False
    assert "manual proof evidence" in str(browser_boundary["proof_limitation"])
    assert browser_boundary["smoke_plan_included"] is False
    assert "smoke_plan" not in browser_boundary
    inspector_queries = cast(
        "tuple[JsonObject, ...]", payload["section_inspector_queries"]
    )
    inspector_sections = cast(
        "tuple[str, ...]", payload["section_inspector_sections"]
    )
    assert payload["section_inspection_status"] == "available"
    assert inspector_sections == (
        "live_resources ",
        "blueprint_summary ",
        "parity_plan ",
        "customer_files ",
        "zero_trace",
    )
    assert {
        str(cast("JsonObject", query["arguments"])["section"])
        for query in inspector_queries
    } == set(inspector_sections)
    assert {
        str(cast("JsonObject", query["arguments"])["output_mode"])
        for query in inspector_queries
    } == {"full"}
    assert all(
        query["tool"] == "project.package.inspect"
        for query in inspector_queries
    )
    assert "one full section at a time" in str(
        payload["full_output_truncation_avoidance"]
    )
    assert payload["next_queries"]
    assert_compact_response_bounded(payload)
    assert_no_raw_walls(payload)
    assert_no_bare_ready_when_surfaces_differ(payload)
    assert_no_ambiguous_available_flags(payload)
    assert_no_empty_detail_arrays_in_compact(payload)
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False

    full = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "package ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert full.ok, full
    full_payload = full.payload
    assert "artifact_json" not in full_payload
    datastore_manifest = cast("JsonObject", full_payload["datastore_manifest"])
    assert datastore_manifest["status"] == "ready"
    assert datastore_manifest["resource_count"] == 1
    resource = cast("tuple[JsonObject, ...]", datastore_manifest["resources"])[
        0
    ]
    assert resource["resource_key"] == "stress_events"
    assert resource["live_tool_required"] == "datastore_create"
    assert resource["key_field"] == "request_id"
    assert resource["key_field_status"] == "inferred_from_mapper_key"
    assert "datastore_id" not in resource
    live_apply_plan = cast("JsonObject", full_payload["live_apply_plan"])
    assert live_apply_plan["required_live_capability"] == "live_apply_package"
    assert live_apply_plan["required_live_tool_status"] == "available"
    assert live_apply_plan["contract_status"] == "observed_live_apply_ready"
    assert live_apply_plan["requires_operator_approval"] is False
    assert (
        live_apply_plan["permission_model"]
        == "runtime_api_token_session_scoped"
    )
    assert live_apply_plan["dry_run_required_before_live_write"] is True
    assert (
        live_apply_plan["target_scenario_policy"]
        == "inactive_scratch_scenario_only"
    )
    assert live_apply_plan["pancakes_executes_live_operations"] is True
    assert live_apply_plan["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    assert (
        live_apply_plan["resource_creation_order_human"]
        == "Data Structure -> Data Store -> Webhook -> Scenario"
    )
    assert "absence in Make UI means cleanup passed" in str(
        live_apply_plan["cleanup_semantics"]
    )
    mutation_contract = cast(
        "JsonObject", live_apply_plan["scenario_mutation_contract"]
    )
    assert (
        mutation_contract["live_evidence"]
        == "make_api_scenario_mutation_contract_shapes"
    )
    create_fields = cast(
        "JsonObject", mutation_contract["create_request_fields"]
    )
    assert create_fields["blueprint"] == "json_string"
    assert create_fields["scheduling"] == "json_string"
    assert mutation_contract["create_id_path"] == "$.scenario.id"
    assert mutation_contract["export_blueprint_path"] == "$.response.blueprint"
    assert mutation_contract["delete_id_path"] == "$.scenario"
    assert mutation_contract["activation_allowed"] is False
    assert mutation_contract["run_once_allowed"] is False
    assert mutation_contract["raw_scenario_id_persistence_allowed"] is False
    write_operations = cast(
        "tuple[str, ...]", live_apply_plan["write_operations"]
    )
    assert "create_data_structures" in write_operations
    assert (
        "create_data_stores_with_created_data_structure_ids" in write_operations
    )
    assert "create_webhooks" in write_operations
    assert "bind_created_resource_ids_into_blueprint" in write_operations
    assert (
        "create_inactive_scratch_scenario_with_bound_blueprint"
        in write_operations
    )
    assert "set_scenario_interface_after_on_demand_schedule" in write_operations
    assert (
        "delete_or_preserve_scratch_scenario_by_rollback_policy"
        in write_operations
    )
    read_operations = cast(
        "tuple[str, ...]", live_apply_plan["read_operations"]
    )
    assert "validate_module_configurations" in read_operations
    assert "export_blueprint_from_response_blueprint_path" in read_operations
    operation_budget = cast("JsonObject", live_apply_plan["operation_budget"])
    assert operation_budget["dry_run_live_operation_budget"] == 0
    assert operation_budget["run_once_operation_budget"] == 0
    assert operation_budget["activation_allowed"] is False
    live_apply_contract = cast(
        "JsonObject", live_apply_plan["capability_contract"]
    )
    dry_run_checks = cast(
        "tuple[str, ...]", live_apply_contract["dry_run_checks"]
    )
    assert "scenario_mutation_request_contract_ready" in dry_run_checks
    assert "scenario_interface_update_contract_ready" in dry_run_checks
    assert "module_configuration_validation_contract_ready" in dry_run_checks
    assert "datastore_strict_schema_validation_contract_ready" in dry_run_checks
    assert "webhook_configuration_validation_contract_ready" in dry_run_checks
    apply_sequence = cast(
        "tuple[str, ...]", live_apply_contract["apply_sequence"]
    )
    assert apply_sequence[0] == "create_data_structures_from_datastructure_json"
    assert apply_sequence[1] == "create_data_stores_from_datastore_json"
    assert apply_sequence[2] == "create_webhooks_from_webhook_json"
    assert apply_sequence[3] == "bind_created_resource_ids_into_blueprint"
    assert (
        "set_scenario_interface_when_package_declares_input_output"
        in apply_sequence
    )
    assert (
        "validate_module_configurations_with_typed_make_validator"
        in apply_sequence
    )
    assert (
        "validate_datastore_seed_records_against_strict_schema"
        in apply_sequence
    )
    assert "validate_webhook_defaults_before_create_or_select" in apply_sequence
    required_child_capabilities = cast(
        "tuple[str, ...]",
        live_apply_contract["required_child_capabilities"],
    )
    assert required_child_capabilities == (
        "scenario_import ",
        "scenario_interface_update ",
        "module_configuration_validation ",
        "datastore_list ",
        "datastore_create ",
        "datastore_strict_schema_validation ",
        "connection_list_metadata ",
        "connection_bind_to_module ",
        "webhook_configuration_validation ",
        "webhook_create_or_select ",
        "webhook_bind_to_module ",
        "scenario_inspect_modules ",
        "scenario_export",
    )
    assert live_apply_plan["rollback_plan_ref"] == "rollback_plan"
    assert live_apply_plan["rollback_required"] is True
    full_browser_boundary = cast(
        "JsonObject", full_payload["browser_validation_boundary"]
    )
    assert full_browser_boundary["smoke_plan_included"] is True
    smoke_plan = cast("JsonObject", full_browser_boundary["smoke_plan"])
    assert smoke_plan["operation_credit_budget"] == 0
    forbidden_actions = cast("list[str]", smoke_plan["forbidden_actions"])
    assert "run_once" in forbidden_actions
    assert "credential_save" in forbidden_actions
    capabilities = cast("JsonObject", full_payload["make_mcp_capabilities"])
    scenario_list = cast("JsonObject", capabilities["scenario_list"])
    scenario_run_once = cast("JsonObject", capabilities["scenario_run_once"])
    scenario_auto_align = cast(
        "JsonObject", capabilities["scenario_auto_align"]
    )
    assert scenario_list["status"] == "available"
    assert scenario_run_once["status"] == "available"
    assert (
        scenario_run_once["bridge_evidence_status"]
        == "observed_run_once_execution_ready"
    )
    run_once_contract = cast(
        "JsonObject", scenario_run_once["run_once_contract"]
    )
    assert (
        run_once_contract["live_evidence"]
        == "make_mcp_scenario_run_once_shapes"
    )
    assert run_once_contract["inactive_run_error"] == "scenario_not_activated"
    assert scenario_auto_align["status"] == "offline_mirror"
    assert scenario_auto_align["owning_layer"] == "pancakes_offline_engine"
    assert (
        scenario_auto_align["fallback_strategy"]
        == "use_pancakes_offline_mirror"
    )
    auto_align_contract = cast(
        "JsonObject", scenario_auto_align["offline_mirror_contract"]
    )
    assert auto_align_contract["contract_status"] == "offline_mirror_ready"
    assert auto_align_contract["live_web_dependency"] is False
    scenario_module_errors = cast(
        "JsonObject", capabilities["scenario_module_error_inspection"]
    )
    assert scenario_module_errors["status"] == "offline_mirror"
    module_error_contract = cast(
        "JsonObject", scenario_module_errors["offline_mirror_contract"]
    )
    assert module_error_contract["contract_status"] == "offline_mirror_ready"
    assert module_error_contract["live_web_dependency"] is False
    assert "make_mcp_module_requirement_extraction_shapes" in cast(
        "tuple[str, ...]",
        module_error_contract["live_evidence"],
    )
    assert "make_mcp_runtime_resource_requirement_extraction_shapes" in cast(
        "tuple[str, ...]",
        module_error_contract["live_evidence"],
    )
    assert (
        module_error_contract["requirement_oracle"]
        == "extract_blueprint_components"
    )
    assert "webhook_create_or_select" in capabilities
    scenario_interface_update = cast(
        "JsonObject", capabilities["scenario_interface_update"]
    )
    assert scenario_interface_update["status"] == "available"
    assert scenario_interface_update["mapped_live_tool"] == (
        "scenarios_set_interface + scenarios_interface"
    )
    interface_contract = cast(
        "JsonObject",
        scenario_interface_update["scenario_interface_contract"],
    )
    assert (
        interface_contract["contract_status"]
        == "observed_interface_schedule_ready"
    )
    assert (
        interface_contract["live_evidence"]
        == "make_mcp_scenario_interface_schedule_shapes"
    )
    assert "on-demand" in str(
        interface_contract["required_input_schedule_policy"]
    )
    module_configuration = cast(
        "JsonObject", capabilities["module_configuration_validation"]
    )
    assert module_configuration["status"] == "available"
    assert (
        module_configuration["mapped_live_tool"]
        == "validate_module_configuration"
    )
    module_configuration_contract = cast(
        "JsonObject",
        module_configuration["module_configuration_contract"],
    )
    assert (
        module_configuration_contract["contract_status"]
        == "observed_module_configuration_validation_ready"
    )
    assert (
        module_configuration_contract["live_evidence"]
        == "make_mcp_module_configuration_validation_shapes"
    )
    assert module_configuration_contract["writes_performed"] is False
    webhook_list = cast("JsonObject", capabilities["webhook_list"])
    webhook_configuration = cast(
        "JsonObject", capabilities["webhook_configuration_validation"]
    )
    webhook_create = cast("JsonObject", capabilities["webhook_create"])
    webhook_create_or_select = cast(
        "JsonObject", capabilities["webhook_create_or_select"]
    )
    connection_bind = cast(
        "JsonObject", capabilities["connection_bind_to_module"]
    )
    webhook_bind = cast("JsonObject", capabilities["webhook_bind_to_module"])
    webhook_delete_or_cleanup = cast(
        "JsonObject", capabilities["webhook_delete_or_cleanup"]
    )
    assert webhook_list["status"] == "available"
    assert webhook_list["mapped_live_tool"] == "hooks_list"
    assert webhook_configuration["status"] == "available"
    assert (
        webhook_configuration["bridge_evidence_status"]
        == "observed_webhook_configuration_validation_ready"
    )
    webhook_configuration_contract = cast(
        "JsonObject",
        webhook_configuration["webhook_configuration_contract"],
    )
    assert (
        webhook_configuration_contract["live_evidence"]
        == "make_mcp_hook_configuration_validation_shapes"
    )
    assert webhook_create["status"] == "available"
    assert webhook_create["mapped_live_tool"] == "hooks_create"
    assert webhook_create_or_select["status"] == "available"
    assert webhook_create_or_select["owning_layer"] == "make_mcp"
    assert (
        webhook_create_or_select["mapped_live_tool"]
        == "hooks_list + hooks_create"
    )
    _assert_binding_bridge_detail(
        connection_bind,
        status="available",
        resource_kind="connection",
        contract_status="observed_live_bind_ready",
    )
    _assert_binding_bridge_detail(
        webhook_bind,
        status="available",
        resource_kind="webhook",
        contract_status="observed_live_bind_ready",
    )
    assert webhook_delete_or_cleanup["status"] == "available"
    assert webhook_delete_or_cleanup["mapped_live_tool"] == "hooks_delete"
    live_apply_capability = cast(
        "JsonObject", capabilities["live_apply_package"]
    )
    assert live_apply_capability["status"] == "available"
    assert live_apply_capability["owning_layer"] == "make_api_bridge"
    assert (
        live_apply_capability["fallback_strategy"]
        == "use_guarded_operator_live_bridge"
    )
    assert "capability_contract" in live_apply_capability
    live_capability_contract = cast(
        "JsonObject", live_apply_capability["capability_contract"]
    )
    assert (
        live_capability_contract["scenario_mutation_contract"]
        == mutation_contract
    )
    for capability_id, detail in capabilities.items():
        detail_mapping = cast("JsonObject", detail)
        assert detail_mapping["capability"] == capability_id
        assert detail_mapping["status"] in {
            "available ",
            "missing ",
            "missing_batch_orchestrator ",
            "partial ",
            "partial_composable ",
            "offline_mirror ",
            "operator_manual ",
            "operator_bridge_ready",
        }
        assert detail_mapping["owning_layer"] in {
            "make_mcp ",
            "pancakes_offline_engine ",
            "operator_manual_make_ui ",
            "future_bridge ",
            "make_api_bridge",
        }
        assert "fallback_strategy" in detail_mapping
        assert "mapped_live_tool" in detail_mapping
    assert_no_orphan_capabilities(full_payload)
    pdf_inputs = cast("JsonObject", full_payload["pdf_report_inputs"])
    assert "available" not in pdf_inputs
    assert pdf_inputs["pdf_report_generator_available"] is True
    assert pdf_inputs["pdf_report_inputs_status"] == "blocked_missing_notes"
    runtime_requirements = cast(
        "tuple[JsonObject, ...]", full_payload["runtime_resource_requirements"]
    )
    live_tools = {
        str(requirement["live_tool_required"])
        for requirement in runtime_requirements
    }
    assert live_tools <= set(capabilities)
    resource_owners = {
        str(requirement["provisioning_owner"])
        for requirement in runtime_requirements
    }
    assert "pancakes_live_upload" in resource_owners
    assert all(
        requirement["manual_make_ui_required"] is False
        for requirement in runtime_requirements
    )
    live_resource_package = cast(
        "JsonObject", full_payload["make_live_resource_package"]
    )
    assert live_resource_package["status"] == "ready"
    assert (
        cast("int", live_resource_package["auto_provisioned_resource_count"])
        >= 2
    )
    assert live_resource_package["client_supplied_connection_count"] == 1
    assert (
        cast(
            "int", live_resource_package["client_supplied_runtime_value_count"]
        )
        >= 1
    )
    assert live_resource_package["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    assert (
        live_resource_package["resource_creation_order_human"]
        == "Data Structure -> Data Store -> Webhook -> Scenario"
    )
    live_canary_contract = cast(
        "JsonObject", live_resource_package["live_canary_contract"]
    )
    assert (
        live_canary_contract["status"]
        == "destructive_webhook_datastore_canary_passed_and_cleaned"
    )
    assert live_canary_contract["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    assert "cleanup passed" in str(live_canary_contract["cleanup_semantics"])
    upload_plan = cast("JsonObject", live_resource_package["upload_plan"])
    assert upload_plan["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    live_files = {
        str(file["path"])
        for file in cast(
            "tuple[JsonObject, ...]", live_resource_package["files"]
        )
    }
    assert "make-live/datastructure.json" in live_files
    assert "make-live/datastore.json" in live_files
    assert "make-live/webhook.json" in live_files
    assert "make-live/upload-plan.json" in live_files
    assert (
        live_resource_package["manual_make_ui_required_for_resources"] is False
    )

    sectioned_live_resources = execute_mcp_tool(
        tool_name="project.package.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "section": "live_resources",
        },
        repo_root=tmp_path,
    )
    sectioned_customer_files = execute_mcp_tool(
        tool_name="project.package.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "section": "customer_files",
        },
        repo_root=tmp_path,
    )
    sectioned_blueprint = execute_mcp_tool(
        tool_name="project.package.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "section": "blueprint_summary",
        },
        repo_root=tmp_path,
    )
    sectioned_parity = execute_mcp_tool(
        tool_name="project.package.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "section": "parity_plan",
        },
        repo_root=tmp_path,
    )
    sectioned_zero_trace = execute_mcp_tool(
        tool_name="project.package.inspect",
        arguments={
            "project_id": "stress ",
            "profile": "live_preflight ",
            "section": "zero_trace",
        },
        repo_root=tmp_path,
    )

    sectioned_results = (
        sectioned_live_resources,
        sectioned_customer_files,
        sectioned_blueprint,
        sectioned_parity,
        sectioned_zero_trace,
    )
    for sectioned_result in sectioned_results:
        assert sectioned_result.ok, sectioned_result
        sectioned_payload = sectioned_result.payload
        rendered = json.dumps(sectioned_payload, sort_keys=True)
        assert sectioned_payload["status"] == "ok"
        assert (
            sectioned_payload["status_surface"]
            == "sectioned_package_inspection"
        )
        inspector_queries = cast(
            "tuple[JsonObject, ...]",
            sectioned_payload["section_inspector_queries"],
        )
        inspector_sections = cast(
            "tuple[str, ...]", sectioned_payload["section_inspector_sections"]
        )
        assert sectioned_payload["section_inspection_status"] == "available"
        assert inspector_sections == (
            "live_resources ",
            "blueprint_summary ",
            "parity_plan ",
            "customer_files ",
            "zero_trace",
        )
        assert (
            sectioned_payload["section_payload_returned"] in inspector_sections
        )
        assert {
            str(cast("JsonObject", query["arguments"])["section"])
            for query in inspector_queries
        } == set(inspector_sections)
        assert "one section at a time" in str(
            sectioned_payload["full_output_truncation_avoidance"]
        )
        assert sectioned_payload["full_package_response_avoided"] is True
        assert sectioned_payload["large_package_payload_returned"] is False
        assert sectioned_payload["writes_performed"] is False
        assert sectioned_payload["write_actions"] == []
        assert sectioned_payload["live_make_called"] is False
        assert sectioned_payload["provider_api_call"] is False
        assert "blueprint_artifact_json" not in sectioned_payload
        assert "make_live_resource_package" not in sectioned_payload
        assert "customer_delivery_package" not in sectioned_payload
        assert "artifact_json" not in rendered
        assert "blueprint_artifact_json" not in rendered

    live_section = cast(
        "JsonObject", sectioned_live_resources.payload["section_payload"]
    )
    assert live_section["section"] == "live_resources"
    assert live_section["evidence_scope"] == "project_local_manifest_evidence"
    assert live_section["global_catalog_structure_evidence"] == (
        "not_required_for_project_local_manifest"
    )
    assert live_section["project_local_structure_evidence"] == "available"
    assert live_section["blocking"] is False
    assert live_section["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    assert live_section["data_structure_count"] == 1
    assert live_section["data_store_count"] == 1
    assert live_section["webhook_count"] == 1
    assert live_section["manual_make_ui_required_for_resources"] is False

    customer_section = cast(
        "JsonObject", sectioned_customer_files.payload["section_payload"]
    )
    assert customer_section["section"] == "customer_files"
    assert customer_section["customer_receives_internal_report"] is False
    assert customer_section["customer_receives_ast"] is False
    assert customer_section["internal_artifacts_exported"] is False
    assert customer_section["file_count"] == 3

    blueprint_section = cast(
        "JsonObject", sectioned_blueprint.payload["section_payload"]
    )
    assert blueprint_section["section"] == "blueprint_summary"
    assert blueprint_section["raw_artifact_returned"] is False
    assert blueprint_section["module_count"] == package_summary["module_count"]
    assert blueprint_section["route_count"] == package_summary["route_count"]

    parity_section = cast(
        "JsonObject", sectioned_parity.payload["section_payload"]
    )
    assert parity_section["section"] == "parity_plan"
    assert parity_section["scenario_activation_allowed"] is False
    assert parity_section["run_once_allowed"] is False
    assert parity_section["resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )

    zero_trace_section = cast(
        "JsonObject", sectioned_zero_trace.payload["section_payload"]
    )
    assert zero_trace_section["section"] == "zero_trace"
    assert zero_trace_section["zero_trace_status"] == "passed"
    assert zero_trace_section["leak_count"] == 0

    compact_with_raw_request = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "package ",
            "profile": "live_preflight",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )
    full_with_raw_request = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "package ",
            "profile": "live_preflight ",
            "output_mode": "full",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )

    assert compact_with_raw_request.ok, compact_with_raw_request
    assert full_with_raw_request.ok, full_with_raw_request
    assert "artifact_json" not in compact_with_raw_request.payload
    assert "artifact_json" in full_with_raw_request.payload

    written = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "stress ",
            "action": "package ",
            "profile": "live_preflight",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert written.ok, written
    written_payload = written.payload
    assert written_payload["customer_delivery_package_written"] is True
    assert written_payload["live_resource_package_written"] is True
    package_path = tmp_path / str(
        written_payload["customer_delivery_package_path"]
    )
    assert package_path.is_dir()
    live_resource_path = tmp_path / str(
        written_payload["live_resource_package_path"]
    )
    assert live_resource_path.is_dir()
    for resource_file in (
        "datastructure.json ",
        "datastore.json ",
        "webhook.json ",
        "upload-plan.json",
    ):
        assert (live_resource_path / resource_file).is_file()
    datastore_artifact = cast(
        "JsonObject",
        json.loads(
            (live_resource_path / "datastore.json").read_text(encoding="utf-8")
        ),
    )
    datastore_resource = cast(
        "list[JsonObject]", datastore_artifact["resources"]
    )[0]
    assert datastore_resource["datastructure_ref"] == "stress_events"
    assert (
        datastore_resource["bind_placeholder"]
        == "{{runtime.datastore.stress_events}}"
    )
    webhook_artifact = cast(
        "JsonObject",
        json.loads(
            (live_resource_path / "webhook.json").read_text(encoding="utf-8")
        ),
    )
    webhook_resource = cast("list[JsonObject]", webhook_artifact["resources"])[
        0
    ]
    assert webhook_resource["typeName"] == "gateway-webhook"
    assert webhook_resource["manual_create_prompt_allowed"] is False
    manifest = cast(
        "JsonObject",
        json.loads(
            (package_path / "delivery-manifest.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    written_files = cast(
        "list[JsonObject] | tuple[JsonObject, ...]", manifest["files"]
    )
    written_paths = {str(file["path"]) for file in written_files}
    assert any(path.endswith(".blueprint.json") for path in written_paths)
    assert any(path.endswith(".import-setup.md") for path in written_paths)
    assert any(path.endswith(".changelog.md") for path in written_paths)
    assert manifest["customer_receives_internal_report"] is False
    assert manifest["internal_artifacts_exported"] is False
    manifest_text = json.dumps(manifest, sort_keys=True)
    assert "blueprint_artifact_json" not in manifest_text
    assert "datastore_manifest" not in manifest_text
    assert "live_apply_plan" not in manifest_text
    assert "raw_validation_report" in manifest_text
    for file_name in written_paths:
        text = (package_path / file_name).read_text(encoding="utf-8")
        if file_name.endswith(".blueprint.json"):
            blueprint = cast("JsonObject", json.loads(text))
            assert "artifact_format" not in blueprint
            assert "scenario" not in blueprint
            assert "flow" in blueprint
        else:
            assert "local_ast_json" not in text
            assert "graph_internals" not in text
            assert "linter_rules" not in text
            assert "internal_prompts" not in text


def test_project_verify_live_preflight_is_package_aware_without_live_calls(
    tmp_path: Path,
) -> None:
    """live_preflight reports Make.com MCP requirements without touching.

    Make.com.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.verify",
        arguments={"project_id": "stress", "profile": "live_preflight"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "ok"
    assert payload["package_status"] == "ready"
    assert payload["minimal_import_package_status"] == "ready"
    assert payload["full_live_validation_status"] == "ready"
    assert payload["make_mcp_live_requirements_status"] == "available"
    assert payload["datastore_manifest_status"] == "ready"
    assert (
        payload["connection_mapping_status"]
        == "client_app_connections_required"
    )
    assert (
        payload["resource_mapping_status"] == "client_runtime_values_required"
    )
    assert payload["live_preflight_status"] == "ready"
    assert (
        payload["live_canary_status"]
        == "destructive_webhook_datastore_canary_passed_and_cleaned"
    )
    assert payload["live_resource_creation_order"] == (
        "data_structure ",
        "data_store ",
        "webhook ",
        "scenario",
    )
    requirements = cast(
        "JsonObject", payload["make_mcp_live_requirements_summary"]
    )
    assert requirements["minimal_import_required_missing_count"] == 0
    assert requirements["full_live_validation_required_missing_count"] == 0
    assert "critical_missing_count" not in requirements
    missing_capabilities = cast(
        "tuple[str, ...]", requirements["missing_for_full_live_validation"]
    )
    assert missing_capabilities == ()
    assert "webhook_list" not in missing_capabilities
    assert "webhook_create" not in missing_capabilities
    assert "webhook_delete_or_cleanup" not in missing_capabilities
    assert requirements["missing_for_minimal_import"] == ()
    assert payload["live_make_runtime_status"] == "not_evaluated"
    browser_boundary = cast(
        "JsonObject", payload["browser_validation_boundary"]
    )
    assert (
        payload["browser_validation_status"]
        == "offline_parity_no_browser_required"
    )
    assert (
        browser_boundary["browser_validation_status"]
        == "offline_parity_no_browser_required"
    )
    assert browser_boundary["requires_operator_approval"] is False
    assert browser_boundary["pancakes_executes_browser_automation"] is False
    assert browser_boundary["pancakes_calls_make_live"] is False
    assert browser_boundary["browser_gated_capabilities"] == ()
    assert (
        browser_boundary["browser_visual_review_status"]
        == "proof_limitation_not_technical_blocker"
    )
    assert browser_boundary["browser_visual_review_blocks_package"] is False
    assert browser_boundary["smoke_plan_included"] is False
    assert "smoke_plan" not in browser_boundary
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False


def test_project_verify_infers_missing_connection_from_module_requirement(
    tmp_path: Path,
) -> None:
    """Live-observed module requirements become local connection mapping.

    evidence.
    """
    project_path = (
        tmp_path / "projects" / "missing-connection" / "scenario.json"
    )
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Connection Requirement Local Check",
        "flow": [
            {
                "id": 1,
                "module": "google-email:sendAnEmail",
                "version": 4,
                "parameters": {},
                "mapper": {
                    "html": "<p>Probe</p>",
                    "subject": "Probe",
                    "to": ["ops@example.invalid"],
                },
            }
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    result = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "missing-connection ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "missing-connection ",
            "action": "preview ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert preview.ok, preview
    payload = result.payload
    assert (
        payload["connection_mapping_status"]
        == "client_app_connections_required"
    )
    summary = cast("JsonObject", preview.payload["connection_binding_summary"])
    assert summary["binding_count"] == 1
    group = cast("tuple[JsonObject, ...]", summary["groups"])[0]
    assert group["projection_kind"] == "make_connection_required_by_module"
    assert group["field"] == "__IMTCONN__"
    assert group["provider"] == "google-email"
    assert (
        group["live_evidence"]
        == "make_mcp_module_requirement_extraction_shapes"
    )


def test_project_verify_infers_missing_webhook_from_module_requirement(
    tmp_path: Path,
) -> None:
    """Live-observed module requirements become local webhook mapping.

    evidence.
    """
    project_path = tmp_path / "projects" / "missing-webhook" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Webhook Requirement Local Check",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "version": 1,
                "parameters": {},
                "mapper": {},
            }
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    result = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "missing-webhook ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "missing-webhook ",
            "action": "preview ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert preview.ok, preview
    payload = result.payload
    assert (
        payload["resource_mapping_status"] == "auto_provisioned_by_live_upload"
    )
    summary = cast("JsonObject", preview.payload["resource_binding_summary"])
    assert summary["binding_count"] == 1
    group = cast("tuple[JsonObject, ...]", summary["groups"])[0]
    assert group["projection_kind"] == "runtime_resource_required_by_module"
    assert group["field"] == "hook"
    assert group["provider"] == "webhook"
    assert group["resource_type"] == "gateway-webhook"
    assert (
        group["live_evidence"]
        == "make_mcp_runtime_resource_requirement_extraction_shapes"
    )


def test_project_verify_infers_missing_datastore_from_module_requirement(
    tmp_path: Path,
) -> None:
    """Live-observed module requirements become local Data Store mapping.

    evidence.
    """
    project_path = tmp_path / "projects" / "missing-datastore" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Data Store Requirement Local Check",
        "flow": [
            {
                "id": 1,
                "module": "datastore:AddRecord",
                "version": 1,
                "parameters": {},
                "mapper": {
                    "data": {"status": "probe"},
                    "key": "probe-key",
                    "overwrite": False,
                },
            }
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    result = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "missing-datastore ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "missing-datastore ",
            "action": "preview ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert preview.ok, preview
    payload = result.payload
    assert (
        payload["resource_mapping_status"] == "auto_provisioned_by_live_upload"
    )
    summary = cast("JsonObject", preview.payload["resource_binding_summary"])
    assert summary["binding_count"] == 1
    group = cast("tuple[JsonObject, ...]", summary["groups"])[0]
    assert group["projection_kind"] == "runtime_resource_required_by_module"
    assert group["field"] == "datastore"
    assert group["provider"] == "datastore"
    assert group["resource_type"] == "datastore"
    assert (
        group["live_evidence"]
        == "make_mcp_runtime_resource_requirement_extraction_shapes"
    )


def test_project_view_datastores_extracts_local_manifest(
    tmp_path: Path,
) -> None:
    """project.view surface=datastores prepares local datastore manifests.

    only.
    """
    _write_stress_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "stress", "surface": "datastores"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    assert manifest["status"] == "ready"
    assert manifest["resource_count"] == 1
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    assert resource["resource_key"] == "stress_events"
    assert resource["live_tool_required"] == "datastore_create"
    assert resource["key_field"] == "request_id"
    assert resource["key_field_status"] == "inferred_from_mapper_key"
    assert resource["key_field_confidence"] == "high"
    assert resource["key_field_source_path"]
    assert resource["source_json_pointer"]
    assert resource["make_resource_kind"] == "datastore"
    assert resource["schema_status"] == "known"
    assert resource["data_structure_status"] == "known_from_mapper_data"
    assert resource["data_structure_confidence"] == "high"
    schema_fields = cast("list[str]", resource["schema_fields"])
    assert resource["data_structure_field_count"] == len(schema_fields)
    assert resource["data_structure_source_path_count"] == 270
    assert resource["returned_data_structure_source_path_count"] == 3
    assert resource["hidden_data_structure_source_path_count"] == 267
    assert resource["raw_data_structure_source_paths_available"] is True
    assert resource["data_structure_requires_schema_evidence"] is False
    source_paths = cast(
        "tuple[str, ...]", resource["data_structure_source_paths"]
    )
    assert source_paths
    assert all(path.endswith(".mapper.data") for path in source_paths)
    assert resource["seed_records_available"] is False
    assert resource["record_count"] == 0
    _assert_datastore_batch_plan(
        cast("JsonObject", resource["batch_upsert_plan"]),
        dry_run_status="empty_batch",
        record_count=0,
    )
    assert resource["overwrite_policy"] == "created_package_resources_only"
    assert resource["upsert_strategy"] == "live_upload_sequence"
    assert resource["requires_live_make_mcp"] is True
    assert resource["capability_status"] == "available"
    assert resource["fallback_strategy"] == "use_make_mcp_tool"
    assert resource["requires_operator_mapping"] is False
    assert "datastore_id" not in resource
    assert "make_datastore_id" not in resource
    assert "provider_resource_id" not in resource
    assert result.payload["live_make_called"] is False


def test_project_view_datastores_infers_key_field_only_from_mapper_key(
    tmp_path: Path,
) -> None:
    """Datastore keys come from AddRecord mapper.key evidence, not first data.

    fields.
    """
    _write_datastore_key_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "keyed", "surface": "datastores"},
        repo_root=tmp_path,
    )
    package = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "keyed ",
            "action": "package ",
            "profile": "live_preflight ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert package.ok, package
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    package_manifest = cast("JsonObject", package.payload["datastore_manifest"])
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    package_resource = cast(
        "tuple[JsonObject, ...]", package_manifest["resources"]
    )[0]
    for row in (resource, package_resource):
        assert row["schema_fields"] == ["company", "request_id"]
        assert row["schema_status"] == "known"
        assert row["data_structure_status"] == "known_from_mapper_data"
        assert row["data_structure_confidence"] == "high"
        assert row["data_structure_field_count"] == 2
        assert row["data_structure_source_path_count"] == 1
        assert row["returned_data_structure_source_path_count"] == 1
        assert row["hidden_data_structure_source_path_count"] == 0
        assert row["raw_data_structure_source_paths_available"] is True
        assert row["data_structure_requires_schema_evidence"] is False
        assert row["key_field"] == "request_id"
        assert row["key_field_status"] == "inferred_from_mapper_key"
        assert row["key_field_confidence"] == "high"
        assert str(row["key_field_source_path"]).endswith(".mapper.key")
        assert row["requires_operator_mapping"] is False


def test_project_view_datastores_plans_batch_upsert_records(
    tmp_path: Path,
) -> None:
    """Seed records produce create/update dry-run plans without live.

    operations.
    """
    _write_seeded_datastore_project(
        tmp_path,
        project_id="seeded",
        resource_key="seeded_records",
        seed_records=(
            {
                "operation": "create ",
                "key": "req-1",
                "data": {"request_id": "req-1"},
            },
            {
                "operation": "update ",
                "key": "req-2",
                "data": {"request_id": "req-2"},
            },
        ),
    )

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "seeded", "surface": "datastores"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    plan = cast("JsonObject", resource["batch_upsert_plan"])
    counts = cast("JsonObject", plan["operation_counts"])
    assert resource["seed_records_available"] is True
    _assert_datastore_batch_plan(
        plan, dry_run_status="dry_run_plan_ready", record_count=2
    )
    assert counts["create"] == 1
    assert counts["update"] == 1
    assert plan["record_keys"] == ("req-1", "req-2")
    assert plan["schema_validation_status"] == "passed"
    assert plan["unknown_record_fields"] == ()
    assert plan["apply_status"] == "session_scoped_apply_ready"
    assert result.payload["live_make_called"] is False


def test_project_view_datastores_blocks_seed_fields_outside_known_schema(
    tmp_path: Path,
) -> None:
    """Seed record fields must match the inferred Data Store schema before live.

    upsert.
    """
    _write_seeded_datastore_project(
        tmp_path,
        project_id="schema-mismatch",
        resource_key="schema_mismatch_records",
        seed_records=(
            {
                "operation": "update ",
                "key": "req-1",
                "data": {
                    "request_id": "req-1 ",
                    "unexpected": "rejected by Make strict schemas",
                },
            },
        ),
    )

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "schema-mismatch", "surface": "datastores"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    plan = cast("JsonObject", resource["batch_upsert_plan"])
    _assert_datastore_batch_plan(
        plan,
        dry_run_status="blocked_unknown_record_fields",
        record_count=1,
    )
    assert plan["apply_status"] == "blocked_unknown_record_fields"
    assert plan["schema_validation_status"] == "blocked_unknown_record_fields"
    assert plan["unknown_record_fields"] == ("unexpected",)
    assert plan["unknown_record_field_count"] == 1
    assert result.payload["live_make_called"] is False


def test_project_view_datastores_blocks_oversized_batch_plan(
    tmp_path: Path,
) -> None:
    """Oversized Data Store seed batches are blocked before any live apply."""
    seed_records: tuple[JsonObject, ...] = tuple(
        cast(
            "JsonObject",
            {
                "operation": "create ",
                "key": f"req-{index}",
                "data": {"request_id": f"req-{index}"},
            },
        )
        for index in range(101)
    )
    _write_seeded_datastore_project(
        tmp_path,
        project_id="oversized",
        resource_key="oversized_records",
        seed_records=seed_records,
    )

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "oversized", "surface": "datastores"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    plan = cast("JsonObject", resource["batch_upsert_plan"])
    _assert_datastore_batch_plan(
        plan,
        dry_run_status="blocked_oversized_batch",
        record_count=101,
    )
    assert plan["apply_status"] == "blocked_oversized_batch"
    assert plan["returned_record_key_count"] == 12
    assert plan["hidden_record_key_count"] == 89


def test_project_view_datastores_marks_unknown_key_operator_gated(
    tmp_path: Path,
) -> None:
    """Datastore manifests do not invent key fields when AddRecord has no.

    mapper.key.
    """
    _write_unknown_datastore_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "unknown-key", "surface": "datastores"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    manifest = cast("JsonObject", result.payload["datastore_manifest"])
    resource = cast("tuple[JsonObject, ...]", manifest["resources"])[0]
    assert resource["schema_fields"] == []
    assert resource["schema_status"] == "unknown"
    assert (
        resource["data_structure_status"] == "unknown_requires_schema_evidence"
    )
    assert resource["data_structure_confidence"] == "unknown"
    assert resource["data_structure_field_count"] == 0
    assert resource["data_structure_source_path_count"] == 0
    assert resource["returned_data_structure_source_path_count"] == 0
    assert resource["hidden_data_structure_source_path_count"] == 0
    assert resource["raw_data_structure_source_paths_available"] is False
    assert resource["data_structure_requires_schema_evidence"] is True
    assert resource["key_field"] is None
    assert resource["key_field_status"] == "unknown_requires_key_evidence"
    assert resource["key_field_confidence"] == "unknown"
    assert resource["key_field_source_path"] is None
    assert resource["source_json_pointer"] is None
    assert resource["requires_operator_mapping"] is False
    assert (
        resource["auto_provisioning_status"] == "blocked_missing_schema_or_key"
    )


def test_project_search_separates_templates_from_scenarios_locally(
    tmp_path: Path,
) -> None:
    """Local search never depends on an external business database."""
    _write_stress_project(tmp_path)
    _write_template_library(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.search",
        arguments={},
        repo_root=tmp_path,
    )
    with_templates = execute_mcp_tool(
        tool_name="project.search",
        arguments={"include_templates": True},
        repo_root=tmp_path,
    )
    templates_only = execute_mcp_tool(
        tool_name="project.search",
        arguments={"project_kind": "template_library"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert with_templates.ok, with_templates
    assert templates_only.ok, templates_only
    payload = result.payload
    assert payload["status"] == "ok"
    assert payload["core_database_contains_business_state"] is False
    assert payload["external_business_state_read"] is False
    assert payload["database_owner"] == "pancakes_core"
    assert "business_lifecycle_status" not in payload
    assert "sre_lifecycle_project_count" not in payload
    assert payload["local_project_count"] == 1
    assert (
        payload["local_project_count_semantics"]
        == "local_scenario_project_count"
    )
    assert payload["local_scenario_project_count"] == 1
    assert payload["local_template_library_count"] == 1
    assert payload["local_fixture_project_count"] == 0
    assert payload["total_local_artifact_count"] == 2
    assert payload["returned_local_artifact_count"] == 1
    assert payload["returned_local_scenario_project_count"] == 1
    assert payload["returned_template_library_count"] == 0
    assert payload["template_libraries_available"] is True
    assert payload["hidden_template_library_count"] == 1
    assert payload["local_projects_available"] is True
    projects = cast("tuple[JsonObject, ...]", payload["local_projects"])
    assert [project["project_id"] for project in projects] == ["stress"]
    assert projects[0]["project_kind"] == "local_scenario_project"
    template_rows = cast(
        "tuple[JsonObject, ...]", with_templates.payload["local_projects"]
    )
    assert with_templates.payload["returned_local_artifact_count"] == 2
    assert with_templates.payload["returned_local_scenario_project_count"] == 1
    assert with_templates.payload["returned_template_library_count"] == 1
    assert with_templates.payload["hidden_template_library_count"] == 0
    assert {project["project_kind"] for project in template_rows} == {
        "local_scenario_project ",
        "template_library",
    }
    templates = cast(
        "tuple[JsonObject, ...]", templates_only.payload["local_projects"]
    )
    assert [project["project_kind"] for project in templates] == [
        "template_library"
    ]
    assert templates_only.payload["hidden_template_library_count"] == 0
    assert templates[0]["source_of_truth"] == "local_template_library"
    assert templates[0]["artifact_source"] == "template_library_json"
    assert templates[0]["artifact_status"] == "approved_template_library"
    _assert_template_library_path_report(templates[0])


def test_project_create_writes_sqlite_metadata_and_deterministic_envelope(
    tmp_path: Path,
) -> None:
    """New local projects use SQLite metadata plus deterministic artifact.

    envelopes.
    """
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "enveloped ",
            "name": "Enveloped ",
            "workspace_number": "0007 ",
            "scenario_number": "0012",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "0007"
        / "0012-enveloped"
        / "scenario.json"
    )
    scenario_path_text = (
        "temp/pancakes/project-artifacts/0007/0012-enveloped/scenario.json"
    )
    assert scenario_path.is_file()
    assert not (tmp_path / "projects" / "0007").exists()
    assert payload["status"] == "created"
    assert payload["created"] is True
    storage_model = cast("JsonObject", payload["storage_model"])
    assert (
        storage_model["sqlite_source_of_truth"]
        == "sqlite:local_project_metadata"
    )
    _assert_generated_project_path_report(
        storage_model,
        logical_project_path="projects/0007/0012-enveloped",
        physical_artifact_path="temp/pancakes/project-artifacts/0007/0012-enveloped",
        scenario_path_text=scenario_path_text,
    )
    project = cast("JsonObject", payload["project"])
    assert project["source_of_truth"] == "sqlite:local_project_metadata"
    assert project["artifact_source"] == "generated_project_envelope"
    _assert_generated_project_path_report(
        project,
        logical_project_path="projects/0007/0012-enveloped",
        physical_artifact_path="temp/pancakes/project-artifacts/0007/0012-enveloped",
        scenario_path_text=scenario_path_text,
    )
    assert project["workspace_folder_key"] == "0007"
    assert project["scenario_or_product_key"] == "0012"
    assert project["folder_reconstructable_from_sqlite"] is True
    assert project["core_business_state_written"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False

    connection = sqlite3.connect(tmp_path / "src" / "data" / "pancakes.sqlite")
    try:
        row = cast(
            "tuple[object, ...] | None",
            connection.execute(
                """
                SELECT
                  project_id,
                  project_kind,
                  workspace_folder_key,
                  scenario_or_product_key,
                  artifact_envelope_path,
                  scenario_artifact_path,
                  source_kind,
                  valid_to
                FROM local_project_metadata
                WHERE project_id = ?
                """,
                ("enveloped",),
            ).fetchone(),
        )
    finally:
        connection.close()

    assert row == (
        "enveloped ",
        "local_scenario_project ",
        "0007 ",
        "0012 ",
        "temp/pancakes/project-artifacts/0007/0012-enveloped",
        scenario_path_text,
        "mcp:project.create",
        None,
    )

    view = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "enveloped", "surface": "overview"},
        repo_root=tmp_path,
    )
    assert view.ok, view
    assert view.payload["source_path"] == scenario_path_text
    viewed_project = cast("JsonObject", view.payload["project"])
    assert viewed_project["source_of_truth"] == "sqlite:local_project_metadata"
    _assert_generated_project_path_report(
        viewed_project,
        logical_project_path="projects/0007/0012-enveloped",
        physical_artifact_path="temp/pancakes/project-artifacts/0007/0012-enveloped",
        scenario_path_text=scenario_path_text,
    )

    search = execute_mcp_tool(
        tool_name="project.search", arguments={}, repo_root=tmp_path
    )
    assert search.ok, search
    rows = cast("tuple[JsonObject, ...]", search.payload["local_projects"])
    assert rows[0]["project_id"] == "enveloped"
    assert rows[0]["source_of_truth"] == "sqlite:local_project_metadata"
    assert rows[0]["workspace_folder_key"] == "0007"
    assert rows[0]["scenario_path"] == scenario_path_text
    _assert_generated_project_path_report(
        rows[0],
        logical_project_path="projects/0007/0012-enveloped",
        physical_artifact_path="temp/pancakes/project-artifacts/0007/0012-enveloped",
        scenario_path_text=scenario_path_text,
    )


def test_project_create_default_keys_avoid_legacy_local_demo_projects_folder(
    tmp_path: Path,
) -> None:
    """Default IDE smoke projects use generated state instead of.

    projects/local-demo.
    """
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "smoke ",
            "name": "Smoke",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-smoke"
        / "scenario.json"
    )
    scenario_path_text = (
        "temp/pancakes/project-artifacts/local-demo/0001-smoke/scenario.json"
    )
    assert scenario_path.is_file()
    assert not (tmp_path / "projects" / "local-demo").exists()
    payload = result.payload
    project = cast("JsonObject", payload["project"])
    assert project["scenario_path"] == scenario_path_text
    _assert_generated_project_path_report(
        project,
        logical_project_path="projects/local-demo/0001-smoke",
        physical_artifact_path="temp/pancakes/project-artifacts/local-demo/0001-smoke",
        scenario_path_text=scenario_path_text,
    )
    storage_model = cast("JsonObject", payload["storage_model"])
    assert str(storage_model["artifact_folder_policy"]).startswith(
        "temp/pancakes/project-artifacts/"
    )


def test_project_search_reports_legacy_artifact_migration_plan(
    tmp_path: Path,
) -> None:
    """Legacy repo-local project artifacts stay readable but get a cleanup.

    plan.
    """
    _write_stress_project(tmp_path)

    search = execute_mcp_tool(
        tool_name="project.search",
        arguments={"query": "stress"},
        repo_root=tmp_path,
    )
    view = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "stress", "surface": "overview"},
        repo_root=tmp_path,
    )

    assert search.ok, search
    assert view.ok, view
    rows = cast("tuple[JsonObject, ...]", search.payload["local_projects"])
    row = next(project for project in rows if project["project_id"] == "stress")
    assert row["artifact_status"] == "legacy_folder_without_sqlite_metadata"
    assert row["artifact_source"] == "legacy_project_json"
    _assert_legacy_project_path_report(row, project_id="stress")
    project = cast("JsonObject", view.payload["project"])
    assert project["artifact_status"] == "legacy_folder_without_sqlite_metadata"
    _assert_legacy_project_path_report(project, project_id="stress")


def test_project_verify_resolves_nested_legacy_artifact_project_id(
    tmp_path: Path,
) -> None:
    """Nested legacy project artifacts found by search can be verified by.

    project_id.
    """
    project_id = "catalog-ide-real-use-smoke-20260524"
    scenario_path = (
        tmp_path
        / "projects"
        / "local-demo"
        / "0001-catalog-ide-real-use-smoke-20260524"
        / "scenario.json"
    )
    scenario_path.parent.mkdir(parents=True)
    scenario: JsonObject = {
        "name": "Catalog IDE smoke",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": "{{runtime.webhook.catalog_smoke}}"},
            }
        ],
        "metadata": {"project_id": project_id},
    }
    _ = scenario_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    search = execute_mcp_tool(
        tool_name="project.search",
        arguments={"query": project_id},
        repo_root=tmp_path,
    )
    verify = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": project_id,
            "profile": "local_structure ",
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert search.ok, search
    assert verify.ok, verify
    rows = cast("tuple[JsonObject, ...]", search.payload["local_projects"])
    assert rows[0]["scenario_path"] == (
        "projects/local-demo/0001-catalog-ide-real-use-smoke-20260524/scenario.json"
    )
    assert rows[0]["artifact_policy_status"] == "legacy_repo_project_artifact"
    assert verify.payload["status"] == "ok"
    assert verify.payload["project_id"] == project_id
    project = cast("JsonObject", verify.payload["project"])
    assert project["scenario_path"] == rows[0]["scenario_path"]
    assert project["artifact_status"] == "legacy_folder_without_sqlite_metadata"
    assert project["source_of_truth"] == "local_project_scenario"


def test_project_draft_stage_to_project_create_pipeline_covers_google_email(
    tmp_path: Path,
) -> None:
    """Scenario summaries stage a scrubbed local draft before project.create.

    import.
    """
    summary = "Create webhook, datastore, Slack, and Google Email handling."
    preview = execute_mcp_tool(
        tool_name="project.draft.stage",
        arguments={
            "project_id": "staged-google-email",
            "scenario_summary": summary,
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert preview.ok, preview
    preview_payload = preview.payload
    assert preview_payload["status"] == "dry_run"
    assert (
        preview_payload["permission_posture"]
        == "local_dry_run_no_write_no_approval"
    )
    assert preview_payload["writes_performed"] is False
    assert preview_payload["write_actions"] == []
    assert preview_payload["scenario_summary_returned"] is False
    scan_status_key = "draft_" + "secret" + "_scan_status"
    assert preview_payload[scan_status_key] == "passed"
    assert preview_payload["intent_coverage_status"] == "covered"
    assert "google-email:ActionSendEmail" in cast(
        "tuple[str, ...]",
        preview_payload["selected_modules"],
    )
    staged_path_text = str(preview_payload["staged_draft_path"])
    assert not (tmp_path / staged_path_text).exists()

    staged = execute_mcp_tool(
        tool_name="project.draft.stage",
        arguments={
            "project_id": "staged-google-email",
            "scenario_summary": summary,
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    assert staged.ok, staged
    staged_payload = staged.payload
    assert staged_payload["status"] == "staged"
    assert staged_payload["writes_performed"] is True
    assert staged_payload["write_actions"] == ["write_staged_draft"]
    assert (tmp_path / str(staged_payload["staged_draft_path"])).exists()

    created = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "staged-google-email",
            "staged_draft_path": staged_payload["staged_draft_path"],
            "staged_draft_sha256": staged_payload["staged_draft_sha256"],
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    viewed = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "staged-google-email ",
            "surface": "modules ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert created.ok, created
    assert viewed.ok, viewed
    assert created.payload["creation_mode"] == "from_make_blueprint"
    assert_no_secret_or_credential_values(preview_payload)
    assert_no_secret_or_credential_values(staged_payload)
    assert_no_secret_or_credential_values(created.payload)
    assert_safety_flags_false(preview_payload)
    assert_safety_flags_false(staged_payload)
    assert_safety_flags_false(created.payload)
    assert "google-email:ActionSendEmail" in json.dumps(
        viewed.payload, sort_keys=True
    )


def test_project_draft_stage_blocks_prompt_triggering_values_without_writing(
    tmp_path: Path,
) -> None:
    """Staged-draft intake rejects literal private values before a file.

    exists.
    """
    result = execute_mcp_tool(
        tool_name="project.draft.stage",
        arguments={
            "project_id": "unsafe-stage",
            "scenario_summary": (
                "Create a local draft that posts to https://example.invalid "
                "with "
                "Authorization Bearer sk_test_secret_like_123456."
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "blocked"
    assert payload["blocked_surface"] == "make_import"
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    scan_status_key = "draft_" + "secret" + "_scan_status"
    assert payload[scan_status_key] == "blocked"
    assert cast("int", payload["secret_like_finding_count"]) >= 1
    assert cast("int", payload["prompt_triggering_literal_count"]) >= 1
    assert_no_secret_or_credential_values(payload)
    assert_safety_flags_false(payload)
    assert not (
        tmp_path / "temp" / "pancakes" / "project-intake" / "unsafe-stage.json"
    ).exists()


def test_project_draft_import_to_project_create_pipeline_imports_local_artifact(
    tmp_path: Path,
) -> None:
    """Existing local JSON artifacts are scrub-gated before project.create.

    import.
    """
    source_path = _write_staged_draft(
        tmp_path,
        file_name="uploads/representative-import.json",
        payload=_representative_make_blueprint(),
    )
    preview = execute_mcp_tool(
        tool_name="project.draft.import",
        arguments={
            "project_id": "artifact-stage",
            "source_artifact_path": source_path,
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert preview.ok, preview
    preview_payload = preview.payload
    assert preview_payload["status"] == "dry_run"
    assert (
        preview_payload["permission_posture"]
        == "local_dry_run_no_write_no_approval"
    )
    assert preview_payload["writes_performed"] is False
    assert preview_payload["write_actions"] == []
    assert preview_payload["source_artifact_json_returned"] is False
    scan_status_key = "draft_" + "secret" + "_scan_status"
    assert preview_payload[scan_status_key] == "passed"
    assert_no_secret_or_credential_values(preview_payload)

    staged = execute_mcp_tool(
        tool_name="project.draft.import",
        arguments={
            "project_id": "artifact-stage",
            "source_artifact_path": source_path,
            "source_artifact_sha256": preview_payload["source_artifact_sha256"],
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    assert staged.ok, staged
    staged_payload = staged.payload
    assert staged_payload["status"] == "staged"
    assert staged_payload["writes_performed"] is True
    assert staged_payload["write_actions"] == ["write_staged_draft"]

    created = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "artifact-stage",
            "staged_draft_path": staged_payload["staged_draft_path"],
            "staged_draft_sha256": staged_payload["staged_draft_sha256"],
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert created.ok, created
    assert created.payload["creation_mode"] == "from_make_blueprint"
    assert created.payload["source_blueprint_role"] == "import_evidence_only"
    assert_no_secret_or_credential_values(staged_payload)
    assert_no_secret_or_credential_values(created.payload)
    assert_safety_flags_false(staged_payload)
    assert_safety_flags_false(created.payload)


def test_project_draft_import_missing_artifact_returns_safe_structured_blocker(
    tmp_path: Path,
) -> None:
    """Missing local import artifacts return a safe relative path, never a raw.

    OS.

    path.
    """
    missing_path = "temp/pancakes/project-intake/uploads/missing-import.json"
    absolute_missing_path = tmp_path / missing_path

    for source_argument in (missing_path, str(absolute_missing_path)):
        result = execute_mcp_tool(
            tool_name="project.draft.import",
            arguments={
                "project_id": "missing-artifact",
                "source_artifact_path": source_argument,
                "dry_run": False,
            },
            repo_root=tmp_path,
        )

        assert result.ok, result
        payload = result.payload
        rendered = json.dumps(payload, sort_keys=True)
        assert payload["status"] == "blocked"
        assert payload["blocker_code"] == "source_artifact_not_found"
        assert payload["safe_relative_path"] == missing_path
        assert payload["source_artifact_path"] == missing_path
        assert payload["writes_performed"] is False
        assert payload["write_actions"] == []
        assert payload["source_artifact_json_returned"] is False
        assert str(tmp_path) not in rendered
        assert str(tmp_path).replace("\\", "/") not in rendered
        assert_safety_flags_false(payload)
    assert not (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-intake"
        / "missing-artifact.json"
    ).exists()


def test_project_draft_import_invalid_json_returns_safe_structured_blocker(
    tmp_path: Path,
) -> None:
    """Invalid local import artifacts do not leak raw absolute source paths."""
    safe_path = "temp/pancakes/project-intake/uploads/invalid-import.json"
    absolute_path = tmp_path / safe_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    _ = absolute_path.write_text("[]\n", encoding="utf-8")

    result = execute_mcp_tool(
        tool_name="project.draft.import",
        arguments={
            "project_id": "invalid-artifact",
            "source_artifact_path": str(absolute_path),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["status"] == "blocked"
    assert payload["blocker_code"] == "source_artifact_invalid_json"
    assert payload["safe_relative_path"] == safe_path
    assert payload["source_artifact_path"] == safe_path
    assert payload["source_artifact_exists"] is True
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["source_artifact_json_returned"] is False
    assert str(tmp_path) not in rendered
    assert str(tmp_path).replace("\\", "/") not in rendered
    assert_safety_flags_false(payload)
    assert not (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-intake"
        / "invalid-artifact.json"
    ).exists()


def test_project_draft_import_blocks_secret_like_artifact_without_writing(
    tmp_path: Path,
) -> None:
    """Local JSON artifacts with secret-like values never become staged.

    drafts.
    """
    source_path = _write_staged_draft(
        tmp_path,
        file_name="uploads/secret-source.json",
        payload=_http_secret_like_make_blueprint(),
    )
    result = execute_mcp_tool(
        tool_name="project.draft.import",
        arguments={
            "project_id": "artifact-secret-block",
            "source_artifact_path": source_path,
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "blocked"
    assert payload["blocked_surface"] == "make_import"
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["source_artifact_json_returned"] is False
    scan_status_key = "draft_" + "secret" + "_scan_status"
    assert payload[scan_status_key] == "blocked"
    assert cast("int", payload["secret_like_finding_count"]) >= 1
    assert_no_secret_or_credential_values(payload)
    assert_safety_flags_false(payload)
    assert not (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-intake"
        / "artifact-secret-block.json"
    ).exists()


def test_project_draft_stage_from_summary_20333670(
    tmp_path: Path,
) -> None:
    """A staged workflow summary becomes a local AST that project tools can.

    inspect.
    """
    result = _create_project_from_summary(
        tmp_path,
        project_id="lead-alert",
        name="Lead Alert",
        summary=(
            "Capture website leads, store them, and alert the team in Slack."
        ),
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "created"
    assert payload["creation_mode"] == "from_make_blueprint"
    assert payload["ast_source_of_truth"] == "local_scenario_json"
    assert payload["customer_deliverable"] == "make_blueprint_json"
    assert payload["source_blueprint_role"] == "import_evidence_only"
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False

    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-lead-alert"
        / "scenario.json"
    )
    scenario = cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )
    _assert_lead_alert_generated_scenario(scenario)

    modules = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "lead-alert ",
            "surface": "modules ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    links = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "lead-alert ",
            "surface": "links ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    notes = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "lead-alert ",
            "surface": "notes ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    verify = execute_mcp_tool(
        tool_name="project.verify",
        arguments={"project_id": "lead-alert", "profile": "import_test"},
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "lead-alert ",
            "action": "preview ",
            "output_mode": "debug",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )

    assert modules.ok, modules
    assert links.ok, links
    assert notes.ok, notes
    assert verify.ok, verify
    assert preview.ok, preview
    assert modules.payload["module_count"] == 4
    assert links.payload["link_count"] == 3
    notes_summary = cast("JsonObject", notes.payload["scenario_notes_summary"])
    assert notes_summary["missing_module_note_count"] == 0
    assert notes_summary["missing_connection_note_count"] == 0
    assert verify.payload["make_import_validation_status"] == "ready"
    _assert_lead_alert_make_projection(preview.payload)
    assert (
        "report" not in json.dumps(preview.payload, sort_keys=True).casefold()
    )


def test_project_verify_local_linter_smoke_references_generated_ast_fields(
    tmp_path: Path,
) -> None:
    """Local verification exposes actionable linter smoke evidence from the.

    AST.
    """
    create = _create_project_from_summary(
        tmp_path,
        project_id="lintable",
        summary="Capture support requests, store them, and alert Slack.",
    )
    assert create.ok, create

    reports = {
        profile: execute_mcp_tool(
            tool_name="project.verify",
            arguments={
                "project_id": "lintable",
                "profile": profile,
                "output_mode": "full",
            },
            repo_root=tmp_path,
        )
        for profile in ("local_structure", "import_test", "handoff_test")
    }

    for report in reports.values():
        assert report.ok, report
        assert "Traceback" not in json.dumps(report.payload, sort_keys=True)
        assert report.payload["provider_api_call"] is False
        assert report.payload["live_make_called"] is False

    local_structure = reports["local_structure"].payload
    assert local_structure["structural_validation_status"] == "valid"
    assert (
        local_structure["local_linter_status"]
        == "passed_with_advisory_findings"
    )
    findings = cast(
        "tuple[JsonObject, ...]", local_structure["local_linter_findings"]
    )
    surfaces = {str(finding["surface"]) for finding in findings}
    assert {"nodes", "filters", "notes", "placeholders"} <= surfaces
    assert any(
        finding["surface"] == "nodes" and finding.get("node_id") == "1"
        for finding in findings
    )
    assert any(
        finding["surface"] == "filters" and "route_index" in finding
        for finding in findings
    )
    assert any(
        finding["surface"] == "notes" and finding.get("note_kind") == "module"
        for finding in findings
    )
    assert any(
        finding["surface"] == "placeholders" and "field_path" in finding
        for finding in findings
    )
    assert (
        reports["import_test"].payload["make_import_validation_status"]
        == "ready"
    )
    assert (
        reports["handoff_test"].payload["client_handoff_validation_status"]
        == "ready"
    )


def test_project_create_imports_make_blueprint_as_ast_ssot(
    tmp_path: Path,
) -> None:
    """Uploaded Make blueprint JSON becomes editable AST with bounded source.

    evidence.
    """
    blueprint = _representative_make_blueprint()
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "imported-blueprint",
            "staged_draft_path": _write_staged_draft(
                tmp_path,
                file_name="representative-import.json",
                payload=blueprint,
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "created"
    assert payload["creation_mode"] == "from_make_blueprint"
    assert payload["ast_source_of_truth"] == "local_scenario_json"
    assert payload["source_blueprint_role"] == "import_evidence_only"
    assert payload["source_blueprint_evidence_stored"] is True
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False

    envelope = (
        tmp_path / "temp" / "pancakes" / "project-artifacts" / "local-demo"
    )
    scenario_path = envelope / "0001-imported-blueprint" / "scenario.json"
    evidence_path = (
        envelope
        / "0001-imported-blueprint"
        / "artifacts"
        / "imported-make-blueprint.evidence.json"
    )
    scenario = cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )
    evidence = cast(
        "JsonObject", json.loads(evidence_path.read_text(encoding="utf-8"))
    )
    metadata = cast("JsonObject", scenario["metadata"])
    creation = cast("JsonObject", metadata["creation"])
    import_evidence = cast("JsonObject", metadata["import_evidence"])
    imported_metadata = cast(
        "JsonObject", metadata["imported_blueprint_metadata"]
    )
    flow = cast("list[JsonObject]", scenario["flow"])
    router = flow[1]
    route = cast("list[JsonObject]", router["routes"])[0]
    route_flow = cast("list[JsonObject]", route["flow"])
    error_handlers = cast("list[JsonObject]", flow[2]["onerror"])

    assert creation["mode"] == "from_make_blueprint"
    assert import_evidence["editable_authority"] == "scenario.json"
    assert imported_metadata["layout"] == "uploaded-client-layout"
    assert scenario["datastores"] == blueprint["datastores"]
    assert scenario["dataStructures"] == blueprint["dataStructures"]
    assert scenario["webhooks"] == blueprint["webhooks"]
    assert scenario["schedule"] == blueprint["schedule"]
    assert scenario["sample_payloads"] == blueprint["sample_payloads"]
    assert cast("JsonObject", route["filter"])["name"] == "VIP lead"
    assert route_flow[0]["module"] == "datastore:AddRecord"
    assert error_handlers[0]["module"] == "email:ActionSendEmail"
    assert (
        cast("JsonObject", evidence["source_blueprint_json"])["flow"]
        == blueprint["flow"]
    )

    modules = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "imported-blueprint ",
            "surface": "modules ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    verify = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "imported-blueprint ",
            "profile": "import_test",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={"project_id": "imported-blueprint", "action": "preview"},
        repo_root=tmp_path,
    )

    assert modules.ok, modules
    assert verify.ok, verify
    assert preview.ok, preview
    assert modules.payload["module_count"] == 4
    assert verify.payload["make_import_validation_status"] == "ready"
    assert preview.payload["artifact_format"] == "make_blueprint_json"
    assert "Traceback" not in json.dumps(preview.payload, sort_keys=True)


def test_project_create_rejects_raw_draft_json_arguments(
    tmp_path: Path,
) -> None:
    """project.create requires staged local draft paths instead of raw JSON.

    arguments.
    """
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "raw-draft-rejected",
            "blueprint_json": {"flow": []},
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "no longer accepts raw blueprint JSON" in result.error
    assert not (tmp_path / "projects" / "raw-draft-rejected").exists()


def test_project_create_rejects_legacy_blueprint_artifact_aliases(
    tmp_path: Path,
) -> None:
    """project.create accepts only the sanitized staged draft path contract."""
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "legacy-artifact-alias-rejected ",
            "blueprint_artifact_path": (
                "temp/pancakes/project-intake/draft.json"
            ),
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "legacy blueprint artifact aliases are not accepted" in result.error
    assert not (
        tmp_path / "projects" / "legacy-artifact-alias-rejected"
    ).exists()


def test_project_create_rejects_legacy_summary_arguments(
    tmp_path: Path,
) -> None:
    """project.create no longer accepts free-text summary arguments."""
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "raw-intent-rejected ",
            "intent": "Capture support requests, store them, and alert Slack.",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "project.create no longer accepts scenario summaries" in result.error
    assert not (tmp_path / "projects" / "raw-intent-rejected").exists()


def test_project_create_covers_google_email_intent_without_silent_omission(
    tmp_path: Path,
) -> None:
    """Summary staging includes Google Email when requested and reports.

    coverage.
    """
    created = _create_project_from_summary(
        tmp_path,
        project_id="google-email-intent",
        summary="Create webhook, datastore, Slack, and Google Email handling.",
    )
    viewed = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "google-email-intent ",
            "surface": "modules ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    handoff = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": "google-email-intent ",
            "profile": "handoff_test",
        },
        repo_root=tmp_path,
    )

    assert created.ok, created
    assert viewed.ok, viewed
    assert handoff.ok, handoff
    serialized_modules = json.dumps(viewed.payload, sort_keys=True)
    assert "google-email:ActionSendEmail" in serialized_modules
    assert handoff.payload["client_handoff_validation_status"] == "ready"

    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-google-email-intent"
        / "scenario.json"
    )
    scenario = cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )
    metadata = cast("JsonObject", scenario["metadata"])
    imported_metadata = cast(
        "JsonObject", metadata["imported_blueprint_metadata"]
    )
    catalog_assist = cast("JsonObject", imported_metadata["catalog_assist"])
    assert catalog_assist["intent_coverage_status"] == "covered"
    assert catalog_assist["intent_coverage_gap_count"] == 0
    assert "google_email" in cast(
        "tuple[str, ...]", catalog_assist["requested_capabilities"]
    )
    assert "google-email:ActionSendEmail" in cast(
        "tuple[str, ...]",
        catalog_assist["selected_modules"],
    )


def test_project_create_blocks_secret_like_88b63ce7(
    tmp_path: Path,
) -> None:
    """Secret-like staged blueprints fail closed before scenario or evidence.

    writes.
    """
    blueprint = _http_secret_like_make_blueprint()
    artifact_path = (
        tmp_path / "temp" / "pancakes" / "project-intake" / "secret-import.json"
    )
    artifact_path.parent.mkdir(parents=True)
    _ = artifact_path.write_text(
        f"{json.dumps(blueprint, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    arguments: JsonObject = {
        "project_id": "audit-import-blueprint-secret-dry-run ",
        "name": "Audit Import Blueprint Secret Dry Run ",
        "staged_draft_path": "temp/pancakes/project-intake/secret-import.json",
        "dry_run": False,
    }

    result = execute_mcp_tool(
        tool_name="project.create",
        arguments=arguments,
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert "sk_test_secret_like" not in json.dumps(arguments, sort_keys=True)
    assert "Bearer " not in json.dumps(arguments, sort_keys=True)
    assert_no_secret_or_credential_values(result.payload)
    assert_safety_flags_false(result.payload)
    assert result.payload["status"] == "blocked"
    assert result.payload["creation_mode"] == "from_make_blueprint"
    assert result.payload["blocked_surface"] == "make_import"
    assert result.payload["secret_like_finding_count"] == 1
    assert result.payload["writes_performed"] is False
    assert result.payload["source_blueprint_evidence_stored"] is False

    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-audit-import-blueprint-secret-dry-run"
        / "scenario.json"
    )
    evidence_path = (
        scenario_path.parent
        / "artifacts"
        / "imported-make-blueprint.evidence.json"
    )
    assert not scenario_path.exists()
    assert not evidence_path.exists()


def test_project_create_import_quarantines_unknowns_without_loss(
    tmp_path: Path,
) -> None:
    """Unknown imported structures stay in the AST and get typed review.

    records.
    """
    blueprint = _representative_make_blueprint_with_unknowns()
    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "unknown-import",
            "staged_draft_path": _write_staged_draft(
                tmp_path,
                file_name="unknown-import.json",
                payload=blueprint,
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "created"
    assert cast("int", payload["import_quarantine_record_count"]) >= 2
    assert cast("int", payload["missing_evidence_record_count"]) >= 1
    assert payload["human_review_requested"] is True
    assert payload["human_review_surface"] == "typed_import_quarantine"

    envelope = (
        tmp_path / "temp" / "pancakes" / "project-artifacts" / "local-demo"
    )
    scenario_path = envelope / "0001-unknown-import" / "scenario.json"
    evidence_path = (
        envelope
        / "0001-unknown-import"
        / "artifacts"
        / "imported-make-blueprint.evidence.json"
    )
    scenario = cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )
    evidence = cast(
        "JsonObject", json.loads(evidence_path.read_text(encoding="utf-8"))
    )
    metadata = cast("JsonObject", scenario["metadata"])
    quarantine = cast("list[JsonObject]", metadata["import_quarantine_records"])
    missing = cast("list[JsonObject]", metadata["missing_evidence_records"])
    flow = cast("list[JsonObject]", scenario["flow"])
    unknown = flow[-1]

    assert scenario["x-client-vendor-block"] == {"preserve": True}
    assert unknown["module"] == "acme:UnsupportedAction"
    assert unknown["customUnsupported"] == {"keep": True}
    assert {record["record_kind"] for record in quarantine} == {
        "import_quarantine"
    }
    assert any(
        record["field"] == "x-client-vendor-block" for record in quarantine
    )
    assert any(record["field"] == "customUnsupported" for record in quarantine)
    assert any(
        record["field"] == "module"
        and record["value"] == "acme:UnsupportedAction"
        for record in quarantine
    )
    assert missing[0]["record_kind"] == "missing_evidence"
    assert missing[0]["evidence_kind"] == "module_projector"
    evidence_quarantine = cast(
        "list[JsonObject]", evidence["import_quarantine_records"]
    )
    evidence_missing = cast(
        "list[JsonObject]", evidence["missing_evidence_records"]
    )
    assert evidence_quarantine == quarantine
    assert evidence_missing == missing

    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={"project_id": "unknown-import", "action": "preview"},
        repo_root=tmp_path,
    )
    assert preview.ok, preview
    assert (
        cast("int", preview.payload["pass_through_unknown_module_count"]) >= 1
    )
    assert preview.payload["provider_api_call"] is False
    assert preview.payload["live_make_called"] is False


def test_project_make_roundtrip_validates_imported_ast_without_known_loss(
    tmp_path: Path,
) -> None:
    """Roundtrip export compares source blueprint, AST, and regenerated.

    blueprint.
    """
    blueprint = _representative_make_blueprint_with_unknowns()
    create = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "roundtrip-import",
            "staged_draft_path": _write_staged_draft(
                tmp_path,
                file_name="roundtrip-import.json",
                payload=blueprint,
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    assert create.ok, create

    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "roundtrip-import ",
            "action": "preview ",
            "output_mode": "full",
            "include_blueprint_json": True,
        },
        repo_root=tmp_path,
    )

    assert preview.ok, preview
    payload = preview.payload
    assert payload["roundtrip_validation_status"] == "passed"
    assert (
        payload["roundtrip_semantic_equivalence_status"]
        == "semantically_equivalent"
    )
    assert payload["roundtrip_importability_status"] == "importable"
    assert payload["known_node_count"] == 4
    assert payload["lost_known_node_count"] == 0
    assert payload["known_field_loss_count"] == 0
    assert payload["quarantined_unknown_node_count"] == 2
    assert payload["quarantined_unknowns_traceable"] is True

    artifact = cast("JsonObject", payload["artifact_json"])
    regenerated = cast("JsonObject", artifact["scenario"])
    flow = cast("list[JsonObject]", regenerated["flow"])
    router = flow[1]
    route = cast("list[JsonObject]", router["routes"])[0]
    route_flow = cast("list[JsonObject]", route["flow"])
    unknown = flow[-1]

    assert flow[0]["module"] == "gateway:CustomWebHook"
    assert router["module"] == "builtin:BasicRouter"
    assert route_flow[0]["module"] == "datastore:AddRecord"
    assert flow[2]["module"] == "slack:CreateMessage"
    assert unknown["module"] == "acme:UnsupportedAction"
    assert unknown["customUnsupported"] == {"keep": True}
    assert regenerated["x-client-vendor-block"] == {"preserve": True}
    assert regenerated["datastores"] == blueprint["datastores"]
    assert regenerated["dataStructures"] == blueprint["dataStructures"]
    assert regenerated["webhooks"] == blueprint["webhooks"]


def test_project_create_permission_denied_returns_structured_ide_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """project.create reports path permission failures as MCP payload fields."""
    denied_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "0007"
        / "0012-denied"
    ).resolve()
    original_mkdir = Path.mkdir

    def deny_project_envelope_mkdir(
        path: Path,
        mode: int = 0o777,
        *,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path.resolve() == denied_path:
            msg = "Access is denied."
            raise PermissionError(msg)
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", deny_project_envelope_mkdir)

    result = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "denied ",
            "name": "Denied ",
            "workspace_number": "0007 ",
            "scenario_number": "0012",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "project_create_permission_denied"
    assert (
        payload["expected_path"]
        == "temp/pancakes/project-artifacts/0007/0012-denied/scenario.json"
    )
    assert str(tmp_path) not in str(payload["expected_path"])
    assert not Path(str(payload["expected_path"])).is_absolute()
    assert payload["next_action"] == "project.create"
    assert (
        payload["required_prerequisite"] == "project workspace write permission"
    )
    assert payload["diagnostic"] == "PermissionError"
    assert payload["created"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False


def test_project_read_tools_return_structured_errors_for_missing_project(
    tmp_path: Path,
) -> None:
    """IDE read tools never return raw missing scenario.json filesystem.

    errors.
    """
    for tool_name in (
        "project.health ",
        "project.view ",
        "project.verify ",
        "project.make",
    ):
        result = execute_mcp_tool(
            tool_name=tool_name,
            arguments={"project_id": "missing-project"},
            repo_root=tmp_path,
        )

        assert result.ok, result
        assert result.error is None
        payload = result.payload
        assert payload["status"] == "blocked"
        assert payload["error_code"] == "project_not_found"
        assert payload["tool"] == tool_name
        assert (
            payload["expected_path"] == "projects/missing-project/scenario.json"
        )
        assert payload["next_action"] == "project.create"
        assert payload["scenario_file_exists"] is False
        assert payload["provider_api_call"] is False
        assert payload["live_make_called"] is False


def test_project_read_tools_return_structured_errors_for_missing_scenario_file(
    tmp_path: Path,
) -> None:
    """SQLite metadata without scenario.json is reported as a repairable IDE.

    state.
    """
    create = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "enveloped ",
            "name": "Enveloped ",
            "workspace_number": "0007 ",
            "scenario_number": "0012",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    assert create.ok, create
    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "0007"
        / "0012-enveloped"
        / "scenario.json"
    )
    scenario_path.unlink()

    for tool_name in (
        "project.health ",
        "project.view ",
        "project.verify ",
        "project.make",
    ):
        result = execute_mcp_tool(
            tool_name=tool_name,
            arguments={"project_id": "enveloped"},
            repo_root=tmp_path,
        )

        assert result.ok, result
        assert result.error is None
        payload = result.payload
        serialized_payload = json.dumps(payload, sort_keys=True)
        assert "Traceback" not in serialized_payload
        assert payload["status"] == "blocked"
        assert payload["error_code"] == "scenario_file_missing"
        assert payload["tool"] == tool_name
        assert (
            payload["expected_path"]
            == "temp/pancakes/project-artifacts/0007/0012-enveloped/scenario.json"
        )
        assert payload["local_project_exists"] is True
        project = cast("JsonObject", payload["project"])
        assert project["artifact_status"] == "sqlite_metadata_without_artifact"


def test_project_search_skips_filesystem_reread_for_sqlite_metadata_projects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SQLite-owned search rows are not reparsed during the fallback filesystem.

    sweep.
    """
    create = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "enveloped ",
            "name": "Enveloped ",
            "workspace_number": "0007 ",
            "scenario_number": "0012",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    assert create.ok, create

    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "0007"
        / "0012-enveloped"
        / "scenario.json"
    ).resolve()
    original_read_text = Path.read_text
    read_paths: list[str] = []

    def count_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if path.resolve() == scenario_path:
            read_paths.append(path.relative_to(tmp_path).as_posix())
        return original_read_text(
            path, encoding=encoding, errors=errors, newline=newline
        )

    monkeypatch.setattr(Path, "read_text", count_read_text)

    search = execute_mcp_tool(
        tool_name="project.search", arguments={}, repo_root=tmp_path
    )

    assert search.ok, search
    assert (
        read_paths.count(
            "temp/pancakes/project-artifacts/0007/0012-enveloped/scenario.json"
        )
        == 1
    )


def _representative_make_blueprint() -> JsonObject:
    return {
        "name": "Uploaded Lead Router",
        "metadata": {"layout": "uploaded-client-layout", "version": 1},
        "datastores": [
            {"name": "Imported Leads", "datastructure": "lead_record"}
        ],
        "dataStructures": [
            {
                "name": "lead_record",
                "fields": [
                    {"name": "email", "type": "email"},
                    {"name": "priority", "type": "text"},
                ],
            }
        ],
        "webhooks": [
            {
                "name": "Lead intake ",
                "hook": "{{runtime.webhook.imported_leads}}",
            }
        ],
        "layout": {"1": {"x": 0, "y": 0}, "2": {"x": 240, "y": 0}},
        "schedule": {"type": "indefinitely", "interval": 15},
        "sample_payloads": {
            "lead": {"email": "lead@example.invalid", "priority": "vip"}
        },
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": "{{runtime.webhook.imported_leads}}"},
                "mapper": {"sample_payload": {"email": "lead@example.invalid"}},
            },
            {
                "id": 2,
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "name": "VIP lead ",
                            "condition": "{{1.priority}} = vip",
                        },
                        "flow": [
                            {
                                "id": 3,
                                "module": "datastore:AddRecord",
                                "parameters": {
                                    "datastore": "{{runtime.datastore.imported_leads}}"
                                },
                                "mapper": {
                                    "data": {
                                        "email": "{{1.email}}",
                                        "priority": "{{1.priority}}",
                                    },
                                    "key": "{{1.email}}",
                                    "overwrite": False,
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "id": 4,
                "module": "slack:ActionCreateMessage",
                "parameters": {
                    "account": "{{runtime.connection.slack_ops}}",
                    "channel": "{{runtime.slack.channel.ops_alerts}}",
                },
                "mapper": {"text": "Imported lead {{1.email}}"},
                "onerror": [
                    {
                        "id": 5,
                        "module": "email:ActionSendEmail",
                        "parameters": {"to": "{{runtime.email.ops_address}}"},
                        "mapper": {"subject": "Slack notification failed"},
                    }
                ],
            },
        ],
    }


def _representative_make_blueprint_with_unknowns() -> JsonObject:
    blueprint = cast(
        "JsonObject", json.loads(json.dumps(_representative_make_blueprint()))
    )
    blueprint["x-client-vendor-block"] = {"preserve": True}
    flow = cast("list[JsonObject]", blueprint["flow"])
    flow.append(
        {
            "id": 6,
            "module": "acme:UnsupportedAction",
            "parameters": {"connection": "{{runtime.connection.acme_ops}}"},
            "mapper": {"payload": "{{1.raw_payload}}"},
            "customUnsupported": {"keep": True},
        }
    )
    return blueprint


def _http_secret_like_make_blueprint() -> JsonObject:
    api_key = "sk_test_secret_like_123456"
    return {
        "name": "Audit Import Blueprint Secret Dry Run",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "parameters": {
                    "url": "https://example.com ",
                    "method": "POST",
                    "headers": [
                        {
                            "name": "Authorization ",
                            "value": f"Bearer {api_key}",
                        }
                    ],
                },
                "mapper": {"body": '{"audit":true}'},
            }
        ],
    }


def _write_template_library(repo_root: Path) -> None:
    template_path = repo_root / "projects" / "templates" / "scenario.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Templates",
        "flow": [],
        "metadata": {"scenario": {"name": "Template"}},
    }
    _ = template_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _write_stress_project(repo_root: Path) -> None:
    project_path = repo_root / "projects" / "stress" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    routes: list[JsonObject] = [
        {
            "filter": {
                "name": f"Route {route_index}",
                "condition": f"{{{{2.route_{route_index}.accepted}}}}",
            },
            "flow": [
                {
                    "id": 1000 + route_index,
                    "module": "slack:ActionCreateMessage",
                    "parameters": {
                        "account": "{{runtime.connection.slack_ops}}",
                        "channel": "{{runtime.slack.channel.ops_alerts}}",
                    },
                }
            ],
        }
        for route_index in range(30)
    ]
    flow: list[JsonObject] = [
        {
            "id": 1,
            "module": "gateway:CustomWebHook",
            "parameters": {"hook": "{{runtime.webhook.stress_intake_hook}}"},
        },
        {"id": 2, "module": "builtin:BasicRouter", "routes": routes},
    ]
    flow.extend(
        {
            "id": offset,
            "module": "datastore:AddRecord",
            "parameters": {"datastore": "{{runtime.datastore.stress_events}}"},
            "mapper": {
                "data": {
                    "company": "{{1.company}}",
                    "email": "{{1.email}}",
                    "module_index": offset - 2,
                    "record_kind": "branch_record ",
                    "request_id": "{{1.request_id}}",
                    "route_index": 1,
                    "score": "{{1.score}}",
                },
                "key": "{{1.request_id}}",
                "overwrite": False,
            },
        }
        for offset in range(3, 273)
    )
    scenario: JsonObject = {
        "name": "Stress",
        "flow": flow,
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _write_datastore_key_project(repo_root: Path) -> None:
    project_path = repo_root / "projects" / "keyed" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Keyed",
        "flow": [
            {
                "id": 1,
                "module": "datastore:AddRecord",
                "parameters": {
                    "datastore": "{{runtime.datastore.keyed_records}}"
                },
                "mapper": {
                    "data": {
                        "company": "{{1.company}}",
                        "request_id": "{{1.request_id}}",
                    },
                    "key": "{{1.request_id}}",
                    "overwrite": False,
                },
            }
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _write_seeded_datastore_project(
    repo_root: Path,
    *,
    project_id: str,
    resource_key: str,
    seed_records: tuple[JsonObject, ...],
) -> None:
    project_path = repo_root / "projects" / project_id / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": project_id.title(),
        "flow": [
            {
                "id": 1,
                "module": "datastore:AddRecord",
                "parameters": {
                    "datastore": f"{{{{runtime.datastore.{resource_key}}}}}"
                },
                "mapper": {
                    "data": {
                        "company": "{{1.company}}",
                        "request_id": "{{1.request_id}}",
                    },
                    "key": "{{1.request_id}}",
                    "overwrite": False,
                },
            }
        ],
        "metadata": {
            "notes": [],
            "datastore_manifest": {
                "resources": [
                    {
                        "resource_key": resource_key,
                        "seed_records": list(seed_records),
                    }
                ]
            },
        },
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _write_unknown_datastore_project(repo_root: Path) -> None:
    project_path = repo_root / "projects" / "unknown-key" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: JsonObject = {
        "name": "Unknown Key",
        "flow": [
            {
                "id": 1,
                "module": "datastore:AddRecord",
                "parameters": {
                    "datastore": "{{runtime.datastore.unknown_records}}"
                },
            }
        ],
        "metadata": {"notes": []},
    }
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
