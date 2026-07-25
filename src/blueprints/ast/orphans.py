# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.unknown-fields-preserved
# - 001061#repo.delivery.live-verification-explicit-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Read Make designer orphan fragments without live verification.

Boundary contract:
- Owns: extraction of designer orphan groups preserved in blueprint metadata.
- Must not: verify live designer state, repair orphans, or mutate payloads.
- Allows: typed orphan records from already-parsed AST metadata.
- Split when: orphan normalization or repair planning needs ownership.
- Merge when: another orphan extractor returns the same groups identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstRoot


class DesignerOrphanNode(NamedTuple):
    """One node preserved in a Make designer orphan group."""

    node_id: str
    module_token: str
    raw_payload: JsonObject


class DesignerOrphanGroup(NamedTuple):
    """One Make designer orphan group."""

    group_index: int
    nodes: tuple[DesignerOrphanNode, ...]


def extract_designer_orphan_groups(
    root: MakeAstRoot,
) -> tuple[DesignerOrphanGroup, ...]:
    """Return orphan groups preserved in root designer metadata."""
    designer = _designer_metadata(root)
    if designer is None:
        return ()
    raw_orphans = designer.get("orphans")
    if not isinstance(raw_orphans, list):
        return ()
    groups: list[DesignerOrphanGroup] = []
    for index, raw_group in enumerate(cast("list[object]", raw_orphans)):
        nodes = _orphan_nodes(raw_group)
        if nodes:
            groups.append(DesignerOrphanGroup(group_index=index, nodes=nodes))
    return tuple(groups)


def _orphan_nodes(raw_group: object) -> tuple[DesignerOrphanNode, ...]:
    """Return nodes from one raw orphan group."""
    if not isinstance(raw_group, list):
        return ()
    nodes: list[DesignerOrphanNode] = []
    for raw_node in cast("list[object]", raw_group):
        if not _is_json_object(raw_node):
            continue
        node_id = _node_id_text(raw_node.get("id"))
        module_token = _module_token_text(raw_node.get("module"))
        if node_id is None or module_token is None:
            continue
        nodes.append(
            DesignerOrphanNode(
                node_id=node_id,
                module_token=module_token,
                raw_payload=raw_node,
            )
        )
    return tuple(nodes)


def _designer_metadata(root: MakeAstRoot) -> JsonObject | None:
    """Return root designer metadata when it is object-shaped."""
    designer = root.scenario.metadata.get("designer")
    return designer if _is_json_object(designer) else None


def _node_id_text(value: object) -> str | None:
    """Return a safe designer node id string."""
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    return None


def _module_token_text(value: object) -> str | None:
    """Return a safe designer module token."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
