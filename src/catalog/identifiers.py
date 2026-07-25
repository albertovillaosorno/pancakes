# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.schema-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Stable Make catalog identifier helpers.

Boundary contract:
- Owns: deterministic string identifiers for catalog apps, modules, and fields.
- Must not: inspect raw specs, catalog snapshots, JSON payloads, or filesystem
state.
- Allows: percent-encoding and validation of one identifier component.
- Split when: identifier policy needs persisted state or schema-aware lookup.
- Merge when: another module builds the same catalog identifier formats.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import quote

ID_SAFE_CHARACTERS: Final = "-._~"
CURRENT_VERSION_LABEL: Final = "current"
LEGACY_MODULE_INTERNAL_NAME_PREFIXES: Final[tuple[str, ...]] = (
    "action ",
    "search ",
    "trigger",
)


def stable_id_part(value: str) -> str:
    """Return one stable identifier component.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    normalized = value.strip()
    if not normalized:
        message = "Catalog identifier parts must be non-empty."
        raise ValueError(message)
    return quote(normalized, safe=ID_SAFE_CHARACTERS)


def app_id(app_slug: str) -> str:
    """Return the stable ID for one Make app."""
    return f"app:{stable_id_part(app_slug)}"


def app_version_id(app_slug: str, app_version: str) -> str:
    """Return the stable ID for one Make app version."""
    return (
        f"app-version:{stable_id_part(app_slug)}:{stable_id_part(app_version)}"
    )


def module_id(
    *,
    app_slug: str,
    app_version: str,
    module_kind: str,
    internal_name: str,
) -> str:
    """Return the stable ID for one Make module."""
    return (
        f"module:{stable_id_part(app_slug)}:{stable_id_part(app_version)}:"
        f"{stable_id_part(module_kind)}:{stable_id_part(internal_name)}"
    )


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
        message = (
            f"Make module token must include app and module names:"
            f"{module_token!r}"
        )
        raise ValueError(message)
    return app_slug.strip(), internal_name.strip()


def module_token_resolution_key(value: str) -> str:
    """Return a separator-insensitive key for matching catalog module tokens."""
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )


def module_token_logical_key(value: str) -> str:
    """Return a stable logical key after legacy Make internal-name prefixes.

    Returns:
        The separator-insensitive logical token key.
    """
    normalized = module_token_resolution_key(value)
    for prefix in LEGACY_MODULE_INTERNAL_NAME_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            return normalized[len(prefix) :]
    return normalized


def module_token_match_keys(value: str) -> frozenset[str]:
    """Return normalized module identity keys for version-stable matching.

    Returns:
        A set containing the raw normalized key and legacy-prefix-stripped
        logical key.
    """
    normalized = module_token_resolution_key(value)
    if not normalized:
        return frozenset()
    logical_key = module_token_logical_key(value)
    return frozenset((normalized, logical_key))


def module_version_sort_key(version_text: str) -> tuple[int, ...]:
    """Return a descending-friendly semantic version key."""
    if version_text.strip().casefold() == CURRENT_VERSION_LABEL:
        return (-1,)
    matches: list[str] = re.findall(r"[0-9]+", version_text)
    segments = [int(segment) for segment in matches]
    if not segments:
        return (1,)
    return (0, *(-segment for segment in segments))


def field_id(
    *,
    parent_module_id: str,
    direction: str,
    path: tuple[str, ...],
) -> str:
    """Return the stable ID for one Make module field."""
    path_key = ".".join(stable_id_part(part) for part in path)
    return f"field:{parent_module_id}:{stable_id_part(direction)}:{path_key}"


def constraint_id(
    *,
    parent_field_id: str,
    key: str,
) -> str:
    """Return the stable ID for one field constraint."""
    return f"constraint:{parent_field_id}:{stable_id_part(key)}"
