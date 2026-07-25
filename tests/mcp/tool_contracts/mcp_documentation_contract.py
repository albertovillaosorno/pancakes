# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for local MCP documentation and onboarding tools."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from mcp import execute_mcp_tool, mcp_tool_registry

if TYPE_CHECKING:
    from pathlib import Path


def _create_project_from_summary(
    repo_root: Path,
    *,
    project_id: str,
    summary: str,
) -> None:
    staged = execute_mcp_tool(
        tool_name="project.draft.stage",
        arguments={
            "project_id": project_id,
            "scenario_summary": summary,
            "dry_run": False,
        },
        repo_root=repo_root,
    )
    assert staged.ok, staged
    created = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": project_id,
            "staged_draft_path": staged.payload["staged_draft_path"],
            "staged_draft_sha256": staged.payload["staged_draft_sha256"],
            "dry_run": False,
        },
        repo_root=repo_root,
    )
    assert created.ok, created


def test_documentation_tool_schemas_accept_consistent_preview_inputs() -> None:
    """Documentation tools expose consistent read/preview schema knobs."""
    schemas = {tool.name: tool.input_schema() for tool in mcp_tool_registry()}
    generate_properties = cast(
        "dict[str, object]",
        schemas["documentation.generate"]["properties"],
    )
    validate_properties = cast(
        "dict[str, object]",
        schemas["documentation.validate"]["properties"],
    )

    assert "output_mode" in generate_properties
    assert "dry_run" in generate_properties
    assert "output_mode" in validate_properties


def test_documentation_generate_uses_local_project_state_without_provider_calls(
    tmp_path: Path,
) -> None:
    """documentation.generate prebuilds a local manual base from project.

    state.
    """
    _create_project_from_summary(
        tmp_path,
        project_id="docs-demo",
        summary="Create a local invoice intake scenario.",
    )

    generated = execute_mcp_tool(
        tool_name="documentation.generate",
        arguments={
            "project_id": "docs-demo",
            "dry_run": True,
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert generated.ok, generated
    payload = generated.payload
    assert payload["source_of_truth"] == "local_project_scenario"
    assert payload["generation_mode"] == "realtime_project_state"
    assert payload["document_type"] == "technical_manual"
    assert payload["document_kind"] == "customer_technical_manual"
    assert payload["not_a_report"] is True
    assert payload["output_mode"] == "compact"
    assert payload["dry_run"] is True
    assert payload["documentation_write_status"] == "read_only_no_write"
    assert payload["write_performed"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    sections = cast(
        "list[dict[str, object]]", payload["documentation_sections"]
    )
    section_ids = {str(section["section_id"]) for section in sections}
    assert "make_modules_and_data_flow" in section_ids
    assert "numbered_make_note_references" in section_ids
    assert "operational_behavior" in section_ids
    validation = cast("dict[str, object]", payload["documentation_validation"])
    assert validation["forbidden_words_checked"] is True
    assert validation["no_secret_check"] is True
    assert validation["no_guarantee_check"] is True


def test_documentation_validate_full_is_local_and_not_blocked_for_clean_project(
    tmp_path: Path,
) -> None:
    """The full documentation validator is a safe local read when project.

    evidence.

    is clean.
    """
    _create_project_from_summary(
        tmp_path,
        project_id="docs-full-clean",
        summary="Capture support requests, store them, and alert Slack.",
    )

    validation = execute_mcp_tool(
        tool_name="documentation.validate",
        arguments={"project_id": "docs-full-clean", "output_mode": "full"},
        repo_root=tmp_path,
    )

    assert validation.ok, validation
    payload = validation.payload
    assert payload["status"] == "pass"
    assert payload["output_mode"] == "full"
    assert payload["permission_posture"] == "read_only_local_no_approval"
    assert payload["writes_performed"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False


def test_documentation_redaction_section_uses_redaction_f6d930(
    tmp_path: Path,
) -> None:
    """A zero-trace blocker does not masquerade as missing documentation.

    redaction.

    evidence.
    """
    _create_project_from_summary(
        tmp_path,
        project_id="docs-zero-trace",
        summary="Capture support requests, store them, and alert Slack.",
    )
    scenario_path = (
        tmp_path
        / "temp"
        / "pancakes"
        / "project-artifacts"
        / "local-demo"
        / "0001-docs-zero-trace"
        / "scenario.json"
    )
    scenario = cast(
        "dict[str, object]",
        json.loads(scenario_path.read_text(encoding="utf-8")),
    )
    flow = cast("list[dict[str, object]]", scenario["flow"])
    flow[0]["mapper"] = {"private_debug_marker": "local_project_scenario"}
    _ = scenario_path.write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    generated = execute_mcp_tool(
        tool_name="documentation.generate",
        arguments={
            "project_id": "docs-zero-trace",
            "dry_run": True,
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert generated.ok, generated
    sections = cast(
        "tuple[dict[str, object], ...]",
        generated.payload["documentation_sections"],
    )
    redaction_section = next(
        section
        for section in sections
        if section["section_id"] == "redaction_and_secret_free_evidence"
    )
    assert redaction_section["status"] == "present"
    assert (
        cast("dict[str, object]", generated.payload["redaction_evidence"])[
            "status"
        ]
        == "passed"
    )
    assert generated.payload["documentation_status"] == "pass"


def test_documentation_validate_rejects_forbidden_content_and_missing_sections(
    tmp_path: Path,
) -> None:
    """documentation.validate fails closed on private content and incomplete.

    bases.
    """
    result = execute_mcp_tool(
        tool_name="documentation.validate",
        arguments={
            "output_mode": "full",
            "documentation_json": json.dumps(
                {
                    "documentation_sections": [
                        {
                            "section_id": "scenario_architecture ",
                            "status": "present",
                            "missing_field_count": 0,
                        }
                    ],
                    "body": (
                        "api_key=exampletoken123 "
                        "100% secure private prompt linter logic "
                        "C:/Users/example/source"
                    ),
                }
            ),
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    validation = cast(
        "dict[str, object]", result.payload["documentation_validation"]
    )
    assert result.payload["status"] == "fail"
    assert result.payload["output_mode"] == "full"
    assert validation["secret_like_value_count"] == 1
    assert validation["unsupported_claim_count"] == 1
    private_internal_count = validation["private_internal_reference_count"]
    assert isinstance(private_internal_count, int)
    assert private_internal_count >= 1
    assert validation["local_path_reference_count"] == 1
    redaction_evidence = cast(
        "dict[str, object]", result.payload["redaction_evidence"]
    )
    assert redaction_evidence["status"] == "failed"
    assert redaction_evidence["redacted_values_returned"] is False
    assert "exampletoken123" not in json.dumps(result.payload, sort_keys=True)
    missing_section_ids = validation["missing_section_ids"]
    assert isinstance(missing_section_ids, tuple | list)
    assert "make_modules_and_data_flow" in missing_section_ids


def test_onboarding_validate_rejects_legacy_payload_values_before_processing(
    tmp_path: Path,
) -> None:
    """onboarding.validate does not expose raw setup-value collection as a.

    public.

    tool input.
    """
    secret_value = "sk_test_secret_like_123456"

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "onboarding_json": json.dumps(
                {
                    "required_connection": "{{runtime.client_make_connection}}",
                    "api_key": secret_value,
                }
            )
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "onboarding_json no longer accepts credential values" in result.error
    assert secret_value not in result.error
    assert secret_value not in json.dumps(result.payload, sort_keys=True)


def test_onboarding_validate_rejects_known_secret_shapes_without_echoing_values(
    tmp_path: Path,
) -> None:
    """Legacy raw onboarding payloads fail closed without echoing.

    credential-shaped.

    values.
    """
    secret_values = {
        "slack_token": (
            "xoxb-123456789012-123456789012-AbCdEfGhIjKlMnOpQrStUvWx "
        ),
        "google_api_key": "AIzaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA ",
        "openai_key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890 ",
        "anthropic_key": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890",
        "jwt": (
            "eyJhbGciOiJIUzI1NiJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "abcdefghijklmnopqrstuvwxyz123456"
        ),
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz1234567890",
        "oauth": {"refresh_token": "1//0gabcdefghijklmnopqrstuvwxyz1234567890"},
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n "
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
            "-----END PRIVATE KEY-----"
        ),
        "high_entropy": "mF9cL2pQ7sR8tU4vW6xY0zA3bC5dE7fG9hJ1kL3mN5pQ",
    }

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={"onboarding_json": json.dumps(secret_values)},
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "provided_placeholders_json" in result.error
    serialized_payload = json.dumps(
        {"error": result.error, "payload": result.payload},
        sort_keys=True,
    )
    for secret_value in secret_values.values():
        if isinstance(secret_value, dict):
            for nested_secret_value in secret_value.values():
                assert nested_secret_value not in serialized_payload
        else:
            assert secret_value not in serialized_payload


def test_onboarding_validate_rejects_secret_shaped_65f998c9(
    tmp_path: Path,
) -> None:
    """The replacement placeholder-name input rejects obvious credential.

    values.
    """
    secret_value = "sk_test_secret_like_123456"

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={"provided_placeholders_json": json.dumps([secret_value])},
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "looks like a credential value" in result.error
    assert secret_value not in result.error
    assert secret_value not in json.dumps(result.payload, sort_keys=True)


def test_onboarding_validate_keeps_placeholder_names_actionable(
    tmp_path: Path,
) -> None:
    """Placeholder names remain allowed when they are not real credential.

    values.
    """
    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "provided_placeholders_json": json.dumps(
                [
                    "runtime.client_api_key",
                    "__SLACK_TOKEN__",
                    "OPENAI_API_KEY",
                ]
            )
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["status"] == "pass"
    assert result.payload["secret_value_count"] == 0
    assert result.payload["findings"] == ()
    assert result.payload["placeholder_count"] == 3
    assert result.payload["raw_onboarding_values_accepted"] is False
    assert result.payload["placeholder_values_allowed"] is False
    assert result.payload["placeholder_names_allowed"] is True
    assert result.payload["placeholder_value_policy"] == "names_only_no_values"


def test_onboarding_validate_reports_project_placeholder_coverage_gaps(
    tmp_path: Path,
) -> None:
    """Project-aware onboarding reports missing, extra, and duplicate.

    placeholder.

    names.
    """
    _write_onboarding_fixture_project(tmp_path)
    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "project_id": "onboarding-fixture",
            "provided_placeholders_json": json.dumps(
                [
                    "runtime.webhook.lead_intake_hook",
                    "{{runtime.webhook.lead_intake_hook}}",
                    "runtime.extra.unused",
                ]
            ),
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "fail"
    assert payload["project_id"] == "onboarding-fixture"
    assert payload["project_placeholder_validation_status"] == "fail"
    assert payload["project_placeholder_required_count"] == 2
    assert payload["project_placeholder_entry_count"] == 3
    assert payload["project_placeholder_provided_count"] == 1
    assert payload["project_placeholder_missing_count"] == 1
    assert payload["project_placeholder_extra_count"] == 1
    assert payload["project_placeholder_duplicate_count"] == 1
    assert payload["missing_placeholders"] == (
        "runtime.datastore.qualified_leads",
    )
    assert payload["extra_placeholders"] == ("runtime.extra.unused",)
    assert payload["duplicate_placeholders"] == (
        "runtime.webhook.lead_intake_hook",
    )
    project_findings = cast(
        "tuple[dict[str, object], ...]", payload["project_placeholder_findings"]
    )
    assert {finding["code"] for finding in project_findings} == {
        "onboarding.placeholder_duplicate ",
        "onboarding.placeholder_extra ",
        "onboarding.placeholder_missing",
    }
    assert payload["secret_value_count"] == 0
    actions = cast("tuple[dict[str, object], ...]", payload["next_actions"])
    assert {action["action"] for action in actions} == {
        "deduplicate_placeholders ",
        "provide_missing_placeholders ",
        "remove_extra_placeholders",
    }
    assert payload["stores_credentials"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False


def test_onboarding_validate_reports_one_missing_project_placeholder(
    tmp_path: Path,
) -> None:
    """One omitted required placeholder fails with a focused.

    missing-placeholder.

    action.
    """
    _write_onboarding_fixture_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "project_id": "onboarding-fixture",
            "provided_placeholders_json": json.dumps(
                ["runtime.webhook.lead_intake_hook"]
            ),
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "fail"
    assert payload["project_placeholder_validation_status"] == "fail"
    assert payload["placeholder_count"] == 1
    assert payload["project_placeholder_missing_count"] == 1
    assert payload["missing_placeholders"] == (
        "runtime.datastore.qualified_leads",
    )
    actions = cast("tuple[dict[str, object], ...]", payload["next_actions"])
    assert [action["action"] for action in actions] == [
        "provide_missing_placeholders"
    ]


def test_onboarding_validate_reports_one_extra_project_placeholder(
    tmp_path: Path,
) -> None:
    """One non-required placeholder fails with a focused extra-placeholder.

    action.
    """
    _write_onboarding_fixture_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "project_id": "onboarding-fixture",
            "provided_placeholders_json": json.dumps(
                [
                    "runtime.webhook.lead_intake_hook ",
                    "runtime.datastore.qualified_leads ",
                    "runtime.extra.unused",
                ]
            ),
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "fail"
    assert payload["project_placeholder_validation_status"] == "fail"
    assert payload["placeholder_count"] == 3
    assert payload["project_placeholder_extra_count"] == 1
    assert payload["extra_placeholders"] == ("runtime.extra.unused",)
    actions = cast("tuple[dict[str, object], ...]", payload["next_actions"])
    assert [action["action"] for action in actions] == [
        "remove_extra_placeholders"
    ]


def test_onboarding_validate_rejects_secret_value_inside_required_placeholder(
    tmp_path: Path,
) -> None:
    """A legacy required-placeholder value is rejected without returning the.

    raw.

    secret.
    """
    _write_onboarding_fixture_project(tmp_path)
    secret_value = "xoxb-123456789012-123456789012-AbCdEfGhIjKlMnOpQrStUvWx"

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "project_id": "onboarding-fixture",
            "onboarding_json": json.dumps(
                {
                    "placeholders": {
                        "runtime.webhook.lead_intake_hook": secret_value
                    }
                }
            ),
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert result.error is not None
    assert "onboarding_json no longer accepts credential values" in result.error
    assert secret_value not in result.error
    assert secret_value not in json.dumps(result.payload, sort_keys=True)


def test_onboarding_validate_accepts_complete_nested_project_placeholders(
    tmp_path: Path,
) -> None:
    """A nested placeholders object can cover every runtime setup requirement.

    once.
    """
    _write_onboarding_fixture_project(tmp_path)

    result = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={
            "project_id": "onboarding-fixture ",
            "output_mode": "full",
            "provided_placeholders_json": json.dumps(
                [
                    "{{runtime.webhook.lead_intake_hook}}",
                    "runtime_datastore_qualified_leads",
                ]
            ),
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "pass"
    assert payload["output_mode"] == "full"
    assert payload["project_placeholder_validation_status"] == "pass"
    assert payload["project_placeholder_required_count"] == 2
    assert payload["project_placeholder_entry_count"] == 2
    assert payload["project_placeholder_provided_count"] == 2
    assert payload["project_placeholder_missing_count"] == 0
    assert payload["project_placeholder_extra_count"] == 0
    assert payload["project_placeholder_duplicate_count"] == 0
    assert payload["project_placeholder_findings"] == ()
    actions = cast("tuple[dict[str, object], ...]", payload["next_actions"])
    assert actions == (
        {
            "action": "ready_for_customer_form ",
            "message": (
                "All required project placeholders are represented once."
            ),
        },
    )


def test_onboarding_validate_returns_actionable_schema_errors(
    tmp_path: Path,
) -> None:
    """Invalid onboarding validation inputs fail with specific messages."""
    invalid_mode = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={"output_mode": "debug"},
        repo_root=tmp_path,
    )
    invalid_json = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={"provided_placeholders_json": "{"},
        repo_root=tmp_path,
    )
    legacy_json = execute_mcp_tool(
        tool_name="onboarding.validate",
        arguments={"onboarding_json": "{}"},
        repo_root=tmp_path,
    )

    assert not invalid_mode.ok
    assert (
        invalid_mode.error
        == "onboarding.validate output_mode must be compact or full."
    )
    assert not invalid_json.ok
    assert (
        invalid_json.error
        == "provided_placeholders_json must be valid JSON array text."
    )
    assert not legacy_json.ok
    assert legacy_json.error is not None
    assert "onboarding_json is no longer accepted" in legacy_json.error


def test_documentation_tools_return_actionable_schema_errors(
    tmp_path: Path,
) -> None:
    """Invalid documentation preview inputs fail with specific messages."""
    invalid_generate_dry_run = execute_mcp_tool(
        tool_name="documentation.generate",
        arguments={"project_id": "docs-demo", "dry_run": "yes"},
        repo_root=tmp_path,
    )
    invalid_validate_mode = execute_mcp_tool(
        tool_name="documentation.validate",
        arguments={"documentation_json": "{}", "output_mode": "debug"},
        repo_root=tmp_path,
    )

    assert not invalid_generate_dry_run.ok
    assert (
        invalid_generate_dry_run.error
        == "documentation.generate dry_run must be boolean."
    )
    assert not invalid_validate_mode.ok
    assert (
        invalid_validate_mode.error
        == "documentation.validate output_mode must be compact or full."
    )


def _write_onboarding_fixture_project(root: Path) -> None:
    project_dir = root / "projects" / "onboarding-fixture"
    project_dir.mkdir(parents=True)
    scenario = {
        "name": "onboarding fixture",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": "{{runtime.webhook.lead_intake_hook}}"},
            },
            {
                "id": 2,
                "module": "datastore:AddRecord",
                "parameters": {
                    "datastore": "{{runtime.datastore.qualified_leads}}"
                },
            },
        ],
    }
    _ = (project_dir / "scenario.json").write_text(
        f"{json.dumps(scenario, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
