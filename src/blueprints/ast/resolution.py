# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# - 001045#repo.make-ast.module-resolution-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Resolve Make AST module nodes against the canonical catalog.

Boundary contract:
- Owns: offline catalog resolution for module-like blueprint AST nodes.
- Must not: fetch raw specs, mutate AST nodes, or validate full blueprint flows.
- Allows: deterministic module matching, unresolved issues, and
  resolution reports.
- Split when: matching heuristics or catalog evidence policy needs ownership.
- Merge when: another resolver returns the same module-resolution report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from catalog.fallback.results import (
    SOURCE_LABEL_KNOWLEDGE_DB,
    SOURCE_LABEL_RAW_SPEC_MANIFEST,
    catalog_source_rank,
)
from catalog.identifiers import (
    module_token_logical_key,
    module_token_match_keys,
    module_version_sort_key,
)
from catalog.validation import validate_catalog_snapshot

from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from catalog.models import CatalogModule, CatalogSnapshot

    from blueprints.ast.models import MakeAstNode, MakeAstRoot

RESOLVED_STATUS: Final = "resolved"
UNRESOLVED_STATUS: Final = "unresolved"
MISSING_RAW_SPEC: Final = "missing_raw_spec"
AMBIGUOUS_MODULE_FAMILY: Final = "ambiguous_module_family"
DEPRECATED_MODULE: Final = "deprecated_module"
UNSUPPORTED_CUSTOM_APP: Final = "unsupported_custom_app"
LEGACY_MODULE_SHAPE: Final = "legacy_module_shape"
INSUFFICIENT_BLUEPRINT_METADATA: Final = "insufficient_blueprint_metadata"
RAW_SPEC_BINDING_VERSION_DRIFT: Final = "raw_spec_binding_version_drift"


class MakeAstModuleResolution(NamedTuple):
    """Catalog resolution result for one AST module-like node."""

    node_id: str
    module_token: str
    status: str
    catalog_module_id: str | None
    app_slug: str | None
    app_version: str | None
    module_kind: str | None
    internal_name: str | None
    module_family: str | None
    parameter_ids: tuple[str, ...]
    expect_field_ids: tuple[str, ...]
    interface_field_ids: tuple[str, ...]
    rpc_dependencies: tuple[str, ...]
    deprecated: bool
    issues: tuple[str, ...]
    raw_spec_references: tuple[str, ...]
    source_label: str | None = None
    source_rank: int | None = None


class MakeAstResolutionReport(NamedTuple):
    """Catalog resolution report for all module-like AST nodes."""

    catalog_fingerprint: str
    resolutions: tuple[MakeAstModuleResolution, ...]


def resolve_ast_modules(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
) -> MakeAstResolutionReport:
    """Resolve all AST module tokens against the canonical catalog.

    Returns:
        The resolved value.
    """
    validate_catalog_snapshot(catalog)
    modules = _catalog_modules(catalog)
    source_label = _catalog_snapshot_source_label(catalog)
    resolutions = tuple(
        _resolve_node(node=node, modules=modules, source_label=source_label)
        for node in iter_ast_nodes(root)
        if node.module_token
    )
    return MakeAstResolutionReport(
        catalog_fingerprint=catalog.fingerprint,
        resolutions=resolutions,
    )


def require_module_resolution(
    report: MakeAstResolutionReport,
    node_id: str,
) -> MakeAstModuleResolution:
    """Return one node resolution or fail loudly.

    Raises:
        LookupError: If a required lookup cannot be resolved.
    """
    for resolution in report.resolutions:
        if resolution.node_id == node_id:
            return resolution
    message = f"No Make AST module resolution exists for node {node_id!r}."
    raise LookupError(message)


def _resolve_node(
    *,
    node: MakeAstNode,
    modules: tuple[CatalogModule, ...],
    source_label: str,
) -> MakeAstModuleResolution:
    """Resolve one AST node against catalog modules.

    Returns:
        The resolved value.
    """
    exact_binding = node.raw_spec_binding.catalog_module_id
    if exact_binding is not None:
        return _resolve_exact_binding(
            node=node,
            modules=modules,
            source_label=source_label,
            exact_binding=exact_binding,
        )

    shape_issue = _shape_issue(node.module_token)
    if shape_issue is not None:
        return _unresolved(node=node, issues=(shape_issue,))

    candidates = _candidate_modules(node.module_token, modules)
    if not candidates:
        return _unresolved(
            node=node, issues=(_missing_module_issue(node.module_token),)
        )
    if len(candidates) > 1:
        return _unresolved(
            node=node,
            issues=(AMBIGUOUS_MODULE_FAMILY, INSUFFICIENT_BLUEPRINT_METADATA),
        )
    preferred_module = _preferred_module_match(candidates)
    if preferred_module is None:
        return _unresolved(
            node=node,
            issues=(AMBIGUOUS_MODULE_FAMILY, INSUFFICIENT_BLUEPRINT_METADATA),
        )
    return _resolved(
        node=node, module=preferred_module, source_label=source_label
    )


def _resolve_exact_binding(
    *,
    node: MakeAstNode,
    modules: tuple[CatalogModule, ...],
    source_label: str,
    exact_binding: str,
) -> MakeAstModuleResolution:
    """Resolve a metadata catalog binding, including safe version refreshes.

    Returns:
        The module resolution for the bound node.
    """
    exact_module = _find_module_by_id(modules, exact_binding)
    shape_issue = _shape_issue(node.module_token)
    candidate_modules = (
        ()
        if shape_issue is not None
        else _candidate_modules(node.module_token, modules)
    )
    refreshed_module = (
        None
        if shape_issue is not None
        else _preferred_module_match(candidate_modules)
    )
    if exact_module is not None:
        if (
            refreshed_module is not None
            and refreshed_module.module_id != exact_module.module_id
        ):
            return _resolved(
                node=node,
                module=refreshed_module,
                source_label=source_label,
                issues=(RAW_SPEC_BINDING_VERSION_DRIFT,),
            )
        return _resolved(
            node=node, module=exact_module, source_label=source_label
        )
    if shape_issue is not None:
        return _unresolved(node=node, issues=(MISSING_RAW_SPEC,))
    if refreshed_module is not None:
        return _resolved(
            node=node,
            module=refreshed_module,
            source_label=source_label,
            issues=(RAW_SPEC_BINDING_VERSION_DRIFT,),
        )
    if candidate_modules:
        return _unresolved(
            node=node,
            issues=(AMBIGUOUS_MODULE_FAMILY, INSUFFICIENT_BLUEPRINT_METADATA),
        )
    return _unresolved(
        node=node, issues=(_missing_module_issue(node.module_token),)
    )


def _resolved(
    *,
    node: MakeAstNode,
    module: CatalogModule,
    source_label: str,
    issues: tuple[str, ...] = (),
) -> MakeAstModuleResolution:
    """Return a resolved AST module binding."""
    resolved_issues = (
        *issues,
        *((DEPRECATED_MODULE,) if module.deprecated else ()),
    )
    return MakeAstModuleResolution(
        node_id=node.node_id,
        module_token=node.module_token,
        status=RESOLVED_STATUS,
        source_label=source_label,
        source_rank=catalog_source_rank(source_label),
        catalog_module_id=module.module_id,
        app_slug=module.app_slug,
        app_version=module.app_version,
        module_kind=module.module_kind,
        internal_name=module.internal_name,
        module_family=f"{module.app_slug}:{module.app_version}:{module.module_kind}",
        parameter_ids=tuple(field.field_id for field in module.parameters),
        expect_field_ids=tuple(
            field.field_id for field in module.expect_schema
        ),
        interface_field_ids=tuple(
            field.field_id for field in module.interface_schema
        ),
        rpc_dependencies=module.rpc_dependencies,
        deprecated=module.deprecated,
        issues=resolved_issues,
        raw_spec_references=(
            module.module_id,
            f"{module.app_slug}:{module.app_version}:{module.module_kind}:{module.internal_name}",
            module.raw_spec_sha256,
        ),
    )


def _unresolved(
    *,
    node: MakeAstNode,
    issues: tuple[str, ...],
) -> MakeAstModuleResolution:
    """Return an unresolved AST module binding."""
    return MakeAstModuleResolution(
        node_id=node.node_id,
        module_token=node.module_token,
        status=UNRESOLVED_STATUS,
        source_label=None,
        source_rank=None,
        catalog_module_id=None,
        app_slug=None,
        app_version=None,
        module_kind=None,
        internal_name=None,
        module_family=None,
        parameter_ids=(),
        expect_field_ids=(),
        interface_field_ids=(),
        rpc_dependencies=(),
        deprecated=False,
        issues=issues,
        raw_spec_references=(),
    )


def _catalog_modules(catalog: CatalogSnapshot) -> tuple[CatalogModule, ...]:
    """Return all catalog modules in stable order."""
    return tuple(
        sorted(
            (
                module
                for app in catalog.apps
                for version in app.versions
                for module in version.modules
            ),
            key=lambda module: module.module_id,
        )
    )


def _catalog_snapshot_source_label(catalog: CatalogSnapshot) -> str:
    """Return the source label implied by one resolution catalog snapshot."""
    if catalog.generated_at_utc == "knowledge-store":
        return SOURCE_LABEL_KNOWLEDGE_DB
    return SOURCE_LABEL_RAW_SPEC_MANIFEST


def _find_module_by_id(
    modules: tuple[CatalogModule, ...],
    module_id: str,
) -> CatalogModule | None:
    """Return a catalog module by exact stable ID."""
    for module in modules:
        if module.module_id == module_id:
            return module
    return None


def _candidate_modules(
    module_token: str,
    modules: tuple[CatalogModule, ...],
) -> tuple[CatalogModule, ...]:
    """Return candidate catalog modules for one AST token."""
    app_slug, raw_action = module_token.split(":", maxsplit=1)
    requested_keys = module_token_match_keys(raw_action)
    candidates = [
        module
        for module in modules
        if module.app_slug.casefold() == app_slug.casefold()
        and requested_keys & _catalog_module_match_keys(module)
    ]
    return tuple(sorted(candidates, key=lambda module: module.module_id))


def _preferred_module_match(
    modules: tuple[CatalogModule, ...],
) -> CatalogModule | None:
    """Return the newest safe module when candidates are one logical family."""
    if not modules:
        return None
    family_keys = {
        (
            module.app_slug.casefold(),
            module.module_kind.casefold(),
            module_token_logical_key(module.internal_name),
        )
        for module in modules
    }
    if len(family_keys) != 1:
        return None
    return min(
        modules,
        key=lambda module: (
            module.deprecated,
            module_version_sort_key(module.app_version),
            module.module_id.casefold(),
        ),
    )


def _catalog_module_match_keys(module: CatalogModule) -> frozenset[str]:
    """Return version-stable token keys that can identify one catalog module."""
    return frozenset(
        (
            *module_token_match_keys(module.internal_name),
            *module_token_match_keys(module.display_name),
            *module_token_match_keys(module.external_id),
        )
    )


def _shape_issue(module_token: str) -> str | None:
    """Return the unresolved shape issue for a module token, if any."""
    if ":" not in module_token:
        return LEGACY_MODULE_SHAPE
    return None


def _missing_module_issue(module_token: str) -> str:
    """Return the unresolved issue for a missing catalog module token."""
    app_slug = module_token.split(":", maxsplit=1)[0].casefold()
    if app_slug.startswith(("custom",)):
        return UNSUPPORTED_CUSTOM_APP
    return MISSING_RAW_SPEC
