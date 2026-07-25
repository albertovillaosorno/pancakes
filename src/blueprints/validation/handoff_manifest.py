# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001061#repo.delivery.client-ready-handoff-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Build client handoff placeholder manifests from validated AST evidence.

Boundary contract:
- Owns: client handoff placeholders and replacement paths from AST/catalog
input.
- Must not: validate full blueprints, mutate AST payloads, or bind live
accounts.
- Allows: deterministic field classification, manifest keys, and seed values.
- Split when: placeholder grouping or client binding policy becomes separate.
- Merge when: another manifest builder emits the same placeholder contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast.references import (
    RuntimePlaceholderUsage,
    collect_runtime_placeholder_usages,
)
from blueprints.ast.resolution import RESOLVED_STATUS, resolve_ast_modules
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.handoff_policy import (
    choose_catalog_field_seed_value,
    classify_catalog_field_binding,
    is_unresolved_handoff_value,
)
from blueprints.validation.importability import placeholder_registry_entries

if TYPE_CHECKING:
    from catalog.models import CatalogField, CatalogModule, CatalogSnapshot

    from blueprints.ast.layout_analysis import BlueprintDesignerDiagnostic
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import (
        BlueprintFindingSeverity,
        BlueprintValidationReport,
        RuntimePlaceholderRegistryEntry,
    )

type HandoffImportabilityStatus = Literal[
    "source_draft ",
    "importable_candidate ",
    "live_make_scenario",
]

BINDING_KINDS = frozenset(("connection", "hook", "dynamic_selector"))
CATALOG_OWNER_PREFIXES: Final = (
    "module.",
    "importability.module.",
    "raw_spec.",
)
OPERATOR_OWNER_PREFIXES: Final = (
    "handoff.",
    "importability.placeholder_",
    "mapping.",
)
BLUEPRINT_OWNER_PREFIXES: Final = (
    "ai_agent.",
    "ast.",
    "importability.router_topology ",
    "output_contract.",
    "router.",
    "semantic.",
)


class HandoffReplacementPath(NamedTuple):
    """One JSON pointer location that must be replaced or bound by a client."""

    json_pointer: str
    node_id: str
    module_token: str
    field_path: str
    binding_kind: str


class HandoffPlaceholder(NamedTuple):
    """One client-facing placeholder manifest item."""

    key: str
    label: str
    description: str
    expected_type: str
    seed_value: object
    client_supplies_value: bool
    bind_in_make: bool
    secret: bool
    required: bool
    replacement_paths: tuple[HandoffReplacementPath, ...]


class HandoffBlockerSummary(NamedTuple):
    """One validation blocker summarized for client handoff readiness."""

    code: str
    json_pointer: str
    severity: BlueprintFindingSeverity
    suggested_owner: str
    message: str


class HandoffWarningSummary(NamedTuple):
    """One nonblocking validation warning summarized for handoff review."""

    code: str
    json_pointer: str
    severity: BlueprintFindingSeverity
    suggested_owner: str
    message: str


class HandoffSecondaryDiagnosticSummary(NamedTuple):
    """One nonblocking secondary diagnostic surfaced for handoff review."""

    code: str
    json_pointer: str
    severity: BlueprintFindingSeverity
    diagnostic_source: str
    node_id: str | None
    message: str


class HandoffEvidenceSource(NamedTuple):
    """One evidence source used to build an offline handoff manifest."""

    source_id: str
    label: str
    detail: str


class BlueprintHandoffReadinessManifest(NamedTuple):
    """Aggregate offline handoff status without creating live-verification.

    claims.
    """

    importability_status: HandoffImportabilityStatus
    live_make_called: bool
    blockers: tuple[HandoffBlockerSummary, ...]
    warnings: tuple[HandoffWarningSummary, ...]
    secondary_diagnostics: tuple[HandoffSecondaryDiagnosticSummary, ...]
    placeholders: tuple[HandoffPlaceholder, ...]
    evidence_sources: tuple[HandoffEvidenceSource, ...]


def build_handoff_placeholder_manifest(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
) -> tuple[HandoffPlaceholder, ...]:
    """Return deterministic client handoff placeholders for one AST root."""
    modules = _catalog_modules_by_id(catalog)
    resolutions = resolve_ast_modules(root=root, catalog=catalog)
    modules_by_node = {
        resolution.node_id: modules[resolution.catalog_module_id]
        for resolution in resolutions.resolutions
        if resolution.status == RESOLVED_STATUS
        and resolution.catalog_module_id is not None
        and resolution.catalog_module_id in modules
    }
    placeholders: dict[str, HandoffPlaceholder] = {}
    for node in iter_ast_nodes(root):
        module = modules_by_node.get(node.node_id)
        if module is None:
            continue
        for field in module.parameters:
            replacement = _replacement_for_field(node=node, field=field)
            if replacement is None:
                continue
            placeholder = _placeholder_for_field(
                field=field, replacement=replacement
            )
            placeholders[placeholder.key] = _merge_placeholder(
                placeholders.get(placeholder.key),
                placeholder,
            )
    for placeholder in _project_registry_placeholders(root):
        placeholders[placeholder.key] = _merge_placeholder(
            placeholders.get(placeholder.key),
            placeholder,
        )
    return tuple(placeholders[key] for key in sorted(placeholders))


def build_handoff_blocker_manifest(
    *,
    report: BlueprintValidationReport,
) -> tuple[HandoffBlockerSummary, ...]:
    """Return deterministic handoff blockers from a validation report."""
    return tuple(
        HandoffBlockerSummary(
            code=finding.code,
            json_pointer=_json_pointer(finding.source_path),
            severity=finding.severity,
            suggested_owner=_suggested_owner(finding.code),
            message=finding.client_message,
        )
        for finding in report.blocking_findings()
    )


def build_handoff_warning_manifest(
    *,
    report: BlueprintValidationReport,
) -> tuple[HandoffWarningSummary, ...]:
    """Return deterministic nonblocking warning summaries from a validation.

    report.
    """
    return tuple(
        HandoffWarningSummary(
            code=finding.code,
            json_pointer=_json_pointer(finding.source_path),
            severity=finding.severity,
            suggested_owner=_suggested_owner(finding.code),
            message=finding.client_message,
        )
        for finding in report.findings
        if finding.severity == "warning"
    )


def build_handoff_secondary_diagnostics_manifest(
    *,
    secondary_diagnostics: tuple[BlueprintDesignerDiagnostic, ...] = (),
) -> tuple[HandoffSecondaryDiagnosticSummary, ...]:
    """Return deterministic nonblocking secondary diagnostics for handoff.

    review.
    """
    return tuple(
        HandoffSecondaryDiagnosticSummary(
            code=diagnostic.code,
            json_pointer=_json_pointer(diagnostic.source_path),
            severity=diagnostic.severity,
            diagnostic_source=diagnostic.diagnostic_source,
            node_id=diagnostic.node_id,
            message=diagnostic.client_message,
        )
        for diagnostic in sorted(
            secondary_diagnostics,
            key=lambda item: (item.code, item.node_id or "", item.source_path),
        )
    )


def build_handoff_readiness_manifest(
    *,
    report: BlueprintValidationReport,
    placeholders: tuple[HandoffPlaceholder, ...],
    importable: bool,
    live_make_called: bool,
    evidence_sources: tuple[HandoffEvidenceSource, ...],
) -> BlueprintHandoffReadinessManifest:
    """Return one aggregate offline handoff manifest from existing evidence."""
    blockers = build_handoff_blocker_manifest(report=report)
    return BlueprintHandoffReadinessManifest(
        importability_status=_handoff_importability_status(
            importable=importable,
            live_make_called=live_make_called,
        ),
        live_make_called=live_make_called,
        blockers=blockers,
        warnings=build_handoff_warning_manifest(report=report),
        secondary_diagnostics=(),
        placeholders=tuple(
            sorted(placeholders, key=lambda placeholder: placeholder.key)
        ),
        evidence_sources=_dedupe_evidence_sources(evidence_sources),
    )


def build_offline_handoff_evidence_sources() -> tuple[
    HandoffEvidenceSource, ...
]:
    """Return canonical offline evidence labels for local handoff reporting."""
    return (
        HandoffEvidenceSource(
            source_id="ast.parse",
            label="AST parser",
            detail="Parsed with blueprints.ast.parse_make_ast_json_text.",
        ),
        HandoffEvidenceSource(
            source_id="validation.importability",
            label="Importability validation",
            detail=(
                "Validated through blueprints.validation.validate_blueprint."
            ),
        ),
        HandoffEvidenceSource(
            source_id="handoff.strict_gate",
            label="Strict handoff gate",
            detail="Checked with guard_blueprint_for_handoff in strict mode.",
        ),
        HandoffEvidenceSource(
            source_id="handoff.placeholder_manifest",
            label="Placeholder manifest",
            detail=(
                "Built from runtime placeholder registry and catalog fields."
            ),
        ),
        HandoffEvidenceSource(
            source_id="delivery.coverage",
            label="Delivery coverage",
            detail=(
                "Summarized from validation findings and placeholder counts."
            ),
        ),
    )


def with_handoff_secondary_diagnostics(
    *,
    manifest: BlueprintHandoffReadinessManifest,
    secondary_diagnostics: tuple[BlueprintDesignerDiagnostic, ...] = (),
) -> BlueprintHandoffReadinessManifest:
    """Return a handoff manifest copy with nonblocking secondary diagnostics.

    attached.
    """
    return BlueprintHandoffReadinessManifest(
        importability_status=manifest.importability_status,
        live_make_called=manifest.live_make_called,
        blockers=manifest.blockers,
        warnings=manifest.warnings,
        secondary_diagnostics=build_handoff_secondary_diagnostics_manifest(
            secondary_diagnostics=secondary_diagnostics,
        ),
        placeholders=manifest.placeholders,
        evidence_sources=manifest.evidence_sources,
    )


def _replacement_for_field(
    *,
    node: MakeAstNode,
    field: CatalogField,
) -> HandoffReplacementPath | None:
    """Return a replacement path when a field needs client handoff."""
    binding_kind = classify_catalog_field_binding(field)
    value = _field_value(node.raw_payload, field)
    needs_handoff = binding_kind in BINDING_KINDS or (
        field.required and is_unresolved_handoff_value(value)
    )
    if not needs_handoff:
        return None
    section = (
        "parameters" if field.direction == "parameter" else field.direction
    )
    return HandoffReplacementPath(
        json_pointer=_json_pointer(
            (*node.source_trace.path, section, *field.path)
        ),
        node_id=node.node_id,
        module_token=node.module_token,
        field_path=".".join(field.path),
        binding_kind=binding_kind,
    )


def _placeholder_for_field(
    *,
    field: CatalogField,
    replacement: HandoffReplacementPath,
) -> HandoffPlaceholder:
    """Return one placeholder manifest item."""
    binding_kind = replacement.binding_kind
    bind_in_make = binding_kind in BINDING_KINDS
    return HandoffPlaceholder(
        key=_manifest_key(replacement.module_token, field),
        label=field.label or replacement.field_path,
        description=_description(field=field, bind_in_make=bind_in_make),
        expected_type=_expected_type(field),
        seed_value=choose_catalog_field_seed_value(field),
        client_supplies_value=field.required or bind_in_make,
        bind_in_make=bind_in_make,
        secret=_secret(field),
        required=field.required,
        replacement_paths=(replacement,),
    )


def _merge_placeholder(
    existing: HandoffPlaceholder | None,
    incoming: HandoffPlaceholder,
) -> HandoffPlaceholder:
    """Merge duplicate placeholder keys across repeated module fields.

    Returns:
        The result produced by merge duplicate placeholder keys across repeated
        module fields.
    """
    if existing is None:
        return incoming
    paths = tuple(
        sorted(
            {*existing.replacement_paths, *incoming.replacement_paths},
            key=lambda path: path.json_pointer,
        )
    )
    return HandoffPlaceholder(
        key=existing.key,
        label=existing.label,
        description=existing.description,
        expected_type=existing.expected_type,
        seed_value=existing.seed_value,
        client_supplies_value=existing.client_supplies_value,
        bind_in_make=existing.bind_in_make,
        secret=existing.secret,
        required=existing.required,
        replacement_paths=paths,
    )


def _project_registry_placeholders(
    root: MakeAstRoot,
) -> tuple[HandoffPlaceholder, ...]:
    """Return manifest placeholders declared by root.

    metadata.placeholder_registry.
    """
    usages_by_placeholder = _runtime_usages_by_placeholder(
        collect_runtime_placeholder_usages(root)
    )
    placeholders: list[HandoffPlaceholder] = []
    for entry in placeholder_registry_entries(root.scenario.metadata):
        usages = usages_by_placeholder.get(entry.placeholder, ())
        if not usages:
            continue
        placeholders.append(
            _placeholder_for_registry_entry(entry=entry, usages=usages)
        )
    return tuple(placeholders)


def _placeholder_for_registry_entry(
    *,
    entry: RuntimePlaceholderRegistryEntry,
    usages: tuple[RuntimePlaceholderUsage, ...],
) -> HandoffPlaceholder:
    return HandoffPlaceholder(
        key=_normalize_manifest_token(entry.placeholder),
        label=_registry_label(entry.placeholder),
        description=entry.handoff_instructions,
        expected_type=entry.expected_type,
        seed_value=f"{{{{{entry.placeholder}}}}}",
        client_supplies_value=entry.required,
        bind_in_make=True,
        secret=_registry_secret(entry),
        required=entry.required,
        replacement_paths=tuple(
            HandoffReplacementPath(
                json_pointer=_json_pointer(usage.expression_path),
                node_id=usage.node_id or "root",
                module_token=usage.module_token,
                field_path=entry.target_path,
                binding_kind=entry.kind,
            )
            for usage in sorted(usages, key=lambda usage: usage.expression_path)
        ),
    )


def _runtime_usages_by_placeholder(
    usages: tuple[RuntimePlaceholderUsage, ...],
) -> dict[str, tuple[RuntimePlaceholderUsage, ...]]:
    grouped: dict[str, list[RuntimePlaceholderUsage]] = {}
    for usage in usages:
        grouped.setdefault(usage.placeholder, []).append(usage)
    return {placeholder: tuple(items) for placeholder, items in grouped.items()}


def _registry_label(placeholder: str) -> str:
    return placeholder.rsplit(".", maxsplit=1)[-1].replace("_", " ").title()


def _registry_secret(entry: RuntimePlaceholderRegistryEntry) -> bool:
    hint_text = (
        f"{entry.placeholder} {entry.expected_type} "
        f"{entry.handoff_instructions}"
    )
    hint = hint_text.casefold()
    return any(
        token in hint for token in ("secret", "password", "token", "api key")
    )


def _field_value(node_payload: JsonObject, field: CatalogField) -> object:
    """Return a node field value from parameters or mapper."""
    containers = (
        ("parameters", "mapper")
        if field.direction == "parameter"
        else (field.direction,)
    )
    for container in containers:
        value = _nested_value(
            _object_or_empty(node_payload.get(container)), field.path
        )
        if value is not None:
            return value
    return None


def _nested_value(payload: JsonObject, path: tuple[str, ...]) -> object:
    """Return a nested value or None."""
    current: object = payload
    for part in path:
        if not _is_json_object(current) or part not in current:
            return None
        current = current[part]
    return current


def _manifest_key(module_token: str, field: CatalogField) -> str:
    """Return a stable manifest key."""
    app_slug = module_token.partition(":")[0] or "module"
    return _normalize_manifest_token(f"{app_slug}_{'_'.join(field.path)}")


def _description(*, field: CatalogField, bind_in_make: bool) -> str:
    """Return client-facing manifest description."""
    if bind_in_make:
        return "Complete this binding in Make after importing the scenario."
    help_text = field.raw_schema.get("help")
    if isinstance(help_text, str) and help_text.strip():
        return help_text.strip()
    return (
        f"Replace or confirm the value for {'.'.join(field.path)} before "
        f"activation."
    )


def _expected_type(field: CatalogField) -> str:
    """Return a manifest expected type label."""
    if field.field_type:
        return field.field_type
    leaf = field.path[-1].casefold()
    if leaf.endswith("url"):
        return "url"
    if leaf.endswith("id"):
        return "id"
    return "text"


def _secret(field: CatalogField) -> bool:
    """Return whether one field likely contains sensitive material."""
    hint = f"{field.path[-1]} {field.label} {field.field_type or ''}".casefold()
    return any(
        token in hint for token in ("secret", "password", "token", "api key")
    )


def _catalog_modules_by_id(
    catalog: CatalogSnapshot,
) -> dict[str, CatalogModule]:
    """Return catalog modules by stable module ID."""
    return {
        module.module_id: module
        for app in catalog.apps
        for version in app.versions
        for module in version.modules
    }


def _json_pointer(path: tuple[AstPathPart, ...]) -> str:
    """Return an RFC-style JSON pointer for one AST path."""
    return "/" + "/".join(_escape_pointer_part(part) for part in path)


def _escape_pointer_part(value: AstPathPart) -> str:
    """Escape one JSON pointer segment.

    Returns:
        The result produced by escape one JSON pointer segment.
    """
    return str(value).replace("~", "~0").replace("/", "~1")


def _normalize_manifest_token(value: str) -> str:
    """Return a lowercase underscore token for manifest keys."""
    token = "".join(
        character if character.isalnum() else "_"
        for character in value.casefold()
    )
    return "_".join(part for part in token.split("_") if part)


def _handoff_importability_status(
    *,
    importable: bool,
    live_make_called: bool,
) -> HandoffImportabilityStatus:
    """Return the strongest handoff claim supported by supplied evidence."""
    _ = live_make_called
    if importable:
        return "importable_candidate"
    return "source_draft"


def _dedupe_evidence_sources(
    evidence_sources: tuple[HandoffEvidenceSource, ...],
) -> tuple[HandoffEvidenceSource, ...]:
    """Return evidence sources keyed by first occurrence of source_id."""
    deduped: dict[str, HandoffEvidenceSource] = {}
    for source in evidence_sources:
        if source.source_id not in deduped:
            deduped[source.source_id] = source
    return tuple(deduped[source_id] for source_id in sorted(deduped))


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object or an empty mapping."""
    return value if _is_json_object(value) else {}


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether one value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)


def _suggested_owner(code: str) -> str:
    """Return the first owner likely able to resolve a validation blocker."""
    if code.startswith(CATALOG_OWNER_PREFIXES):
        return "catalog"
    if code.startswith(OPERATOR_OWNER_PREFIXES):
        return "operator"
    if code.startswith(BLUEPRINT_OWNER_PREFIXES):
        return "blueprint"
    return "validation"
