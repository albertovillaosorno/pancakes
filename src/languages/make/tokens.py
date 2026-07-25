# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make.com module token helpers.

Boundary contract:
- Owns: language-level parsing and comparison keys for Make `app:module` tokens.
- Must not: import catalog, raw-spec, filesystem, or MCP modules.
- Allows: separator-insensitive keys used by higher-level catalog slices.
- Split when: token policy becomes platform-independent or stateful.
- Merge when: another Make language module owns the same token semantics.
"""

from __future__ import annotations


def module_token_parts(module_token: str) -> tuple[str, str]:
    """Return the app slug and internal module token parts.

    Raises:
        ValueError: If the token is not the Make `app:module` shape.
    """
    normalized = module_token.strip()
    if ":" not in normalized:
        message = (
            f"Make module token must use app:module shape: {module_token!r}"
        )
        raise ValueError(message)
    app_slug, internal_name = normalized.split(":", maxsplit=1)
    if not app_slug.strip() or not internal_name.strip():
        message = f"Make token must include app and module: {module_token!r}"
        raise ValueError(message)
    return app_slug.strip(), internal_name.strip()


def module_token_resolution_key(value: str) -> str:
    """Return a separator-insensitive key for matching Make module tokens."""
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )
