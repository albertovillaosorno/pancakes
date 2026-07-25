# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Placeholder importability checks for Make blueprint payloads.

Boundary contract:
- Owns: unresolved handoff placeholder detection in executable node mappings.
- Must not: resolve catalog modules, validate routes, or mutate payloads.
- Allows: local AST node scans, telemetry events, and typed validation findings.
- Split when: placeholder registry reconciliation needs independent data models.
- Merge when: another module owns the same placeholder finding behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard, cast

from catalog.generation_audit import (
    CatalogPlanShadowEntry,
    emit_catalog_plan_shadow_event,
)

from blueprints.validation.findings import (
    UNRESOLVED_PLACEHOLDER_CODE,
    build_validation_finding,
)

if TYPE_CHECKING:
    from catalog.generation_audit import CatalogPlanShadowSink

    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

IMPORTABILITY_PLACEHOLDER_UNRESOLVED: Final = UNRESOLVED_PLACEHOLDER_CODE
PLACEHOLDER_TOKENS: Final[tuple[str, ...]] = (
    "{{todo",
    "__todo__",
    "<todo",
    "todo:",
)


def validate_importability_placeholders(
    node: MakeAstNode,
    *,
    telemetry: CatalogPlanShadowSink | None = None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return unresolved handoff placeholder findings for one AST node."""
    findings: list[BlueprintValidationFinding] = []
    for key in ("parameters", "mapper"):
        payload = node.raw_payload.get(key)
        if not _is_json_object(payload):
            continue
        for path, value in _string_items(payload, path=(key,)):
            if _has_unresolved_placeholder(value):
                _emit_placeholder_registry_event(
                    telemetry=telemetry,
                    node=node,
                    path=path,
                    value=value,
                )
                findings.append(_placeholder_finding(node=node, path=path))
    return tuple(findings)


def _emit_placeholder_registry_event(
    *,
    telemetry: CatalogPlanShadowSink | None,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    value: str,
) -> None:
    emit_catalog_plan_shadow_event(
        telemetry,
        CatalogPlanShadowEntry(
            sequence=0,
            source="blueprints.validation.placeholders",
            decision="placeholder_registry_mismatch",
            rule=IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
            outcome="unresolved_placeholder",
            inputs=(
                ("node_id", node.node_id),
                ("field_path", path),
                ("value", value),
            ),
        ),
    )


def _placeholder_finding(
    *,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
        severity="error",
        node=(node.node_id, (*node.source_trace.path, *path)),
        catalog_module_id=None,
        messages=(
            "A blueprint field contains an unresolved handoff placeholder.",
            f"Node {node.node_id} has unresolved placeholder text at {path!r}.",
        ),
    )


def _string_items(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[tuple[AstPathPart, ...], str], ...]:
    if isinstance(value, str):
        return ((path, value),)
    if _is_json_object(value):
        items: list[tuple[tuple[AstPathPart, ...], str]] = []
        for key, item in value.items():
            items.extend(_string_items(item, path=(*path, key)))
        return tuple(items)
    if isinstance(value, list):
        items = []
        for index, item in enumerate(cast("list[object]", value)):
            items.extend(_string_items(item, path=(*path, index)))
        return tuple(items)
    return ()


def _has_unresolved_placeholder(value: str) -> bool:
    normalized = value.casefold()
    return any(token in normalized for token in PLACEHOLDER_TOKENS)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)
