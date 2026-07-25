# ruff: noqa: C901, E501, PLR0911, PLR0912, PLR0913, PLR0914
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.no-obsolete-domain-tools
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Minimal local project MCP tools.

Boundary contract:
- Owns: the retained MCP project search, health, view, and narrow node editor tools.
- Must not: store customer, purchase, subscription, Lemon Squeezy, or business state in
  Pancakes Core.
- Allows: searching and editing local ignored Make scenario drafts and technical package evidence.
- Split when: local technical draft/package orchestration needs a narrower module.
- Merge when: another MCP module exposes the same active project tool names.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn, cast

from blueprints.ast.parser import parse_make_ast
from languages.make.layout import plan_make_blueprint_layout
from languages.make.live_browser_validation import make_live_browser_smoke_plan
from languages.make.notes import (
    MAKE_CONNECTION_NOTE_COLOR,
    MAKE_MODULE_NOTE_COLOR,
    MAKE_NOTE_COLOR_PALETTE,
)
from languages.make.public_safe_artifacts import (
    make_public_safe_artifact_report_payload,
    make_public_safe_blueprint_json,
    make_public_safe_live_resource_manifest,
    validate_make_public_safe_artifact,
)
from languages.make.translation import (
    translate_make_blueprint_to_pancakes_projection,
)

from mcp.onboarding_security import (
    onboarding_secret_class_counts,
    onboarding_secret_findings,
)
from mcp.project_loop_storage import (
    BLUEPRINT_IMPORT_EVIDENCE_FILE_NAME,
    LOCAL_PROJECT_FOLDER_POLICY,
    LOCAL_PROJECT_METADATA_TABLE,
    PROJECT_ROOT,
    SCENARIO_FILE_NAME,
)
from mcp.project_loop_storage import (
    bool_argument as _bool_argument,
)
from mcp.project_loop_storage import (
    bounded_int as _bounded_int,
)
from mcp.project_loop_storage import (
    derive_links as _derive_links,
)
from mcp.project_loop_storage import (
    filter_summary as _filter_summary,
)
from mcp.project_loop_storage import (
    flow_from_mapping as _flow_from_mapping,
)
from mcp.project_loop_storage import (
    flow_path as _flow_path,
)
from mcp.project_loop_storage import (
    handlers_for_module as _handlers_for_module,
)
from mcp.project_loop_storage import (
    insert_position as _insert_position,
)
from mcp.project_loop_storage import (
    iter_modules as _iter_modules,
)
from mcp.project_loop_storage import (
    iter_routes as _iter_routes,
)
from mcp.project_loop_storage import (
    json_copy as _json_copy,
)
from mcp.project_loop_storage import (
    json_object_argument as _json_object_argument,
)
from mcp.project_loop_storage import (
    legacy_scenario_path as _legacy_scenario_path,
)
from mcp.project_loop_storage import (
    local_offline_safety_flags as _local_offline_safety_flags,
)
from mcp.project_loop_storage import (
    local_project_artifact_rows as _local_project_artifact_rows,
)
from mcp.project_loop_storage import (
    local_project_display_path as _local_project_display_path,
)
from mcp.project_loop_storage import (
    local_project_metadata_row as _local_project_metadata_row,
)
from mcp.project_loop_storage import (
    local_project_path_report as _local_project_path_report,
)
from mcp.project_loop_storage import (
    local_project_storage_request as _local_project_storage_request,
)
from mcp.project_loop_storage import (
    mapping_member as _mapping_member,
)
from mcp.project_loop_storage import (
    merge_patch as _merge_patch,
)
from mcp.project_loop_storage import (
    module_summary as _module_summary,
)
from mcp.project_loop_storage import (
    node_id as _node_id,
)
from mcp.project_loop_storage import (
    nonnegative_int as _nonnegative_int,
)
from mcp.project_loop_storage import (
    operator_workspace_root as _operator_workspace_root,
)
from mcp.project_loop_storage import (
    optional_node_id as _optional_node_id,
)
from mcp.project_loop_storage import (
    optional_text as _optional_text,
)
from mcp.project_loop_storage import (
    path_has_prefix as _path_has_prefix,
)
from mcp.project_loop_storage import (
    project_metadata as _project_metadata,
)
from mcp.project_loop_storage import (
    raw_route_and_flow_edge_count as _raw_route_and_flow_edge_count,
)
from mcp.project_loop_storage import (
    read_json_object as _read_json_object,
)
from mcp.project_loop_storage import (
    remove_module as _remove_module,
)
from mcp.project_loop_storage import (
    require_unique_node_id as _require_unique_node_id,
)
from mcp.project_loop_storage import (
    required_module as _required_module,
)
from mcp.project_loop_storage import (
    required_node_id as _required_node_id,
)
from mcp.project_loop_storage import (
    required_project_id as _required_project_id,
)
from mcp.project_loop_storage import (
    routes_for_module as _routes_for_module,
)
from mcp.project_loop_storage import (
    scenario_path as _scenario_path,
)
from mcp.project_loop_storage import (
    scenario_summary as _scenario_summary,
)
from mcp.project_loop_storage import (
    target_flow as _target_flow,
)
from mcp.project_loop_storage import (
    text_list as _text_list,
)
from mcp.project_loop_storage import (
    upsert_local_project_metadata as _upsert_local_project_metadata,
)
from mcp.project_loop_storage import (
    write_json_object as _write_json_object,
)
from mcp.project_loop_storage import (
    write_response as _write_response,
)
from mcp.response_contracts import (
    RuntimeSetupSurfaceCounts,
    ValidationSurfaceStatuses,
    blocked_surface_payload,
    runtime_setup_count_payload,
    runtime_setup_surface_payload,
    validation_surface_payload,
    zero_trace_payload,
)


def _raise_value_error(message: str) -> NoReturn:
    """Raise a ValueError with an existing validated message.

    Raises:
        ValueError: Always raised with the supplied message.
    """
    raise ValueError(message)


def _raise_type_error(message: str) -> NoReturn:
    """Raise a TypeError with an existing validated message.

    Raises:
        TypeError: Always raised with the supplied message.
    """
    raise TypeError(message)


def _raise_assertion_error(message: str) -> NoReturn:
    """Raise an AssertionError with an existing validated message.

    Raises:
        AssertionError: Always raised with the supplied message.
    """
    raise AssertionError(message)


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, MutableMapping, Sequence

    from mcp.models import JsonObject

BLUEPRINT_IMPORT_INTAKE_ROOT = Path("temp") / "pancakes" / "project-intake"
BLUEPRINT_IMPORT_EVIDENCE_MAX_BYTES = 65_536
STAGED_DRAFT_FILE_NAME_MAX_LENGTH = 96
SCENARIO_SUMMARY_MAX_LENGTH = 2_000
INTENT_SUMMARY_MAX_LENGTH = 240
INTENT_SUMMARY_ELLIPSIS_LENGTH = 3
PROJECT_CREATE_RAW_DRAFT_TEXT_PATTERN = re.compile(
    r"https?://|\bBearer\s+\S{8,}|\bsk_test_[A-Za-z0-9_=-]{6,}|api[_ -]?key\s*[:=]",
    re.IGNORECASE,
)
PROJECT_DRAFT_SECRET_TEXT_PATTERN = re.compile(
    r"\bBearer\s+\S{8,}|\bsk_test_[A-Za-z0-9_=-]{6,}|api[_ -]?key\s*[:=]",
    re.IGNORECASE,
)
CUSTOMER_DELIVERY_PACKAGE_FOLDER_NAME = "customer-delivery-package"
MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME = "make-live"
MAKE_LIVE_RESOURCE_MAX_SIZE_MB: Final = 1
MAKE_LIVE_WEBHOOK_TYPE_NAME = "gateway-webhook"
MAKE_LIVE_WEBHOOK_DEFAULT_DATA: Final[JsonObject] = {
    "headers": False,
    "method": False,
    "stringify": False,
}
MAKE_LIVE_RESOURCE_CREATION_ORDER: Final = (
    "data_structure",
    "data_store",
    "webhook",
    "scenario",
)
MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN: Final = (
    "Data Structure -> Data Store -> Webhook -> Scenario"
)
MAKE_LIVE_CANARY_CLEANUP_SEMANTICS: Final = (
    "Scratch Data Structures, Data Stores, Webhooks, and scenarios are deleted after "
    "the destructive proof; absence in Make UI means cleanup passed, not that validation "
    "never created them."
)
CUSTOMER_DELIVERY_EXCLUDED_INTERNAL_ARTIFACTS = (
    "local_ast_json",
    "graph_internals",
    "linter_rules",
    "internal_prompts",
    "scoring_logic",
    "industrial_logic",
    "raw_validation_report",
)
PROJECT_SEARCH_DEFAULT_LIMIT = 20
PROJECT_SEARCH_MAX_LIMIT = 100
PROJECT_VIEW_DEFAULT_LIMIT = 12
PROJECT_VIEW_MAX_LIMIT = 100
PROJECT_WRAPPER_DEFAULT_LIMIT = 20
PROJECT_EXAMPLE_LIMIT = 3
PROJECT_VERIFY_TOP_BLOCKER_LIMIT = 5
BLUEPRINT_IMPORT_ROOT_FIELDS = frozenset(
    (
        "name",
        "flow",
        "metadata",
        "datastores",
        "dataStores",
        "dataStructures",
        "webhooks",
        "layout",
        "schedule",
        "sample_payloads",
    )
)
BLUEPRINT_IMPORT_MODULE_FIELDS = frozenset(
    (
        "id",
        "module",
        "version",
        "name",
        "parameters",
        "mapper",
        "routes",
        "onerror",
        "metadata",
        "expect",
        "restore",
    )
)
BLUEPRINT_IMPORT_ROUTE_FIELDS = frozenset(
    ("filter", "flow", "metadata", "label", "name")
)
BLUEPRINT_IMPORT_FILTER_FIELDS = frozenset(
    (
        "name",
        "condition",
        "conditions",
        "expression",
        "metadata",
    )
)
BASIC_ROUTER_MODULE = "builtin:BasicRouter"
ERROR_HANDLER_TARGET_EXAMPLE = 'Example: {"parent_node_id":"1","handler_json":{"directive":"retry","flow":[{"id":9,"module":"datastore:AddRecord"}]}}'
ERROR_HANDLER_TARGET_KEYS = frozenset(
    (
        "handler",
        "handler_json",
        "node_id",
        "parent_node_id",
        "target_node_id",
        "handler_index",
    )
)
FILTER_TARGET_EXAMPLE = 'Example: {"node_id":"2","route_index":0,"filter_json":{"name":"Qualified","condition":"{{1.email}}"}}'
FILTER_TARGET_KEYS = frozenset(
    ("filter", "filter_json", "node_id", "route_index", "target_node_id")
)
FILTER_ARGUMENT_EXPECTED_KEYS = (
    "node_id",
    "target_node_id",
    "route_index",
    "filter_json",
    "filter_json.node_id",
    "filter_json.target_node_id",
    "filter_json.route_index",
    "filter_json.filter",
)
FILTER_BODY_EXPECTED_KEYS = ("name", "condition", "conditions", "expression")
FILTER_CONDITION_KEYS = frozenset(("condition", "conditions", "expression"))
PROJECT_OUTPUT_MODES = frozenset(
    ("micro", "compact", "outline", "full", "debug")
)
PROJECT_VIEW_SURFACES = frozenset(
    (
        "overview",
        "graph",
        "modules",
        "links",
        "filters",
        "error_handlers",
        "runtime",
        "datastores",
        "notes",
        "make_blueprint",
        "readiness",
        "parity",
        "issues",
        "lineage",
        "layout",
        "raw",
    )
)
PROJECT_MAKE_ACTIONS = frozenset(("preview", "render", "write", "package"))
PROJECT_PACKAGE_INSPECT_SECTIONS = (
    "live_resources",
    "blueprint_summary",
    "parity_plan",
    "customer_files",
    "zero_trace",
)
PROJECT_PACKAGE_INSPECTOR_REASONS: Final[dict[str, str]] = {
    "live_resources": "Inspect live resource manifests without returning the full package.",
    "blueprint_summary": "Inspect blueprint and package counts without raw blueprint JSON.",
    "parity_plan": "Inspect parity and live-apply planning without raw package sections.",
    "customer_files": "Inspect customer-visible files without internal package details.",
    "zero_trace": "Inspect redaction and zero-trace evidence.",
}
PROJECT_MAKE_PROFILES = frozenset(
    (
        "import_test",
        "parity_fixture",
        "client_handoff",
        "live_preflight",
    )
)
PROJECT_VERIFY_PROFILES = frozenset(
    (
        "local_structure",
        "import_test",
        "handoff_test",
        "parity_fixture",
        "live_preflight",
        "runtime_setup",
        "zero_trace",
        "field_test",
        "build_test",
        "catalog_test",
    )
)
ZERO_TRACE_BLOCKING_VERIFY_PROFILES = frozenset(
    (
        "zero_trace",
        "handoff_test",
        "live_preflight",
        "build_test",
    )
)
PROJECT_NEXT_MODES = frozenset(("one", "plan"))
RUNTIME_PLACEHOLDER_PATTERN = re.compile(
    r"(__IMTCONN__|\{\{\s*runtime\.[^}]+\}\})"
)
MAKE_CONNECTION_FIELD_NAMES = frozenset(
    ("account", "connection", "connections")
)
MODULE_REQUIRED_CONNECTION_TARGETS: Final[
    dict[str, tuple[tuple[str, str], ...]]
] = {
    "google-email:sendAnEmail": (("__IMTCONN__", "google-email"),),
}
MODULE_REQUIRED_RUNTIME_RESOURCE_TARGETS: Final[
    dict[str, tuple[tuple[str, str, str], ...]]
] = {
    "datastore:AddRecord": (("datastore", "datastore", "datastore"),),
    "gateway:CustomWebHook": (("hook", "webhook", "gateway-webhook"),),
}
PRIVATE_TRACE_MARKERS = (
    "pancakes",
    "schoenwald",
    "repos/",
    ".env",
    "source/",
    "candidate_id",
    "raw payload",
    "project.make",
    "local_project_scenario",
)
NOTE_MODULE_REQUIRED_SECTIONS = ("Purpose", "Input", "Output", "Operator check")
NOTE_CONNECTION_REQUIRED_SECTIONS = (
    "Handoff",
    "Data contract",
    "Failure signal",
)
NOTE_SECTION_MIN_CHARACTERS = 16
MAKE_NATIVE_NOTE_COLOR: Final = MAKE_MODULE_NOTE_COLOR
MAKE_NATIVE_SCENARIO_SETTINGS_DEFAULTS: Final[JsonObject] = {
    "roundtrips": 1,
    "maxErrors": 3,
    "autoCommit": True,
    "autoCommitTriggerLast": True,
    "sequential": True,
    "slots": None,
    "confidential": False,
    "dataloss": False,
    "dlq": True,
    "freshVariables": True,
}
NOTE_REDACTION_MARKERS = (
    *PRIVATE_TRACE_MARKERS,
    "blueprints.ast",
    "candidate id",
    "debug dump",
    "graph algorithm",
    "industrial architecture",
    "industrial logic",
    "internal dsl",
    "internal graph",
    "linter logic",
    "private prompt",
    "raw provider payload",
    "raw scenario",
    "rule code",
    "source path",
)
NOTE_LOCAL_PATH_PATTERN = re.compile(
    r"\b[A-Z]:[\\/]|(?:^|\s)/(?:home|mnt|users|var|tmp)/", re.IGNORECASE
)
NOTE_SECRET_LIKE_PATTERN = re.compile(
    r"\b(?:access_token|api[_-]?key|authorization|bearer|password|secret|x-hook-key)\b\s*[:=|]\s*[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=-]{8,}",
    re.IGNORECASE,
)
MAKE_MCP_CAPABILITY_MATRIX: JsonObject = {
    "scenario_list": "available",
    "scenario_import": "available",
    "scenario_create": "available",
    "scenario_update": "available",
    "scenario_export": "available",
    "scenario_run_once": "available",
    "scenario_interface_update": "available",
    "scenario_auto_align": "offline_mirror",
    "scenario_inspect_modules": "available",
    "module_configuration_validation": "available",
    "scenario_module_error_inspection": "offline_mirror",
    "datastore_list": "available",
    "datastore_create": "available",
    "datastore_update_schema": "available",
    "datastore_delete": "available",
    "datastore_record_create": "available",
    "datastore_record_update": "available",
    "datastore_record_upsert_batch": "available",
    "datastore_strict_schema_validation": "available",
    "datastore_record_delete_batch": "available",
    "connection_list_metadata": "available",
    "connection_bind_to_module": "available",
    "webhook_list": "available",
    "webhook_configuration_validation": "available",
    "webhook_create": "available",
    "webhook_create_or_select": "available",
    "webhook_bind_to_module": "available",
    "webhook_delete_or_cleanup": "available",
    "live_apply_package": "available",
}
MAKE_MCP_CAPABILITY_MAPPED_TOOLS: JsonObject = {
    "scenario_list": "scenarios_list",
    "scenario_import": "scenarios_create",
    "scenario_create": "scenarios_create",
    "scenario_update": "scenarios_update",
    "scenario_export": "scenarios_get",
    "scenario_run_once": "scenarios_run",
    "scenario_interface_update": "scenarios_set_interface + scenarios_interface",
    "scenario_auto_align": "pancakes_offline_layout_plan",
    "scenario_inspect_modules": "scenarios_get",
    "module_configuration_validation": "validate_module_configuration",
    "scenario_module_error_inspection": "pancakes_offline_linter + designer_messages",
    "datastore_list": "data_stores_list",
    "datastore_create": "data_stores_create",
    "datastore_update_schema": "data_structures_update",
    "datastore_delete": "data_stores_delete",
    "datastore_record_create": "data_store_records_create",
    "datastore_record_update": "data_store_records_update",
    "datastore_record_delete_batch": "data_store_records_delete",
    "datastore_strict_schema_validation": "data_store_records_create",
    "connection_list_metadata": "connections_list",
    "connection_bind_to_module": "scenarios_create + scenarios_get",
    "webhook_list": "hooks_list",
    "webhook_configuration_validation": "hook_config_get + validate_hook_configuration",
    "webhook_create": "hooks_create",
    "webhook_create_or_select": "hooks_list + hooks_create",
    "webhook_bind_to_module": "scenarios_update + hooks_list/hooks_create",
    "webhook_delete_or_cleanup": "hooks_delete",
    "live_apply_package": "bounded composition contract",
}
LIVE_APPLY_PACKAGE_REQUIRED_CAPABILITIES: Final[tuple[str, ...]] = (
    "scenario_import",
    "scenario_interface_update",
    "module_configuration_validation",
    "datastore_list",
    "datastore_create",
    "datastore_strict_schema_validation",
    "connection_list_metadata",
    "connection_bind_to_module",
    "webhook_configuration_validation",
    "webhook_create_or_select",
    "webhook_bind_to_module",
    "scenario_inspect_modules",
    "scenario_export",
)
LIVE_APPLY_PACKAGE_ROLLBACK_CAPABILITIES: Final[tuple[str, ...]] = (
    "scenario_export",
    "webhook_delete_or_cleanup",
    "datastore_record_delete_batch",
)
DATASTORE_BATCH_UPSERT_MAX_RECORDS: Final = 100
DATASTORE_BATCH_UPSERT_RETRY_LIMIT: Final = 3
MINIMAL_IMPORT_CAPABILITIES = frozenset(
    (
        "scenario_import",
        "datastore_create",
        "connection_list_metadata",
    )
)
FULL_LIVE_VALIDATION_CAPABILITIES = frozenset(
    (
        "datastore_list",
        "scenario_import",
        "scenario_export",
        "scenario_run_once",
        "scenario_interface_update",
        "scenario_auto_align",
        "module_configuration_validation",
        "datastore_create",
        "datastore_record_upsert_batch",
        "datastore_strict_schema_validation",
        "connection_list_metadata",
        "connection_bind_to_module",
        "scenario_inspect_modules",
        "scenario_module_error_inspection",
        "webhook_configuration_validation",
        "webhook_create_or_select",
        "webhook_bind_to_module",
        "webhook_delete_or_cleanup",
        "live_apply_package",
    )
)


def search_projects(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Search local technical project drafts only.

    Returns:
        The computed value.
    """
    query = _optional_text(arguments.get("query"))
    limit = _bounded_int(
        arguments.get("limit"),
        default=PROJECT_SEARCH_DEFAULT_LIMIT,
        upper=PROJECT_SEARCH_MAX_LIMIT,
    )
    project_kind = _optional_text(arguments.get("project_kind"))
    include_templates = _bool_argument(
        arguments.get("include_templates"), default=False
    )
    local_artifacts = _local_project_artifact_rows(
        repo_root=repo_root, query=query
    )
    local_scenario_projects = tuple(
        row
        for row in local_artifacts
        if row["project_kind"] == "local_scenario_project"
    )
    local_fixture_projects = tuple(
        row
        for row in local_artifacts
        if row["project_kind"] == "fixture_project"
    )
    template_libraries = tuple(
        row
        for row in local_artifacts
        if row["project_kind"] == "template_library"
    )
    if project_kind == "template_library":
        visible_local_projects = template_libraries[:limit]
    elif project_kind == "fixture_project":
        visible_local_projects = local_fixture_projects[:limit]
    elif project_kind == "local_scenario_project":
        visible_local_projects = local_scenario_projects[:limit]
    elif include_templates:
        visible_local_projects = local_artifacts[:limit]
    else:
        visible_local_projects = (
            *local_scenario_projects,
            *local_fixture_projects,
        )[:limit]
    visible_unbounded_count = (
        len(template_libraries)
        if project_kind == "template_library"
        else len(local_fixture_projects)
        if project_kind == "fixture_project"
        else len(local_scenario_projects)
        if project_kind == "local_scenario_project"
        else len(local_artifacts)
        if include_templates
        else len(local_scenario_projects) + len(local_fixture_projects)
    )
    return {
        "status": "ok",
        "status_detail": "local_artifacts_only",
        "source_of_truth": {
            "local_artifacts": "local_project_scenario",
            "local_metadata": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
        },
        "database_owner": "pancakes_core",
        "local_metadata_table": LOCAL_PROJECT_METADATA_TABLE,
        "core_database_contains_business_state": False,
        "external_business_state_read": False,
        "local_project_count": len(local_scenario_projects),
        "local_project_count_semantics": "local_scenario_project_count",
        "local_scenario_project_count": len(local_scenario_projects),
        "local_template_library_count": len(template_libraries),
        "local_fixture_project_count": len(local_fixture_projects),
        "total_local_artifact_count": len(local_artifacts),
        "local_projects_available": bool(
            local_scenario_projects or local_fixture_projects
        ),
        "template_libraries_available": bool(template_libraries),
        "hidden_template_library_count": (
            0
            if include_templates or project_kind == "template_library"
            else len(template_libraries)
        ),
        "local_projects": visible_local_projects,
        "returned_local_project_count": len(visible_local_projects),
        "returned_local_project_count_semantics": "returned_local_artifact_count",
        "returned_local_artifact_count": len(visible_local_projects),
        "returned_local_scenario_project_count": sum(
            1
            for row in visible_local_projects
            if row["project_kind"] == "local_scenario_project"
        ),
        "returned_template_library_count": sum(
            1
            for row in visible_local_projects
            if row["project_kind"] == "template_library"
        ),
        "returned_local_fixture_project_count": sum(
            1
            for row in visible_local_projects
            if row["project_kind"] == "fixture_project"
        ),
        "hidden_local_project_count": max(
            visible_unbounded_count - len(visible_local_projects), 0
        ),
        "projects": visible_local_projects,
        "project_count": len(visible_local_projects),
        "next_action": "Create a local Make scenario draft when no matching artifact exists.",
        "next_queries": (
            _next_query(
                tool="project.search",
                arguments={"query": query or "", "include_templates": True},
                reason="Include local template libraries when template inspection is intended.",
            ),
        )
        if template_libraries and not include_templates
        else (),
        "query": query,
        "limit": limit,
        "include_templates": include_templates,
        **_local_offline_safety_flags(),
    }


def stage_project_draft(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Stage one local Make draft from a safe scenario summary.

    Returns:
        The computed value.
    """
    project_id = _required_project_id(arguments)
    project_name = _optional_text(arguments.get("name")) or project_id
    scenario_summary = _required_scenario_summary(arguments)
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    staged_path = _project_draft_stage_path(
        repo_root=repo_root,
        project_id=project_id,
        file_name=_optional_text(arguments.get("staged_draft_file_name")),
    )
    staged_path_text = _local_project_display_path(
        repo_root=repo_root, path=staged_path
    )
    input_findings = _project_draft_stage_input_findings(
        name=project_name,
        scenario_summary=scenario_summary,
    )
    if input_findings:
        return _project_draft_stage_blocked_payload(
            project_id=project_id,
            dry_run=dry_run,
            staged_path_text=staged_path_text,
            findings=input_findings,
            blocked_reason="scenario_summary contains prompt-triggering or credential-shaped text",
        )
    catalog_assist = _intent_catalog_assist_metadata(scenario_summary)
    metadata = _project_draft_stage_metadata(
        project_id=project_id,
        scenario_summary=scenario_summary,
        catalog_assist=catalog_assist,
    )
    draft_payload = _starter_scenario_from_intent(
        project_name=project_name,
        metadata=metadata,
    )
    draft_findings = onboarding_secret_findings(draft_payload)
    if draft_findings:
        return _project_draft_stage_blocked_payload(
            project_id=project_id,
            dry_run=dry_run,
            staged_path_text=staged_path_text,
            findings=draft_findings,
            blocked_reason="generated local draft failed the scrub scan",
        )
    staged_sha256 = _json_sha256(draft_payload)
    existing_sha256 = _existing_json_sha256(staged_path)
    if (
        not dry_run
        and existing_sha256 is not None
        and existing_sha256 != staged_sha256
    ):
        _raise_value_error(
            "staged draft path already exists with different JSON content."
        )
    wrote = False
    if not dry_run and existing_sha256 is None:
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_object(staged_path, draft_payload)
        wrote = True
    would_change = existing_sha256 != staged_sha256
    return {
        "status": "dry_run"
        if dry_run
        else "staged"
        if wrote
        else "already_staged",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": would_change,
        "would_write": would_change,
        "writes_performed": wrote,
        "write_actions": ["write_staged_draft"] if wrote else [],
        "staged_draft_path": staged_path_text,
        "staged_draft_sha256": staged_sha256,
        "staged_draft_exists": staged_path.exists(),
        "staged_draft_role": "local_import_draft",
        "draft_artifact_policy": "approved_generated_state",
        "raw_blueprint_values_returned": False,
        "scenario_summary_returned": False,
        "scenario_summary_sha256": hashlib.sha256(
            scenario_summary.encode("utf-8")
        ).hexdigest(),
        "draft_secret_scan_status": "passed",
        "scrub_status": "passed_no_secret_like_values",
        "secret_like_finding_count": 0,
        "prompt_triggering_literal_count": 0,
        "catalog_assisted_module_selection": True,
        "intent_coverage_status": catalog_assist["intent_coverage_status"],
        "intent_coverage_gap_count": catalog_assist[
            "intent_coverage_gap_count"
        ],
        "requested_capabilities": catalog_assist["requested_capabilities"],
        "selected_modules": catalog_assist["selected_modules"],
        "missing_capabilities": catalog_assist["missing_capabilities"],
        "next_queries": _project_draft_stage_next_queries(
            project_id=project_id,
            staged_draft_path=staged_path_text,
            staged_draft_sha256=staged_sha256,
            dry_run=dry_run,
        ),
        **_local_offline_safety_flags(),
    }


def import_project_draft(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Stage one existing local JSON artifact after the intake scrub gate.

    Returns:
        The computed value.
    """
    project_id = _required_project_id(arguments)
    source_path_text = _required_source_artifact_path_text(arguments)
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    staged_path = _project_draft_stage_path(
        repo_root=repo_root,
        project_id=project_id,
        file_name=_optional_text(arguments.get("staged_draft_file_name")),
    )
    staged_path_text = _local_project_display_path(
        repo_root=repo_root, path=staged_path
    )
    try:
        source_path = _make_blueprint_payload_artifact_path(
            repo_root=repo_root,
            path_text=source_path_text,
        )
    except ValueError:
        return _project_draft_import_missing_source_payload(
            project_id=project_id,
            dry_run=dry_run,
            source_path_text=_redacted_source_artifact_reference(
                source_path_text
            ),
            staged_path_text=staged_path_text,
        )
    source_path_display = _local_project_display_path(
        repo_root=repo_root, path=source_path
    )
    if not source_path.is_file():
        return _project_draft_import_missing_source_payload(
            project_id=project_id,
            dry_run=dry_run,
            source_path_text=source_path_display,
            staged_path_text=staged_path_text,
        )
    try:
        source_payload = _read_json_object(source_path)
    except (json.JSONDecodeError, ValueError):
        return _project_draft_import_invalid_source_payload(
            project_id=project_id,
            dry_run=dry_run,
            source_path_text=source_path_display,
            staged_path_text=staged_path_text,
        )
    source_sha256 = _json_sha256(source_payload)
    expected_source_sha256 = _optional_text(
        arguments.get("source_artifact_sha256")
    )
    if (
        expected_source_sha256 is not None
        and expected_source_sha256.casefold() != source_sha256
    ):
        _raise_value_error(
            "source_artifact_sha256 did not match the local source artifact."
        )
    secret_findings = onboarding_secret_findings(source_payload)
    if secret_findings:
        return _project_draft_import_blocked_payload(
            project_id=project_id,
            dry_run=dry_run,
            source_path_text=source_path_display,
            staged_path_text=staged_path_text,
            source_sha256=source_sha256,
            findings=secret_findings,
        )
    existing_sha256 = _existing_json_sha256(staged_path)
    if (
        not dry_run
        and existing_sha256 is not None
        and existing_sha256 != source_sha256
    ):
        _raise_value_error(
            "staged draft path already exists with different JSON content."
        )
    wrote = False
    if not dry_run and existing_sha256 is None:
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_object(staged_path, source_payload)
        wrote = True
    would_change = existing_sha256 != source_sha256
    return {
        "status": "dry_run"
        if dry_run
        else "staged"
        if wrote
        else "already_staged",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": would_change,
        "would_write": would_change,
        "writes_performed": wrote,
        "write_actions": ["write_staged_draft"] if wrote else [],
        "source_artifact_path": source_path_display,
        "source_artifact_sha256": source_sha256,
        "staged_draft_path": staged_path_text,
        "staged_draft_sha256": source_sha256,
        "staged_draft_exists": staged_path.exists(),
        "staged_draft_role": "local_import_draft",
        "draft_artifact_policy": "approved_generated_state",
        "raw_blueprint_values_returned": False,
        "source_artifact_json_returned": False,
        "draft_secret_scan_status": "passed",
        "scrub_status": "passed_no_secret_like_values",
        "secret_like_finding_count": 0,
        "next_queries": _project_draft_import_next_queries(
            project_id=project_id,
            staged_draft_path=staged_path_text,
            staged_draft_sha256=source_sha256,
            dry_run=dry_run,
        ),
        **_local_offline_safety_flags(),
    }


def project_health(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Return a compact health summary for one local Make scenario draft."""
    context = _scenario_context_or_error(
        arguments,
        repo_root,
        tool_name="project.health",
    )
    if isinstance(context, dict):
        return context
    project_id, scenario_path, scenario = context
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    validation_statuses = _validation_statuses(
        summary=summary, runtime_counts=runtime_counts
    )
    return {
        "status": "ok",
        "project_id": project_id,
        "source_of_truth": "local_project_scenario",
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        **summary,
        **runtime_setup_count_payload(runtime_counts),
        **validation_surface_payload(statuses=validation_statuses),
        "next_actions": _state_aware_next_actions(
            summary=summary,
            verification=_verification_context(
                scenario=scenario, profile="import_test"
            ),
            runtime_counts=runtime_counts,
            project_id=project_id,
            profile="import_test",
            mode="plan",
        ),
        "next_queries": (
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "overview",
                    "output_mode": "compact",
                },
                reason="Inspect the compact local scenario overview.",
            ),
            _next_query(
                tool="project.verify",
                arguments={"project_id": project_id, "profile": "import_test"},
                reason="Verify local Make import readiness.",
            ),
        ),
        **_local_offline_safety_flags(),
    }


def create_project(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or create one repository-local project scenario draft.

    Returns:
        The computed value.
    """
    project_id = _required_project_id(arguments)
    storage = _local_project_storage_request(
        arguments=arguments, repo_root=repo_root
    )
    scenario_path = storage["scenario_path"]
    if not isinstance(scenario_path, Path):
        _raise_value_error("Internal project storage path was not resolved.")
    legacy_path = _legacy_scenario_path(
        repo_root=repo_root, project_id=project_id
    )
    metadata_row = _local_project_metadata_row(
        repo_root=repo_root, project_id=project_id
    )
    if (
        metadata_row is not None
        or scenario_path.exists()
        or legacy_path.exists()
    ):
        _raise_value_error(
            "project.create will not overwrite an existing project."
        )
    project_name = _optional_text(arguments.get("name")) or project_id
    blueprint_payload = _optional_make_blueprint_payload(
        arguments, repo_root=repo_root
    )
    legacy_intent_text = _optional_text(
        arguments.get("intent") or arguments.get("customer_intent")
    )
    if legacy_intent_text is not None:
        _raise_value_error(
            "project.create no longer accepts scenario summaries; call project.draft.stage and then pass staged_draft_path with staged_draft_sha256."
        )
    _reject_project_create_prompt_triggering_text(name=project_name)
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    path_report = _local_project_path_report(
        repo_root=repo_root, scenario_path=scenario_path
    )
    if blueprint_payload is not None:
        secret_findings = onboarding_secret_findings(blueprint_payload)
        if secret_findings:
            return _project_create_secret_import_blocked_payload(
                project_id=project_id,
                dry_run=dry_run,
                path_report=path_report,
                secret_findings=secret_findings,
            )
    creation_mode = (
        "from_make_blueprint" if blueprint_payload is not None else "empty_ast"
    )
    metadata = _project_create_metadata(
        project_id=project_id,
        storage=storage,
        blueprint_payload=blueprint_payload,
    )
    evidence_payload = (
        _blueprint_import_evidence_payload(blueprint_payload)
        if blueprint_payload is not None
        else None
    )
    scenario: JsonObject
    if blueprint_payload is not None:
        scenario = _scenario_from_make_blueprint(
            blueprint_payload=blueprint_payload,
            fallback_name=project_name,
            metadata=metadata,
        )
    else:
        scenario = {"name": project_name, "flow": [], "metadata": metadata}
    import_quarantine_records = cast(
        "tuple[JsonObject, ...]",
        metadata.get("import_quarantine_records", ()),
    )
    missing_evidence_records = cast(
        "tuple[JsonObject, ...]",
        metadata.get("missing_evidence_records", ()),
    )
    if evidence_payload is not None:
        evidence_payload["import_quarantine_records"] = (
            import_quarantine_records
        )
        evidence_payload["missing_evidence_records"] = missing_evidence_records
    if not dry_run:
        try:
            scenario_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json_object(scenario_path, scenario)
            if evidence_payload is not None:
                evidence_path = (
                    scenario_path.parent
                    / "artifacts"
                    / BLUEPRINT_IMPORT_EVIDENCE_FILE_NAME
                )
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                _write_json_object(evidence_path, evidence_payload)
            _upsert_local_project_metadata(
                repo_root=repo_root,
                project_id=project_id,
                project_kind="local_scenario_project",
                storage=storage,
            )
        except (PermissionError, sqlite3.OperationalError) as exc:
            return _project_create_permission_denied_payload(
                repo_root=repo_root,
                project_id=project_id,
                scenario_path=scenario_path,
                storage=storage,
                exception=exc,
            )
    return {
        "status": "dry_run" if dry_run else "created",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_create": True,
        "would_change": True,
        "created": not dry_run,
        "writes_performed": not dry_run,
        "write_actions": _project_create_write_actions(
            dry_run=dry_run,
            has_import_evidence=evidence_payload is not None,
        ),
        "storage_model": {
            "sqlite_source_of_truth": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
            "artifact_folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
            "logical_project_path": path_report["logical_project_path"],
            "logical_scenario_path": path_report["logical_scenario_path"],
            "physical_artifact_path": path_report["physical_artifact_path"],
            "physical_scenario_artifact_path": path_report[
                "physical_scenario_artifact_path"
            ],
            "artifact_policy_status": path_report["artifact_policy_status"],
            "artifact_policy_detail": path_report["artifact_policy_detail"],
            "generated_state_physical_path": path_report[
                "generated_state_physical_path"
            ],
            "folder_reconstructable_from_sqlite": True,
            "core_business_state_written": False,
        },
        "creation_mode": creation_mode,
        "ast_source_of_truth": "local_scenario_json",
        "customer_deliverable": "make_blueprint_json",
        "catalog_assisted_module_selection": False,
        "source_blueprint_evidence_stored": bool(
            evidence_payload is not None and not dry_run
        ),
        "source_blueprint_role": "import_evidence_only"
        if blueprint_payload is not None
        else None,
        "import_evidence_path": (
            str(storage["import_evidence_path"])
            if blueprint_payload is not None
            else None
        ),
        "import_quarantine_record_count": len(import_quarantine_records),
        "missing_evidence_record_count": len(missing_evidence_records),
        "human_review_requested": bool(
            import_quarantine_records or missing_evidence_records
        ),
        "human_review_surface": (
            "typed_import_quarantine"
            if import_quarantine_records or missing_evidence_records
            else None
        ),
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "initial_summary": _scenario_summary(scenario),
        "next_queries": _project_create_next_queries(project_id=project_id),
        **_local_offline_safety_flags(),
    }


def _required_scenario_summary(arguments: Mapping[str, object]) -> str:
    summary = _optional_text(arguments.get("scenario_summary"))
    if summary is None:
        _raise_value_error("scenario_summary is required.")
    if len(summary) > SCENARIO_SUMMARY_MAX_LENGTH:
        _raise_value_error("scenario_summary must be 2000 characters or fewer.")
    return summary


def _required_source_artifact_path_text(arguments: Mapping[str, object]) -> str:
    source_path_text = _optional_text(arguments.get("source_artifact_path"))
    if source_path_text is None:
        _raise_value_error("source_artifact_path is required.")
    if (
        PROJECT_CREATE_RAW_DRAFT_TEXT_PATTERN.search(source_path_text)
        is not None
    ):
        _raise_value_error(
            "source_artifact_path must be a clean approved local JSON path."
        )
    return source_path_text


def _redacted_source_artifact_reference(path_text: str) -> str:
    requested_path = Path(path_text)
    name = (
        requested_path.name
        if requested_path.name.endswith(".json")
        else "source-artifact.json"
    )
    return f"unapproved-local-path-redacted/{name}"


def _project_draft_stage_path(
    *,
    repo_root: Path,
    project_id: str,
    file_name: str | None,
) -> Path:
    safe_file_name = _safe_staged_draft_file_name(
        file_name=file_name,
        project_id=project_id,
    )
    return (
        _operator_workspace_root(repo_root)
        / BLUEPRINT_IMPORT_INTAKE_ROOT
        / safe_file_name
    ).resolve()


def _safe_staged_draft_file_name(
    *, file_name: str | None, project_id: str
) -> str:
    safe_name = file_name or f"{project_id}.json"
    if len(safe_name) > STAGED_DRAFT_FILE_NAME_MAX_LENGTH:
        _raise_value_error("staged_draft_file_name is too long.")
    if not safe_name.endswith(".json"):
        _raise_value_error("staged_draft_file_name must end with .json.")
    if safe_name in {".json", "..json"}:
        _raise_value_error(
            "staged_draft_file_name must include a non-empty stem."
        )
    if any(separator in safe_name for separator in ("/", "\\")):
        _raise_value_error(
            "staged_draft_file_name cannot contain path separators."
        )
    if not all(char.isalnum() or char in {"-", "_", "."} for char in safe_name):
        _raise_value_error(
            "staged_draft_file_name must be a safe local file name."
        )
    return safe_name


def _project_draft_stage_input_findings(
    *,
    name: str,
    scenario_summary: str,
) -> tuple[JsonObject, ...]:
    fields: JsonObject = {"name": name, "scenario_summary": scenario_summary}
    findings: list[JsonObject] = [
        dict(finding) for finding in onboarding_secret_findings(fields)
    ]
    for field_name, value in fields.items():
        if not isinstance(value, str):
            continue
        prompt_triggering = (
            PROJECT_CREATE_RAW_DRAFT_TEXT_PATTERN.search(value) is not None
            or NOTE_LOCAL_PATH_PATTERN.search(value) is not None
        )
        if not prompt_triggering:
            continue
        secret_like = (
            PROJECT_DRAFT_SECRET_TEXT_PATTERN.search(value) is not None
        )
        findings.append(
            {
                "class": (
                    "prompt_triggering_secret_like"
                    if secret_like
                    else "prompt_triggering_literal"
                ),
                "field": field_name,
                "redacted": True,
                "secret_like": secret_like,
                "message": (
                    "Use a neutral workflow description; literal endpoints, authorization "
                    "phrases, and private values are not accepted in MCP arguments."
                ),
            }
        )
    return tuple(findings)


def _project_draft_import_blocked_payload(
    *,
    project_id: str,
    dry_run: bool,
    source_path_text: str,
    staged_path_text: str,
    source_sha256: str,
    findings: tuple[JsonObject, ...],
) -> JsonObject:
    return {
        "status": "blocked",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": False,
        "would_write": False,
        "writes_performed": False,
        "write_actions": [],
        "source_artifact_path": source_path_text,
        "source_artifact_sha256": source_sha256,
        "staged_draft_path": staged_path_text,
        "staged_draft_role": "local_import_draft",
        "blocked_surface": "make_import",
        "blocked_surfaces": ["make_import"],
        "unblocked_surfaces": ["structure"],
        "status_reason": (
            "The local source artifact contains secret-like values; staging is blocked "
            "before a draft file is written."
        ),
        "draft_secret_scan_status": "blocked",
        "scrub_status": "blocked_before_write",
        "secret_like_finding_count": len(findings),
        "secret_class_counts": onboarding_secret_class_counts(findings),
        "findings": findings,
        "raw_blueprint_values_returned": False,
        "source_artifact_json_returned": False,
        **_local_offline_safety_flags(),
    }


def _project_draft_import_missing_source_payload(
    *,
    project_id: str,
    dry_run: bool,
    source_path_text: str,
    staged_path_text: str,
) -> JsonObject:
    return {
        "status": "blocked",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": False,
        "would_write": False,
        "writes_performed": False,
        "write_actions": [],
        "source_artifact_path": source_path_text,
        "safe_relative_path": source_path_text,
        "source_artifact_exists": False,
        "staged_draft_path": staged_path_text,
        "staged_draft_role": "local_import_draft",
        "blocked_surface": "make_import",
        "blocked_surfaces": ["make_import"],
        "unblocked_surfaces": ["structure"],
        "blocker_code": "source_artifact_not_found",
        "status_reason": "The local source artifact was not found under approved import roots.",
        "recommended_action": "Create or stage the JSON artifact, then retry project.draft.import.",
        "draft_secret_scan_status": "not_evaluated",
        "scrub_status": "blocked_before_read",
        "secret_like_finding_count": 0,
        "raw_blueprint_values_returned": False,
        "source_artifact_json_returned": False,
        **_local_offline_safety_flags(),
    }


def _project_draft_import_invalid_source_payload(
    *,
    project_id: str,
    dry_run: bool,
    source_path_text: str,
    staged_path_text: str,
) -> JsonObject:
    return {
        "status": "blocked",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": False,
        "would_write": False,
        "writes_performed": False,
        "write_actions": [],
        "source_artifact_path": source_path_text,
        "safe_relative_path": source_path_text,
        "source_artifact_exists": True,
        "staged_draft_path": staged_path_text,
        "staged_draft_role": "local_import_draft",
        "blocked_surface": "make_import",
        "blocked_surfaces": ["make_import"],
        "unblocked_surfaces": ["structure"],
        "blocker_code": "source_artifact_invalid_json",
        "status_reason": (
            "The local source artifact exists but is not an importable JSON object."
        ),
        "recommended_action": (
            "Replace the local artifact with a Make blueprint JSON object, then retry "
            "project.draft.import."
        ),
        "draft_secret_scan_status": "not_evaluated",
        "scrub_status": "blocked_before_import",
        "secret_like_finding_count": 0,
        "raw_blueprint_values_returned": False,
        "source_artifact_json_returned": False,
        **_local_offline_safety_flags(),
    }


def _project_draft_stage_metadata(
    *,
    project_id: str,
    scenario_summary: str,
    catalog_assist: Mapping[str, object],
) -> JsonObject:
    return {
        "created_by": "project.draft.stage",
        "source_of_truth": "local_staged_draft_json",
        "draft_kind": "make_blueprint_staged_draft",
        "project_id": project_id,
        "creation": {
            "mode": "from_scenario_summary",
            "scenario_summary": _bounded_intent_summary(scenario_summary),
            "ast_source_of_truth": "local_staged_draft_json",
            "customer_deliverable": "make_blueprint_json",
            "next_action": "project.create",
        },
        "catalog_assist": cast("JsonObject", _json_copy(catalog_assist)),
        "notes": _starter_scenario_notes(
            include_google_email=_intent_assist_includes_google_email(
                catalog_assist
            )
        ),
    }


def _project_draft_stage_blocked_payload(
    *,
    project_id: str,
    dry_run: bool,
    staged_path_text: str,
    findings: tuple[JsonObject, ...],
    blocked_reason: str,
) -> JsonObject:
    prompt_triggering_count = sum(
        1
        for finding in findings
        if str(finding.get("class") or "").startswith("prompt_triggering")
    )
    secret_like_count = sum(
        1
        for finding in findings
        if finding.get("secret_like") is True
        or not str(finding.get("class") or "").startswith("prompt_triggering")
    )
    return {
        "status": "blocked",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_change": False,
        "would_write": False,
        "writes_performed": False,
        "write_actions": [],
        "staged_draft_path": staged_path_text,
        "staged_draft_role": "local_import_draft",
        "blocked_surface": "make_import",
        "blocked_surfaces": ["make_import"],
        "unblocked_surfaces": ["structure"],
        "status_reason": blocked_reason,
        "draft_secret_scan_status": "blocked",
        "scrub_status": "blocked_before_write",
        "secret_like_finding_count": secret_like_count,
        "secret_class_counts": onboarding_secret_class_counts(findings),
        "prompt_triggering_literal_count": prompt_triggering_count,
        "findings": findings,
        "raw_blueprint_values_returned": False,
        "scenario_summary_returned": False,
        **_local_offline_safety_flags(),
    }


def _existing_json_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return _json_sha256(_read_json_object(path))


def _project_draft_stage_next_queries(
    *,
    project_id: str,
    staged_draft_path: str,
    staged_draft_sha256: str,
    dry_run: bool,
) -> tuple[JsonObject, ...]:
    if dry_run:
        return (
            _next_query(
                tool="project.draft.stage",
                arguments={
                    "project_id": project_id,
                    "scenario_summary": "<same safe scenario summary>",
                    "dry_run": False,
                },
                reason="Write the sanitized local staged draft before importing it.",
            ),
        )
    return (
        _next_query(
            tool="project.create",
            arguments={
                "project_id": project_id,
                "staged_draft_path": staged_draft_path,
                "staged_draft_sha256": staged_draft_sha256,
                "dry_run": True,
            },
            reason="Preview importing the local staged draft into a project artifact.",
        ),
        _next_query(
            tool="project.create",
            arguments={
                "project_id": project_id,
                "staged_draft_path": staged_draft_path,
                "staged_draft_sha256": staged_draft_sha256,
                "dry_run": False,
            },
            reason="Create the local project only after the import preview is clean.",
        ),
    )


def _project_draft_import_next_queries(
    *,
    project_id: str,
    staged_draft_path: str,
    staged_draft_sha256: str,
    dry_run: bool,
) -> tuple[JsonObject, ...]:
    if dry_run:
        return (
            _next_query(
                tool="project.draft.import",
                arguments={
                    "project_id": project_id,
                    "source_artifact_path": "<same approved local JSON artifact>",
                    "source_artifact_sha256": staged_draft_sha256,
                    "dry_run": False,
                },
                reason="Write the scrubbed staged draft before importing it.",
            ),
        )
    return (
        _next_query(
            tool="project.create",
            arguments={
                "project_id": project_id,
                "staged_draft_path": staged_draft_path,
                "staged_draft_sha256": staged_draft_sha256,
                "dry_run": True,
            },
            reason="Preview importing the staged local artifact into a project.",
        ),
        _next_query(
            tool="project.create",
            arguments={
                "project_id": project_id,
                "staged_draft_path": staged_draft_path,
                "staged_draft_sha256": staged_draft_sha256,
                "dry_run": False,
            },
            reason="Create the local project only after the import preview is clean.",
        ),
    )


def _project_create_metadata(
    *,
    project_id: str,
    storage: Mapping[str, object],
    blueprint_payload: JsonObject | None,
) -> JsonObject:
    metadata: JsonObject = {
        "created_by": "project.create",
        "source_of_truth": "sqlite:local_project_metadata",
        "project_kind": "local_scenario_project",
        "project_id": project_id,
        "storage": {
            "folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
            "workspace_folder_key": storage["workspace_folder_key"],
            "scenario_or_product_key": storage["scenario_or_product_key"],
            "logical_project_path": storage["logical_project_path"],
            "logical_scenario_path": storage["logical_scenario_path"],
            "artifact_envelope_path": storage["artifact_envelope_path"],
            "scenario_artifact_path": storage["scenario_artifact_path"],
            "folder_reconstructable_from_sqlite": True,
        },
    }
    if blueprint_payload is not None:
        metadata["creation"] = {
            "mode": "from_make_blueprint",
            "ast_source_of_truth": "local_scenario_json",
            "customer_deliverable": "make_blueprint_json",
        }
        metadata["import_evidence"] = {
            "source_blueprint_role": "import_evidence_only",
            "source_blueprint_sha256": _json_sha256(blueprint_payload),
            "evidence_path": storage["import_evidence_path"],
            "editable_authority": "scenario.json",
        }
    return metadata


def _scenario_from_make_blueprint(
    *,
    blueprint_payload: JsonObject,
    fallback_name: str,
    metadata: JsonObject,
) -> JsonObject:
    projection = translate_make_blueprint_to_pancakes_projection(
        blueprint_payload
    )
    scenario = cast("JsonObject", _json_copy(projection.make_payload))
    _ = scenario.setdefault("name", fallback_name)
    imported_metadata = scenario.get("metadata")
    if isinstance(imported_metadata, dict):
        imported_metadata_payload = cast(
            "JsonObject",
            _json_copy(cast("Mapping[str, object]", imported_metadata)),
        )
        metadata["imported_blueprint_metadata"] = imported_metadata_payload
        if imported_metadata_payload.get("created_by") == "project.draft.stage":
            _promote_staged_draft_metadata(metadata, imported_metadata_payload)
    metadata.update(_blueprint_import_review_payload(scenario))
    scenario["metadata"] = metadata
    return scenario


def _promote_staged_draft_metadata(
    metadata: MutableMapping[str, object],
    staged_metadata: Mapping[str, object],
) -> None:
    """Promote safe generated stage metadata into the active project envelope."""
    catalog_assist = staged_metadata.get("catalog_assist")
    if isinstance(catalog_assist, dict):
        metadata["catalog_assist"] = _json_copy(
            cast("Mapping[str, object]", catalog_assist)
        )
    notes = staged_metadata.get("notes")
    if isinstance(notes, list):
        metadata["notes"] = _json_copy(cast("object", notes))
    scenario_settings = staged_metadata.get("scenario")
    if isinstance(scenario_settings, dict):
        metadata["scenario"] = _json_copy(
            cast("Mapping[str, object]", scenario_settings)
        )


def _optional_make_blueprint_payload(
    arguments: Mapping[str, object],
    *,
    repo_root: Path,
) -> JsonObject | None:
    artifact_path_text = _optional_text(arguments.get("staged_draft_path"))
    if any(
        arguments.get(key) is not None
        for key in (
            "blueprint_artifact_path",
            "make_blueprint_artifact_path",
            "blueprint_artifact_sha256",
        )
    ):
        accepted = "project.create accepts staged_draft_path and staged_draft_sha256 only;"
        message = (
            f"{accepted} legacy blueprint artifact aliases are not accepted."
        )
        _raise_value_error(message)
    if (
        arguments.get("blueprint_json") is not None
        or arguments.get("make_blueprint_json") is not None
    ):
        restriction = "project.create no longer accepts raw blueprint JSON in MCP arguments;"
        message = (
            f"{restriction} stage the draft locally and pass staged_draft_path."
        )
        _raise_value_error(message)
    if artifact_path_text is not None:
        return _make_blueprint_payload_from_artifact(
            repo_root=repo_root,
            path_text=artifact_path_text,
            expected_sha256=_optional_text(
                arguments.get("staged_draft_sha256")
            ),
        )
    return None


def _reject_project_create_prompt_triggering_text(
    *,
    name: str,
) -> None:
    fields: JsonObject = {"name": name}
    if onboarding_secret_findings(fields):
        message = (
            "project.create name cannot contain credential-shaped values; "
            "pass a safe local project name."
        )
        _raise_value_error(message)
    for value in fields.values():
        if isinstance(
            value, str
        ) and PROJECT_CREATE_RAW_DRAFT_TEXT_PATTERN.search(value):
            message = "project.create name cannot contain URLs, authorization text, or raw draft details."
            _raise_value_error(message)


def _project_create_write_actions(
    *, dry_run: bool, has_import_evidence: bool
) -> list[str]:
    if dry_run:
        return []
    actions = ["write_project_scenario", "upsert_local_project_metadata"]
    if has_import_evidence:
        actions.append("write_import_evidence")
    return actions


def _project_create_secret_import_blocked_payload(
    *,
    project_id: str,
    dry_run: bool,
    path_report: Mapping[str, object],
    secret_findings: tuple[JsonObject, ...],
) -> JsonObject:
    return {
        "status": "blocked",
        "project_id": project_id,
        "dry_run": dry_run,
        "would_create": False,
        "would_change": False,
        "created": False,
        "writes_performed": False,
        "write_actions": [],
        "creation_mode": "from_make_blueprint",
        "blocked_surface": "make_import",
        "blocked_surfaces": ["make_import"],
        "unblocked_surfaces": ["structure"],
        "status_reason": (
            "The staged Make blueprint contains secret-like values; import is blocked "
            "before scenario or evidence files are created."
        ),
        "secret_like_finding_count": len(secret_findings),
        "secret_class_counts": onboarding_secret_class_counts(secret_findings),
        "secret_like_findings": secret_findings,
        "raw_blueprint_values_returned": False,
        "source_blueprint_evidence_stored": False,
        "import_quarantine_record_count": 0,
        "missing_evidence_record_count": 0,
        "human_review_requested": True,
        "human_review_surface": "secret_like_import_block",
        "storage_model": {
            "sqlite_source_of_truth": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
            "artifact_folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
            "logical_project_path": path_report["logical_project_path"],
            "logical_scenario_path": path_report["logical_scenario_path"],
            "physical_artifact_path": path_report["physical_artifact_path"],
            "physical_scenario_artifact_path": path_report[
                "physical_scenario_artifact_path"
            ],
            "artifact_policy_status": path_report["artifact_policy_status"],
            "artifact_policy_detail": path_report["artifact_policy_detail"],
            "generated_state_physical_path": path_report[
                "generated_state_physical_path"
            ],
            "folder_reconstructable_from_sqlite": True,
            "core_business_state_written": False,
        },
        **_local_offline_safety_flags(),
    }


def _make_blueprint_payload_from_artifact(
    *,
    repo_root: Path,
    path_text: str,
    expected_sha256: str | None,
) -> JsonObject:
    artifact_path = _make_blueprint_payload_artifact_path(
        repo_root=repo_root, path_text=path_text
    )
    if artifact_path.suffix.casefold() != ".json":
        _raise_value_error("staged_draft_path must point to a JSON file.")
    payload = _read_json_object(artifact_path)
    if expected_sha256 is not None:
        actual_sha256 = _json_sha256(payload)
        if actual_sha256 != expected_sha256.casefold():
            _raise_value_error(
                "staged_draft_sha256 did not match the staged draft artifact."
            )
    return payload


def _make_blueprint_payload_artifact_path(
    *, repo_root: Path, path_text: str
) -> Path:
    return _local_blueprint_import_artifact_path(
        repo_root=repo_root, path_text=path_text
    )


def _local_blueprint_import_artifact_path(
    *, repo_root: Path, path_text: str
) -> Path:
    requested_path = Path(path_text)
    if requested_path.is_absolute():
        return _confined_blueprint_import_artifact_path(
            repo_root=repo_root, path=requested_path
        )
    workspace_root = _operator_workspace_root(repo_root)
    if _path_has_prefix(requested_path, BLUEPRINT_IMPORT_INTAKE_ROOT):
        return _confined_blueprint_import_artifact_path(
            repo_root=repo_root,
            path=workspace_root / requested_path,
        )
    if _path_has_prefix(requested_path, PROJECT_ROOT):
        return _confined_blueprint_import_artifact_path(
            repo_root=repo_root,
            path=repo_root / requested_path,
        )
    _raise_value_error(
        "staged_draft_path must be under temp/pancakes/project-intake or projects."
    )


def _confined_blueprint_import_artifact_path(
    *, repo_root: Path, path: Path
) -> Path:
    resolved = path.resolve()
    repo_root_resolved = repo_root.resolve()
    intake_root = (
        _operator_workspace_root(repo_root) / BLUEPRINT_IMPORT_INTAKE_ROOT
    ).resolve()
    projects_root = (repo_root / PROJECT_ROOT).resolve()
    if resolved == intake_root or intake_root in resolved.parents:
        return resolved
    if resolved == projects_root or projects_root in resolved.parents:
        return resolved
    if resolved == repo_root_resolved or repo_root_resolved in resolved.parents:
        relative = resolved.relative_to(repo_root_resolved)
        if _path_has_prefix(relative, PROJECT_ROOT):
            return resolved
    _raise_value_error(
        "staged_draft_path escaped the approved local import roots."
    )


def _blueprint_import_evidence_payload(
    blueprint_payload: JsonObject,
) -> JsonObject:
    source_text = json.dumps(
        blueprint_payload, sort_keys=True, separators=(",", ":")
    )
    include_source = (
        len(source_text.encode("utf-8")) <= BLUEPRINT_IMPORT_EVIDENCE_MAX_BYTES
    )
    return {
        "evidence_kind": "make_blueprint_import",
        "source_blueprint_role": "import_evidence_only",
        "source_blueprint_sha256": _json_sha256(blueprint_payload),
        "source_blueprint_bytes": len(source_text.encode("utf-8")),
        "source_blueprint_json": blueprint_payload if include_source else None,
        "source_blueprint_json_omitted": not include_source,
        "editable_authority": "scenario.json",
    }


def _json_sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _blueprint_import_review_payload(
    scenario: Mapping[str, object],
) -> JsonObject:
    quarantine_records = tuple(_blueprint_import_quarantine_records(scenario))
    missing_evidence_records = tuple(
        _blueprint_import_missing_evidence_records(quarantine_records)
    )
    return {
        "import_quarantine_records": quarantine_records,
        "missing_evidence_records": missing_evidence_records,
        "human_review_request": {
            "surface": "typed_import_quarantine",
            "record_count": len(quarantine_records)
            + len(missing_evidence_records),
            "review_only": True,
        },
    }


def _blueprint_import_quarantine_records(
    scenario: Mapping[str, object],
) -> Iterator[JsonObject]:
    yield from _unsupported_field_records(
        path="$",
        payload=scenario,
        supported_fields=BLUEPRINT_IMPORT_ROOT_FIELDS,
        structure_kind="root",
    )
    for path, module in _iter_import_module_payloads(
        _flow_from_mapping(scenario), "flow"
    ):
        module_token = _optional_text(module.get("module")) or "unknown"
        if _translated_module(module_token)["change"] == "pass_through":
            yield _import_quarantine_record(
                path=path,
                structure_kind="module",
                reason="Unknown Make module was preserved as raw AST and needs projector review.",
                field="module",
                value=module_token,
            )
        yield from _unsupported_field_records(
            path=path,
            payload=module,
            supported_fields=BLUEPRINT_IMPORT_MODULE_FIELDS,
            structure_kind="module",
        )
        for route_index, route in enumerate(_routes_for_module(module)):
            route_path = f"{path}.routes[{route_index}]"
            yield from _unsupported_field_records(
                path=route_path,
                payload=route,
                supported_fields=BLUEPRINT_IMPORT_ROUTE_FIELDS,
                structure_kind="route",
            )
            filter_value = route.get("filter")
            if isinstance(filter_value, dict):
                yield from _unsupported_field_records(
                    path=f"{route_path}.filter",
                    payload=cast("Mapping[str, object]", filter_value),
                    supported_fields=BLUEPRINT_IMPORT_FILTER_FIELDS,
                    structure_kind="filter",
                )


def _blueprint_import_missing_evidence_records(
    quarantine_records: Sequence[Mapping[str, object]],
) -> Iterator[JsonObject]:
    for record in quarantine_records:
        if record.get("field") != "module":
            continue
        module_token = _optional_text(record.get("value")) or "unknown"
        yield {
            "record_kind": "missing_evidence",
            "record_id": _stable_import_record_id(
                "missing-evidence", str(record["path"])
            ),
            "evidence_kind": "module_projector",
            "module": module_token,
            "path": record["path"],
            "status": "needs_review",
            "reason": (
                "Unknown imported module is preserved, but catalog/projector evidence is "
                "missing for semantic edits."
            ),
        }


def _unsupported_field_records(
    *,
    path: str,
    payload: Mapping[str, object],
    supported_fields: frozenset[str],
    structure_kind: str,
) -> Iterator[JsonObject]:
    for field in sorted(set(payload) - supported_fields):
        yield _import_quarantine_record(
            path=path,
            structure_kind=structure_kind,
            reason="Unsupported Make blueprint field was preserved and needs review.",
            field=field,
            value=None,
        )


def _iter_import_module_payloads(
    flow: Sequence[object],
    path: str,
) -> Iterator[tuple[str, JsonObject]]:
    for index, item in enumerate(flow):
        if not isinstance(item, dict):
            continue
        module = cast("JsonObject", item)
        module_path = f"{path}[{index}]"
        yield module_path, module
        for route_index, route in enumerate(_routes_for_module(module)):
            yield from _iter_import_module_payloads(
                _flow_from_mapping(route),
                f"{module_path}.routes[{route_index}].flow",
            )
        for handler_index, handler in enumerate(_handlers_for_module(module)):
            yield f"{module_path}.onerror[{handler_index}]", handler
            yield from _iter_import_module_payloads(
                _flow_from_mapping(handler),
                f"{module_path}.onerror[{handler_index}].flow",
            )


def _import_quarantine_record(
    *,
    path: str,
    structure_kind: str,
    reason: str,
    field: str,
    value: object,
) -> JsonObject:
    return {
        "record_kind": "import_quarantine",
        "record_id": _stable_import_record_id("import-quarantine", path, field),
        "structure_kind": structure_kind,
        "path": path,
        "field": field,
        "value": value,
        "status": "needs_review",
        "reason": reason,
        "review_surface": "typed_import_quarantine",
    }


def _stable_import_record_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _starter_scenario_from_intent(
    *,
    project_name: str,
    metadata: JsonObject,
) -> JsonObject:
    include_google_email = _intent_metadata_includes_google_email(metadata)
    datastore_error_handler_id = 6 if include_google_email else 5
    routes: list[JsonObject] = [
        {
            "filter": {
                "name": "Needs team notification",
                "condition": "{{1.priority}} = urgent",
            },
            "flow": [
                {
                    "id": 4,
                    "module": "slack:ActionCreateMessage",
                    "parameters": {
                        "account": "{{runtime.connection.slack_ops}}",
                        "channel": "{{runtime.slack.channel.ops_alerts}}",
                    },
                    "mapper": {
                        "text": (
                            "New customer request {{1.request_id}} from "
                            "{{1.customer_name}}: {{1.message}}"
                        )
                    },
                }
            ],
        }
    ]
    if include_google_email:
        routes.append(
            {
                "filter": {
                    "name": "Send customer email acknowledgement",
                    "condition": "{{1.email}} exists",
                },
                "flow": [
                    {
                        "id": 5,
                        "module": "google-email:ActionSendEmail",
                        "parameters": {
                            "account": "{{runtime.connection.google_email_ops}}",
                        },
                        "mapper": {
                            "to": ["{{1.email}}"],
                            "subject": "Request {{1.request_id}} received",
                            "html": (
                                "<p>Thanks for contacting us. We received request "
                                "{{1.request_id}} and will follow up.</p>"
                            ),
                        },
                    }
                ],
            }
        )
    return {
        "name": project_name,
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {
                    "hook": "{{runtime.webhook.customer_intent_hook}}"
                },
                "mapper": {},
            },
            {
                "id": 2,
                "module": BASIC_ROUTER_MODULE,
                "routes": routes,
            },
            {
                "id": 3,
                "module": "datastore:AddRecord",
                "parameters": {
                    "datastore": "{{runtime.datastore.customer_requests}}"
                },
                "mapper": {
                    "data": {
                        "customer_name": "{{1.customer_name}}",
                        "email": "{{1.email}}",
                        "message": "{{1.message}}",
                        "priority": "{{1.priority}}",
                        "request_id": "{{1.request_id}}",
                    },
                    "key": "{{1.request_id}}",
                    "overwrite": False,
                },
                "onerror": [
                    _starter_break_error_handler(
                        handler_id=datastore_error_handler_id
                    )
                ],
            },
        ],
        "metadata": {
            **metadata,
            "scenario": dict(MAKE_NATIVE_SCENARIO_SETTINGS_DEFAULTS),
        },
    }


def _starter_break_error_handler(*, handler_id: int) -> JsonObject:
    return {
        "id": handler_id,
        "module": "builtin:Break",
        "version": 1,
        "parameters": {},
        "mapper": {
            "count": "3",
            "retry": "{{true}}",
            "interval": "15",
        },
        "metadata": {
            "restore": {"expect": {"retry": {"mode": "edit"}}},
            "expect": [
                {
                    "name": "retry",
                    "type": "boolean",
                    "label": "Retry automatically",
                    "required": True,
                },
                {
                    "name": "count",
                    "type": "uinteger",
                    "label": "Number of retries",
                    "required": True,
                    "validate": {"max": 10000, "min": 1},
                },
                {
                    "name": "interval",
                    "type": "uinteger",
                    "label": "Minutes between retries",
                    "required": True,
                    "validate": {"max": 44640, "min": 1},
                },
            ],
        },
    }


def _intent_catalog_assist_metadata(intent_text: str) -> JsonObject:
    normalized = intent_text.casefold()
    capability_terms: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("webhook", ("webhook", "lead", "request", "intake")),
        ("datastore", ("store", "datastore", "record")),
        ("slack", ("slack", "alert", "notification")),
        ("google_email", ("google email", "gmail", "email")),
    )
    requested_capabilities = tuple(
        capability
        for capability, terms in capability_terms
        if any(term in normalized for term in terms)
    )
    matched_terms = tuple(
        term
        for _capability, terms in capability_terms
        for term in terms
        if term in normalized
    )
    selected_modules: list[str] = [
        "gateway:CustomWebHook",
        BASIC_ROUTER_MODULE,
        "datastore:AddRecord",
        "slack:ActionCreateMessage",
    ]
    if "google_email" in requested_capabilities:
        selected_modules.append("google-email:ActionSendEmail")
    return {
        "selection_mode": "deterministic_local_catalog_hints",
        "matched_terms": matched_terms,
        "requested_capabilities": requested_capabilities,
        "selected_modules": tuple(selected_modules),
        "missing_capabilities": (),
        "intent_coverage_status": "covered",
        "intent_coverage_gap_count": 0,
        "provider_api_call": False,
        "live_make_called": False,
    }


def _intent_assist_includes_google_email(
    catalog_assist: Mapping[str, object],
) -> bool:
    selected_modules = catalog_assist.get("selected_modules")
    if not isinstance(selected_modules, list | tuple):
        return False
    modules = cast("Sequence[object]", selected_modules)
    return "google-email:ActionSendEmail" in {str(module) for module in modules}


def _intent_metadata_includes_google_email(
    metadata: Mapping[str, object],
) -> bool:
    catalog_assist = metadata.get("catalog_assist")
    if not isinstance(catalog_assist, dict):
        return False
    return _intent_assist_includes_google_email(
        cast("Mapping[str, object]", catalog_assist)
    )


def _starter_scenario_notes(
    *, include_google_email: bool = False
) -> list[JsonObject]:
    datastore_error_handler_id = "6" if include_google_email else "5"
    notes = [
        _starter_module_note(
            node_id="1",
            label="Customer intake webhook",
            purpose="Receives the customer request and starts the intake workflow.",
            input_contract="Accepts the submitted request fields from the configured webhook.",
            output_contract="Makes the request details available to the routing step.",
            operator_check="Confirm the webhook is selected and active before handoff.",
        ),
        _starter_module_note(
            node_id="2",
            label="Request routing",
            purpose="Separates urgent and routine requests into the right workflow path.",
            input_contract="Uses request priority and contact fields from the intake step.",
            output_contract="Sends each request to the matching storage or notification branch.",
            operator_check="Confirm each route condition matches the customer priority policy.",
        ),
        _starter_module_note(
            node_id="3",
            label="Request record",
            purpose="Records handled requests in the customer-owned data store.",
            input_contract="Receives request identifiers, contact fields, and message details.",
            output_contract="Stores a durable request record for follow-up and audit.",
            operator_check="Confirm the target data store exists before handoff.",
        ),
        _starter_module_note(
            node_id=datastore_error_handler_id,
            label="Storage retry guard",
            purpose="Handles temporary storage write failures without losing the request.",
            input_contract="Receives the failed storage operation and retry context from Make.",
            output_contract="Retries the storage step using the configured retry count and interval.",
            operator_check="Confirm retry count, interval, and incomplete execution settings before handoff.",
        ),
        _starter_module_note(
            node_id="4",
            label="Team notification",
            purpose="Alerts the team when an urgent request needs fast attention.",
            input_contract="Receives the routed urgent request summary from the router.",
            output_contract="Posts a concise notification to the configured team channel.",
            operator_check="Confirm the team channel and account are selected in Make.",
        ),
        _starter_connection_note(
            source_id="1",
            target_id="2",
            label="Intake to routing",
            handoff="Routes captured request fields into the decision branch.",
            data_contract="Request identifier, priority, contact fields, and message stay mapped.",
            failure_signal="Missing request identity or priority should pause handoff review.",
        ),
        _starter_connection_note(
            source_id="2",
            target_id="3",
            label="Routing to storage",
            handoff="Persists each request after routing decisions are available.",
            data_contract="The storage step receives the request identity and follow-up details.",
            failure_signal="A missing storage key or request identity should block activation.",
        ),
        _starter_connection_note(
            source_id="3",
            target_id=datastore_error_handler_id,
            label="Storage failure to retry guard",
            handoff="Transfers storage write failures to the retry handler for controlled recovery.",
            data_contract="The retry handler keeps the failing storage operation context available.",
            failure_signal="Missing retry configuration should block activation before handoff.",
        ),
        _starter_connection_note(
            source_id="2",
            target_id="4",
            label="Routing to notification",
            handoff="Sends urgent routed requests to the team notification branch.",
            data_contract="The notification step receives contact details and urgency context.",
            failure_signal="A missing recipient channel or summary should stop handoff.",
        ),
    ]
    if include_google_email:
        notes.extend(
            (
                _starter_module_note(
                    node_id="5",
                    label="Customer email acknowledgement",
                    purpose="Sends a Google Email acknowledgement to the requester.",
                    input_contract="Receives the customer email and request identifier.",
                    output_contract="Sends a confirmation email from the client-owned account.",
                    operator_check="Confirm the Google Email account is selected in Make.",
                ),
                _starter_connection_note(
                    source_id="2",
                    target_id="5",
                    label="Routing to customer email",
                    handoff="Sends routine routed requests to the customer email branch.",
                    data_contract="The email step receives the customer email and request ID.",
                    failure_signal="Missing customer email should skip or block the email branch.",
                ),
            )
        )
    return notes


def _starter_module_note(
    *,
    node_id: str,
    label: str,
    purpose: str,
    input_contract: str,
    output_contract: str,
    operator_check: str,
) -> JsonObject:
    sections = {
        "Purpose": purpose,
        "Input": input_contract,
        "Output": output_contract,
        "Operator check": operator_check,
    }
    return {
        "note_kind": "module",
        "target_node_id": node_id,
        "citation_ref": f"NOTE-MOD-{node_id}",
        "title": f"MOD-{node_id} | {label}",
        "sections": sections,
        "body": _note_sections_body(sections),
    }


def _starter_connection_note(
    *,
    source_id: str,
    target_id: str,
    label: str,
    handoff: str,
    data_contract: str,
    failure_signal: str,
) -> JsonObject:
    sections = {
        "Handoff": handoff,
        "Data contract": data_contract,
        "Failure signal": failure_signal,
    }
    return {
        "note_kind": "connection",
        "source_node_id": source_id,
        "target_node_id": target_id,
        "citation_ref": f"NOTE-CONN-{source_id}-{target_id}",
        "title": f"CONN-{source_id}-{target_id} | {label}",
        "sections": sections,
        "body": _note_sections_body(sections),
    }


def _bounded_intent_summary(intent_text: str) -> str:
    summary = " ".join(intent_text.split())
    if len(summary) <= INTENT_SUMMARY_MAX_LENGTH:
        return summary
    prefix_length = INTENT_SUMMARY_MAX_LENGTH - INTENT_SUMMARY_ELLIPSIS_LENGTH
    return f"{summary[:prefix_length].rstrip()}..."


def _project_create_next_queries(*, project_id: str) -> tuple[JsonObject, ...]:
    return (
        _next_query(
            tool="project.view",
            arguments={"project_id": project_id, "surface": "overview"},
            reason="Inspect the local AST created for this project.",
        ),
        _next_query(
            tool="project.make",
            arguments={"project_id": project_id, "action": "preview"},
            reason="Preview the customer-facing Make blueprint artifact.",
        ),
    )


def view_project(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Return a bounded local Make scenario IDE surface."""
    context = _scenario_context_or_error(
        arguments,
        repo_root,
        tool_name="project.view",
    )
    if isinstance(context, dict):
        return context
    project_id, scenario_path, scenario = context
    output_mode = _project_output_mode(
        arguments.get("output_mode"), default="compact"
    )
    surface = _project_surface(arguments.get("surface"))
    limit = _project_view_limit(arguments.get("limit"), output_mode=output_mode)
    focus = _focus_payload(arguments)
    summary = _scenario_summary(scenario)
    surface_payload = _surface_payload(
        scenario=scenario,
        surface=surface,
        focus=focus,
        output_mode=output_mode,
        limit=limit,
        project_id=project_id,
    )
    return {
        "status": "ok",
        "project_id": project_id,
        "context_surface": "project_view",
        "surface": surface,
        "source": "local_project_scenario",
        "source_of_truth": "local_project_scenario",
        "source_path": _local_project_display_path(
            repo_root=repo_root, path=scenario_path
        ),
        "output_mode": output_mode,
        "focus": focus,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "scenario_overview": {
            "name": _optional_text(scenario.get("name")) or project_id,
            **summary,
        },
        **surface_payload,
        **_local_offline_safety_flags(),
    }


def edit_project(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Route one semantic project edit to the narrow local node-editor implementation.

    Returns:
        The computed value.
    """
    surface = _project_edit_surface(arguments.get("surface"))
    operation = _project_edit_operation(arguments.get("operation"))
    dispatch_arguments = dict(arguments)
    if "target" in arguments:
        target = arguments["target"]
        if not isinstance(target, dict):
            _raise_value_error("target must be a JSON object when provided.")
        dispatch_arguments.update(cast("Mapping[str, object]", target))
    payload = _project_edit_payload(arguments.get("payload_json"))
    if surface == "modules":
        return _edit_project_module(
            operation=operation,
            arguments=dispatch_arguments,
            payload=payload,
            repo_root=repo_root,
        )
    if surface == "filters":
        return _edit_project_filter(
            operation=operation,
            arguments=dispatch_arguments,
            payload=payload,
            repo_root=repo_root,
        )
    if surface == "error_handlers":
        return _edit_project_error_handler(
            operation=operation,
            arguments=dispatch_arguments,
            payload=payload,
            repo_root=repo_root,
        )
    if surface == "datastores":
        return _edit_project_datastore_manifest(
            operation=operation,
            arguments=dispatch_arguments,
            payload=payload,
            repo_root=repo_root,
        )
    if surface == "notes":
        return _edit_project_notes(
            operation=operation,
            arguments=dispatch_arguments,
            payload=payload,
            repo_root=repo_root,
        )
    _raise_value_error(
        "project.edit supports modules, filters, error_handlers, datastores, and notes surfaces."
    )


def project_make(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Preview or locally write a Make-native artifact projection.

    Returns:
        The computed value.
    """
    context = _scenario_context_or_error(
        arguments,
        repo_root,
        tool_name="project.make",
    )
    if isinstance(context, dict):
        return context
    project_id, scenario_path, scenario = context
    action = _project_make_action(arguments.get("action"))
    profile = _project_make_profile(arguments.get("profile"))
    output_mode = _project_output_mode(
        arguments.get("output_mode"), default="compact"
    )
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    include_blueprint_json = _bool_argument(
        arguments.get("include_blueprint_json"), default=False
    )
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    projection = _make_artifact_projection(scenario)
    verification_profile = (
        "handoff_test" if profile == "client_handoff" else profile
    )
    verification = _verification_context(
        scenario=scenario,
        profile=verification_profile,
    )
    handoff_verification = _verification_context(
        scenario=scenario, profile="handoff_test"
    )
    preview = _make_preview_payload(
        scenario=scenario,
        projection=projection,
        summary=summary,
        runtime_counts=runtime_counts,
        output_mode=output_mode,
        include_blueprint_json=include_blueprint_json,
        verification=verification,
    )
    zero_trace_blocked = preview.get("zero_trace_status") == "failed"
    handoff_blocked = profile == "client_handoff" and (
        preview.get("client_handoff_status") == "blocked" or zero_trace_blocked
    )
    package_write_blocked = (
        action == "package"
        and not dry_run
        and profile == "client_handoff"
        and (
            handoff_verification["client_handoff_status"] == "blocked"
            or zero_trace_blocked
        )
    )
    package_blocked = action == "package" and (
        handoff_blocked or package_write_blocked or zero_trace_blocked
    )
    artifact_render_status = (
        "blocked_by_zero_trace" if zero_trace_blocked else "rendered"
    )
    artifact_path = (
        scenario_path.parent / "artifacts" / "make-blueprint.preview.json"
    )
    package_path = (
        scenario_path.parent / "artifacts" / "make-import-package.json"
    )
    customer_package_path = (
        scenario_path.parent
        / "artifacts"
        / CUSTOMER_DELIVERY_PACKAGE_FOLDER_NAME
    )
    live_resource_package_path = (
        scenario_path.parent
        / "artifacts"
        / MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME
    )
    wrote_artifact = False
    (
        package_payload,
        wrote_package,
        wrote_customer_package,
        wrote_live_resource_package,
    ) = _project_make_package_response(
        action=action,
        project_id=project_id,
        scenario=scenario,
        profile=profile,
        dry_run=dry_run,
        output_mode=output_mode,
        preview=preview,
        verification=verification,
        package_blocked=package_blocked,
        package_path=package_path,
        customer_package_path=customer_package_path,
        live_resource_package_path=live_resource_package_path,
        projection=projection,
    )
    if action == "write" and not dry_run and not handoff_blocked:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_object(artifact_path, projection)
        wrote_artifact = True
    status = (
        "blocked"
        if zero_trace_blocked or handoff_blocked or package_blocked
        else "updated"
        if wrote_artifact or wrote_package
        else "ready"
        if action == "package"
        else "ok"
    )
    payload: JsonObject = {
        "status": status,
        "project_id": project_id,
        "action": action,
        "profile": profile,
        "output_mode": output_mode,
        "source_of_truth": "local_project_scenario",
        "artifact_kind": "make_blueprint_projection",
        "artifact_format": "make_blueprint_json",
        "artifact_written": wrote_artifact,
        "artifact_preview_status": preview["preview_status"],
        "artifact_render_status": artifact_render_status,
        "artifact_path": (
            _local_project_display_path(repo_root=repo_root, path=artifact_path)
            if wrote_artifact or action == "write"
            else None
        ),
        "package_kind": "make_import_package" if action == "package" else None,
        "package_profile": profile if action == "package" else None,
        "package_written": wrote_package,
        "customer_delivery_package_written": wrote_customer_package,
        "live_resource_package_written": wrote_live_resource_package,
        "writes_performed": bool(
            wrote_artifact
            or wrote_package
            or wrote_customer_package
            or wrote_live_resource_package
        ),
        "write_actions": _project_make_write_actions(
            wrote_artifact=wrote_artifact,
            wrote_package=wrote_package,
            wrote_customer_package=wrote_customer_package,
            wrote_live_resource_package=wrote_live_resource_package,
        ),
        "package_path": (
            _local_project_display_path(repo_root=repo_root, path=package_path)
            if wrote_package
            else None
        ),
        "customer_delivery_package_path": (
            _local_project_display_path(
                repo_root=repo_root, path=customer_package_path
            )
            if wrote_customer_package
            else None
        ),
        "live_resource_package_path": (
            _local_project_display_path(
                repo_root=repo_root, path=live_resource_package_path
            )
            if wrote_live_resource_package
            else None
        ),
        "dry_run": dry_run,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        **_local_offline_safety_flags(),
    }
    if action != "package" or output_mode in {"full", "debug"}:
        payload.update(preview)
    if package_payload is not None:
        payload.update(package_payload)
        if package_blocked and not wrote_package:
            payload["status"] = "package_blocked"
            payload["package_status"] = "blocked"
            if package_write_blocked:
                payload["package_write_status"] = "blocked_by_client_handoff"
        if wrote_package:
            payload["status"] = "package_written"
            payload["status_surface"] = "local_package"
            payload["status_reason"] = (
                "The local Make import package was written; full live validation remains "
                "separate and gated outside Pancakes MCP."
            )
    payload.update(
        _project_make_blocked_surface_payload(
            zero_trace_blocked=zero_trace_blocked,
            handoff_blocked=handoff_blocked,
            package_write_blocked=package_write_blocked,
        )
    )
    return payload


def inspect_project_package(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Inspect one bounded local package section without returning the full package payload.

    Returns:
        The computed value.
    """
    context = _scenario_context_or_error(
        arguments,
        repo_root,
        tool_name="project.package.inspect",
    )
    if isinstance(context, dict):
        return context
    project_id, _scenario_path, scenario = context
    profile = _project_make_profile(arguments.get("profile"))
    output_mode = _project_output_mode(
        arguments.get("output_mode"), default="compact"
    )
    section = _project_package_inspect_section(arguments.get("section"))
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    projection = _make_artifact_projection(scenario)
    verification_profile = (
        "handoff_test" if profile == "client_handoff" else profile
    )
    verification = _verification_context(
        scenario=scenario,
        profile=verification_profile,
    )
    handoff_verification = _verification_context(
        scenario=scenario,
        profile="handoff_test",
    )
    preview = _make_preview_payload(
        scenario=scenario,
        projection=projection,
        summary=summary,
        runtime_counts=runtime_counts,
        output_mode="compact",
        include_blueprint_json=False,
        verification=verification,
    )
    zero_trace_blocked = preview.get("zero_trace_status") == "failed"
    handoff_blocked = profile == "client_handoff" and (
        preview.get("client_handoff_status") == "blocked" or zero_trace_blocked
    )
    package_write_blocked = profile == "client_handoff" and (
        handoff_verification["client_handoff_status"] == "blocked"
        or zero_trace_blocked
    )
    package_blocked = (
        handoff_blocked or package_write_blocked or zero_trace_blocked
    )
    package_payload, _, _, _ = _project_make_package_response(
        action="package",
        project_id=project_id,
        scenario=scenario,
        profile=profile,
        dry_run=True,
        output_mode="full",
        preview=preview,
        verification=verification,
        package_blocked=package_blocked,
        package_path=Path(),
        customer_package_path=Path(),
        live_resource_package_path=Path(),
        projection=projection,
    )
    if package_payload is None:
        _raise_assertion_error("package inspection requires a package payload")
    section_payload = _project_package_section_payload(
        package_payload=package_payload,
        section=section,
        output_mode=output_mode,
    )
    return {
        "status": "ok"
        if package_payload["package_status"] == "ready"
        else "package_blocked",
        "status_surface": "sectioned_package_inspection",
        "status_reason": (
            "Returned one bounded package section instead of the full package payload."
        ),
        "project_id": project_id,
        "action": "inspect",
        "profile": profile,
        "section": section,
        "available_sections": PROJECT_PACKAGE_INSPECT_SECTIONS,
        "output_mode": output_mode,
        "package_status": package_payload["package_status"],
        "package_kind": package_payload["package_kind"],
        "section_payload": section_payload,
        "section_payload_returned": section,
        "section_inspection_status": "available",
        "section_inspector_sections": PROJECT_PACKAGE_INSPECT_SECTIONS,
        "section_inspector_queries": _project_package_inspector_queries(
            project_id=project_id,
            profile=profile,
        ),
        "full_output_truncation_avoidance": (
            "Use project.package.inspect output_mode=full for one section at a time; "
            "do not paste the full package payload into chat."
        ),
        "full_package_response_avoided": True,
        "large_package_payload_returned": False,
        "raw_blueprint_json_omitted_from_response": True,
        "writes_performed": False,
        "write_actions": [],
        **_local_offline_safety_flags(),
    }


def _project_make_blocked_surface_payload(
    *,
    zero_trace_blocked: bool,
    handoff_blocked: bool,
    package_write_blocked: bool,
) -> JsonObject:
    if not (zero_trace_blocked or handoff_blocked or package_write_blocked):
        return {}
    blocked_surfaces = ["zero_trace"] if zero_trace_blocked else []
    if handoff_blocked or package_write_blocked:
        blocked_surfaces.append("client_handoff")
    status_reason = (
        "Rendered artifact failed zero-trace; customer-facing output is blocked."
        if zero_trace_blocked
        else "Client handoff notes are incomplete; import-safe artifact preview remains available."
    )
    return blocked_surface_payload(
        blocked_surfaces=blocked_surfaces,
        unblocked_surfaces=("structure", "make_import", "runtime_setup"),
        status_reason=status_reason,
    )


def _project_make_write_actions(
    *,
    wrote_artifact: bool,
    wrote_package: bool,
    wrote_customer_package: bool,
    wrote_live_resource_package: bool,
) -> list[str]:
    actions: list[str] = []
    if wrote_artifact:
        actions.append("write_make_preview_artifact")
    if wrote_package:
        actions.append("write_make_import_package")
    if wrote_customer_package:
        actions.append("write_customer_delivery_package")
    if wrote_live_resource_package:
        actions.append("write_make_live_resource_package")
    return actions


def _project_make_package_response(
    *,
    action: str,
    project_id: str,
    scenario: Mapping[str, object],
    profile: str,
    dry_run: bool,
    output_mode: str,
    preview: Mapping[str, object],
    verification: Mapping[str, object],
    package_blocked: bool,
    package_path: Path,
    customer_package_path: Path,
    live_resource_package_path: Path,
    projection: JsonObject,
) -> tuple[JsonObject | None, bool, bool, bool]:
    if action != "package":
        return None, False, False, False
    package_payload = _make_import_package_payload(
        project_id=project_id,
        scenario=scenario,
        profile=profile,
        dry_run=dry_run,
        output_mode=output_mode,
        preview=preview,
        verification=verification,
    )
    customer_delivery_package = _customer_delivery_package_payload(
        project_id=project_id,
        scenario=scenario,
    )
    live_resource_package = _make_live_resource_package(
        project_id=project_id,
        scenario=scenario,
        datastore_manifest=cast(
            "Mapping[str, object]", package_payload["datastore_manifest"]
        )
        if "datastore_manifest" in package_payload
        else _datastore_manifest(scenario=scenario, output_mode="full"),
    )
    planned_files = _planned_customer_package_files(customer_delivery_package)
    planned_live_resource_files = _planned_make_live_resource_files(
        live_resource_package
    )
    package_payload["customer_delivery_package"] = customer_delivery_package
    if output_mode not in {"full", "debug"}:
        package_payload["make_live_resource_package"] = (
            _make_live_resource_package_summary(live_resource_package)
        )
    package_payload["customer_delivery_package_status"] = (
        "ready"
        if package_payload.get("package_status") == "ready"
        else "blocked"
    )
    package_payload["live_resource_artifact_status"] = live_resource_package[
        "status"
    ]
    package_payload["planned_files"] = planned_files
    package_payload["planned_file_count"] = len(planned_files)
    package_payload["planned_live_resource_files"] = planned_live_resource_files
    package_payload["planned_live_resource_file_count"] = len(
        planned_live_resource_files
    )
    package_payload["package_write_status"] = (
        "dry_run_no_write"
        if dry_run
        else "blocked_no_write"
        if package_blocked
        else "write_enabled_after_validation"
    )
    if dry_run or package_blocked:
        return package_payload, False, False, False
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_file_payload = _make_import_package_payload(
        project_id=project_id,
        scenario=scenario,
        profile=profile,
        dry_run=False,
        output_mode="full",
        preview=preview,
        verification=verification,
    )
    package_file_payload["blueprint_artifact_json"] = projection
    package_file_payload["customer_delivery_package"] = (
        customer_delivery_package
    )
    package_file_payload["make_live_resource_package"] = live_resource_package
    _write_json_object(package_path, package_file_payload)
    _write_customer_delivery_package(
        package_path=customer_package_path,
        delivery_package=customer_delivery_package,
        projection=projection,
    )
    _write_make_live_resource_package(
        package_path=live_resource_package_path,
        resource_package=live_resource_package,
    )
    return package_payload, True, True, True


def _planned_customer_package_files(
    delivery_package: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    files = cast("tuple[JsonObject, ...]", delivery_package["files"])
    return tuple(
        {
            "path": str(file_record["path"]),
            "artifact_role": str(file_record["artifact_role"]),
            "customer_visible": bool(file_record["customer_visible"]),
            "write_status": "planned",
        }
        for file_record in files
    )


def _planned_make_live_resource_files(
    resource_package: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    files = cast("tuple[JsonObject, ...]", resource_package["files"])
    return tuple(
        {
            "path": str(file_record["path"]),
            "artifact_role": str(file_record["artifact_role"]),
            "customer_visible": False,
            "write_status": "planned",
        }
        for file_record in files
    )


def _make_live_resource_package_summary(
    resource_package: Mapping[str, object],
) -> JsonObject:
    return {
        "package_kind": resource_package["package_kind"],
        "status": resource_package["status"],
        "artifact_folder_name": resource_package["artifact_folder_name"],
        "auto_provisioned_resource_count": resource_package[
            "auto_provisioned_resource_count"
        ],
        "client_supplied_connection_count": resource_package[
            "client_supplied_connection_count"
        ],
        "client_supplied_runtime_value_count": resource_package[
            "client_supplied_runtime_value_count"
        ],
        "file_count": resource_package["file_count"],
        "files": resource_package["files"],
        "dependency_order": resource_package["dependency_order"],
        "resource_creation_order": resource_package["resource_creation_order"],
        "resource_creation_order_human": resource_package[
            "resource_creation_order_human"
        ],
        "live_canary_contract": resource_package["live_canary_contract"],
        "cleanup_semantics": resource_package["cleanup_semantics"],
        "dynamic_api_key_policy": resource_package["dynamic_api_key_policy"],
        "one_command_upload_entrypoint": resource_package[
            "one_command_upload_entrypoint"
        ],
    }


def _project_package_section_payload(
    *,
    package_payload: Mapping[str, object],
    section: str,
    output_mode: str,
) -> JsonObject:
    include_details = output_mode in {"full", "debug"}
    if section == "live_resources":
        return _project_package_live_resources_section(
            resource_package=cast(
                "Mapping[str, object]",
                package_payload["make_live_resource_package"],
            ),
            include_details=include_details,
        )
    if section == "blueprint_summary":
        return _project_package_blueprint_summary_section(package_payload)
    if section == "parity_plan":
        return _project_package_parity_plan_section(
            package_payload=package_payload,
            include_details=include_details,
        )
    if section == "customer_files":
        return _project_package_customer_files_section(
            customer_package=cast(
                "Mapping[str, object]",
                package_payload["customer_delivery_package"],
            ),
            include_details=include_details,
        )
    if section == "zero_trace":
        return _project_package_zero_trace_section(package_payload)
    _raise_assertion_error(f"unhandled project package section: {section}")


def _project_package_inspector_queries(
    *,
    project_id: str,
    profile: str,
) -> tuple[JsonObject, ...]:
    return tuple(
        _next_query(
            tool="project.package.inspect",
            arguments={
                "project_id": project_id,
                "profile": profile,
                "section": section,
                "output_mode": "full",
            },
            reason=PROJECT_PACKAGE_INSPECTOR_REASONS[section],
        )
        for section in PROJECT_PACKAGE_INSPECT_SECTIONS
    )


def _project_package_live_resources_section(
    *, resource_package: Mapping[str, object], include_details: bool
) -> JsonObject:
    data_structures = cast(
        "tuple[JsonObject, ...]", resource_package["data_structures"]
    )
    data_stores = cast(
        "tuple[JsonObject, ...]", resource_package["data_stores"]
    )
    webhooks = cast("tuple[JsonObject, ...]", resource_package["webhooks"])
    project_local_structure_available = bool(
        data_structures or data_stores or webhooks
    )
    payload: JsonObject = {
        "section": "live_resources",
        "status": resource_package["status"],
        "evidence_scope": "project_local_manifest_evidence",
        "global_catalog_structure_evidence": "not_required_for_project_local_manifest",
        "project_local_structure_evidence": (
            "available" if project_local_structure_available else "not_required"
        ),
        "blocking": False,
        "artifact_folder_name": resource_package["artifact_folder_name"],
        "file_count": resource_package["file_count"],
        "files": resource_package["files"],
        "data_structure_count": len(data_structures),
        "data_store_count": len(data_stores),
        "webhook_count": len(webhooks),
        "client_supplied_connection_count": resource_package[
            "client_supplied_connection_count"
        ],
        "client_supplied_runtime_value_count": resource_package[
            "client_supplied_runtime_value_count"
        ],
        "resource_creation_order": resource_package["resource_creation_order"],
        "resource_creation_order_human": resource_package[
            "resource_creation_order_human"
        ],
        "manual_make_ui_required_for_resources": resource_package[
            "manual_make_ui_required_for_resources"
        ],
        "one_command_upload_entrypoint": resource_package[
            "one_command_upload_entrypoint"
        ],
        "cleanup_semantics": resource_package["cleanup_semantics"],
    }
    if include_details:
        payload.update(
            {
                "data_structures": data_structures,
                "data_stores": data_stores,
                "webhooks": webhooks,
                "connections": resource_package["connections"],
                "runtime_values": resource_package["runtime_values"],
                "upload_plan": resource_package["upload_plan"],
                "live_canary_contract": resource_package[
                    "live_canary_contract"
                ],
            }
        )
    return payload


def _project_package_blueprint_summary_section(
    package_payload: Mapping[str, object],
) -> JsonObject:
    package_summary = cast(
        "Mapping[str, object]", package_payload["package_summary"]
    )
    blueprint_artifact = cast(
        "Mapping[str, object]", package_payload["blueprint_artifact"]
    )
    return {
        "section": "blueprint_summary",
        "status": blueprint_artifact["status"],
        "artifact_format": blueprint_artifact["artifact_format"],
        "raw_artifact_available": blueprint_artifact["raw_artifact_available"],
        "raw_artifact_returned": False,
        "response_includes_raw_json": False,
        "module_count": package_summary["module_count"],
        "route_count": package_summary["route_count"],
        "deduped_link_count": package_summary["deduped_link_count"],
        "datastore_resource_count": package_summary["datastore_resource_count"],
        "connection_requirement_count": package_summary[
            "connection_requirement_count"
        ],
        "runtime_resource_requirement_count": package_summary[
            "runtime_resource_requirement_count"
        ],
        "zero_trace_status": blueprint_artifact["zero_trace_status"],
        "zero_trace_surface": "package_blueprint_artifact",
    }


def _project_package_parity_plan_section(
    *, package_payload: Mapping[str, object], include_details: bool
) -> JsonObject:
    live_apply_plan = cast(
        "Mapping[str, object]", package_payload["live_apply_plan"]
    )
    mutation_contract = cast(
        "Mapping[str, object]", live_apply_plan["scenario_mutation_contract"]
    )
    operation_budget = cast(
        "Mapping[str, object]", live_apply_plan["operation_budget"]
    )
    payload: JsonObject = {
        "section": "parity_plan",
        "parity_evidence_status": package_payload["parity_evidence_status"],
        "browser_validation_status": package_payload[
            "browser_validation_status"
        ],
        "make_mcp_live_requirements_status": package_payload[
            "make_mcp_live_requirements_status"
        ],
        "required_live_capability": live_apply_plan["required_live_capability"],
        "required_live_tool_status": live_apply_plan[
            "required_live_tool_status"
        ],
        "contract_status": live_apply_plan["contract_status"],
        "target_scenario_policy": live_apply_plan["target_scenario_policy"],
        "resource_creation_order": live_apply_plan["resource_creation_order"],
        "resource_creation_order_human": live_apply_plan[
            "resource_creation_order_human"
        ],
        "scenario_activation_allowed": operation_budget["activation_allowed"],
        "run_once_allowed": mutation_contract["run_once_allowed"],
        "cleanup_semantics": live_apply_plan["cleanup_semantics"],
    }
    if include_details:
        payload.update(
            {
                "live_apply_plan": live_apply_plan,
                "browser_validation_boundary": package_payload[
                    "browser_validation_boundary"
                ],
                "make_mcp_live_requirements_summary": package_payload[
                    "make_mcp_live_requirements_summary"
                ],
            }
        )
    return payload


def _project_package_customer_files_section(
    *, customer_package: Mapping[str, object], include_details: bool
) -> JsonObject:
    files = cast("tuple[JsonObject, ...]", customer_package["files"])
    payload: JsonObject = {
        "section": "customer_files",
        "package_kind": customer_package["package_kind"],
        "delivery_boundary": customer_package["delivery_boundary"],
        "customer_artifact_name": customer_package["customer_artifact_name"],
        "customer_receives_internal_report": customer_package[
            "customer_receives_internal_report"
        ],
        "customer_receives_ast": customer_package["customer_receives_ast"],
        "customer_receives_graph": customer_package["customer_receives_graph"],
        "customer_receives_linter_logic": customer_package[
            "customer_receives_linter_logic"
        ],
        "customer_receives_internal_prompts": customer_package[
            "customer_receives_internal_prompts"
        ],
        "customer_receives_scoring_logic": customer_package[
            "customer_receives_scoring_logic"
        ],
        "internal_artifacts_exported": customer_package[
            "internal_artifacts_exported"
        ],
        "included_customer_artifacts": customer_package[
            "included_customer_artifacts"
        ],
        "excluded_internal_artifacts": customer_package[
            "excluded_internal_artifacts"
        ],
        "file_count": len(files),
        "files": files,
    }
    if include_details:
        payload.update(
            {
                "import_setup_guidance": customer_package[
                    "import_setup_guidance"
                ],
                "non_technical_changelog": customer_package[
                    "non_technical_changelog"
                ],
            }
        )
    return payload


def _project_package_zero_trace_section(
    package_payload: Mapping[str, object],
) -> JsonObject:
    return {
        "section": "zero_trace",
        "zero_trace": package_payload["zero_trace"],
        "zero_trace_status": package_payload["zero_trace_status"],
        "zero_trace_surface": package_payload["zero_trace_surface"],
        "leak_count": package_payload["leak_count"],
        "redaction_status": package_payload["redaction_status"],
        "note_redaction_status": package_payload["note_redaction_status"],
        "package_contains_secrets": package_payload["package_contains_secrets"],
        "package_contains_fake_provider_ids": package_payload[
            "package_contains_fake_provider_ids"
        ],
        "customer_report_included": package_payload["customer_report_included"],
        "internal_report_status": package_payload["internal_report_status"],
    }


def project_verify(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Run a deterministic local verification profile for one project.

    Returns:
        The computed value.
    """
    context = _scenario_context_or_error(
        arguments,
        repo_root,
        tool_name="project.verify",
    )
    if isinstance(context, dict):
        return context
    project_id, scenario_path, scenario = context
    profile = (
        _optional_text(arguments.get("profile")) or "import_test"
    ).casefold()
    if profile not in PROJECT_VERIFY_PROFILES:
        return _unsupported_project_verify_profile_payload(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
            requested_profile=profile,
        )
    output_mode = _project_output_mode(
        arguments.get("output_mode"), default="compact"
    )
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    verification = _verification_context(scenario=scenario, profile=profile)
    statuses = cast("ValidationSurfaceStatuses", verification["statuses"])
    blocking_findings = cast(
        "tuple[JsonObject, ...]", verification["blocking_findings"]
    )
    local_linter_findings = cast(
        "tuple[JsonObject, ...]", verification["local_linter_findings"]
    )
    full_payload: JsonObject = {
        "status": "ok" if not blocking_findings else "blocked",
        "project_id": project_id,
        "profile": profile,
        "output_mode": output_mode,
        "source_of_truth": "local_project_scenario",
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "summary": summary,
        "findings": blocking_findings,
        "finding_count": len(blocking_findings),
        "local_linter_status": verification["local_linter_status"],
        "local_linter_findings": local_linter_findings,
        "local_linter_finding_count": len(local_linter_findings),
        **runtime_setup_count_payload(runtime_counts),
        "runtime_setup_groups": _runtime_setup_groups(
            scenario,
            limit=PROJECT_VIEW_DEFAULT_LIMIT,
            include_paths=output_mode in {"full", "debug"},
        ),
        "grouped_findings": verification["grouped_findings"],
        "zero_trace": verification["zero_trace"],
        "zero_trace_status": verification["zero_trace_status"],
        "zero_trace_reason": verification["zero_trace_reason"],
        "zero_trace_surface": verification["zero_trace_surface"],
        "leak_count": verification["leak_count"],
        "scenario_behavior_status": verification["scenario_behavior_status"],
        "scenario_embedded_checks_status": verification[
            "scenario_embedded_checks_status"
        ],
        "local_lineage_invariants_status": verification[
            "local_lineage_invariants_status"
        ],
        "live_make_runtime_status": verification["live_make_runtime_status"],
        "error_handler_count": verification["error_handler_count"],
        "package_status": verification["package_status"],
        "minimal_import_package_status": verification[
            "minimal_import_package_status"
        ],
        "full_live_validation_status": verification[
            "full_live_validation_status"
        ],
        "make_mcp_live_requirements_status": verification[
            "make_mcp_live_requirements_status"
        ],
        "make_mcp_live_requirements_summary": verification[
            "make_mcp_live_requirements_summary"
        ],
        "datastore_manifest_status": verification["datastore_manifest_status"],
        "connection_mapping_status": verification["connection_mapping_status"],
        "resource_mapping_status": verification["resource_mapping_status"],
        "live_preflight_status": verification["live_preflight_status"],
        "live_canary_status": verification["live_canary_status"],
        "live_resource_creation_order": verification[
            "live_resource_creation_order"
        ],
        "live_resource_creation_order_human": verification[
            "live_resource_creation_order_human"
        ],
        "live_canary_cleanup_semantics": verification[
            "live_canary_cleanup_semantics"
        ],
        "make_mcp_capabilities": verification["make_mcp_capabilities"],
        "make_mcp_capability_details": verification[
            "make_mcp_capability_details"
        ],
        "live_apply_plan": verification["live_apply_plan"],
        "browser_validation_status": verification["browser_validation_status"],
        "browser_validation_boundary": verification[
            "browser_validation_boundary"
        ],
        "datastore_manifest": verification["datastore_manifest"],
        "client_handoff_status": verification["client_handoff_status"],
        "handoff_risk_summary": verification["handoff_risk_summary"],
        "next_queries": _verify_next_queries(
            project_id=project_id, profile=profile
        ),
        **_project_verify_permission_boundary(profile=profile),
        **_project_verify_validation_surface_payload(
            statuses=statuses,
            verification=verification,
        ),
        **_local_offline_safety_flags(),
    }
    if output_mode == "micro":
        return _project_verify_micro_payload(
            project_id=project_id,
            profile=profile,
            summary=summary,
            verification=verification,
            blocking_findings=blocking_findings,
            local_linter_findings=local_linter_findings,
            runtime_counts=runtime_counts,
            statuses=statuses,
        )
    if output_mode not in {"full", "debug"}:
        return _project_verify_compact_payload(
            repo_root=repo_root,
            project_id=project_id,
            profile=profile,
            scenario_path=scenario_path,
            summary=summary,
            verification=verification,
            blocking_findings=blocking_findings,
            local_linter_findings=local_linter_findings,
            runtime_counts=runtime_counts,
            statuses=statuses,
            output_mode=output_mode,
        )
    return full_payload


def inspect_project_capabilities(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Inspect Make.com MCP capability details outside compact project.verify payloads.

    Returns:
        The computed value.
    """
    project_id = _optional_text(arguments.get("project_id"))
    profile = _project_verify_profile(arguments.get("profile"))
    output_mode = _project_output_mode(
        arguments.get("output_mode"), default="compact"
    )
    requested_capability = _optional_text(
        arguments.get("capability")
    ) or _optional_text(arguments.get("capability_id"))
    if project_id:
        context = _scenario_context_or_error(
            arguments,
            repo_root,
            tool_name="project.capabilities.inspect",
        )
        if isinstance(context, dict):
            return context
    requirements = _make_mcp_live_requirements_summary()
    details = _make_mcp_capability_details()
    unavailable = tuple(
        row
        for row in details
        if _is_unavailable_capability_status(str(row["status"]))
    )
    payload: JsonObject = {
        "status": "ok",
        "project_id": project_id,
        "profile": profile,
        "output_mode": output_mode,
        "source_of_truth": "local_make_mcp_capability_contract",
        "make_mcp_live_requirements_summary": requirements,
        "capability_count": len(details),
        "unavailable_capability_count": len(unavailable),
        "missing_capabilities": tuple(
            str(row["capability"]) for row in unavailable
        ),
        "raw_capability_matrix_available": True,
        "provider_api_call": False,
        "live_make_called": False,
        **_local_offline_safety_flags(),
    }
    if requested_capability is not None:
        detail = _make_mcp_capability_detail_for(requested_capability)
        unavailable_requested = _is_unavailable_capability_status(
            str(detail["status"])
        )
        payload.update(
            {
                "capability": detail["capability"],
                "capability_status": detail["status"],
                "capability_detail": detail,
                "returned_capability_count": 1,
                "requested_capability_available": not unavailable_requested,
                "missing_capabilities": (
                    (str(detail["capability"]),)
                    if unavailable_requested
                    else ()
                ),
            }
        )
        if output_mode in {"full", "debug"}:
            payload["make_mcp_capabilities"] = {
                str(detail["capability"]): detail
            }
            payload["make_mcp_capability_details"] = (detail,)
        return payload
    if output_mode in {"full", "debug"}:
        payload.update(
            {
                "make_mcp_capabilities": _make_mcp_capability_matrix(),
                "make_mcp_capability_details": details,
                "live_apply_plan": _live_apply_plan(),
                "browser_validation_boundary": _browser_validation_boundary(
                    include_plan=False
                ),
            }
        )
    else:
        payload["top_missing_capability_details"] = unavailable[
            :PROJECT_VERIFY_TOP_BLOCKER_LIMIT
        ]
        payload["hidden_missing_capability_detail_count"] = max(
            len(unavailable) - PROJECT_VERIFY_TOP_BLOCKER_LIMIT,
            0,
        )
        payload["next_queries"] = (
            _next_query(
                tool="project.capabilities.inspect",
                arguments={
                    "project_id": project_id or "<id>",
                    "profile": profile,
                    "output_mode": "full",
                },
                reason="Inspect the full local Make.com MCP capability matrix.",
            ),
        )
    return payload


def _project_verify_micro_payload(
    *,
    project_id: str,
    profile: str,
    summary: Mapping[str, object],
    verification: Mapping[str, object],
    blocking_findings: tuple[JsonObject, ...],
    local_linter_findings: tuple[JsonObject, ...],
    runtime_counts: RuntimeSetupSurfaceCounts,
    statuses: ValidationSurfaceStatuses,
) -> JsonObject:
    return {
        "status": "ok" if not blocking_findings else "blocked",
        "project_id": project_id,
        "profile": profile,
        "output_mode": "micro",
        "summary_counts": _project_verify_summary_counts(
            summary=summary,
            runtime_counts=runtime_counts,
        ),
        "finding_count": len(blocking_findings),
        "top_blockers": blocking_findings[:PROJECT_VERIFY_TOP_BLOCKER_LIMIT],
        "local_linter_status": verification["local_linter_status"],
        "local_linter_finding_count": len(local_linter_findings),
        "zero_trace": verification["zero_trace"],
        "zero_trace_status": verification["zero_trace_status"],
        "zero_trace_reason": verification["zero_trace_reason"],
        "zero_trace_surface": verification["zero_trace_surface"],
        "leak_count": verification["leak_count"],
        "package_status": verification["package_status"],
        "minimal_import_package_status": verification[
            "minimal_import_package_status"
        ],
        "full_live_validation_status": verification[
            "full_live_validation_status"
        ],
        "make_mcp_live_requirements_summary": verification[
            "make_mcp_live_requirements_summary"
        ],
        "next_queries": (
            _next_query(
                tool="project.capabilities.inspect",
                arguments={
                    "project_id": project_id,
                    "profile": profile,
                    "output_mode": "full",
                },
                reason="Inspect detailed Make.com MCP capability maps.",
            ),
        ),
        **_project_verify_validation_surface_payload(
            statuses=statuses,
            verification=verification,
        ),
        **_project_verify_permission_boundary(profile=profile),
        **_local_offline_safety_flags(),
    }


def _project_verify_compact_payload(
    *,
    repo_root: Path,
    project_id: str,
    profile: str,
    scenario_path: Path,
    summary: Mapping[str, object],
    verification: Mapping[str, object],
    blocking_findings: tuple[JsonObject, ...],
    local_linter_findings: tuple[JsonObject, ...],
    runtime_counts: RuntimeSetupSurfaceCounts,
    statuses: ValidationSurfaceStatuses,
    output_mode: str,
) -> JsonObject:
    return {
        "status": "ok" if not blocking_findings else "blocked",
        "project_id": project_id,
        "profile": profile,
        "output_mode": output_mode,
        "source_of_truth": "local_project_scenario",
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "summary": dict(summary),
        "summary_counts": _project_verify_summary_counts(
            summary=summary,
            runtime_counts=runtime_counts,
        ),
        "findings": blocking_findings[:PROJECT_VERIFY_TOP_BLOCKER_LIMIT],
        "finding_count": len(blocking_findings),
        "hidden_finding_count": max(
            len(blocking_findings) - PROJECT_VERIFY_TOP_BLOCKER_LIMIT,
            0,
        ),
        "grouped_findings": cast(
            "tuple[JsonObject, ...]", verification["grouped_findings"]
        )[:PROJECT_VERIFY_TOP_BLOCKER_LIMIT],
        "local_linter_status": verification["local_linter_status"],
        "local_linter_finding_count": len(local_linter_findings),
        "zero_trace": verification["zero_trace"],
        "zero_trace_status": verification["zero_trace_status"],
        "zero_trace_reason": verification["zero_trace_reason"],
        "zero_trace_surface": verification["zero_trace_surface"],
        "leak_count": verification["leak_count"],
        "package_status": verification["package_status"],
        "minimal_import_package_status": verification[
            "minimal_import_package_status"
        ],
        "full_live_validation_status": verification[
            "full_live_validation_status"
        ],
        "make_mcp_live_requirements_status": verification[
            "make_mcp_live_requirements_status"
        ],
        "make_mcp_live_requirements_summary": verification[
            "make_mcp_live_requirements_summary"
        ],
        "datastore_manifest_status": verification["datastore_manifest_status"],
        "connection_mapping_status": verification["connection_mapping_status"],
        "resource_mapping_status": verification["resource_mapping_status"],
        "live_preflight_status": verification["live_preflight_status"],
        "live_canary_status": verification["live_canary_status"],
        "live_resource_creation_order": verification[
            "live_resource_creation_order"
        ],
        "live_resource_creation_order_human": verification[
            "live_resource_creation_order_human"
        ],
        "live_canary_cleanup_semantics": verification[
            "live_canary_cleanup_semantics"
        ],
        "live_make_runtime_status": verification["live_make_runtime_status"],
        "browser_validation_status": verification["browser_validation_status"],
        "browser_validation_boundary": verification[
            "browser_validation_boundary"
        ],
        "client_handoff_status": verification["client_handoff_status"],
        "handoff_risk_summary": verification["handoff_risk_summary"],
        "next_queries": (
            *_verify_next_queries(project_id=project_id, profile=profile),
            _next_query(
                tool="project.capabilities.inspect",
                arguments={
                    "project_id": project_id,
                    "profile": profile,
                    "output_mode": "full",
                },
                reason="Inspect detailed Make.com MCP capability maps.",
            ),
        ),
        **runtime_setup_count_payload(runtime_counts),
        **_project_verify_validation_surface_payload(
            statuses=statuses,
            verification=verification,
        ),
        **_project_verify_permission_boundary(profile=profile),
        **_local_offline_safety_flags(),
    }


def _project_verify_summary_counts(
    *,
    summary: Mapping[str, object],
    runtime_counts: RuntimeSetupSurfaceCounts,
) -> JsonObject:
    return {
        "module_count": summary["module_count"],
        "route_count": summary["route_count"],
        "link_count": summary["link_count"],
        "error_handler_count": summary["error_handler_count"],
        "runtime_setup_occurrence_count": runtime_counts.occurrence_count,
        "runtime_setup_item_count": runtime_counts.item_count,
    }


def _project_verify_validation_surface_payload(
    *,
    statuses: ValidationSurfaceStatuses,
    verification: Mapping[str, object],
) -> JsonObject:
    payload = validation_surface_payload(statuses=statuses)
    if verification.get("zero_trace_status") != "failed":
        return payload
    invalid_surfaces = [
        str(surface)
        for surface in cast("Sequence[object]", payload["invalid_surfaces"])
    ]
    if "zero_trace" not in invalid_surfaces:
        invalid_surfaces.append("zero_trace")
    unblocked_surfaces = [
        str(surface)
        for surface in cast("Sequence[object]", payload["unblocked_surfaces"])
        if str(surface) != "zero_trace"
    ]
    surface_payload = blocked_surface_payload(
        blocked_surfaces=invalid_surfaces,
        unblocked_surfaces=unblocked_surfaces,
        status_reason=(
            "Rendered artifact failed zero-trace; customer-facing readiness is blocked."
        ),
    )
    payload.update(
        {
            "invalid_surface": invalid_surfaces[0]
            if invalid_surfaces
            else None,
            "invalid_surfaces": invalid_surfaces,
            **surface_payload,
        }
    )
    return payload


def _unsupported_project_verify_profile_payload(
    *,
    repo_root: Path,
    project_id: str,
    scenario_path: Path,
    requested_profile: str,
) -> JsonObject:
    recommended_queries = (
        _next_query(
            tool="project.verify",
            arguments={"project_id": project_id, "profile": "import_test"},
            reason="Run the local import projection safety profile.",
        ),
        _next_query(
            tool="project.view",
            arguments={"project_id": project_id, "surface": "readiness"},
            reason="Inspect local readiness surfaces before choosing a profile.",
        ),
        _next_query(
            tool="project.make",
            arguments={
                "project_id": project_id,
                "action": "preview",
                "profile": "import_test",
            },
            reason="Preview the local Make artifact without live import.",
        ),
    )
    return {
        "status": "invalid_profile",
        "error_code": "unsupported_project_verify_profile",
        "project_id": project_id,
        "requested_profile": requested_profile,
        "valid_profile_names": tuple(sorted(PROJECT_VERIFY_PROFILES)),
        "recommended_tools": recommended_queries,
        "next_queries": recommended_queries,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        **_project_verify_permission_boundary(profile="unsupported"),
        **_local_offline_safety_flags(),
    }


def _project_verify_permission_boundary(*, profile: str) -> JsonObject:
    local_projection = profile == "import_test"
    live_preflight = profile == "live_preflight"
    verification_scope = (
        "local_import_projection"
        if local_projection
        else "live_import_preflight"
        if live_preflight
        else "local_project_verification"
    )
    return {
        "permission_boundary": {
            "profile": profile,
            "verification_execution_scope": verification_scope,
            "local_import_projection": local_projection,
            "live_make_import": False,
            "live_make_import_called": False,
            "live_make_import_requires_operator_approval": True,
            "provider_api_call": False,
            "recommended_live_import_preflight": {
                "tool": "project.make",
                "arguments": {
                    "project_id": "<id>",
                    "action": "package",
                    "profile": "live_preflight",
                    "dry_run": True,
                },
            },
        },
        "verification_execution_scope": verification_scope,
        "local_import_projection": local_projection,
        "local_import_projection_only": local_projection,
        "live_make_import_called": False,
        "live_make_import_status": "not_executed_operator_gated",
        "live_import_requires_operator_approval": True,
    }


def project_next(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Return the next local IDE action or a compact execution plan."""
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    mode = _project_next_mode(arguments.get("mode"))
    profile = _project_verify_profile(arguments.get("profile"))
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    verification = _verification_context(scenario=scenario, profile=profile)
    actions = _state_aware_next_actions(
        summary=summary,
        verification=verification,
        runtime_counts=runtime_counts,
        project_id=project_id,
        profile=profile,
        mode=mode,
    )
    return {
        "status": "ok",
        "project_id": project_id,
        "mode": mode,
        "profile": profile,
        "source_of_truth": "local_project_scenario",
        "next_action": actions[0] if actions else None,
        "plan": actions,
        "next_queries": actions,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        **_local_offline_safety_flags(),
    }


def _verify_next_queries(
    *, project_id: str, profile: str
) -> tuple[JsonObject, ...]:
    if profile == "live_preflight":
        return (
            _next_query(
                tool="project.make",
                arguments={
                    "project_id": project_id,
                    "action": "package",
                    "profile": "live_preflight",
                    "dry_run": True,
                },
                reason="Prepare the local Make import package for gated Make.com MCP apply.",
            ),
        )
    if profile == "handoff_test":
        return (
            _next_query(
                tool="project.view",
                arguments={"project_id": project_id, "surface": "notes"},
                reason="Inspect missing handoff notes.",
            ),
        )
    return (
        _next_query(
            tool="project.make",
            arguments={
                "project_id": project_id,
                "action": "preview",
                "profile": profile,
            },
            reason="Preview the local Make-native artifact for this verification profile.",
        ),
    )


def view_project_modules(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Compatibility wrapper over project.view surface=modules.

    Returns:
        The computed value.
    """
    dispatch = _wrapper_view_arguments(arguments=arguments, surface="modules")
    result = view_project(dispatch, repo_root)
    result["domain_surface"] = "modules"
    result["canonical_tool"] = "project.view"
    result["wrapped_tool"] = "project.modules.view"
    return result


def add_project_module(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or add one module node to a local scenario draft.

    Returns:
        The computed value.
    """
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    updated = deepcopy(scenario)
    module = _json_object_argument(arguments, "module_json")
    target_id = _node_id(module)
    if target_id is None:
        _raise_value_error("module_json must include id.")
    _require_unique_node_id(updated, target_id)
    flow = _target_flow(updated, arguments)
    position = _insert_position(arguments.get("position"), len(flow))
    flow.insert(position, module)
    target = _module_summary(f"{_flow_path(arguments)}[{position}]", module)
    return _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="modules",
        operation="add",
        target=target,
    )


def modify_project_module(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or merge-patch one local module node.

    Returns:
        The computed value.
    """
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    node_id = _required_node_id(arguments, "module_id")
    patch = _json_object_argument(
        arguments, "patch_json", fallback_name="merge_patch_json"
    )
    updated = deepcopy(scenario)
    path, module = _required_module(updated, node_id)
    _merge_patch(module, patch)
    return _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="modules",
        operation="modify",
        target=_module_summary(path, module),
    )


def delete_project_module(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Preview one local module node deletion without writing.

    Returns:
        The computed value.
    """
    return _delete_project_module(
        arguments=arguments, repo_root=repo_root, allow_write=False
    )


def _delete_project_module(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
    allow_write: bool,
) -> JsonObject:
    """Dry-run or delete one local module node after confirmation.

    Returns:
        The computed value.
    """
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    node_id = _required_node_id(arguments, "module_id")
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    if not dry_run and not allow_write:
        _raise_value_error(
            "Direct project.modules.delete is preview-only; use project.edit to write."
        )
    confirm_module_id = _optional_text(arguments.get("confirm_module_id"))
    if confirm_module_id is not None and confirm_module_id != node_id:
        _raise_value_error(
            "Module deletion confirm_module_id must match module_id."
        )
    if (
        not dry_run
        and not _bool_argument(arguments.get("confirm"), default=False)
        and (confirm_module_id != node_id)
    ):
        _raise_value_error(
            "Module deletion requires confirm=true or confirm_module_id."
        )
    updated = deepcopy(scenario)
    removed = _remove_module(updated, node_id)
    return _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="modules",
        operation="delete",
        target=removed,
    )


def view_project_links(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Compatibility wrapper over project.view surface=links.

    Returns:
        The computed value.
    """
    dispatch = _wrapper_view_arguments(arguments=arguments, surface="links")
    result = view_project(dispatch, repo_root)
    result["domain_surface"] = "links"
    result["canonical_tool"] = "project.view"
    result["wrapped_tool"] = "project.links.view"
    return result


def view_project_filters(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Compatibility wrapper over project.view surface=filters.

    Returns:
        The computed value.
    """
    route_id = _optional_text(arguments.get("route_id"))
    dispatch = _wrapper_view_arguments(arguments=arguments, surface="filters")
    if route_id is not None:
        route_index = _route_index_from_route_id(route_id)
        if route_index is None:
            return {
                "status": "invalid_filter",
                "project_id": _required_project_id(arguments),
                "domain_surface": "filters",
                "canonical_tool": "project.view",
                "wrapped_tool": "project.filters.view",
                "focus": {"route_id": route_id},
                "message": "route_id must be an integer route index or route:<index>.",
                **_local_offline_safety_flags(),
            }
        dispatch["route_index"] = route_index
    result = view_project(dispatch, repo_root)
    result["domain_surface"] = "filters"
    result["canonical_tool"] = "project.view"
    result["wrapped_tool"] = "project.filters.view"
    return result


def add_project_filter(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or add one route filter.

    Returns:
        The computed value.
    """
    return _filter_write(
        arguments=arguments, repo_root=repo_root, operation="add"
    )


def modify_project_filter(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or merge-patch one route filter.

    Returns:
        The computed value.
    """
    return _filter_write(
        arguments=arguments, repo_root=repo_root, operation="modify"
    )


def delete_project_filter(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Preview one route filter deletion without writing.

    Returns:
        The computed value.
    """
    return _delete_project_filter(
        arguments=arguments, repo_root=repo_root, allow_write=False
    )


def _delete_project_filter(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
    allow_write: bool,
) -> JsonObject:
    """Dry-run or delete one route filter after confirmation.

    Returns:
        The computed value.
    """
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    if not dry_run and not allow_write:
        _raise_value_error(
            "Direct project.filters.delete is preview-only; use project.edit to write."
        )
    confirm = _optional_text(arguments.get("confirm_node_id"))
    node_id = _filter_target_node_id(arguments, payload={}, operation="delete")
    if confirm is not None and confirm != node_id:
        _raise_value_error(
            "Filter deletion confirm_node_id must match node_id."
        )
    if not dry_run and confirm != node_id:
        _raise_value_error(
            "Filter deletion requires confirm_node_id to match node_id."
        )
    return _filter_write(
        arguments=arguments, repo_root=repo_root, operation="delete"
    )


def view_project_error_handlers(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Compatibility wrapper over project.view surface=error_handlers.

    Returns:
        The computed value.
    """
    dispatch = _wrapper_view_arguments(
        arguments=arguments, surface="error_handlers"
    )
    result = view_project(dispatch, repo_root)
    result["domain_surface"] = "error_handlers"
    result["canonical_tool"] = "project.view"
    result["wrapped_tool"] = "project.error_handlers.view"
    return result


def add_project_error_handler(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or add one local module error handler.

    Returns:
        The computed value.
    """
    return _error_handler_write(
        arguments=arguments, repo_root=repo_root, operation="add"
    )


def modify_project_error_handler(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Dry-run or merge-patch one local module error handler.

    Returns:
        The computed value.
    """
    return _error_handler_write(
        arguments=arguments, repo_root=repo_root, operation="modify"
    )


def delete_project_error_handler(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Preview one local module error-handler deletion without writing.

    Returns:
        The computed value.
    """
    return _delete_project_error_handler(
        arguments=arguments, repo_root=repo_root, allow_write=False
    )


def _delete_project_error_handler(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
    allow_write: bool,
) -> JsonObject:
    """Dry-run or delete one local module error handler after confirmation.

    Returns:
        The computed value.
    """
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    if not dry_run and not allow_write:
        _raise_value_error(
            "Direct project.error_handlers.delete is preview-only; use project.edit to write."
        )
    parent_node_id = _error_handler_parent_node_id(
        arguments,
        payload={},
        operation="delete",
    )
    confirm_node_id = _optional_text(arguments.get("confirm_node_id"))
    if confirm_node_id is not None and confirm_node_id != parent_node_id:
        _raise_value_error(
            "Error-handler deletion confirm_node_id must match parent_node_id."
        )
    if not dry_run and confirm_node_id != parent_node_id:
        _raise_value_error(
            "Error-handler deletion requires confirm_node_id to match parent_node_id."
        )
    return _error_handler_write(
        arguments=arguments, repo_root=repo_root, operation="delete"
    )


def _error_handler_write(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
    operation: str,
) -> JsonObject:
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    payload = _error_handler_operation_payload(arguments, operation=operation)
    parent_node_id = _error_handler_parent_node_id(
        arguments,
        payload=payload,
        operation=operation,
    )
    index = _error_handler_index(arguments, payload=payload)
    updated = deepcopy(scenario)
    path, module = _required_parent_module(
        updated,
        parent_node_id=parent_node_id,
        operation=operation,
    )
    handlers = _handlers_for_module(module)
    if operation == "add":
        handlers.append(_error_handler_body(payload, operation=operation))
        target: JsonObject = {
            "parent_node_id": parent_node_id,
            "node_id": parent_node_id,
            "handler_index": len(handlers) - 1,
            "path": path,
        }
    elif operation == "modify":
        if index >= len(handlers):
            _raise_value_error(
                f"handler_index {index} is out of range for parent_node_id {parent_node_id}. {ERROR_HANDLER_TARGET_EXAMPLE}"
            )
        _merge_patch(
            handlers[index], _error_handler_body(payload, operation=operation)
        )
        target = {
            "parent_node_id": parent_node_id,
            "node_id": parent_node_id,
            "handler_index": index,
            "path": path,
        }
    elif operation == "delete":
        if index >= len(handlers):
            _raise_value_error(
                f"handler_index {index} is out of range for parent_node_id {parent_node_id}. {ERROR_HANDLER_TARGET_EXAMPLE}"
            )
        removed = handlers.pop(index)
        target = {
            "parent_node_id": parent_node_id,
            "node_id": parent_node_id,
            "handler_index": index,
            "path": path,
            "removed": removed,
        }
    else:
        _raise_value_error(f"Unsupported error-handler operation: {operation}")
    module["onerror"] = handlers
    return _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="error_handlers",
        operation=operation,
        target=target,
    )


def _error_handler_operation_payload(
    arguments: Mapping[str, object],
    *,
    operation: str,
) -> JsonObject:
    if operation == "add":
        return _json_object_argument(arguments, "handler_json")
    if operation == "modify":
        return _json_object_argument(
            arguments, "patch_json", fallback_name="merge_patch_json"
        )
    return {}


def _error_handler_parent_node_id(
    arguments: Mapping[str, object],
    *,
    payload: Mapping[str, object],
    operation: str,
) -> str:
    parent_node_id = _optional_node_id(
        arguments.get("parent_node_id")
        or arguments.get("node_id")
        or arguments.get("target_node_id")
        or payload.get("parent_node_id")
        or payload.get("node_id")
        or payload.get("target_node_id")
    )
    if parent_node_id is None:
        payload_name = "handler_json" if operation == "add" else "patch_json"
        if operation == "delete":
            _raise_value_error(
                f"missing_parent_node_id: project.error_handlers.delete requires top-level parent_node_id or node_id. {ERROR_HANDLER_TARGET_EXAMPLE}"
            )
        _raise_value_error(
            f"missing_parent_node_id: project.error_handlers.{operation} requires top-level parent_node_id, top-level node_id, or {payload_name}.parent_node_id. {ERROR_HANDLER_TARGET_EXAMPLE}"
        )
    return parent_node_id


def _error_handler_index(
    arguments: Mapping[str, object],
    *,
    payload: Mapping[str, object],
) -> int:
    return _nonnegative_int(
        arguments.get("handler_index", payload.get("handler_index")),
        default=0,
        upper=10_000,
    )


def _required_parent_module(
    scenario: JsonObject,
    *,
    parent_node_id: str,
    operation: str,
) -> tuple[str, JsonObject]:
    try:
        return _required_module(scenario, parent_node_id)
    except ValueError:
        _raise_value_error(
            f"unknown_parent_node: project.error_handlers.{operation} parent_node_id {parent_node_id} was not found. {ERROR_HANDLER_TARGET_EXAMPLE}"
        )


def _error_handler_body(
    payload: Mapping[str, object], *, operation: str
) -> JsonObject:
    nested_key = "handler" if operation == "add" else "patch"
    nested = payload.get(nested_key)
    if isinstance(nested, dict):
        return cast(
            "JsonObject", _json_copy(cast("Mapping[str, object]", nested))
        )
    body = {
        str(key): value
        for key, value in payload.items()
        if str(key) not in ERROR_HANDLER_TARGET_KEYS
    }
    if not body:
        _raise_value_error(
            f"project.error_handlers.{operation} payload must include error-handler fields or a {nested_key} object. {ERROR_HANDLER_TARGET_EXAMPLE}"
        )
    return cast("JsonObject", _json_copy(body))


def _filter_write(
    *, arguments: Mapping[str, object], repo_root: Path, operation: str
) -> JsonObject:
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    payload = _filter_operation_payload(arguments, operation=operation)
    node_id = _filter_target_node_id(
        arguments, payload=payload, operation=operation
    )
    route_index = _filter_route_index(arguments, payload=payload)
    updated = deepcopy(scenario)
    _path, module = _required_module(updated, node_id)
    routes = _routes_for_module(module)
    if not routes:
        _raise_value_error(
            f"node_has_no_routes: project.filters.{operation} node_id {node_id} has no route index. {_filter_error_context(arguments=arguments, payload=payload)}"
        )
    if route_index >= len(routes):
        _raise_value_error(
            f"route_index_out_of_range: project.filters.{operation} route_index {route_index} is out of range for node_id {node_id}; route_count={len(routes)}. {_filter_error_context(arguments=arguments, payload=payload)}"
        )
    route = routes[route_index]
    if operation == "add":
        route["filter"] = _filter_body(payload, operation=operation)
    elif operation == "modify":
        current = _mapping_member(route, "filter")
        patch = _filter_body(payload, operation=operation)
        _merge_patch(current, patch)
        route["filter"] = current
    elif operation == "delete":
        _ = route.pop("filter", None)
    else:
        _raise_value_error(f"Unsupported filter operation: {operation}")
    target = _filter_summary(
        module=module, route_index=route_index, route=route
    )
    response = _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="filters",
        operation=operation,
        target=target,
    )
    response["accepted_payload_shape"] = _filter_payload_contract(
        operation=operation
    )
    return response


def _filter_operation_payload(
    arguments: Mapping[str, object],
    *,
    operation: str,
) -> JsonObject:
    if operation == "add":
        return _json_object_argument(arguments, "filter_json")
    if operation == "modify":
        return _json_object_argument(
            arguments, "patch_json", fallback_name="merge_patch_json"
        )
    return {}


def _filter_target_node_id(
    arguments: Mapping[str, object],
    *,
    payload: Mapping[str, object],
    operation: str,
) -> str:
    node_id = _optional_node_id(
        arguments.get("node_id")
        or arguments.get("target_node_id")
        or payload.get("node_id")
        or payload.get("target_node_id")
    )
    if node_id is None:
        payload_name = "filter_json" if operation == "add" else "patch_json"
        _raise_value_error(
            f"missing_node_id: project.filters.{operation} requires top-level node_id or {payload_name}.node_id. {_filter_error_context(arguments=arguments, payload=payload)}"
        )
    return node_id


def _filter_route_index(
    arguments: Mapping[str, object],
    *,
    payload: Mapping[str, object],
) -> int:
    return _nonnegative_int(
        arguments.get("route_index", payload.get("route_index")),
        default=0,
        upper=10_000,
    )


def _filter_body(
    payload: Mapping[str, object], *, operation: str
) -> JsonObject:
    nested_key = "filter" if operation == "add" else "patch"
    nested = payload.get(nested_key)
    if isinstance(nested, dict):
        return cast(
            "JsonObject", _json_copy(cast("Mapping[str, object]", nested))
        )
    body = {
        str(key): value
        for key, value in payload.items()
        if str(key) not in FILTER_TARGET_KEYS
    }
    if not body:
        _raise_value_error(
            f"missing_filter_body: project.filters.{operation} payload must include filter fields or a {nested_key} object. {_filter_body_error_context(body)}"
        )
    _validate_filter_body(body, operation=operation)
    return cast("JsonObject", _json_copy(body))


def _validate_filter_body(
    body: Mapping[str, object], *, operation: str
) -> None:
    if operation == "add" and not any(
        key in body for key in FILTER_CONDITION_KEYS
    ):
        _raise_value_error(
            f"malformed_filter_condition: project.filters.{operation} filter must include condition, conditions, or expression. {_filter_body_error_context(body)}"
        )
    condition = body.get("condition")
    if condition is not None and (
        not isinstance(condition, str) or not condition.strip()
    ):
        _raise_value_error(
            f"malformed_filter_condition: project.filters.{operation} condition must be a non-empty string. {_filter_body_error_context(body)}"
        )
    expression = body.get("expression")
    if expression is not None and (
        not isinstance(expression, str) or not expression.strip()
    ):
        _raise_value_error(
            f"malformed_filter_condition: project.filters.{operation} expression must be a non-empty string. {_filter_body_error_context(body)}"
        )
    conditions = body.get("conditions")
    if conditions is not None and not isinstance(
        conditions, list | tuple | dict
    ):
        _raise_value_error(
            f"malformed_filter_condition: project.filters.{operation} conditions must be an object or array. {_filter_body_error_context(body)}"
        )


def _filter_payload_contract(*, operation: str) -> JsonObject:
    payload_name = "filter_json" if operation == "add" else "patch_json"
    nested_key = "filter" if operation == "add" else "patch"
    return {
        "top_level_keys": (
            "project_id",
            "node_id",
            "route_index",
            payload_name,
            "dry_run",
        ),
        "payload_envelope_keys": (
            "node_id",
            "target_node_id",
            "route_index",
            nested_key,
        ),
        "filter_body_keys": FILTER_BODY_EXPECTED_KEYS,
        "minimal_example": FILTER_TARGET_EXAMPLE,
    }


def _filter_error_context(
    *,
    arguments: Mapping[str, object],
    payload: Mapping[str, object],
) -> str:
    received_keys = _filter_received_keys(arguments=arguments, payload=payload)
    return (
        f"received_keys={_format_key_tuple(received_keys)} "
        f"expected_keys={_format_key_tuple(FILTER_ARGUMENT_EXPECTED_KEYS)} "
        f"minimal_example={FILTER_TARGET_EXAMPLE}"
    )


def _filter_body_error_context(body: Mapping[str, object]) -> str:
    return (
        f"received_keys={_format_key_tuple(sorted(str(key) for key in body))} "
        f"expected_keys={_format_key_tuple(FILTER_BODY_EXPECTED_KEYS)} "
        f"minimal_example={FILTER_TARGET_EXAMPLE}"
    )


def _filter_received_keys(
    *,
    arguments: Mapping[str, object],
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    ignored = frozenset(("project_id", "dry_run", "output_mode"))
    keys = {str(key) for key in arguments if str(key) not in ignored}
    for key in payload:
        key_text = str(key)
        keys.add(f"filter_json.{key_text}")
        keys.add(f"patch_json.{key_text}")
    return tuple(sorted(keys))


def _format_key_tuple(keys: Iterable[str]) -> str:
    return "[" + ",".join(keys) + "]"


def _surface_payload(
    *,
    scenario: Mapping[str, object],
    surface: str,
    focus: JsonObject,
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    """Return a bounded payload for one project.view surface."""
    if surface == "overview":
        return _overview_surface_payload(
            scenario=scenario,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "graph":
        return _graph_surface_payload(
            scenario=scenario,
            focus=focus,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "modules":
        return _modules_surface_payload(
            scenario=scenario,
            focus=focus,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "links":
        return _links_surface_payload(
            scenario=scenario,
            focus=focus,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "filters":
        return _filters_surface_payload(
            scenario=scenario,
            focus=focus,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "error_handlers":
        return _error_handlers_surface_payload(
            scenario=scenario,
            focus=focus,
            output_mode=output_mode,
            limit=limit,
            project_id=project_id,
        )
    if surface == "runtime":
        runtime_counts = _runtime_setup_counts(scenario)
        return {
            "runtime": {
                **runtime_setup_count_payload(runtime_counts),
                "groups": _runtime_setup_groups(
                    scenario,
                    limit=limit,
                    include_paths=output_mode in {"full", "debug"},
                ),
                "surfaces": runtime_setup_surface_payload(
                    counts=runtime_counts,
                    render_status="not_evaluated",
                    render_reason="project.view does not render Make artifacts.",
                ),
            }
        }
    if surface == "datastores":
        return {
            "datastore_manifest": _datastore_manifest(
                scenario=scenario, output_mode=output_mode
            )
        }
    if surface == "notes":
        return _notes_surface_payload(
            scenario=scenario,
            project_id=project_id,
            output_mode=output_mode,
            limit=limit,
        )
    if surface == "make_blueprint":
        summary = _scenario_summary(scenario)
        runtime_counts = _runtime_setup_counts(scenario)
        projection = _make_artifact_projection(scenario)
        return {
            "make_preview": _make_preview_payload(
                scenario=scenario,
                projection=projection,
                summary=summary,
                runtime_counts=runtime_counts,
                output_mode=output_mode,
                include_blueprint_json=False,
                verification=_verification_context(
                    scenario=scenario, profile="import_test"
                ),
            )
        }
    if surface == "readiness":
        summary = _scenario_summary(scenario)
        runtime_counts = _runtime_setup_counts(scenario)
        return {
            "readiness": validation_surface_payload(
                statuses=_validation_statuses(
                    summary=summary, runtime_counts=runtime_counts
                )
            )
        }
    if surface in {"parity", "issues", "lineage", "layout"}:
        return _analysis_surface_payload(
            surface=surface, scenario=scenario, project_id=project_id
        )
    if surface == "raw":
        return {
            "raw": {
                "omitted": True,
                "reason": (
                    "Raw scenario JSON is debug evidence, not the normal IDE workflow. "
                    "Use semantic project.view surfaces or project.edit instead."
                ),
                "next_query": f"project.view project_id={project_id} surface=modules output_mode=full",
            }
        }
    _raise_value_error(f"Unsupported project.view surface: {surface}")


def _overview_surface_payload(
    *,
    scenario: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    """Return grouped overview counts without dumping raw graph rows."""
    summary = _scenario_summary(scenario)
    module_groups = _module_groups(
        scenario=scenario, output_mode=output_mode, limit=limit
    )
    hidden_group_count = max(
        len(_all_module_group_rows(scenario)) - len(module_groups), 0
    )
    return {
        "scenario_overview": summary,
        "module_groups": module_groups,
        "hidden_module_group_count": hidden_group_count,
        "raw_graph_available": bool(
            _int_mapping_value(summary, "module_count")
        ),
        "raw_available": True,
        "next_queries": (
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "graph",
                    "output_mode": "compact",
                },
                reason="Inspect the bounded execution graph.",
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "modules",
                    "output_mode": "compact",
                },
                reason="Inspect grouped module rows.",
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "links",
                    "output_mode": "compact",
                },
                reason="Inspect deduped semantic execution links.",
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "filters",
                    "output_mode": "compact",
                },
                reason="Inspect route filters.",
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "notes",
                    "output_mode": "compact",
                },
                reason="Inspect handoff note coverage.",
            ),
        ),
        "expansion_options": (
            "surface=graph",
            "surface=modules",
            "surface=links",
            "surface=filters",
            "surface=runtime",
            "surface=notes",
            "surface=raw output_mode=debug",
        ),
    }


def _graph_surface_payload(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    modules = tuple(_focused_modules(scenario=scenario, focus=focus))
    links = tuple(_focused_links(scenario=scenario, focus=focus))
    returned_modules, hidden_modules = _bounded_items(
        items=modules,
        output_mode=output_mode,
        limit=limit,
    )
    returned_links, hidden_links = _bounded_items(
        items=links,
        output_mode=output_mode,
        limit=limit,
    )
    next_query = None
    if hidden_modules or hidden_links:
        next_query = f"project.view project_id={project_id} surface=graph output_mode=full"
    return {
        "graph_view": {
            "nodes": returned_modules,
            "connections": returned_links,
            "groups": _graph_groups(returned_modules),
            "returned_node_count": len(returned_modules),
            "hidden_node_count": hidden_modules,
            "returned_connection_count": len(returned_links),
            "hidden_connection_count": hidden_links,
            "next_query": next_query,
        },
        "hidden_context": (
            "compact_graph_omits_node_details"
            if hidden_modules or hidden_links
            else None
        ),
        "expansion_options": (
            "surface=modules",
            "surface=links",
            "surface=filters",
            "surface=error_handlers",
            "output_mode=full",
        ),
    }


def _modules_surface_payload(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    modules = tuple(_focused_modules(scenario=scenario, focus=focus))
    returned_modules, hidden_modules = _bounded_items(
        items=modules,
        output_mode=output_mode,
        limit=limit,
    )
    return {
        "modules": returned_modules,
        "module_count": len(modules),
        "returned_module_count": len(returned_modules),
        "hidden_module_count": hidden_modules,
        "next_query": (
            f"project.view project_id={project_id} surface=modules output_mode=full"
            if hidden_modules
            else None
        ),
    }


def _links_surface_payload(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    links = tuple(_focused_links(scenario=scenario, focus=focus))
    returned_links, hidden_links = _bounded_items(
        items=links,
        output_mode=output_mode,
        limit=limit,
    )
    return {
        "links": returned_links,
        "link_count": len(links),
        "link_count_semantics": "deduped_semantic_execution_links",
        "raw_route_and_flow_edge_count": _raw_route_and_flow_edge_count(
            scenario
        ),
        "link_deduplication_note": (
            "Route-entry edges and duplicate flow edges are deduped for handoff note counts; "
            "stress fixture semantic links are 301 rather than the raw 331 route/flow edge views."
        ),
        "returned_link_count": len(returned_links),
        "hidden_link_count": hidden_links,
        "next_query": (
            f"project.view project_id={project_id} surface=links output_mode=full"
            if hidden_links
            else None
        ),
    }


def _filters_surface_payload(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    filters = tuple(_focused_filters(scenario=scenario, focus=focus))
    returned_filters, hidden_filters = _bounded_items(
        items=filters,
        output_mode=output_mode,
        limit=limit,
    )
    return {
        "filters": returned_filters,
        "filter_count": len(filters),
        "returned_filter_count": len(returned_filters),
        "hidden_filter_count": hidden_filters,
        "next_query": (
            f"project.view project_id={project_id} surface=filters output_mode=full"
            if hidden_filters
            else None
        ),
    }


def _error_handlers_surface_payload(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
    output_mode: str,
    limit: int,
    project_id: str,
) -> JsonObject:
    handlers = tuple(_focused_error_handlers(scenario=scenario, focus=focus))
    returned_handlers, hidden_handlers = _bounded_items(
        items=handlers,
        output_mode=output_mode,
        limit=limit,
    )
    return {
        "error_handlers": returned_handlers,
        "error_handler_count": len(handlers),
        "returned_error_handler_count": len(returned_handlers),
        "hidden_error_handler_count": hidden_handlers,
        "next_query": (
            f"project.view project_id={project_id} surface=error_handlers output_mode=full"
            if hidden_handlers
            else None
        ),
    }


def _notes_surface_payload(
    *,
    scenario: Mapping[str, object],
    project_id: str,
    output_mode: str,
    limit: int,
) -> JsonObject:
    coverage = _note_coverage(scenario)
    notes = _scenario_notes(scenario)
    returned_notes = (
        notes if output_mode in {"full", "debug"} else tuple(notes[:limit])
    )
    payload: JsonObject = {
        "scenario_notes_summary": {
            **coverage,
            "note_count": len(notes),
            "present_note_count": len(notes),
            "returned_note_count": len(returned_notes),
            "hidden_note_count": max(len(notes) - len(returned_notes), 0),
            "next_queries": (
                (
                    _next_query(
                        tool="project.view",
                        arguments={
                            "project_id": project_id,
                            "surface": "notes",
                            "output_mode": "full",
                        },
                        reason="Inspect exact note rows and raw missing note evidence.",
                    ),
                )
                if len(notes) > len(returned_notes)
                else ()
            ),
        },
        "batch_note_plan": _batch_note_plan(coverage=coverage),
        "missing_note_plan": _missing_note_plan(scenario=scenario, limit=limit),
        "raw_missing_notes_available": bool(
            coverage["missing_module_note_count"]
            or coverage["missing_connection_note_count"]
        ),
        "raw_available": bool(notes),
    }
    if output_mode in {"full", "debug"} and returned_notes:
        payload["notes"] = _redacted_notes_for_output(returned_notes)
        payload["notes_output_redaction_status"] = (
            "redacted"
            if coverage["note_redaction_issue_count"]
            else "not_needed"
        )
    return payload


def _analysis_surface_payload(
    *,
    surface: str,
    scenario: Mapping[str, object],
    project_id: str,
) -> JsonObject:
    summary = _scenario_summary(scenario)
    return {
        surface: {
            "status": "not_evaluated",
            "reason": (
                f"{surface} is an IDE analysis surface. It needs the next dedicated "
                "implementation pass before it can claim external Make runtime truth."
            ),
            "local_graph_summary": summary,
            "follow_up": {
                "tool": "backlog.add",
                "suggested_title": f"Implement project.view {surface} analysis for {project_id}",
            },
        }
    }


def _next_query(
    *, tool: str, arguments: Mapping[str, object], reason: str
) -> JsonObject:
    return {"tool": tool, "arguments": dict(arguments), "reason": reason}


def _focused_modules(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
) -> Iterable[JsonObject]:
    requested_node = _focus_node_id(focus)
    for path, module in _iter_modules(scenario):
        if requested_node is None or _node_id(module) == requested_node:
            yield _module_summary(path, module)


def _focused_links(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
) -> Iterable[JsonObject]:
    requested_node = _focus_node_id(focus)
    requested_route = _focus_route_index(focus)
    for link in _derive_links(scenario):
        if requested_node is not None and requested_node not in {
            str(link.get("source_node_id")),
            str(link.get("target_node_id")),
        }:
            continue
        if (
            requested_route is not None
            and link.get("route_index") != requested_route
        ):
            continue
        yield link


def _focused_filters(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
) -> Iterable[JsonObject]:
    requested_node = _focus_node_id(focus)
    requested_route = _focus_route_index(focus)
    global_route_index = 0
    for module, route_index, route in _iter_routes(scenario):
        current_global_route_index = global_route_index
        global_route_index += 1
        if "filter" not in route:
            continue
        if requested_node is not None and _node_id(module) != requested_node:
            continue
        if (
            requested_route is not None
            and requested_node is not None
            and route_index != requested_route
        ):
            continue
        if (
            requested_route is not None
            and requested_node is None
            and current_global_route_index != requested_route
        ):
            continue
        summary = _filter_summary(
            module=module, route_index=route_index, route=route
        )
        summary["route_id"] = f"route:{current_global_route_index}"
        summary["global_route_index"] = current_global_route_index
        yield summary


def _focused_error_handlers(
    *,
    scenario: Mapping[str, object],
    focus: Mapping[str, object],
) -> Iterable[JsonObject]:
    requested_node = _focus_node_id(focus)
    for path, module in _iter_modules(scenario):
        node_id = _node_id(module)
        if requested_node is not None and node_id != requested_node:
            continue
        for index, handler in enumerate(_handlers_for_module(module)):
            yield {
                "node_id": node_id,
                "handler_index": index,
                "path": f"{path}.onerror[{index}]",
                "flow_count": len(_flow_from_mapping(handler)),
            }


def _bounded_items(
    *,
    items: tuple[JsonObject, ...],
    output_mode: str,
    limit: int,
) -> tuple[tuple[JsonObject, ...], int]:
    if output_mode in {"full", "debug"}:
        return items, 0
    bounded = items[:limit]
    return bounded, max(len(items) - len(bounded), 0)


def _graph_groups(
    modules: Iterable[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    counts: dict[str, int] = {}
    for module in modules:
        module_name = str(module.get("module") or "")
        app_slug = (
            module_name.split(":", maxsplit=1)[0]
            if ":" in module_name
            else module_name
        )
        key = app_slug or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        {"group": app_slug, "node_count": count}
        for app_slug, count in sorted(counts.items())
    )


def _module_groups(
    *,
    scenario: Mapping[str, object],
    output_mode: str,
    limit: int,
) -> tuple[JsonObject, ...]:
    rows = _all_module_group_rows(scenario)
    if output_mode in {"full", "debug"}:
        return rows
    return rows[:limit]


def _all_module_group_rows(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    groups: dict[str, JsonObject] = {}
    for _path, module in _iter_modules(scenario):
        module_token = _optional_text(module.get("module")) or "unknown"
        app_slug = (
            module_token.split(":", maxsplit=1)[0]
            if ":" in module_token
            else module_token
        )
        group = groups.setdefault(
            app_slug,
            {
                "group": app_slug,
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_node_ids"])
        if len(examples) < PROJECT_EXAMPLE_LIMIT:
            node_id = _node_id(module)
            if node_id is not None:
                examples.append(node_id)
    rows: list[JsonObject] = []
    for group in groups.values():
        example_count = len(cast("list[str]", group["example_node_ids"]))
        group["hidden_node_count"] = max(
            _int_mapping_value(group, "count") - example_count, 0
        )
        rows.append(group)
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["group"]),
            ),
        )
    )


def _focus_payload(arguments: Mapping[str, object]) -> JsonObject:
    focus_value = arguments.get("focus")
    focus: JsonObject = {}
    if isinstance(focus_value, dict):
        focus.update(
            {
                str(key): item
                for key, item in cast(
                    "Mapping[object, object]", focus_value
                ).items()
            }
        )
    for key in (
        "node_id",
        "module_id",
        "route_index",
        "handler_index",
        "module",
        "app_slug",
        "field_ref",
    ):
        if key in arguments and arguments[key] is not None:
            focus[key] = arguments[key]
    if "module_id" in focus and "node_id" not in focus:
        focus["node_id"] = focus["module_id"]
    return focus


def _wrapper_view_arguments(
    *, arguments: Mapping[str, object], surface: str
) -> JsonObject:
    dispatch: JsonObject = {
        str(key): value for key, value in arguments.items() if key != "route_id"
    }
    dispatch["surface"] = surface
    _ = dispatch.setdefault("output_mode", "compact")
    _ = dispatch.setdefault("limit", PROJECT_WRAPPER_DEFAULT_LIMIT)
    return dispatch


def _route_index_from_route_id(route_id: str) -> int | None:
    normalized = route_id.strip().casefold()
    if normalized.startswith("route:"):
        normalized = normalized.removeprefix("route:").strip()
    if not normalized.isdecimal():
        return None
    return int(normalized)


def _focus_node_id(focus: Mapping[str, object]) -> str | None:
    return _optional_node_id(focus.get("node_id") or focus.get("module_id"))


def _focus_route_index(focus: Mapping[str, object]) -> int | None:
    value = focus.get("route_index")
    if value is None:
        return None
    return _nonnegative_int(value, default=0, upper=10_000)


def _runtime_setup_counts(
    scenario: Mapping[str, object],
) -> RuntimeSetupSurfaceCounts:
    occurrences = _runtime_placeholder_occurrences(scenario)
    affected_nodes = {str(row["node_id"]) for row in occurrences}
    distinct_bindings = {str(row["source"]) for row in occurrences}
    item_count = len(distinct_bindings)
    group_count = len(
        {_runtime_provider(binding) for binding in distinct_bindings}
    )
    return RuntimeSetupSurfaceCounts(
        occurrence_count=len(occurrences),
        affected_node_count=len(affected_nodes),
        distinct_binding_count=len(distinct_bindings),
        item_count=item_count,
        group_count=group_count,
    )


def _runtime_placeholder_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        for match in RUNTIME_PLACEHOLDER_PATTERN.finditer(value):
            yield match.group(0).strip()
        return
    if isinstance(value, dict):
        for child in cast("Mapping[object, object]", value).values():
            yield from _runtime_placeholder_values(child)
        return
    if isinstance(value, list | tuple):
        for child in cast("Sequence[object]", value):
            yield from _runtime_placeholder_values(child)


def _runtime_placeholder_occurrences(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    occurrences: list[JsonObject] = []
    seen: set[tuple[str, str, str, str]] = set()
    for module_path, module in _iter_modules(scenario):
        node_id = _node_id(module)
        if node_id is None:
            continue
        module_token = _optional_text(module.get("module")) or "unknown"
        for (
            field_path,
            field_name,
            placeholder,
        ) in _runtime_occurrences_in_module(
            module=module,
            module_path=module_path,
        ):
            surface_kind = _runtime_surface_kind(
                field_name=field_name, source=placeholder
            )
            key = (node_id, field_path, placeholder, surface_kind)
            if key in seen:
                continue
            seen.add(key)
            occurrences.append(
                {
                    "node_id": node_id,
                    "owner_path": module_path,
                    "field_path": field_path,
                    "field": field_name,
                    "module": module_token,
                    "source": placeholder,
                    "provider": _runtime_provider(placeholder),
                    "surface_kind": surface_kind,
                }
            )
    return tuple(occurrences)


def _runtime_occurrences_in_module(
    *,
    module: Mapping[str, object],
    module_path: str,
) -> Iterator[tuple[str, str, str]]:
    for key, child in module.items():
        key_text = str(key)
        if key_text == "routes" and isinstance(child, list):
            for route_index, route in enumerate(cast("list[object]", child)):
                if not isinstance(route, dict):
                    continue
                for route_key, route_child in cast(
                    "Mapping[object, object]", route
                ).items():
                    route_key_text = str(route_key)
                    if route_key_text == "flow":
                        continue
                    route_path = (
                        f"{module_path}.routes[{route_index}].{route_key_text}"
                    )
                    yield from _runtime_occurrences_in_value(
                        route_child,
                        field_path=route_path,
                        field_name=route_key_text,
                    )
            continue
        if key_text == "onerror" and isinstance(child, list):
            for handler_index, handler in enumerate(
                cast("list[object]", child)
            ):
                if not isinstance(handler, dict):
                    continue
                for handler_key, handler_child in cast(
                    "Mapping[object, object]", handler
                ).items():
                    handler_key_text = str(handler_key)
                    if handler_key_text == "flow":
                        continue
                    handler_path = f"{module_path}.onerror[{handler_index}].{handler_key_text}"
                    yield from _runtime_occurrences_in_value(
                        handler_child,
                        field_path=handler_path,
                        field_name=handler_key_text,
                    )
            continue
        yield from _runtime_occurrences_in_value(
            child,
            field_path=f"{module_path}.{key_text}",
            field_name=key_text,
        )


def _runtime_occurrences_in_value(
    value: object,
    *,
    field_path: str,
    field_name: str,
) -> Iterator[tuple[str, str, str]]:
    if isinstance(value, str):
        for placeholder in _runtime_placeholder_values(value):
            yield field_path, field_name, placeholder
        return
    if isinstance(value, dict):
        for key, child in cast("Mapping[object, object]", value).items():
            key_text = str(key)
            yield from _runtime_occurrences_in_value(
                child,
                field_path=f"{field_path}.{key_text}",
                field_name=key_text,
            )
        return
    if isinstance(value, list | tuple):
        for index, child in enumerate(cast("Sequence[object]", value)):
            yield from _runtime_occurrences_in_value(
                child,
                field_path=f"{field_path}[{index}]",
                field_name=field_name,
            )


def _runtime_setup_groups(
    scenario: Mapping[str, object],
    *,
    limit: int,
    include_paths: bool = False,
) -> tuple[JsonObject, ...]:
    groups: dict[tuple[str, str], JsonObject] = {}
    for occurrence in _runtime_placeholder_occurrences(scenario):
        provider = str(occurrence["provider"])
        placeholder = str(occurrence["source"])
        key = (provider, placeholder)
        group = groups.setdefault(
            key,
            {
                "provider": provider,
                "setup_group": _runtime_setup_group_label(provider),
                "source": placeholder,
                "placeholder_name": _runtime_placeholder_name(placeholder),
                "placeholder_value_included": False,
                "value_policy": "names_only_no_runtime_values",
                "count": 0,
                "example_node_ids": [],
                "module_examples": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        node_examples = cast("list[str]", group["example_node_ids"])
        node_id = str(occurrence["node_id"])
        if (
            node_id not in node_examples
            and len(node_examples) < PROJECT_EXAMPLE_LIMIT
        ):
            node_examples.append(node_id)
        module_examples = cast("list[str]", group["module_examples"])
        module_token = str(occurrence["module"])
        if (
            len(module_examples) < PROJECT_EXAMPLE_LIMIT
            and module_token not in module_examples
        ):
            module_examples.append(module_token)
        if include_paths:
            path_examples = cast(
                "list[str]", group.setdefault("example_field_paths", [])
            )
            field_path = str(occurrence["field_path"])
            if (
                field_path not in path_examples
                and len(path_examples) < PROJECT_EXAMPLE_LIMIT
            ):
                path_examples.append(field_path)
    return tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["provider"]),
            ),
        )[:limit]
    )


def _runtime_placeholder_name(placeholder: str) -> str:
    normalized = placeholder.strip()
    if normalized == "__IMTCONN__":
        return normalized
    return normalized.strip("{} ").strip()


def _runtime_surface_kind(*, field_name: str, source: str) -> str:
    if _is_make_connection_binding(field_name=field_name, source=source):
        return "make_connection_placeholder"
    return "runtime_resource_placeholder"


def _runtime_setup_group_label(provider: str) -> str:
    if provider == "datastore":
        return "Data stores"
    if provider == "webhook":
        return "Webhook"
    if provider == "slack":
        return "Slack"
    if provider == "make_connection":
        return "Make connections"
    return provider.replace("_", " ").title()


def _runtime_provider(placeholder: str) -> str:
    normalized = placeholder.strip("{} ").casefold()
    if normalized.startswith("runtime.connection."):
        remainder = normalized.removeprefix("runtime.connection.")
        return remainder.split("_", maxsplit=1)[0] or "connection"
    if normalized.startswith("runtime."):
        remainder = normalized.removeprefix("runtime.")
        return remainder.split(".", maxsplit=1)[0] or "runtime"
    if "__imtconn__" in normalized:
        return "make_connection"
    return "runtime"


def _validation_statuses(
    *,
    summary: Mapping[str, object],
    runtime_counts: RuntimeSetupSurfaceCounts,
) -> ValidationSurfaceStatuses:
    module_count = _int_mapping_value(summary, "module_count")
    structural_status = "valid" if module_count >= 0 else "invalid"
    import_status = "ready" if module_count > 0 else "blocked"
    runtime_status = "required" if runtime_counts.item_count else "not_required"
    return ValidationSurfaceStatuses(
        structural_validation_status=structural_status,
        make_import_validation_status=import_status,
        client_handoff_validation_status="not_required",
        runtime_setup_validation_status=runtime_status,
        scenario_tests_status="not_required",
        native_parity_validation_status="not_evaluated",
    )


def _make_preview_payload(
    *,
    scenario: Mapping[str, object],
    projection: JsonObject,
    summary: Mapping[str, object],
    runtime_counts: RuntimeSetupSurfaceCounts,
    output_mode: str,
    include_blueprint_json: bool,
    verification: Mapping[str, object],
) -> JsonObject:
    zero_trace = _zero_trace_for_projection(projection)
    roundtrip = _roundtrip_validation_payload(
        scenario=scenario, projection=projection
    )
    include_raw = include_blueprint_json and output_mode in {"full", "debug"}
    import_status = str(verification["make_import_validation_status"])
    client_handoff_status = str(verification["client_handoff_status"])
    note_coverage = cast("Mapping[str, object]", verification["note_coverage"])
    payload: JsonObject = {
        "preview_status": "preview_ready",
        "artifact_format": "make_blueprint_json",
        "response_includes_raw_json": include_raw,
        "raw_artifact_available": True,
        "raw_available": True,
        "summary": dict(summary),
        "make_import_validation_status": import_status,
        "import_status": import_status,
        "importable": import_status == "ready",
        "can_import_to_make": import_status == "ready",
        "client_handoff_status": client_handoff_status,
        "client_handoff_validation_status": client_handoff_status,
        "native_parity_status": verification["native_parity_validation_status"],
        "private_metadata_blocked": zero_trace["zero_trace_status"] == "failed",
        "runtime_setup": {
            **runtime_setup_count_payload(runtime_counts),
            "groups": _runtime_setup_groups(
                scenario,
                limit=PROJECT_VIEW_DEFAULT_LIMIT,
                include_paths=output_mode in {"full", "debug"},
            ),
        },
        **runtime_setup_count_payload(runtime_counts),
        **zero_trace,
        "zero_trace_surface": "rendered_preview_artifact",
        "module_translation_summary": _module_translation_summary(
            scenario=scenario,
            output_mode=output_mode,
        ),
        "connection_binding_summary": _connection_binding_summary(
            scenario=scenario,
            output_mode=output_mode,
        ),
        "resource_binding_summary": _resource_binding_summary(
            scenario=scenario,
            output_mode=output_mode,
        ),
        "pass_through_unknown_module_count": _pass_through_unknown_module_count(
            scenario
        ),
        **roundtrip,
        "next_queries": (
            _next_query(
                tool="project.make",
                arguments={
                    "project_id": "<id>",
                    "action": "render",
                    "output_mode": "full",
                },
                reason="Render the Make-native blueprint artifact with exact projection evidence.",
            ),
        ),
        "handoff_risk_summary": verification["handoff_risk_summary"],
        "note_readiness_status": _note_readiness_status(note_coverage),
        "note_section_validation_status": note_coverage[
            "note_section_validation_status"
        ],
        "note_redaction_status": note_coverage["note_redaction_status"],
        "note_redaction_evidence": note_coverage["redaction_evidence"],
    }
    if _note_readiness_status(note_coverage) != "ready":
        payload["missing_note_plan"] = _missing_note_plan(scenario=scenario)
    if include_raw:
        payload["artifact_json"] = projection
    return payload


def _make_import_package_payload(
    *,
    project_id: str,
    scenario: Mapping[str, object],
    profile: str,
    dry_run: bool,
    output_mode: str,
    preview: Mapping[str, object],
    verification: Mapping[str, object],
) -> JsonObject:
    """Return a local-only Make import package handoff summary."""
    note_coverage = cast("Mapping[str, object]", verification["note_coverage"])
    include_details = output_mode in {"full", "debug"}
    datastore_manifest = _datastore_manifest(
        scenario=scenario,
        output_mode="full" if include_details else "compact",
    )
    live_resource_datastore_manifest = (
        datastore_manifest
        if include_details
        else _datastore_manifest(scenario=scenario, output_mode="full")
    )
    import_ready = preview.get("import_status") == "ready"
    zero_trace_ready = preview.get("zero_trace_status") == "passed"
    note_readiness_status = _note_readiness_status(note_coverage)
    handoff_blocked = (
        profile == "client_handoff"
        and preview.get("client_handoff_status") == "blocked"
    )
    live_requirements_summary = _make_mcp_live_requirements_summary()
    full_live_validation_status = (
        "blocked_missing_capabilities"
        if live_requirements_summary[
            "full_live_validation_required_missing_count"
        ]
        else "ready"
    )
    minimal_import_ready = (
        import_ready
        and zero_trace_ready
        and live_requirements_summary["minimal_import_required_missing_count"]
        == 0
    )
    status = (
        "blocked"
        if handoff_blocked or not import_ready or not zero_trace_ready
        else "ready"
    )
    package_status = "ready" if status == "ready" else "blocked"
    top_status = (
        "package_ready" if package_status == "ready" else "package_blocked"
    )
    blocked_surfaces = _package_readiness_blocked_surfaces(
        import_ready=import_ready,
        zero_trace_ready=zero_trace_ready,
        note_readiness_status=note_readiness_status,
    )
    status_reason = _package_status_reason(
        package_status=package_status,
        full_live_validation_status=full_live_validation_status,
    )
    package_summary = _package_summary(
        scenario=scenario,
        datastore_manifest=datastore_manifest,
        preview=preview,
        note_coverage=note_coverage,
    )
    live_resource_package = _make_live_resource_package(
        project_id=project_id,
        scenario=scenario,
        datastore_manifest=live_resource_datastore_manifest,
    )
    live_resource_canary_contract = cast(
        "Mapping[str, object]",
        live_resource_package["live_canary_contract"],
    )
    live_resource_summary = _runtime_resource_provisioning_summary(scenario)
    payload: JsonObject = {
        "status": top_status,
        "status_surface": "local_package",
        "status_reason": status_reason,
        "action": "package",
        "dry_run": dry_run,
        "package_kind": "make_import_package",
        "package_profile": profile,
        "profile": profile,
        "artifact_format": "make_blueprint_json",
        "package_status": package_status,
        "redaction_status": "passed" if zero_trace_ready else "blocked",
        "note_readiness_status": note_readiness_status,
        "note_section_validation_status": note_coverage[
            "note_section_validation_status"
        ],
        "note_redaction_status": note_coverage["note_redaction_status"],
        "note_redaction_evidence": note_coverage["redaction_evidence"],
        "documentation_readiness_status": note_readiness_status,
        "blueprint_readiness_status": "ready"
        if import_ready and zero_trace_ready
        else "blocked",
        "blocked_surfaces": blocked_surfaces,
        "minimal_import_package_status": "ready"
        if minimal_import_ready
        else "blocked",
        "live_preflight_status": (
            "ready"
            if package_status == "ready"
            and full_live_validation_status == "ready"
            else "ready_with_gaps"
            if package_status == "ready"
            else "blocked"
        ),
        "full_live_validation_status": full_live_validation_status,
        "blueprint_artifact": {
            "status": "ready"
            if import_ready and zero_trace_ready
            else "blocked",
            "artifact_format": "make_blueprint_json",
            "raw_artifact_available": True,
            "response_includes_raw_json": False,
            "zero_trace_status": preview["zero_trace_status"],
            "zero_trace_surface": preview["zero_trace_surface"],
        },
        "zero_trace": preview["zero_trace"],
        "zero_trace_status": preview["zero_trace_status"],
        "zero_trace_surface": "package_blueprint_artifact",
        "leak_count": preview["leak_count"],
        "package_summary": package_summary,
        "make_mcp_live_requirements_summary": live_requirements_summary,
        "browser_validation_status": "offline_parity_no_browser_required",
        "browser_validation_boundary": _browser_validation_boundary(
            include_plan=False
        ),
        "raw_package_sections_available": True,
        "written_package_contents_preview": {
            "blueprint_artifact_json": "included",
            "datastore_manifest": "included",
            "live_resource_files": "included",
            "live_apply_plan": "included",
        },
        "live_resource_artifact_status": live_resource_package["status"],
        "live_resource_file_count": live_resource_package["file_count"],
        "auto_provisioned_resource_count": live_resource_package[
            "auto_provisioned_resource_count"
        ],
        "client_supplied_connection_count": live_resource_package[
            "client_supplied_connection_count"
        ],
        "client_supplied_runtime_value_count": live_resource_package[
            "client_supplied_runtime_value_count"
        ],
        "live_canary_status": live_resource_canary_contract["status"],
        "live_resource_creation_order": live_resource_package[
            "resource_creation_order"
        ],
        "live_resource_creation_order_human": live_resource_package[
            "resource_creation_order_human"
        ],
        "live_canary_cleanup_semantics": live_resource_package[
            "cleanup_semantics"
        ],
        "dynamic_api_key_policy": live_resource_package[
            "dynamic_api_key_policy"
        ],
        "one_command_upload_entrypoint": live_resource_package[
            "one_command_upload_entrypoint"
        ],
        "parity_evidence_status": verification[
            "native_parity_validation_status"
        ],
        "make_mcp_live_requirements_status": live_requirements_summary[
            "status"
        ],
        "datastore_manifest_status": datastore_manifest["status"],
        "connection_mapping_status": (
            "client_app_connections_required"
            if _int_mapping_value(
                cast(
                    "Mapping[str, object]",
                    preview["connection_binding_summary"],
                ),
                "binding_count",
            )
            else "not_required"
        ),
        "resource_mapping_status": live_resource_summary["status"],
        "resource_auto_provisioning_status": live_resource_summary[
            "auto_provisioning_status"
        ],
        "blueprint_artifact_json_would_be_included": True,
        "blueprint_artifact_json_omitted_from_response": True,
        "package_contains_secrets": False,
        "package_contains_fake_provider_ids": False,
        "customer_report_included": False,
        "internal_report_status": "not_included",
        "section_inspection_status": "available",
        "section_inspector_sections": PROJECT_PACKAGE_INSPECT_SECTIONS,
        "section_inspector_queries": _project_package_inspector_queries(
            project_id=project_id,
            profile=profile,
        ),
        "full_output_truncation_avoidance": (
            "Use project.package.inspect for one full section at a time instead of asking "
            "chat clients to render the whole package payload."
        ),
        "next_queries": (
            *_project_package_inspector_queries(
                project_id=project_id,
                profile=profile,
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "datastores",
                    "output_mode": "compact",
                },
                reason="Inspect Data Store resource manifests.",
            ),
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": project_id,
                    "surface": "runtime",
                    "output_mode": "compact",
                },
                reason="Inspect runtime resource requirements.",
            ),
        ),
        "project_id": project_id,
        **_local_offline_safety_flags(),
    }
    if note_readiness_status != "ready":
        payload["missing_note_plan"] = _missing_note_plan(scenario=scenario)
    if include_details:
        payload.update(
            {
                "datastore_manifest": datastore_manifest,
                "connection_requirements": _connection_requirements(scenario),
                "runtime_resource_requirements": _runtime_resource_requirements(
                    scenario
                ),
                "make_live_resource_package": live_resource_package,
                "connection_binding_summary": preview[
                    "connection_binding_summary"
                ],
                "resource_binding_summary": preview["resource_binding_summary"],
                "runtime_setup": preview["runtime_setup"],
                "live_apply_plan": _live_apply_plan(),
                "rollback_plan": _rollback_plan(
                    datastore_manifest=datastore_manifest
                ),
                "operator_checklist": _operator_checklist(),
                "pdf_report_inputs": _pdf_report_inputs(
                    note_coverage=note_coverage
                ),
                "make_mcp_capabilities": _make_mcp_capability_matrix(),
                "make_mcp_capability_details": _make_mcp_capability_details(),
                "browser_validation_boundary": _browser_validation_boundary(
                    include_plan=True
                ),
            }
        )
    return payload


def _customer_delivery_package_payload(
    *,
    project_id: str,
    scenario: Mapping[str, object],
) -> JsonObject:
    """Return the customer-visible delivery package contract."""
    package_stem = _customer_delivery_package_stem(
        project_id=project_id, scenario=scenario
    )
    return {
        "package_kind": "customer_blueprint_delivery_package",
        "delivery_boundary": "blueprint_import_only",
        "customer_artifact_name": f"{package_stem}.blueprint.json",
        "customer_receives_internal_report": False,
        "customer_receives_ast": False,
        "customer_receives_graph": False,
        "customer_receives_linter_logic": False,
        "customer_receives_internal_prompts": False,
        "customer_receives_scoring_logic": False,
        "internal_artifacts_exported": False,
        "included_customer_artifacts": (
            "make_blueprint_json",
            "minimal_import_setup_guidance",
            "non_technical_changelog",
        ),
        "excluded_internal_artifacts": CUSTOMER_DELIVERY_EXCLUDED_INTERNAL_ARTIFACTS,
        "files": (
            {
                "path": f"{package_stem}.blueprint.json",
                "artifact_role": "make_blueprint_json",
                "customer_visible": True,
            },
            {
                "path": f"{package_stem}.import-setup.md",
                "artifact_role": "minimal_import_setup_guidance",
                "customer_visible": True,
            },
            {
                "path": f"{package_stem}.changelog.md",
                "artifact_role": "non_technical_changelog",
                "customer_visible": True,
            },
        ),
        "import_setup_guidance": (
            "Run the live upload command with a runtime-only Make API token.",
            (
                "The upload creates resources in this order: Data Structure, Data Store, "
                "Webhook, Scenario."
            ),
            "Customer setup is limited to required app connections and app-specific runtime values.",
            "Review the non-technical changelog before enabling the scenario.",
        ),
        "non_technical_changelog": (
            "Prepared a Make.com blueprint delivery package.",
            "Kept API tokens, provider credentials, and webhook URLs outside the package.",
            "Added first-class live resource manifests for automated Make setup.",
            "Kept internal implementation details outside the delivery package.",
        ),
    }


def _write_customer_delivery_package(
    *,
    package_path: Path,
    delivery_package: Mapping[str, object],
    projection: JsonObject,
) -> None:
    package_path.mkdir(parents=True, exist_ok=True)
    files = cast("tuple[JsonObject, ...]", delivery_package["files"])
    for file_record in files:
        role = str(file_record["artifact_role"])
        file_path = package_path / str(file_record["path"])
        if role == "make_blueprint_json":
            _write_json_object(
                file_path, make_public_safe_blueprint_json(projection)
            )
        elif role == "minimal_import_setup_guidance":
            _ = file_path.write_text(
                _customer_delivery_markdown(
                    title="Import setup",
                    lines=cast(
                        "tuple[str, ...]",
                        delivery_package["import_setup_guidance"],
                    ),
                ),
                encoding="utf-8",
            )
        elif role == "non_technical_changelog":
            _ = file_path.write_text(
                _customer_delivery_markdown(
                    title="Changelog",
                    lines=cast(
                        "tuple[str, ...]",
                        delivery_package["non_technical_changelog"],
                    ),
                ),
                encoding="utf-8",
            )
    manifest: JsonObject = {
        "package_kind": str(delivery_package["package_kind"]),
        "delivery_boundary": str(delivery_package["delivery_boundary"]),
        "customer_artifact_name": str(
            delivery_package["customer_artifact_name"]
        ),
        "customer_receives_internal_report": False,
        "internal_artifacts_exported": False,
        "included_customer_artifacts": delivery_package[
            "included_customer_artifacts"
        ],
        "excluded_internal_artifacts": delivery_package[
            "excluded_internal_artifacts"
        ],
        "files": delivery_package["files"],
    }
    _write_json_object(package_path / "delivery-manifest.json", manifest)


def _customer_delivery_markdown(*, title: str, lines: tuple[str, ...]) -> str:
    body = "\n".join(f"- {line}" for line in lines)
    return f"# {title}\n\n{body}\n"


def _make_live_resource_package(
    *,
    project_id: str,
    scenario: Mapping[str, object],
    datastore_manifest: Mapping[str, object],
) -> JsonObject:
    data_structures = _make_live_data_structure_artifacts(datastore_manifest)
    data_stores = _make_live_datastore_artifacts(datastore_manifest)
    webhooks = _make_live_webhook_artifacts(scenario)
    connections = _connection_requirements(scenario, include_paths=True)
    runtime_values = tuple(
        requirement
        for requirement in _runtime_resource_requirements(scenario)
        if not _runtime_requirement_is_auto_provisioned(requirement)
    )
    files: tuple[JsonObject, ...] = (
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/datastructure.json",
            "artifact_role": "make_data_structure_manifest",
        },
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/datastore.json",
            "artifact_role": "make_data_store_manifest",
        },
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/webhook.json",
            "artifact_role": "make_webhook_manifest",
        },
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/connections.json",
            "artifact_role": "client_app_connection_requirements",
        },
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/runtime-values.json",
            "artifact_role": "client_runtime_value_requirements",
        },
        {
            "path": f"{MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME}/upload-plan.json",
            "artifact_role": "one_command_live_upload_plan",
        },
    )
    auto_resource_count = (
        len(data_structures) + len(data_stores) + len(webhooks)
    )
    status = (
        "blocked_missing_datastore_schema"
        if any(
            resource.get("schema_status") != "known"
            for resource in cast(
                "tuple[JsonObject, ...]", datastore_manifest["resources"]
            )
        )
        else "ready"
    )
    upload_plan = _make_live_upload_plan_artifact(
        project_id=project_id,
        data_structures=data_structures,
        data_stores=data_stores,
        webhooks=webhooks,
        connections=connections,
        runtime_values=runtime_values,
        status=status,
    )
    return {
        "package_kind": "make_live_resource_package",
        "status": status,
        "artifact_folder_name": MAKE_LIVE_RESOURCE_PACKAGE_FOLDER_NAME,
        "file_count": len(files),
        "files": files,
        "data_structures": data_structures,
        "data_stores": data_stores,
        "webhooks": webhooks,
        "connections": connections,
        "runtime_values": runtime_values,
        "upload_plan": upload_plan,
        "auto_provisioned_resource_count": auto_resource_count,
        "client_supplied_connection_count": len(connections),
        "client_supplied_runtime_value_count": len(runtime_values),
        "dependency_order": upload_plan["dependency_order"],
        "resource_creation_order": MAKE_LIVE_RESOURCE_CREATION_ORDER,
        "resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "live_canary_contract": _make_live_canary_contract(),
        "cleanup_semantics": MAKE_LIVE_CANARY_CLEANUP_SEMANTICS,
        "dynamic_api_key_policy": _dynamic_make_api_key_policy(),
        "one_command_upload_entrypoint": _make_live_upload_entrypoint(),
        "manual_make_ui_required_for_resources": False,
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _make_live_data_structure_artifacts(
    datastore_manifest: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    resources = cast("tuple[JsonObject, ...]", datastore_manifest["resources"])
    artifacts: list[JsonObject] = []
    for resource in resources:
        resource_key = str(resource["resource_key"])
        key_field = _optional_text(resource.get("key_field"))
        fields = _text_list(resource.get("schema_fields"))
        artifacts.append(
            {
                "resource_key": resource_key,
                "name": _human_label(resource_key, suffix="Data Structure"),
                "strict": True,
                "schema_status": resource["schema_status"],
                "source_json_pointer": resource.get("source_json_pointer"),
                "spec": tuple(
                    {
                        "name": field,
                        "label": _human_label(field, suffix=""),
                        "type": "text",
                        "required": field == key_field,
                    }
                    for field in fields
                ),
                "required_field": key_field,
                "bind_ref": resource_key,
            }
        )
    return tuple(artifacts)


def _make_live_datastore_artifacts(
    datastore_manifest: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    resources = cast("tuple[JsonObject, ...]", datastore_manifest["resources"])
    artifacts: list[JsonObject] = []
    for resource in resources:
        resource_key = str(resource["resource_key"])
        artifacts.append(
            {
                "resource_key": resource_key,
                "name": str(resource["human_label"]),
                "datastructure_ref": resource_key,
                "maxSizeMB": MAKE_LIVE_RESOURCE_MAX_SIZE_MB,
                "bind_placeholder": f"{{{{runtime.datastore.{resource_key}}}}}",
                "target_blueprint_field": "parameters.datastore",
                "seed_records_available": resource["seed_records_available"],
                "record_count": resource["record_count"],
                "batch_upsert_plan": resource["batch_upsert_plan"],
            }
        )
    return tuple(artifacts)


def _make_live_webhook_artifacts(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    grouped: dict[str, JsonObject] = {}
    for occurrence in _runtime_placeholder_occurrences(scenario):
        if occurrence["provider"] != "webhook":
            continue
        source = str(occurrence["source"])
        resource_key = _runtime_resource_key(source)
        group = grouped.setdefault(
            resource_key,
            {
                "resource_key": resource_key,
                "name": _human_label(resource_key, suffix="Webhook"),
                "typeName": MAKE_LIVE_WEBHOOK_TYPE_NAME,
                "data": dict(MAKE_LIVE_WEBHOOK_DEFAULT_DATA),
                "bind_placeholder": source,
                "target_blueprint_field": "parameters.hook",
                "example_node_ids": [],
                "example_field_paths": [],
                "manual_create_prompt_allowed": False,
            },
        )
        examples = cast("list[str]", group["example_node_ids"])
        node_id = str(occurrence["node_id"])
        if node_id not in examples and len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
        paths = cast("list[str]", group["example_field_paths"])
        field_path = str(occurrence["field_path"])
        if field_path not in paths and len(paths) < PROJECT_EXAMPLE_LIMIT:
            paths.append(field_path)
    return tuple(
        sorted(grouped.values(), key=lambda item: str(item["resource_key"]))
    )


def _make_live_upload_plan_artifact(
    *,
    project_id: str,
    data_structures: tuple[JsonObject, ...],
    data_stores: tuple[JsonObject, ...],
    webhooks: tuple[JsonObject, ...],
    connections: tuple[JsonObject, ...],
    runtime_values: tuple[JsonObject, ...],
    status: str,
) -> JsonObject:
    return {
        "artifact_kind": "make_live_upload_plan",
        "status": status,
        "project_id": project_id,
        "dependency_order": (
            "create_data_structures",
            "create_data_stores_with_created_data_structure_ids",
            "create_webhooks",
            "validate_client_app_connections",
            "bind_created_resource_ids_into_blueprint",
            "bind_client_connection_ids_into_blueprint",
            "bind_client_runtime_values_into_blueprint",
            "create_inactive_on_demand_scenario",
            "export_and_compare_blueprint",
        ),
        "resource_creation_order": MAKE_LIVE_RESOURCE_CREATION_ORDER,
        "resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "live_canary_status": _make_live_canary_contract()["status"],
        "cleanup_semantics": MAKE_LIVE_CANARY_CLEANUP_SEMANTICS,
        "data_structure_count": len(data_structures),
        "data_store_count": len(data_stores),
        "webhook_count": len(webhooks),
        "client_connection_requirement_count": len(connections),
        "client_runtime_value_requirement_count": len(runtime_values),
        "dynamic_api_key_policy": _dynamic_make_api_key_policy(),
        "one_command_upload_entrypoint": _make_live_upload_entrypoint(),
        "manual_resource_creation_required": False,
        "webhook_create_prompt_allowed": False,
        "scenario_activation_allowed": False,
        "run_once_allowed": False,
        "rollback_policy": (
            "Delete created scenario, hooks, data stores, and data structures if any "
            "later upload step fails before handoff."
        ),
    }


def _make_live_canary_contract() -> JsonObject:
    return {
        "status": "destructive_webhook_datastore_canary_passed_and_cleaned",
        "evidence_kind": "mcp_browser_make_destructive_canary",
        "resource_creation_order": MAKE_LIVE_RESOURCE_CREATION_ORDER,
        "resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "cleanup_required": True,
        "cleanup_semantics": MAKE_LIVE_CANARY_CLEANUP_SEMANTICS,
        "run_once_policy": "not_used_by_package_preflight",
        "scenario_activation_policy": "destructive_canary_only_then_deactivate",
        "raw_provider_ids_persisted": False,
        "secret_output": False,
    }


def _dynamic_make_api_key_policy() -> JsonObject:
    return {
        "api_key_source": "runtime_environment_or_stdin_only",
        "artifact_storage_allowed": False,
        "database_storage_allowed": False,
        "local_storage_allowed": False,
        "log_output_allowed": False,
        "recommended_env_var": "MAKE_API_TOKEN",
    }


def _make_live_upload_entrypoint() -> str:
    return (
        "python -m languages.make.live_upload --project-folder <project-folder> "
        "--team-id <team-id> --organization-id <organization-id> --apply"
    )


def _write_make_live_resource_package(
    *,
    package_path: Path,
    resource_package: Mapping[str, object],
) -> None:
    package_path.mkdir(parents=True, exist_ok=True)
    _write_json_object(
        package_path / "datastructure.json",
        make_public_safe_live_resource_manifest(
            {
                "artifact_kind": "make_live_data_structures",
                "resources": resource_package["data_structures"],
            }
        ),
    )
    _write_json_object(
        package_path / "datastore.json",
        make_public_safe_live_resource_manifest(
            {
                "artifact_kind": "make_live_data_stores",
                "resources": resource_package["data_stores"],
            }
        ),
    )
    _write_json_object(
        package_path / "webhook.json",
        make_public_safe_live_resource_manifest(
            {
                "artifact_kind": "make_live_webhooks",
                "resources": resource_package["webhooks"],
            }
        ),
    )
    _write_json_object(
        package_path / "connections.json",
        make_public_safe_live_resource_manifest(
            {
                "artifact_kind": "client_app_connection_requirements",
                "resources": resource_package["connections"],
            }
        ),
    )
    _write_json_object(
        package_path / "runtime-values.json",
        make_public_safe_live_resource_manifest(
            {
                "artifact_kind": "client_runtime_value_requirements",
                "resources": resource_package["runtime_values"],
            }
        ),
    )
    _write_json_object(
        package_path / "upload-plan.json",
        make_public_safe_live_resource_manifest(
            cast("JsonObject", resource_package["upload_plan"])
        ),
    )


def _customer_delivery_package_stem(
    *,
    project_id: str,
    scenario: Mapping[str, object],
) -> str:
    name = _optional_text(scenario.get("name")) or project_id
    customer_key = (
        re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").casefold()
    )
    if not customer_key:
        customer_key = project_id.casefold()
    calver = datetime.now(UTC).strftime("%Y.%m.%d")
    return f"{customer_key}_{calver}"


def _datastore_manifest(
    *, scenario: Mapping[str, object], output_mode: str
) -> JsonObject:
    resources = _datastore_manifest_resources(scenario=scenario)
    visible_resources = (
        resources
        if output_mode in {"full", "debug"}
        else resources[:PROJECT_VIEW_MAX_LIMIT]
    )
    return {
        "status": "ready" if resources else "not_required",
        "required": bool(resources),
        "resource_count": len(resources),
        "returned_resource_count": len(visible_resources),
        "hidden_resource_count": max(
            len(resources) - len(visible_resources), 0
        ),
        "resources": visible_resources,
        "raw_manifest_available": bool(resources),
    }


def _package_summary(
    *,
    scenario: Mapping[str, object],
    datastore_manifest: Mapping[str, object],
    preview: Mapping[str, object],
    note_coverage: Mapping[str, object],
) -> JsonObject:
    summary = _scenario_summary(scenario)
    runtime_setup = cast("Mapping[str, object]", preview["runtime_setup"])
    connection_summary = cast(
        "Mapping[str, object]", preview["connection_binding_summary"]
    )
    resource_summary = cast(
        "Mapping[str, object]", preview["resource_binding_summary"]
    )
    connection_groups = cast(
        "tuple[JsonObject, ...]", connection_summary["groups"]
    )
    resource_groups = cast("tuple[JsonObject, ...]", resource_summary["groups"])
    return {
        "module_count": summary["module_count"],
        "route_count": summary["route_count"],
        "deduped_link_count": summary["link_count"],
        "raw_route_and_flow_edge_count": summary[
            "raw_route_and_flow_edge_count"
        ],
        "datastore_resource_count": datastore_manifest["resource_count"],
        "connection_requirement_count": len(connection_groups),
        "runtime_resource_requirement_count": len(resource_groups),
        "runtime_setup_item_count": runtime_setup["runtime_setup_item_count"],
        "operator_checklist_item_count": len(_operator_checklist()),
        "rollback_step_count": len(
            cast(
                "tuple[str, ...]",
                _rollback_plan(datastore_manifest=datastore_manifest)["steps"],
            )
        ),
        "required_module_note_count": note_coverage[
            "missing_module_note_count"
        ],
        "required_connection_note_count": note_coverage[
            "missing_connection_note_count"
        ],
    }


def _note_readiness_status(note_coverage: Mapping[str, object]) -> str:
    missing_notes = _int_mapping_value(
        note_coverage, "missing_module_note_count"
    ) + _int_mapping_value(
        note_coverage,
        "missing_connection_note_count",
    )
    if missing_notes:
        return "blocked_missing_notes"
    if _int_mapping_value(note_coverage, "note_section_issue_count"):
        return "blocked_note_sections"
    if _int_mapping_value(note_coverage, "note_redaction_issue_count"):
        return "blocked_note_redaction"
    return "ready"


def _package_readiness_blocked_surfaces(
    *,
    import_ready: bool,
    zero_trace_ready: bool,
    note_readiness_status: str,
) -> tuple[str, ...]:
    blocked: list[str] = []
    if not import_ready:
        blocked.append("make_import")
    if not zero_trace_ready:
        blocked.append("zero_trace")
    if note_readiness_status != "ready":
        blocked.append("client_handoff")
    return tuple(blocked)


def _package_status_reason(
    *, package_status: str, full_live_validation_status: str
) -> str:
    if package_status != "ready":
        return (
            "The local Make import package is blocked by local package prerequisites; no live "
            "Make.com work was attempted."
        )
    if full_live_validation_status != "ready":
        return (
            "The local Make import package is ready; full live validation remains blocked by "
            "missing Make.com MCP or browser-gated capabilities."
        )
    return (
        "The local Make import package is ready and the declared live validation capabilities "
        "are available; live execution uses a runtime-only Make API token and typed bindings."
    )


def _make_mcp_live_requirements_summary() -> JsonObject:
    details = _make_mcp_capability_details()
    unavailable = tuple(
        row
        for row in details
        if _is_unavailable_capability_status(str(row["status"]))
    )
    available = tuple(row for row in details if row not in unavailable)
    minimal_missing = tuple(
        row for row in unavailable if row["required_for_minimal_import"] is True
    )
    full_missing = tuple(
        row
        for row in unavailable
        if row["required_for_full_live_validation"] is True
    )
    visible_available = tuple(
        str(row["capability"]) for row in available[:PROJECT_VIEW_DEFAULT_LIMIT]
    )
    if full_missing and not minimal_missing:
        status_reason = (
            "Minimal import can proceed with typed client app bindings; "
            "full live validation is blocked until missing live capabilities exist."
        )
    elif not unavailable:
        status_reason = (
            "All declared Make.com MCP live capabilities are available."
        )
    else:
        status_reason = "Minimal import and full live validation are blocked by missing live capabilities."
    return {
        "status": "available_with_gaps" if unavailable else "available",
        "available_count": len(available),
        "available_capabilities": visible_available,
        "returned_available_capability_count": len(visible_available),
        "hidden_available_capability_count": max(
            len(available) - len(visible_available), 0
        ),
        "missing_count": len(unavailable),
        "minimal_import_required_missing_count": len(minimal_missing),
        "minimal_import_optional_missing_count": 0,
        "full_live_validation_required_missing_count": len(full_missing),
        "full_live_validation_optional_missing_count": max(
            len(unavailable) - len(minimal_missing) - len(full_missing),
            0,
        ),
        "missing_capabilities": tuple(
            str(row["capability"]) for row in unavailable
        ),
        "missing_for_minimal_import": tuple(
            str(row["capability"]) for row in minimal_missing
        ),
        "missing_for_full_live_validation": tuple(
            str(row["capability"]) for row in full_missing
        ),
        "status_reason": status_reason,
        "raw_capability_matrix_available": True,
    }


def _make_mcp_capability_details() -> tuple[JsonObject, ...]:
    return tuple(
        _make_mcp_capability_detail(capability)
        for capability in sorted(MAKE_MCP_CAPABILITY_MATRIX)
    )


def _make_mcp_capability_detail_for(capability: str) -> JsonObject:
    capability_id = capability.strip()
    if capability_id not in MAKE_MCP_CAPABILITY_MATRIX:
        _raise_value_error(f"Unknown Make.com MCP capability: {capability_id}")
    return _make_mcp_capability_detail(capability_id)


def _make_mcp_capability_detail(capability: str) -> JsonObject:
    status = str(MAKE_MCP_CAPABILITY_MATRIX[capability])
    detail: JsonObject = {
        "capability": capability,
        "status": status,
        "required_for_minimal_import": capability
        in MINIMAL_IMPORT_CAPABILITIES,
        "required_for_full_live_validation": capability
        in FULL_LIVE_VALIDATION_CAPABILITIES,
        "owning_layer": _capability_owning_layer(capability, status),
        "fallback_strategy": _capability_fallback_strategy(capability, status),
        "mapped_live_tool": MAKE_MCP_CAPABILITY_MAPPED_TOOLS.get(capability),
    }
    if capability == "live_apply_package":
        detail["capability_contract"] = _live_apply_capability_contract()
    if status == "offline_mirror":
        detail["offline_mirror_contract"] = _offline_mirror_capability_contract(
            capability=capability
        )
    if capability in {"connection_bind_to_module", "webhook_bind_to_module"}:
        binding_contract = _binding_bridge_contract(capability=capability)
        detail["binding_bridge_contract"] = binding_contract
        if _is_unavailable_capability_status(status):
            detail["missing_capability_error"] = (
                _binding_missing_capability_error(
                    capability=capability,
                    status=status,
                )
            )
        else:
            detail["bridge_evidence_status"] = binding_contract[
                "contract_status"
            ]
    if capability == "datastore_record_upsert_batch":
        detail["orchestrator_contract"] = _datastore_batch_upsert_contract()
        if _is_unavailable_capability_status(status):
            detail["missing_capability_error"] = (
                _datastore_batch_missing_capability_error(status=status)
            )
        else:
            detail["bridge_evidence_status"] = (
                "schema_checked_batch_upsert_ready"
            )
    if capability == "datastore_strict_schema_validation":
        detail["strict_schema_contract"] = (
            _datastore_strict_schema_validation_contract()
        )
        detail["bridge_evidence_status"] = (
            "observed_strict_schema_validation_ready"
        )
    if capability == "scenario_interface_update":
        detail["scenario_interface_contract"] = (
            _scenario_interface_update_contract()
        )
        detail["bridge_evidence_status"] = "observed_interface_schedule_ready"
    if capability == "module_configuration_validation":
        detail["module_configuration_contract"] = (
            _module_configuration_validation_contract()
        )
        detail["bridge_evidence_status"] = (
            "observed_module_configuration_validation_ready"
        )
    if capability == "scenario_run_once":
        detail["run_once_contract"] = _scenario_run_once_contract()
        detail["bridge_evidence_status"] = "observed_run_once_execution_ready"
    if capability == "webhook_configuration_validation":
        detail["webhook_configuration_contract"] = (
            _webhook_configuration_validation_contract()
        )
        detail["bridge_evidence_status"] = (
            "observed_webhook_configuration_validation_ready"
        )
    return detail


def _make_mcp_capability_matrix() -> JsonObject:
    return {
        capability: _make_mcp_capability_detail(capability)
        for capability in sorted(MAKE_MCP_CAPABILITY_MATRIX)
    }


def _browser_validation_boundary(*, include_plan: bool) -> JsonObject:
    plan = make_live_browser_smoke_plan()
    payload: JsonObject = {
        "browser_validation_status": "offline_parity_no_browser_required",
        "live_canary_status": plan["live_canary_status"],
        "fully_automated_production_status": plan[
            "fully_automated_production_status"
        ],
        "live_canary_resource_creation_order": plan["resource_creation_order"],
        "live_canary_resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "live_canary_cleanup_semantics": plan["cleanup_semantics"],
        "owning_layer": "pancakes_offline_engine",
        "requires_operator_approval": False,
        "pancakes_executes_browser_automation": False,
        "pancakes_calls_make_live": False,
        "provider_api_call": False,
        "operation_credit_budget": plan["operation_credit_budget"],
        "mutation_scope": plan["mutation_scope"],
        "browser_gated_capabilities": (),
        "browser_visual_review_status": "proof_limitation_not_technical_blocker",
        "browser_visual_review_blocks_package": False,
        "proof_limitation": (
            "Browser visual review remains retained manual proof evidence; local package "
            "readiness is not technically blocked when offline parity and live canary "
            "evidence are ready."
        ),
        "offline_mirror_capabilities": (
            "scenario_auto_align",
            "scenario_module_error_inspection",
        ),
        "live_read_capabilities_needed": (
            "scenario_export",
            "scenario_inspect_modules",
        ),
        "live_write_capabilities_needed": ("scenario_import",),
        "smoke_plan_status": "retained_for_manual_live_review_only",
        "smoke_plan_included": include_plan,
        "raw_smoke_plan_available": True,
        "status_reason": (
            "Pancakes mirrors designer layout and module-error inspection locally; Make API "
            "roundtrip evidence shows browser auto-align is not required for package parity, "
            "and the destructive live canary creates Data Structure, Data Store, Webhook, "
            "then Scenario before cleanup."
        ),
    }
    if include_plan:
        payload["smoke_plan"] = plan
    return payload


def _capability_status(capability: str) -> str:
    return str(MAKE_MCP_CAPABILITY_MATRIX[capability])


def _is_unavailable_capability_status(status: str) -> bool:
    return status not in {
        "available",
        "offline_mirror",
        "operator_bridge_ready",
    }


def _capability_owning_layer(capability: str, status: str) -> str:
    if status == "offline_mirror":
        return "pancakes_offline_engine"
    if status == "operator_bridge_ready":
        return "make_api_bridge"
    if capability in {
        "connection_bind_to_module",
        "live_apply_package",
        "webhook_bind_to_module",
    }:
        return "make_api_bridge"
    if status == "available":
        return "make_mcp"
    if capability in {
        "datastore_record_upsert_batch",
        "connection_bind_to_module",
        "webhook_create_or_select",
        "webhook_bind_to_module",
        "live_apply_package",
    }:
        return "future_bridge"
    if status == "operator_manual":
        return "operator_manual_make_ui"
    return "make_mcp"


def _capability_fallback_strategy(capability: str, status: str) -> str:
    if capability in {
        "connection_bind_to_module",
        "live_apply_package",
        "webhook_bind_to_module",
    }:
        return "use_guarded_operator_live_bridge"
    if status == "available":
        return "use_make_mcp_tool"
    if status == "offline_mirror":
        return "use_pancakes_offline_mirror"
    if status == "operator_bridge_ready":
        return "use_guarded_operator_live_bridge"
    if status == "partial_composable":
        return "compose_after_operator_approval"
    if status == "missing_batch_orchestrator":
        return "compose_bounded_loop_after_operator_approval"
    if status == "operator_manual":
        return "operator_manual_make_ui"
    if capability.startswith("webhook_"):
        return "operator_manual_make_ui"
    if capability == "scenario_module_error_inspection":
        return "operator_manual_make_ui"
    if capability not in MINIMAL_IMPORT_CAPABILITIES:
        return "not_required_for_minimal_import"
    return "future_make_mcp_tool"


def _datastore_manifest_resources(
    *, scenario: Mapping[str, object]
) -> tuple[JsonObject, ...]:
    grouped: dict[str, JsonObject] = {}
    metadata_resources = _metadata_datastore_resources(scenario)
    for occurrence in _runtime_placeholder_occurrences(scenario):
        if occurrence["provider"] != "datastore":
            continue
        source = str(occurrence["source"])
        resource_key = _runtime_resource_key(source)
        group = grouped.setdefault(
            resource_key,
            {
                "resource_key": resource_key,
                "human_label": _human_label(resource_key, suffix="Data Store"),
                "provider": "datastore",
                "make_resource_kind": "datastore",
                "intended_operation": "create_or_select",
                "schema_fields": [],
                "schema_status": "unknown",
                "data_structure_status": "unknown_requires_schema_evidence",
                "data_structure_field_count": 0,
                "data_structure_confidence": "unknown",
                "data_structure_source_paths": (),
                "data_structure_source_path_count": 0,
                "returned_data_structure_source_path_count": 0,
                "hidden_data_structure_source_path_count": 0,
                "raw_data_structure_source_paths_available": False,
                "data_structure_requires_schema_evidence": True,
                "key_field": None,
                "key_field_status": "unknown_requires_key_evidence",
                "key_field_source_path": None,
                "source_json_pointer": None,
                "key_field_confidence": "unknown",
                "record_count": 0,
                "seed_records_available": False,
                "upsert_strategy": "live_upload_sequence",
                "overwrite_policy": "created_package_resources_only",
                "safety_notes": (
                    "Pancakes prepares this manifest locally; the live upload command creates "
                    "the Make Data Structure and Data Store before scenario import."
                ),
                "live_tool_required": "datastore_create",
                "required_live_capability": "datastore_create",
                "capability_status": _capability_status("datastore_create"),
                "fallback_strategy": _capability_fallback_strategy(
                    "datastore_create",
                    _capability_status("datastore_create"),
                ),
                "requires_live_make_mcp": True,
                "requires_operator_mapping": False,
                "auto_provisioned_by_live_upload": True,
                "manual_make_ui_required": False,
                "source": source,
                "example_node_ids": [],
            },
        )
        examples = cast("list[str]", group["example_node_ids"])
        node_id = str(occurrence["node_id"])
        if node_id not in examples and len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
    for resource_key, group in grouped.items():
        structure_evidence = _datastore_data_structure_evidence(
            scenario=scenario,
            resource_key=resource_key,
        )
        group.update(structure_evidence)
        key_evidence = _datastore_key_field_evidence(
            scenario=scenario, resource_key=resource_key
        )
        if key_evidence is not None:
            group.update(key_evidence)
        seed_records = _datastore_seed_records(
            metadata_resources.get(resource_key)
        )
        group["seed_records_available"] = bool(seed_records)
        group["record_count"] = len(seed_records)
        group["batch_upsert_plan"] = _datastore_batch_upsert_plan(
            resource=group,
            seed_records=seed_records,
        )
        group["requires_operator_mapping"] = False
        group["auto_provisioning_status"] = (
            "ready"
            if group["key_field"] is not None
            and group["data_structure_requires_schema_evidence"] is False
            else "blocked_missing_schema_or_key"
        )
    return tuple(
        sorted(grouped.values(), key=lambda item: str(item["resource_key"]))
    )


def _metadata_datastore_resources(
    scenario: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    metadata = scenario.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    manifest = cast("Mapping[str, object]", metadata).get("datastore_manifest")
    if not isinstance(manifest, dict):
        return {}
    raw_resources = cast("Mapping[str, object]", manifest).get("resources")
    if not isinstance(raw_resources, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    resources = cast("list[object]", raw_resources)
    for row in resources:
        if not isinstance(row, dict):
            continue
        resource_key = _optional_text(
            cast("Mapping[str, object]", row).get("resource_key")
        )
        if resource_key:
            result[resource_key] = cast("Mapping[str, object]", row)
    return result


def _datastore_seed_records(
    resource: Mapping[str, object] | None,
) -> tuple[JsonObject, ...]:
    if resource is None:
        return ()
    raw_records = resource.get("seed_records")
    if not isinstance(raw_records, list):
        return ()
    records = cast("list[object]", raw_records)
    return tuple(
        dict(cast("Mapping[str, object]", record))
        for record in records
        if isinstance(record, dict)
    )


def _datastore_batch_upsert_plan(
    *,
    resource: Mapping[str, object],
    seed_records: tuple[JsonObject, ...],
) -> JsonObject:
    capability_status = _capability_status("datastore_record_upsert_batch")
    record_count = len(seed_records)
    oversized = record_count > DATASTORE_BATCH_UPSERT_MAX_RECORDS
    operation_counts = _datastore_batch_operation_counts(seed_records)
    schema_fields = _text_list(resource.get("schema_fields"))
    unknown_record_fields = _datastore_batch_unknown_data_fields(
        seed_records=seed_records,
        schema_fields=schema_fields,
    )
    if record_count == 0:
        dry_run_status = "empty_batch"
    elif unknown_record_fields:
        dry_run_status = "blocked_unknown_record_fields"
    elif oversized:
        dry_run_status = "blocked_oversized_batch"
    else:
        dry_run_status = "dry_run_plan_ready"
    return {
        "contract_status": "schema_checked_batch_upsert_ready",
        "dry_run_status": dry_run_status,
        "apply_status": (
            "blocked_unknown_record_fields"
            if unknown_record_fields
            else "blocked_oversized_batch"
            if oversized
            else "blocked_missing_capability"
            if capability_status != "available"
            else "session_scoped_apply_ready"
        ),
        "required_live_capability": "datastore_record_upsert_batch",
        "required_live_capability_status": capability_status,
        "resource_key": resource["resource_key"],
        "key_field": resource.get("key_field"),
        "record_count": record_count,
        "max_batch_records": DATASTORE_BATCH_UPSERT_MAX_RECORDS,
        "returned_record_key_count": min(
            record_count, PROJECT_VIEW_DEFAULT_LIMIT
        ),
        "hidden_record_key_count": max(
            record_count - PROJECT_VIEW_DEFAULT_LIMIT, 0
        ),
        "record_keys": _datastore_batch_record_keys(
            seed_records=seed_records,
            key_field=_optional_text(resource.get("key_field")),
        ),
        "operation_counts": operation_counts,
        "schema_validation_status": (
            "passed"
            if not unknown_record_fields
            else "blocked_unknown_record_fields"
        ),
        "schema_field_count": len(schema_fields),
        "unknown_record_fields": unknown_record_fields,
        "unknown_record_field_count": len(unknown_record_fields),
        "operation_budget": {
            "max_records_per_batch": DATASTORE_BATCH_UPSERT_MAX_RECORDS,
            "max_retries_per_record": DATASTORE_BATCH_UPSERT_RETRY_LIMIT,
            "live_operation_budget": record_count,
            "apply_requires_operator_approval": False,
            "requires_session_scope": True,
        },
        "retry_policy": {
            "retry_transient_errors": True,
            "retry_limit": DATASTORE_BATCH_UPSERT_RETRY_LIMIT,
            "stop_on_schema_error": True,
            "stop_on_permission_error": True,
        },
        "rollback_policy": {
            "delete_created_records_only_with_session_scope": True,
            "overwrite_customer_data_without_approval": False,
            "preserve_pre_existing_customer_records": True,
            "cleanup_capability": "datastore_record_delete_batch",
        },
    }


def _datastore_batch_operation_counts(
    seed_records: tuple[JsonObject, ...],
) -> JsonObject:
    counts: JsonObject = {"create": 0, "update": 0, "upsert": 0}
    for record in seed_records:
        operation = _optional_text(record.get("operation")) or "upsert"
        normalized = operation if operation in counts else "upsert"
        counts[normalized] = _int_mapping_value(counts, normalized) + 1
    return counts


def _datastore_batch_record_keys(
    *,
    seed_records: tuple[JsonObject, ...],
    key_field: str | None,
) -> tuple[str, ...]:
    keys: list[str] = []
    for record in seed_records[:PROJECT_VIEW_DEFAULT_LIMIT]:
        key = _optional_text(record.get("key"))
        data = record.get("data")
        if key is None and key_field and isinstance(data, dict):
            key = _optional_text(
                cast("Mapping[str, object]", data).get(key_field)
            )
        keys.append(key or "<missing-key>")
    return tuple(keys)


def _datastore_batch_unknown_data_fields(
    *,
    seed_records: tuple[JsonObject, ...],
    schema_fields: tuple[str, ...],
) -> tuple[str, ...]:
    if not schema_fields:
        return ()
    allowed = set(schema_fields)
    unknown: list[str] = []
    for record in seed_records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        for key in cast("Mapping[object, object]", data):
            key_text = str(key)
            if key_text not in allowed and key_text not in unknown:
                unknown.append(key_text)
    return tuple(sorted(unknown))


def _datastore_data_structure_evidence(
    *,
    scenario: Mapping[str, object],
    resource_key: str,
) -> JsonObject:
    fields: list[str] = []
    source_paths: list[str] = []
    source_path_count = 0
    placeholder = f"{{{{runtime.datastore.{resource_key}}}}}"
    for module_path, module in _iter_modules(scenario):
        if _optional_text(module.get("module")) != "datastore:AddRecord":
            continue
        if placeholder not in tuple(_runtime_placeholder_values(module)):
            continue
        for container_name in ("mapper", "parameters"):
            container = module.get(container_name)
            if not isinstance(container, dict):
                continue
            data = cast("Mapping[str, object]", container).get("data")
            if not isinstance(data, dict):
                continue
            source_path_count += 1
            source_path = f"{module_path}.{container_name}.data"
            if (
                source_path not in source_paths
                and len(source_paths) < PROJECT_EXAMPLE_LIMIT
            ):
                source_paths.append(source_path)
            for key in cast("Mapping[object, object]", data):
                key_text = str(key)
                if key_text not in fields:
                    fields.append(key_text)
    if not fields:
        return {
            "schema_fields": [],
            "schema_status": "unknown",
            "data_structure_status": "unknown_requires_schema_evidence",
            "data_structure_field_count": 0,
            "data_structure_confidence": "unknown",
            "data_structure_source_paths": (),
            "data_structure_source_path_count": source_path_count,
            "returned_data_structure_source_path_count": 0,
            "hidden_data_structure_source_path_count": 0,
            "raw_data_structure_source_paths_available": bool(
                source_path_count
            ),
            "data_structure_requires_schema_evidence": True,
        }
    return {
        "schema_fields": fields,
        "schema_status": "known",
        "data_structure_status": "known_from_mapper_data",
        "data_structure_field_count": len(fields),
        "data_structure_confidence": "high",
        "data_structure_source_paths": tuple(source_paths),
        "data_structure_source_path_count": source_path_count,
        "returned_data_structure_source_path_count": len(source_paths),
        "hidden_data_structure_source_path_count": max(
            source_path_count - len(source_paths), 0
        ),
        "raw_data_structure_source_paths_available": True,
        "data_structure_requires_schema_evidence": False,
    }


def _datastore_key_field_evidence(
    *,
    scenario: Mapping[str, object],
    resource_key: str,
) -> JsonObject | None:
    """Infer a datastore key only from explicit mapper/project evidence.

    Returns:
        The computed value.
    """
    placeholder = f"{{{{runtime.datastore.{resource_key}}}}}"
    for module_path, module in _iter_modules(scenario):
        if _optional_text(module.get("module")) != "datastore:AddRecord":
            continue
        if placeholder not in tuple(_runtime_placeholder_values(module)):
            continue
        mapper = module.get("mapper")
        if not isinstance(mapper, dict):
            continue
        mapper_mapping = cast("Mapping[str, object]", mapper)
        key_value = mapper_mapping.get("key")
        if key_value is None:
            continue
        field_name = _datastore_key_field_from_mapper_key(
            key_value=key_value,
            data=mapper_mapping.get("data"),
        )
        if field_name is None:
            continue
        return {
            "key_field": field_name,
            "key_field_status": "inferred_from_mapper_key",
            "key_field_source_path": f"{module_path}.mapper.key",
            "source_json_pointer": f"{module_path}.mapper.key",
            "key_field_confidence": "high",
        }
    return None


def _datastore_key_field_from_mapper_key(
    *, key_value: object, data: object
) -> str | None:
    key_text = str(key_value)
    if isinstance(data, dict):
        for raw_field, raw_value in cast(
            "Mapping[object, object]", data
        ).items():
            field = str(raw_field)
            if field == key_text or str(raw_value) == key_text:
                return field
    identifier_match = re.fullmatch(
        r"\{\{\s*\d+\.([A-Za-z0-9_]+)\s*\}\}", key_text
    )
    if identifier_match is not None:
        return identifier_match.group(1)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_text):
        return key_text
    return None


def _connection_requirements(
    scenario: Mapping[str, object],
    *,
    include_paths: bool = False,
) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "provider": group["provider"],
            "field": group["field"],
            "source": group["source"],
            "projection_kind": group["projection_kind"],
            "live_tool_required": "connection_list_metadata",
            "required_live_capability": "connection_list_metadata",
            "capability_status": _capability_status("connection_list_metadata"),
            "requires_live_make_mcp": True,
            "requires_operator_mapping": False,
            "requires_client_connection": True,
            "provisioning_owner": "client_app_connection",
            "manual_make_ui_required": False,
            "example_node_ids": group["example_node_ids"],
            **(
                {"example_field_paths": group.get("example_field_paths", ())}
                if include_paths
                else {}
            ),
        }
        for group in cast(
            "tuple[JsonObject, ...]",
            _connection_binding_summary(
                scenario=scenario,
                output_mode="full" if include_paths else "compact",
            )["groups"],
        )
    )


def _runtime_resource_requirements(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    requirements: list[JsonObject] = []
    for group in cast(
        "tuple[JsonObject, ...]",
        _resource_binding_summary(scenario=scenario, output_mode="compact")[
            "groups"
        ],
    ):
        provider = str(group["provider"])
        live_tool_required = _live_tool_for_resource(provider)
        auto_provisioned = provider in {"datastore", "webhook"}
        requirements.append(
            {
                "provider": provider,
                "field": group["field"],
                "source": group["source"],
                "projection_kind": group["projection_kind"],
                "live_tool_required": live_tool_required,
                "required_live_capability": live_tool_required,
                "capability_status": _capability_status(live_tool_required),
                "fallback_strategy": _capability_fallback_strategy(
                    live_tool_required,
                    _capability_status(live_tool_required),
                ),
                "requires_live_make_mcp": True,
                "requires_operator_mapping": False,
                "requires_client_runtime_value": not auto_provisioned,
                "provisioning_owner": (
                    "pancakes_live_upload"
                    if auto_provisioned
                    else "client_app_runtime_input"
                ),
                "auto_provisioned_by_live_upload": auto_provisioned,
                "manual_make_ui_required": False,
                "manual_create_prompt_allowed": False,
                "example_node_ids": group["example_node_ids"],
            }
        )
    return tuple(requirements)


def _runtime_requirement_is_auto_provisioned(
    requirement: Mapping[str, object],
) -> bool:
    return bool(requirement.get("auto_provisioned_by_live_upload"))


def _runtime_resource_provisioning_summary(
    scenario: Mapping[str, object],
) -> JsonObject:
    requirements = _runtime_resource_requirements(scenario)
    auto_count = sum(
        1
        for requirement in requirements
        if _runtime_requirement_is_auto_provisioned(requirement)
    )
    client_value_count = len(requirements) - auto_count
    if not requirements:
        status = "not_required"
    elif client_value_count:
        status = "client_runtime_values_required"
    else:
        status = "auto_provisioned_by_live_upload"
    return {
        "status": status,
        "auto_provisioning_status": (
            "ready"
            if auto_count
            else "not_required"
            if not requirements
            else "not_applicable"
        ),
        "requirement_count": len(requirements),
        "auto_provisioned_count": auto_count,
        "client_runtime_value_count": client_value_count,
    }


def _binding_bridge_contract(*, capability: str) -> JsonObject:
    resource_kind = (
        "connection" if capability == "connection_bind_to_module" else "webhook"
    )
    resource_ref_field = (
        "connection_metadata_ref"
        if resource_kind == "connection"
        else "webhook_ref"
    )
    contract_status = "observed_live_bind_ready"
    observed_contract: JsonObject = {}
    if resource_kind == "connection":
        observed_contract = {
            "live_evidence": "make_mcp_connection_bind_lifecycle_shapes",
            "connection_type_name": "google-email",
            "target_module": "google-email:sendAnEmail",
            "bound_connection_id_path": "$.blueprint.flow[0].parameters.__IMTCONN__",
            "module_connection_target": "__IMTCONN__",
            "component_extraction_target_path": "$.connections[0].moduleTargets.__IMTCONN__",
            "target_scenario_active_required": False,
            "cleanup_invariant": "scratch_scenarios_count_0",
        }
    elif resource_kind == "webhook":
        observed_contract = {
            "live_evidence": "make_mcp_webhook_bind_lifecycle_shapes",
            "hook_type_name": "gateway-webhook",
            "target_module": "gateway:CustomWebHook",
            "bound_hook_id_path": "$.blueprint.flow[0].parameters.hook",
            "scenario_hook_id_path": "$.hookId",
            "hook_scenario_id_path": "$.scenarioId",
            "target_scenario_active_required": False,
            "cleanup_invariant": "scratch_hooks_count_0_and_scratch_scenarios_count_0",
        }
    return {
        "contract_status": contract_status,
        "resource_kind": resource_kind,
        "observed_binding_contract": observed_contract,
        "target_module_policy": "inactive_scratch_scenario_module_only",
        "dry_run_first": True,
        "requires_operator_approval": False,
        "requires_session_scope": True,
        "pancakes_executes_live_operations": True,
        "input_contract": {
            "project_id": "local_project_id",
            "package_id": "local_make_import_package_id",
            "target_scenario_id": "inactive_scratch_scenario_id",
            "target_module_id": "make_module_id_from_imported_scenario",
            resource_ref_field: f"operator_selected_{resource_kind}_metadata_reference",
            "dry_run": "boolean_default_true",
            "session_intent_id": "required_for_apply",
            "expected_export_fingerprint": "optional_post_bind_export_guard",
        },
        "forbidden_input_fields": (
            "credential_value",
            "api_key",
            "password",
            "access_token",
            "refresh_token",
            "secret",
        ),
        "apply_gates": (
            "dry_run_passed",
            "session_scope_present",
            "target_scenario_is_inactive_scratch",
            "resource_metadata_selected_without_secret_value",
            "operation_budget_confirmed",
            "post_bind_export_required",
        ),
        "blocked_states": (
            "missing_make_mcp_bind_tool",
            "missing_session_scope",
            "target_scenario_active_or_unknown",
            "credential_value_present",
            "post_bind_export_mismatch",
        ),
    }


def _binding_missing_capability_error(
    *, capability: str, status: str
) -> JsonObject:
    return {
        "status": "blocked",
        "error_code": "make_mcp_bind_capability_missing",
        "capability": capability,
        "capability_status": status,
        "reason": (
            "Make.com MCP does not expose a credential-free typed bind operation for this "
            "resource yet."
        ),
        "safe_fallback": _capability_fallback_strategy(capability, status),
        "retry_when": "a guarded bridge implements this contract or a direct Make.com MCP bind tool exists",
    }


def _datastore_batch_upsert_contract() -> JsonObject:
    return {
        "contract_status": "schema_checked_batch_upsert_ready",
        "live_evidence": (
            "make_api_existing_store_record_probe_shapes",
            "make_mcp_datastore_lifecycle_shapes",
            "make_mcp_datastore_strict_schema_validation_shapes",
        ),
        "dry_run_first": True,
        "requires_operator_approval": False,
        "requires_session_scope": True,
        "pancakes_executes_live_operations": True,
        "input_contract": {
            "project_id": "local_project_id",
            "resource_key": "local_datastore_manifest_resource_key",
            "target_datastore_ref": "operator_selected_datastore_metadata_reference",
            "records": "bounded_seed_records_without_secret_values",
            "dry_run": "boolean_default_true",
            "session_intent_id": "required_for_apply",
        },
        "max_batch_records": DATASTORE_BATCH_UPSERT_MAX_RECORDS,
        "retry_limit": DATASTORE_BATCH_UPSERT_RETRY_LIMIT,
        "operation_semantics": (
            "create records when no target key exists",
            "update records only when an existing target key is selected",
            "upsert means create-or-update by explicit key field",
        ),
        "disposable_lifecycle_contract": {
            "typed_tools": (
                "data_structures_create",
                "data_stores_create",
                "data_store_records_create",
                "data_store_records_update",
                "data_store_records_delete",
                "data_stores_delete",
                "data_structures_delete",
            ),
            "data_structure_spec_shape": (
                "name:string",
                "type:string",
                "required:bool",
            ),
            "cleanup_invariant": "data_stores_count_0_and_data_structures_count_0",
            "record_delete_confirmation": "Records have been deleted.",
            "store_delete_confirmation": "Data store has been deleted.",
            "structure_delete_confirmation": "Data structure has been deleted.",
        },
        "session_boundaries": (
            "delete_only_created_records_with_session_scope",
            "no_overwrite_customer_data_without_session_scope",
            "dry_run_plan_required_before_apply",
        ),
        "forbidden_input_fields": (
            "credential_value",
            "api_key",
            "password",
            "access_token",
            "refresh_token",
            "secret",
        ),
    }


def _datastore_strict_schema_validation_contract() -> JsonObject:
    return {
        "contract_status": "observed_strict_schema_validation_ready",
        "live_evidence": "make_mcp_datastore_strict_schema_validation_shapes",
        "mapped_live_tools": (
            "data_structures_create",
            "data_stores_create",
            "data_store_records_create",
            "data_store_records_delete",
        ),
        "strict_schema_policy": (
            "seed records must satisfy required fields and field types before batch upsert"
        ),
        "observed_rejections": (
            "missing_required_request_id",
            "invalid_number_amount",
        ),
        "cleanup_invariant": "data_stores_count_0_and_data_structures_count_0",
        "requires_operator_approval": True,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _offline_mirror_capability_contract(*, capability: str) -> JsonObject:
    if capability == "scenario_auto_align":
        return {
            "contract_status": "offline_mirror_ready",
            "live_web_dependency": False,
            "offline_engine": "blueprints.ast.plan_blueprint_layout",
            "live_evidence": "make_api_scenario_designer_roundtrip_shapes",
            "observed_make_behavior": "scenario_export_preserves_missing_designer_coordinates",
            "package_policy": "apply_local_layout_before_import_when_coordinates_are_missing",
        }
    if capability == "scenario_module_error_inspection":
        return {
            "contract_status": "offline_mirror_ready",
            "live_web_dependency": False,
            "offline_engine": "blueprints.validation + designer-message ingest",
            "live_evidence": (
                "make_api_scenario_designer_roundtrip_shapes",
                "make_mcp_module_requirement_extraction_shapes",
                "make_mcp_runtime_resource_requirement_extraction_shapes",
            ),
            "observed_make_behavior": (
                "scenario_export_does_not_inject_designer_messages; "
                "component_extraction_reports required account, hook, and Data Store targets "
                "even when isinvalid is false"
            ),
            "requirement_oracle": "extract_blueprint_components",
            "package_policy": "use_local_linter_and_imported_designer_messages_as_evidence",
        }
    return {
        "contract_status": "offline_mirror_ready",
        "live_web_dependency": False,
        "offline_engine": "pancakes",
        "live_evidence": "not_applicable",
    }


def _datastore_batch_missing_capability_error(*, status: str) -> JsonObject:
    return {
        "status": "blocked",
        "error_code": "make_mcp_datastore_batch_upsert_missing",
        "capability": "datastore_record_upsert_batch",
        "capability_status": status,
        "reason": (
            "Make.com MCP exposes record create/update primitives, but Pancakes has no guarded "
            "batch upsert orchestrator yet."
        ),
        "safe_fallback": _capability_fallback_strategy(
            "datastore_record_upsert_batch", status
        ),
    }


def _live_apply_plan() -> JsonObject:
    contract = _live_apply_capability_contract()
    return {
        "required_live_capability": "live_apply_package",
        "required_live_tool": "live_apply_package",
        "required_live_tool_status": _capability_status("live_apply_package"),
        "contract_status": contract["contract_status"],
        "capability_contract": contract,
        "requires_operator_approval": False,
        "permission_model": "runtime_api_token_session_scoped",
        "dry_run_first": True,
        "dry_run_required_before_live_write": True,
        "target_scenario_policy": contract["target_scenario_policy"],
        "scenario_mutation_contract": contract["scenario_mutation_contract"],
        "operation_budget": contract["operation_budget"],
        "resource_creation_order": MAKE_LIVE_RESOURCE_CREATION_ORDER,
        "resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "cleanup_semantics": MAKE_LIVE_CANARY_CLEANUP_SEMANTICS,
        "write_operations": (
            "create_data_structures",
            "create_data_stores_with_created_data_structure_ids",
            "create_webhooks",
            "bind_created_resource_ids_into_blueprint",
            "create_inactive_scratch_scenario_with_bound_blueprint",
            "set_scenario_interface_after_on_demand_schedule",
            "bind_client_supplied_connections",
            "bind_client_supplied_runtime_values",
            "delete_or_preserve_scratch_scenario_by_rollback_policy",
        ),
        "write_operation_capabilities": (
            "datastore_create",
            "webhook_create_or_select",
            "scenario_import",
            "scenario_interface_update",
            "connection_bind_to_module",
        ),
        "read_operations": (
            "list_scenarios",
            "list_datastores",
            "list_connection_metadata",
            "validate_module_configurations",
            "validate_webhook_configurations",
            "inspect_imported_modules",
            "export_blueprint_from_response_blueprint_path",
        ),
        "read_operation_capabilities": (
            "scenario_list",
            "datastore_list",
            "connection_list_metadata",
            "module_configuration_validation",
            "webhook_configuration_validation",
            "scenario_interface_update",
            "scenario_inspect_modules",
        ),
        "cost_runtime_warning": (
            "Run-once validation can consume Make operations and must be separately approved."
        ),
        "rollback_plan_ref": "rollback_plan",
        "rollback_required": True,
        "pancakes_executes_live_operations": True,
    }


def _live_apply_capability_contract() -> JsonObject:
    return {
        "contract_status": "observed_live_apply_ready",
        "live_evidence": "make_mcp_live_apply_package_roundtrip_shapes",
        "apply_toolchain": (
            "project.make package",
            "validate_blueprint_schema",
            "validate_module_configuration",
            "scenarios_create",
            "scenarios_update",
            "scenarios_set_interface",
            "scenarios_interface",
            "scenarios_get",
            "scenarios_delete",
        ),
        "target_scenario_policy": "inactive_scratch_scenario_only",
        "dry_run_first": True,
        "dry_run_required_before_live_write": True,
        "operator_approval_required_after_dry_run": False,
        "runtime_api_token_required_for_apply": True,
        "pancakes_executes_live_operations": True,
        "required_child_capabilities": LIVE_APPLY_PACKAGE_REQUIRED_CAPABILITIES,
        "dry_run_checks": (
            "package_zero_trace_passed",
            "blueprint_importability_ready",
            "scenario_mutation_request_contract_ready",
            "scenario_interface_update_contract_ready",
            "datastore_manifest_ready",
            "datastore_strict_schema_validation_contract_ready",
            "datastore_batch_upsert_plan_ready",
            "module_configuration_validation_contract_ready",
            "connection_metadata_resolvable",
            "connection_bind_contract_ready",
            "webhook_configuration_validation_contract_ready",
            "webhook_create_or_select_plan_ready",
            "webhook_bind_contract_ready",
            "rollback_plan_ready",
        ),
        "apply_sequence": (
            "create_data_structures_from_datastructure_json",
            "create_data_stores_from_datastore_json",
            "create_webhooks_from_webhook_json",
            "bind_created_resource_ids_into_blueprint",
            "create_inactive_scratch_scenario_with_json_string_blueprint",
            "switch_to_on_demand_before_setting_required_interface_inputs",
            "set_scenario_interface_when_package_declares_input_output",
            "validate_module_configurations_with_typed_make_validator",
            "validate_datastore_seed_records_against_strict_schema",
            "validate_webhook_defaults_before_create_or_select",
            "bind_connections_and_runtime_resources",
            "inspect_modules_and_export_blueprint",
            "compare_export_to_local_projection",
        ),
        "scenario_interface_contract": _scenario_interface_update_contract(),
        "module_configuration_contract": _module_configuration_validation_contract(),
        "datastore_strict_schema_contract": _datastore_strict_schema_validation_contract(),
        "webhook_configuration_contract": _webhook_configuration_validation_contract(),
        "scenario_mutation_contract": {
            "live_evidence": "make_api_scenario_mutation_contract_shapes",
            "create_endpoint": "POST /api/v2/scenarios",
            "create_request_fields": {
                "teamId": "int",
                "name": "string",
                "blueprint": "json_string",
                "scheduling": "json_string",
            },
            "create_id_path": "$.scenario.id",
            "list_endpoint": "GET /api/v2/scenarios?teamId={teamId}&limit=100",
            "export_endpoint": "GET /api/v2/scenarios/{scenarioId}/blueprint?draft=false",
            "export_blueprint_path": "$.response.blueprint",
            "delete_endpoint": "DELETE /api/v2/scenarios/{scenarioId}",
            "delete_id_path": "$.scenario",
            "activation_allowed": False,
            "run_once_allowed": False,
            "raw_scenario_id_persistence_allowed": False,
        },
        "rollback_capabilities": LIVE_APPLY_PACKAGE_ROLLBACK_CAPABILITIES,
        "operation_budget": {
            "dry_run_live_operation_budget": 0,
            "apply_live_mutation_budget": "operator_approved_explicit_budget_required",
            "run_once_operation_budget": 0,
            "activation_allowed": False,
        },
        "failure_policy": "stop_on_first_live_error_and_preserve_package_evidence",
    }


def _scenario_interface_update_contract() -> JsonObject:
    return {
        "contract_status": "observed_interface_schedule_ready",
        "live_evidence": "make_mcp_scenario_interface_schedule_shapes",
        "mapped_live_tools": (
            "scenarios_set_interface",
            "scenarios_interface",
            "scenarios_update",
        ),
        "required_input_schedule_policy": (
            "required scenario interface inputs are accepted only when scheduling.type is on-demand"
        ),
        "immediate_schedule_required_input_error": "required_inputs_need_on_demand_schedule",
        "export_contract": (
            "scenario_get returns blueprint.interface and blueprint.scheduling.type=on-demand"
        ),
        "activation_allowed": False,
        "run_once_allowed": False,
        "credential_value_transfer": False,
    }


def _module_configuration_validation_contract() -> JsonObject:
    return {
        "contract_status": "observed_module_configuration_validation_ready",
        "live_evidence": "make_mcp_module_configuration_validation_shapes",
        "mapped_live_tool": "validate_module_configuration",
        "validation_policy": (
            "typed module validation reports required mapper fields before scenario import"
        ),
        "observed_required_field": {
            "appName": "json",
            "appVersion": 1,
            "moduleName": "ParseJSON",
            "mapper_path": "json",
            "error_domain": "expect",
            "error_class": "field_is_mandatory",
        },
        "schema_response_contract": (
            "valid configurations can return default and expect schemas without live writes"
        ),
        "writes_performed": False,
        "activation_allowed": False,
        "run_once_allowed": False,
        "credential_value_transfer": False,
    }


def _scenario_run_once_contract() -> JsonObject:
    return {
        "contract_status": "observed_run_once_execution_ready",
        "live_evidence": "make_mcp_scenario_run_once_shapes",
        "mapped_live_tools": (
            "scenarios_activate",
            "scenarios_run",
            "executions_list",
            "scenarios_deactivate",
        ),
        "inactive_run_policy": "scenarios_run rejects inactive scenarios",
        "inactive_run_error": "scenario_not_activated",
        "response_contract": {
            "run_response": {"executionId": "hex_string", "status": 1},
            "execution_end": {
                "eventType": "EXECUTION_END",
                "status": 1,
                "operations": "positive_int",
                "centicredits": "positive_int",
            },
        },
        "requires_operator_approval": True,
        "activation_cleanup_required": True,
        "scratch_scenario_only": True,
        "live_provider_call_required": True,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _webhook_configuration_validation_contract() -> JsonObject:
    return {
        "contract_status": "observed_webhook_configuration_validation_ready",
        "live_evidence": "make_mcp_hook_configuration_validation_shapes",
        "mapped_live_tools": (
            "hook_config_get",
            "validate_hook_configuration",
        ),
        "type_name": "gateway-webhook",
        "required_default_fields": (
            "headers",
            "method",
            "stringify",
        ),
        "required_default_values": {
            "headers": False,
            "method": False,
            "stringify": False,
        },
        "validation_policy": (
            "gateway webhook creation should validate required default booleans before live create"
        ),
        "writes_performed": False,
        "activation_allowed": False,
        "run_once_allowed": False,
        "credential_value_transfer": False,
    }


def _rollback_plan(*, datastore_manifest: Mapping[str, object]) -> JsonObject:
    return {
        "status": "planned",
        "requires_operator_approval": True,
        "cleanup_live_capability": "datastore_record_delete_batch",
        "cleanup_live_capability_status": _capability_status(
            "datastore_record_delete_batch"
        ),
        "datastore_resource_count": datastore_manifest["resource_count"],
        "steps": (
            "remove_or_disable_imported_scenario_if_requested",
            "delete_seed_records_only_when_created_by_this_package",
            "leave pre-existing client resources untouched unless explicitly confirmed",
        ),
    }


def _operator_checklist() -> tuple[str, ...]:
    return (
        "Review package zero-trace result before live import.",
        "Provide the Make API token only at live upload runtime.",
        "Let the upload command create Data Structure, Data Store, Webhook, then Scenario.",
        "Confirm required Slack, Google Email, or other app connections already exist.",
        "Bind runtime app values from the web session without storing secrets.",
        "Keep the scenario inactive until live parity export comparison passes.",
    )


def _pdf_report_inputs(*, note_coverage: Mapping[str, object]) -> JsonObject:
    missing_notes = _int_mapping_value(
        note_coverage,
        "missing_module_note_count",
    ) + _int_mapping_value(note_coverage, "missing_connection_note_count")
    status = "blocked_missing_notes" if missing_notes else "ready"
    return {
        "pdf_report_generator_available": True,
        "pdf_report_inputs_status": status,
        "citation_map_status": status,
        "module_note_count": note_coverage["present_module_note_count"],
        "connection_note_count": note_coverage["present_connection_note_count"],
        "required_module_note_count": note_coverage[
            "missing_module_note_count"
        ],
        "required_connection_note_count": note_coverage[
            "missing_connection_note_count"
        ],
        "raw_citation_map_available": True,
    }


def _runtime_resource_key(source: str) -> str:
    normalized = source.strip("{} ").strip()
    if normalized.startswith("runtime.datastore."):
        return normalized.removeprefix("runtime.datastore.")
    return normalized.rsplit(".", maxsplit=1)[-1]


def _human_label(value: str, *, suffix: str) -> str:
    return f"{value.replace('_', ' ').strip().title()} {suffix}".strip()


def _live_tool_for_resource(provider: str) -> str:
    if provider == "datastore":
        return "datastore_create"
    if provider == "webhook":
        return "webhook_create_or_select"
    if provider == "slack":
        return "scenario_module_error_inspection"
    return "scenario_module_error_inspection"


def _make_artifact_projection(scenario: Mapping[str, object]) -> JsonObject:
    return {
        "artifact_format": "make_blueprint_json",
        "scenario": _projected_scenario(scenario),
    }


def _roundtrip_validation_payload(
    *,
    scenario: Mapping[str, object],
    projection: Mapping[str, object],
) -> JsonObject:
    projected_scenario = projection.get("scenario")
    projected_mapping = (
        cast("Mapping[str, object]", projected_scenario)
        if isinstance(projected_scenario, dict)
        else cast("Mapping[str, object]", {})
    )
    source_known = _known_roundtrip_modules(scenario)
    source_unknown = _unknown_roundtrip_modules(scenario)
    projected_by_id = _roundtrip_modules_by_id(projected_mapping)
    missing_known_node_ids = tuple(
        node_id
        for node_id in sorted(source_known)
        if node_id not in projected_by_id
    )
    field_losses = tuple(
        loss
        for node_id, source_module in sorted(source_known.items())
        for loss in _roundtrip_field_losses(
            node_id=node_id,
            source_module=source_module,
            projected_module=projected_by_id.get(node_id),
        )
    )
    unknown_traceable = all(
        node_id in projected_by_id for node_id in source_unknown
    )
    status = (
        "passed"
        if not missing_known_node_ids and not field_losses and unknown_traceable
        else "blocked"
    )
    return {
        "roundtrip_validation_status": status,
        "roundtrip_semantic_equivalence_status": (
            "semantically_equivalent"
            if status == "passed"
            else "semantic_gap_detected"
        ),
        "roundtrip_importability_status": "importable"
        if status == "passed"
        else "blocked",
        "known_node_count": len(source_known),
        "preserved_known_node_count": len(source_known)
        - len(missing_known_node_ids),
        "lost_known_node_count": len(missing_known_node_ids),
        "missing_known_node_ids": missing_known_node_ids,
        "known_field_loss_count": len(field_losses),
        "known_field_losses": field_losses,
        "quarantined_unknown_node_count": len(source_unknown),
        "quarantined_unknowns_traceable": unknown_traceable,
    }


def _known_roundtrip_modules(
    scenario: Mapping[str, object],
) -> dict[str, JsonObject]:
    return {
        node_id: module
        for node_id, module in _roundtrip_modules_by_id(scenario).items()
        if _translated_module(_optional_text(module.get("module")) or "")[
            "change"
        ]
        != "pass_through"
    }


def _unknown_roundtrip_modules(
    scenario: Mapping[str, object],
) -> dict[str, JsonObject]:
    return {
        node_id: module
        for node_id, module in _roundtrip_modules_by_id(scenario).items()
        if _translated_module(_optional_text(module.get("module")) or "")[
            "change"
        ]
        == "pass_through"
    }


def _roundtrip_modules_by_id(
    scenario: Mapping[str, object],
) -> dict[str, JsonObject]:
    modules: dict[str, JsonObject] = {}
    for _path, module in _iter_import_module_payloads(
        _flow_from_mapping(scenario), "flow"
    ):
        node_id = _node_id(module)
        if node_id is not None:
            modules[node_id] = module
    return modules


def _roundtrip_field_losses(
    *,
    node_id: str,
    source_module: Mapping[str, object],
    projected_module: Mapping[str, object] | None,
) -> Iterator[JsonObject]:
    if projected_module is None:
        return
    for field in ("parameters", "mapper", "routes", "onerror"):
        if field in source_module and field not in projected_module:
            yield {
                "node_id": node_id,
                "field": field,
                "reason": "Known source field missing after Make blueprint projection.",
            }


def _projected_scenario(scenario: Mapping[str, object]) -> JsonObject:
    projected = cast("JsonObject", _json_copy(scenario))
    projected["flow"] = _projected_flow(_flow_from_mapping(scenario))
    metadata = projected.get("metadata")
    projected_metadata = _projected_customer_safe_metadata(metadata)
    if projected_metadata:
        projected["metadata"] = projected_metadata
    else:
        _ = projected.pop("metadata", None)
    _apply_projected_designer_layouts(projected=projected, source=scenario)
    return projected


def _projected_customer_safe_metadata(metadata: object) -> JsonObject:
    projected: JsonObject = {
        "version": 1,
        "instant": False,
        "scenario": dict(MAKE_NATIVE_SCENARIO_SETTINGS_DEFAULTS),
        "designer": {"orphans": []},
    }
    if not isinstance(metadata, dict):
        return projected
    source = cast("Mapping[str, object]", metadata)
    instant = source.get("instant")
    if isinstance(instant, bool):
        projected["instant"] = instant
    source_scenario = source.get("scenario")
    if isinstance(source_scenario, dict):
        projected["scenario"] = _projected_make_scenario_settings(
            cast("Mapping[str, object]", source_scenario)
        )
    notes = source.get("notes")
    if not isinstance(notes, list | tuple):
        return projected
    native_notes = _projected_make_native_notes(cast("Sequence[object]", notes))
    if native_notes:
        projected["notes"] = native_notes
        designer = cast("JsonObject", projected["designer"])
        designer["notes"] = cast("list[JsonObject]", _json_copy(native_notes))
    return projected


def _projected_make_scenario_settings(
    source: Mapping[str, object],
) -> JsonObject:
    settings = dict(MAKE_NATIVE_SCENARIO_SETTINGS_DEFAULTS)
    for key, default in MAKE_NATIVE_SCENARIO_SETTINGS_DEFAULTS.items():
        value = source.get(key)
        if isinstance(default, bool):
            if isinstance(value, bool):
                settings[key] = value
        elif isinstance(default, int):
            if isinstance(value, int) and not isinstance(value, bool):
                settings[key] = value
        elif key == "slots" and (
            value is None or isinstance(value, dict | list)
        ):
            settings[key] = _json_copy(cast("object", value))
    return settings


def _projected_make_native_notes(notes: Sequence[object]) -> list[JsonObject]:
    projected: list[JsonObject] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        native_note = _projected_make_native_note(
            cast("Mapping[str, object]", note)
        )
        if native_note is not None:
            projected.append(native_note)
    return projected


def _projected_make_native_note(
    note: Mapping[str, object],
) -> JsonObject | None:
    content = _projected_make_note_content(note)
    module_ids = _projected_make_note_module_ids(note)
    if content is None or not module_ids:
        return None
    return {
        "content": content,
        "isFilterNote": note.get("isFilterNote") is True,
        "metadata": {"color": _projected_make_note_color(note)},
        "moduleIds": module_ids,
    }


def _projected_make_note_content(note: Mapping[str, object]) -> str | None:
    native_content = _optional_text(
        note.get("content") or note.get("html") or note.get("text")
    )
    if native_content is not None:
        return native_content

    title = _optional_text(note.get("title"))
    sections = note.get("sections")
    paragraphs: list[str] = []
    if title is not None:
        paragraphs.append(f"<h2>{html.escape(title)}</h2>")
    pdf_index = _projected_make_note_pdf_index(note)
    if pdf_index is not None:
        paragraphs.append(
            f"<p><strong>PDF index:</strong> {html.escape(pdf_index)}</p>"
        )
    if isinstance(sections, dict):
        for raw_label, raw_text in cast(
            "Mapping[object, object]", sections
        ).items():
            label = _optional_text(raw_label)
            text = _optional_text(raw_text)
            if label is not None and text is not None:
                paragraphs.append(
                    f"<p><strong>{html.escape(label)}:</strong> {html.escape(text)}</p>"
                )
    elif (body := _optional_text(note.get("body"))) is not None:
        paragraphs.extend(
            f"<p>{html.escape(line.strip())}</p>"
            for line in body.splitlines()
            if line.strip()
        )
    return "".join(paragraphs) or None


def _projected_make_note_pdf_index(note: Mapping[str, object]) -> str | None:
    citation_ref = _optional_text(note.get("citation_ref"))
    if citation_ref is not None:
        return citation_ref
    inferred = _note_citation_ref(note)
    return inferred if "node" not in inferred.casefold() else None


def _projected_make_note_color(note: Mapping[str, object]) -> str:
    metadata = note.get("metadata")
    if isinstance(metadata, dict):
        color = _optional_text(
            cast("Mapping[str, object]", metadata).get("color")
        )
        if color is not None and color.upper() in MAKE_NOTE_COLOR_PALETTE:
            return color.upper()
    color = _optional_text(note.get("color"))
    if color is not None and color.upper() in MAKE_NOTE_COLOR_PALETTE:
        return color.upper()
    note_kind = _normalized_note_kind(note)
    if note_kind == "connection":
        return MAKE_CONNECTION_NOTE_COLOR
    return MAKE_NATIVE_NOTE_COLOR


def _projected_make_note_module_ids(note: Mapping[str, object]) -> list[object]:
    raw_module_ids = note.get("moduleIds")
    if isinstance(raw_module_ids, list | tuple):
        return _normalized_make_module_ids(
            cast("Sequence[object]", raw_module_ids)
        )

    raw_ids: list[object] = []
    source = _optional_node_id(note.get("source_node_id"))
    target = _optional_node_id(
        note.get("target_node_id") or note.get("node_id")
    )
    title = _optional_text(note.get("title")) or ""
    if target is None and title.startswith("MOD-"):
        target = (
            title.removeprefix("MOD-")
            .split(maxsplit=1)[0]
            .split("|", maxsplit=1)[0]
        )
    if (source is None or target is None) and title.startswith("CONN-"):
        parts = (
            title.removeprefix("CONN-")
            .split(maxsplit=1)[0]
            .split("|", maxsplit=1)[0]
        )
        if "-" in parts:
            source, target = parts.split("-", maxsplit=1)
    if source is not None:
        raw_ids.append(source)
    if target is not None:
        raw_ids.append(target)
    return _normalized_make_module_ids(raw_ids)


def _normalized_make_module_ids(raw_ids: Sequence[object]) -> list[object]:
    normalized: list[object] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        if isinstance(raw_id, bool):
            continue
        text = _optional_text(raw_id)
        if text is None or text in seen:
            continue
        seen.add(text)
        if text.isdigit() and int(text) > 0:
            normalized.append(int(text))
        else:
            normalized.append(text)
    return normalized


def _apply_projected_designer_layouts(
    *,
    projected: JsonObject,
    source: Mapping[str, object],
) -> None:
    root = parse_make_ast(cast("JsonObject", _json_copy(source)))
    plan = plan_make_blueprint_layout(root)
    for layout in plan.layouts:
        node = _projected_node_at_path(projected, layout.source_path)
        if node is None:
            continue
        metadata = _ensure_projected_mapping(node, "metadata")
        designer = _ensure_projected_mapping(metadata, "designer")
        designer["x"] = layout.x
        designer["y"] = layout.y


def _projected_node_at_path(
    projected: Mapping[str, object],
    path: Sequence[object],
) -> JsonObject | None:
    current: object = projected
    for part in path:
        if isinstance(part, str):
            if not isinstance(current, dict):
                return None
            current = cast("Mapping[str, object]", current).get(part)
            continue
        if isinstance(part, int):
            if not isinstance(current, list):
                return None
            current_list = cast("list[object]", current)
            if not 0 <= part < len(current_list):
                return None
            current = current_list[part]
            continue
        return None
    return cast("JsonObject", current) if isinstance(current, dict) else None


def _projected_flow(flow: Sequence[object]) -> list[object]:
    projected: list[object] = []
    for item in flow:
        if not isinstance(item, dict):
            projected.append(_projected_value(item))
            continue
        item_mapping = cast("Mapping[str, object]", item)
        source_module = _optional_text(item_mapping.get("module")) or ""
        module = cast(
            "JsonObject",
            _projected_value(item_mapping, module_token=source_module),
        )
        translated = _translated_module(source_module)
        if translated["to"]:
            module["module"] = translated["to"]
        if translated["version"] is not None:
            module["version"] = translated["version"]
        _normalize_projected_module_shape(
            module=module, source_module=source_module
        )
        if translated["change"] == "trigger_projected":
            _ = module.setdefault("mapper", {})
        for route in _routes_for_module(module):
            route["flow"] = _projected_flow(_flow_from_mapping(route))
            _lower_projected_route_filter(route)
        for handler in _handlers_for_module(module):
            if "flow" in handler:
                handler["flow"] = _projected_flow(_flow_from_mapping(handler))
        projected.append(module)
    return projected


def _normalize_projected_module_shape(
    *, module: JsonObject, source_module: str
) -> None:
    """Project local ergonomic module shapes to Make's importable module parameter schema."""
    projected_module_name = (
        _optional_text(module.get("module")) or source_module
    )
    if projected_module_name == "slack:CreateMessage":
        _normalize_projected_slack_create_message(module)
    if projected_module_name == "google-email:sendAnEmail":
        _normalize_projected_google_email_send(module)


def _normalize_projected_slack_create_message(module: JsonObject) -> None:
    parameters = _ensure_projected_mapping(module, "parameters")
    mapper = _ensure_projected_mapping(module, "mapper")
    account = parameters.pop("account", None)
    if account is not None and "__IMTCONN__" not in parameters:
        parameters["__IMTCONN__"] = account
    channel = parameters.pop("channel", None)
    if channel is not None and "channel" not in mapper:
        mapper["channel"] = channel
    if "channel" in mapper and "channelWType" not in mapper:
        mapper["channelWType"] = "manualy"


def _normalize_projected_google_email_send(module: JsonObject) -> None:
    parameters = _ensure_projected_mapping(module, "parameters")
    mapper = _ensure_projected_mapping(module, "mapper")
    account = parameters.pop("account", None)
    if account is not None and "__IMTCONN__" not in parameters:
        parameters["__IMTCONN__"] = account
    for mapper_key in ("to", "subject", "html", "content", "bodyType"):
        value = parameters.pop(mapper_key, None)
        if value is not None and mapper_key not in mapper:
            mapper[mapper_key] = value
    html = mapper.pop("html", None)
    if html is not None and "content" not in mapper:
        mapper["content"] = html
    if "content" in mapper and "bodyType" not in mapper:
        mapper["bodyType"] = "rawHtml"


def _ensure_projected_mapping(module: JsonObject, key: str) -> JsonObject:
    value = module.get(key)
    if isinstance(value, dict):
        return cast("JsonObject", value)
    replacement: JsonObject = {}
    module[key] = replacement
    return replacement


def _lower_projected_route_filter(route: JsonObject) -> None:
    """Move route-wrapper filters to the first route module for Make import schema validity."""
    raw_filter = route.pop("filter", None)
    if not isinstance(raw_filter, dict):
        return
    route_filter = _projected_make_filter(
        cast("Mapping[str, object]", raw_filter)
    )
    flow = route.get("flow")
    if not isinstance(flow, list) or not flow or not isinstance(flow[0], dict):
        return
    first_node = cast("JsonObject", flow[0])
    first_node["filter"] = _merge_projected_make_filters(
        node_filter=first_node.get("filter"),
        route_filter=route_filter,
    )


def _projected_make_filter(raw_filter: Mapping[str, object]) -> JsonObject:
    payload = cast("JsonObject", _json_copy(raw_filter))
    expression = _projected_filter_expression(raw_filter)
    typed_conditions = (
        _projected_conditions_from_expression(expression)
        if expression
        else None
    )
    if typed_conditions is not None:
        payload["conditions"] = typed_conditions
    _ = payload.pop("condition", None)
    _ = payload.pop("expression", None)
    return payload


def _projected_filter_expression(
    raw_filter: Mapping[str, object],
) -> str | None:
    for key in ("expression", "condition"):
        value = raw_filter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    conditions = raw_filter.get("conditions")
    if isinstance(conditions, dict):
        value = cast("Mapping[str, object]", conditions).get("expression")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _projected_conditions_from_expression(
    expression: str,
) -> list[object] | None:
    groups: list[object] = []
    for raw_group in re.split(r"\s+or\s+", expression, flags=re.IGNORECASE):
        group_conditions: list[object] = []
        for raw_term in re.split(r"\s+and\s+", raw_group, flags=re.IGNORECASE):
            condition = _projected_condition_from_expression_term(
                raw_term.strip()
            )
            if condition is None:
                return None
            group_conditions.append(condition)
        if group_conditions:
            groups.append(group_conditions)
    return groups or None


def _projected_condition_from_expression_term(term: str) -> JsonObject | None:
    bare_path_match = re.fullmatch(r"(\{\{.+?}})", term)
    if bare_path_match is not None:
        return {"a": bare_path_match.group(1), "o": "exist"}
    exists_match = re.fullmatch(
        r"(\{\{.+?}})\s+exists", term, flags=re.IGNORECASE
    )
    if exists_match is not None:
        return {"a": exists_match.group(1), "o": "exist"}
    empty_match = re.fullmatch(
        r"empty\((\{\{.+?}})\)", term, flags=re.IGNORECASE
    )
    if empty_match is not None:
        return {"a": empty_match.group(1), "o": "notexist"}
    not_empty_match = re.fullmatch(
        r"not\s+empty\((\{\{.+?}})\)", term, flags=re.IGNORECASE
    )
    if not_empty_match is not None:
        return {"a": not_empty_match.group(1), "o": "exist"}
    numeric_match = re.fullmatch(
        r"(\{\{.+?}})\s*(>=|>|<=|<|=|==)\s*([0-9]+(?:\.[0-9]+)?)", term
    )
    if numeric_match is not None:
        return {
            "a": numeric_match.group(1),
            "o": _projected_numeric_operator(numeric_match.group(2)),
            "b": numeric_match.group(3),
        }
    text_match = re.fullmatch(
        r"(\{\{.+?}})\s*(=|==|!=)\s*(\"[^\"]*\"|'[^']*'|[A-Za-z0-9_.-]+)", term
    )
    if text_match is not None:
        raw_value = text_match.group(3)
        operator = (
            "text:notequal" if text_match.group(2) == "!=" else "text:equal"
        )
        return {
            "a": text_match.group(1),
            "o": operator,
            "b": raw_value[1:-1]
            if raw_value.startswith(("'", '"'))
            else raw_value,
        }
    contains_match = re.fullmatch(
        r"contains\((\{\{.+?}}),\s*(\"[^\"]*\"|'[^']*')\)",
        term,
        flags=re.IGNORECASE,
    )
    if contains_match is not None:
        return {
            "a": contains_match.group(1),
            "o": "text:contains",
            "b": contains_match.group(2)[1:-1],
        }
    return None


def _projected_numeric_operator(operator: str) -> str:
    return {
        ">": "number:greater",
        ">=": "number:greaterorequal",
        "<": "number:less",
        "<=": "number:lessorequal",
        "=": "number:equal",
        "==": "number:equal",
    }[operator]


def _merge_projected_make_filters(
    *,
    node_filter: object,
    route_filter: JsonObject,
) -> JsonObject:
    if not isinstance(node_filter, dict):
        return route_filter
    typed_node_filter = cast("JsonObject", node_filter)
    node_conditions = _projected_condition_groups(
        typed_node_filter.get("conditions")
    )
    route_conditions = _projected_condition_groups(
        route_filter.get("conditions")
    )
    merged = cast("JsonObject", _json_copy(typed_node_filter))
    if node_conditions and route_conditions:
        merged["conditions"] = [
            node_conditions[0] + route_conditions[0],
            *node_conditions[1:],
        ]
    elif route_conditions:
        merged["conditions"] = route_conditions
    merged["name"] = _projected_merged_filter_name(
        node_name=typed_node_filter.get("name"),
        route_name=route_filter.get("name"),
    )
    return merged


def _projected_condition_groups(value: object) -> list[list[object]]:
    if not isinstance(value, list):
        return []
    return [
        list(cast("list[object]", group))
        for group in cast("list[object]", value)
        if isinstance(group, list)
    ]


def _projected_merged_filter_name(
    *, node_name: object, route_name: object
) -> str:
    names = tuple(
        name.strip()
        for name in (node_name, route_name)
        if isinstance(name, str) and name.strip()
    )
    return " + ".join(dict.fromkeys(names)) if names else "route filter"


def _projected_value(
    value: object,
    *,
    field_path: str = "",
    module_token: str = "",
) -> object:
    if isinstance(value, str):
        field_name = field_path.rsplit(".", maxsplit=1)[-1].split(
            "[", maxsplit=1
        )[0]

        def replace_placeholder(match: re.Match[str]) -> str:
            source = match.group(0).strip()
            if _is_make_connection_binding(
                field_name=field_name, source=source
            ):
                return "__IMTCONN__"
            return source

        return RUNTIME_PLACEHOLDER_PATTERN.sub(replace_placeholder, value)
    if isinstance(value, dict):
        return {
            str(key): _projected_value(
                child,
                field_path=f"{field_path}.{key}" if field_path else str(key),
                module_token=module_token,
            )
            for key, child in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, list | tuple):
        return [
            _projected_value(
                child,
                field_path=f"{field_path}[{index}]",
                module_token=module_token,
            )
            for index, child in enumerate(cast("Sequence[object]", value))
        ]
    return _json_copy(value)


def _translated_module(module_token: str) -> JsonObject:
    app_slug, _, internal_name = module_token.partition(":")
    normalized_internal = internal_name.casefold()
    if app_slug == "slack" and normalized_internal == "actioncreatemessage":
        return {
            "from": module_token,
            "to": "slack:CreateMessage",
            "change": "module_translated",
            "version": 4,
        }
    if app_slug == "datastore" and normalized_internal == "addrecord":
        return {
            "from": module_token,
            "to": module_token,
            "change": "version_injected",
            "version": 2,
        }
    if app_slug == "google-email" and normalized_internal == "actionsendemail":
        return {
            "from": module_token,
            "to": "google-email:sendAnEmail",
            "change": "catalog_manifest_backed",
            "version": 4,
        }
    if module_token == BASIC_ROUTER_MODULE:
        return {
            "from": module_token,
            "to": module_token,
            "change": "builtin_manifest_backed",
            "version": 1,
        }
    if app_slug == "gateway" and normalized_internal == "customwebhook":
        return {
            "from": module_token,
            "to": module_token,
            "change": "trigger_projected",
            "version": 1,
        }
    return {
        "from": module_token,
        "to": module_token,
        "change": "pass_through",
        "version": None,
    }


def _module_translation_summary(
    *,
    scenario: Mapping[str, object],
    output_mode: str,
) -> JsonObject:
    groups: dict[tuple[str, str, str, object], JsonObject] = {}
    total_nodes = 0
    for _path, module in _iter_modules(scenario):
        total_nodes += 1
        module_token = _optional_text(module.get("module")) or ""
        translated = _translated_module(module_token)
        key = (
            str(translated["from"]),
            str(translated["to"]),
            str(translated["change"]),
            translated["version"],
        )
        group = groups.setdefault(
            key,
            {
                "from": translated["from"],
                "to": translated["to"],
                "change": translated["change"],
                "version": translated["version"],
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_node_ids"])
        node_id = _node_id(module)
        if node_id is not None and len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
    rows = tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["from"]),
            ),
        )
    )
    visible_rows = (
        rows
        if output_mode in {"full", "debug"}
        else rows[:PROJECT_VIEW_DEFAULT_LIMIT]
    )
    return {
        "total_nodes": total_nodes,
        "groups": visible_rows,
        "hidden_group_count": max(len(rows) - len(visible_rows), 0),
        "raw_translations_available": bool(rows),
    }


def _connection_binding_summary(
    *,
    scenario: Mapping[str, object],
    output_mode: str,
) -> JsonObject:
    groups: dict[tuple[str, str, str, str], JsonObject] = {}
    binding_count = 0
    for occurrence in _runtime_placeholder_occurrences(scenario):
        field = str(occurrence["field"])
        source = str(occurrence["source"])
        if not _is_make_connection_binding(field_name=field, source=source):
            continue
        binding_count += 1
        provider = _runtime_provider(source)
        key = (provider, field, source, "make_connection_placeholder")
        group = groups.setdefault(
            key,
            {
                "provider": provider,
                "field": field,
                "source": source,
                "projection_kind": "make_connection_placeholder",
                "projection": "__IMTCONN__",
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_node_ids"])
        node_id = str(occurrence["node_id"])
        if node_id not in examples and len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
        if output_mode in {"full", "debug"}:
            path_examples = cast(
                "list[str]", group.setdefault("example_field_paths", [])
            )
            field_path = str(occurrence["field_path"])
            if (
                field_path not in path_examples
                and len(path_examples) < PROJECT_EXAMPLE_LIMIT
            ):
                path_examples.append(field_path)
    for path, module in _iter_modules(scenario):
        module_token = _optional_text(module.get("module")) or ""
        required_targets = MODULE_REQUIRED_CONNECTION_TARGETS.get(
            module_token, ()
        )
        if not required_targets:
            continue
        raw_parameters = module.get("parameters")
        parameters: Mapping[str, object] = (
            cast("Mapping[str, object]", raw_parameters)
            if isinstance(raw_parameters, dict)
            else cast("Mapping[str, object]", {})
        )
        for field, provider in required_targets:
            if parameters.get(field):
                continue
            binding_count += 1
            source = f"{module_token}.{field}"
            key = (
                provider,
                field,
                source,
                "make_connection_required_by_module",
            )
            group = groups.setdefault(
                key,
                {
                    "provider": provider,
                    "field": field,
                    "source": source,
                    "projection_kind": "make_connection_required_by_module",
                    "projection": field,
                    "count": 0,
                    "example_node_ids": [],
                    "live_evidence": "make_mcp_module_requirement_extraction_shapes",
                },
            )
            group["count"] = _int_mapping_value(group, "count") + 1
            examples = cast("list[str]", group["example_node_ids"])
            node_id = _node_id(module)
            if (
                node_id is not None
                and node_id not in examples
                and len(examples) < PROJECT_EXAMPLE_LIMIT
            ):
                examples.append(node_id)
            if output_mode in {"full", "debug"}:
                path_examples = cast(
                    "list[str]", group.setdefault("example_field_paths", [])
                )
                field_path = f"{path}.parameters.{field}"
                if (
                    field_path not in path_examples
                    and len(path_examples) < PROJECT_EXAMPLE_LIMIT
                ):
                    path_examples.append(field_path)
    rows = tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["provider"]),
            ),
        )
    )
    visible_rows = (
        rows
        if output_mode in {"full", "debug"}
        else rows[:PROJECT_VIEW_DEFAULT_LIMIT]
    )
    return {
        "binding_count": binding_count,
        "groups": visible_rows,
        "hidden_group_count": max(len(rows) - len(visible_rows), 0),
        "raw_bindings_available": bool(rows),
    }


def _resource_binding_summary(
    *,
    scenario: Mapping[str, object],
    output_mode: str,
) -> JsonObject:
    groups: dict[tuple[str, str, str, str], JsonObject] = {}
    binding_count = 0
    for occurrence in _runtime_placeholder_occurrences(scenario):
        field = str(occurrence["field"])
        source = str(occurrence["source"])
        if _is_make_connection_binding(field_name=field, source=source):
            continue
        binding_count += 1
        provider = _runtime_provider(source)
        key = (provider, field, source, "runtime_resource_placeholder")
        group = groups.setdefault(
            key,
            {
                "provider": provider,
                "field": field,
                "source": source,
                "projection_kind": "runtime_resource_placeholder",
                "projection": source,
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_node_ids"])
        node_id = str(occurrence["node_id"])
        if node_id not in examples and len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
        if output_mode in {"full", "debug"}:
            path_examples = cast(
                "list[str]", group.setdefault("example_field_paths", [])
            )
            field_path = str(occurrence["field_path"])
            if (
                field_path not in path_examples
                and len(path_examples) < PROJECT_EXAMPLE_LIMIT
            ):
                path_examples.append(field_path)
    for path, module in _iter_modules(scenario):
        module_token = _optional_text(module.get("module")) or ""
        required_targets = MODULE_REQUIRED_RUNTIME_RESOURCE_TARGETS.get(
            module_token, ()
        )
        if not required_targets:
            continue
        raw_parameters = module.get("parameters")
        parameters: Mapping[str, object] = (
            cast("Mapping[str, object]", raw_parameters)
            if isinstance(raw_parameters, dict)
            else cast("Mapping[str, object]", {})
        )
        for field, provider, resource_type in required_targets:
            if parameters.get(field):
                continue
            binding_count += 1
            source = f"{module_token}.{field}"
            key = (
                provider,
                field,
                source,
                "runtime_resource_required_by_module",
            )
            group = groups.setdefault(
                key,
                {
                    "provider": provider,
                    "field": field,
                    "source": source,
                    "projection_kind": "runtime_resource_required_by_module",
                    "projection": field,
                    "resource_type": resource_type,
                    "count": 0,
                    "example_node_ids": [],
                    "live_evidence": "make_mcp_runtime_resource_requirement_extraction_shapes",
                },
            )
            group["count"] = _int_mapping_value(group, "count") + 1
            examples = cast("list[str]", group["example_node_ids"])
            node_id = _node_id(module)
            if (
                node_id is not None
                and node_id not in examples
                and len(examples) < PROJECT_EXAMPLE_LIMIT
            ):
                examples.append(node_id)
            if output_mode in {"full", "debug"}:
                path_examples = cast(
                    "list[str]", group.setdefault("example_field_paths", [])
                )
                field_path = f"{path}.parameters.{field}"
                if (
                    field_path not in path_examples
                    and len(path_examples) < PROJECT_EXAMPLE_LIMIT
                ):
                    path_examples.append(field_path)
    rows = tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["provider"]),
            ),
        )
    )
    visible_rows = (
        rows
        if output_mode in {"full", "debug"}
        else rows[:PROJECT_VIEW_DEFAULT_LIMIT]
    )
    return {
        "binding_count": binding_count,
        "groups": visible_rows,
        "hidden_group_count": max(len(rows) - len(visible_rows), 0),
        "raw_bindings_available": bool(rows),
    }


def _is_make_connection_binding(*, field_name: str, source: str) -> bool:
    normalized_source = source.strip("{} ").casefold()
    if normalized_source.startswith("runtime.connection."):
        return True
    return (
        field_name.casefold() in MAKE_CONNECTION_FIELD_NAMES
        and "__imtconn__" in normalized_source
    )


def _pass_through_unknown_module_count(scenario: Mapping[str, object]) -> int:
    return sum(
        1
        for _path, module in _iter_modules(scenario)
        if _translated_module(_optional_text(module.get("module")) or "")[
            "change"
        ]
        == "pass_through"
    )


def _zero_trace_for_projection(projection: Mapping[str, object]) -> JsonObject:
    report = validate_make_public_safe_artifact(
        projection,
        artifact_kind="make_blueprint_projection",
    )
    payload = zero_trace_payload(
        status="passed" if report.safe else "failed",
        leak_count=report.issue_count,
    )
    payload["public_safe_artifact_boundary"] = (
        make_public_safe_artifact_report_payload(report)
    )
    return payload


def _verification_context(
    *,
    profile: str,
    scenario: Mapping[str, object],
) -> JsonObject:
    summary = _scenario_summary(scenario)
    runtime_counts = _runtime_setup_counts(scenario)
    structure_findings = list(_structure_findings(scenario))
    local_linter_findings = _local_linter_smoke_findings(scenario)
    note_coverage = _note_coverage(scenario)
    zero_trace = _zero_trace_for_projection(_make_artifact_projection(scenario))
    module_count = _int_mapping_value(summary, "module_count")
    make_import_status = (
        "ready" if module_count > 0 and not structure_findings else "blocked"
    )
    notes_missing_count = _int_mapping_value(
        note_coverage, "missing_module_note_count"
    ) + _int_mapping_value(
        note_coverage,
        "missing_connection_note_count",
    )
    zero_trace_failed = zero_trace["zero_trace_status"] == "failed"
    handoff_status = (
        "blocked"
        if profile == "handoff_test"
        and (notes_missing_count or zero_trace_failed)
        else "ready"
        if profile == "handoff_test"
        else "not_evaluated_for_profile"
    )
    native_parity_status = (
        "blocked" if profile == "parity_fixture" else "not_evaluated"
    )
    blocking_findings = list(structure_findings)
    if make_import_status == "blocked" and not blocking_findings:
        blocking_findings.append(
            _finding(
                surface="make_import",
                severity="error",
                code="make_import.empty_graph",
                message="A Make import candidate needs at least one module.",
            )
        )
    if profile == "handoff_test" and notes_missing_count:
        blocking_findings.append(
            _finding(
                surface="client_handoff",
                severity="error",
                code="client_handoff.notes_missing",
                message="Client handoff requires useful module and connection notes.",
                count=notes_missing_count,
            )
        )
    if profile in ZERO_TRACE_BLOCKING_VERIFY_PROFILES and zero_trace_failed:
        blocking_findings.append(
            _finding(
                surface="zero_trace",
                severity="error",
                code="zero_trace.private_trace",
                message=(
                    "Rendered artifact contains private metadata or runtime placeholders."
                ),
                count=_int_mapping_value(zero_trace, "leak_count"),
            )
        )
    if profile == "parity_fixture":
        blocking_findings.append(
            _finding(
                surface="native_parity",
                severity="warning",
                code="native_parity.evidence_missing",
                message="Native re-export parity evidence is not attached to this local draft.",
            )
        )
    statuses = ValidationSurfaceStatuses(
        structural_validation_status="valid"
        if not structure_findings
        else "invalid",
        make_import_validation_status=make_import_status,
        client_handoff_validation_status=handoff_status,
        runtime_setup_validation_status="required"
        if runtime_counts.item_count
        else "not_required",
        scenario_tests_status="not_required",
        native_parity_validation_status=native_parity_status,
    )
    zero_trace_blocking_count = (
        _int_mapping_value(zero_trace, "leak_count")
        if profile == "handoff_test" and zero_trace_failed
        else 0
    )
    handoff_blocking = (
        notes_missing_count + zero_trace_blocking_count
        if handoff_status == "blocked"
        else 0
    )
    error_handler_count = _int_mapping_value(summary, "error_handler_count")
    embedded_checks_status = (
        "configured" if error_handler_count else "not_configured"
    )
    lineage_status = "passed" if not structure_findings else "failed"
    connection_binding_summary = _connection_binding_summary(
        scenario=scenario, output_mode="compact"
    )
    datastore_manifest = _datastore_manifest(
        scenario=scenario, output_mode="compact"
    )
    package_status = (
        "ready"
        if make_import_status == "ready"
        and zero_trace["zero_trace_status"] == "passed"
        else "blocked"
    )
    live_requirements_summary = _make_mcp_live_requirements_summary()
    full_live_validation_status = (
        "blocked_missing_capabilities"
        if live_requirements_summary[
            "full_live_validation_required_missing_count"
        ]
        else "ready"
    )
    connection_mapping_status = (
        "client_app_connections_required"
        if _int_mapping_value(connection_binding_summary, "binding_count")
        else "not_required"
    )
    resource_mapping_status = _runtime_resource_provisioning_summary(scenario)[
        "status"
    ]
    minimal_import_package_status = (
        "ready"
        if package_status == "ready"
        and live_requirements_summary["minimal_import_required_missing_count"]
        == 0
        else "blocked"
    )
    live_preflight_status = (
        "ready"
        if (
            profile == "live_preflight"
            and package_status == "ready"
            and full_live_validation_status == "ready"
        )
        else "ready_with_gaps"
        if profile == "live_preflight" and package_status == "ready"
        else "not_evaluated_for_profile"
        if profile != "live_preflight"
        else "blocked"
    )
    handoff_risk_summary: JsonObject
    if profile == "handoff_test":
        handoff_risk_summary = {
            "risk_level": "blocked" if handoff_blocking else "clear",
            "finding_surface": "client_handoff",
            "blocking_error_count": handoff_blocking,
            "missing_module_note_count": note_coverage[
                "missing_module_note_count"
            ],
            "missing_connection_note_count": note_coverage[
                "missing_connection_note_count"
            ],
            "zero_trace_status": zero_trace["zero_trace_status"],
            "zero_trace_blocking_count": zero_trace_blocking_count,
        }
    else:
        handoff_risk_summary = {
            "risk_level": "not_evaluated_for_profile",
            "finding_surface": "client_handoff",
            "blocking_error_count": 0,
            "advisory_missing_note_count": notes_missing_count,
            "missing_module_note_count": note_coverage[
                "missing_module_note_count"
            ],
            "missing_connection_note_count": note_coverage[
                "missing_connection_note_count"
            ],
            "items": ("Handoff notes are not required for import_test.",),
        }
    return {
        "statuses": statuses,
        "blocking_findings": tuple(blocking_findings),
        "grouped_findings": _grouped_findings(blocking_findings),
        "local_linter_status": (
            "blocked"
            if structure_findings
            else "passed_with_advisory_findings"
            if local_linter_findings
            else "passed"
        ),
        "local_linter_findings": local_linter_findings,
        "note_coverage": note_coverage,
        "zero_trace": zero_trace["zero_trace"],
        "zero_trace_status": zero_trace["zero_trace_status"],
        "zero_trace_reason": zero_trace["zero_trace_reason"],
        "zero_trace_surface": "rendered_preview_artifact",
        "leak_count": zero_trace["leak_count"],
        "scenario_behavior_status": "local_only_not_live_make_runtime_truth",
        "scenario_embedded_checks_status": embedded_checks_status,
        "local_lineage_invariants_status": lineage_status,
        "live_make_runtime_status": "not_evaluated",
        "error_handler_count": error_handler_count,
        "package_status": package_status,
        "minimal_import_package_status": minimal_import_package_status,
        "full_live_validation_status": full_live_validation_status,
        "make_mcp_live_requirements_status": (
            live_requirements_summary["status"]
            if profile == "live_preflight"
            else "not_evaluated_for_profile"
        ),
        "make_mcp_live_requirements_summary": live_requirements_summary,
        "datastore_manifest_status": datastore_manifest["status"],
        "connection_mapping_status": connection_mapping_status,
        "resource_mapping_status": resource_mapping_status,
        "live_preflight_status": live_preflight_status,
        "live_canary_status": _make_live_canary_contract()["status"],
        "live_resource_creation_order": MAKE_LIVE_RESOURCE_CREATION_ORDER,
        "live_resource_creation_order_human": MAKE_LIVE_RESOURCE_CREATION_ORDER_HUMAN,
        "live_canary_cleanup_semantics": MAKE_LIVE_CANARY_CLEANUP_SEMANTICS,
        "make_mcp_capabilities": _make_mcp_capability_matrix(),
        "make_mcp_capability_details": _make_mcp_capability_details(),
        "live_apply_plan": _live_apply_plan(),
        "browser_validation_status": (
            "offline_parity_no_browser_required"
            if profile in {"live_preflight", "parity_fixture"}
            else "not_evaluated_for_profile"
        ),
        "browser_validation_boundary": _browser_validation_boundary(
            include_plan=False
        ),
        "datastore_manifest": datastore_manifest,
        "client_handoff_status": handoff_status,
        "handoff_risk_summary": handoff_risk_summary,
        "structural_validation_status": statuses.structural_validation_status,
        "make_import_validation_status": statuses.make_import_validation_status,
        "client_handoff_validation_status": statuses.client_handoff_validation_status,
        "runtime_setup_validation_status": statuses.runtime_setup_validation_status,
        "scenario_tests_status": statuses.scenario_tests_status,
        "native_parity_validation_status": statuses.native_parity_validation_status,
    }


def _local_linter_smoke_findings(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    findings: list[JsonObject] = []
    for path, module in _iter_modules(scenario):
        node_id = _node_id(module)
        if node_id is not None:
            findings.append(
                {
                    "surface": "nodes",
                    "severity": "info",
                    "code": "node.present",
                    "node_id": node_id,
                    "path": path,
                    "message": f"Node {node_id} is addressable for local verification.",
                }
            )
    for module, route_index, route in _iter_routes(scenario):
        filter_value = route.get("filter")
        if not isinstance(filter_value, dict):
            continue
        node_id = _node_id(module)
        findings.append(
            {
                "surface": "filters",
                "severity": "info",
                "code": "filter.present",
                "node_id": node_id,
                "route_index": route_index,
                "filter_name": _optional_text(
                    cast("Mapping[str, object]", filter_value).get("name")
                ),
                "message": f"Route filter {route_index} is available for local verification.",
            }
        )
    findings.extend(
        {
            "surface": "placeholders",
            "severity": "info",
            "code": "placeholder.runtime_mapping_required",
            "node_id": occurrence["node_id"],
            "field_path": occurrence["field_path"],
            "placeholder": occurrence["source"],
            "message": "Runtime placeholder is explicit and operator-mappable.",
        }
        for occurrence in _runtime_placeholder_occurrences(scenario)
    )
    findings.extend(
        {
            "surface": "notes",
            "severity": "info",
            "code": "note.present",
            "note_kind": note.get("note_kind"),
            "node_id": note.get("target_node_id") or note.get("node_id"),
            "source_node_id": note.get("source_node_id"),
            "target_node_id": note.get("target_node_id"),
            "message": "Handoff note is attached to the local AST.",
        }
        for note in _scenario_notes(scenario)
    )
    return tuple(findings[:PROJECT_VIEW_MAX_LIMIT])


def _structure_findings(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    findings: list[JsonObject] = []
    flow = scenario.get("flow")
    if not isinstance(flow, list):
        findings.append(
            _finding(
                surface="structure",
                severity="error",
                code="structure.flow_missing",
                message="Scenario root must contain a flow array.",
            )
        )
    seen: set[str] = set()
    duplicates: set[str] = set()
    missing_id_count = 0
    for path, module in _iter_modules(scenario):
        node_id = _node_id(module)
        if node_id is None:
            missing_id_count += 1
            findings.append(
                _finding(
                    surface="structure",
                    severity="error",
                    code="structure.node_id_missing",
                    message=f"Module at {path} has no stable node id.",
                )
            )
            continue
        if node_id in seen:
            duplicates.add(node_id)
        seen.add(node_id)
    findings.extend(
        _finding(
            surface="structure",
            severity="error",
            code="structure.node_id_duplicate",
            message=f"Node id {node_id} appears more than once.",
        )
        for node_id in sorted(duplicates)
    )
    if missing_id_count and len(findings) > PROJECT_VIEW_DEFAULT_LIMIT:
        findings.append(
            _finding(
                surface="structure",
                severity="error",
                code="structure.node_id_missing_hidden",
                message="Additional modules without ids were omitted from compact findings.",
                count=missing_id_count,
            )
        )
    return tuple(findings[:PROJECT_VIEW_DEFAULT_LIMIT])


def _finding(
    *,
    surface: str,
    severity: str,
    code: str,
    message: str,
    count: int = 1,
) -> JsonObject:
    return {
        "surface": surface,
        "severity": severity,
        "code": code,
        "message": message,
        "count": count,
    }


def _grouped_findings(
    findings: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    groups: dict[tuple[str, str], JsonObject] = {}
    for finding in findings:
        surface = str(finding.get("surface") or "unknown")
        code = str(finding.get("code") or "unknown")
        key = (surface, code)
        group = groups.setdefault(
            key,
            {
                "surface": surface,
                "code": code,
                "count": 0,
                "examples": [],
            },
        )
        group["count"] = _int_mapping_value(
            group, "count"
        ) + _int_mapping_value(finding, "count")
        examples = cast("list[str]", group["examples"])
        if len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(str(finding.get("message") or code))
    return tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["surface"]),
            ),
        )
    )


def _note_coverage(scenario: Mapping[str, object]) -> JsonObject:
    modules = tuple(_iter_modules(scenario))
    links = tuple(_derive_links(scenario))
    notes = _scenario_notes(scenario)
    module_targets = _module_note_targets(notes)
    connection_targets = _connection_note_targets(notes)
    section_validation = _note_section_validation(notes)
    redaction_evidence = _note_redaction_evidence(notes)
    section_issue_count = _int_mapping_value(
        section_validation, "finding_count"
    )
    redaction_issue_count = _int_mapping_value(
        redaction_evidence, "finding_count"
    )
    missing_module_ids = tuple(
        node_id
        for _path, module in modules
        if (node_id := _node_id(module)) is not None
        and node_id not in module_targets
    )
    semantic_connections = _semantic_handoff_connections(links)
    missing_connections = tuple(
        connection
        for connection in semantic_connections
        if connection not in connection_targets
    )
    grouped_missing = _grouped_missing_notes(
        scenario=scenario,
        missing_module_ids=missing_module_ids,
        missing_connections=missing_connections,
    )
    status = (
        "passed"
        if not missing_module_ids
        and not missing_connections
        and section_issue_count == 0
        and redaction_issue_count == 0
        else "failed"
    )
    return {
        "status": status,
        "required_module_note_count": len(modules),
        "required_connection_note_count": len(semantic_connections),
        "present_module_note_count": len(module_targets),
        "present_connection_note_count": len(connection_targets),
        "missing_module_note_count": len(missing_module_ids),
        "missing_connection_note_count": len(missing_connections),
        "note_section_validation_status": section_validation["status"],
        "note_section_issue_count": section_issue_count,
        "note_section_validation": section_validation,
        "note_redaction_status": redaction_evidence["status"],
        "note_redaction_issue_count": redaction_issue_count,
        "redaction_evidence": redaction_evidence,
        "grouped_missing_notes": grouped_missing,
        "quality_contract": _note_quality_contract(),
        "next_queries": (
            _next_query(
                tool="project.view",
                arguments={
                    "project_id": "<id>",
                    "surface": "notes",
                    "output_mode": "full",
                },
                reason="Inspect exact note rows and raw missing note evidence.",
            ),
        ),
    }


def _note_section_validation(
    notes: Sequence[Mapping[str, object]],
) -> JsonObject:
    findings: list[JsonObject] = []
    checked_note_count = 0
    for index, note in enumerate(notes):
        note_kind = _normalized_note_kind(note)
        required_sections = _required_note_sections(note_kind)
        if not required_sections:
            findings.append(
                {
                    "code": "notes.section_unknown_kind",
                    "note_index": index,
                    "citation_ref": _note_citation_ref(note),
                    "message": "Note must be a module or connection note before handoff.",
                }
            )
            continue
        checked_note_count += 1
        sections = _note_sections(note, required_sections=required_sections)
        missing_sections = tuple(
            section for section in required_sections if section not in sections
        )
        weak_sections = tuple(
            section
            for section, text in sections.items()
            if section in required_sections
            and len(text.strip()) < NOTE_SECTION_MIN_CHARACTERS
        )
        if missing_sections or weak_sections:
            findings.append(
                {
                    "code": "notes.required_sections_missing_or_weak",
                    "note_index": index,
                    "citation_ref": _note_citation_ref(note),
                    "note_kind": note_kind,
                    "missing_sections": missing_sections,
                    "weak_sections": weak_sections,
                    "message": "Client handoff notes need every required functional section.",
                }
            )
    return {
        "status": "passed" if not findings else "failed",
        "checked_note_count": checked_note_count,
        "finding_count": len(findings),
        "findings": tuple(findings[:PROJECT_VIEW_DEFAULT_LIMIT]),
        "hidden_finding_count": max(
            len(findings) - PROJECT_VIEW_DEFAULT_LIMIT, 0
        ),
        "required_sections": {
            "module": NOTE_MODULE_REQUIRED_SECTIONS,
            "connection": NOTE_CONNECTION_REQUIRED_SECTIONS,
        },
    }


def _note_redaction_evidence(
    notes: Sequence[Mapping[str, object]],
) -> JsonObject:
    findings: list[JsonObject] = []
    class_counts: dict[str, int] = {}
    for index, note in enumerate(notes):
        text = "\n".join(_note_text_values(note))
        normalized = text.casefold().replace("\\", "/")
        classes: set[str] = set()
        if NOTE_SECRET_LIKE_PATTERN.search(text):
            classes.add("secret_like_value")
        if (
            NOTE_LOCAL_PATH_PATTERN.search(text)
            or "repos/" in normalized
            or "source/" in normalized
        ):
            classes.add("local_path")
        if "{{runtime." in normalized or "__imtconn__" in normalized:
            classes.add("runtime_placeholder")
        if any(marker in normalized for marker in NOTE_REDACTION_MARKERS):
            classes.add("private_implementation_reference")
        if not classes:
            continue
        for class_name in classes:
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
        findings.append(
            {
                "code": "notes.redaction_unsafe",
                "note_index": index,
                "citation_ref": _note_citation_ref(note),
                "classes": tuple(sorted(classes)),
                "message": (
                    "Note contains non-customer-facing material; rewrite without secrets, "
                    "local paths, prompts, internal graph/linter logic, or industrial details."
                ),
            }
        )
    return {
        "status": "passed" if not findings else "failed",
        "surface": "project_notes",
        "checked_note_count": len(notes),
        "finding_count": len(findings),
        "class_counts": dict(sorted(class_counts.items())),
        "findings": tuple(findings[:PROJECT_VIEW_DEFAULT_LIMIT]),
        "hidden_finding_count": max(
            len(findings) - PROJECT_VIEW_DEFAULT_LIMIT, 0
        ),
        "proof": (
            "Notes were scanned for secret-like values, runtime placeholders, local paths, "
            "prompts, and private implementation references."
        ),
        "redacted_values_returned": False,
        "customer_manual_boundary": "functional_documentation_only",
    }


def _normalized_note_kind(note: Mapping[str, object]) -> str:
    note_kind = (_optional_text(note.get("note_kind")) or "").casefold()
    title = (_optional_text(note.get("title")) or "").casefold()
    if note_kind == "connection" or title.startswith("conn-"):
        return "connection"
    if note_kind == "module" or title.startswith("mod-"):
        return "module"
    if (
        note.get("source_node_id") is not None
        and note.get("target_node_id") is not None
    ):
        return "connection"
    if (
        note.get("target_node_id") is not None
        or note.get("node_id") is not None
    ):
        return "module"
    return "unknown"


def _required_note_sections(note_kind: str) -> tuple[str, ...]:
    if note_kind == "module":
        return NOTE_MODULE_REQUIRED_SECTIONS
    if note_kind == "connection":
        return NOTE_CONNECTION_REQUIRED_SECTIONS
    return ()


def _note_sections(
    note: Mapping[str, object],
    *,
    required_sections: tuple[str, ...],
) -> dict[str, str]:
    sections_value = note.get("sections")
    sections: dict[str, str] = {}
    if isinstance(sections_value, dict):
        for key, value in cast(
            "Mapping[object, object]", sections_value
        ).items():
            if isinstance(key, str) and isinstance(value, str):
                sections[key.strip()] = value.strip()
    body = _optional_text(note.get("body") or note.get("content")) or ""
    for section in required_sections:
        if section in sections:
            continue
        text = _body_section_value(
            body=body, section=section, sections=required_sections
        )
        if text:
            sections[section] = text
    return sections


def _body_section_value(
    *, body: str, section: str, sections: tuple[str, ...]
) -> str | None:
    if not body:
        return None
    alternatives = "|".join(re.escape(item) for item in sections)
    pattern = re.compile(
        rf"(?:^|\n)\s*{re.escape(section)}\s*:\s*(.*?)(?=\n\s*(?:{alternatives})\s*:|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(body)
    if match is None:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _note_text_values(value: object) -> tuple[str, ...]:
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            values.append(str(key))
            values.extend(_note_text_values(item))
    elif isinstance(value, list | tuple):
        sequence = cast("Sequence[object]", value)
        for item in sequence:
            values.extend(_note_text_values(item))
    return tuple(values)


def _redacted_notes_for_output(
    notes: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    return tuple(
        cast("JsonObject", _redacted_note_value(dict(note))) for note in notes
    )


def _redacted_note_value(value: object) -> object:
    if isinstance(value, str):
        return (
            "[redacted:unsafe_note_text]"
            if _note_text_is_unsafe(value)
            else value
        )
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            str(key): _redacted_note_value(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list | tuple):
        sequence = cast("Sequence[object]", value)
        return [_redacted_note_value(item) for item in sequence]
    return value


def _note_text_is_unsafe(text: str) -> bool:
    normalized = text.casefold().replace("\\", "/")
    return (
        NOTE_SECRET_LIKE_PATTERN.search(text) is not None
        or NOTE_LOCAL_PATH_PATTERN.search(text) is not None
        or "repos/" in normalized
        or "source/" in normalized
        or "{{runtime." in normalized
        or "__imtconn__" in normalized
        or any(marker in normalized for marker in NOTE_REDACTION_MARKERS)
    )


def _missing_note_plan(
    *,
    scenario: Mapping[str, object],
    limit: int = PROJECT_VIEW_DEFAULT_LIMIT,
) -> JsonObject:
    coverage = _note_coverage(scenario)
    items = _missing_note_plan_items(scenario)
    returned_items = items[:limit]
    section_issue_count = _int_mapping_value(
        coverage, "note_section_issue_count"
    )
    redaction_issue_count = _int_mapping_value(
        coverage, "note_redaction_issue_count"
    )
    status = "ready"
    if items:
        status = "blocked_missing_notes"
    elif section_issue_count:
        status = "blocked_note_sections"
    elif redaction_issue_count:
        status = "blocked_note_redaction"
    return {
        "status": status,
        "missing_note_count": len(items),
        "returned_missing_note_count": len(returned_items),
        "hidden_missing_note_count": max(len(items) - len(returned_items), 0),
        "note_section_issue_count": section_issue_count,
        "note_redaction_issue_count": redaction_issue_count,
        "items": returned_items,
        "citation_ref_patterns": {
            "module": "NOTE-MOD-<target_node_id>",
            "connection": "NOTE-CONN-<source_node_id>-<target_node_id>",
        },
        "quality_contract": _note_quality_contract(),
        "tool": "project.edit",
        "surface": "notes",
        "operation": "generate_missing" if items else "modify",
        "compact": len(items) > len(returned_items),
    }


def _missing_note_plan_items(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    modules = tuple(_iter_modules(scenario))
    links = tuple(_derive_links(scenario))
    notes = _scenario_notes(scenario)
    module_targets = _module_note_targets(notes)
    connection_targets = _connection_note_targets(notes)
    module_items = tuple(
        cast(
            "JsonObject",
            {
                "note_kind": "module",
                "citation_ref": f"NOTE-MOD-{node_id}",
                "target_node_id": node_id,
                "title": f"MOD-{node_id} {module.get('module') or 'module'!s}",
                "required_pattern": "NOTE-MOD-<target_node_id>",
            },
        )
        for _path, module in modules
        if (node_id := _node_id(module)) is not None
        and node_id not in module_targets
    )
    connection_items = tuple(
        cast(
            "JsonObject",
            {
                "note_kind": "connection",
                "citation_ref": f"NOTE-CONN-{source_id}-{target_id}",
                "source_node_id": source_id,
                "target_node_id": target_id,
                "title": f"CONN-{source_id}-{target_id}",
                "required_pattern": "NOTE-CONN-<source_node_id>-<target_node_id>",
            },
        )
        for source_id, target_id in _semantic_handoff_connections(links)
        if (source_id, target_id) not in connection_targets
    )
    return (*module_items, *connection_items)


def _generated_missing_notes(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    modules = tuple(_iter_modules(scenario))
    links = tuple(_derive_links(scenario))
    notes = _scenario_notes(scenario)
    module_targets = _module_note_targets(notes)
    connection_targets = _connection_note_targets(notes)
    semantic_connections = _semantic_handoff_connections(links)
    incoming_counts: dict[str, int] = {}
    outgoing_counts: dict[str, int] = {}
    for source_id, target_id in semantic_connections:
        outgoing_counts[source_id] = outgoing_counts.get(source_id, 0) + 1
        incoming_counts[target_id] = incoming_counts.get(target_id, 0) + 1
    modules_by_id = {
        node_id: module
        for _path, module in modules
        if (node_id := _node_id(module)) is not None
    }
    generated: list[JsonObject] = []
    for node_id, module in modules_by_id.items():
        if node_id in module_targets:
            continue
        generated.append(
            _generated_module_note(
                node_id=node_id,
                module=module,
                incoming_count=incoming_counts.get(node_id, 0),
                outgoing_count=outgoing_counts.get(node_id, 0),
            )
        )
    for source_id, target_id in semantic_connections:
        if (source_id, target_id) in connection_targets:
            continue
        generated.append(
            _generated_connection_note(
                source_id=source_id,
                target_id=target_id,
                source_label=_module_label_for_note(
                    modules_by_id.get(source_id)
                ),
                target_label=_module_label_for_note(
                    modules_by_id.get(target_id)
                ),
            )
        )
    return tuple(generated)


def _generated_module_note(
    *,
    node_id: str,
    module: Mapping[str, object],
    incoming_count: int,
    outgoing_count: int,
) -> JsonObject:
    label = _module_label_for_note(module)
    sections = {
        "Purpose": f"Runs the {label} step as node {node_id} in the customer workflow.",
        "Input": (
            f"Receives mapped data from {incoming_count} upstream step(s) and the configured Make fields needed by this module."
            if incoming_count
            else "Starts the workflow from the configured trigger or schedule and receives the initial business bundle."
        ),
        "Output": (
            f"Produces mapped output for {outgoing_count} downstream step(s) in the customer workflow."
            if outgoing_count
            else "Completes this branch by performing the configured action or recording the final result."
        ),
        "Operator check": (
            "Confirm the module account, required fields, and customer-owned runtime selections "
            "are configured in Make before handoff."
        ),
    }
    return {
        "note_kind": "module",
        "target_node_id": node_id,
        "citation_ref": f"NOTE-MOD-{node_id}",
        "title": f"MOD-{node_id} | {label}",
        "sections": sections,
        "body": _note_sections_body(sections),
        "generation_status": "generated_from_project_state",
    }


def _generated_connection_note(
    *,
    source_id: str,
    target_id: str,
    source_label: str,
    target_label: str,
) -> JsonObject:
    sections = {
        "Handoff": (
            f"Moves the workflow from node {source_id} ({source_label}) to node {target_id} "
            f"({target_label}) so the next step can continue processing."
        ),
        "Data contract": (
            "Keep the business identifiers and mapped fields needed by the target step available "
            "across this handoff."
        ),
        "Failure signal": (
            "If required mapped fields are missing, malformed, or blocked by a filter, pause "
            "activation and repair the mapping before handoff."
        ),
    }
    return {
        "note_kind": "connection",
        "source_node_id": source_id,
        "target_node_id": target_id,
        "citation_ref": f"NOTE-CONN-{source_id}-{target_id}",
        "title": f"CONN-{source_id}-{target_id} | {source_label} to {target_label}",
        "sections": sections,
        "body": _note_sections_body(sections),
        "generation_status": "generated_from_project_state",
    }


def _note_sections_body(sections: Mapping[str, str]) -> str:
    return "\n".join(f"{section}: {text}" for section, text in sections.items())


def _module_label_for_note(module: Mapping[str, object] | None) -> str:
    if module is None:
        return "Make module"
    token = _optional_text(module.get("module")) or "Make module"
    label = token.replace(":", " ").replace("_", " ")
    return re.sub(r"\s+", " ", label).strip()[:80] or "Make module"


def _grouped_missing_notes(
    *,
    scenario: Mapping[str, object],
    missing_module_ids: Sequence[str],
    missing_connections: Sequence[tuple[str, str]],
) -> tuple[JsonObject, ...]:
    module_by_id = {
        str(_node_id(module)): _optional_text(module.get("module")) or "unknown"
        for _path, module in _iter_modules(scenario)
        if _node_id(module) is not None
    }
    groups: dict[tuple[str, str], JsonObject] = {}
    for node_id in missing_module_ids:
        module_token = module_by_id.get(node_id, "unknown")
        key = ("module", module_token)
        group = groups.setdefault(
            key,
            {
                "note_kind": "module",
                "module": module_token,
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_node_ids"])
        if len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(node_id)
    for source_id, target_id in missing_connections:
        module_token = module_by_id.get(target_id, "unknown")
        key = ("connection", module_token)
        group = groups.setdefault(
            key,
            {
                "note_kind": "connection",
                "module": module_token,
                "count": 0,
                "example_connections": [],
            },
        )
        group["count"] = _int_mapping_value(group, "count") + 1
        examples = cast("list[str]", group["example_connections"])
        if len(examples) < PROJECT_EXAMPLE_LIMIT:
            examples.append(f"{source_id}->{target_id}")
    return tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_int_mapping_value(item, "count"),
                str(item["module"]),
            ),
        )[:PROJECT_VIEW_DEFAULT_LIMIT]
    )


def _semantic_handoff_connections(
    links: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, str], ...]:
    seen: set[tuple[str, str]] = set()
    connections: list[tuple[str, str]] = []
    for link in links:
        source = str(link.get("source_node_id"))
        target = str(link.get("target_node_id"))
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        connections.append(key)
    return tuple(connections)


def _scenario_notes(scenario: Mapping[str, object]) -> tuple[JsonObject, ...]:
    metadata = scenario.get("metadata")
    metadata_mapping = (
        cast("Mapping[str, object]", metadata)
        if isinstance(metadata, dict)
        else cast("Mapping[str, object]", {})
    )
    notes_value = metadata_mapping.get("notes")
    if not isinstance(notes_value, list):
        return ()
    note_items = cast("list[object]", notes_value)
    return tuple(
        cast("JsonObject", note)
        for note in note_items
        if isinstance(note, dict)
    )


def _module_note_targets(
    notes: Sequence[Mapping[str, object]],
) -> frozenset[str]:
    targets: set[str] = set()
    for note in notes:
        target = _optional_node_id(
            note.get("target_node_id") or note.get("node_id")
        )
        title = _optional_text(note.get("title")) or ""
        if target is None and title.startswith("MOD-"):
            target = (
                title.removeprefix("MOD-")
                .split(maxsplit=1)[0]
                .split("|", maxsplit=1)[0]
            )
        if target is not None and (
            note.get("note_kind") in {None, "module"}
            or title.startswith("MOD-")
        ):
            targets.add(target)
    return frozenset(targets)


def _connection_note_targets(
    notes: Sequence[Mapping[str, object]],
) -> frozenset[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for note in notes:
        source = _optional_node_id(note.get("source_node_id"))
        target = _optional_node_id(note.get("target_node_id"))
        title = _optional_text(note.get("title")) or ""
        if (source is None or target is None) and title.startswith("CONN-"):
            parts = (
                title.removeprefix("CONN-")
                .split(maxsplit=1)[0]
                .split("|", maxsplit=1)[0]
            )
            if "-" in parts:
                source, target = parts.split("-", maxsplit=1)
        if source is not None and target is not None:
            targets.add((source, target))
    return frozenset(targets)


def _batch_note_plan(
    *, coverage: Mapping[str, object]
) -> tuple[JsonObject, ...]:
    plan: list[JsonObject] = []
    missing_modules = _int_mapping_value(coverage, "missing_module_note_count")
    missing_connections = _int_mapping_value(
        coverage, "missing_connection_note_count"
    )
    if missing_modules:
        plan.append(
            {
                "note_kind": "module",
                "count": missing_modules,
                "tool": "project.edit",
                "surface": "notes",
                "operation": "add",
                "requirements": _note_quality_contract()["module"],
            }
        )
    if missing_connections:
        plan.append(
            {
                "note_kind": "connection",
                "count": missing_connections,
                "tool": "project.edit",
                "surface": "notes",
                "operation": "add",
                "requirements": _note_quality_contract()["connection"],
            }
        )
    return tuple(plan)


def _note_quality_contract() -> JsonObject:
    return {
        "module": {
            "required_sections": NOTE_MODULE_REQUIRED_SECTIONS,
            "citation_ref_pattern": "NOTE-MOD-<target_node_id>",
            "make_canvas_pdf_index": "PDF index: NOTE-MOD-<target_node_id>",
        },
        "connection": {
            "required_sections": NOTE_CONNECTION_REQUIRED_SECTIONS,
            "citation_ref_pattern": "NOTE-CONN-<source_node_id>-<target_node_id>",
            "make_canvas_pdf_index": (
                "PDF index: NOTE-CONN-<source_node_id>-<target_node_id>"
            ),
        },
        "zero_trace_rule": (
            "Client-facing notes must stay public and omit credentials, machine-local "
            "references, and private implementation details."
        ),
    }


def _state_aware_next_actions(
    *,
    summary: Mapping[str, object],
    verification: Mapping[str, object],
    runtime_counts: RuntimeSetupSurfaceCounts,
    project_id: str,
    profile: str,
    mode: str,
) -> tuple[JsonObject, ...]:
    actions: list[JsonObject] = []
    if _int_mapping_value(summary, "module_count") == 0:
        actions.append(
            {
                "surface": "structure",
                "tool": "project.edit",
                "reason": "Create or add the first local Make module node.",
                "arguments": {
                    "project_id": project_id,
                    "surface": "modules",
                    "operation": "add",
                },
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif verification["structural_validation_status"] != "valid":
        actions.append(
            {
                "surface": "structure",
                "tool": "project.view",
                "reason": "Repair local graph structure before import or handoff work.",
                "arguments": {"project_id": project_id, "surface": "issues"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif verification["make_import_validation_status"] != "ready":
        actions.append(
            {
                "surface": "make_import",
                "tool": "project.verify",
                "reason": "Resolve local Make import blockers before artifact projection.",
                "arguments": {
                    "project_id": project_id,
                    "profile": "import_test",
                },
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif verification["zero_trace_status"] == "failed":
        actions.append(
            {
                "surface": "zero_trace",
                "tool": "project.make",
                "reason": (
                    "Remove private trace markers before client-facing preview, package, "
                    "or handoff."
                ),
                "arguments": {
                    "project_id": project_id,
                    "action": "preview",
                    "output_mode": "full",
                },
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif profile == "import_test" and runtime_counts.item_count:
        actions.append(
            {
                "surface": "runtime_setup",
                "tool": "project.view",
                "reason": "Import is locally ready; inspect runtime setup before live handoff.",
                "arguments": {"project_id": project_id, "surface": "runtime"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif profile == "live_preflight":
        actions.append(
            {
                "surface": "live_preflight",
                "tool": "project.make",
                "reason": (
                    "Inspect the full local package and Make.com MCP capability gaps; "
                    "Pancakes does not execute live steps."
                ),
                "arguments": {
                    "project_id": project_id,
                    "action": "package",
                    "profile": "live_preflight",
                    "dry_run": True,
                    "output_mode": "full",
                },
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif (
        profile == "handoff_test"
        and verification["client_handoff_status"] == "blocked"
    ):
        actions.append(
            {
                "surface": "client_handoff",
                "tool": "project.view",
                "reason": "Missing handoff notes are the current blocker.",
                "arguments": {"project_id": project_id, "surface": "notes"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif verification["native_parity_validation_status"] == "blocked":
        actions.append(
            {
                "surface": "native_parity",
                "tool": "project.view",
                "reason": "Attach or inspect Make-native parity evidence.",
                "arguments": {"project_id": project_id, "surface": "parity"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif runtime_counts.item_count:
        actions.append(
            {
                "surface": "runtime_setup",
                "tool": "project.view",
                "reason": "Runtime setup placeholders need a human setup summary.",
                "arguments": {"project_id": project_id, "surface": "runtime"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    elif verification["client_handoff_status"] == "blocked":
        actions.append(
            {
                "surface": "client_handoff",
                "tool": "project.view",
                "reason": "Client handoff notes need completion.",
                "arguments": {"project_id": project_id, "surface": "notes"},
                "owning_layer": "pancakes_mcp",
                "requires_operator_approval": False,
            }
        )
    else:
        actions.extend(
            (
                {
                    "surface": "make_import",
                    "tool": "project.make",
                    "reason": "Preview the Make-native artifact with zero-trace checks.",
                    "arguments": {
                        "project_id": project_id,
                        "action": "preview",
                    },
                    "owning_layer": "pancakes_mcp",
                    "requires_operator_approval": False,
                },
                {
                    "surface": "client_handoff",
                    "tool": "project.verify",
                    "reason": "Verify client handoff when import projection is ready.",
                    "arguments": {
                        "project_id": project_id,
                        "profile": "handoff_test",
                    },
                    "owning_layer": "pancakes_mcp",
                    "requires_operator_approval": False,
                },
            )
        )
    if mode == "one":
        return tuple(actions[:1])
    return tuple(actions)


def _edit_project_module(
    *,
    operation: str,
    arguments: Mapping[str, object],
    payload: JsonObject,
    repo_root: Path,
) -> JsonObject:
    dispatch = dict(arguments)
    if operation == "add":
        _ = dispatch.setdefault("module_json", payload)
        result = add_project_module(dispatch, repo_root)
        result["wrapped_tool"] = "project.modules.add"
    elif operation == "modify":
        if "module_id" not in dispatch and "node_id" in dispatch:
            dispatch["module_id"] = dispatch["node_id"]
        _ = dispatch.setdefault("patch_json", payload)
        result = modify_project_module(dispatch, repo_root)
        result["wrapped_tool"] = "project.modules.modify"
    elif operation == "delete":
        if "module_id" not in dispatch and "node_id" in dispatch:
            dispatch["module_id"] = dispatch["node_id"]
        result = _delete_project_module(
            arguments=dispatch,
            repo_root=repo_root,
            allow_write=True,
        )
        result["wrapped_tool"] = "project.modules.delete"
    else:
        _raise_value_error("Unsupported module edit operation.")
    result["semantic_tool"] = "project.edit"
    return result


def _edit_project_filter(
    *,
    operation: str,
    arguments: Mapping[str, object],
    payload: JsonObject,
    repo_root: Path,
) -> JsonObject:
    dispatch = dict(arguments)
    if operation == "add":
        _ = dispatch.setdefault("filter_json", payload)
        result = add_project_filter(dispatch, repo_root)
        result["wrapped_tool"] = "project.filters.add"
    elif operation == "modify":
        _ = dispatch.setdefault("patch_json", payload)
        result = modify_project_filter(dispatch, repo_root)
        result["wrapped_tool"] = "project.filters.modify"
    elif operation == "delete":
        result = _delete_project_filter(
            arguments=dispatch,
            repo_root=repo_root,
            allow_write=True,
        )
        result["wrapped_tool"] = "project.filters.delete"
    else:
        _raise_value_error("Unsupported filter edit operation.")
    result["semantic_tool"] = "project.edit"
    return result


def _edit_project_error_handler(
    *,
    operation: str,
    arguments: Mapping[str, object],
    payload: JsonObject,
    repo_root: Path,
) -> JsonObject:
    dispatch = dict(arguments)
    if operation == "add":
        _ = dispatch.setdefault("handler_json", payload)
        result = add_project_error_handler(dispatch, repo_root)
        result["wrapped_tool"] = "project.error_handlers.add"
    elif operation == "modify":
        _ = dispatch.setdefault("patch_json", payload)
        result = modify_project_error_handler(dispatch, repo_root)
        result["wrapped_tool"] = "project.error_handlers.modify"
    elif operation == "delete":
        result = _delete_project_error_handler(
            arguments=dispatch,
            repo_root=repo_root,
            allow_write=True,
        )
        result["wrapped_tool"] = "project.error_handlers.delete"
    else:
        _raise_value_error("Unsupported error-handler edit operation.")
    result["semantic_tool"] = "project.edit"
    return result


def _edit_project_notes(
    *,
    operation: str,
    arguments: Mapping[str, object],
    payload: JsonObject,
    repo_root: Path,
) -> JsonObject:
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    updated = deepcopy(scenario)
    metadata = updated.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        updated["metadata"] = metadata
    metadata_mapping = cast("MutableMapping[str, object]", metadata)
    notes_value = metadata_mapping.get("notes")
    if not isinstance(notes_value, list):
        notes_value = []
        metadata_mapping["notes"] = notes_value
    notes = cast("list[object]", notes_value)
    if operation in {"generate", "generate_missing"}:
        generated_notes = _generated_missing_notes(scenario)
        notes.extend(dict(note) for note in generated_notes)
        returned_notes = generated_notes[:PROJECT_VIEW_DEFAULT_LIMIT]
        target = {
            "added_note_count": len(generated_notes),
            "returned_added_note_count": len(returned_notes),
            "hidden_added_note_count": max(
                len(generated_notes) - len(returned_notes), 0
            ),
            "added_notes": returned_notes,
            "redaction_evidence": _note_redaction_evidence(generated_notes),
            "note_section_validation": _note_section_validation(
                generated_notes
            ),
        }
    elif operation == "add":
        note = dict(payload)
        _ = note.setdefault(
            "note_kind", _optional_text(arguments.get("note_kind")) or "module"
        )
        _ = note.setdefault("citation_ref", _note_citation_ref(note))
        _ensure_notes_redaction_safe((note,))
        notes.append(note)
        target: JsonObject = {"note_index": len(notes) - 1, "note": note}
    elif operation == "modify":
        index = _nonnegative_int(
            arguments.get("note_index"), default=0, upper=10_000
        )
        if index >= len(notes) or not isinstance(notes[index], dict):
            _raise_value_error("note_index is out of range.")
        note = cast("MutableMapping[str, object]", notes[index])
        _merge_patch(note, payload)
        _ensure_notes_redaction_safe((note,))
        target = {
            "note_index": index,
            "note": cast("JsonObject", _json_copy(note)),
        }
    elif operation == "delete":
        index = _nonnegative_int(
            arguments.get("note_index"), default=0, upper=10_000
        )
        if index >= len(notes):
            _raise_value_error("note_index is out of range.")
        if not _bool_argument(arguments.get("confirm"), default=False):
            _raise_value_error("Note deletion requires confirm=true.")
        removed = notes.pop(index)
        target = {"note_index": index, "removed": removed}
    else:
        _raise_value_error("Unsupported notes edit operation.")
    result = _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="notes",
        operation=operation,
        target=target,
    )
    result["semantic_tool"] = "project.edit"
    result["wrapped_tool"] = "project.edit.notes"
    return result


def _ensure_notes_redaction_safe(notes: Sequence[Mapping[str, object]]) -> None:
    evidence = _note_redaction_evidence(notes)
    if _int_mapping_value(evidence, "finding_count"):
        _raise_value_error(
            "project.edit notes redaction failed; remove credentials, machine-local references, runtime placeholders, prompts, and private implementation details."
        )


def _note_citation_ref(note: Mapping[str, object]) -> str:
    note_kind = _optional_text(note.get("note_kind")) or "module"
    if note_kind == "connection":
        source = _optional_node_id(note.get("source_node_id")) or "source"
        target = _optional_node_id(note.get("target_node_id")) or "target"
        return f"NOTE-CONN-{source}-{target}"
    target = (
        _optional_node_id(note.get("target_node_id") or note.get("node_id"))
        or "node"
    )
    return f"NOTE-MOD-{target}"


def _edit_project_datastore_manifest(
    *,
    operation: str,
    arguments: Mapping[str, object],
    payload: JsonObject,
    repo_root: Path,
) -> JsonObject:
    project_id, scenario_path, scenario = _scenario_context(
        arguments, repo_root
    )
    updated = deepcopy(scenario)
    metadata = updated.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        _raise_value_error(
            "metadata must be an object before editing datastores."
        )
    metadata_mapping = cast("MutableMapping[str, object]", metadata)
    manifest = metadata_mapping.setdefault(
        "datastore_manifest", {"resources": []}
    )
    if not isinstance(manifest, dict):
        _raise_value_error("metadata.datastore_manifest must be an object.")
    resources = cast("MutableMapping[str, object]", manifest).setdefault(
        "resources", []
    )
    if not isinstance(resources, list):
        _raise_value_error(
            "metadata.datastore_manifest.resources must be a list."
        )
    resource_rows = cast("list[object]", resources)
    resource_key = _optional_text(
        arguments.get("resource_key") or payload.get("resource_key")
    )
    target: JsonObject
    if operation == "add":
        if not resource_key:
            _raise_value_error("datastore add requires resource_key.")
        if any(
            _datastore_resource_key_matches(row, resource_key)
            for row in resource_rows
        ):
            _raise_value_error(
                f"Duplicate datastore resource_key: {resource_key}."
            )
        resource_rows.append(dict(payload))
        target = {"resource_key": resource_key}
    elif operation == "modify":
        if not resource_key:
            _raise_value_error("datastore modify requires resource_key.")
        target = _merge_datastore_resource(
            resources=resource_rows,
            resource_key=resource_key,
            patch=payload,
        )
    elif operation == "delete":
        if not resource_key:
            _raise_value_error("datastore delete requires resource_key.")
        target = _delete_datastore_resource(
            resources=resource_rows, resource_key=resource_key
        )
    else:
        _raise_value_error("Unsupported datastores edit operation.")
    result = _write_response(
        repo_root=repo_root,
        project_id=project_id,
        scenario_path=scenario_path,
        current=scenario,
        updated=updated,
        arguments=arguments,
        domain_surface="datastores",
        operation=operation,
        target=target,
    )
    result["semantic_tool"] = "project.edit"
    result["wrapped_tool"] = "project.edit.datastores"
    return result


def _merge_datastore_resource(
    *,
    resources: list[object],
    resource_key: str,
    patch: Mapping[str, object],
) -> JsonObject:
    for row in resources:
        if _datastore_resource_key_matches(row, resource_key):
            target = cast("MutableMapping[str, object]", row)
            _merge_patch(target, patch)
            return {"resource_key": resource_key, "resource": dict(target)}
    _raise_value_error(f"Unknown datastore resource_key: {resource_key}.")


def _delete_datastore_resource(
    *, resources: list[object], resource_key: str
) -> JsonObject:
    for index, row in enumerate(tuple(resources)):
        if _datastore_resource_key_matches(row, resource_key):
            removed = resources.pop(index)
            return {
                "resource_key": resource_key,
                "removed": _json_copy(removed),
            }
    _raise_value_error(f"Unknown datastore resource_key: {resource_key}.")


def _datastore_resource_key_matches(row: object, resource_key: str) -> bool:
    if not isinstance(row, dict):
        return False
    mapping = cast("Mapping[str, object]", row)
    return mapping.get("resource_key") == resource_key


def _project_edit_payload(value: object) -> JsonObject:
    if value is None:
        return {}
    if isinstance(value, str):
        value = cast("object", json.loads(value))
    if not isinstance(value, dict):
        _raise_value_error("payload_json must be a JSON object when provided.")
    return cast("JsonObject", _json_copy(cast("Mapping[str, object]", value)))


def _project_output_mode(value: object, *, default: str) -> str:
    output_mode = _optional_text(value) or default
    normalized = output_mode.casefold()
    if normalized not in PROJECT_OUTPUT_MODES:
        _raise_value_error(
            "output_mode must be micro, compact, outline, full, or debug."
        )
    return normalized


def _project_surface(value: object) -> str:
    surface = (_optional_text(value) or "overview").casefold()
    if surface not in PROJECT_VIEW_SURFACES:
        _raise_value_error("Unsupported project.view surface.")
    return surface


def _project_edit_surface(value: object) -> str:
    surface = (_optional_text(value) or "modules").casefold()
    aliases = {
        "module": "modules",
        "filter": "filters",
        "error_handler": "error_handlers",
        "note": "notes",
    }
    return aliases.get(surface, surface)


def _project_edit_operation(value: object) -> str:
    operation = (_optional_text(value) or "add").casefold()
    if operation not in {
        "add",
        "modify",
        "delete",
        "generate",
        "generate_missing",
    }:
        _raise_value_error(
            "project.edit operation must be add, modify, delete, or generate_missing."
        )
    return operation


def _project_make_action(value: object) -> str:
    action = (_optional_text(value) or "preview").casefold()
    if action not in PROJECT_MAKE_ACTIONS:
        _raise_value_error(
            "project.make action must be preview, render, write, or package."
        )
    return action


def _project_make_profile(value: object) -> str:
    profile = (_optional_text(value) or "import_test").casefold()
    if profile not in PROJECT_MAKE_PROFILES:
        _raise_value_error(
            "project.make profile must be import_test, parity_fixture, client_handoff, or live_preflight."
        )
    return profile


def _project_package_inspect_section(value: object) -> str:
    section = (_optional_text(value) or "live_resources").casefold()
    aliases = {
        "resources": "live_resources",
        "live_resource": "live_resources",
        "live_resource_package": "live_resources",
        "blueprint": "blueprint_summary",
        "summary": "blueprint_summary",
        "parity": "parity_plan",
        "customer": "customer_files",
        "customer_package": "customer_files",
        "files": "customer_files",
        "zero": "zero_trace",
        "redaction": "zero_trace",
    }
    normalized = aliases.get(section, section)
    if normalized not in PROJECT_PACKAGE_INSPECT_SECTIONS:
        supported_sections = ", ".join(PROJECT_PACKAGE_INSPECT_SECTIONS)
        _raise_value_error(
            f"project.package.inspect section must be one of: {supported_sections}."
        )
    return normalized


def _project_verify_profile(value: object) -> str:
    profile = (_optional_text(value) or "import_test").casefold()
    if profile not in PROJECT_VERIFY_PROFILES:
        _raise_value_error("project.verify profile is unsupported.")
    return profile


def _project_next_mode(value: object) -> str:
    mode = (_optional_text(value) or "one").casefold()
    if mode not in PROJECT_NEXT_MODES:
        _raise_value_error("project.next mode must be one or plan.")
    return mode


def _project_view_limit(value: object, *, output_mode: str) -> int:
    if output_mode in {"full", "debug"}:
        return PROJECT_VIEW_MAX_LIMIT
    return _bounded_int(
        value, default=PROJECT_VIEW_DEFAULT_LIMIT, upper=PROJECT_VIEW_MAX_LIMIT
    )


def _int_mapping_value(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _scenario_context(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> tuple[str, Path, JsonObject]:
    project_id = _required_project_id(arguments)
    scenario_path = _scenario_path(repo_root=repo_root, project_id=project_id)
    scenario = _read_json_object(scenario_path)
    return project_id, scenario_path, scenario


def _scenario_context_or_error(
    arguments: Mapping[str, object],
    repo_root: Path,
    *,
    tool_name: str,
) -> tuple[str, Path, JsonObject] | JsonObject:
    project_id = _required_project_id(arguments)
    scenario_path = _scenario_path(repo_root=repo_root, project_id=project_id)
    if not scenario_path.exists():
        return _project_access_error_payload(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
            tool_name=tool_name,
        )
    try:
        scenario = _read_json_object(scenario_path)
    except FileNotFoundError:
        return _project_access_error_payload(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
            tool_name=tool_name,
        )
    return project_id, scenario_path, scenario


def _project_access_error_payload(
    *,
    repo_root: Path,
    project_id: str,
    scenario_path: Path,
    tool_name: str,
) -> JsonObject:
    metadata_row = _local_project_metadata_row(
        repo_root=repo_root, project_id=project_id
    )
    local_folder_exists = scenario_path.parent.exists()
    error_code = (
        "scenario_file_missing"
        if metadata_row is not None or local_folder_exists
        else "project_not_found"
    )
    status_reason = (
        "Project metadata or a local project folder exists, but scenario.json is missing."
        if error_code == "scenario_file_missing"
        else "No local project metadata or scenario.json artifact exists for this project_id."
    )
    surface_status = blocked_surface_payload(
        blocked_surfaces=("structure",),
        unblocked_surfaces=(),
        status_reason=status_reason,
    )
    return {
        "status": "blocked",
        "error_code": error_code,
        "project_id": project_id,
        "source_of_truth": "local_project_scenario",
        "tool": tool_name,
        "expected_path": _local_project_display_path(
            repo_root=repo_root, path=scenario_path
        ),
        "scenario_file_name": SCENARIO_FILE_NAME,
        "scenario_file_exists": False,
        "local_project_exists": error_code == "scenario_file_missing",
        "next_action": "project.create",
        **surface_status,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "next_queries": (
            _next_query(
                tool="project.create",
                arguments={"project_id": project_id, "dry_run": False},
                reason="Create the local project artifact before reading or verifying it.",
            ),
        ),
        **_local_offline_safety_flags(),
    }


def _project_create_permission_denied_payload(
    *,
    repo_root: Path,
    project_id: str,
    scenario_path: Path,
    storage: Mapping[str, object],
    exception: BaseException,
) -> JsonObject:
    partial_written = scenario_path.exists()
    surface_status = blocked_surface_payload(
        blocked_surfaces=("artifact_render",),
        unblocked_surfaces=("structure",),
        status_reason="project.create could not write the local project artifact path.",
    )
    path_report = _local_project_path_report(
        repo_root=repo_root, scenario_path=scenario_path
    )
    return {
        "status": "blocked",
        "error_code": "project_create_permission_denied",
        "project_id": project_id,
        "would_create": True,
        "created": False,
        "writes_performed": partial_written,
        "write_actions": ["partial_project_scenario_write"]
        if partial_written
        else [],
        "source_of_truth": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
        "expected_path": _local_project_display_path(
            repo_root=repo_root, path=scenario_path
        ),
        "artifact_envelope_path": str(storage["artifact_envelope_path"]),
        "scenario_artifact_path": str(storage["scenario_artifact_path"]),
        "partial_artifact_written": partial_written,
        "next_action": "project.create",
        "required_prerequisite": "project workspace write permission",
        **surface_status,
        "diagnostic": type(exception).__name__,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        "storage_model": {
            "sqlite_source_of_truth": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
            "artifact_folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
            "logical_project_path": path_report["logical_project_path"],
            "logical_scenario_path": path_report["logical_scenario_path"],
            "physical_artifact_path": path_report["physical_artifact_path"],
            "physical_scenario_artifact_path": path_report[
                "physical_scenario_artifact_path"
            ],
            "artifact_policy_status": path_report["artifact_policy_status"],
            "artifact_policy_detail": path_report["artifact_policy_detail"],
            "generated_state_physical_path": path_report[
                "generated_state_physical_path"
            ],
            "folder_reconstructable_from_sqlite": True,
            "core_business_state_written": False,
        },
        **_local_offline_safety_flags(),
    }
