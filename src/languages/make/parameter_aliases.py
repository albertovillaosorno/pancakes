# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make-native parameter alias helpers.

Boundary contract:
- Owns: Make-specific compatibility aliases for native module parameter names.
- Must not: validate full blueprints, render payloads, call providers, or mutate
catalog data.
- Allows: pure field classification used by Make adapters and Make AST
validation.
- Split when: non-connection parameter aliases need independent migration
ownership.
- Merge when: another Make adapter module owns the same field-alias semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from catalog.models import CatalogField

MAKE_CONNECTION_PARAMETER_ALIASES: Final[tuple[str, ...]] = (
    "__IMTCONN__",
    "account ",
    "connection",
)


def make_connection_parameter_aliases_for_field(
    field: CatalogField,
) -> tuple[str, ...]:
    """Return accepted Make connection aliases for one catalog field.

    Returns:
        The compatible parameter aliases, or an empty tuple for non-connection
        fields.
    """
    if not _is_make_connection_parameter(field):
        return ()
    return MAKE_CONNECTION_PARAMETER_ALIASES


def make_connection_parameter_target_for_field(
    field: CatalogField,
) -> str | None:
    """Return the native Make connection parameter target for one field.

    Returns:
        The native single-segment parameter key, or None for non-connection
        fields.
    """
    if not _is_make_connection_parameter(field):
        return None
    return field.path[0]


def _is_make_connection_parameter(field: CatalogField) -> bool:
    """Return whether one field is a Make-native connection parameter."""
    return (
        len(field.path) == 1
        and field.path[0] in MAKE_CONNECTION_PARAMETER_ALIASES
        and (
            (field.field_type or "").startswith("account:")
            or str(field.raw_schema.get("type", "")).startswith("account:")
            or field.label.casefold() == "connection"
        )
    )
