# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Parse Make IMT raw specs into deterministic summaries.

Boundary contract:
- Owns: structural parsing of raw IMT app payloads into summaries.
- Must not: fetch payloads, write manifests, build catalog entities, or
  perform IO.
- Allows: fail-closed normalization of app metadata and module counts.
- Split when: parsing needs catalog compilation or endpoint-specific adapters.
- Merge when: another parser emits the same raw-spec summary model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.models import JsonObject, MakeModuleSummary

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_COLLECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("actions", "action"),
    ("searches", "search"),
    ("triggers", "trigger"),
    ("routers", "router"),
    ("convergers", "router"),
    ("transformers", "transformer"),
    ("feeders", "transformer"),
    ("aggregators", "aggregator"),
    ("directives", "action"),
    ("starters", "trigger"),
    ("returners", "action"),
    ("agents", "agent"),
    ("customModules", "custom"),
    ("modules", "unknown"),
)


class ParsedMakeRawSpec(NamedTuple):
    """Normalized summary for one Make IMT app payload."""

    app_slug: str
    app_version: str
    app_label: str
    latest: bool
    manifest_version: int
    modules: tuple[MakeModuleSummary, ...]


def parse_make_raw_spec(payload: JsonObject) -> ParsedMakeRawSpec:
    """Parse one raw Make IMT app payload.

    Returns:
        The parsed value.
    """
    app = _object_member(payload, "app")
    app_slug = _required_text(app, "name")
    app_version = _required_text(app, "version")
    app_label = _optional_text(app, "label") or app_slug
    manifest = _optional_object_member(app, "manifest")
    manifest_version = _positive_int(
        manifest.get("version") if manifest is not None else None
    )
    modules = tuple(sorted(_iter_module_summaries(app), key=_module_sort_key))
    return ParsedMakeRawSpec(
        app_slug=app_slug,
        app_version=app_version,
        app_label=app_label,
        latest=_optional_bool(app, "latest", default=False),
        manifest_version=manifest_version,
        modules=modules,
    )


def _iter_module_summaries(app: JsonObject) -> tuple[MakeModuleSummary, ...]:
    """Return module summaries from all known Make IMT module collections.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    summaries: list[MakeModuleSummary] = []
    for collection_key, module_kind in MODULE_COLLECTIONS:
        collection = app.get(collection_key)
        if collection is None:
            continue
        if not isinstance(collection, list):
            message = (
                "Make raw spec module collection "
                f"{collection_key!r} must be a list."
            )
            raise TypeError(message)
        for index, item in enumerate(cast("list[object]", collection)):
            if not isinstance(item, dict):
                message = (
                    "Make raw spec module collection "
                    f"{collection_key}[{index}] "
                    "must contain an object."
                )
                raise TypeError(message)
            module = _json_object_from_mapping(
                cast("Mapping[object, object]", item)
            )
            internal_name = _optional_text(module, "name")
            if internal_name is None:
                continue
            display_name = _optional_text(module, "label") or internal_name
            summaries.append(
                MakeModuleSummary(
                    module_kind=module_kind,
                    internal_name=internal_name,
                    display_name=display_name,
                    parameter_count=_field_count(module.get("parameters"))
                    + _field_count(module.get("expect")),
                    output_count=_field_count(module.get("interface")),
                )
            )
    return tuple(summaries)


def _object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one required object member.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Make raw spec must contain an object member named {key!r}."
        raise TypeError(message)
    return _json_object_from_mapping(cast("Mapping[object, object]", value))


def _optional_object_member(payload: JsonObject, key: str) -> JsonObject | None:
    """Return one optional object member.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        message = (
            f"Make raw spec member {key!r} must be an object when present."
        )
        raise TypeError(message)
    return _json_object_from_mapping(cast("Mapping[object, object]", value))


def _required_text(payload: JsonObject, key: str) -> str:
    """Return one required non-empty text member.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    value = _optional_text(payload, key)
    if value is None:
        message = f"Make raw spec must contain text member {key!r}."
        raise ValueError(message)
    return value


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional non-empty text member."""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _positive_int(value: object) -> int:
    """Return a positive integer, defaulting absent manifest versions to one.

    Raises:
        TypeError: If an input value has an unsupported type.
        ValueError: If an input value violates the documented contract.
    """
    if value is None:
        return 1
    if isinstance(value, bool):
        message = "Manifest version must be a positive integer."
        raise TypeError(message)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value)
    else:
        message = "Manifest version must be a positive integer."
        raise TypeError(message)
    if parsed <= 0:
        message = "Manifest version must be a positive integer."
        raise ValueError(message)
    return parsed


def _optional_bool(payload: JsonObject, key: str, *, default: bool) -> bool:
    """Return one optional boolean member.

    Raises:
        TypeError: If a present value is not boolean.
    """
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        message = (
            f"Make raw spec member {key!r} must be a boolean when present."
        )
        raise TypeError(message)
    return value


def _field_count(value: object) -> int:
    """Return the number of object fields in a heterogeneous field list."""
    if not isinstance(value, list):
        return 0
    return sum(
        1 for item in cast("list[object]", value) if isinstance(item, dict)
    )


def _module_sort_key(module: MakeModuleSummary) -> tuple[str, str]:
    """Return the stable sort key for module summaries."""
    return module.module_kind, module.internal_name


def _json_object_from_mapping(mapping: Mapping[object, object]) -> JsonObject:
    """Return a JSON object with string keys from a validated mapping."""
    return {str(key): value for key, value in mapping.items()}
