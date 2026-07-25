# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP project domain edit tool contracts.

Boundary contract:
- Owns: module, link, filter, and error-handler domain MCP tool behavior.
- Must not: expose generic JSON editors publicly, call Make.com, or write by
default.
- Allows: isolated local scenario drafts and dry-run/apply checks.
- Split when: each domain grows enough semantic validation to need its own
suite.
- Merge when: project JSON loop contracts own the same domain edit surface.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from mcp import execute_mcp_tool

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject


def test_project_module_tools_dry_run_apply_and_view_derived_links(
    tmp_path: Path,
) -> None:
    """Module domain tools replace raw JSON editing for normal topology.

    changes.
    """
    _write_domain_scenario(tmp_path)

    viewed = execute_mcp_tool(
        tool_name="project.modules.view",
        arguments={"project_id": "domain-loop"},
        repo_root=tmp_path,
    )
    dry_run = execute_mcp_tool(
        tool_name="project.modules.add",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "2",
            "route_index": 0,
            "module_json": json.dumps(
                {"id": 3, "module": "datastore:AddRecord"}
            ),
        },
        repo_root=tmp_path,
    )
    scenario_after_dry_run = _read_domain_scenario(tmp_path)
    applied = execute_mcp_tool(
        tool_name="project.modules.add",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "2",
            "route_index": 0,
            "module_json": json.dumps(
                {"id": 3, "module": "datastore:AddRecord"}
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    duplicate = execute_mcp_tool(
        tool_name="project.modules.add",
        arguments={
            "project_id": "domain-loop",
            "module_json": json.dumps(
                {"id": 3, "module": "slack:ActionCreateMessage"}
            ),
        },
        repo_root=tmp_path,
    )
    links = execute_mcp_tool(
        tool_name="project.links.view",
        arguments={"project_id": "domain-loop"},
        repo_root=tmp_path,
    )

    assert viewed.ok, f"project.modules.view failed: {viewed}"
    _assert_response_contract(
        viewed.payload, contract="project.modules.view", version=2
    )
    assert viewed.payload.get("module_count") == 2, viewed.payload
    assert "scenario" not in viewed.payload, viewed.payload

    assert dry_run.ok, f"project.modules.add dry-run failed: {dry_run}"
    _assert_response_contract(
        dry_run.payload, contract="project.modules.add", version=2
    )
    assert dry_run.payload.get("status") == "dry_run", dry_run.payload
    assert dry_run.payload.get("changed") is False, dry_run.payload
    assert dry_run.payload.get("would_change") is True, dry_run.payload
    assert _route_flow_node_ids(scenario_after_dry_run) == [], (
        scenario_after_dry_run
    )

    assert applied.ok, f"project.modules.add apply failed: {applied}"
    assert applied.payload.get("status") == "updated", applied.payload
    assert _route_flow_node_ids(_read_domain_scenario(tmp_path)) == [3]
    assert not duplicate.ok, (
        f"project.modules.add accepted duplicate node ids: {duplicate}"
    )

    assert links.ok, f"project.links.view failed: {links}"
    _assert_response_contract(
        links.payload, contract="project.links.view", version=2
    )
    link_pairs = {
        (link["source_node_id"], link["target_node_id"])
        for link in cast("tuple[JsonObject, ...]", links.payload["links"])
    }
    assert ("2", "3") in link_pairs, links.payload


def test_project_filter_and_error_handler_tools_are_confirmed_domain_edits(
    tmp_path: Path,
) -> None:
    """Filter and error-handler tools edit narrow surfaces with.

    confirmations.
    """
    _write_domain_scenario(tmp_path)

    added_filter = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
            "filter_json": json.dumps(
                {"name": "Qualified", "condition": "{{1.email}}"}
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    modified_filter = execute_mcp_tool(
        tool_name="project.filters.modify",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
            "merge_patch_json": json.dumps({"name": "Qualified Leads"}),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    rejected_filter_delete = execute_mcp_tool(
        tool_name="project.filters.delete",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    deleted_filter = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "domain-loop",
            "surface": "filters",
            "operation": "delete",
            "node_id": "2",
            "route_index": 0,
            "confirm_node_id": "2",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    added_handler = execute_mcp_tool(
        tool_name="project.error_handlers.add",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "1",
            "handler_json": json.dumps(
                {"flow": [{"id": 9, "module": "datastore:AddRecord"}]}
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    handlers = execute_mcp_tool(
        tool_name="project.error_handlers.view",
        arguments={"project_id": "domain-loop", "node_id": "1"},
        repo_root=tmp_path,
    )
    rejected_handler_delete = execute_mcp_tool(
        tool_name="project.error_handlers.delete",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "1",
            "handler_index": 0,
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    deleted_handler = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "domain-loop",
            "surface": "error_handlers",
            "operation": "delete",
            "parent_node_id": "1",
            "handler_index": 0,
            "confirm_node_id": "1",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )

    assert added_filter.ok, f"project.filters.add failed: {added_filter}"
    _assert_response_contract(
        added_filter.payload, contract="project.filters.add", version=2
    )
    assert modified_filter.ok, (
        f"project.filters.modify failed: {modified_filter}"
    )
    assert not rejected_filter_delete.ok, rejected_filter_delete
    assert deleted_filter.ok, (
        f"project.edit filter delete failed: {deleted_filter}"
    )
    route = cast(
        "JsonObject",
        cast("list[object]", _read_domain_scenario(tmp_path)["flow"])[1],
    )
    assert "filter" not in cast(
        "JsonObject", cast("list[object]", route["routes"])[0]
    )

    assert added_handler.ok, (
        f"project.error_handlers.add failed: {added_handler}"
    )
    assert handlers.ok, f"project.error_handlers.view failed: {handlers}"
    assert handlers.payload.get("error_handler_count") == 1, handlers.payload
    assert not rejected_handler_delete.ok, rejected_handler_delete
    assert deleted_handler.ok, (
        f"project.edit error-handler delete failed: {deleted_handler}"
    )
    webhook = cast(
        "JsonObject",
        cast("list[object]", _read_domain_scenario(tmp_path)["flow"])[0],
    )
    assert cast("list[object]", webhook.get("onerror", [])) == []


def test_project_filter_tools_accept_envelopes_and_keep_dry_run_read_only(
    tmp_path: Path,
) -> None:
    """Filter tools support canonical envelopes and dry-run delete without.

    writes.
    """
    _write_domain_scenario(tmp_path)

    envelope_add = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "filter_json": json.dumps(
                {
                    "node_id": "2",
                    "route_index": 0,
                    "filter": {"name": "Qualified", "condition": "{{1.email}}"},
                }
            ),
        },
        repo_root=tmp_path,
    )
    scenario_after_add_dry_run = _read_domain_scenario(tmp_path)
    applied = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "filter_json": json.dumps(
                {
                    "node_id": "2",
                    "route_index": 0,
                    "filter": {"name": "Qualified", "condition": "{{1.email}}"},
                }
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    edit_dry_run = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "domain-loop",
            "surface": "filters",
            "operation": "add",
            "target": {"node_id": "2", "route_index": 0},
            "payload_json": json.dumps(
                {"name": "Edit wrapper", "condition": "{{1.email}}"}
            ),
        },
        repo_root=tmp_path,
    )
    dry_run_delete = execute_mcp_tool(
        tool_name="project.filters.delete",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
        },
        repo_root=tmp_path,
    )
    wrong_confirm_delete = execute_mcp_tool(
        tool_name="project.filters.delete",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
            "confirm_node_id": "wrong",
        },
        repo_root=tmp_path,
    )
    scenario_after_delete_dry_run = _read_domain_scenario(tmp_path)

    assert envelope_add.ok, envelope_add
    assert envelope_add.payload["status"] == "dry_run"
    assert envelope_add.payload["would_change"] is True
    payload_shape = cast(
        "dict[str, object]", envelope_add.payload["accepted_payload_shape"]
    )
    assert payload_shape["minimal_example"] == (
        'Example: {"node_id":"2","route_index":0,'
        '"filter_json":{"name":"Qualified","condition":"{{1.email}}"}}'
    )
    assert "filter_json" in cast(
        "tuple[str, ...]", payload_shape["top_level_keys"]
    )
    dry_run_route = cast(
        "JsonObject",
        cast("list[object]", scenario_after_add_dry_run["flow"])[1],
    )
    assert "filter" not in cast(
        "JsonObject", cast("list[object]", dry_run_route["routes"])[0]
    )
    assert applied.ok, applied
    assert edit_dry_run.ok, edit_dry_run
    assert edit_dry_run.payload["wrapped_tool"] == "project.filters.add"
    assert edit_dry_run.payload["semantic_tool"] == "project.edit"
    assert edit_dry_run.payload["status"] == "dry_run"
    edit_target = cast("dict[str, object]", edit_dry_run.payload["target"])
    applied_target = cast("dict[str, object]", applied.payload["target"])
    assert edit_target["node_id"] == applied_target["node_id"] == "2"
    assert edit_target["route_index"] == applied_target["route_index"] == 0
    assert (
        edit_dry_run.payload["accepted_payload_shape"]
        == applied.payload["accepted_payload_shape"]
    )
    assert dry_run_delete.ok, dry_run_delete
    assert dry_run_delete.payload["status"] == "dry_run"
    assert dry_run_delete.payload["changed"] is False
    assert dry_run_delete.payload["would_change"] is True
    assert not wrong_confirm_delete.ok, wrong_confirm_delete
    assert wrong_confirm_delete.error is not None
    assert "confirm_node_id must match node_id" in wrong_confirm_delete.error
    route = cast(
        "JsonObject",
        cast("list[object]", scenario_after_delete_dry_run["flow"])[1],
    )
    assert "filter" in cast(
        "JsonObject", cast("list[object]", route["routes"])[0]
    )


def test_project_filter_tools_report_route_aware_errors(tmp_path: Path) -> None:
    """Filter add errors name received keys, expected keys, and a minimal.

    example.
    """
    _write_domain_scenario(tmp_path)

    missing_target = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "filter_json": json.dumps(
                {"name": "Missing target", "condition": "{{1.email}}"}
            ),
        },
        repo_root=tmp_path,
    )
    invalid_route_target = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "node_id": "1",
            "route_index": 0,
            "filter_json": json.dumps(
                {"name": "No route", "condition": "{{1.email}}"}
            ),
        },
        repo_root=tmp_path,
    )
    out_of_range_route = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 5,
            "filter_json": json.dumps(
                {"name": "Far route", "condition": "{{1.email}}"}
            ),
        },
        repo_root=tmp_path,
    )
    malformed_condition = execute_mcp_tool(
        tool_name="project.filters.add",
        arguments={
            "project_id": "domain-loop",
            "node_id": "2",
            "route_index": 0,
            "filter_json": json.dumps(
                {"name": "Broken condition", "condition": ""}
            ),
        },
        repo_root=tmp_path,
    )

    assert not missing_target.ok
    assert "missing_node_id" in str(missing_target.error)
    assert "top-level node_id or filter_json.node_id" in str(
        missing_target.error
    )
    assert (
        "received_keys=[filter_json,filter_json.condition,filter_json.name"
        in str(missing_target.error)
    )
    assert "expected_keys=[node_id,target_node_id,route_index" in str(
        missing_target.error
    )
    assert "minimal_example=Example:" in str(missing_target.error)
    assert not invalid_route_target.ok
    assert "node_has_no_routes" in str(invalid_route_target.error)
    assert "node_id 1 has no route index" in str(invalid_route_target.error)
    assert "minimal_example=Example:" in str(invalid_route_target.error)
    assert not out_of_range_route.ok
    assert "route_index_out_of_range" in str(out_of_range_route.error)
    assert "route_count=1" in str(out_of_range_route.error)
    assert not malformed_condition.ok
    assert "malformed_filter_condition" in str(malformed_condition.error)
    assert "received_keys=[condition,name]" in str(malformed_condition.error)


def test_project_error_handler_tools_accept_61a5f275(
    tmp_path: Path,
) -> None:
    """Error-handler tools support canonical envelopes and no-write dry runs."""
    _write_domain_scenario(tmp_path)

    retry_handler_dry_run = execute_mcp_tool(
        tool_name="project.error_handlers.add",
        arguments={
            "project_id": "domain-loop",
            "handler_json": json.dumps(
                {
                    "parent_node_id": "1",
                    "handler": {
                        "directive": "retry",
                        "flow": [{"id": 9, "module": "datastore:AddRecord"}],
                    },
                }
            ),
        },
        repo_root=tmp_path,
    )
    scenario_after_add_dry_run = _read_domain_scenario(tmp_path)
    missing_parent = execute_mcp_tool(
        tool_name="project.error_handlers.add",
        arguments={
            "project_id": "domain-loop",
            "handler_json": json.dumps({"handler": {"flow": []}}),
        },
        repo_root=tmp_path,
    )
    unknown_parent = execute_mcp_tool(
        tool_name="project.error_handlers.add",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "999",
            "handler_json": json.dumps(
                {
                    "directive": "retry",
                    "flow": [{"id": 9, "module": "datastore:AddRecord"}],
                }
            ),
        },
        repo_root=tmp_path,
    )
    applied_retry_handler = execute_mcp_tool(
        tool_name="project.error_handlers.add",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "1",
            "handler_json": json.dumps(
                {
                    "directive": "retry",
                    "flow": [{"id": 9, "module": "datastore:AddRecord"}],
                }
            ),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    resume_patch_dry_run = execute_mcp_tool(
        tool_name="project.error_handlers.modify",
        arguments={
            "project_id": "domain-loop",
            "patch_json": json.dumps(
                {
                    "parent_node_id": "1",
                    "handler_index": 0,
                    "patch": {"directive": "resume"},
                }
            ),
        },
        repo_root=tmp_path,
    )
    delete_dry_run = execute_mcp_tool(
        tool_name="project.error_handlers.delete",
        arguments={
            "project_id": "domain-loop",
            "parent_node_id": "1",
            "handler_index": 0,
        },
        repo_root=tmp_path,
    )
    scenario_after_delete_dry_run = _read_domain_scenario(tmp_path)

    assert retry_handler_dry_run.ok, retry_handler_dry_run
    assert retry_handler_dry_run.payload["status"] == "dry_run"
    assert retry_handler_dry_run.payload["would_change"] is True
    webhook_after_add_dry_run = cast(
        "JsonObject",
        cast("list[object]", scenario_after_add_dry_run["flow"])[0],
    )
    assert (
        cast("list[object]", webhook_after_add_dry_run.get("onerror", [])) == []
    )
    assert not missing_parent.ok
    assert "missing_parent_node_id" in str(missing_parent.error)
    assert "Example:" in str(missing_parent.error)
    assert not unknown_parent.ok
    assert "unknown_parent_node" in str(unknown_parent.error)
    assert "999" in str(unknown_parent.error)
    assert applied_retry_handler.ok, applied_retry_handler
    assert resume_patch_dry_run.ok, resume_patch_dry_run
    assert resume_patch_dry_run.payload["status"] == "dry_run"
    assert resume_patch_dry_run.payload["would_change"] is True
    assert delete_dry_run.ok, delete_dry_run
    assert delete_dry_run.payload["status"] == "dry_run"
    assert delete_dry_run.payload["changed"] is False
    assert delete_dry_run.payload["would_change"] is True
    webhook = cast(
        "JsonObject",
        cast("list[object]", scenario_after_delete_dry_run["flow"])[0],
    )
    handlers = cast("list[JsonObject]", webhook["onerror"])
    assert handlers[0]["directive"] == "retry"


def _write_domain_scenario(
    repo_root: Path,
    *,
    notes: list[JsonObject] | None = None,
) -> None:
    scenario: JsonObject = {
        "name": "Domain Loop",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook"},
            {
                "id": 2,
                "module": "builtin:BasicRouter",
                "routes": [{"flow": []}],
            },
        ],
        "metadata": {"notes": [] if notes is None else notes},
    }
    scenario_path = repo_root / "projects" / "domain-loop" / "scenario.json"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _read_domain_scenario(repo_root: Path) -> JsonObject:
    scenario_path = repo_root / "projects" / "domain-loop" / "scenario.json"
    return cast(
        "JsonObject", json.loads(scenario_path.read_text(encoding="utf-8"))
    )


def _route_flow_node_ids(scenario: JsonObject) -> list[int]:
    flow = cast("list[JsonObject]", scenario["flow"])
    router = flow[1]
    route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    node_ids: list[int] = []
    for node in cast("list[object]", route.get("flow", [])):
        node_id = cast("JsonObject", node).get("id")
        assert isinstance(node_id, int | str)
        node_ids.append(int(node_id))
    return node_ids


def _assert_response_contract(
    payload: JsonObject, *, contract: str, version: int
) -> None:
    assert payload.get("response_contract") == contract, payload
    assert payload.get("response_schema_version") == version, payload
