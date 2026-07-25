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

"""JSON adapters for typed Make catalog entities.

Boundary contract:
- Owns: catalog JSON normalization, deterministic bytes, and model conversion.
- Must not: compile raw specs, read files, validate business rules, or rank
modules.
- Allows: structural JSON type checks and deterministic payload fingerprints.
- Split when: adapters need IO, schema migration, or non-catalog payload
behavior.
- Merge when: another module duplicates catalog JSON conversion logic.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, cast

from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    FIELD_DIRECTIONS,
    MODULE_KINDS,
    CatalogApp,
    CatalogAppVersion,
    CatalogConstraint,
    CatalogField,
    CatalogFieldDirection,
    CatalogModule,
    CatalogModuleKind,
    CatalogRawSpecDiagnostic,
    CatalogRawSpecDiagnosticCode,
    CatalogRawSpecDiagnosticSeverity,
    CatalogSnapshot,
    JsonObject,
    JsonValue,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def canonical_catalog_bytes(payload: JsonObject) -> bytes:
    """Return deterministic JSON bytes for a catalog payload."""
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def payload_fingerprint(payload: JsonObject) -> str:
    """Return the deterministic fingerprint for one catalog payload."""
    return hashlib.sha256(canonical_catalog_bytes(payload)).hexdigest()


def catalog_snapshot_to_json(snapshot: CatalogSnapshot) -> JsonObject:
    """Return the JSON payload for one catalog snapshot."""
    payload: JsonObject = {
        "catalog_schema_version": snapshot.catalog_schema_version,
        "generated_at_utc": snapshot.generated_at_utc,
        "raw_spec_manifest_sha256": snapshot.raw_spec_manifest_sha256,
        "apps": [_app_to_json(app) for app in snapshot.apps],
        "fingerprint": snapshot.fingerprint,
    }
    if snapshot.diagnostics:
        payload["diagnostics"] = [
            _diagnostic_to_json(diagnostic)
            for diagnostic in snapshot.diagnostics
        ]
    return payload


def catalog_snapshot_from_json(payload: JsonObject) -> CatalogSnapshot:
    """Return a typed catalog snapshot from JSON.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    catalog_schema_version = _required_int(payload, "catalog_schema_version")
    if catalog_schema_version != CATALOG_SCHEMA_VERSION:
        message = (
            f"Unsupported catalog schema version: {catalog_schema_version}"
        )
        raise ValueError(message)
    return CatalogSnapshot(
        catalog_schema_version=catalog_schema_version,
        generated_at_utc=_required_text(payload, "generated_at_utc"),
        raw_spec_manifest_sha256=_required_text(
            payload, "raw_spec_manifest_sha256"
        ),
        apps=tuple(
            _app_from_json(app) for app in _object_sequence(payload, "apps")
        ),
        fingerprint=_required_text(payload, "fingerprint"),
        diagnostics=tuple(
            _diagnostic_from_json(diagnostic)
            for diagnostic in _optional_object_sequence(payload, "diagnostics")
        ),
    )


def normalize_json_object(payload: Mapping[str, object]) -> JsonObject:
    """Return a JSON object with string keys and validated JSON values."""
    return {
        str(key): normalize_json_value(value) for key, value in payload.items()
    }


def normalize_json_value(value: object) -> JsonValue:
    """Return a recursively validated JSON value.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return normalize_json_object(cast("Mapping[str, object]", value))
    if isinstance(value, tuple):
        return [
            normalize_json_value(item)
            for item in cast("tuple[object, ...]", value)
        ]
    if isinstance(value, list):
        return [
            normalize_json_value(item) for item in cast("list[object]", value)
        ]
    message = f"Unsupported JSON value type: {type(value).__name__}"
    raise TypeError(message)


def _app_to_json(app: CatalogApp) -> JsonObject:
    """Return the JSON payload for one app."""
    return {
        "app_id": app.app_id,
        "app_slug": app.app_slug,
        "label": app.label,
        "external_id": app.external_id,
        "deprecated": app.deprecated,
        "versions": [_app_version_to_json(version) for version in app.versions],
        "fingerprint": app.fingerprint,
    }


def _app_version_to_json(version: CatalogAppVersion) -> JsonObject:
    """Return the JSON payload for one app version."""
    return {
        "app_version_id": version.app_version_id,
        "app_id": version.app_id,
        "app_slug": version.app_slug,
        "version": version.version,
        "latest": version.latest,
        "manifest_version": version.manifest_version,
        "modules": [_module_to_json(module) for module in version.modules],
        "raw_spec_sha256": version.raw_spec_sha256,
        "fingerprint": version.fingerprint,
    }


def _module_to_json(module: CatalogModule) -> JsonObject:
    """Return the JSON payload for one module."""
    return {
        "module_id": module.module_id,
        "app_version_id": module.app_version_id,
        "app_slug": module.app_slug,
        "app_version": module.app_version,
        "module_kind": module.module_kind,
        "internal_name": module.internal_name,
        "display_name": module.display_name,
        "external_id": module.external_id,
        "deprecated": module.deprecated,
        "parameters": [_field_to_json(field) for field in module.parameters],
        "expect_schema": [
            _field_to_json(field) for field in module.expect_schema
        ],
        "interface_schema": [
            _field_to_json(field) for field in module.interface_schema
        ],
        "rpc_dependencies": list(module.rpc_dependencies),
        "raw_spec_sha256": module.raw_spec_sha256,
        "fingerprint": module.fingerprint,
    }


def _field_to_json(field: CatalogField) -> JsonObject:
    """Return the JSON payload for one field."""
    return {
        "field_id": field.field_id,
        "module_id": field.module_id,
        "direction": field.direction,
        "path": list(field.path),
        "label": field.label,
        "required": field.required,
        "field_type": field.field_type,
        "advanced": field.advanced,
        "external_id": field.external_id,
        "rpc_dependencies": list(field.rpc_dependencies),
        "raw_schema": field.raw_schema,
        "constraints": [
            _constraint_to_json(constraint) for constraint in field.constraints
        ],
        "fingerprint": field.fingerprint,
    }


def _constraint_to_json(constraint: CatalogConstraint) -> JsonObject:
    """Return the JSON payload for one constraint."""
    return {
        "constraint_id": constraint.constraint_id,
        "field_id": constraint.field_id,
        "key": constraint.key,
        "value": constraint.value,
        "fingerprint": constraint.fingerprint,
    }


def _diagnostic_to_json(diagnostic: CatalogRawSpecDiagnostic) -> JsonObject:
    """Return the JSON payload for one raw-spec diagnostic."""
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "module_id": diagnostic.module_id,
        "app_slug": diagnostic.app_slug,
        "app_version": diagnostic.app_version,
        "module_kind": diagnostic.module_kind,
        "internal_name": diagnostic.internal_name,
        "field_path": list(diagnostic.field_path),
        "collection_path": list(diagnostic.collection_path),
        "source_ref": diagnostic.source_ref,
        "message": diagnostic.message,
    }


def _app_from_json(payload: JsonObject) -> CatalogApp:
    """Return a typed app from JSON."""
    return CatalogApp(
        app_id=_required_text(payload, "app_id"),
        app_slug=_required_text(payload, "app_slug"),
        label=_required_text(payload, "label"),
        external_id=_required_text(payload, "external_id"),
        deprecated=_required_bool(payload, "deprecated"),
        versions=tuple(
            _app_version_from_json(version)
            for version in _object_sequence(payload, "versions")
        ),
        fingerprint=_required_text(payload, "fingerprint"),
    )


def _app_version_from_json(payload: JsonObject) -> CatalogAppVersion:
    """Return a typed app version from JSON."""
    return CatalogAppVersion(
        app_version_id=_required_text(payload, "app_version_id"),
        app_id=_required_text(payload, "app_id"),
        app_slug=_required_text(payload, "app_slug"),
        version=_required_text(payload, "version"),
        latest=_required_bool(payload, "latest"),
        manifest_version=_required_int(payload, "manifest_version"),
        modules=tuple(
            _module_from_json(module)
            for module in _object_sequence(payload, "modules")
        ),
        raw_spec_sha256=_required_text(payload, "raw_spec_sha256"),
        fingerprint=_required_text(payload, "fingerprint"),
    )


def _module_from_json(payload: JsonObject) -> CatalogModule:
    """Return a typed module from JSON."""
    module_kind = _module_kind(payload, "module_kind")
    return CatalogModule(
        module_id=_required_text(payload, "module_id"),
        app_version_id=_required_text(payload, "app_version_id"),
        app_slug=_required_text(payload, "app_slug"),
        app_version=_required_text(payload, "app_version"),
        module_kind=module_kind,
        internal_name=_required_text(payload, "internal_name"),
        display_name=_required_text(payload, "display_name"),
        external_id=_required_text(payload, "external_id"),
        deprecated=_required_bool(payload, "deprecated"),
        parameters=tuple(
            _field_from_json(field)
            for field in _object_sequence(payload, "parameters")
        ),
        expect_schema=tuple(
            _field_from_json(field)
            for field in _object_sequence(payload, "expect_schema")
        ),
        interface_schema=tuple(
            _field_from_json(field)
            for field in _object_sequence(payload, "interface_schema")
        ),
        rpc_dependencies=_text_tuple(payload, "rpc_dependencies"),
        raw_spec_sha256=_required_text(payload, "raw_spec_sha256"),
        fingerprint=_required_text(payload, "fingerprint"),
    )


def _field_from_json(payload: JsonObject) -> CatalogField:
    """Return a typed field from JSON."""
    return CatalogField(
        field_id=_required_text(payload, "field_id"),
        module_id=_required_text(payload, "module_id"),
        direction=_field_direction(payload, "direction"),
        path=_text_tuple(payload, "path"),
        label=_required_text(payload, "label"),
        required=_required_bool(payload, "required"),
        field_type=_optional_text(payload, "field_type"),
        advanced=_required_optional_bool(payload, "advanced"),
        external_id=_required_text(payload, "external_id"),
        rpc_dependencies=_text_tuple(payload, "rpc_dependencies"),
        raw_schema=_required_object(payload, "raw_schema"),
        constraints=tuple(
            _constraint_from_json(constraint)
            for constraint in _object_sequence(payload, "constraints")
        ),
        fingerprint=_required_text(payload, "fingerprint"),
    )


def _constraint_from_json(payload: JsonObject) -> CatalogConstraint:
    """Return a typed constraint from JSON."""
    return CatalogConstraint(
        constraint_id=_required_text(payload, "constraint_id"),
        field_id=_required_text(payload, "field_id"),
        key=_required_text(payload, "key"),
        value=_required_object(payload, "value"),
        fingerprint=_required_text(payload, "fingerprint"),
    )


def _diagnostic_from_json(payload: JsonObject) -> CatalogRawSpecDiagnostic:
    """Return a typed raw-spec diagnostic from JSON."""
    return CatalogRawSpecDiagnostic(
        code=cast(
            "CatalogRawSpecDiagnosticCode", _required_text(payload, "code")
        ),
        severity=cast(
            "CatalogRawSpecDiagnosticSeverity",
            _required_text(payload, "severity"),
        ),
        module_id=_required_text(payload, "module_id"),
        app_slug=_required_text(payload, "app_slug"),
        app_version=_required_text(payload, "app_version"),
        module_kind=_module_kind(payload, "module_kind"),
        internal_name=_required_text(payload, "internal_name"),
        field_path=_text_tuple(payload, "field_path"),
        collection_path=_path_tuple(payload, "collection_path"),
        source_ref=_required_text(payload, "source_ref"),
        message=_required_text(payload, "message"),
    )


def _required_text(payload: JsonObject, key: str) -> str:
    """Return one required non-empty text member.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Catalog member {key!r} must be non-empty text."
        raise ValueError(message)
    return value


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional text member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"Catalog member {key!r} must be text when present."
        raise TypeError(message)
    return value


def _required_bool(payload: JsonObject, key: str) -> bool:
    """Return one required Boolean member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, bool):
        message = f"Catalog member {key!r} must be Boolean."
        raise TypeError(message)
    return value


def _required_optional_bool(payload: JsonObject, key: str) -> bool | None:
    """Return one required member whose value is either Boolean or null.

    Raises:
        KeyError: If the member is absent.
        TypeError: If a value has an invalid type.
    """
    if key not in payload:
        message = f"Catalog member {key!r} must be present."
        raise KeyError(message)
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, bool):
        message = f"Catalog member {key!r} must be Boolean or null."
        raise TypeError(message)
    return value


def _required_int(payload: JsonObject, key: str) -> int:
    """Return one required integer member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Catalog member {key!r} must be an integer."
        raise TypeError(message)
    return value


def _required_object(payload: JsonObject, key: str) -> JsonObject:
    """Return one required object member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Catalog member {key!r} must be an object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", value))


def _object_sequence(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return one required sequence of objects.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Catalog member {key!r} must be a list."
        raise TypeError(message)
    return tuple(
        _object_item(key, item) for item in cast("Sequence[object]", value)
    )


def _optional_object_sequence(
    payload: JsonObject, key: str
) -> tuple[JsonObject, ...]:
    """Return one optional sequence of objects.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        message = f"Catalog member {key!r} must be a list when present."
        raise TypeError(message)
    return tuple(
        _object_item(key, item) for item in cast("Sequence[object]", value)
    )


def _object_item(key: str, item: object) -> JsonObject:
    """Return one JSON object item.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if not isinstance(item, dict):
        message = f"Catalog member {key!r} must contain only objects."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", item))


def _text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    """Return one required text tuple member.

    Raises:
        TypeError: If a value has an invalid type.
        ValueError: If a value violates the expected contract.
    """
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Catalog member {key!r} must be a text list."
        raise TypeError(message)
    strings: list[str] = []
    for item in cast("Sequence[object]", value):
        if not isinstance(item, str) or not item.strip():
            message = f"Catalog member {key!r} must be a non-empty text list."
            raise ValueError(message)
        strings.append(item)
    return tuple(strings)


def _path_tuple(payload: JsonObject, key: str) -> tuple[str | int, ...]:
    """Return one required diagnostic path member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Catalog member {key!r} must be a path list."
        raise TypeError(message)
    path: list[str | int] = []
    for item in cast("Sequence[object]", value):
        if isinstance(item, bool) or not isinstance(item, str | int):
            message = (
                f"Catalog member {key!r} must contain only strings andintegers."
            )
            raise TypeError(message)
        path.append(item)
    return tuple(path)


def _module_kind(payload: JsonObject, key: str) -> CatalogModuleKind:
    """Return one validated module kind.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _required_text(payload, key)
    if value not in MODULE_KINDS:
        message = f"Catalog module kind {value!r} is not supported."
        raise ValueError(message)
    return cast("CatalogModuleKind", value)


def _field_direction(payload: JsonObject, key: str) -> CatalogFieldDirection:
    """Return one validated field direction.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _required_text(payload, key)
    if value not in FIELD_DIRECTIONS:
        message = f"Catalog field direction {value!r} is not supported."
        raise ValueError(message)
    return cast("CatalogFieldDirection", value)
