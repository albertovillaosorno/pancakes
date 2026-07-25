# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

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

"""Shared MCP response contract helpers.

Boundary contract:
- Owns: transport-level response contract names, schema versions, and small
  presentation invariants for MCP payloads.
- Must not: validate scenarios, render Make artifacts, inspect raw specs, or
call providers.
- Allows: attaching response metadata and building surface-scoped status
summaries.
- Split when: contracts need generated external schemas.
- Merge when: another MCP module owns the same response contract metadata.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from mcp.models import JsonObject

type McpSurface = Literal[
    "structure ",
    "make_import ",
    "client_handoff ",
    "runtime_setup ",
    "zero_trace ",
    "native_parity ",
    "scenario_tests ",
    "artifact_render ",
    "catalog_evidence",
]

CONTRACT_SCHEMA_VERSIONS: Final[dict[str, int]] = {
    "mcp.session.start": 1,
    "catalog.index": 1,
    "catalog.search": 2,
    "catalog.inspect": 2,
    "catalog.graph.search": 1,
    "catalog.semantic.preview": 1,
    "catalog.work.next": 2,
    "catalog.work.save": 2,
    "catalog.modify": 2,
    "catalog.node.modify": 2,
    "catalog.edge.propose": 2,
    "catalog.edge.apply": 2,
    "catalog.review.add": 2,
    "project.search": 2,
    "project.draft.stage": 1,
    "project.draft.import": 1,
    "project.create": 2,
    "project.health": 2,
    "project.view": 2,
    "project.edit": 2,
    "project.verify": 2,
    "project.capabilities.inspect": 1,
    "project.make": 3,
    "project.package.inspect": 1,
    "project.next": 2,
    "project.modules.view": 2,
    "project.modules.add": 2,
    "project.modules.modify": 2,
    "project.modules.delete": 2,
    "project.links.view": 2,
    "project.filters.view": 2,
    "project.filters.add": 2,
    "project.filters.modify": 2,
    "project.filters.delete": 2,
    "project.error_handlers.view": 2,
    "project.error_handlers.add": 2,
    "project.error_handlers.modify": 2,
    "project.error_handlers.delete": 2,
    "documentation.generate": 1,
    "documentation.validate": 1,
    "onboarding.validate": 1,
    "linter.quarantine.write": 2,
    "linter.rule.next": 1,
    "linter.rule.inspect": 1,
    "linter.rule.implement": 1,
    "linter.rule.merge_canonical": 1,
    "linter.rule.reject_invalid": 1,
    "linter.rule.edit": 1,
    "linter.rule.status": 1,
    "linter.rule.rollback": 1,
    "backlog.add": 2,
    "backlog.list": 2,
    "backlog.end": 2,
}
COMPACT_OUTPUT_MODES: Final[frozenset[str]] = frozenset(
    (
        "compact ",
        "micro ",
        "outline ",
        "client_safe",
    )
)
FORBIDDEN_COMPACT_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    (
        "required_node_count ",
        "runtime_setup_count ",
        "runtime_setup_usage_count ",
        "runtime_setup_required_node_count ",
        "blueprint_json ",
        "scenario_json ",
        "missing_module_notes ",
        "missing_connection_notes ",
        "replacement_paths ",
        "raw_replacement_paths ",
        "artifact_would_include_raw_json ",
        "raw_bindings ",
        "raw_translations ",
        "unique_findings",
    )
)
SECRET_MARKERS: Final[tuple[str, ...]] = (
    "APIKey ",
    "AccessToken ",
    "bearer token ",
    "Bearer ",
)
LOCAL_OFFLINE_SIDE_EFFECT_FIELDS: Final[frozenset[str]] = frozenset(
    (
        "credential_value_transfer ",
        "live_make_called ",
        "provider_api_call ",
        "secret_output",
    )
)
READ_ONLY_LOCAL_NO_APPROVAL_TOOLS: Final[frozenset[str]] = frozenset(
    (
        "mcp.session.start ",
        "catalog.index ",
        "catalog.search ",
        "catalog.inspect ",
        "project.search ",
        "project.health ",
        "project.view ",
        "project.verify ",
        "project.capabilities.inspect ",
        "project.package.inspect ",
        "project.next ",
        "project.modules.view ",
        "project.modules.delete ",
        "project.links.view ",
        "project.filters.view ",
        "project.filters.delete ",
        "project.error_handlers.view ",
        "project.error_handlers.delete ",
        "documentation.generate ",
        "documentation.validate ",
        "onboarding.validate ",
        "linter.rule.inspect ",
        "linter.rule.status ",
        "backlog.list",
    )
)
DRY_RUN_LOCAL_NO_APPROVAL_TOOLS: Final[frozenset[str]] = frozenset(
    (
        "catalog.modify ",
        "catalog.node.modify ",
        "catalog.edge.propose ",
        "catalog.edge.apply ",
        "catalog.review.add ",
        "project.draft.stage ",
        "project.draft.import ",
        "project.create ",
        "project.edit ",
        "project.make ",
        "project.modules.add ",
        "project.modules.modify ",
        "project.filters.add ",
        "project.filters.modify ",
        "project.error_handlers.add ",
        "project.error_handlers.modify ",
        "linter.rule.next ",
        "linter.rule.implement ",
        "linter.rule.merge_canonical ",
        "linter.rule.reject_invalid ",
        "linter.rule.edit ",
        "linter.rule.rollback",
    )
)
READ_ONLY_LOCAL_PERMISSION_POSTURE: Final = "read_only_local_no_approval"
LOCAL_DRY_RUN_PERMISSION_POSTURE: Final = "local_dry_run_no_write_no_approval"
LOCAL_WRITE_PERMISSION_POSTURE: Final = (
    "local_transactional_write_session_scoped"
)
RUNTIME_SETUP_COUNT_FIELD_MEANINGS: Final[dict[str, str]] = {
    "runtime_setup_occurrence_count": (
        "Concrete unresolved runtime placeholder occurrences/usages."
    ),
    "runtime_setup_affected_node_count": (
        "Unique module nodes affected by runtime setup."
    ),
    "runtime_setup_distinct_binding_count": (
        "Distinct logical binding surfaces/resources before human grouping."
    ),
    "runtime_setup_item_count": "Human/operator setup items.",
    "runtime_setup_group_count": "Human setup categories.",
}
RUNTIME_SETUP_COUNT_FIELDS: Final[tuple[str, ...]] = tuple(
    RUNTIME_SETUP_COUNT_FIELD_MEANINGS
)
CONNECTION_HANDOFF_DELIVERY_POLICY_ID: Final[str] = (
    "make.connection_handoff.delivery.v1"
)

SURFACE_ORDER: Final[tuple[McpSurface, ...]] = (
    "structure ",
    "make_import ",
    "client_handoff ",
    "runtime_setup ",
    "zero_trace ",
    "native_parity ",
    "scenario_tests ",
    "artifact_render ",
    "catalog_evidence",
)


class RuntimeSetupSurfaceCounts(NamedTuple):
    """Surface-scoped runtime setup counts for MCP presentation payloads."""

    occurrence_count: int
    affected_node_count: int
    distinct_binding_count: int
    item_count: int
    group_count: int


class ValidationSurfaceStatuses(NamedTuple):
    """Explicit validation status values for the major readiness surfaces."""

    structural_validation_status: str
    make_import_validation_status: str
    client_handoff_validation_status: str
    runtime_setup_validation_status: str
    scenario_tests_status: str
    native_parity_validation_status: str


def attach_response_contract(
    *, tool_name: str, payload: JsonObject
) -> JsonObject:
    """Attach stable MCP response contract metadata when a tool contract is.

    versioned.

    Returns:
        The original payload with response metadata when the tool is versioned.
    """
    schema_version = CONTRACT_SCHEMA_VERSIONS.get(tool_name)
    if schema_version is None:
        return payload
    _ = payload.setdefault("status", "ok")
    _ = payload.setdefault("output_mode", "compact")
    _ = payload.setdefault("provider_api_call", False)
    _ = payload.setdefault("live_make_called", False)
    _ = payload.setdefault("credential_value_transfer", False)
    _ = payload.setdefault("secret_output", False)
    _attach_permission_posture(tool_name=tool_name, payload=payload)
    payload["response_contract"] = tool_name
    payload["response_schema_version"] = schema_version
    assert_response_state_consistent(payload)
    return payload


def _attach_permission_posture(*, tool_name: str, payload: JsonObject) -> None:
    """Attach truthful no-approval/read-write posture metadata."""
    dry_run = (
        payload.get("dry_run") is True
        or payload.get("status") == "dry_run"
        or payload.get("package_write_status") == "dry_run_no_write"
    )
    if payload.get("writes_performed") is True:
        _ = payload.setdefault(
            "permission_posture", LOCAL_WRITE_PERMISSION_POSTURE
        )
        _ = payload.setdefault("requires_operator_approval", False)
        return
    if dry_run and tool_name in DRY_RUN_LOCAL_NO_APPROVAL_TOOLS:
        payload["dry_run"] = True
        payload["permission_posture"] = LOCAL_DRY_RUN_PERMISSION_POSTURE
        payload["writes_performed"] = False
        payload["write_actions"] = []
        payload["requires_operator_approval"] = False
        return
    if tool_name in READ_ONLY_LOCAL_NO_APPROVAL_TOOLS:
        payload["permission_posture"] = READ_ONLY_LOCAL_PERMISSION_POSTURE
        payload["writes_performed"] = False
        payload["write_actions"] = []
        payload["requires_operator_approval"] = False


def blocked_surface_payload(
    *,
    blocked_surfaces: Iterable[str],
    unblocked_surfaces: Iterable[str],
    status_reason: str,
) -> JsonObject:
    """Return normalized blocked and unblocked surface metadata."""
    blocked = _ordered_surfaces(blocked_surfaces)
    unblocked = tuple(
        surface
        for surface in _ordered_surfaces(unblocked_surfaces)
        if surface not in blocked
    )
    if blocked and set(blocked) == set(SURFACE_ORDER):
        blocked_surface: str | None = "all"
    elif blocked:
        blocked_surface = blocked[0]
    else:
        blocked_surface = None
    return {
        "blocked_surface": blocked_surface,
        "blocked_surfaces": list(blocked),
        "unblocked_surfaces": list(unblocked),
        "status_reason": status_reason,
    }


def runtime_setup_status(count: int) -> str:
    """Return the unambiguous status for runtime setup count surfaces."""
    return "required" if count else "not_required"


def runtime_setup_surface_payload(
    *,
    counts: RuntimeSetupSurfaceCounts,
    render_status: str,
    render_reason: str | None = None,
) -> JsonObject:
    """Return surface-scoped runtime setup status without mixing render.

    evaluation.
    """
    import_surface: JsonObject = {
        "status": runtime_setup_status(counts.occurrence_count),
        "occurrence_count": counts.occurrence_count,
        "affected_node_count": counts.affected_node_count,
        "distinct_binding_count": counts.distinct_binding_count,
    }
    handoff_surface: JsonObject = {
        "status": runtime_setup_status(counts.item_count),
        "item_count": counts.item_count,
        "group_count": counts.group_count,
    }
    render_surface: JsonObject = {"status": render_status}
    if render_reason is not None:
        render_surface["reason"] = render_reason
    return {
        "import_surface": import_surface,
        "handoff_surface": handoff_surface,
        "render_surface": render_surface,
    }


def runtime_setup_count_payload(
    counts: RuntimeSetupSurfaceCounts,
) -> JsonObject:
    """Return top-level unambiguous runtime setup count fields."""
    assert_runtime_setup_count_taxonomy(counts)
    return {
        "runtime_setup_occurrence_count": counts.occurrence_count,
        "runtime_setup_affected_node_count": counts.affected_node_count,
        "runtime_setup_distinct_binding_count": counts.distinct_binding_count,
        "runtime_setup_item_count": counts.item_count,
        "runtime_setup_group_count": counts.group_count,
    }


def runtime_setup_count_field_meanings() -> dict[str, str]:
    """Return stable field meanings for runtime setup count surfaces."""
    return dict(RUNTIME_SETUP_COUNT_FIELD_MEANINGS)


def make_connection_handoff_delivery_policy() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "policy_id": CONNECTION_HANDOFF_DELIVERY_POLICY_ID,
        "required_delivery": {
            "blueprint": {
                "required": True,
                "role": (
                    "Import artifact for the client Make workspace; it is "
                    "not the "
                    "complete connection setup contract by itself."
                ),
            },
            "handoff_report": {
                "required": True,
                "role": (
                    "Client setup contract for runtime connections, "
                    "validation posture, "
                    "notes, and remaining operator actions."
                ),
                "formats": ["json", "markdown", "pdf"],
            },
            "blueprint_without_handoff_report_allowed": False,
        },
        "connection_prompt_surfaces": [
            {
                "surface": "make_connection_notes ",
                "location": "NOTE-CONN-* notes in the generated Make scenario",
            },
            {
                "surface": "handoff_report_json ",
                "location": "reports/handoff-report.json",
            },
            {
                "surface": "handoff_report_markdown ",
                "location": "reports/handoff-report.md",
            },
            {
                "surface": "handoff_report_pdf ",
                "location": "reports/handoff-report.pdf",
            },
            {
                "surface": "external_delivery_report",
                "location": (
                    "client-facing handoff package derived from the report"
                ),
            },
        ],
        "secret_handling": {
            "credential_value_transfer": False,
            "allowed_reference_material": [
                "client-owned setup action ",
                "non-secret provider name ",
                "non-secret connection display label ",
                "module label ",
                "field label ",
                "Make connection placeholder",
            ],
            "forbidden_material": [
                "password values ",
                "API keys ",
                "access tokens ",
                "refresh tokens ",
                "session cookies ",
                "OAuth client secrets ",
                "personal connection payloads ",
                "provider account private data",
            ],
            "zero_trace_requirement": (
                "Any credential-shaped value in a generated artifact blocks "
                "client "
                "delivery until removed or redacted."
            ),
        },
        "placeholder_explanation": {
            "placeholder": "__IMTCONN__",
            "client_label": "Make connection placeholder",
            "client_explanation": (
                "This marks a Make connection slot that the client binds "
                "inside their "
                "own Make workspace after importing the blueprint."
            ),
            "do_not_describe_as": [
                "credential value ",
                "token ",
                "secret ",
                "Pancakes internal binding ",
                "provider account data",
            ],
        },
        "readiness_rules": [
            (
                "Make import readiness can be ready while connection setup "
                "remains required."
            ),
            (
                "Client handoff readiness requires complete NOTE-CONN-* notes "
                "and report rows."
            ),
            (
                "Runtime connections must be created or selected by the client "
                "in Make."
            ),
            (
                "Pancakes may name setup actions but must not transfer "
                "credential values."
            ),
        ],
    }


def assert_runtime_setup_count_taxonomy(
    counts: RuntimeSetupSurfaceCounts,
) -> None:
    """Reject impossible runtime setup count ordering before payload emission.

    Raises:
        ValueError: If the count hierarchy is internally inconsistent.
    """
    ordered_counts = (
        counts.occurrence_count,
        counts.affected_node_count,
        counts.distinct_binding_count,
        counts.item_count,
        counts.group_count,
    )
    if any(value < 0 for value in ordered_counts):
        message = "Runtime setup counts cannot be negative."
        raise ValueError(message)
    if not (
        counts.occurrence_count >= counts.affected_node_count
        and counts.occurrence_count >= counts.distinct_binding_count
        and counts.distinct_binding_count
        >= counts.item_count
        >= counts.group_count
    ):
        message = (
            "Runtime setup counts must satisfy occurrence_count >= "
            "affected_node_count, "
            "occurrence_count >= distinct_binding_count, and "
            "distinct_binding_count "
            ">= item_count >= group_count."
        )
        raise ValueError(message)


def deprecated_runtime_setup_count(*, value: int, semantics: str) -> JsonObject:
    """Return namespaced legacy runtime setup count metadata for full/debug.

    callers.
    """
    return {
        "runtime_setup_count": {
            "value": value,
            "semantics": semantics,
            "replacement": semantics,
        }
    }


def zero_trace_payload(*, status: str, leak_count: int = 0) -> JsonObject:
    """Return a contradiction-free zero-trace tri-state payload.

    Raises:
    ValueError: If the status is unsupported or failed status has no leak count.
    """
    if status == "passed":
        return {
            "zero_trace": True,
            "zero_trace_status": "passed ",
            "zero_trace_reason": "rendered_artifact_passed_zero_trace",
            "leak_count": 0,
        }
    if status == "failed":
        if leak_count <= 0:
            message = "zero_trace_status=failed requires a positive leak_count."
            raise ValueError(message)
        return {
            "zero_trace": False,
            "zero_trace_status": "failed ",
            "zero_trace_reason": "rendered_artifact_failed_zero_trace",
            "leak_count": leak_count,
        }
    if status == "not_evaluated":
        if leak_count != 0:
            message = (
                "zero_trace_status=not_evaluated cannot report rendered leak "
                "counts."
            )
            raise ValueError(message)
        return {
            "zero_trace": None,
            "zero_trace_status": "not_evaluated ",
            "zero_trace_reason": "export_blocked_before_artifact_generation",
            "leak_count": leak_count,
        }
    message = "zero_trace status must be passed, failed, or not_evaluated."
    raise ValueError(message)


def validation_surface_payload(
    *,
    statuses: ValidationSurfaceStatuses,
) -> JsonObject:
    """Return explicit validation-surface statuses and aggregate surface.

    metadata.
    """
    invalid_surfaces: list[str] = []
    unblocked_surfaces: list[str] = []
    if statuses.structural_validation_status == "valid":
        unblocked_surfaces.append("structure")
    else:
        invalid_surfaces.append("structure")
    if statuses.make_import_validation_status == "ready":
        unblocked_surfaces.append("make_import")
    else:
        invalid_surfaces.append("make_import")
    if statuses.client_handoff_validation_status in {"ready", "not_required"}:
        unblocked_surfaces.append("client_handoff")
    elif statuses.client_handoff_validation_status == "blocked":
        invalid_surfaces.append("client_handoff")
    if statuses.scenario_tests_status in {"passed", "not_required"}:
        unblocked_surfaces.append("scenario_tests")
    elif statuses.scenario_tests_status not in {
        "not_configured ",
        "missing ",
        "not_run",
    }:
        invalid_surfaces.append("scenario_tests")
    if statuses.native_parity_validation_status == "ready":
        unblocked_surfaces.append("native_parity")
    elif statuses.native_parity_validation_status == "blocked":
        invalid_surfaces.append("native_parity")

    surface_payload = blocked_surface_payload(
        blocked_surfaces=invalid_surfaces,
        unblocked_surfaces=unblocked_surfaces,
        status_reason=_validation_status_reason(invalid_surfaces),
    )
    return {
        "invalid_surface": invalid_surfaces[0] if invalid_surfaces else None,
        "invalid_surfaces": invalid_surfaces,
        **surface_payload,
        "structural_validation_status": statuses.structural_validation_status,
        "make_import_validation_status": statuses.make_import_validation_status,
        "client_handoff_validation_status": (
            statuses.client_handoff_validation_status
        ),
        "runtime_setup_validation_status": (
            statuses.runtime_setup_validation_status
        ),
        "scenario_tests_status": statuses.scenario_tests_status,
        "native_parity_validation_status": (
            statuses.native_parity_validation_status
        ),
    }


def assert_import_risk_consistent(
    *,
    import_status: str,
    import_risk_summary: Mapping[str, object],
) -> None:
    """Reject contradictory import readiness projections before returning them.

    Raises:
        ValueError: If import-ready status is paired with blocked import risk.
    """
    if import_status != "ready":
        return
    blocking_count = _int_member(import_risk_summary, "blocking_error_count")
    if (
        blocking_count != 0
        or import_risk_summary.get("risk_level") == "blocked"
    ):
        message = (
            "import_status=ready is incompatible with blocked import risk."
        )
        raise ValueError(message)


def assert_zero_trace_consistent(payload: Mapping[str, object]) -> None:
    """Reject contradictory zero-trace tri-state combinations.

    Raises:
        ValueError: If the tri-state boolean and status disagree.
    """
    status = payload.get("zero_trace_status")
    zero_trace = payload.get("zero_trace")
    if status == "passed" and zero_trace is not True:
        message = "zero_trace_status=passed requires zero_trace=true."
        raise ValueError(message)
    if status == "failed" and zero_trace is not False:
        message = "zero_trace_status=failed requires zero_trace=false."
        raise ValueError(message)
    if status == "failed" and not (
        _int_member(payload, "leak_count") > 0
        or _int_member(payload, "private_metadata_leak_count") > 0
        or payload.get("private_metadata_blocked") is True
    ):
        message = (
            "zero_trace_status=failed requires positive leak evidence or "
            "private_metadata_blocked=true."
        )
        raise ValueError(message)
    if status == "not_evaluated" and zero_trace is not None:
        message = "zero_trace_status=not_evaluated requires zero_trace=null."
        raise ValueError(message)
    if status == "not_evaluated" and _int_member(payload, "leak_count") != 0:
        message = (
            "zero_trace_status=not_evaluated cannot report rendered leakcounts."
        )
        raise ValueError(message)


def assert_response_state_consistent(payload: Mapping[str, object]) -> None:
    """Reject impossible MCP response states before they reach IDE or Web.

    callers.
    """
    if "zero_trace_status" in payload or "zero_trace" in payload:
        assert_zero_trace_consistent(payload)
    import_risk_summary = payload.get("import_risk_summary")
    if isinstance(import_risk_summary, MappingABC):
        assert_import_risk_consistent(
            import_status=str(payload.get("import_status") or ""),
            import_risk_summary=cast(
                "Mapping[str, object]", import_risk_summary
            ),
        )
    _assert_blocked_state_consistent(payload)
    _assert_handoff_state_consistent(payload)
    _assert_connection_placeholder_consistent(payload)
    _assert_local_offline_flags_consistent(payload)
    _assert_permission_posture_consistent(payload)
    if payload.get("output_mode") in COMPACT_OUTPUT_MODES:
        _assert_compact_state_consistent(payload)


def _assert_blocked_state_consistent(payload: Mapping[str, object]) -> None:
    """Reject aggregate blocked states that do not name their surface.

    Raises:
        ValueError: If the aggregate blocked status has no blocked surface.
    """
    if payload.get("status") == "blocked":
        blocked_surfaces = _strings(payload.get("blocked_surfaces"))
        if not blocked_surfaces and not str(
            payload.get("blocked_surface") or ""
        ):
            message = (
                "status=blocked requires blocked_surface or blocked_surfaces."
            )
            raise ValueError(message)
    if payload.get("blocked_surface") == "client_handoff" and payload.get(
        "import_status"
    ) == ("blocked"):
        blocked_surfaces = _strings(payload.get("blocked_surfaces"))
        if "make_import" not in blocked_surfaces:
            message = (
                "blocked_surface=client_handoff with import_status=blocked "
                "must also "
                "name make_import as blocked."
            )
            raise ValueError(message)


def _assert_handoff_state_consistent(payload: Mapping[str, object]) -> None:
    """Reject handoff-blocked states without handoff-specific evidence.

    Raises:
        ValueError: If a handoff-blocked state lacks blocker evidence.
    """
    if payload.get("client_handoff_status") == "blocked":
        handoff_risk = payload.get("handoff_risk_summary")
        blocking_count = (
            _int_member(
                cast("Mapping[str, object]", handoff_risk),
                "blocking_error_count",
            )
            if isinstance(handoff_risk, MappingABC)
            else 0
        )
        blocked_surfaces = _strings(payload.get("blocked_surfaces"))
        blocked_surface = payload.get("blocked_surface")
        blocked_by_other_surface = (
            isinstance(blocked_surface, str)
            and blocked_surface not in {"", "client_handoff"}
        ) or any(surface != "client_handoff" for surface in blocked_surfaces)
        explicit_blocker = (
            any(
                payload.get(field) is True
                or payload.get(field) not in {None, False}
                for field in (
                    "operator_blocker ",
                    "external_blocker ",
                    "blocked_reason",
                )
            )
            or blocked_by_other_surface
        )
        if blocking_count <= 0 and not explicit_blocker:
            message = (
                "client_handoff_status=blocked requires handoff risk "
                "blockers or an "
                "explicit operator/external blocker."
            )
            raise ValueError(message)


def _assert_connection_placeholder_consistent(
    payload: Mapping[str, object],
) -> None:
    """Reject payloads that label Make connection placeholders as credentials.

    Raises:
        ValueError: If a response places the Make connection placeholder under a
            credential-named field.
    """
    for _path, key, value in _walk_mapping(payload):
        if "__IMTCONN__" in str(value) and "credential" in key.casefold():
            message = (
                "__IMTCONN__ is a Make connection placeholder, not acredential."
            )
            raise ValueError(message)


def _assert_local_offline_flags_consistent(
    payload: Mapping[str, object],
) -> None:
    """Reject local/offline responses that claim live/provider side effects.

    Raises:
        ValueError: If a local/offline safety flag reports a side effect.
    """
    for path, key, value in _walk_mapping(payload):
        if key in LOCAL_OFFLINE_SIDE_EFFECT_FIELDS and value is True:
            message = (
                f"Local/offline MCP response cannot report {key}=true at{path}."
            )
            raise ValueError(message)


def _assert_permission_posture_consistent(
    payload: Mapping[str, object],
) -> None:
    """Reject write/read permission contradictions in MCP responses.

    Raises:
        ValueError: If the response claims contradictory permission posture.
    """
    writes_performed = payload.get("writes_performed")
    permission_posture = str(payload.get("permission_posture") or "")
    operation_mode = str(payload.get("operation_mode") or "")
    write_actions = payload.get("write_actions")
    write_action_count = (
        len(cast("Sequence[object]", write_actions))
        if isinstance(write_actions, list | tuple)
        else 0
    )
    if writes_performed is True and permission_posture.startswith("read_only_"):
        message = (
            "writes_performed=true cannot use a read_only permission_posture."
        )
        raise ValueError(message)
    if writes_performed is True and operation_mode.startswith("read_only_"):
        message = "writes_performed=true cannot use a read_only operation_mode."
        raise ValueError(message)
    if writes_performed is False and write_action_count:
        message = "writes_performed=false cannot report write_actions."
        raise ValueError(message)
    if (
        permission_posture == READ_ONLY_LOCAL_PERMISSION_POSTURE
        and writes_performed is not False
    ):
        message = "read_only_local_no_approval requires writes_performed=false."
        raise ValueError(message)
    if permission_posture == LOCAL_DRY_RUN_PERMISSION_POSTURE and (
        payload.get("dry_run") is not True or writes_performed is not False
    ):
        message = (
            "local_dry_run_no_write_no_approval requires dry_run=true and "
            "writes_performed=false."
        )
        raise ValueError(message)


def _ordered_surfaces(values: Iterable[str]) -> tuple[str, ...]:
    seen = {str(value) for value in values if str(value)}
    unknown_surfaces = seen.difference(SURFACE_ORDER)
    if unknown_surfaces:
        unknown = ", ".join(sorted(unknown_surfaces))
        message = f"Unknown MCP response surface: {unknown}."
        raise ValueError(message)
    ordered = [surface for surface in SURFACE_ORDER if surface in seen]
    return tuple(ordered)


def _assert_compact_state_consistent(payload: Mapping[str, object]) -> None:
    for path, key, value in _walk_mapping(payload):
        if key in FORBIDDEN_COMPACT_FIELD_NAMES:
            message = f"Compact MCP payload exposed forbidden field {path}."
            raise ValueError(message)
        if key == "scenario_notes" and _sibling_has_summary(path, payload):
            message = (
                "Compact MCP payload duplicated scenario_notes and "
                "scenario_notes_summary."
            )
            raise ValueError(message)
        if isinstance(value, str):
            if any(marker in value for marker in SECRET_MARKERS):
                message = (
                    f"Compact MCP payload exposed secret-like marker at {path}."
                )
                raise ValueError(message)
            normalized = value.replace("\\", "/")
            if normalized.startswith("C:/") or "C:/Users/" in normalized:
                message = (
                    f"Compact MCP payload exposed a local absolute path at"
                    f"{path}."
                )
                raise ValueError(message)


def _walk_mapping(
    value: object,
    path: str = "$",
) -> tuple[tuple[str, str, object], ...]:
    rows: list[tuple[str, str, object]] = []
    if isinstance(value, MappingABC):
        mapping = cast("Mapping[object, object]", value)
        for key, child in mapping.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            rows.append((child_path, key_text, child))
            rows.extend(_walk_mapping(child, child_path))
    elif isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        for index, child in enumerate(sequence):
            rows.extend(_walk_mapping(child, f"{path}[{index}]"))
    return tuple(rows)


def _sibling_has_summary(path: str, payload: Mapping[str, object]) -> bool:
    parent_path = path.rsplit(".", maxsplit=1)[0]
    for current_path, key, _value in _walk_mapping(payload):
        if key == "scenario_notes_summary" and current_path.rsplit(
            ".", maxsplit=1
        )[0] == (parent_path):
            return True
    return False


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        return tuple(str(item) for item in sequence if str(item))
    if isinstance(value, str) and value:
        return (value,)
    return ()


def _validation_status_reason(invalid_surfaces: list[str]) -> str:
    if invalid_surfaces == ["client_handoff"]:
        return (
            "Client handoff notes are incomplete; import-safe artifact "
            "generation remains "
            "available."
        )
    if not invalid_surfaces:
        return "All evaluated validation surfaces are ready or non-blocking."
    if "make_import" in invalid_surfaces:
        return (
            "Make import is blocked by import-surface validation or artifact "
            "generation."
        )
    return "One or more validation surfaces require local remediation."


def _int_member(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0
