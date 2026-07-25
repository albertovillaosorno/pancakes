# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.live-roundtrip-review-tool
# - 001064#repo.make-knowledge.live-probe-evidence
# - 001068#repo.operator-commands.command-registry
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make live Browser validation ledger and smoke-plan helpers.

Boundary contract:
- Owns: deterministic local ledgering for Make live Browser validation work.
- Must not: call Make.com, read browser cookies, import scenarios, or run
scenarios.
- Allows: paginating local catalog entries and returning zero-operation Browser
review steps.
- Split when: a service-owned Browser runner records reviewed live evidence
automatically.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

from catalog.identifiers import module_id
from catalog.json_payloads import normalize_json_object, payload_fingerprint

from languages.make.default_manifest_coverage import (
    MakeDefaultManifestCoverageFact,
    make_default_manifest_coverage_facts,
)
from languages.make.raw_specs import load_raw_spec_manifest, parse_make_raw_spec
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_MANIFEST,
    DEFAULT_RAW_SPEC_SQLITE_DATABASE,
    resolve_repo_relative_path,
)
from languages.make.raw_specs.sqlite_store import (
    load_sqlite_raw_spec_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from catalog.models import CatalogModuleKind

    from languages.make.raw_specs.models import (
        JsonObject,
        RawSpecManifest,
        RawSpecRecord,
    )

MAKE_LIVE_BROWSER_LEDGER_STATUS: Final = "browser_validation_required"
MAKE_LIVE_BROWSER_ENTRY_STATUS: Final = (
    "live_browser_import_export_not_recorded"
)
MAKE_LIVE_BROWSER_DEFAULT_LIMIT: Final = 50
MAKE_LIVE_BROWSER_MAX_LIMIT: Final = 500
MAKE_LIVE_BROWSER_VALIDATION_GATES: Final[tuple[str, ...]] = (
    "preload_webhooks_data_structures_data_stores_before_editor_load ",
    "browser_import_inactive_scratch_scenario ",
    "browser_editor_loaded ",
    "auto_align_reviewed_when_available ",
    "designer_diagnostics_reviewed ",
    "live_export_or_copy_blueprint_captured ",
    "generated_vs_live_blueprint_diff_classified ",
    "scratch_scenario_cleaned_or_archived",
)
MAKE_LIVE_BROWSER_FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "run_once ",
    "scenario_activation ",
    "schedule_enablement ",
    "connection_creation ",
    "credential_save ",
    "operation_credit_consumption",
)
MAKE_API_BLUEPRINT_RESPONSE_PATH: Final = "$.response.blueprint"
MAKE_API_BLUEPRINT_SHAPE_LABELS: Final[tuple[str, ...]] = (
    "draft_true ",
    "draft_false ",
    "no_query",
)
MAKE_SCENARIO_DESIGNER_ROUNDTRIP_LABELS: Final[tuple[str, ...]] = (
    "json_parse_no_messages ",
    "two_nodes_no_coordinates",
)
MAKE_LIVE_APPLY_PACKAGE_ROUNDTRIP_MODULE_COUNT: Final = 2
MAKE_MODULE_REQUIREMENT_PROBE_APP_VERSION: Final = 4
MAKE_MODULE_REQUIREMENT_PROBE_CONNECTION_COUNT: Final = 1
MAKE_MODULE_REQUIREMENT_PROBE_MODULE_ID: Final = 1
MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_APP_VERSION: Final = 1
MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_COUNT: Final = 2
MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_MODULE_ID: Final = 1
MAKE_RUNTIME_RESOURCE_REQUIREMENT_LABELS: Final[tuple[str, ...]] = (
    "webhook_missing_hook ",
    "datastore_missing_store",
)
MAKE_SCENARIO_INTERFACE_FIELD_COUNT: Final = 2
MAKE_SCENARIO_INTERFACE_MODULE_VERSION: Final = 1
MAKE_SCENARIO_INTERFACE_REQUIRED_INPUT_COUNT: Final = 1
MAKE_MODULE_CONFIGURATION_VALIDATION_PROBE_COUNT: Final = 2
MAKE_MODULE_CONFIGURATION_VALIDATION_LABELS: Final[tuple[str, ...]] = (
    "parse_json_missing_required_mapper_json ",
    "parse_json_valid_required_mapper_json",
)
MAKE_MODULE_CONFIGURATION_VALIDATION_APP_VERSION: Final = 1
MAKE_MODULE_CONFIGURATION_EXPECT_FIELD_COUNT: Final = 1
MAKE_SCENARIO_RUN_ONCE_MODULE_VERSION: Final = 1
MAKE_SCENARIO_RUN_ONCE_OPERATION_COUNT: Final = 1
MAKE_HOOK_CONFIGURATION_REQUIRED_DEFAULT_FIELDS: Final[tuple[str, ...]] = (
    "headers ",
    "method ",
    "stringify",
)
MAKE_DATASTORE_STRICT_SCHEMA_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "request_id",
)
MAKE_DATASTORE_STRICT_SCHEMA_TYPED_FIELDS: Final[tuple[str, ...]] = (
    "amount ",
    "request_id ",
    "status",
)
MAKE_DATASTORE_STRICT_SCHEMA_REJECTION_COUNT: Final = 2
MAKE_QUALITY_CANARY_FILTER_COUNT: Final = 1
MAKE_QUALITY_CANARY_MIN_EXECUTION_OPERATIONS: Final = 2
MAKE_QUALITY_CANARY_NOTE_COUNT: Final = 3
MAKE_QUALITY_CANARY_SUCCESS_HTTP_STATUS: Final = 200
MAKE_DASHBOARD_REQUIRED_LANDMARKS: Final[dict[str, tuple[str, ...]]] = {
    "scenarios_nav": (
        "scenario_export ",
        "scenario_import ",
        "scenario_list",
    ),
    "credentials_nav": (
        "connection_list_metadata ",
        "connection_bind_to_module",
    ),
    "webhooks_nav": ("webhook_create_or_select", "webhook_bind_to_module"),
    "data_stores_nav": ("datastore_list", "datastore_record_upsert_batch"),
    "data_structures_nav": (
        "datastore_create ",
        "datastore_record_upsert_batch ",
        "datastore_strict_schema_validation",
    ),
    "mcp_toolboxes_nav": ("live_apply_package",),
    "create_scenario_entrypoint": ("scenario_create",),
    "templates_nav": ("scenario_import",),
}


class MakeLiveBrowserValidationEntry(NamedTuple):
    """One catalog entry that needs live Browser import/export validation."""

    entry_id: str
    source_label: str
    source_ref: str
    module_id: str
    app_slug: str
    app_version: str
    module_kind: CatalogModuleKind
    internal_name: str
    display_name: str
    status: str
    blocker_code: str


class MakeLiveBrowserValidationSources(NamedTuple):
    """Catalog sources used to build one validation ledger page."""

    repo_root: Path
    manifest: RawSpecManifest
    payloads_by_ref: Mapping[str, JsonObject] | None
    default_facts: tuple[MakeDefaultManifestCoverageFact, ...]
    raw_spec_entry_count: int


def build_make_live_browser_validation_ledger(
    *,
    repo_root: Path,
    offset: int = 0,
    limit: int = MAKE_LIVE_BROWSER_DEFAULT_LIMIT,
) -> JsonObject:
    """Return a paged full-catalog live Browser validation ledger.

    Returns:
    A JSON-ready ledger page covering every local catalog entry by pagination.
    """
    _validate_paging(offset=offset, limit=limit)
    sqlite_bundle = load_sqlite_raw_spec_bundle(
        database_path=resolve_repo_relative_path(
            repo_root, DEFAULT_RAW_SPEC_SQLITE_DATABASE
        )
    )
    manifest = (
        sqlite_bundle.manifest
        if sqlite_bundle is not None
        else load_raw_spec_manifest(
            resolve_repo_relative_path(repo_root, DEFAULT_RAW_SPEC_MANIFEST)
        )
    )
    default_facts = make_default_manifest_coverage_facts(repo_root)
    raw_spec_entry_count = sum(
        record.module_count for record in manifest.records
    )
    default_manifest_entry_count = len(default_facts)
    total_entry_count = raw_spec_entry_count + default_manifest_entry_count
    sources = MakeLiveBrowserValidationSources(
        repo_root=repo_root,
        manifest=manifest,
        payloads_by_ref=None
        if sqlite_bundle is None
        else sqlite_bundle.payloads_by_ref,
        default_facts=default_facts,
        raw_spec_entry_count=raw_spec_entry_count,
    )
    entries = tuple(
        _paged_entries(
            sources=sources,
            offset=offset,
            limit=limit,
        )
    )
    return {
        "status": MAKE_LIVE_BROWSER_LEDGER_STATUS,
        "scope": (
            "full_make_catalog_local_manifest_plus_default_manifest_coverage"
        ),
        "offset": offset,
        "limit": limit,
        "returned_entry_count": len(entries),
        "total_entry_count": total_entry_count,
        "raw_spec_record_count": len(manifest.records),
        "raw_spec_entry_count": raw_spec_entry_count,
        "default_manifest_entry_count": default_manifest_entry_count,
        "documented_blocker_count": total_entry_count,
        "live_browser_validated_count": 0,
        "manifest_sha256": manifest.manifest_sha256,
        "required_gates": list(MAKE_LIVE_BROWSER_VALIDATION_GATES),
        "forbidden_actions": list(MAKE_LIVE_BROWSER_FORBIDDEN_ACTIONS),
        "browser_smoke_plan": make_live_browser_smoke_plan(),
        "entries": [_entry_payload(entry) for entry in entries],
        "fingerprint": payload_fingerprint(
            {
                "manifest_sha256": manifest.manifest_sha256,
                "offset": offset,
                "limit": limit,
                "entry_ids": [entry.entry_id for entry in entries],
            }
        ),
    }


def make_live_browser_smoke_plan() -> JsonObject:
    """Return the repeatable zero-operation Browser smoke plan for roulette."""
    return {
        "status": "operator_gated_browser_smoke_ready",
        "live_canary_status": (
            "destructive_webhook_datastore_canary_passed_and_cleaned"
        ),
        "fully_automated_production_status": (
            "local_mcp_ready_live_canary_passed"
        ),
        "preferred_surface": "Codex in-app Browser ",
        "fallback_surface": "none_browser_only",
        "headless_allowed_for_first_pass": False,
        "operation_credit_budget": 0,
        "mutation_scope": "inactive scratch scenario only",
        "resource_creation_order": [
            "data_structure ",
            "data_store ",
            "webhook ",
            "scenario",
        ],
        "resource_creation_order_human": (
            "Data Structure -> Data Store -> Webhook -> Scenario"
        ),
        "cleanup_semantics": (
            "Scratch resources are deleted after destructive proof; absence "
            "in Make UI means "
            "cleanup passed, not that the Data Structure, Data Store, "
            "Webhook, or Scenario "
            "were skipped."
        ),
        "required_start_url": "https://us2.make.com/*/scenarios",
        "steps": [
            "Open the logged-in Make scenarios page in Browser.",
            (
                "Create and bind live resources in this exact order: Data "
                "Structure, "
                "Data Store, Webhook, Scenario."
            ),
            (
                "Create or open an inactive scratch scenario dedicated to "
                "validation."
            ),
            "Import the generated blueprint without enabling scheduling.",
            (
                "Bind required Data Store, webhook, and app connection "
                "resources without "
                "saving credentials."
            ),
            "Confirm the editor loads and never click Run once.",
            (
                "Run auto-align only when the editor exposes it without "
                "scenario execution."
            ),
            (
                "Record designer diagnostics for setup, setupreq, epochreq, "
                "link, and trigger order."
            ),
            (
                "Export or copy the blueprint and diff it against the "
                "generated "
                "payload."
            ),
            "Compare generated and exported blueprint fingerprints for parity.",
            (
                "Delete scratch resources after evidence capture; "
                "cleaned-up resources are "
                "expected to be absent."
            ),
        ],
        "forbidden_actions": list(MAKE_LIVE_BROWSER_FORBIDDEN_ACTIONS),
        "evidence_outputs": [
            "validation ledger entry id ",
            "generated blueprint fingerprint ",
            "live exported blueprint fingerprint",
            (
                "preloaded webhook, data-structure, and data-store resource "
                "summaries"
            ),
            "diagnostic categories ",
            "diff classification ",
            "cleanup outcome",
        ],
    }


def inspect_make_api_blueprint_response(
    payload: Mapping[str, object],
) -> JsonObject:
    """Return the sanitized blueprint location contract for one Make API.

    response.

    Returns:
        JSON-ready shape metadata without copying the raw blueprint.
    """
    response = payload.get("response")
    if not _is_json_object(response):
        return {
            "status": "response_missing",
            "blueprint_available": False,
            "candidate_blueprint_paths": (),
            "blueprint_response_path": None,
            "blueprint_response_shape": "missing",
        }
    blueprint = response.get("blueprint")
    shape = _blueprint_response_shape(blueprint)
    available = shape in {"object", "json_text_object"}
    return {
        "status": "blueprint_available" if available else "blueprint_absent",
        "blueprint_available": available,
        "candidate_blueprint_paths": (MAKE_API_BLUEPRINT_RESPONSE_PATH,)
        if available
        else (),
        "blueprint_response_path": MAKE_API_BLUEPRINT_RESPONSE_PATH
        if available
        else None,
        "blueprint_response_shape": shape,
    }


def classify_make_api_blueprint_response_shapes(
    evidence: Mapping[str, object],
) -> JsonObject:
    """Classify sanitized Make API blueprint response shape evidence.

    Returns:
        JSON-ready status and expected response-path evidence.
    """
    reports = _shape_reports(evidence)
    reports_by_label = {
        str(report.get("label")): report
        for report in reports
        if isinstance(report.get("label"), str)
    }
    missing_labels = tuple(
        label
        for label in MAKE_API_BLUEPRINT_SHAPE_LABELS
        if label not in reports_by_label
    )
    draft_true_paths = _candidate_paths(reports_by_label.get("draft_true"))
    draft_false_paths = _candidate_paths(reports_by_label.get("draft_false"))
    no_query_paths = _candidate_paths(reports_by_label.get("no_query"))
    status = (
        "pass"
        if not missing_labels
        and not draft_true_paths
        and MAKE_API_BLUEPRINT_RESPONSE_PATH in draft_false_paths
        and MAKE_API_BLUEPRINT_RESPONSE_PATH in no_query_paths
        else "fail"
    )
    return {
        "status": status,
        "stable_blueprint_response_path": MAKE_API_BLUEPRINT_RESPONSE_PATH,
        "draft_true_blueprint_available": bool(draft_true_paths),
        "draft_false_blueprint_available": MAKE_API_BLUEPRINT_RESPONSE_PATH
        in draft_false_paths,
        "no_query_blueprint_available": MAKE_API_BLUEPRINT_RESPONSE_PATH
        in no_query_paths,
        "missing_shape_labels": missing_labels,
        "shape_labels": tuple(reports_by_label),
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "scenario_run_once_called": bool(
            evidence.get("scenario_run_once_called")
        ),
        "scenario_activation_called": bool(
            evidence.get("scenario_activation_called")
        ),
        "cleanup_status": str(evidence.get("cleanup_status") or "unknown"),
    }


def validate_make_dashboard_navigation_landmarks(
    snapshot: Mapping[str, object],
) -> JsonObject:
    """Return local Browser landmark evidence for live-parity capability.

    surfaces.

    Returns:
    JSON-ready capability evidence derived from Browser navigation landmarks.
    """
    missing_landmarks = tuple(
        landmark
        for landmark in MAKE_DASHBOARD_REQUIRED_LANDMARKS
        if snapshot.get(landmark) is not True
    )
    required_landmarks = MAKE_DASHBOARD_REQUIRED_LANDMARKS.items()
    capabilities = tuple(
        capability
        for landmark, mapped_capabilities in required_landmarks
        if snapshot.get(landmark) is True
        for capability in mapped_capabilities
    )
    return {
        "status": "pass" if not missing_landmarks else "fail ",
        "surface": "codex_in_app_browser_make_dashboard",
        "browser_only": True,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "missing_landmarks": missing_landmarks,
        "capability_evidence": tuple(sorted(set(capabilities))),
    }


def classify_make_live_bridge_probe_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized live Make API bridge evidence without exposing live.

    IDs.

    Returns:
    JSON-ready status for required capabilities, cleanup posture, and secret
    posture.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_activation_called ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )
    cleanup_ok = (
        evidence.get("cleanup_status") == "scratch_resources_deleted"
        or evidence.get("scratch_key_deleted") is True
    )
    blockers = tuple(
        str(blocker["code"])
        for blocker in _json_object_tuple(evidence.get("blockers"))
        if isinstance(blocker.get("code"), str)
    )
    status = (
        "pass"
        if not missing_capabilities and not unsafe_flags and cleanup_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "blocker_codes": blockers,
        "cleanup_ok": cleanup_ok,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_datastore_lifecycle_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized typed-MCP Data Store lifecycle evidence.

    Returns:
    JSON-ready status proving disposable Data Structure, Data Store, and record
    cleanup.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_activation_called ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )
    steps = _json_object_tuple(evidence.get("steps"))
    completed_steps = {
        str(step["name"])
        for step in steps
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "data_structures_create ",
        "data_stores_create ",
        "data_store_records_create ",
        "data_store_records_update ",
        "data_store_records_list ",
        "data_store_records_delete ",
        "data_stores_delete ",
        "data_structures_delete ",
        "cleanup_data_stores_list ",
        "cleanup_data_structures_list",
    )
    missing_steps = tuple(
        step for step in required_steps if step not in completed_steps
    )
    request_contract_ok = _datastore_lifecycle_request_contract_ok(evidence)
    cleanup_ok = _datastore_lifecycle_cleanup_ok(evidence)
    delete_responses_ok = (
        evidence.get("record_delete_response") == "Records have been deleted."
        and evidence.get("data_store_delete_response")
        == "Data store has been deleted."
        and evidence.get("data_structure_delete_response")
        == "Data structure has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and cleanup_ok
        and delete_responses_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_responses_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_webhook_bind_lifecycle_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized typed-MCP webhook bind evidence.

    Returns:
    JSON-ready status proving hook creation, inactive scenario bind, export, and
    cleanup.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_webhook_bind_steps(evidence)
    request_contract_ok = _webhook_bind_request_contract_ok(evidence)
    export_contract_ok = _webhook_bind_export_contract_ok(evidence)
    cleanup_ok = _webhook_bind_cleanup_ok(evidence)
    delete_responses_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
        and evidence.get("hook_delete_response") == "Hook has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and export_contract_ok
        and cleanup_ok
        and delete_responses_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_responses_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_webhook_datastore_quality_canary_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify a destructive webhook-to-Data-Store live canary.

    Returns:
    JSON-ready status proving resource preload, edit-mode review, notes, a
    valid-route
    filter, no discard/skip branch, one authorized execution, Data Store output,
        deactivation, and cleanup.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_quality_canary_flags(evidence)
    missing_steps = _missing_webhook_datastore_quality_canary_steps(evidence)
    resource_preload_ok = _quality_canary_resource_preload_ok(evidence)
    request_contract_ok = _quality_canary_request_contract_ok(evidence)
    export_contract_ok = _quality_canary_export_contract_ok(evidence)
    browser_review_ok = _quality_canary_browser_review_ok(evidence)
    functional_probe_ok = _quality_canary_functional_probe_ok(evidence)
    cleanup_ok = _quality_canary_cleanup_ok(evidence)
    delete_responses_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
        and evidence.get("hook_delete_response") == "Hook has been deleted."
        and evidence.get("data_store_delete_response")
        == "Data store has been deleted."
        and evidence.get("data_structure_delete_response")
        == "Data structure has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and resource_preload_ok
        and request_contract_ok
        and export_contract_ok
        and browser_review_ok
        and functional_probe_ok
        and cleanup_ok
        and delete_responses_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "resource_preload_status": "pass" if resource_preload_ok else "fail ",
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail ",
        "browser_review_status": "pass" if browser_review_ok else "fail ",
        "functional_probe_status": "pass" if functional_probe_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_responses_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "scenario_activation_called": evidence.get("scenario_activation_called")
        is True,
        "scenario_run_once_called": bool(
            evidence.get("scenario_run_once_called")
        ),
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_connection_bind_lifecycle_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized typed-MCP connection bind evidence.

    Returns:
    JSON-ready status proving credential-free metadata discovery, inactive bind,
    and cleanup.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_connection_bind_steps(evidence)
    request_contract_ok = _connection_bind_request_contract_ok(evidence)
    export_contract_ok = _connection_bind_export_contract_ok(evidence)
    cleanup_ok = _connection_bind_cleanup_ok(evidence)
    delete_response_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and export_contract_ok
        and cleanup_ok
        and delete_response_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_response_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_live_apply_package_roundtrip_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized typed-MCP live apply evidence for a Pancakes package.

    Returns:
        JSON-ready status proving a zero-trace local package can roundtrip live.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_live_apply_package_steps(evidence)
    package_contract_ok = _live_apply_package_source_contract_ok(evidence)
    request_contract_ok = _live_apply_package_request_contract_ok(evidence)
    export_contract_ok = _live_apply_package_export_contract_ok(evidence)
    cleanup_ok = _live_apply_package_cleanup_ok(evidence)
    delete_response_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and package_contract_ok
        and request_contract_ok
        and export_contract_ok
        and cleanup_ok
        and delete_response_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "package_contract_status": "pass" if package_contract_ok else "fail ",
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_response_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_module_requirement_extraction_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized module-requirement extraction evidence.

    Returns:
    JSON-ready status proving extraction is required for missing connection
    targets.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_module_requirement_extraction_steps(evidence)
    request_contract_ok = _module_requirement_request_contract_ok(evidence)
    export_contract_ok = _module_requirement_export_contract_ok(evidence)
    extraction_contract_ok = _module_requirement_extraction_contract_ok(
        evidence
    )
    cleanup_ok = _module_requirement_cleanup_ok(evidence)
    delete_response_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and export_contract_ok
        and extraction_contract_ok
        and cleanup_ok
        and delete_response_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail ",
        "extraction_contract_status": "pass"
        if extraction_contract_ok
        else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_response_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_runtime_resource_requirement_extraction_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized runtime-resource requirement extraction evidence.

    Returns:
    JSON-ready status proving extraction is required for missing webhook and
    Data Store
        targets.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    probes = _runtime_resource_requirement_probes_by_label(evidence)
    missing_labels = tuple(
        label
        for label in MAKE_RUNTIME_RESOURCE_REQUIREMENT_LABELS
        if label not in probes
    )
    missing_steps = _missing_runtime_resource_requirement_extraction_steps(
        evidence
    )
    request_contract_ok = _runtime_resource_requirement_request_contract_ok(
        probes
    )
    export_contract_ok = _runtime_resource_requirement_export_contract_ok(
        probes
    )
    extraction_contract_ok = (
        _runtime_resource_requirement_extraction_contract_ok(probes)
    )
    cleanup_ok = _runtime_resource_requirement_cleanup_ok(evidence)
    delete_response_ok = all(
        probes[label].get("scenario_delete_response")
        == "Scenario has been deleted."
        for label in MAKE_RUNTIME_RESOURCE_REQUIREMENT_LABELS
        if label in probes
    )
    status = (
        "pass"
        if len(probes) == MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_COUNT
        and not missing_capabilities
        and not missing_labels
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and export_contract_ok
        and extraction_contract_ok
        and cleanup_ok
        and delete_response_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_probe_labels": missing_labels,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail ",
        "extraction_contract_status": "pass"
        if extraction_contract_ok
        else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_response_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_module_configuration_validation_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized module-configuration validation evidence.

    Returns:
    JSON-ready status proving Make's typed validator reports required mapper
    fields and
        response schemas without writing live scenario state.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    probes = _module_configuration_validation_probes_by_label(evidence)
    missing_labels = tuple(
        label
        for label in MAKE_MODULE_CONFIGURATION_VALIDATION_LABELS
        if label not in probes
    )
    missing_steps = _missing_module_configuration_validation_steps(evidence)
    invalid_contract_ok = _module_configuration_invalid_contract_ok(
        probes.get("parse_json_missing_required_mapper_json")
    )
    valid_contract_ok = _module_configuration_valid_contract_ok(
        probes.get("parse_json_valid_required_mapper_json")
    )
    status = (
        "pass"
        if len(probes) == MAKE_MODULE_CONFIGURATION_VALIDATION_PROBE_COUNT
        and not missing_capabilities
        and not missing_labels
        and not missing_steps
        and not unsafe_flags
        and invalid_contract_ok
        and valid_contract_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_probe_labels": missing_labels,
        "missing_steps": missing_steps,
        "invalid_config_contract_status": "pass"
        if invalid_contract_ok
        else "fail",
        "valid_config_contract_status": "pass" if valid_contract_ok else "fail",
        "write_operations": (),
        "writes_performed": False,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_scenario_run_once_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized run-once execution evidence for a scratch scenario.

    Returns:
    JSON-ready status proving responsive run and execution-list shapes without
    persisting live
        IDs, names, emails, or payload values.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_run_once_probe_flags(evidence)
    missing_steps = _missing_scenario_run_once_steps(evidence)
    request_contract_ok = _scenario_run_once_request_contract_ok(evidence)
    execution_contract_ok = _scenario_run_once_execution_contract_ok(evidence)
    cleanup_ok = _scenario_run_once_cleanup_ok(evidence)
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and execution_contract_ok
        and cleanup_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "execution_contract_status": "pass"
        if execution_contract_ok
        else "fail",
        "cleanup_ok": cleanup_ok,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "scenario_activation_called": evidence.get("scenario_activation_called")
        is True,
        "scenario_run_once_called": evidence.get("scenario_run_once_called")
        is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_hook_configuration_validation_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized hook configuration validation evidence.

    Returns:
    JSON-ready status proving required gateway webhook config fields before hook
    creation.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_hook_configuration_validation_steps(evidence)
    schema_contract_ok = _hook_configuration_schema_contract_ok(evidence)
    validation_contract_ok = _hook_configuration_validation_contract_ok(
        evidence
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and schema_contract_ok
        and validation_contract_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "schema_contract_status": "pass" if schema_contract_ok else "fail ",
        "validation_contract_status": "pass"
        if validation_contract_ok
        else "fail",
        "write_operations": (),
        "writes_performed": False,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def classify_make_datastore_strict_schema_validation_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized Data Store strict-schema validation evidence.

    Returns:
    JSON-ready status proving Make rejects missing required fields and invalid
    numeric values.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_datastore_strict_schema_steps(evidence)
    request_contract_ok = _datastore_strict_schema_request_contract_ok(evidence)
    validation_contract_ok = _datastore_strict_schema_validation_contract_ok(
        evidence
    )
    cleanup_ok = _datastore_lifecycle_cleanup_ok(evidence)
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and validation_contract_ok
        and cleanup_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "validation_contract_status": "pass"
        if validation_contract_ok
        else "fail",
        "cleanup_ok": cleanup_ok,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def _unsafe_live_probe_flags(evidence: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_activation_called ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )


def _unsafe_quality_canary_flags(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    unsafe_flags = [
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    ]
    if (
        evidence.get("scenario_activation_called") is True
        and evidence.get("operator_destructive_canary_authorized") is not True
    ):
        unsafe_flags.append(
            "scenario_activation_without_destructive_canary_authorization"
        )
    return tuple(unsafe_flags)


def _missing_datastore_strict_schema_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "data_structures_create_strict_schema ",
        "data_stores_create_strict_store ",
        "data_store_records_create_invalid_rejected ",
        "data_store_records_create_valid_accepted ",
        "data_store_records_delete_valid ",
        "data_stores_delete ",
        "data_structures_delete ",
        "cleanup_data_stores_list ",
        "cleanup_data_structures_list",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_hook_configuration_validation_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "hook_config_get_gateway_webhook ",
        "validate_gateway_webhook_empty_rejected ",
        "validate_gateway_webhook_defaults_accepted",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _unsafe_run_once_probe_flags(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    return tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )


def _missing_scenario_run_once_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "validate_blueprint_schema ",
        "validate_on_demand_scheduling_schema ",
        "scenarios_create_on_demand_inactive ",
        "scenarios_run_rejected_when_inactive ",
        "scenarios_activate ",
        "scenarios_run_responsive ",
        "executions_list_success ",
        "scenarios_deactivate ",
        "cleanup_scenarios_delete ",
        "cleanup_deleted_scenario_unavailable",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_module_configuration_validation_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "validate_parse_json_missing_required_mapper ",
        "validate_parse_json_valid_required_mapper ",
        "inspect_schema_fields_from_valid_response",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_webhook_bind_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "hooks_create_gateway_webhook ",
        "scenarios_create_inactive_custom_webhook ",
        "scenarios_get_export_bound_webhook ",
        "hooks_get_bound_to_inactive_scenario ",
        "cleanup_scenarios_delete ",
        "cleanup_hooks_delete ",
        "cleanup_scratch_scenarios_count ",
        "cleanup_scratch_hooks_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_webhook_datastore_quality_canary_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "preload_hooks_before_editor_load ",
        "preload_data_structures_before_editor_load ",
        "preload_data_stores_before_editor_load ",
        "validate_blueprint_schema ",
        "scenarios_create_inactive_filtered_webhook_datastore ",
        "scenarios_get_export_bound_blueprint ",
        "browser_editor_open_edit_mode ",
        "scenario_activate_destructive_probe ",
        "webhook_post_valid_payload ",
        "executions_list_success ",
        "data_store_records_list_observed ",
        "scenario_deactivate ",
        "cleanup_scenarios_delete ",
        "cleanup_hooks_delete ",
        "cleanup_data_stores_delete ",
        "cleanup_data_structures_delete ",
        "cleanup_scratch_resources_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_connection_bind_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "connections_list_metadata_redacted ",
        "extract_module_components_google_email_send ",
        "scenarios_create_inactive_connection_bound_module ",
        "scenarios_get_export_bound_connection ",
        "cleanup_scenarios_delete ",
        "cleanup_scratch_scenarios_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_live_apply_package_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "project_make_package_zero_trace_ready ",
        "validate_blueprint_schema ",
        "scenarios_create_inactive_from_package_blueprint ",
        "scenarios_get_export_package_blueprint ",
        "scenarios_interface_empty ",
        "cleanup_scenarios_delete ",
        "cleanup_scratch_scenarios_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_module_requirement_extraction_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "validate_blueprint_schema_missing_connection_module ",
        "scenarios_create_missing_connection_inactive ",
        "scenarios_get_missing_connection_export ",
        "extract_blueprint_components_account_target ",
        "cleanup_scenarios_delete ",
        "cleanup_scratch_scenarios_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _missing_runtime_resource_requirement_extraction_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "validate_blueprint_schema_missing_webhook_resource ",
        "scenarios_create_missing_webhook_inactive ",
        "scenarios_get_missing_webhook_export ",
        "extract_blueprint_components_hook_target ",
        "validate_blueprint_schema_missing_datastore_resource ",
        "scenarios_create_missing_datastore_inactive ",
        "scenarios_get_missing_datastore_export ",
        "extract_blueprint_components_datastore_target ",
        "cleanup_scenarios_delete ",
        "cleanup_scratch_scenarios_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _webhook_bind_request_contract_ok(evidence: Mapping[str, object]) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    hook_create = request_contract.get("hook_create")
    scenario_create = request_contract.get("scenario_create")
    return (
        _is_json_object(hook_create)
        and hook_create.get("typeName") == "gateway-webhook"
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module")
        == "gateway:CustomWebHook"
        and scenario_create.get("blueprint.flow[0].parameters.hook") == "int"
        and scenario_create.get(
            "blueprint.flow[0].metadata.parameters[hook].type"
        )
        == "hook:gateway-webhook"
        and scenario_create.get("scheduling.type") == "immediately"
        and scenario_create.get("confirmed") == "bool_true"
    )


def _connection_bind_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    scenario_create = request_contract.get("scenario_create")
    return (
        _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module")
        == "google-email:sendAnEmail"
        and scenario_create.get("blueprint.flow[0].parameters.__IMTCONN__")
        == "int"
        and scenario_create.get(
            "blueprint.flow[0].metadata.parameters[__IMTCONN__].type"
        )
        == "account:google-email"
        and scenario_create.get("scheduling.type") == "immediately"
        and scenario_create.get("confirmed") == "bool_true"
    )


def _live_apply_package_source_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    package_source = evidence.get("package_source_shape")
    return (
        _is_json_object(package_source)
        and package_source.get("source_tool") == "project.make"
        and package_source.get("artifact_format") == "make_blueprint_json"
        and package_source.get("package_status") == "ready"
        and package_source.get("blueprint_readiness_status") == "ready"
        and package_source.get("zero_trace_status") == "passed"
        and package_source.get("module_count")
        == MAKE_LIVE_APPLY_PACKAGE_ROUNDTRIP_MODULE_COUNT
    )


def _live_apply_package_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    schema_validation = request_contract.get("validate_blueprint_schema")
    scenario_create = request_contract.get("scenario_create")
    return (
        _is_json_object(schema_validation)
        and schema_validation.get("message")
        == "Blueprint is valid against the schema."
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow.modules")
        == ["json:ParseJSON", "json:CreateJSON"]
        and scenario_create.get("scheduling.type") == "immediately"
        and scenario_create.get("confirmed") == "bool_true"
        and scenario_create.get("teamId") == "int"
    )


def _module_requirement_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    schema_validation = request_contract.get("validate_blueprint_schema")
    scenario_create = request_contract.get("scenario_create")
    return (
        _is_json_object(schema_validation)
        and schema_validation.get("message")
        == "Blueprint is valid against the schema."
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module")
        == "google-email:sendAnEmail"
        and scenario_create.get("blueprint.flow[0].version")
        == MAKE_MODULE_REQUIREMENT_PROBE_APP_VERSION
        and scenario_create.get("blueprint.flow[0].parameters") == {}
        and scenario_create.get("confirmed") == "bool_true"
        and scenario_create.get("scheduling.type") == "immediately"
    )


def _runtime_resource_requirement_request_contract_ok(
    probes: Mapping[str, JsonObject],
) -> bool:
    return _runtime_resource_request_contract_ok(
        probes.get("webhook_missing_hook"),
        expected_module="gateway:CustomWebHook",
        expected_package="gateway",
    ) and _runtime_resource_request_contract_ok(
        probes.get("datastore_missing_store"),
        expected_module="datastore:AddRecord",
        expected_package="datastore",
    )


def _runtime_resource_request_contract_ok(
    probe: Mapping[str, object] | None,
    *,
    expected_module: str,
    expected_package: str,
) -> bool:
    if probe is None:
        return False
    request_contract = probe.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    schema_validation = request_contract.get("validate_blueprint_schema")
    scenario_create = request_contract.get("scenario_create")
    create_response = probe.get("scenario_create_response_shape")
    return (
        _is_json_object(schema_validation)
        and schema_validation.get("message")
        == "Blueprint is valid against the schema."
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module") == expected_module
        and scenario_create.get("blueprint.flow[0].version")
        == MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_APP_VERSION
        and scenario_create.get("blueprint.flow[0].parameters") == {}
        and scenario_create.get("confirmed") == "bool_true"
        and scenario_create.get("scheduling.type") == "immediately"
        and scenario_create.get("teamId") == "int"
        and _is_json_object(create_response)
        and create_response.get("hookId") == "none"
        and create_response.get("isActive") == "bool_false"
        and create_response.get("isinvalid") == "bool_false"
        and create_response.get("usedPackages") == [expected_package]
    )


def _webhook_bind_export_contract_ok(evidence: Mapping[str, object]) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    hook_get_shape = evidence.get("hook_get_bound_response_shape")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow[0].module")
        == "gateway:CustomWebHook"
        and export_contract.get("$.blueprint.flow[0].parameters.hook") == "int"
        and export_contract.get(
            "$.blueprint.flow[0].metadata.parameters[0].type"
        )
        == "hook:gateway-webhook"
        and export_contract.get("$.hookId") == "int"
        and export_contract.get("$.isActive") == "bool_false"
        and _is_json_object(hook_get_shape)
        and hook_get_shape.get("scenarioId") == "int"
        and hook_get_shape.get("scenarioIsActive") == "bool_false"
        and hook_get_shape.get("typeName") == "gateway-webhook"
    )


def _quality_canary_resource_preload_ok(evidence: Mapping[str, object]) -> bool:
    preload = evidence.get("resource_preload")
    return (
        _is_json_object(preload)
        and preload.get("before_scenario_editor_load") is True
        and _int_at_least(preload.get("matched_hooks"), 1)
        and _int_at_least(preload.get("matched_data_structures"), 1)
        and _int_at_least(preload.get("matched_data_stores"), 1)
    )


def _quality_canary_request_contract_ok(evidence: Mapping[str, object]) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    scenario_create = request_contract.get("scenario_create")
    route_shape = request_contract.get("route_quality_shape")
    note_shape = request_contract.get("note_quality_shape")
    return (
        _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow.modules")
        == ["gateway:CustomWebHook", "builtin:BasicRouter"]
        and scenario_create.get("blueprint.route.flow.modules")
        == ["datastore:AddRecord"]
        and scenario_create.get("blueprint.flow[0].parameters.hook") == "int"
        and scenario_create.get("blueprint.route.flow[0].parameters.datastore")
        == "int"
        and scenario_create.get("scheduling.type") == "immediately"
        and scenario_create.get("confirmed") == "bool_true"
        and _is_json_object(route_shape)
        and route_shape.get("route_filter_count")
        == MAKE_QUALITY_CANARY_FILTER_COUNT
        and route_shape.get("route_filter_names") == ["Has request id"]
        and route_shape.get("retry_module_present") is False
        and route_shape.get("flow_control_discard_module_present") is False
        and route_shape.get("skip_directive_outside_error_handler_visible")
        is False
        and _is_json_object(note_shape)
        and _int_at_least(
            note_shape.get("scenario_note_count"),
            MAKE_QUALITY_CANARY_NOTE_COUNT,
        )
        and _int_at_least(
            note_shape.get("designer_note_count"),
            MAKE_QUALITY_CANARY_NOTE_COUNT,
        )
        and _int_at_least(note_shape.get("module_note_count"), 2)
        and _int_at_least(note_shape.get("filter_note_count"), 1)
    )


def _quality_canary_export_contract_ok(evidence: Mapping[str, object]) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow.modules")
        == ["gateway:CustomWebHook", "builtin:BasicRouter"]
        and export_contract.get("$.blueprint.route.flow.modules")
        == ["datastore:AddRecord"]
        and export_contract.get("$.blueprint.route.filter.names")
        == ["Has request id"]
        and export_contract.get("$.blueprint.metadata.notes")
        == MAKE_QUALITY_CANARY_NOTE_COUNT
        and export_contract.get("$.blueprint.metadata.designer.notes")
        == MAKE_QUALITY_CANARY_NOTE_COUNT
        and export_contract.get("$.blueprint.retry_module_present") is False
        and export_contract.get(
            "$.blueprint.flow_control_discard_module_present"
        )
        is False
        and export_contract.get(
            "$.blueprint.skip_directive_outside_error_handler_visible"
        )
        is False
        and export_contract.get("$.blueprint.scheduling.type") == "immediately"
        and export_contract.get("$.hookId") == "int"
        and export_contract.get("$.isActive") == "bool_false"
    )


def _quality_canary_browser_review_ok(evidence: Mapping[str, object]) -> bool:
    browser = evidence.get("scenario_browser_inspection")
    return (
        _is_json_object(browser)
        and browser.get("editor_opened") is True
        and browser.get("edit_mode_entered") is True
        and browser.get("run_once_visible") is True
        and browser.get("schedule_visible") == "Immediately as data arrives"
        and browser.get("retry_visible") is False
        and browser.get("flow_control_discard_visible") is False
        and browser.get("skip_directive_outside_error_handler_visible") is False
        and browser.get("route_filters_visible") == ["Has request id"]
    )


def _quality_canary_functional_probe_ok(evidence: Mapping[str, object]) -> bool:
    probe = evidence.get("functional_probe")
    record_contract = (
        probe.get("data_store_record_contract")
        if _is_json_object(probe)
        else None
    )
    return (
        _is_json_object(probe)
        and probe.get("operator_destructive_canary_authorized") is True
        and probe.get("scenario_activation_called") is True
        and probe.get("scenario_deactivation_called") is True
        and probe.get("webhook_http_status")
        == MAKE_QUALITY_CANARY_SUCCESS_HTTP_STATUS
        and probe.get("execution_status") == "success"
        and _int_at_least(
            probe.get("execution_operations"),
            MAKE_QUALITY_CANARY_MIN_EXECUTION_OPERATIONS,
        )
        and probe.get("data_store_record_observed") is True
        and _is_json_object(record_contract)
        and record_contract.get("key_present") is True
        and record_contract.get("fields") == ["payload", "request_id", "status"]
    )


def _quality_canary_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_data_stores") == 0
        and cleanup_counts.get("scratch_data_structures") == 0
        and cleanup_counts.get("scratch_hooks") == 0
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _connection_bind_export_contract_ok(evidence: Mapping[str, object]) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    component_shape = evidence.get("component_extraction_shape")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow[0].module")
        == "google-email:sendAnEmail"
        and export_contract.get("$.blueprint.flow[0].parameters.__IMTCONN__")
        == "int"
        and export_contract.get(
            "$.blueprint.flow[0].metadata.parameters[0].type"
        )
        == "account:google-email"
        and export_contract.get("$.hookId") == "none"
        and export_contract.get("$.isActive") == "bool_false"
        and _is_json_object(component_shape)
        and component_shape.get("hooks") == []
        and component_shape.get("keys") == []
    )


def _live_apply_package_export_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    interface_shape = evidence.get("scenario_interface_shape")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow.modules")
        == ["json:ParseJSON", "json:CreateJSON"]
        and export_contract.get("$.blueprint.metadata.instant") == "bool_true"
        and export_contract.get("$.blueprint.scheduling.type") == "immediately"
        and export_contract.get("$.blueprint.interface.input") == []
        and export_contract.get("$.blueprint.interface.output") == []
        and export_contract.get("$.hookId") == "none"
        and export_contract.get("$.isActive") == "bool_false"
        and _is_json_object(interface_shape)
        and interface_shape.get("input") == []
        and interface_shape.get("output") == []
    )


def _module_requirement_export_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    interface_shape = evidence.get("scenario_interface_shape")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow[0].module")
        == "google-email:sendAnEmail"
        and export_contract.get("$.blueprint.flow[0].version")
        == MAKE_MODULE_REQUIREMENT_PROBE_APP_VERSION
        and export_contract.get("$.blueprint.flow[0].parameters") == {}
        and export_contract.get("$.blueprint.metadata.instant") == "bool_true"
        and export_contract.get("$.blueprint.interface.input") == []
        and export_contract.get("$.blueprint.interface.output") == []
        and export_contract.get("$.hookId") == "none"
        and export_contract.get("$.isActive") == "bool_false"
        and export_contract.get("$.isinvalid") == "bool_false"
        and _is_json_object(interface_shape)
        and interface_shape.get("input") == []
        and interface_shape.get("output") == []
    )


def _runtime_resource_requirement_export_contract_ok(
    probes: Mapping[str, JsonObject],
) -> bool:
    return _runtime_resource_export_contract_ok(
        probes.get("webhook_missing_hook"),
        expected_module="gateway:CustomWebHook",
    ) and _runtime_resource_export_contract_ok(
        probes.get("datastore_missing_store"),
        expected_module="datastore:AddRecord",
    )


def _runtime_resource_export_contract_ok(
    probe: Mapping[str, object] | None,
    *,
    expected_module: str,
) -> bool:
    if probe is None:
        return False
    export_contract = probe.get("scenario_get_blueprint_contract")
    interface_shape = probe.get("scenario_interface_shape")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow[0].module") == expected_module
        and export_contract.get("$.blueprint.flow[0].version")
        == MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_APP_VERSION
        and export_contract.get("$.blueprint.flow[0].parameters") == {}
        and export_contract.get("$.blueprint.metadata.instant") == "bool_true"
        and export_contract.get("$.blueprint.interface.input") == []
        and export_contract.get("$.blueprint.interface.output") == []
        and export_contract.get("$.hookId") == "none"
        and export_contract.get("$.isActive") == "bool_false"
        and export_contract.get("$.isinvalid") == "bool_false"
        and _is_json_object(interface_shape)
        and interface_shape.get("input") == []
        and interface_shape.get("output") == []
    )


def _module_requirement_extraction_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    component_shape = evidence.get("component_extraction_shape")
    if not _is_json_object(component_shape):
        return False
    connections = _json_object_tuple(component_shape.get("connections"))
    if len(connections) != MAKE_MODULE_REQUIREMENT_PROBE_CONNECTION_COUNT:
        return False
    connection = connections[0]
    targets = connection.get("moduleTargets")
    interpretation = evidence.get("interpretation")
    return (
        connection.get("id") == "account_1"
        and connection.get("componentType") == "account"
        and connection.get("typeName") == "google-email"
        and connection.get("moduleIds")
        == [MAKE_MODULE_REQUIREMENT_PROBE_MODULE_ID]
        and _is_json_object(targets)
        and targets.get("__IMTCONN__")
        == [MAKE_MODULE_REQUIREMENT_PROBE_MODULE_ID]
        and component_shape.get("hooks") == []
        and component_shape.get("keys") == []
        and component_shape.get("dataStores") == []
        and component_shape.get("dataStructures") == []
        and _is_json_object(interpretation)
        and interpretation.get("is_invalid_is_not_requirement_oracle") is True
        and interpretation.get("component_extraction_is_required") is True
    )


def _runtime_resource_requirement_extraction_contract_ok(
    probes: Mapping[str, JsonObject],
) -> bool:
    webhook_probe = probes.get("webhook_missing_hook")
    datastore_probe = probes.get("datastore_missing_store")
    return _webhook_requirement_extraction_contract_ok(
        webhook_probe
    ) and _datastore_requirement_extraction_contract_ok(datastore_probe)


def _webhook_requirement_extraction_contract_ok(
    probe: Mapping[str, object] | None,
) -> bool:
    if probe is None:
        return False
    component_shape = probe.get("component_extraction_shape")
    if not _is_json_object(component_shape):
        return False
    hooks = _json_object_tuple(component_shape.get("hooks"))
    if len(hooks) != 1:
        return False
    hook = hooks[0]
    targets = hook.get("moduleTargets")
    return (
        hook.get("id") == "hook_1"
        and hook.get("componentType") == "hook"
        and hook.get("typeName") == "gateway-webhook"
        and hook.get("moduleIds")
        == [MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_MODULE_ID]
        and _is_json_object(targets)
        and targets.get("hook")
        == [MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_MODULE_ID]
        and component_shape.get("connections") == []
        and component_shape.get("keys") == []
        and component_shape.get("dataStores") == []
        and component_shape.get("dataStructures") == []
    )


def _datastore_requirement_extraction_contract_ok(
    probe: Mapping[str, object] | None,
) -> bool:
    if probe is None:
        return False
    component_shape = probe.get("component_extraction_shape")
    if not _is_json_object(component_shape):
        return False
    data_stores = _json_object_tuple(component_shape.get("dataStores"))
    if len(data_stores) != 1:
        return False
    data_store = data_stores[0]
    targets = data_store.get("moduleTargets")
    return (
        data_store.get("id") == "datastore_1"
        and data_store.get("componentType") == "datastore"
        and data_store.get("moduleIds")
        == [MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_MODULE_ID]
        and _is_json_object(targets)
        and targets.get("datastore")
        == [MAKE_RUNTIME_RESOURCE_REQUIREMENT_PROBE_MODULE_ID]
        and component_shape.get("connections") == []
        and component_shape.get("keys") == []
        and component_shape.get("hooks") == []
        and component_shape.get("dataStructures") == []
    )


def _webhook_bind_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_hooks") == 0
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _connection_bind_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _live_apply_package_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _module_requirement_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _runtime_resource_requirement_cleanup_ok(
    evidence: Mapping[str, object],
) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _runtime_resource_requirement_probes_by_label(
    evidence: Mapping[str, object],
) -> dict[str, JsonObject]:
    return {
        str(probe["label"]): probe
        for probe in _json_object_tuple(evidence.get("probes"))
        if isinstance(probe.get("label"), str)
    }


def _module_configuration_validation_probes_by_label(
    evidence: Mapping[str, object],
) -> dict[str, JsonObject]:
    return {
        str(probe["label"]): probe
        for probe in _json_object_tuple(evidence.get("probes"))
        if isinstance(probe.get("label"), str)
    }


def _module_configuration_invalid_contract_ok(
    probe: Mapping[str, object] | None,
) -> bool:
    if probe is None:
        return False
    request_contract = probe.get("request_contract")
    response_shape = probe.get("response_shape")
    if not _is_json_object(request_contract) or not _is_json_object(
        response_shape
    ):
        return False
    validation_request = request_contract.get("validate_module_configuration")
    errors = _json_object_tuple(response_shape.get("errors"))
    if len(errors) != 1:
        return False
    error = errors[0]
    return (
        _is_json_object(validation_request)
        and validation_request.get("appName") == "json"
        and validation_request.get("appVersion")
        == MAKE_MODULE_CONFIGURATION_VALIDATION_APP_VERSION
        and validation_request.get("moduleName") == "ParseJSON"
        and validation_request.get("parameters") == {}
        and validation_request.get("mapper") == {}
        and validation_request.get("strict") == "bool_true"
        and response_shape.get("valid") is False
        and error.get("domain") == "expect"
        and error.get("path") == "json"
        and error.get("message_class") == "field_is_mandatory"
        and response_shape.get("warnings") == []
    )


def _module_configuration_valid_contract_ok(
    probe: Mapping[str, object] | None,
) -> bool:
    if probe is None:
        return False
    request_contract = probe.get("request_contract")
    response_shape = probe.get("response_shape")
    if not _is_json_object(request_contract) or not _is_json_object(
        response_shape
    ):
        return False
    validation_request = request_contract.get("validate_module_configuration")
    schemas = response_shape.get("schemas")
    if not _is_json_object(validation_request) or not _is_json_object(schemas):
        return False
    default_fields = _json_object_tuple(schemas.get("default"))
    expect_fields = _json_object_tuple(schemas.get("expect"))
    return (
        validation_request.get("appName") == "json"
        and validation_request.get("appVersion")
        == MAKE_MODULE_CONFIGURATION_VALIDATION_APP_VERSION
        and validation_request.get("moduleName") == "ParseJSON"
        and validation_request.get("mapper.json") == "string"
        and validation_request.get("strict") == "bool_true"
        and validation_request.get("schemas") == "bool_true"
        and validation_request.get("states") == "bool_true"
        and response_shape.get("valid") is True
        and response_shape.get("errors") == []
        and response_shape.get("warnings") == []
        and response_shape.get("states") == {}
        and len(default_fields) == MAKE_MODULE_CONFIGURATION_EXPECT_FIELD_COUNT
        and len(expect_fields) == MAKE_MODULE_CONFIGURATION_EXPECT_FIELD_COUNT
        and default_fields[0].get("name") == "type"
        and default_fields[0].get("type") == "udt"
        and expect_fields[0].get("name") == "json"
        and expect_fields[0].get("type") == "text"
        and expect_fields[0].get("required") is True
    )


def _scenario_run_once_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    create_response = evidence.get("scenario_create_response_shape")
    if not _is_json_object(request_contract) or not _is_json_object(
        create_response
    ):
        return False
    schema_validation = request_contract.get("validate_blueprint_schema")
    schedule_validation = request_contract.get(
        "validate_on_demand_scheduling_schema"
    )
    scenario_create = request_contract.get("scenario_create")
    inactive_run_rejection = request_contract.get("inactive_run_rejection")
    return (
        _is_json_object(schema_validation)
        and schema_validation.get("message")
        == "Blueprint is valid against the schema."
        and _is_json_object(schedule_validation)
        and schedule_validation.get("message")
        == "Scheduling configuration is valid against the schema."
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module") == "json:ParseJSON"
        and scenario_create.get("blueprint.flow[0].version")
        == MAKE_SCENARIO_RUN_ONCE_MODULE_VERSION
        and scenario_create.get("blueprint.flow[0].mapper.json")
        == "json_string"
        and scenario_create.get("confirmed") == "bool_true"
        and scenario_create.get("scheduling.type") == "on-demand"
        and _is_json_object(inactive_run_rejection)
        and inactive_run_rejection.get("message_class")
        == "scenario_not_activated"
        and create_response.get("isActive") == "bool_false"
        and create_response.get("isinvalid") == "bool_false"
        and create_response.get("usedPackages") == ["json"]
    )


def _scenario_run_once_execution_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    run_response = evidence.get("run_response_shape")
    execution_list = evidence.get("executions_list_shape")
    if not _is_json_object(run_response) or not _is_json_object(execution_list):
        return False
    success_event = execution_list.get("success_execution_end")
    activity_types = _text_tuple(execution_list.get("activity_event_types"))
    return (
        run_response.get("executionId") == "hex_string"
        and run_response.get("status") == 1
        and _is_json_object(success_event)
        and success_event.get("eventType") == "EXECUTION_END"
        and success_event.get("status") == 1
        and success_event.get("type") == "auto"
        and success_event.get("operations")
        == MAKE_SCENARIO_RUN_ONCE_OPERATION_COUNT
        and success_event.get("centicredits") == "positive_int"
        and success_event.get("duration") == "non_negative_int"
        and success_event.get("transfer") == "non_negative_int"
        and {"start", "modify"} <= set(activity_types)
    )


def _scenario_run_once_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        evidence.get("scenario_activate_response")
        == "Scenario has been activated."
        and evidence.get("scenario_deactivate_response")
        == "Scenario has been deactivated."
        and evidence.get("scenario_delete_response")
        == "Scenario has been deleted."
        and evidence.get("deleted_scenario_get_error_class")
        == "insufficient_rights_after_delete"
        and _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _hook_configuration_schema_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    schema_shape = evidence.get("hook_config_schema_shape")
    if not _is_json_object(schema_shape):
        return False
    required_default_fields = _text_tuple(
        schema_shape.get("required_default_fields")
    )
    optional_fields = _text_tuple(schema_shape.get("optional_fields"))
    return (
        schema_shape.get("typeName") == "gateway-webhook"
        and schema_shape.get("transport") == "http"
        and schema_shape.get("selfAttaching") is False
        and schema_shape.get("selfDetaching") is False
        and required_default_fields
        == MAKE_HOOK_CONFIGURATION_REQUIRED_DEFAULT_FIELDS
        and {"authenticationMethod", "ip", "udt"} <= set(optional_fields)
        and schema_shape.get("required_defaults")
        == {
            "headers": False,
            "method": False,
            "stringify": False,
        }
    )


def _hook_configuration_validation_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    empty_response = evidence.get("empty_values_response_shape")
    defaults_response = evidence.get("default_values_response_shape")
    if (
        not _is_json_object(request_contract)
        or not _is_json_object(empty_response)
        or not _is_json_object(defaults_response)
    ):
        return False
    empty_errors = _json_object_tuple(empty_response.get("errors"))
    return (
        request_contract.get("typeName") == "gateway-webhook"
        and request_contract.get("strict") == "bool_true"
        and request_contract.get("accepted_values")
        == {
            "headers": "bool_false ",
            "method": "bool_false ",
            "stringify": "bool_false",
        }
        and empty_response.get("valid") is False
        and tuple(error.get("path") for error in empty_errors)
        == MAKE_HOOK_CONFIGURATION_REQUIRED_DEFAULT_FIELDS
        and all(error.get("domain") == "default" for error in empty_errors)
        and all(
            error.get("message_class") == "field_is_mandatory"
            for error in empty_errors
        )
        and empty_response.get("warnings") == []
        and defaults_response.get("valid") is True
        and defaults_response.get("errors") == []
        and defaults_response.get("warnings") == []
    )


def _datastore_lifecycle_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    structure_create = request_contract.get("data_structure_create")
    store_create = request_contract.get("data_store_create")
    record_create = request_contract.get("record_create")
    record_update = request_contract.get("record_update")
    return (
        _is_json_object(structure_create)
        and structure_create.get("spec") is not None
        and structure_create.get("strict") == "bool"
        and _is_json_object(store_create)
        and store_create.get("datastructureId") == "int"
        and store_create.get("maxSizeMB") == "int"
        and _is_json_object(record_create)
        and record_create.get("dataStoreId") == "int"
        and record_create.get("key") == "string_optional"
        and _is_json_object(record_update)
        and record_update.get("key") == "string"
    )


def _datastore_lifecycle_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("data_stores") == 0
        and cleanup_counts.get("data_structures") == 0
    )


def _datastore_strict_schema_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    structure_create = request_contract.get("data_structure_create")
    store_create = request_contract.get("data_store_create")
    invalid_record = request_contract.get("invalid_record_create")
    valid_record = request_contract.get("valid_record_create")
    return (
        _is_json_object(structure_create)
        and structure_create.get("strict") == "bool_true"
        and _text_tuple(structure_create.get("required_fields"))
        == MAKE_DATASTORE_STRICT_SCHEMA_REQUIRED_FIELDS
        and _text_tuple(structure_create.get("typed_fields"))
        == MAKE_DATASTORE_STRICT_SCHEMA_TYPED_FIELDS
        and _is_json_object(store_create)
        and store_create.get("datastructureId") == "int"
        and store_create.get("maxSizeMB") == "int"
        and _is_json_object(invalid_record)
        and invalid_record.get("dataStoreId") == "int"
        and invalid_record.get("data.amount") == "invalid_number_string"
        and invalid_record.get("data.request_id") == "missing"
        and _is_json_object(valid_record)
        and valid_record.get("data.request_id") == "string"
        and valid_record.get("data.amount") == "number"
        and valid_record.get("data.status") == "string"
    )


def _datastore_strict_schema_validation_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    invalid_response = evidence.get("invalid_record_response_shape")
    valid_response = evidence.get("valid_record_response_shape")
    if not _is_json_object(invalid_response) or not _is_json_object(
        valid_response
    ):
        return False
    invalid_errors = _text_tuple(invalid_response.get("error_messages"))
    valid_data = valid_response.get("data")
    return (
        invalid_response.get("error_class") == "schema_validation_failed"
        and invalid_response.get("error_count")
        == MAKE_DATASTORE_STRICT_SCHEMA_REJECTION_COUNT
        and "missing_required_request_id" in invalid_errors
        and "invalid_number_amount" in invalid_errors
        and _is_json_object(valid_data)
        and valid_data.get("request_id") == "string"
        and valid_data.get("amount") == "number"
        and valid_data.get("status") == "string"
        and valid_response.get("key") == "string"
        and evidence.get("record_delete_response")
        == "Records have been deleted."
        and evidence.get("data_store_delete_response")
        == "Data store has been deleted."
        and evidence.get("data_structure_delete_response")
        == "Data structure has been deleted."
    )


def classify_make_scenario_designer_roundtrip_evidence(
    evidence: Mapping[str, object],
) -> JsonObject:
    """Classify sanitized scenario-designer roundtrip evidence.

    Returns:
    JSON-ready status proving designer alignment and warning inspection are
    offline mirrors.
    """
    reports = _json_object_tuple(evidence.get("reports"))
    reports_by_label = {
        str(report.get("label")): report
        for report in reports
        if isinstance(report.get("label"), str)
    }
    missing_labels = tuple(
        label
        for label in MAKE_SCENARIO_DESIGNER_ROUNDTRIP_LABELS
        if label not in reports_by_label
    )
    request_shape = evidence.get("request_shape")
    request_shape_ok = (
        _is_json_object(request_shape)
        and request_shape.get("blueprint") == "json_string"
        and request_shape.get("scheduling") == "json_string"
    )
    json_parse_report = reports_by_label.get("json_parse_no_messages")
    no_coordinate_report = reports_by_label.get("two_nodes_no_coordinates")
    designer_message_injected = _report_message_count(json_parse_report) > 0
    auto_align_injected_coordinates = _report_has_any_coordinate(
        no_coordinate_report
    )
    cleanup_ok = evidence.get("cleanup_status") == "scratch_scenarios_deleted"
    unsafe_flags = tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_activation_called ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )
    status = (
        "pass"
        if not missing_labels
        and request_shape_ok
        and cleanup_ok
        and not unsafe_flags
        and not designer_message_injected
        and not auto_align_injected_coordinates
        else "fail"
    )
    return {
        "status": status,
        "capability_evidence": (
            "scenario_auto_align ",
            "scenario_module_error_inspection",
        ),
        "missing_shape_labels": missing_labels,
        "request_shape_status": "pass" if request_shape_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "unsafe_flags": unsafe_flags,
        "api_auto_align_injected_coordinates": auto_align_injected_coordinates,
        "api_designer_message_injection": designer_message_injected,
        "offline_mirror_required": True,
        "scenario_auto_align_contract": (
            "local_designer_layout_required_before_import"
        ),
        "scenario_module_error_inspection_contract": (
            "offline_linter_and_designer_message_ingest_required"
        ),
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
    }


def classify_make_scenario_mutation_contract_evidence(
    evidence: Mapping[str, object],
) -> JsonObject:
    """Classify sanitized scenario create/export/delete contract evidence.

    Returns:
    JSON-ready status proving exact Make API request and response paths for live
    apply.
    """
    request_contract = evidence.get("request_contract")
    request_contract_ok = (
        _is_json_object(request_contract)
        and request_contract.get("teamId") == "int"
        and request_contract.get("name") == "string"
        and request_contract.get("blueprint") == "json_string"
        and request_contract.get("scheduling") == "json_string"
    )
    create_id_paths = _text_tuple(evidence.get("create_id_path_candidates"))
    delete_id_paths = _text_tuple(evidence.get("delete_id_path_candidates"))
    list_rows = _json_object_tuple(evidence.get("list_created_row_summary"))
    list_row_ok = any(
        row.get("matched_by_id") is True
        and row.get("isActive") is False
        and row.get("isinvalid") is False
        for row in list_rows
    )
    cleanup_ok = (
        evidence.get("cleanup_status") == "scratch_scenario_deleted"
        and evidence.get("scratch_remaining_count") == 0
    )
    unsafe_flags = tuple(
        flag
        for flag in (
            "credential_value_transfer ",
            "credentials_printed ",
            "customer_data_used ",
            "scenario_activation_called ",
            "scenario_run_once_called ",
            "secret_output",
        )
        if evidence.get(flag) is not False
    )
    status = (
        "pass"
        if request_contract_ok
        and "$.scenario.id" in create_id_paths
        and evidence.get("export_blueprint_path") == "$.response.blueprint"
        and "$.scenario" in delete_id_paths
        and list_row_ok
        and cleanup_ok
        and not unsafe_flags
        and evidence.get("scenario_created_inactive") is True
        else "fail"
    )
    return {
        "status": status,
        "capability_evidence": (
            "live_apply_package ",
            "scenario_create ",
            "scenario_export",
        ),
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "create_id_path": "$.scenario.id"
        if "$.scenario.id" in create_id_paths
        else None,
        "export_blueprint_path": evidence.get("export_blueprint_path"),
        "delete_id_path": "$.scenario"
        if "$.scenario" in delete_id_paths
        else None,
        "created_scenario_list_row_status": "pass" if list_row_ok else "fail",
        "cleanup_ok": cleanup_ok,
        "scenario_created_inactive": evidence.get("scenario_created_inactive")
        is True,
        "unsafe_flags": unsafe_flags,
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
    }


def classify_make_scenario_interface_schedule_evidence(
    evidence: Mapping[str, object],
    *,
    required_capabilities: tuple[str, ...],
) -> JsonObject:
    """Classify sanitized scenario interface scheduling evidence.

    Returns:
    JSON-ready status proving required interface inputs need on-demand
    scheduling.
    """
    capabilities = _text_tuple(evidence.get("capabilities_proven"))
    missing_capabilities = tuple(
        capability
        for capability in required_capabilities
        if capability not in capabilities
    )
    unsafe_flags = _unsafe_live_probe_flags(evidence)
    missing_steps = _missing_scenario_interface_schedule_steps(evidence)
    request_contract_ok = _scenario_interface_schedule_request_contract_ok(
        evidence
    )
    export_contract_ok = _scenario_interface_schedule_export_contract_ok(
        evidence
    )
    interface_contract_ok = _scenario_interface_roundtrip_contract_ok(evidence)
    cleanup_ok = _scenario_interface_cleanup_ok(evidence)
    delete_response_ok = (
        evidence.get("scenario_delete_response") == "Scenario has been deleted."
    )
    status = (
        "pass"
        if not missing_capabilities
        and not missing_steps
        and not unsafe_flags
        and request_contract_ok
        and export_contract_ok
        and interface_contract_ok
        and cleanup_ok
        and delete_response_ok
        else "fail"
    )
    return {
        "status": status,
        "required_capabilities": required_capabilities,
        "capabilities_proven": capabilities,
        "missing_capabilities": missing_capabilities,
        "missing_steps": missing_steps,
        "request_contract_status": "pass" if request_contract_ok else "fail ",
        "export_contract_status": "pass" if export_contract_ok else "fail ",
        "interface_contract_status": "pass"
        if interface_contract_ok
        else "fail",
        "cleanup_ok": cleanup_ok,
        "delete_response_status": "pass" if delete_response_ok else "fail",
        "live_make_called": evidence.get("live_make_called") is True,
        "provider_api_call": evidence.get("provider_api_call") is True,
        "credential_value_transfer": bool(
            evidence.get("credential_value_transfer")
        ),
        "secret_output": bool(evidence.get("secret_output")),
        "unsafe_flags": unsafe_flags,
    }


def _missing_scenario_interface_schedule_steps(
    evidence: Mapping[str, object],
) -> tuple[str, ...]:
    completed_steps = {
        str(step["name"])
        for step in _json_object_tuple(evidence.get("steps"))
        if isinstance(step.get("name"), str)
        and step.get("status") in {"ok", "empty"}
    }
    required_steps = (
        "validate_blueprint_schema ",
        "scenarios_create_immediate_inactive ",
        "scenarios_set_interface_required_input_rejected_immediate ",
        "validate_on_demand_scheduling_schema ",
        "scenarios_update_on_demand_schedule ",
        "scenarios_set_interface_required_input_accepted_on_demand ",
        "scenarios_interface_roundtrip ",
        "scenarios_get_export_interface_roundtrip ",
        "cleanup_scenarios_delete ",
        "cleanup_scratch_scenarios_count",
    )
    return tuple(step for step in required_steps if step not in completed_steps)


def _scenario_interface_schedule_request_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    request_contract = evidence.get("request_contract")
    if not _is_json_object(request_contract):
        return False
    schema_validation = request_contract.get("validate_blueprint_schema")
    schedule_validation = request_contract.get(
        "validate_on_demand_scheduling_schema"
    )
    scenario_create = request_contract.get("initial_scenario_create")
    rejection = request_contract.get("required_input_immediate_rejection")
    schedule_update = request_contract.get("on_demand_schedule_update")
    interface_update = request_contract.get("scenario_interface_update")
    create_response = evidence.get("scenario_create_response_shape")
    return (
        _is_json_object(schema_validation)
        and schema_validation.get("message")
        == "Blueprint is valid against the schema."
        and _is_json_object(schedule_validation)
        and schedule_validation.get("message")
        == "Scheduling configuration is valid against the schema."
        and _is_json_object(scenario_create)
        and scenario_create.get("blueprint.flow[0].module") == "json:ParseJSON"
        and scenario_create.get("blueprint.flow[0].version")
        == MAKE_SCENARIO_INTERFACE_MODULE_VERSION
        and scenario_create.get("confirmed") == "bool_true"
        and scenario_create.get("scheduling.type") == "immediately"
        and _is_json_object(create_response)
        and create_response.get("isActive") == "bool_false"
        and create_response.get("isinvalid") == "bool_false"
        and _is_json_object(rejection)
        and rejection.get("message_class")
        == "required_inputs_need_on_demand_schedule"
        and _is_json_object(schedule_update)
        and schedule_update.get("scheduling.type") == "on-demand"
        and _is_json_object(interface_update)
        and interface_update.get("input.required_present") is True
        and interface_update.get("input.type_values") == ["text", "number"]
        and interface_update.get("output.type_values") == ["text", "boolean"]
    )


def _scenario_interface_schedule_export_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    export_contract = evidence.get("scenario_get_blueprint_contract")
    return (
        _is_json_object(export_contract)
        and export_contract.get("$.blueprint.flow[0].module")
        == "json:ParseJSON"
        and export_contract.get("$.blueprint.flow[0].version")
        == MAKE_SCENARIO_INTERFACE_MODULE_VERSION
        and export_contract.get("$.blueprint.scheduling.type") == "on-demand"
        and export_contract.get("$.blueprint.metadata.instant") == "bool_false"
        and export_contract.get("$.blueprint.interface.input.required_count")
        == MAKE_SCENARIO_INTERFACE_REQUIRED_INPUT_COUNT
        and export_contract.get("$.blueprint.interface.input.types")
        == ["text", "number"]
        and export_contract.get("$.blueprint.interface.output.types")
        == ["text", "boolean"]
        and export_contract.get("$.hookId") == "none"
        and export_contract.get("$.isActive") == "bool_false"
        and export_contract.get("$.isinvalid") == "bool_false"
    )


def _scenario_interface_roundtrip_contract_ok(
    evidence: Mapping[str, object],
) -> bool:
    interface_shape = evidence.get("scenario_interface_shape")
    if not _is_json_object(interface_shape):
        return False
    inputs = _json_object_tuple(interface_shape.get("input"))
    outputs = _json_object_tuple(interface_shape.get("output"))
    return (
        len(inputs) == MAKE_SCENARIO_INTERFACE_FIELD_COUNT
        and len(outputs) == MAKE_SCENARIO_INTERFACE_FIELD_COUNT
        and sum(1 for field in inputs if field.get("required") is True)
        == MAKE_SCENARIO_INTERFACE_REQUIRED_INPUT_COUNT
        and [field.get("type") for field in inputs] == ["text", "number"]
        and [field.get("type") for field in outputs] == ["text", "boolean"]
    )


def _scenario_interface_cleanup_ok(evidence: Mapping[str, object]) -> bool:
    cleanup_counts = evidence.get("cleanup_counts")
    return (
        _is_json_object(cleanup_counts)
        and cleanup_counts.get("scratch_scenarios") == 0
    )


def _paged_entries(
    *,
    sources: MakeLiveBrowserValidationSources,
    offset: int,
    limit: int,
) -> Iterable[MakeLiveBrowserValidationEntry]:
    remaining = limit
    for entry in _raw_spec_entries(
        repo_root=sources.repo_root,
        manifest=sources.manifest,
        payloads_by_ref=sources.payloads_by_ref,
        offset=offset,
    ):
        if remaining <= 0:
            return
        remaining -= 1
        yield entry
    if remaining <= 0:
        return
    default_offset = max(0, offset - sources.raw_spec_entry_count)
    for entry in _default_manifest_entries(
        default_facts=sources.default_facts,
        offset=default_offset,
    ):
        if remaining <= 0:
            return
        remaining -= 1
        yield entry


def _blueprint_response_shape(value: object) -> str:
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, str):
        try:
            decoded = cast("object", json.loads(value))
        except json.JSONDecodeError:
            return "string"
        return (
            "json_text_object"
            if isinstance(decoded, dict)
            else "json_text_non_object"
        )
    if value is None:
        return "none"
    return type(value).__name__


def _shape_reports(evidence: Mapping[str, object]) -> tuple[JsonObject, ...]:
    reports = evidence.get("shape_reports")
    if not isinstance(reports, list):
        return ()
    return tuple(
        report
        for report in cast("list[object]", reports)
        if _is_json_object(report)
    )


def _candidate_paths(report: Mapping[str, object] | None) -> tuple[str, ...]:
    if report is None:
        return ()
    paths = report.get("candidate_blueprint_paths")
    if not isinstance(paths, list):
        return ()
    return tuple(
        path for path in cast("list[object]", paths) if isinstance(path, str)
    )


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item for item in cast("list[object]", value) if isinstance(item, str)
    )


def _json_object_tuple(value: object) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item for item in cast("list[object]", value) if _is_json_object(item)
    )


def _int_at_least(value: object, minimum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= minimum
    )


def _report_message_count(report: Mapping[str, object] | None) -> int:
    if report is None:
        return 0
    count = report.get("message_count")
    return (
        count
        if isinstance(count, int) and not isinstance(count, bool) and count > 0
        else 0
    )


def _report_has_any_coordinate(report: Mapping[str, object] | None) -> bool:
    if report is None:
        return False
    summaries = _json_object_tuple(report.get("coordinate_summaries"))
    return any(
        summary.get("has_x") is True or summary.get("has_y") is True
        for summary in summaries
    )


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)


def _raw_spec_entries(
    *,
    repo_root: Path,
    manifest: RawSpecManifest,
    payloads_by_ref: Mapping[str, JsonObject] | None,
    offset: int,
) -> Iterable[MakeLiveBrowserValidationEntry]:
    skipped = 0
    for record in manifest.records:
        if skipped + record.module_count <= offset:
            skipped += record.module_count
            continue
        payload = _load_verified_raw_spec_payload(
            repo_root=repo_root,
            record=record,
            payloads_by_ref=payloads_by_ref,
        )
        parsed = parse_make_raw_spec(payload)
        for module in parsed.modules:
            if skipped < offset:
                skipped += 1
                continue
            current_module_id = module_id(
                app_slug=record.app_slug,
                app_version=record.app_version,
                module_kind=cast("CatalogModuleKind", module.module_kind),
                internal_name=module.internal_name,
            )
            yield MakeLiveBrowserValidationEntry(
                entry_id=f"raw_spec:{current_module_id}",
                source_label="raw_spec_manifest",
                source_ref=record.relative_path,
                module_id=current_module_id,
                app_slug=record.app_slug,
                app_version=record.app_version,
                module_kind=cast("CatalogModuleKind", module.module_kind),
                internal_name=module.internal_name,
                display_name=module.display_name,
                status=MAKE_LIVE_BROWSER_ENTRY_STATUS,
                blocker_code="no_reviewed_browser_import_export_diff",
            )
            skipped += 1


def _default_manifest_entries(
    *,
    default_facts: tuple[MakeDefaultManifestCoverageFact, ...],
    offset: int,
) -> Iterable[MakeLiveBrowserValidationEntry]:
    for index, fact in enumerate(default_facts):
        if index < offset:
            continue
        module = fact.module
        yield MakeLiveBrowserValidationEntry(
            entry_id=f"default_manifest:{module.module_id}",
            source_label="default_manifest_coverage",
            source_ref=",".join(fact.source_files),
            module_id=module.module_id,
            app_slug=module.app_slug,
            app_version=module.app_version,
            module_kind=cast("CatalogModuleKind", module.module_kind),
            internal_name=module.internal_name,
            display_name=module.display_name,
            status=MAKE_LIVE_BROWSER_ENTRY_STATUS,
            blocker_code="no_reviewed_browser_import_export_diff",
        )


def _load_verified_raw_spec_payload(
    *,
    repo_root: Path,
    record: RawSpecRecord,
    payloads_by_ref: Mapping[str, JsonObject] | None,
) -> JsonObject:
    if payloads_by_ref is not None:
        payload = payloads_by_ref.get(record.relative_path)
        if payload is None:
            message = (
                f"SQLite raw spec payload is missing for{record.relative_path}."
            )
            raise FileNotFoundError(message)
        return payload
    path = resolve_repo_relative_path(repo_root, Path(record.relative_path))
    payload_bytes = path.read_bytes()
    if hashlib.sha256(payload_bytes).hexdigest() != record.sha256:
        message = f"Raw spec hash mismatch for {record.relative_path}."
        raise ValueError(message)
    payload = cast("object", json.loads(payload_bytes.decode("utf-8")))
    if not isinstance(payload, dict):
        message = f"Raw spec {record.relative_path} must contain a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _entry_payload(entry: MakeLiveBrowserValidationEntry) -> JsonObject:
    return {
        "entry_id": entry.entry_id,
        "source_label": entry.source_label,
        "source_ref": entry.source_ref,
        "module_id": entry.module_id,
        "app_slug": entry.app_slug,
        "app_version": entry.app_version,
        "module_kind": entry.module_kind,
        "internal_name": entry.internal_name,
        "display_name": entry.display_name,
        "status": entry.status,
        "blocker_code": entry.blocker_code,
    }


def _validate_paging(*, offset: int, limit: int) -> None:
    if offset < 0:
        message = "offset must be non-negative."
        raise ValueError(message)
    if limit <= 0 or limit > MAKE_LIVE_BROWSER_MAX_LIMIT:
        message = f"limit must be between 1 and {MAKE_LIVE_BROWSER_MAX_LIMIT}."
        raise ValueError(message)
