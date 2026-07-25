# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001044#repo.make-ast.traversal-contract
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Webhook response execution-path coverage for validation.

Boundary contract:
- Owns: deterministic webhook response coverage over parsed AST execution paths.
- Must not: build validation findings, resolve catalog modules, or mutate ASTs.
- Allows: route, branch, and tool flow expansion for local response checks.
- Split when: Make exposes distinct response semantics per trigger or route.
- Merge when: AST traversal owns this exact execution-path coverage contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from blueprints.ast.execution_paths import iter_ast_execution_paths
from blueprints.ast.module_roles import module_looks_like_webhook_response

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstNode, MakeAstRoot


def webhook_has_response_on_all_paths(
    *,
    root: MakeAstRoot,
    webhook_node: MakeAstNode,
) -> bool:
    """Return whether every path through a webhook has response behavior."""
    if _webhook_declares_response(webhook_node):
        return True
    paths = _paths_containing_webhook(root=root, webhook_node=webhook_node)
    return bool(paths) and all(
        _path_has_response_after_webhook(path=path, webhook_node=webhook_node)
        for path in paths
    )


def webhook_has_response_on_any_path(
    *,
    root: MakeAstRoot,
    webhook_node: MakeAstNode,
) -> bool:
    """Return whether any path through a webhook has response behavior."""
    if _webhook_declares_response(webhook_node):
        return True
    return any(
        _path_has_response_after_webhook(path=path, webhook_node=webhook_node)
        for path in _paths_containing_webhook(
            root=root, webhook_node=webhook_node
        )
    )


def _paths_containing_webhook(
    *,
    root: MakeAstRoot,
    webhook_node: MakeAstNode,
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return execution paths that contain a specific webhook node."""
    return tuple(
        path
        for path in iter_ast_execution_paths(root)
        if any(node is webhook_node for node in path)
    )


def _path_has_response_after_webhook(
    *,
    path: tuple[MakeAstNode, ...],
    webhook_node: MakeAstNode,
) -> bool:
    """Return whether one path responds after a webhook node."""
    webhook_seen = False
    for node in path:
        if node is webhook_node:
            webhook_seen = True
            continue
        if webhook_seen and module_looks_like_webhook_response(
            node.module_token
        ):
            return True
    return False


def _webhook_declares_response(node: MakeAstNode) -> bool:
    """Return whether one webhook node declares response behavior itself."""
    return (
        module_looks_like_webhook_response(node.module_token)
        or _contains_any_key(node.raw_payload, ("response", "respond"))
        or _metadata_declares_response_behavior(node.raw_payload)
    )


def _metadata_declares_response_behavior(value: object) -> bool:
    """Return whether node-local metadata declares webhook response behavior."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    metadata = raw_mapping.get("metadata")
    if not isinstance(metadata, dict):
        return False
    metadata_mapping = cast("dict[object, object]", metadata)
    return _contains_any_key_deep(
        metadata_mapping,
        (
            "response_behavior",
            "responsebehavior",
            "response_contract",
            "responsecontract",
            "webhook_response",
            "webhookresponse",
            "webhook_response_behavior",
            "webhookresponsebehavior",
        ),
    )


def _contains_any_key_deep(value: object, keys: tuple[str, ...]) -> bool:
    """Return whether a metadata object contains a matching field name."""
    if not isinstance(value, dict):
        return False
    lowered = {key.casefold() for key in keys}
    raw_mapping = cast("dict[object, object]", value)
    for key, item in raw_mapping.items():
        if isinstance(key, str) and key.casefold() in lowered:
            return True
        if _contains_any_key_deep(item, keys):
            return True
    return False


def _contains_any_key(value: object, keys: tuple[str, ...]) -> bool:
    """Return whether a JSON object contains any matching field name."""
    if not isinstance(value, dict):
        return False
    lowered = {key.casefold() for key in keys}
    raw_mapping = cast("dict[object, object]", value)
    return any(
        isinstance(key, str) and key.casefold() in lowered
        for key in raw_mapping
    )
