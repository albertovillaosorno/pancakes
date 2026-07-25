# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Traversal helpers for the typed Make AST contract.

Boundary contract:
- Owns: deterministic traversal and lookup over typed blueprint AST nodes.
- Must not: parse payloads, validate references, or mutate node structures.
- Allows: preorder node iteration, ID collection, and fail-fast lookup.
- Split when: traversal variants need independent ordering or filtering policy.
- Merge when: another traversal file returns the same node sequences.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstNode, MakeAstRoot


def iter_ast_nodes(root: MakeAstRoot) -> tuple[MakeAstNode, ...]:
    """Return nodes in deterministic preorder traversal."""
    nodes: list[MakeAstNode] = []
    for node in root.flow:
        nodes.extend(_iter_node(node))
    return tuple(nodes)


def collect_ast_node_ids(root: MakeAstRoot) -> tuple[str, ...]:
    """Return all non-empty AST node IDs in traversal order."""
    return tuple(node.node_id for node in iter_ast_nodes(root) if node.node_id)


def require_ast_node(root: MakeAstRoot, node_id: str) -> MakeAstNode:
    """Return one AST node by ID or fail loudly.

    Raises:
        LookupError: If a required lookup cannot be resolved.
    """
    for node in iter_ast_nodes(root):
        if node.node_id == node_id:
            return node
    message = f"Make AST node does not exist: {node_id}"
    raise LookupError(message)


def _iter_node(node: MakeAstNode) -> tuple[MakeAstNode, ...]:
    """Return a node and all child nodes in preorder."""
    nodes = [node]
    for route in (*node.routes, *node.branches, *node.tools):
        for child in route.flow:
            nodes.extend(_iter_node(child))
    for handler in node.error_handlers:
        nodes.extend(_iter_node(handler))
    return tuple(nodes)
