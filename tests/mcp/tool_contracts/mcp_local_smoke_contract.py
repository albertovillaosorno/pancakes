# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Minimal local MCP smoke tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from mcp import execute_mcp_tool, mcp_tool_registry
from mcp.project_loop_storage import scenario_summary

RICH_SMOKE_PROJECT_ID = "fixture-rich-project-smoke"
RICH_SMOKE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "rich_project_smoke"
    / "scenario.json"
)


def test_local_mcp_smoke_lists_minimal_tools() -> None:
    """The smoke profile sees only the public minimal tool surface."""
    tool_names = tuple(tool.name for tool in mcp_tool_registry())

    assert tool_names[0] == "mcp.session.start"
    assert "catalog.index" in tool_names
    assert "catalog.search" in tool_names
    assert "catalog.inspect" in tool_names
    assert "project.make" in tool_names
    assert "project.verify" in tool_names
    assert "project.capabilities.inspect" in tool_names
    assert "project.next" in tool_names
    assert "project.view" in tool_names
    assert _tool("project", "tests", "run") not in tool_names
    assert _tool("scraper", "refresh_status") not in tool_names


def test_local_project_view_and_domain_tools_smoke(tmp_path: Path) -> None:
    """The retained project tools can read and update a tiny local graph."""
    _write_smoke_project(tmp_path)

    viewed = execute_mcp_tool(
        tool_name="project.view",
        arguments={"project_id": "smoke"},
        repo_root=tmp_path,
    )
    modules = execute_mcp_tool(
        tool_name="project.modules.view",
        arguments={"project_id": "smoke"},
        repo_root=tmp_path,
    )
    links = execute_mcp_tool(
        tool_name="project.links.view",
        arguments={"project_id": "smoke"},
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={"project_id": "smoke", "action": "preview"},
        repo_root=tmp_path,
    )
    next_action = execute_mcp_tool(
        tool_name="project.next",
        arguments={"project_id": "smoke", "mode": "one"},
        repo_root=tmp_path,
    )

    assert viewed.ok, viewed
    assert modules.ok, modules
    assert links.ok, links
    assert preview.ok, preview
    assert next_action.ok, next_action
    assert viewed.payload["response_contract"] == "project.view"
    assert modules.payload["response_contract"] == "project.modules.view"
    assert links.payload["response_contract"] == "project.links.view"
    assert preview.payload["response_contract"] == "project.make"
    assert next_action.payload["response_contract"] == "project.next"


def test_project_module_delete_direct_tool_is_read_only_preview(
    tmp_path: Path,
) -> None:
    """Direct module removal preview must not require write permissions or.

    confirmation.
    """
    _write_smoke_project(tmp_path)
    tool = next(
        item
        for item in mcp_tool_registry()
        if item.name == "project.modules.delete"
    )
    assert tool.annotations is not None
    schema_properties = cast(
        "dict[str, object]", tool.input_schema()["properties"]
    )
    before = (tmp_path / "projects" / "smoke" / "scenario.json").read_text(
        encoding="utf-8"
    )

    preview = execute_mcp_tool(
        tool_name="project.modules.delete",
        arguments={
            "project_id": "smoke",
            "module_id": 2,
            "dry_run": True,
            "confirm": True,
        },
        repo_root=tmp_path,
    )
    rejected_write = execute_mcp_tool(
        tool_name="project.modules.delete",
        arguments={
            "project_id": "smoke",
            "module_id": 2,
            "dry_run": False,
            "confirm": True,
        },
        repo_root=tmp_path,
    )
    after = (tmp_path / "projects" / "smoke" / "scenario.json").read_text(
        encoding="utf-8"
    )

    assert tool.read_only is True
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert "confirm" not in schema_properties
    assert preview.ok, preview
    assert preview.payload["status"] == "dry_run"
    assert preview.payload["would_change"] is True
    _assert_read_only_local_no_approval(preview.payload)
    assert before == after
    assert not rejected_write.ok
    assert rejected_write.error is not None
    assert "preview-only" in rejected_write.error


def test_rich_project_smoke_surfaces_filters_handlers_runtime_and_make_preview(
    tmp_path: Path,
) -> None:
    """A durable rich fixture covers product surfaces missing from the tiny.

    smoke.
    """
    _write_rich_smoke_project(tmp_path)

    search = execute_mcp_tool(
        tool_name="project.search",
        arguments={"query": "rich project smoke"},
        repo_root=tmp_path,
    )
    views = {
        surface: execute_mcp_tool(
            tool_name="project.view",
            arguments={
                "project_id": RICH_SMOKE_PROJECT_ID,
                "surface": surface,
                "output_mode": "full",
            },
            repo_root=tmp_path,
        )
        for surface in (
            "modules ",
            "links ",
            "filters ",
            "error_handlers ",
            "runtime ",
            "notes ",
            "graph",
        )
    }
    verified = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "profile": "local_structure ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    preview = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "action": "preview ",
            "profile": "import_test ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    documentation = execute_mcp_tool(
        tool_name="documentation.validate",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert search.ok, search
    project_rows = cast("list[dict[str, object]]", search.payload["projects"])
    assert any(
        row["project_id"] == RICH_SMOKE_PROJECT_ID for row in project_rows
    )
    for surface, result in views.items():
        assert result.ok, f"project.view surface={surface} failed: {result}"

    assert views["modules"].payload["module_count"] == 7
    link_count = views["links"].payload["link_count"]
    assert isinstance(link_count, int)
    assert link_count >= 6
    assert views["filters"].payload["filter_count"] == 2
    assert views["error_handlers"].payload["error_handler_count"] == 1
    runtime = cast("dict[str, object]", views["runtime"].payload["runtime"])
    runtime_setup_item_count = runtime["runtime_setup_item_count"]
    assert isinstance(runtime_setup_item_count, int)
    assert runtime_setup_item_count >= 5
    notes_summary = cast(
        "dict[str, object]",
        views["notes"].payload["scenario_notes_summary"],
    )
    assert notes_summary["status"] == "passed"
    assert notes_summary["note_section_validation_status"] == "passed"
    assert notes_summary["note_redaction_status"] == "passed"
    graph_view = cast("dict[str, object]", views["graph"].payload["graph_view"])
    assert graph_view["returned_node_count"] == 7
    returned_connection_count = graph_view["returned_connection_count"]
    assert isinstance(returned_connection_count, int)
    assert returned_connection_count >= 6

    assert verified.ok, verified
    assert verified.payload["status"] == "ok"
    assert verified.payload["structural_validation_status"] == "valid"
    assert verified.payload["scenario_embedded_checks_status"] == "configured"
    assert verified.payload["scenario_tests_status"] == "not_required"
    unblocked_surfaces = cast(
        "tuple[str, ...]",
        verified.payload["unblocked_surfaces"],
    )
    assert "scenario_tests" in unblocked_surfaces
    assert verified.payload["finding_count"] == 0
    local_findings = cast(
        "tuple[dict[str, object], ...]",
        verified.payload["local_linter_findings"],
    )
    assert {finding["severity"] for finding in local_findings} == {"info"}

    assert preview.ok, preview
    assert preview.payload["importable"] is True
    assert preview.payload["roundtrip_importability_status"] == "importable"
    assert preview.payload["zero_trace_status"] == "passed"

    assert documentation.ok, documentation
    assert documentation.payload["status"] == "pass"
    assert documentation.payload["provider_api_call"] is False
    assert documentation.payload["live_make_called"] is False
    assert documentation.payload["credential_value_transfer"] is False


def test_project_loop_storage_summary_matches_project_health_contract(
    tmp_path: Path,
) -> None:
    """The extracted storage helper remains wired into the public project.

    health.

    tool.
    """
    _write_rich_smoke_project(tmp_path)
    scenario = cast(
        "dict[str, object]",
        json.loads(RICH_SMOKE_FIXTURE.read_text(encoding="utf-8")),
    )
    expected_summary = scenario_summary(scenario)

    health = execute_mcp_tool(
        tool_name="project.health",
        arguments={"project_id": RICH_SMOKE_PROJECT_ID},
        repo_root=tmp_path,
    )

    assert health.ok, health
    for summary_key in (
        "module_count ",
        "link_count ",
        "raw_route_and_flow_edge_count ",
        "route_count ",
        "filter_count ",
        "error_handler_count",
    ):
        assert health.payload[summary_key] == expected_summary[summary_key]
    assert (
        health.payload["link_count_semantics"]
        == "deduped_semantic_execution_links"
    )
    assert health.payload["source_of_truth"] == "local_project_scenario"


def test_project_verify_import_test_permission_boundary_is_local_only(
    tmp_path: Path,
) -> None:
    """Import-test verification is local projection, not live Make import."""
    _write_rich_smoke_project(tmp_path)

    import_test = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "profile": "import_test",
        },
        repo_root=tmp_path,
    )
    live_preflight = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "profile": "live_preflight",
        },
        repo_root=tmp_path,
    )
    invalid_profile = execute_mcp_tool(
        tool_name="project.verify",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "profile": "live_import",
        },
        repo_root=tmp_path,
    )
    verify_tool = next(
        tool for tool in mcp_tool_registry() if tool.name == "project.verify"
    )

    assert import_test.ok, import_test
    assert (
        import_test.payload["verification_execution_scope"]
        == "local_import_projection"
    )
    assert import_test.payload["local_import_projection_only"] is True
    assert import_test.payload["provider_api_call"] is False
    assert import_test.payload["live_make_called"] is False
    assert import_test.payload["live_make_import_called"] is False
    _assert_read_only_local_no_approval(import_test.payload)
    permission = cast(
        "dict[str, object]", import_test.payload["permission_boundary"]
    )
    assert permission["local_import_projection"] is True
    assert permission["live_make_import_requires_operator_approval"] is True

    assert live_preflight.ok, live_preflight
    assert (
        live_preflight.payload["verification_execution_scope"]
        == "live_import_preflight"
    )
    assert live_preflight.payload["live_make_import_called"] is False
    assert (
        live_preflight.payload["live_import_requires_operator_approval"] is True
    )
    _assert_read_only_local_no_approval(live_preflight.payload)

    assert invalid_profile.ok, invalid_profile
    assert invalid_profile.payload["status"] == "invalid_profile"
    _assert_read_only_local_no_approval(invalid_profile.payload)
    valid_profiles = cast(
        "tuple[str, ...]", invalid_profile.payload["valid_profile_names"]
    )
    assert {"import_test", "local_structure", "live_preflight"} <= set(
        valid_profiles
    )
    recommended = cast(
        "tuple[dict[str, object], ...]",
        invalid_profile.payload["recommended_tools"],
    )
    assert {row["tool"] for row in recommended} >= {
        "project.verify ",
        "project.make",
    }

    assert verify_tool.annotations is not None
    rationale = verify_tool.annotations.rationale.casefold()
    assert "local import projection" in rationale
    assert "operator gating" in rationale


def test_project_health_runtime_view_and_next_are_safe_read_only(
    tmp_path: Path,
) -> None:
    """Health and runtime setup views are safe read-only targets for.

    project.next.
    """
    _write_rich_smoke_project(tmp_path)

    health = execute_mcp_tool(
        tool_name="project.health",
        arguments={"project_id": RICH_SMOKE_PROJECT_ID},
        repo_root=tmp_path,
    )
    runtime_view = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "surface": "runtime ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    next_result = execute_mcp_tool(
        tool_name="project.next",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "profile": "import_test",
        },
        repo_root=tmp_path,
    )
    tools = {tool.name: tool for tool in mcp_tool_registry()}

    assert health.ok, health
    assert runtime_view.ok, runtime_view
    assert next_result.ok, next_result
    for tool_name in ("project.health", "project.view", "project.next"):
        tool = tools[tool_name]
        assert tool.read_only is True
        assert tool.annotations is not None
        assert tool.annotations.provider_api_call is False
        assert tool.annotations.secret_output is False

    assert health.payload["status"] == "ok"
    assert health.payload["provider_api_call"] is False
    assert health.payload["live_make_called"] is False
    _assert_read_only_local_no_approval(health.payload)
    _assert_read_only_local_no_approval(runtime_view.payload)
    _assert_read_only_local_no_approval(next_result.payload)
    health_runtime_count = health.payload["runtime_setup_item_count"]
    assert isinstance(health_runtime_count, int)
    assert health_runtime_count >= 5

    runtime = cast("dict[str, object]", runtime_view.payload["runtime"])
    runtime_count = runtime["runtime_setup_item_count"]
    assert isinstance(runtime_count, int)
    assert runtime_count >= 5
    groups = cast("tuple[dict[str, object], ...]", runtime["groups"])
    assert groups
    for group in groups:
        placeholder_name = group["placeholder_name"]
        assert isinstance(placeholder_name, str)
        assert placeholder_name == "__IMTCONN__" or placeholder_name.startswith(
            "runtime."
        )
        assert group["placeholder_value_included"] is False
        assert group["value_policy"] == "names_only_no_runtime_values"
        assert "resolved_value" not in group
        assert "credential_value" not in group

    next_action = cast("dict[str, object]", next_result.payload["next_action"])
    assert next_action["tool"] == "project.view"
    next_arguments = cast("dict[str, object]", next_action["arguments"])
    assert next_arguments["surface"] == "runtime"
    followup = execute_mcp_tool(
        tool_name=str(next_action["tool"]),
        arguments=next_arguments,
        repo_root=tmp_path,
    )
    assert followup.ok, followup


def test_project_make_package_dry_run_reports_blocked_notes_without_writes(
    tmp_path: Path,
) -> None:
    """Package dry-run is auditable even when client handoff notes block.

    delivery.
    """
    _write_smoke_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "smoke ",
            "action": "package ",
            "profile": "client_handoff",
            "dry_run": True,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "package_blocked"
    assert payload["blocked_surface"] == "client_handoff"
    assert payload["package_written"] is False
    assert payload["customer_delivery_package_written"] is False
    assert payload["package_path"] is None
    assert payload["customer_delivery_package_path"] is None
    assert payload["package_write_status"] == "dry_run_no_write"
    _assert_dry_run_local_no_write(payload)
    assert payload["redaction_status"] == "passed"
    assert payload["blueprint_readiness_status"] == "ready"
    assert payload["note_readiness_status"] == "blocked_missing_notes"
    assert payload["documentation_readiness_status"] == "blocked_missing_notes"
    assert "client_handoff" in cast("list[str]", payload["blocked_surfaces"])
    planned_files = cast(
        "tuple[dict[str, object], ...]", payload["planned_files"]
    )
    assert len(planned_files) == 3
    assert {file["write_status"] for file in planned_files} == {"planned"}
    assert not (tmp_path / "projects" / "smoke" / "artifacts").exists()


def test_project_make_package_ready_dry_run_reports_planned_customer_files(
    tmp_path: Path,
) -> None:
    """Ready package dry-run reports customer files without writing them."""
    _write_rich_smoke_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": RICH_SMOKE_PROJECT_ID,
            "action": "package ",
            "profile": "client_handoff",
            "dry_run": True,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "package_ready"
    assert payload["package_written"] is False
    assert payload["customer_delivery_package_written"] is False
    assert payload["package_write_status"] == "dry_run_no_write"
    _assert_dry_run_local_no_write(payload)
    assert payload["redaction_status"] == "passed"
    assert payload["blueprint_readiness_status"] == "ready"
    assert payload["note_readiness_status"] == "ready"
    assert payload["note_section_validation_status"] == "passed"
    assert payload["note_redaction_status"] == "passed"
    assert payload["documentation_readiness_status"] == "ready"
    assert payload["planned_file_count"] == 3
    planned_files = cast(
        "tuple[dict[str, object], ...]", payload["planned_files"]
    )
    assert [file["artifact_role"] for file in planned_files] == [
        "make_blueprint_json ",
        "minimal_import_setup_guidance ",
        "non_technical_changelog",
    ]
    assert all(file["customer_visible"] is True for file in planned_files)
    assert not (
        tmp_path / "projects" / RICH_SMOKE_PROJECT_ID / "artifacts"
    ).exists()


def test_project_make_package_non_dry_run_writes_blueprint_only_package(
    tmp_path: Path,
) -> None:
    """Live-preflight package writes stay local and blueprint-import-only."""
    _write_smoke_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "smoke ",
            "action": "package ",
            "profile": "live_preflight",
            "dry_run": False,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "package_written"
    assert payload["status_surface"] == "local_package"
    assert payload["package_written"] is True
    assert payload["customer_delivery_package_written"] is True
    assert payload["package_write_status"] == "write_enabled_after_validation"
    _assert_local_transactional_write(payload)
    assert payload["full_live_validation_status"] == "ready"
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert (tmp_path / str(payload["package_path"])).is_file()
    assert (tmp_path / str(payload["customer_delivery_package_path"])).is_dir()


def test_project_make_compact_outputs_include_missing_note_plan(
    tmp_path: Path,
) -> None:
    """Make preview, render, and package expose exact compact note refs."""
    _write_smoke_project(tmp_path)

    reports = {
        action: execute_mcp_tool(
            tool_name="project.make",
            arguments={
                "project_id": "smoke",
                "action": action,
                "profile": "client_handoff",
                "dry_run": True,
            },
            repo_root=tmp_path,
        )
        for action in ("preview", "render", "package")
    }

    for action, result in reports.items():
        assert result.ok, f"project.make action={action} failed: {result}"
        plan = cast("dict[str, object]", result.payload["missing_note_plan"])
        assert plan["status"] == "blocked_missing_notes"
        assert plan["missing_note_count"] == 3
        assert plan["hidden_missing_note_count"] == 0
        patterns = cast("dict[str, str]", plan["citation_ref_patterns"])
        assert patterns["module"] == "NOTE-MOD-<target_node_id>"
        assert (
            patterns["connection"]
            == "NOTE-CONN-<source_node_id>-<target_node_id>"
        )
        contract = cast("dict[str, object]", plan["quality_contract"])
        module_contract = cast("dict[str, object]", contract["module"])
        connection_contract = cast("dict[str, object]", contract["connection"])
        assert (
            module_contract["make_canvas_pdf_index"]
            == "PDF index: NOTE-MOD-<target_node_id>"
        )
        assert connection_contract["make_canvas_pdf_index"] == (
            "PDF index: NOTE-CONN-<source_node_id>-<target_node_id>"
        )
        items = cast("tuple[dict[str, object], ...]", plan["items"])
        refs = {item["citation_ref"] for item in items}
        assert refs == {"NOTE-MOD-1", "NOTE-MOD-2", "NOTE-CONN-1-2"}
        assert {item["note_kind"] for item in items} == {"module", "connection"}
        serialized_plan = json.dumps(plan, sort_keys=True).casefold()
        assert "projects/" not in serialized_plan
        assert "scenario.json" not in serialized_plan


def test_project_edit_generate_missing_notes_closes_documentation_readiness(
    tmp_path: Path,
) -> None:
    """Generated note sections let a small project pass manual readiness.

    gates.
    """
    _write_smoke_project(tmp_path)

    dry_run = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "operation": "generate_missing",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    unchanged_notes = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    applied = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "operation": "generate_missing",
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    notes = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    docs = execute_mcp_tool(
        tool_name="documentation.generate",
        arguments={
            "project_id": "smoke ",
            "output_mode": "full",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    package = execute_mcp_tool(
        tool_name="project.make",
        arguments={
            "project_id": "smoke ",
            "action": "package ",
            "profile": "client_handoff",
            "dry_run": True,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert dry_run.ok, dry_run
    assert dry_run.payload["status"] == "dry_run"
    assert dry_run.payload["would_change"] is True
    _assert_dry_run_local_no_write(dry_run.payload)
    dry_run_target = cast("dict[str, object]", dry_run.payload["target"])
    assert dry_run_target["added_note_count"] == 3
    assert (
        cast("dict[str, object]", dry_run_target["redaction_evidence"])[
            "status"
        ]
        == "passed"
    )

    assert unchanged_notes.ok, unchanged_notes
    unchanged_summary = cast(
        "dict[str, object]",
        unchanged_notes.payload["scenario_notes_summary"],
    )
    assert unchanged_summary["missing_module_note_count"] == 2
    assert unchanged_summary["missing_connection_note_count"] == 1

    assert applied.ok, applied
    assert applied.payload["status"] == "updated"
    assert applied.payload["changed"] is True

    assert notes.ok, notes
    summary = cast("dict[str, object]", notes.payload["scenario_notes_summary"])
    assert summary["status"] == "passed"
    assert summary["missing_module_note_count"] == 0
    assert summary["missing_connection_note_count"] == 0
    assert summary["note_section_validation_status"] == "passed"
    assert summary["note_redaction_status"] == "passed"
    note_rows = cast("tuple[dict[str, object], ...]", notes.payload["notes"])
    assert len(note_rows) == 3
    for note in note_rows:
        sections = cast("dict[str, str]", note["sections"])
        assert sections
        assert str(note["citation_ref"]).startswith("NOTE-")
        assert not any("[redacted:" in value for value in sections.values())

    assert docs.ok, docs
    assert docs.payload["document_type"] == "technical_manual"
    assert docs.payload["not_a_report"] is True
    assert docs.payload["documentation_status"] == "pass"
    assert (
        cast("dict[str, object]", docs.payload["redaction_evidence"])["status"]
        == "passed"
    )

    assert package.ok, package
    assert package.payload["status"] == "package_ready"
    assert package.payload["documentation_readiness_status"] == "ready"


def test_project_notes_redaction_blocks_and_redacts_unsafe_note_output(
    tmp_path: Path,
) -> None:
    """Unsafe client notes are blocked without echoing the unsafe value."""
    _write_smoke_project(tmp_path)
    unsafe_value = "api_key=sk_test_secret_123456789"
    unsafe_note = {
        "note_kind": "module ",
        "target_node_id": "1 ",
        "title": "MOD-1 | Unsafe note",
        "sections": {
            "Purpose": f"Uses {unsafe_value} from C:/Users/example/.env.",
            "Input": "Receives the customer request fields from the trigger.",
            "Output": "Makes the request available to the next workflow step.",
            "Operator check": (
                "Review internal graph linter logic before handoff."
            ),
        },
    }

    rejected = execute_mcp_tool(
        tool_name="project.edit",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "operation": "add",
            "payload_json": json.dumps(unsafe_note),
            "dry_run": False,
        },
        repo_root=tmp_path,
    )
    scenario_path = tmp_path / "projects" / "smoke" / "scenario.json"
    scenario = cast(
        "dict[str, object]",
        json.loads(scenario_path.read_text(encoding="utf-8")),
    )
    metadata = cast("dict[str, object]", scenario.setdefault("metadata", {}))
    metadata["notes"] = [unsafe_note]
    _ = scenario_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    notes = execute_mcp_tool(
        tool_name="project.view",
        arguments={
            "project_id": "smoke ",
            "surface": "notes ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert "project.edit notes redaction failed" in rejected.error
    assert unsafe_value not in json.dumps(rejected.payload, sort_keys=True)
    assert notes.ok, notes
    summary = cast("dict[str, object]", notes.payload["scenario_notes_summary"])
    assert summary["note_redaction_status"] == "failed"
    evidence = cast("dict[str, object]", summary["redaction_evidence"])
    assert evidence["status"] == "failed"
    class_counts = cast("dict[str, int]", evidence["class_counts"])
    assert class_counts["secret_like_value"] == 1
    assert class_counts["local_path"] == 1
    assert class_counts["private_implementation_reference"] == 1
    assert notes.payload["notes_output_redaction_status"] == "redacted"
    serialized_notes = json.dumps(notes.payload, sort_keys=True)
    assert unsafe_value not in serialized_notes
    assert "[redacted:unsafe_note_text]" in serialized_notes


def test_removed_local_smoke_routes_are_unknown(tmp_path: Path) -> None:
    """Smoke validation rejects routes removed from the MCP."""
    for tool_name in (
        _tool("project", "tests", "run"),
        _tool("project", "blueprint_query"),
        _tool("catalog", "plan"),
        _tool("catalog", "next_unit"),
        _tool("catalog", "save_unit"),
        _tool("catalog", "checkpoint_unit"),
    ):
        result = execute_mcp_tool(
            tool_name=tool_name, arguments={}, repo_root=tmp_path
        )
        assert not result.ok, result
        assert result.error == f"Unknown MCP tool: {tool_name}"


def _write_smoke_project(repo_root: Path) -> None:
    project_path = repo_root / "projects" / "smoke" / "scenario.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario: dict[str, object] = {
        "name": "Smoke",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook"},
            {
                "id": 2,
                "module": "builtin:BasicRouter",
                "routes": [{"flow": []}],
            },
        ],
        "metadata": {},
    }
    _ = project_path.write_text(
        json.dumps(scenario, indent=2), encoding="utf-8"
    )


def _write_rich_smoke_project(repo_root: Path) -> None:
    project_path = (
        repo_root / "projects" / RICH_SMOKE_PROJECT_ID / "scenario.json"
    )
    project_path.parent.mkdir(parents=True, exist_ok=True)
    scenario = cast(
        "dict[str, object]",
        json.loads(RICH_SMOKE_FIXTURE.read_text(encoding="utf-8")),
    )
    _ = project_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _tool(*parts: str) -> str:
    return ".".join(parts)


def _assert_read_only_local_no_approval(payload: dict[str, object]) -> None:
    assert payload["permission_posture"] == "read_only_local_no_approval"
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["requires_operator_approval"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False


def _assert_dry_run_local_no_write(payload: dict[str, object]) -> None:
    assert payload["permission_posture"] == "local_dry_run_no_write_no_approval"
    assert payload["dry_run"] is True
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["requires_operator_approval"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False


def _assert_local_transactional_write(payload: dict[str, object]) -> None:
    assert (
        payload["permission_posture"]
        == "local_transactional_write_session_scoped"
    )
    assert payload["writes_performed"] is True
    assert payload["write_actions"]
    assert payload["requires_operator_approval"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
