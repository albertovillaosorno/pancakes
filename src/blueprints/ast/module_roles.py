# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.reference-rewrite-and-role-classification
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Coarse Make module role classification helpers.

Boundary contract:
- Owns: separator-insensitive module role and trigger/response classification.
- Must not: parse blueprint JSON, resolve catalog rows, or validate scenarios.
- Allows: deterministic token heuristics backed by AST contract tests.
- Split when: role inference needs catalog evidence or live Make metadata.
- Merge when: another AST module owns the same module-role predicates.
"""

from __future__ import annotations

from typing import Final

TRIGGER_KEYWORDS: Final[tuple[str, ...]] = ("watch", "webhook", "trigger")
WRITE_KEYWORDS: Final[tuple[str, ...]] = (
    "create",
    "update",
    "append",
    "upsert",
    "add",
    "send",
    "respond",
)
READ_KEYWORDS: Final[tuple[str, ...]] = ("search", "list", "get", "watch")


def infer_module_role(module_token: str) -> str:
    """Return a coarse semantic role for one module token."""
    lowered = module_token.casefold()
    if _module_token_is_webhook_response(lowered):
        return "write"
    if any(keyword in lowered for keyword in TRIGGER_KEYWORDS):
        return "trigger"
    if any(keyword in lowered for keyword in WRITE_KEYWORDS):
        return "write"
    if any(keyword in lowered for keyword in READ_KEYWORDS):
        return "read"
    return "action"


def module_looks_like_trigger(
    module_token: str, *, module_kind: str | None = None
) -> bool:
    """Return whether one module should be treated as a trigger."""
    normalized_kind = module_token_semantic_key(str(module_kind or ""))
    if normalized_kind in {
        "trigger",
        "instanttrigger",
        "pollingtrigger",
        "scheduledtrigger",
        "webhooktrigger",
    }:
        return True
    if normalized_kind in {"action", "search", "router", "agent"}:
        return False
    lowered = module_token.casefold()
    if _module_token_is_webhook_response(lowered):
        return False
    return any(keyword in lowered for keyword in TRIGGER_KEYWORDS)


def module_looks_like_webhook_response(module_token: str) -> bool:
    """Return whether one module token is a webhook response action."""
    return _module_token_is_webhook_response(module_token.casefold())


def module_token_semantic_key(value: str) -> str:
    """Return a separator-insensitive module token key."""
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )


def _module_token_is_webhook_response(lowered_module_token: str) -> bool:
    """Return whether one lowered token is a known webhook response action."""
    semantic_key = module_token_semantic_key(lowered_module_token)
    return semantic_key.endswith(
        (
            "webhook" + "respond",
            "webhook" + "response",
            "webhooks" + "respond",
            "webhooks" + "response",
        )
    )
