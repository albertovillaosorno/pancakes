# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the Make live Browser validation ledger.

Boundary contract:
- Owns: deterministic ledger and Browser smoke-plan behavior.
- Must not: contact Make.com, automate a browser, or depend on credentials.
- Allows: local raw-spec and default-manifest coverage enumeration.
- Split when: reviewed live Browser evidence becomes persisted by a service
runner.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from languages.make.default_manifest_coverage import (
    make_default_manifest_coverage_facts,
)
from languages.make.live_browser_validation import (
    MAKE_LIVE_BROWSER_ENTRY_STATUS,
    MAKE_LIVE_BROWSER_FORBIDDEN_ACTIONS,
    build_make_live_browser_validation_ledger,
    classify_make_api_blueprint_response_shapes,
    classify_make_connection_bind_lifecycle_evidence,
    classify_make_datastore_lifecycle_evidence,
    classify_make_datastore_strict_schema_validation_evidence,
    classify_make_hook_configuration_validation_evidence,
    classify_make_live_apply_package_roundtrip_evidence,
    classify_make_live_bridge_probe_evidence,
    classify_make_module_configuration_validation_evidence,
    classify_make_module_requirement_extraction_evidence,
    classify_make_runtime_resource_requirement_extraction_evidence,
    classify_make_scenario_designer_roundtrip_evidence,
    classify_make_scenario_interface_schedule_evidence,
    classify_make_scenario_mutation_contract_evidence,
    classify_make_scenario_run_once_evidence,
    classify_make_webhook_bind_lifecycle_evidence,
    classify_make_webhook_datastore_quality_canary_evidence,
    inspect_make_api_blueprint_response,
    make_live_browser_smoke_plan,
    validate_make_dashboard_navigation_landmarks,
)
from languages.make.raw_specs.paths import DEFAULT_RAW_SPEC_SQLITE_DATABASE
from languages.make.raw_specs.sqlite_store import load_sqlite_raw_spec_bundle

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from languages.make.raw_specs.models import RawSpecManifest

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
SHAPE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_api_blueprint_response_shapes.json"
)
DASHBOARD_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "dashboard_navigation_landmarks.json"
)
LIVE_BRIDGE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_api_live_bridge_probe_shapes.json"
)
SCENARIO_DESIGNER_ROUNDTRIP_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_api_scenario_designer_roundtrip_shapes.json"
)
SCENARIO_MUTATION_CONTRACT_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_api_scenario_mutation_contract_shapes.json"
)
DATASTORE_RECORD_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_api_existing_store_record_probe_shapes.json"
)
DATASTORE_LIFECYCLE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_datastore_lifecycle_shapes.json"
)
WEBHOOK_BIND_LIFECYCLE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_webhook_bind_lifecycle_shapes.json"
)
CONNECTION_BIND_LIFECYCLE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_connection_bind_lifecycle_shapes.json"
)
LIVE_APPLY_PACKAGE_ROUNDTRIP_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_live_apply_package_roundtrip_shapes.json"
)
MODULE_REQUIREMENT_EXTRACTION_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_module_requirement_extraction_shapes.json"
)
RUNTIME_RESOURCE_REQUIREMENT_EXTRACTION_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_runtime_resource_requirement_extraction_shapes.json"
)
SCENARIO_INTERFACE_SCHEDULE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_scenario_interface_schedule_shapes.json"
)
MODULE_CONFIGURATION_VALIDATION_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_module_configuration_validation_shapes.json"
)
SCENARIO_RUN_ONCE_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_scenario_run_once_shapes.json"
)
HOOK_CONFIGURATION_VALIDATION_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_hook_configuration_validation_shapes.json"
)
DATASTORE_STRICT_SCHEMA_VALIDATION_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_datastore_strict_schema_validation_shapes.json"
)
WEBHOOK_DATASTORE_LIVE_CANARY_FIXTURE = (
    "tests/languages/make/fixtures/live_parity/"
    "make_mcp_browser_webhook_datastore_canary_shapes.json"
)


def test_live_browser_validation_ledger_covers_3011fddd() -> None:
    """The ledger accounts for every raw-spec and default-manifest catalog.

    entry.
    """
    manifest = _sqlite_raw_spec_manifest()
    raw_spec_entry_count = sum(
        record.module_count for record in manifest.records
    )
    default_manifest_entry_count = len(
        make_default_manifest_coverage_facts(REPO_ROOT)
    )

    ledger = build_make_live_browser_validation_ledger(
        repo_root=REPO_ROOT, offset=0, limit=3
    )

    assert ledger["status"] == "browser_validation_required"
    assert (
        ledger["total_entry_count"]
        == raw_spec_entry_count + default_manifest_entry_count
    )
    assert ledger["raw_spec_entry_count"] == raw_spec_entry_count
    assert (
        ledger["default_manifest_entry_count"] == default_manifest_entry_count
    )
    assert ledger["documented_blocker_count"] == ledger["total_entry_count"]
    assert ledger["live_browser_validated_count"] == 0
    assert ledger["returned_entry_count"] == 3
    entries = cast("list[JsonObject]", ledger["entries"])
    assert isinstance(entries, list), (
        f"Ledger entries must be JSON-ready: {ledger}"
    )
    assert all(
        entry["status"] == MAKE_LIVE_BROWSER_ENTRY_STATUS for entry in entries
    )
    assert all(
        entry["blocker_code"] == "no_reviewed_browser_import_export_diff"
        for entry in entries
    )


def test_live_browser_validation_ledger_paginates_default_manifest_tail() -> (
    None
):
    """Default-manifest entries are covered after raw-spec manifest entries."""
    manifest = _sqlite_raw_spec_manifest()
    raw_spec_entry_count = sum(
        record.module_count for record in manifest.records
    )

    ledger = build_make_live_browser_validation_ledger(
        repo_root=REPO_ROOT,
        offset=raw_spec_entry_count,
        limit=2,
    )

    entries = cast("list[JsonObject]", ledger["entries"])
    assert isinstance(entries, list), (
        f"Ledger entries must be JSON-ready: {ledger}"
    )
    assert len(entries) == 2
    assert all(
        entry["source_label"] == "default_manifest_coverage"
        for entry in entries
    )
    assert all(
        str(entry["entry_id"]).startswith("default_manifest:")
        for entry in entries
    )


def test_live_browser_smoke_plan_is_zero_operation_and_browser_first() -> None:
    """Roulette receives a repeatable Browser-first smoke plan without live.

    mutation.
    """
    plan = make_live_browser_smoke_plan()

    assert plan["preferred_surface"] == "Codex in-app Browser"
    assert (
        plan["live_canary_status"]
        == "destructive_webhook_datastore_canary_passed_and_cleaned"
    )
    assert (
        plan["fully_automated_production_status"]
        == "local_mcp_ready_live_canary_passed"
    )
    assert plan["resource_creation_order"] == [
        "data_structure",
        "data_store",
        "webhook",
        "scenario",
    ]
    assert "absence in Make UI means cleanup passed" in str(
        plan["cleanup_semantics"]
    )
    assert plan["fallback_surface"] == "none_browser_only"
    assert "Chrome" not in json.dumps(plan, sort_keys=True)
    assert "make-auth" not in json.dumps(plan, sort_keys=True)
    assert plan["headless_allowed_for_first_pass"] is False
    assert plan["operation_credit_budget"] == 0
    forbidden_actions = cast("list[str]", plan["forbidden_actions"])
    steps = cast("list[str]", plan["steps"])
    assert set(MAKE_LIVE_BROWSER_FORBIDDEN_ACTIONS) <= set(forbidden_actions)
    assert "run_once" in forbidden_actions
    assert "connection_creation" in forbidden_actions
    assert any(
        "Data Structure, Data Store, Webhook, Scenario" in step
        for step in steps
    ), plan
    assert any("Bind required" in step for step in steps), plan
    assert any("fingerprint" in step and "parity" in step for step in steps), (
        plan
    )
    assert any(
        "cleaned-up resources are expected to be absent" in step
        for step in steps
    ), plan
    assert any("diff" in step for step in steps), (
        f"Diff step is missing: {plan}"
    )


def test_webhook_datastore_live_canary_fixture_proves_quality_green_path() -> (
    None
):
    """Redacted live canary evidence proves resource preload, quality,.

    execution, and cleanup.
    """
    evidence = _read_json_object(
        REPO_ROOT / WEBHOOK_DATASTORE_LIVE_CANARY_FIXTURE
    )

    summary = classify_make_webhook_datastore_quality_canary_evidence(
        evidence,
        required_capabilities=(
            "preload_hooks_before_editor_load",
            "preload_data_structures_before_editor_load",
            "preload_data_stores_before_editor_load",
            "hooks_create_gateway_webhook",
            "data_stores_create",
            "scenarios_create_inactive_filtered_webhook_datastore",
            "browser_editor_open_edit_mode",
            "scenario_activate_destructive_probe",
            "webhook_post_valid_payload",
            "data_store_records_list_observed",
            "scenario_deactivate",
            "cleanup_scenarios_delete",
            "cleanup_hooks_delete",
            "cleanup_data_stores_delete",
            "cleanup_data_structures_delete",
        ),
    )

    assert summary["status"] == "pass", summary
    assert (
        evidence["status"]
        == "live_canary_mcp_browser_webhook_datastore_no_discard_passed"
    )
    assert evidence["validation_actor"] == "codex_make_connector_plus_browser"
    assert evidence["browser_surface"] == "codex_in_app_browser"
    assert evidence["live_make_called"] is True
    assert evidence["provider_api_call"] is True
    assert evidence["operator_destructive_canary_authorized"] is True
    assert evidence["scenario_activation_called"] is True
    assert evidence["scenario_run_once_called"] is False
    assert evidence["credential_value_transfer"] is False
    assert evidence["secret_output"] is False

    capabilities = set(cast("list[str]", evidence["capabilities_proven"]))
    assert {
        "hooks_create_gateway_webhook",
        "data_stores_create",
        "scenarios_create_inactive_filtered_webhook_datastore",
        "scenarios_get_export_bound_blueprint",
        "browser_editor_open_edit_mode",
        "webhook_post_valid_payload",
        "data_store_records_list_observed",
        "cleanup_scenarios_delete",
        "cleanup_hooks_delete",
        "cleanup_data_stores_delete",
        "cleanup_data_structures_delete",
    } <= capabilities

    created_shape = cast(
        "JsonObject", evidence["scenario_create_response_shape"]
    )
    assert created_shape["isActive"] == "bool_false"
    assert (
        cast("JsonObject", created_shape["scheduling"])["type"] == "immediately"
    )
    assert created_shape["usedPackages"] == ["gateway", "builtin", "datastore"]

    browser = cast("JsonObject", evidence["scenario_browser_inspection"])
    assert browser["editor_opened"] is True
    assert browser["edit_mode_entered"] is True
    assert browser["retry_visible"] is False
    assert browser["flow_control_discard_visible"] is False
    assert browser["skip_directive_outside_error_handler_visible"] is False
    assert browser["route_filters_visible"] == ["Has request id"]

    request_contract = cast("JsonObject", evidence["request_contract"])
    note_shape = cast("JsonObject", request_contract["note_quality_shape"])
    assert note_shape["scenario_note_count"] == 3
    assert note_shape["designer_note_count"] == 3
    assert note_shape["filter_note_count"] == 1

    export_contract = cast(
        "JsonObject", evidence["scenario_get_blueprint_contract"]
    )
    assert export_contract["$.blueprint.metadata.notes"] == 3
    assert export_contract["$.blueprint.metadata.designer.notes"] == 3

    functional_probe = cast("JsonObject", evidence["functional_probe"])
    assert functional_probe["webhook_http_status"] == 200
    assert functional_probe["execution_status"] == "success"
    assert functional_probe["data_store_record_observed"] is True

    cleanup_counts = cast("JsonObject", evidence["cleanup_counts"])
    assert cleanup_counts == {
        "scratch_data_stores": 0,
        "scratch_data_structures": 0,
        "scratch_hooks": 0,
        "scratch_scenarios": 0,
    }
    evidence_text = json.dumps(evidence, sort_keys=True)
    assert "hook.us2.make.com" not in evidence_text
    assert "@pm.me" not in evidence_text


def test_webhook_datastore_live_canary_classifier_045226b7() -> None:
    """A plumbing-only scenario with no functional probe, filters, or notes is.

    not green.
    """
    evidence: JsonObject = {
        "capabilities_proven": [
            "hooks_create_gateway_webhook",
            "data_stores_create",
            "scenarios_create_inactive_filtered_webhook_datastore",
            "browser_editor_open_edit_mode",
        ],
        "credential_value_transfer": False,
        "credentials_printed": False,
        "customer_data_used": False,
        "live_make_called": True,
        "operator_destructive_canary_authorized": True,
        "provider_api_call": True,
        "scenario_activation_called": False,
        "scenario_browser_inspection": {
            "editor_opened": True,
            "edit_mode_entered": True,
            "flow_control_discard_visible": False,
            "retry_visible": True,
            "route_filters_visible": [],
            "run_once_visible": True,
            "schedule_visible": "Immediately as data arrives",
            "skip_directive_outside_error_handler_visible": False,
        },
        "scenario_run_once_called": False,
        "secret_output": False,
        "steps": [
            {"name": "hooks_create_gateway_webhook", "status": "ok"},
            {"name": "data_stores_create", "status": "ok"},
            {
                "name": "scenarios_create_inactive_filtered_webhook_datastore",
                "status": "ok",
            },
            {"name": "browser_editor_open_edit_mode", "status": "ok"},
        ],
    }

    summary = classify_make_webhook_datastore_quality_canary_evidence(
        evidence,
        required_capabilities=("webhook_post_valid_payload",),
    )

    assert summary["status"] == "fail"
    assert summary["request_contract_status"] == "fail"
    assert summary["browser_review_status"] == "fail"
    assert summary["functional_probe_status"] == "fail"


def test_webhook_datastore_live_canary_classifier_da2a4e0d() -> None:
    """A Make Skip directive outside an error handler is never acceptable.

    canary.

    quality.
    """
    evidence: JsonObject = {
        "capabilities_proven": [
            "preload_hooks_before_editor_load",
            "preload_data_structures_before_editor_load",
            "preload_data_stores_before_editor_load",
            "hooks_create_gateway_webhook",
            "data_stores_create",
            "scenarios_create_inactive_filtered_webhook_datastore",
            "browser_editor_open_edit_mode",
            "scenario_activate_destructive_probe",
            "webhook_post_valid_payload",
            "data_store_records_list_observed",
            "scenario_deactivate",
            "cleanup_scenarios_delete",
            "cleanup_hooks_delete",
            "cleanup_data_stores_delete",
            "cleanup_data_structures_delete",
        ],
        "cleanup_counts": {
            "scratch_data_stores": 0,
            "scratch_data_structures": 0,
            "scratch_hooks": 0,
            "scratch_scenarios": 0,
        },
        "credential_value_transfer": False,
        "credentials_printed": False,
        "customer_data_used": False,
        "functional_probe": {
            "data_store_record_contract": {
                "fields": ["payload", "request_id", "status"],
                "key_present": True,
            },
            "data_store_record_observed": True,
            "execution_operations": 2,
            "execution_status": "success",
            "operator_destructive_canary_authorized": True,
            "scenario_activation_called": True,
            "scenario_deactivation_called": True,
            "webhook_http_status": 200,
        },
        "hook_delete_response": "Hook has been deleted.",
        "live_make_called": True,
        "operator_destructive_canary_authorized": True,
        "provider_api_call": True,
        "request_contract": {
            "note_quality_shape": {
                "designer_note_count": 4,
                "filter_note_count": 1,
                "module_note_count": 3,
                "scenario_note_count": 4,
            },
            "route_quality_shape": {
                "flow_control_discard_module_present": True,
                "retry_module_present": False,
                "route_filter_count": 2,
                "route_filter_names": ["Has request id", "Missing request id"],
                "skip_directive_outside_error_handler_visible": True,
            },
            "scenario_create": {
                "blueprint.flow.modules": [
                    "gateway:CustomWebHook",
                    "builtin:BasicRouter",
                ],
                "blueprint.flow[0].parameters.hook": "int",
                "blueprint.route.flow.modules": [
                    "datastore:AddRecord",
                    "builtin:Ignore",
                ],
                "blueprint.route.flow[0].parameters.datastore": "int",
                "confirmed": "bool_true",
                "scheduling.type": "immediately",
            },
        },
        "scenario_activation_called": True,
        "scenario_browser_inspection": {
            "editor_opened": True,
            "edit_mode_entered": True,
            "flow_control_discard_visible": True,
            "retry_visible": False,
            "route_filters_visible": ["Has request id", "Missing request id"],
            "run_once_visible": True,
            "schedule_visible": "Immediately as data arrives",
            "skip_directive_outside_error_handler_visible": True,
        },
        "scenario_delete_response": "Scenario has been deleted.",
        "scenario_get_blueprint_contract": {
            "$.blueprint.flow.modules": [
                "gateway:CustomWebHook",
                "builtin:BasicRouter",
            ],
            "$.blueprint.flow_control_discard_module_present": True,
            "$.blueprint.metadata.designer.notes": 4,
            "$.blueprint.metadata.notes": 4,
            "$.blueprint.retry_module_present": False,
            "$.blueprint.route.filter.names": [
                "Has request id",
                "Missing request id",
            ],
            "$.blueprint.route.flow.modules": [
                "datastore:AddRecord",
                "builtin:Ignore",
            ],
            "$.blueprint.scheduling.type": "immediately",
            "$.blueprint.skip_directive_outside_error_handler_visible": True,
            "$.hookId": "int",
            "$.isActive": "bool_false",
        },
        "scenario_run_once_called": False,
        "secret_output": False,
        "steps": [
            {"name": "preload_hooks_before_editor_load", "status": "ok"},
            {
                "name": "preload_data_structures_before_editor_load",
                "status": "ok",
            },
            {"name": "preload_data_stores_before_editor_load", "status": "ok"},
            {"name": "validate_blueprint_schema", "status": "ok"},
            {
                "name": "scenarios_create_inactive_filtered_webhook_datastore",
                "status": "ok",
            },
            {"name": "scenarios_get_export_bound_blueprint", "status": "ok"},
            {"name": "browser_editor_open_edit_mode", "status": "ok"},
            {"name": "scenario_activate_destructive_probe", "status": "ok"},
            {"name": "webhook_post_valid_payload", "status": "ok"},
            {"name": "executions_list_success", "status": "ok"},
            {"name": "data_store_records_list_observed", "status": "ok"},
            {"name": "scenario_deactivate", "status": "ok"},
            {"name": "cleanup_scenarios_delete", "status": "ok"},
            {"name": "cleanup_hooks_delete", "status": "ok"},
            {"name": "cleanup_data_stores_delete", "status": "ok"},
            {"name": "cleanup_data_structures_delete", "status": "ok"},
            {"name": "cleanup_scratch_resources_count", "status": "empty"},
        ],
    }

    summary = classify_make_webhook_datastore_quality_canary_evidence(
        evidence,
        required_capabilities=("webhook_post_valid_payload",),
    )

    assert summary["status"] == "fail"
    assert summary["request_contract_status"] == "fail"
    assert summary["export_contract_status"] == "fail"
    assert summary["browser_review_status"] == "fail"


def test_default_manifest_browser_evidence_has_no_chrome_fallback() -> None:
    """Persisted Browser evidence must not route live review back to Chrome."""
    payload = _read_json_object(
        REPO_ROOT / "src/languages/make/data/default_manifest_coverage.json"
    )
    browser_evidence = cast("JsonObject", payload["browser_evidence"])

    assert browser_evidence["preferred_surface"] == "Codex in-app Browser"
    assert browser_evidence["fallback_surface"] == "none_browser_only"
    assert "Chrome" not in json.dumps(browser_evidence, sort_keys=True)
    assert "make-auth" not in json.dumps(browser_evidence, sort_keys=True)


def test_make_api_blueprint_response_shape_fixture_matches_live_contract() -> (
    None
):
    """Sanitized live API evidence locks the current blueprint response path."""
    evidence = _read_json_object(REPO_ROOT / SHAPE_FIXTURE)

    summary = classify_make_api_blueprint_response_shapes(evidence)

    assert summary["status"] == "pass"
    assert summary["stable_blueprint_response_path"] == "$.response.blueprint"
    assert summary["draft_true_blueprint_available"] is False
    assert summary["draft_false_blueprint_available"] is True
    assert summary["no_query_blueprint_available"] is True
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["scenario_run_once_called"] is False
    assert summary["scenario_activation_called"] is False


def test_make_api_blueprint_response_inspector_is_sanitized() -> None:
    """The response inspector reports paths and shapes, never raw blueprint.

    values.
    """
    available = inspect_make_api_blueprint_response(
        {
            "response": {
                "blueprint": {
                    "name": "fixture",
                    "flow": [],
                    "metadata": {"version": 1, "instant": False},
                }
            }
        }
    )
    absent = inspect_make_api_blueprint_response(
        {"response": {"blueprint": None}}
    )

    assert available == {
        "status": "blueprint_available",
        "blueprint_available": True,
        "candidate_blueprint_paths": ("$.response.blueprint",),
        "blueprint_response_path": "$.response.blueprint",
        "blueprint_response_shape": "object",
    }
    assert absent["status"] == "blueprint_absent"
    assert absent["candidate_blueprint_paths"] == ()


def test_make_dashboard_navigation_landmarks_cover_live_parity_surfaces() -> (
    None
):
    """Browser dashboard landmarks identify the local evidence surface for live.

    parity gaps.
    """
    snapshot = _read_json_object(REPO_ROOT / DASHBOARD_FIXTURE)

    summary = validate_make_dashboard_navigation_landmarks(snapshot)

    assert summary["status"] == "pass"
    assert summary["browser_only"] is True
    assert summary["provider_api_call"] is False
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["missing_landmarks"] == ()
    capabilities = set(cast("tuple[str, ...]", summary["capability_evidence"]))
    assert {
        "connection_bind_to_module",
        "datastore_record_upsert_batch",
        "datastore_strict_schema_validation",
        "live_apply_package",
        "scenario_create",
        "scenario_export",
        "scenario_import",
        "webhook_bind_to_module",
        "webhook_create_or_select",
    } <= capabilities


def test_make_live_bridge_probe_fixture_proves_core_live_surfaces() -> None:
    """Sanitized live bridge evidence proves connection, webhook, and Data.

    Store.

    surfaces.
    """
    evidence = _read_json_object(REPO_ROOT / LIVE_BRIDGE_FIXTURE)

    summary = classify_make_live_bridge_probe_evidence(
        evidence,
        required_capabilities=(
            "connection_list_metadata",
            "webhook_create_or_select",
            "webhook_delete_or_cleanup",
            "datastore_create",
            "datastore_list",
            "datastore_record_create",
            "datastore_record_update",
            "datastore_record_upsert_batch",
            "datastore_record_delete_batch",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["live_make_called"] is True
    assert summary["provider_api_call"] is True
    assert summary["missing_capabilities"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["blocker_codes"] == ()


def test_make_datastore_record_probe_fixture_d915834d() -> None:
    """Existing-store probe proves schema-aware record create/update/delete.

    mechanics.
    """
    evidence = _read_json_object(REPO_ROOT / DATASTORE_RECORD_FIXTURE)

    summary = classify_make_live_bridge_probe_evidence(
        evidence,
        required_capabilities=(
            "datastore_list",
            "datastore_record_create",
            "datastore_record_update",
            "datastore_record_upsert_batch",
            "datastore_record_delete_batch",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["missing_capabilities"] == ()
    assert summary["blocker_codes"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False


def test_make_datastore_lifecycle_fixture_proves_disposable_store_cleanup() -> (
    None
):
    """Typed MCP evidence proves disposable Data Store lifecycle and cleanup.

    coverage.
    """
    evidence = _read_json_object(REPO_ROOT / DATASTORE_LIFECYCLE_FIXTURE)

    summary = classify_make_datastore_lifecycle_evidence(
        evidence,
        required_capabilities=(
            "datastore_create",
            "datastore_delete",
            "datastore_record_create",
            "datastore_record_update",
            "datastore_record_upsert_batch",
            "datastore_record_delete_batch",
            "datastore_update_schema",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_datastore_strict_schema_fixture_32586a23() -> None:
    """Typed Data Store evidence proves strict schema rejection and cleanup."""
    evidence = _read_json_object(
        REPO_ROOT / DATASTORE_STRICT_SCHEMA_VALIDATION_FIXTURE
    )

    summary = classify_make_datastore_strict_schema_validation_evidence(
        evidence,
        required_capabilities=(
            "datastore_create",
            "datastore_delete",
            "datastore_record_create",
            "datastore_record_delete_batch",
            "datastore_record_upsert_batch",
            "datastore_strict_schema_validation",
            "datastore_update_schema",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["validation_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_webhook_bind_lifecycle_fixture_fe1fa573() -> None:
    """Typed MCP evidence proves custom webhook binding and cleanup coverage."""
    evidence = _read_json_object(REPO_ROOT / WEBHOOK_BIND_LIFECYCLE_FIXTURE)

    summary = classify_make_webhook_bind_lifecycle_evidence(
        evidence,
        required_capabilities=(
            "scenario_create",
            "scenario_export",
            "webhook_bind_to_module",
            "webhook_create_or_select",
            "webhook_delete_or_cleanup",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_connection_bind_lifecycle_fixture_d40b4866() -> None:
    """Typed MCP evidence proves credential-free connection binding and cleanup.

    coverage.
    """
    evidence = _read_json_object(REPO_ROOT / CONNECTION_BIND_LIFECYCLE_FIXTURE)

    summary = classify_make_connection_bind_lifecycle_evidence(
        evidence,
        required_capabilities=(
            "connection_bind_to_module",
            "connection_list_metadata",
            "scenario_create",
            "scenario_export",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_live_apply_package_roundtrip_e7239ffd() -> None:
    """Typed MCP evidence proves a zero-trace Pancakes package can roundtrip.

    live.
    """
    evidence = _read_json_object(
        REPO_ROOT / LIVE_APPLY_PACKAGE_ROUNDTRIP_FIXTURE
    )

    summary = classify_make_live_apply_package_roundtrip_evidence(
        evidence,
        required_capabilities=(
            "live_apply_package",
            "scenario_create",
            "scenario_export",
            "scenario_interface",
            "scenario_delete",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["package_contract_status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_module_requirement_extraction_fixture_9a26dd2a() -> None:
    """Component extraction, not isinvalid alone, proves missing account.

    targets.
    """
    evidence = _read_json_object(
        REPO_ROOT / MODULE_REQUIREMENT_EXTRACTION_FIXTURE
    )

    summary = classify_make_module_requirement_extraction_evidence(
        evidence,
        required_capabilities=(
            "scenario_module_error_inspection",
            "connection_requirement_extraction",
            "scenario_create",
            "scenario_export",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["extraction_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_runtime_resource_requirement_fixture_f01571ed() -> None:
    """Component extraction proves missing webhook and Data Store module.

    targets.
    """
    evidence = _read_json_object(
        REPO_ROOT / RUNTIME_RESOURCE_REQUIREMENT_EXTRACTION_FIXTURE
    )

    summary = classify_make_runtime_resource_requirement_extraction_evidence(
        evidence,
        required_capabilities=(
            "scenario_module_error_inspection",
            "runtime_resource_requirement_extraction",
            "webhook_requirement_extraction",
            "datastore_requirement_extraction",
            "scenario_create",
            "scenario_export",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["extraction_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_probe_labels"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_scenario_interface_schedule_fixture_f9181635() -> None:
    """Required scenario inputs are accepted only after the schedule becomes.

    on-demand.
    """
    evidence = _read_json_object(
        REPO_ROOT / SCENARIO_INTERFACE_SCHEDULE_FIXTURE
    )

    summary = classify_make_scenario_interface_schedule_evidence(
        evidence,
        required_capabilities=(
            "scenario_create",
            "scenario_export",
            "scenario_interface",
            "scenario_interface_update",
            "scenario_update",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["export_contract_status"] == "pass"
    assert summary["interface_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["delete_response_status"] == "pass"
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_module_configuration_validation_fixture_cd4c94ec() -> None:
    """Typed module validation reports required mapper fields and schema.

    details.
    """
    evidence = _read_json_object(
        REPO_ROOT / MODULE_CONFIGURATION_VALIDATION_FIXTURE
    )

    summary = classify_make_module_configuration_validation_evidence(
        evidence,
        required_capabilities=(
            "module_configuration_validation",
            "required_mapper_field_validation",
            "module_schema_extraction",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["invalid_config_contract_status"] == "pass"
    assert summary["valid_config_contract_status"] == "pass"
    assert summary["writes_performed"] is False
    assert summary["write_operations"] == ()
    assert summary["missing_capabilities"] == ()
    assert summary["missing_probe_labels"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_scenario_run_once_fixture_proves_execution_contract() -> None:
    """Typed MCP evidence proves the bounded run-once and execution-list.

    contract.
    """
    evidence = _read_json_object(REPO_ROOT / SCENARIO_RUN_ONCE_FIXTURE)

    summary = classify_make_scenario_run_once_evidence(
        evidence,
        required_capabilities=(
            "scenario_create",
            "scenario_activate",
            "scenario_run_once",
            "scenario_execution_list",
            "scenario_deactivate",
            "scenario_delete",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["execution_contract_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["scenario_activation_called"] is True
    assert summary["scenario_run_once_called"] is True
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_hook_configuration_validation_fixture_879d520f() -> None:
    """Typed hook validation proves gateway webhook required default config.

    fields.
    """
    evidence = _read_json_object(
        REPO_ROOT / HOOK_CONFIGURATION_VALIDATION_FIXTURE
    )

    summary = classify_make_hook_configuration_validation_evidence(
        evidence,
        required_capabilities=(
            "webhook_configuration_validation",
            "webhook_create_or_select",
        ),
    )

    assert summary["status"] == "pass"
    assert summary["schema_contract_status"] == "pass"
    assert summary["validation_contract_status"] == "pass"
    assert summary["writes_performed"] is False
    assert summary["write_operations"] == ()
    assert summary["missing_capabilities"] == ()
    assert summary["missing_steps"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    assert summary["unsafe_flags"] == ()


def test_make_scenario_designer_roundtrip_fixture_c95448dd() -> None:
    """Scenario designer parity is an offline mirror, not a future browser.

    dependency.
    """
    evidence = _read_json_object(
        REPO_ROOT / SCENARIO_DESIGNER_ROUNDTRIP_FIXTURE
    )

    summary = classify_make_scenario_designer_roundtrip_evidence(evidence)

    assert summary["status"] == "pass"
    assert summary["request_shape_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["unsafe_flags"] == ()
    assert summary["api_auto_align_injected_coordinates"] is False
    assert summary["api_designer_message_injection"] is False
    assert summary["offline_mirror_required"] is True
    capabilities = set(cast("tuple[str, ...]", summary["capability_evidence"]))
    assert capabilities == {
        "scenario_auto_align",
        "scenario_module_error_inspection",
    }
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False


def test_make_scenario_mutation_contract_fixture_proves_live_apply_paths() -> (
    None
):
    """Scenario mutation evidence locks the Make API request and response.

    contract.
    """
    evidence = _read_json_object(REPO_ROOT / SCENARIO_MUTATION_CONTRACT_FIXTURE)

    summary = classify_make_scenario_mutation_contract_evidence(evidence)

    assert summary["status"] == "pass"
    assert summary["request_contract_status"] == "pass"
    assert summary["create_id_path"] == "$.scenario.id"
    assert summary["export_blueprint_path"] == "$.response.blueprint"
    assert summary["delete_id_path"] == "$.scenario"
    assert summary["created_scenario_list_row_status"] == "pass"
    assert summary["cleanup_ok"] is True
    assert summary["scenario_created_inactive"] is True
    assert summary["unsafe_flags"] == ()
    assert summary["credential_value_transfer"] is False
    assert summary["secret_output"] is False
    capabilities = set(cast("tuple[str, ...]", summary["capability_evidence"]))
    assert {
        "live_apply_package",
        "scenario_create",
        "scenario_export",
    } <= capabilities


def test_live_parity_evidence_covers_previous_missing_capability_set() -> None:
    """The combined Browser/API evidence accounts for the prior live-parity gap.

    list.
    """
    covered: set[str] = set()
    for summary in _live_parity_capability_evidence_summaries():
        covered.update(
            cast("tuple[str, ...]", summary.get("capability_evidence", ()))
        )
        covered.update(
            cast("tuple[str, ...]", summary.get("capabilities_proven", ()))
        )

    assert {
        "connection_bind_to_module",
        "datastore_record_upsert_batch",
        "live_apply_package",
        "module_configuration_validation",
        "scenario_auto_align",
        "scenario_interface_update",
        "scenario_module_error_inspection",
        "scenario_run_once",
        "webhook_bind_to_module",
        "webhook_configuration_validation",
        "webhook_create_or_select",
    } <= covered


def _live_parity_capability_evidence_summaries() -> tuple[JsonObject, ...]:
    return (
        validate_make_dashboard_navigation_landmarks(
            _read_json_object(REPO_ROOT / DASHBOARD_FIXTURE)
        ),
        classify_make_live_bridge_probe_evidence(
            _read_json_object(REPO_ROOT / LIVE_BRIDGE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_live_bridge_probe_evidence(
            _read_json_object(REPO_ROOT / DATASTORE_RECORD_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_datastore_lifecycle_evidence(
            _read_json_object(REPO_ROOT / DATASTORE_LIFECYCLE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_datastore_strict_schema_validation_evidence(
            _read_json_object(
                REPO_ROOT / DATASTORE_STRICT_SCHEMA_VALIDATION_FIXTURE
            ),
            required_capabilities=(),
        ),
        classify_make_webhook_bind_lifecycle_evidence(
            _read_json_object(REPO_ROOT / WEBHOOK_BIND_LIFECYCLE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_connection_bind_lifecycle_evidence(
            _read_json_object(REPO_ROOT / CONNECTION_BIND_LIFECYCLE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_live_apply_package_roundtrip_evidence(
            _read_json_object(REPO_ROOT / LIVE_APPLY_PACKAGE_ROUNDTRIP_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_module_requirement_extraction_evidence(
            _read_json_object(
                REPO_ROOT / MODULE_REQUIREMENT_EXTRACTION_FIXTURE
            ),
            required_capabilities=(),
        ),
        classify_make_runtime_resource_requirement_extraction_evidence(
            _read_json_object(
                REPO_ROOT / RUNTIME_RESOURCE_REQUIREMENT_EXTRACTION_FIXTURE
            ),
            required_capabilities=(),
        ),
        classify_make_scenario_interface_schedule_evidence(
            _read_json_object(REPO_ROOT / SCENARIO_INTERFACE_SCHEDULE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_module_configuration_validation_evidence(
            _read_json_object(
                REPO_ROOT / MODULE_CONFIGURATION_VALIDATION_FIXTURE
            ),
            required_capabilities=(),
        ),
        classify_make_scenario_run_once_evidence(
            _read_json_object(REPO_ROOT / SCENARIO_RUN_ONCE_FIXTURE),
            required_capabilities=(),
        ),
        classify_make_hook_configuration_validation_evidence(
            _read_json_object(
                REPO_ROOT / HOOK_CONFIGURATION_VALIDATION_FIXTURE
            ),
            required_capabilities=(),
        ),
        classify_make_scenario_designer_roundtrip_evidence(
            _read_json_object(REPO_ROOT / SCENARIO_DESIGNER_ROUNDTRIP_FIXTURE)
        ),
        classify_make_scenario_mutation_contract_evidence(
            _read_json_object(REPO_ROOT / SCENARIO_MUTATION_CONTRACT_FIXTURE)
        ),
    )


def _sqlite_raw_spec_manifest() -> RawSpecManifest:
    bundle = load_sqlite_raw_spec_bundle(
        database_path=REPO_ROOT / DEFAULT_RAW_SPEC_SQLITE_DATABASE
    )
    assert bundle is not None, (
        "Expected SQLite raw-spec manifest rows in pancakes.sqlite."
    )
    return bundle.manifest


def _read_json_object(path: Path) -> JsonObject:
    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(raw, dict), f"Expected JSON object fixture: {path}"
    return cast("JsonObject", raw)
