# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001045#repo.make-ast.module-resolution.family-lineage
# - 001049#repo.blueprint-repair.offline-action-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Assess catalog-backed AST module migration safety.

Boundary contract:
- Owns: pure compatibility assessment between two resolved module records.
- Must not: rewrite AST nodes, query catalogs, or choose replacement modules.
- Allows: deterministic reason collection from already-resolved module evidence.
- Split when: migration scoring or recommendation planning becomes separate.
- Merge when: another migration file owns the same pure assessment outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from blueprints.ast.resolution import RESOLVED_STATUS

if TYPE_CHECKING:
    from blueprints.ast.resolution import MakeAstModuleResolution


class ModuleMigrationAssessment(NamedTuple):
    """Safety assessment for one proposed module migration."""

    node_id: str
    before_module_token: str
    after_module_token: str
    safe: bool
    reasons: tuple[str, ...]


def assess_module_migration(
    *,
    current: MakeAstModuleResolution,
    target: MakeAstModuleResolution,
) -> ModuleMigrationAssessment:
    """Assess whether one catalog resolution can replace another offline.

    Returns:
        The result produced by assessing whether one catalog resolution can
        replace another offline.
    """
    reasons = [
        *_resolution_reasons("current", current),
        *_resolution_reasons("target", target),
        *_compatibility_reasons(current=current, target=target),
    ]
    return ModuleMigrationAssessment(
        node_id=current.node_id,
        before_module_token=current.module_token,
        after_module_token=target.module_token,
        safe=not reasons,
        reasons=tuple(sorted(set(reasons))),
    )


def _resolution_reasons(
    label: str, resolution: MakeAstModuleResolution
) -> tuple[str, ...]:
    """Return reasons tied to one resolution state."""
    if resolution.status != RESOLVED_STATUS:
        return (f"{label} module is unresolved",)
    return ()


def _compatibility_reasons(
    *,
    current: MakeAstModuleResolution,
    target: MakeAstModuleResolution,
) -> tuple[str, ...]:
    """Return deterministic migration compatibility failures."""
    reasons: list[str] = []
    if current.app_slug != target.app_slug:
        reasons.append("app slug changes")
    if current.module_kind != target.module_kind:
        reasons.append("module kind changes")
    if not set(target.parameter_ids).issuperset(current.parameter_ids):
        reasons.append("target loses parameter fields")
    if not set(target.interface_field_ids).issuperset(
        current.interface_field_ids
    ):
        reasons.append("target loses output fields")
    if not set(target.rpc_dependencies).issuperset(current.rpc_dependencies):
        reasons.append("target loses RPC dependencies")
    return tuple(reasons)
