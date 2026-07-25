# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001044#repo.make-ast.traversal-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Execution-path expansion for parsed Make AST flows.

Boundary contract:
- Owns: deterministic route-like execution path expansion for parsed AST roots.
- Must not: validate semantics, score paths, parse payloads, or mutate
blueprints.
- Allows: route, branch, and tool child-flow expansion over typed AST nodes.
- Split when: Make-specific runtime scheduling or error-route paths need
modeling.
- Merge when: traversal.py absorbs execution-path expansion as the same
contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstNode, MakeAstRoot


def iter_ast_execution_paths(
    root: MakeAstRoot,
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return route-like execution paths through a parsed AST root."""
    return _flow_paths(root.flow)


def available_node_ids_before(
    root: MakeAstRoot, node_id: str
) -> frozenset[str]:
    """Return prior node IDs on every path containing one node."""
    candidate_sets: list[frozenset[str]] = []
    for path in iter_ast_execution_paths(root):
        available: list[str] = []
        for node in path:
            if node.node_id == node_id:
                candidate_sets.append(frozenset(available))
                break
            if node.node_id:
                available.append(node.node_id)
    if not candidate_sets:
        return frozenset()
    available_ids = set(candidate_sets[0])
    for candidate in candidate_sets[1:]:
        available_ids.intersection_update(candidate)
    return frozenset(available_ids)


def _flow_paths(
    flow: tuple[MakeAstNode, ...],
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return route-like execution paths through one flow."""
    paths: tuple[tuple[MakeAstNode, ...], ...] = ((),)
    for node in flow:
        paths = tuple(
            expanded_path
            for prefix in paths
            for expanded_path in _node_paths(prefix=prefix, node=node)
        )
    return paths


def _node_paths(
    *,
    prefix: tuple[MakeAstNode, ...],
    node: MakeAstNode,
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return route-like execution paths after one node."""
    child_paths = _route_like_child_paths(node)
    if not child_paths:
        return ((*prefix, node),)
    return tuple((*prefix, node, *child_path) for child_path in child_paths)


def _route_like_child_paths(
    node: MakeAstNode,
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return execution paths through route-like child flows."""
    child_paths: list[tuple[MakeAstNode, ...]] = []
    for route in (*node.routes, *node.branches, *node.tools):
        child_paths.extend(_flow_paths(route.flow))
    return tuple(child_paths)
