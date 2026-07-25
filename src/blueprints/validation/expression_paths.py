# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Classify AST JSON paths that can contain executable Make expressions.

Boundary contract:
- Owns: path-level selection for executable Make mapping expression strings.
- Must not: parse expression bodies, validate output contracts,
  or inspect catalogs.
- Allows: filtering mapping-risk expression scans to executable payload paths.
- Split when: route filters or node-local mappings need separate path policies.
- Merge when: another validation module owns the exact same path predicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart

EXPRESSION_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    (
        "mapper",
        "parameters",
        "filter",
        "conditions",
        "condition",
        "rules",
        "expression",
        "formula",
    )
)
CHILD_FLOW_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools")
)
DIRECT_ERROR_CHILD_KEYS: Final[frozenset[str]] = frozenset(
    ("onerror", "on_error")
)


def path_allows_mapping_expression(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether a raw-payload path belongs to executable mapping data."""
    string_parts = tuple(part for part in path if isinstance(part, str))
    if "metadata" in string_parts or not _contains_expression_container(
        string_parts
    ):
        return False
    return not _descends_into_child_node(string_parts)


def _contains_expression_container(path: tuple[str, ...]) -> bool:
    """Return whether the path passes through a mapping-capable container."""
    return any(part in EXPRESSION_CONTAINER_KEYS for part in path)


def _descends_into_child_node(path: tuple[str, ...]) -> bool:
    """Return whether the path belongs to a nested child node payload."""
    if any(part in DIRECT_ERROR_CHILD_KEYS for part in path):
        return True
    return any(
        _has_flow_after_child_container(path, child_key)
        for child_key in CHILD_FLOW_CONTAINER_KEYS
    )


def _has_flow_after_child_container(
    path: tuple[str, ...], child_key: str
) -> bool:
    """Return whether a route-like container path enters a child flow node."""
    if child_key not in path:
        return False
    child_index = path.index(child_key)
    return "flow" in path[child_index + 1 :]
