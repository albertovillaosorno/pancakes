# ruff: noqa: PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001060#repo.architecture.srp.extreme-one-responsibility
# - 001063#repo.architecture.file-boundary.contract-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Importability blockers for locally validated Make blueprints.

Boundary contract:
- Owns: deterministic importability blockers derived from parsed AST payloads.
- Must not: repair blueprints, render JSON, call Make.com, or inspect live
scenarios.
- Allows: node-local scans that emit typed validation findings.
- Split when: router, placeholder, or metadata importability rules diverge.
- Merge when: another module owns the same importability blocker codes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, Literal, TypeGuard, cast

from catalog.generation_audit import (
    CatalogPlanShadowEntry,
    emit_catalog_plan_shadow_event,
)
from catalog.validation import (
    OPERATOR_APPROVED_STUB_ISSUE,
    OPERATOR_APPROVED_STUB_STRICT_HANDOFF_ISSUE,
    resolve_module_token,
)
from languages.make.raw_specs.local_stubs import (
    find_operator_approved_raw_spec_stub,
)

from blueprints.ast.evidence import (
    MAKE_FIELD_COLLECTION_METADATA_KEYS,
    MAKE_OBJECT_METADATA_KEYS,
)
from blueprints.ast.execution_paths import available_node_ids_before
from blueprints.ast.references import (
    MakeReferenceUsage,
    RuntimePlaceholderUsage,
    collect_reference_usages,
    collect_runtime_placeholder_usages,
)
from blueprints.validation.findings import (
    METADATA_RESTORE_SHAPE_CODE,
    build_validation_finding,
)
from blueprints.validation.models import RuntimePlaceholderRegistryEntry
from blueprints.validation.placeholders import (
    IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
    validate_importability_placeholders,
)

if TYPE_CHECKING:
    from catalog.generation_audit import CatalogPlanShadowSink
    from catalog.models import CatalogModuleTokenResolution, CatalogSnapshot
    from languages.make.raw_specs.local_stubs import OperatorApprovedRawSpecStub

    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import BlueprintValidationFinding

type ImportabilityDeliveryMode = Literal[
    "strict_client_handoff", "offline_development"
]

IMPORTABILITY_ROUTER_TOPOLOGY: Final = "importability.router_topology"
IMPORTABILITY_METADATA_INVALID: Final = METADATA_RESTORE_SHAPE_CODE
IMPORTABILITY_MODULE_UNKNOWN: Final = "importability.module.unknown"
IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB: Final = (
    "importability.module.operator_approved_stub"
)
IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED: Final = (
    "importability.error_handler.nested_unsupported"
)
IMPORTABILITY_PLACEHOLDER_UNREGISTERED: Final = (
    "importability.placeholder_unregistered"
)
IMPORTABILITY_PLACEHOLDER_REGISTRY_UNUSED: Final = (
    "importability.placeholder_registry_unused"
)
IMPORTABILITY_PLACEHOLDER_REGISTRY_INCOMPLETE: Final = (
    "importability.placeholder_registry_incomplete"
)
IMPORTABILITY_PLACEHOLDER_REGISTRY_CONFLICT: Final = (
    "importability.placeholder_registry_conflict"
)
IMPORTABILITY_PLACEHOLDER_REGISTRY_TARGET_MISMATCH: Final = (
    "importability.placeholder_registry_target_mismatch"
)
MIN_PLACEHOLDER_REGISTRY_CONFLICT_ENTRIES: Final = 2
RUNTIME_PLACEHOLDER_PREFIX: Final = "runtime."
RUNTIME_PLACEHOLDER_SEGMENT: Final = re.compile(r"^[A-Za-z0-9_]+$")
IMPORTABILITY_REFERENCE_UNAVAILABLE: Final = (
    "importability.reference_unavailable"
)
IMPORTABILITY_FINDING_CODES: Final = frozenset(
    (
        IMPORTABILITY_ROUTER_TOPOLOGY,
        IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
        IMPORTABILITY_PLACEHOLDER_UNREGISTERED,
        IMPORTABILITY_PLACEHOLDER_REGISTRY_UNUSED,
        IMPORTABILITY_PLACEHOLDER_REGISTRY_INCOMPLETE,
        IMPORTABILITY_PLACEHOLDER_REGISTRY_CONFLICT,
        IMPORTABILITY_PLACEHOLDER_REGISTRY_TARGET_MISMATCH,
        IMPORTABILITY_REFERENCE_UNAVAILABLE,
        IMPORTABILITY_METADATA_INVALID,
        IMPORTABILITY_MODULE_UNKNOWN,
        IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB,
        IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED,
    )
)
IMPORTABILITY_RULE_EVIDENCE: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        IMPORTABILITY_ROUTER_TOPOLOGY,
        (
            "local Make AST route shape ",
            "reviewed Make router and filter documentation",
        ),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
        ("local handoff placeholder policy",),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_UNREGISTERED,
        ("local runtime placeholder registry policy",),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_REGISTRY_UNUSED,
        ("local runtime placeholder registry policy",),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_REGISTRY_INCOMPLETE,
        ("local runtime placeholder registry schema",),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_REGISTRY_CONFLICT,
        ("local runtime placeholder registry policy",),
    ),
    (
        IMPORTABILITY_PLACEHOLDER_REGISTRY_TARGET_MISMATCH,
        ("local runtime placeholder registry executable path check",),
    ),
    (
        IMPORTABILITY_REFERENCE_UNAVAILABLE,
        ("local Make AST execution-path availability",),
    ),
    (
        IMPORTABILITY_METADATA_INVALID,
        (
            "local blueprint metadata shape policy ",
            "reviewed Make scenario blueprint API documentation",
        ),
    ),
    (
        IMPORTABILITY_MODULE_UNKNOWN,
        ("local catalog raw-spec module-token resolution",),
    ),
    (
        IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB,
        ("operator-approved local raw-spec stub policy",),
    ),
    (
        IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED,
        ("local Make AST direct error-handler shape policy",),
    ),
)
IMPORTABILITY_RULE_EXTERNAL_BIBLIOGRAPHY: Final[
    tuple[tuple[str, tuple[str, ...]], ...]
] = (
    (
        IMPORTABILITY_ROUTER_TOPOLOGY,
        (
            "docs/bibliography/make-router-topology.md ",
            "docs/bibliography/make-filter-expressions.md",
        ),
    ),
    (
        IMPORTABILITY_METADATA_INVALID,
        ("docs/bibliography/make.com.md",),
    ),
)
UNSAFE_NOTE_CONTENT_MARKERS: Final[tuple[str, ...]] = (
    "<script",
    "</script",
    "<iframe",
    "</iframe",
    "<object",
    "</object",
    "<embed",
    "</embed ",
    "javascript:",
    "{{",
    "}}",
    "{%",
    "%}",
)
DIRECT_ERROR_KEYS: Final[tuple[str, ...]] = ("onerror", "on_error")


def placeholder_registry_entries(
    metadata: JsonObject,
) -> tuple[RuntimePlaceholderRegistryEntry, ...]:
    """Return the computed result for the caller."""
    entries, _ = _parse_placeholder_registry(metadata)
    return entries


def validate_importability(
    nodes: tuple[MakeAstNode, ...],
    catalog: CatalogSnapshot | None = None,
    *,
    root: MakeAstRoot | None = None,
    operator_approved_stubs: tuple[OperatorApprovedRawSpecStub, ...] = (),
    delivery_mode: ImportabilityDeliveryMode = "strict_client_handoff",
    telemetry: CatalogPlanShadowSink | None = None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic importability blockers for parsed AST nodes."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        findings.extend(
            validate_importability_placeholders(node, telemetry=telemetry)
        )
        findings.extend(
            _validate_node_make_metadata(node, delivery_mode=delivery_mode)
        )
        findings.extend(_validate_error_handler_importability(node))
        _emit_router_topology_event(telemetry=telemetry, node=node)
        if catalog is not None and node.module_token:
            token_resolution = resolve_module_token(
                catalog,
                node.module_token,
                operator_approved_stubs=operator_approved_stubs,
                offline_development=delivery_mode == "offline_development",
            )
            _emit_module_resolution_event(
                telemetry=telemetry,
                node=node,
                token_resolution=token_resolution,
            )
            if token_resolution.issue in {
                OPERATOR_APPROVED_STUB_ISSUE,
                OPERATOR_APPROVED_STUB_STRICT_HANDOFF_ISSUE,
            }:
                findings.append(
                    _operator_approved_stub_finding(
                        node=node,
                        token_resolution=token_resolution,
                        operator_approved_stubs=operator_approved_stubs,
                        delivery_mode=delivery_mode,
                    )
                )
            elif not token_resolution.known:
                findings.append(
                    _unknown_module_token_finding(
                        node=node,
                        token_resolution=token_resolution,
                    )
                )
    if root is not None:
        findings.extend(
            _validate_root_make_metadata(root, delivery_mode=delivery_mode)
        )
        findings.extend(_validate_placeholder_registry(root))
        findings.extend(_validate_flow_scope_references(root=root, nodes=nodes))
    return tuple(findings)


def _validate_error_handler_importability(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate unsupported nested direct error-handler shapes for.

    importability.

    Returns:
        Importability findings for one node's unsupported nested error handlers.
    """
    findings: list[BlueprintValidationFinding] = []
    for error_key in DIRECT_ERROR_KEYS:
        if error_key not in node.raw_payload:
            continue
        findings.extend(
            _validate_error_handler_container(
                value=node.raw_payload[error_key],
                node_id=node.node_id,
                path=(*node.source_trace.path, error_key),
            )
        )
    return tuple(findings)


def _validate_error_handler_container(
    *,
    value: object,
    node_id: str,
    path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate one direct onerror or on_error container for nested handlers.

    Returns:
        Importability findings for unsupported nested direct error-handler
        containers.
    """
    if isinstance(value, list):
        findings: list[BlueprintValidationFinding] = []
        for index, item in enumerate(cast("list[object]", value)):
            findings.extend(
                _validate_error_handler_item(
                    value=item,
                    node_id=node_id,
                    path=(*path, index),
                )
            )
        return tuple(findings)
    if not _is_json_object(value):
        return ()
    return _validate_error_handler_item(value=value, node_id=node_id, path=path)


def _validate_error_handler_item(
    *,
    value: object,
    node_id: str,
    path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate one direct error-handler module or flow wrapper for nested.

    handlers.

    Returns:
        Importability findings for unsupported nested direct error-handler
        containers.
    """
    if not _is_json_object(value):
        return ()
    item_node_id = _json_node_id(value, fallback=node_id)
    findings: list[BlueprintValidationFinding] = list(
        _nested_error_handler_findings(
            value=value,
            node_id=item_node_id,
            path=path,
        )
    )
    flow = value.get("flow")
    if not isinstance(flow, list):
        return tuple(findings)
    for index, child in enumerate(cast("list[object]", flow)):
        findings.extend(
            _validate_error_handler_item(
                value=child,
                node_id=item_node_id,
                path=(*path, "flow", index),
            )
        )
    return tuple(findings)


def _nested_error_handler_findings(
    *,
    value: JsonObject,
    node_id: str,
    path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return unsupported nested direct error-handler containers."""
    return tuple(
        _error_handler_nested_unsupported_finding(
            node_id=node_id,
            path=(*path, error_key),
        )
        for error_key in DIRECT_ERROR_KEYS
        if error_key in value
    )


def _json_node_id(value: JsonObject, *, fallback: str) -> str:
    """Return the computed result for the caller."""
    raw_id = value.get("id")
    if isinstance(raw_id, bool) or raw_id is None:
        return fallback
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    if isinstance(raw_id, int) and raw_id > 0:
        return str(raw_id)
    return fallback


def _validate_root_make_metadata(
    root: MakeAstRoot,
    *,
    delivery_mode: ImportabilityDeliveryMode,
) -> tuple[BlueprintValidationFinding, ...]:
    return _validate_make_metadata(
        metadata=root.scenario.metadata,
        node_id=None,
        path=("metadata",),
        delivery_mode=delivery_mode,
        validate_note_shape=False,
    )


def _validate_node_make_metadata(
    node: MakeAstNode,
    *,
    delivery_mode: ImportabilityDeliveryMode,
) -> tuple[BlueprintValidationFinding, ...]:
    metadata = node.raw_payload.get("metadata")
    if not _is_json_object(metadata):
        return ()
    return _validate_make_metadata(
        metadata=metadata,
        node_id=node.node_id,
        path=(*node.source_trace.path, "metadata"),
        delivery_mode=delivery_mode,
        validate_note_shape=True,
    )


def _validate_make_metadata(
    *,
    metadata: JsonObject,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
    delivery_mode: ImportabilityDeliveryMode,
    validate_note_shape: bool,
) -> tuple[BlueprintValidationFinding, ...]:
    findings: list[BlueprintValidationFinding] = []
    for key in MAKE_FIELD_COLLECTION_METADATA_KEYS:
        if key not in metadata:
            continue
        findings.extend(
            _validate_metadata_field_collection(
                value=metadata[key],
                node_id=node_id,
                path=(*path, key),
                key=key,
            )
        )
    for key in MAKE_OBJECT_METADATA_KEYS:
        if key not in metadata or _is_json_object(metadata[key]):
            continue
        findings.append(
            _metadata_invalid_finding(
                node_id=node_id,
                path=(*path, key),
                detail=f"metadata.{key} must be a JSON object when present.",
            )
        )
    if delivery_mode == "strict_client_handoff" and "notes" in metadata:
        findings.extend(
            _validate_metadata_notes(
                value=metadata["notes"],
                node_id=node_id,
                path=(*path, "notes"),
                validate_note_shape=validate_note_shape,
            )
        )
    return tuple(findings)


def _validate_metadata_notes(
    *,
    value: object,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
    validate_note_shape: bool,
) -> tuple[BlueprintValidationFinding, ...]:
    if not isinstance(value, list):
        if not validate_note_shape:
            return ()
        return (
            _note_shape_finding(
                code="ast.notes_invalid",
                node_id=node_id,
                path=path,
                detail="Metadata notes must be a list.",
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    for index, item in enumerate(cast("list[object]", value)):
        note_path = (*path, index)
        if not _is_json_object(item):
            if validate_note_shape:
                findings.append(
                    _note_shape_finding(
                        code="ast.note_invalid",
                        node_id=node_id,
                        path=note_path,
                        detail=f"Metadata note {index + 1} must be an object.",
                    )
                )
            continue
        findings.extend(
            _validate_note_content(note=item, node_id=node_id, path=note_path)
        )
    return tuple(findings)


def _validate_note_content(
    *,
    note: JsonObject,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    findings: list[BlueprintValidationFinding] = []
    for key in ("content", "html", "text"):
        value = note.get(key)
        if value is None:
            continue
        content_path = (*path, key)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                _note_shape_finding(
                    code="ast.note_content_invalid",
                    node_id=node_id,
                    path=content_path,
                    detail=f"Metadata note {key} must be a non-empty string.",
                )
            )
            continue
        if _contains_unsafe_note_content(value):
            findings.append(
                _metadata_invalid_finding(
                    node_id=node_id,
                    path=content_path,
                    detail=(
                        "metadata.notes content must not contain active "
                        "HTML or "
                        ""
                        "template delimiters for strict client handoff."
                    ),
                )
            )
    return tuple(findings)


def _contains_unsafe_note_content(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in UNSAFE_NOTE_CONTENT_MARKERS)


def _note_shape_finding(
    *,
    code: str,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
    detail: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=code,
        severity="error",
        node=(node_id, path),
        catalog_module_id=None,
        messages=(
            "Make metadata notes do not match the expected object shape.",
            detail,
        ),
    )


def _validate_metadata_field_collection(
    *,
    value: object,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
    key: str,
) -> tuple[BlueprintValidationFinding, ...]:
    if not isinstance(value, list):
        return (
            _metadata_invalid_finding(
                node_id=node_id,
                path=path,
                detail=(
                    f"metadata.{key} must be a list of field objects when "
                    f"present."
                ),
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    for index, item in enumerate(cast("list[object]", value)):
        if _is_json_object(item):
            continue
        findings.append(
            _metadata_invalid_finding(
                node_id=node_id,
                path=(*path, index),
                detail=f"metadata.{key}[{index}] must be a JSON object.",
            )
        )
    return tuple(findings)


def _metadata_invalid_finding(
    *,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
    detail: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_METADATA_INVALID,
        severity="error",
        node=(node_id, path),
        catalog_module_id=None,
        messages=(
            "A Make metadata field has an invalid shape.",
            detail,
        ),
    )


def _error_handler_nested_unsupported_finding(
    *,
    node_id: str,
    path: tuple[AstPathPart, ...],
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED,
        severity="error",
        node=(node_id, path),
        catalog_module_id=None,
        messages=(
            "An error handler has an unsupported nested error-handler shape.",
            (
                f"Nested direct error-handler container at {path!r} is "
                f"preserved by "
                "the parser but is not supported for importable handoff."
            ),
        ),
    )


def _validate_flow_scope_references(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    node_ids = {node.node_id for node in nodes}
    findings: list[BlueprintValidationFinding] = []
    seen: set[tuple[str, str, tuple[AstPathPart, ...]]] = set()
    for usage in collect_reference_usages(root):
        if (
            usage.consumer_node_id not in node_ids
            or usage.source_node_id not in node_ids
        ):
            continue
        if usage.source_node_id == usage.consumer_node_id:
            continue
        available_ids = available_node_ids_before(root, usage.consumer_node_id)
        if usage.source_node_id in available_ids:
            continue
        signature = (
            usage.consumer_node_id,
            usage.source_node_id,
            usage.expression_path,
        )
        if signature in seen:
            continue
        seen.add(signature)
        findings.append(
            _unavailable_reference_finding(
                usage=usage, available_ids=available_ids
            )
        )
    return tuple(findings)


def _validate_placeholder_registry(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    usages = collect_runtime_placeholder_usages(root)
    entries, shape_issues = _parse_placeholder_registry(root.scenario.metadata)
    findings: list[BlueprintValidationFinding] = [
        _placeholder_registry_incomplete_finding(path=path, detail=detail)
        for path, detail in shape_issues
    ]
    entries_by_placeholder = _entries_by_placeholder(entries)
    usages_by_placeholder = _usages_by_placeholder(usages)
    for matching_entries in entries_by_placeholder.values():
        conflict = _conflicting_placeholder_registry_entry(matching_entries)
        if conflict is not None:
            findings.append(_conflicting_placeholder_registry_finding(conflict))
    for placeholder, matching_entries in sorted(entries_by_placeholder.items()):
        placeholder_usages = usages_by_placeholder.get(placeholder, ())
        if not placeholder_usages:
            continue
        actual_paths = frozenset(
            _json_pointer(usage.expression_path) for usage in placeholder_usages
        )
        findings.extend(
            _placeholder_registry_target_mismatch_finding(
                entry=entry,
                actual_paths=actual_paths,
            )
            for entry in matching_entries
            if entry.target_path not in actual_paths
        )
    for placeholder, placeholder_usages in sorted(
        usages_by_placeholder.items()
    ):
        matching_entries = entries_by_placeholder.get(placeholder, ())
        if not matching_entries:
            findings.append(
                _unregistered_placeholder_finding(placeholder_usages[0])
            )
            continue
    findings.extend(
        _unused_placeholder_registry_finding(entry)
        for entry in entries
        if entry.placeholder not in usages_by_placeholder
    )
    return tuple(findings)


def _parse_placeholder_registry(
    metadata: JsonObject,
) -> tuple[
    tuple[RuntimePlaceholderRegistryEntry, ...],
    tuple[tuple[tuple[AstPathPart, ...], str], ...],
]:
    registry = metadata.get("placeholder_registry")
    if registry is None:
        return (), ()
    if not isinstance(registry, list):
        return (), (
            (
                ("metadata", "placeholder_registry"),
                "placeholder_registry must be a list.",
            ),
        )
    entries: list[RuntimePlaceholderRegistryEntry] = []
    issues: list[tuple[tuple[AstPathPart, ...], str]] = []
    for index, item in enumerate(cast("list[object]", registry)):
        path = ("metadata", "placeholder_registry", index)
        if not _is_json_object(item):
            issues.append(
                (path, "placeholder registry entries must be JSON objects.")
            )
            continue
        entry = _placeholder_registry_entry(item, source_path=path)
        if entry is None:
            issues.append((path, _placeholder_registry_entry_error(item)))
            continue
        entries.append(entry)
    return tuple(entries), tuple(issues)


def _placeholder_registry_entry(
    payload: JsonObject,
    *,
    source_path: tuple[AstPathPart, ...],
) -> RuntimePlaceholderRegistryEntry | None:
    strings = _placeholder_registry_strings(payload)
    required = payload.get("required")
    if strings is None or not isinstance(required, bool):
        return None
    placeholder, kind, target_path, expected_type, handoff_instructions = (
        strings
    )
    return RuntimePlaceholderRegistryEntry(
        placeholder=placeholder,
        kind=kind,
        target_path=target_path,
        required=required,
        expected_type=expected_type,
        handoff_instructions=handoff_instructions,
        source_path=source_path,
    )


def _placeholder_registry_strings(
    payload: JsonObject,
) -> tuple[str, str, str, str, str] | None:
    placeholder = _required_string(payload, "placeholder")
    if placeholder is None or not _is_runtime_placeholder_identifier(
        placeholder
    ):
        return None
    values = (
        placeholder,
        _required_string(payload, "kind"),
        _required_string(payload, "target_path"),
        _required_string(payload, "expected_type"),
        _required_string(payload, "handoff_instructions"),
    )
    if any(value is None for value in values):
        return None
    return cast("tuple[str, str, str, str, str]", values)


def _placeholder_registry_entry_error(payload: JsonObject) -> str:
    missing = [
        key
        for key in (
            "placeholder ",
            "kind ",
            "target_path ",
            "required ",
            "expected_type ",
            "handoff_instructions",
        )
        if key not in payload
    ]
    if missing:
        return f"missing required fields: {', '.join(missing)}."
    if not isinstance(payload.get("required"), bool):
        return "required must be a boolean."
    placeholder = payload.get("placeholder")
    if isinstance(placeholder, str) and not placeholder.startswith("runtime."):
        return "placeholder must start with runtime."
    if isinstance(placeholder, str) and not _is_runtime_placeholder_identifier(
        placeholder
    ):
        return "placeholder must be a dotted runtime identifier."
    return "required registry fields must be non-empty strings."


def _is_runtime_placeholder_identifier(placeholder: str) -> bool:
    if not placeholder.startswith(RUNTIME_PLACEHOLDER_PREFIX):
        return False
    suffix = placeholder.removeprefix(RUNTIME_PLACEHOLDER_PREFIX)
    parts = suffix.split(".")
    return bool(parts) and all(
        RUNTIME_PLACEHOLDER_SEGMENT.fullmatch(part) for part in parts
    )


def _required_string(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _entries_by_placeholder(
    entries: tuple[RuntimePlaceholderRegistryEntry, ...],
) -> dict[str, tuple[RuntimePlaceholderRegistryEntry, ...]]:
    grouped: dict[str, list[RuntimePlaceholderRegistryEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.placeholder, []).append(entry)
    return {placeholder: tuple(items) for placeholder, items in grouped.items()}


def _conflicting_placeholder_registry_entry(
    entries: tuple[RuntimePlaceholderRegistryEntry, ...],
) -> RuntimePlaceholderRegistryEntry | None:
    if len(entries) < MIN_PLACEHOLDER_REGISTRY_CONFLICT_ENTRIES:
        return None
    baseline = _placeholder_registry_conflict_signature(entries[0])
    for entry in entries[1:]:
        if _placeholder_registry_conflict_signature(entry) != baseline:
            return entry
    return None


def _placeholder_registry_conflict_signature(
    entry: RuntimePlaceholderRegistryEntry,
) -> tuple[str, str, bool, str]:
    return (entry.kind, entry.target_path, entry.required, entry.expected_type)


def _usages_by_placeholder(
    usages: tuple[RuntimePlaceholderUsage, ...],
) -> dict[str, tuple[RuntimePlaceholderUsage, ...]]:
    grouped: dict[str, list[RuntimePlaceholderUsage]] = {}
    for usage in usages:
        grouped.setdefault(usage.placeholder, []).append(usage)
    return {placeholder: tuple(items) for placeholder, items in grouped.items()}


def _unavailable_reference_finding(
    *,
    usage: MakeReferenceUsage,
    available_ids: frozenset[str],
) -> BlueprintValidationFinding:
    available = ", ".join(sorted(available_ids)) or "none"
    return build_validation_finding(
        code=IMPORTABILITY_REFERENCE_UNAVAILABLE,
        severity="error",
        node=(usage.consumer_node_id, usage.expression_path),
        catalog_module_id=None,
        messages=(
            (
                "A mapping or filter references a module unavailable on this "
                "execution path."
            ),
            (
                f"Node {usage.consumer_node_id} references node "
                f"{usage.source_node_id!r} "
                f"at {usage.expression_path!r}, but the available upstream "
                f"nodes are: "
                f"{available}."
            ),
        ),
    )


def _placeholder_registry_incomplete_finding(
    *,
    path: tuple[AstPathPart, ...],
    detail: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_REGISTRY_INCOMPLETE,
        severity="error",
        node=(None, path),
        catalog_module_id=None,
        messages=(
            "A runtime placeholder registry entry is incomplete.",
            (
                f"Runtime placeholder registry entry at {path!r} is invalid: "
                f"{detail}"
            ),
        ),
    )


def _unregistered_placeholder_finding(
    usage: RuntimePlaceholderUsage,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_UNREGISTERED,
        severity="error",
        node=(usage.node_id, usage.expression_path),
        catalog_module_id=None,
        messages=(
            "A runtime placeholder is used but not registered for handoff.",
            (
                f"Runtime placeholder {usage.placeholder!r} at "
                f"{usage.expression_path!r} "
                f"is missing from metadata.placeholder_registry; suggested "
                f"registry entry: "
                f"{_suggested_registry_entry(usage)}."
            ),
        ),
    )


def _conflicting_placeholder_registry_finding(
    entry: RuntimePlaceholderRegistryEntry,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_REGISTRY_CONFLICT,
        severity="error",
        node=(None, entry.source_path),
        catalog_module_id=None,
        messages=(
            (
                "A runtime placeholder registry entry conflicts with another "
                "entry."
            ),
            (
                f"Runtime placeholder {entry.placeholder!r} has conflicting "
                f"registry "
                f"metadata at {entry.source_path!r}; kind, target_path, "
                f"required, and "
                "expected_type must match for duplicate placeholder "
                "declarations."
            ),
        ),
    )


def _placeholder_registry_target_mismatch_finding(
    *,
    entry: RuntimePlaceholderRegistryEntry,
    actual_paths: frozenset[str],
) -> BlueprintValidationFinding:
    actual = ", ".join(sorted(actual_paths)) or "none"
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_REGISTRY_TARGET_MISMATCH,
        severity="error",
        node=(None, entry.source_path),
        catalog_module_id=None,
        messages=(
            (
                "A runtime placeholder registry target does not match the "
                "blueprint "
                "field."
            ),
            (
                f"Runtime placeholder {entry.placeholder!r} declares "
                f"target_path "
                f"{entry.target_path!r} at {entry.source_path!r}, but "
                f"executable "
                f"placeholder usage paths are: {actual}."
            ),
        ),
    )


def _unused_placeholder_registry_finding(
    entry: RuntimePlaceholderRegistryEntry,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_REGISTRY_UNUSED,
        severity="warning",
        node=(None, entry.source_path),
        catalog_module_id=None,
        messages=(
            (
                "A runtime placeholder registry entry is not used by the "
                "blueprint."
            ),
            (
                f"Runtime placeholder {entry.placeholder!r} is registered at "
                f"{entry.source_path!r} but was not found in executable "
                f"placeholder fields."
            ),
        ),
    )


def _suggested_registry_entry(usage: RuntimePlaceholderUsage) -> str:
    expected_type = _suggested_expected_type(usage.placeholder)
    return (
        "{"
        f"'placeholder': '{usage.placeholder}', "
        "'kind': 'runtime_setup', "
        f"'target_path': '{_json_pointer(usage.expression_path)}', "
        "'required': true, "
        f"'expected_type': '{expected_type}', "
        "'handoff_instructions': 'Describe how the operator should supply this "
        "value.'"
        "}"
    )


def _suggested_expected_type(placeholder: str) -> str:
    leaf = placeholder.rsplit(".", maxsplit=1)[-1].casefold()
    if leaf.endswith("hook") or "hook" in leaf:
        return "hook_id"
    if leaf.endswith("url") or "url" in leaf:
        return "url"
    if leaf.endswith(("id", "store")):
        return "id"
    return "text"


def _emit_module_resolution_event(
    *,
    telemetry: CatalogPlanShadowSink | None,
    node: MakeAstNode,
    token_resolution: CatalogModuleTokenResolution,
) -> None:
    outcome = (
        "catalog_confirmed"
        if token_resolution.known
        else token_resolution.issue or "unresolved"
    )
    emit_catalog_plan_shadow_event(
        telemetry,
        CatalogPlanShadowEntry(
            sequence=0,
            source="blueprints.validation.importability",
            decision="module_resolution",
            rule="catalog.module_token_resolution",
            outcome=outcome,
            inputs=(
                ("node_id", node.node_id),
                ("module", token_resolution.module_token),
                ("source_path", node.source_trace.path),
            ),
            provenance=(
                ("catalog_module_id", token_resolution.catalog_module_id),
                ("app_slug", token_resolution.app_slug),
                ("app_version", token_resolution.app_version),
                ("raw_spec_sha256", token_resolution.raw_spec_sha256),
            ),
        ),
    )


def _emit_router_topology_event(
    *,
    telemetry: CatalogPlanShadowSink | None,
    node: MakeAstNode,
) -> None:
    if node.kind != "router":
        return
    emit_catalog_plan_shadow_event(
        telemetry,
        CatalogPlanShadowEntry(
            sequence=0,
            source="blueprints.validation.importability",
            decision="router_topology_validation",
            rule=IMPORTABILITY_ROUTER_TOPOLOGY,
            outcome="routes_present" if node.routes else "routes_missing",
            inputs=(
                ("node_id", node.node_id),
                ("route_count", len(node.routes)),
                ("source_path", node.source_trace.path),
            ),
        ),
    )


def _json_pointer(path: tuple[AstPathPart, ...]) -> str:
    return "/" + "/".join(_escape_pointer_part(part) for part in path)


def _escape_pointer_part(value: AstPathPart) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _operator_approved_stub_finding(
    *,
    node: MakeAstNode,
    token_resolution: CatalogModuleTokenResolution,
    operator_approved_stubs: tuple[OperatorApprovedRawSpecStub, ...],
    delivery_mode: ImportabilityDeliveryMode,
) -> BlueprintValidationFinding:
    stub = find_operator_approved_raw_spec_stub(
        module_token=token_resolution.module_token,
        stubs=operator_approved_stubs,
    )
    unsupported_fields = (
        "none" if stub is None else ", ".join(stub.unsupported_fields)
    )
    source = "unknown" if stub is None else stub.source
    approval_timestamp = "unknown" if stub is None else stub.approval_timestamp
    return build_validation_finding(
        code=IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB,
        severity="warning"
        if delivery_mode == "offline_development"
        else "error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            _operator_approved_stub_client_message(delivery_mode),
            (
                f"Node {node.node_id} uses module token "
                f"{token_resolution.module_token!r} "
                f"with only operator-approved local raw-spec stub evidence "
                f"from {source!r} "
                f"approved at {approval_timestamp!r}; unsupported fields: "
                f"{unsupported_fields}."
            ),
        ),
    )


def _operator_approved_stub_client_message(
    delivery_mode: ImportabilityDeliveryMode,
) -> str:
    """Return client-safe wording for a local raw-spec stub finding."""
    if delivery_mode == "offline_development":
        return (
            "A blueprint module uses local raw-spec stub evidence for offline "
            "development."
        )
    return (
        "A blueprint module still needs Make raw-spec evidence before client "
        "handoff."
    )


def _unknown_module_token_finding(
    *,
    node: MakeAstNode,
    token_resolution: CatalogModuleTokenResolution,
) -> BlueprintValidationFinding:
    available_versions = (
        ", ".join(token_resolution.available_versions) or "none"
    )
    app_slug = token_resolution.app_slug or "unknown"
    return build_validation_finding(
        code=IMPORTABILITY_MODULE_UNKNOWN,
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A blueprint module token is not present in the catalog.",
            (
                f"Node {node.node_id} uses module token "
                f"{token_resolution.module_token!r} "
                f"at {node.source_trace.path!r}; catalog app {app_slug!r} has "
                f"available versions: {available_versions}."
            ),
        ),
    )
