# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001061#repo.delivery.client-ready-handoff-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Client handoff policy helpers for catalog-backed blueprint fields.

Boundary contract:
- Owns: catalog-field handoff policy decisions and seed-value selection.
- Must not: scan AST nodes, build manifests, or validate full blueprints.
- Allows: quality profile normalization and deterministic field classification.
- Split when: policy families need independent configuration or ownership.
- Merge when: another policy file makes the same field decisions identically.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from catalog.models import CatalogField, JsonObject

type HandoffQualityProfile = str
type LegacyModulePolicy = str
type FieldBindingKind = str

DEFAULT_QUALITY_PROFILE: Final = "client_ready"
DEFAULT_GENERATION_LEGACY_POLICY: Final = "forbid_on_new"
DEFAULT_EXISTING_AST_LEGACY_POLICY: Final = "preserve_existing"
ALLOWED_QUALITY_PROFILES: Final = frozenset(("baseline", "client_ready"))
ALLOWED_LEGACY_POLICIES: Final = frozenset(
    ("forbid_on_new", "preserve_existing", "allow")
)
PLACEHOLDER_PREFIX: Final = "{{PLACEHOLDER_"


def normalize_quality_profile(value: str | None) -> HandoffQualityProfile:
    """Return a supported handoff quality profile."""
    normalized = str(value or DEFAULT_QUALITY_PROFILE).strip().casefold()
    if normalized in ALLOWED_QUALITY_PROFILES:
        return normalized
    return DEFAULT_QUALITY_PROFILE


def normalize_legacy_policy(
    value: str | None,
    *,
    existing_ast: bool = False,
) -> LegacyModulePolicy:
    """Return a supported legacy module policy."""
    default = (
        DEFAULT_EXISTING_AST_LEGACY_POLICY
        if existing_ast
        else DEFAULT_GENERATION_LEGACY_POLICY
    )
    normalized = str(value or default).strip().casefold()
    if normalized in ALLOWED_LEGACY_POLICIES:
        return normalized
    return default


def classify_catalog_field_binding(field: CatalogField) -> FieldBindingKind:
    """Classify one catalog field for client handoff.

    Returns:
        The result produced by classify one catalog field for client handoff.
    """
    field_type = str(
        field.field_type or field.raw_schema.get("type") or ""
    ).casefold()
    if field_type.startswith("account:") and len(field.path) == 1:
        return "connection"
    if field_type.startswith("hook:") or field_type == "webhook":
        return "hook"
    if field.rpc_dependencies or _schema_has_rpc(field.raw_schema):
        return "dynamic_selector"
    if field.required:
        return "inline_required"
    return "optional_inline"


def choose_catalog_field_seed_value(
    field: CatalogField, export_value: object = None
) -> object:
    """Choose a conservative inline seed value for a catalog field.

    Returns:
        The result produced by choosing a conservative inline seed value
        for a catalog field.
    """
    default = field.raw_schema.get("default")
    if default is not None:
        return default
    option_values = _schema_option_values(field.raw_schema)
    if option_values:
        return option_values[0]
    if _is_scalar_export_value(export_value):
        return export_value
    return _generic_seed_value(field)


def is_unresolved_handoff_value(value: object) -> bool:
    """Return whether a value remains unresolved for client handoff."""
    if value is None:
        return True
    if not isinstance(value, str):
        if isinstance(value, dict):
            return not value
        if isinstance(value, list):
            return not value
        return False
    stripped = value.strip()
    return not stripped or stripped.startswith(PLACEHOLDER_PREFIX)


def _schema_has_rpc(schema: JsonObject) -> bool:
    """Return whether one schema contains RPC-backed selector metadata."""
    return _visit_rpc_values(schema.get("options")) or _visit_rpc_values(
        schema.get("rpc")
    )


def _visit_rpc_values(value: object) -> bool:
    """Return whether an arbitrary schema value contains an RPC selector."""
    if isinstance(value, str):
        return value.startswith("rpc://")
    if isinstance(value, list):
        return any(
            _visit_rpc_values(item) for item in cast("list[object]", value)
        )
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return any(_visit_rpc_values(item) for item in mapping.values())
    return False


def _schema_option_values(schema: JsonObject) -> tuple[object, ...]:
    """Return option values with explicit defaults first."""
    options = schema.get("options")
    if not isinstance(options, list):
        return ()
    values: list[object] = []
    defaults: list[object] = []
    for option in cast("list[object]", options):
        value = _option_value(option)
        if not _is_valid_option_seed_value(value):
            continue
        if (
            isinstance(option, dict)
            and cast("dict[object, object]", option).get("default") is True
        ):
            defaults.append(value)
        values.append(value)
    return _deduplicate((*defaults, *values))


def _option_value(option: object) -> object:
    """Return one option value."""
    if isinstance(option, dict):
        return cast("dict[object, object]", option).get("value")
    return option


def _is_valid_option_seed_value(value: object) -> bool:
    """Return whether a schema option can seed a concrete handoff value."""
    if value is None or isinstance(value, dict | list):
        return False
    if isinstance(value, str):
        return not is_unresolved_handoff_value(value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _deduplicate(values: tuple[object, ...]) -> tuple[object, ...]:
    """Deduplicate values by representation while preserving order.

    Returns:
        The result produced by deduplicating values by representation
        while preserving order.
    """
    deduplicated: list[object] = []
    seen: set[str] = set()
    for value in values:
        key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(value)
    return tuple(deduplicated)


def _is_scalar_export_value(value: object) -> bool:
    """Return whether an export value can safely seed a simple field."""
    if isinstance(value, bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and not is_unresolved_handoff_value(value)


def _generic_seed_value(field: CatalogField) -> object:
    """Return a conservative generic seed for simple scalar fields."""
    field_type = str(
        field.field_type or field.raw_schema.get("type") or ""
    ).casefold()
    leaf = field.path[-1].casefold()
    seed: object = None
    if field_type == "boolean":
        seed = False
    elif field_type in {"number", "integer"}:
        seed = 1
    elif field_type == "url" or leaf.endswith("url"):
        seed = "https://example.invalid/resource"
    elif field_type == "email" or "email" in leaf:
        seed = "client@example.com"
    elif "prompt" in leaf or "message" in leaf:
        seed = "Replace this value with the client-specific instruction."
    elif field_type in {"text", "textarea"}:
        seed = "Replace this value with the client-specific input."
    return seed
