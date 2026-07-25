# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001033#repo.paths.no-output-outside-repository
# - 001034#repo.paths.no-hardcoded-repository-paths
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.schema-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compile Make raw specs into the canonical catalog schema.

Boundary contract:
- Owns: deterministic raw-spec to catalog snapshot compilation.
- Must not: scrape remote specs, render blueprints, or own catalog query policy.
- Allows: repository-relative raw-spec reads and fingerprint construction.
- Split when: compilation gains network, repair, rendering, or query behavior.
- Merge when: another compiler module emits the same catalog entities.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_SQLITE_DATABASE,
    resolve_repo_relative_path,
)
from languages.make.raw_specs.sqlite_store import (
    is_sqlite_raw_spec_ref,
    load_sqlite_raw_spec_bundle,
)

from catalog.field_collections import FIELD_COLLECTIONS
from catalog.identifiers import (
    app_id,
    app_version_id,
    constraint_id,
    field_id,
    module_id,
    module_version_sort_key,
)
from catalog.json_payloads import (
    catalog_snapshot_to_json,
    normalize_json_object,
    payload_fingerprint,
)
from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    CatalogApp,
    CatalogAppVersion,
    CatalogConstraint,
    CatalogField,
    CatalogFieldDirection,
    CatalogModule,
    CatalogModuleKind,
    CatalogRawSpecDiagnostic,
    CatalogRawSpecDiagnosticCode,
    CatalogSnapshot,
    JsonObject,
)
from catalog.validation import validate_catalog_snapshot
from catalog.value_index import canonicalize_catalog_field_type

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from languages.make.raw_specs.models import RawSpecManifest, RawSpecRecord

MODULE_COLLECTIONS: Final[tuple[tuple[str, CatalogModuleKind], ...]] = (
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
FIELD_CONSTRAINT_KEYS: Final[frozenset[str]] = frozenset(
    (
        "advanced ",
        "default ",
        "editable ",
        "forceReload ",
        "grouped ",
        "help ",
        "labels ",
        "mappable ",
        "max ",
        "maxItems ",
        "maxLength ",
        "min ",
        "minItems ",
        "minLength ",
        "multiple ",
        "options ",
        "placeholder ",
        "scope ",
        "semantic",
    )
)
VALIDATE_CONSTRAINT_KEYS: Final[frozenset[str]] = frozenset(
    ("max", "min", "pattern")
)
RPC_PREFIX: Final = "rpc://"
NESTED_FIELD_KEYS: Final[frozenset[str]] = frozenset(
    ("fields", "schema", "spec")
)


class RawFieldDiagnosticContext(NamedTuple):
    """Shared context for quarantined raw field metadata diagnostics."""

    diagnostics: list[CatalogRawSpecDiagnostic]
    compiled_module_id: str
    record: RawSpecRecord
    module_kind: CatalogModuleKind
    internal_name: str


class RawFieldIssue(NamedTuple):
    """One pending malformed raw field metadata issue."""

    code: CatalogRawSpecDiagnosticCode
    field_path: tuple[str, ...]
    collection_path: tuple[str | int, ...]
    message: str


def compile_catalog_from_manifest(
    *,
    repo_root: Path,
    manifest: RawSpecManifest,
    allow_empty_app_versions: bool = False,
) -> CatalogSnapshot:
    """Compile a raw-spec manifest into a deterministic catalog snapshot.

    Returns:
        The deterministic catalog snapshot.
    """
    diagnostics: list[CatalogRawSpecDiagnostic] = []
    app_versions: list[CatalogAppVersion] = []
    for record in manifest.records:
        app_version = _compile_app_version(
            repo_root=repo_root,
            record=record,
            diagnostics=diagnostics,
            allow_empty_app_versions=allow_empty_app_versions,
        )
        if app_version is not None:
            app_versions.append(app_version)
    apps = _group_app_versions(tuple(app_versions))
    snapshot = CatalogSnapshot(
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        generated_at_utc=manifest.generated_at_utc,
        raw_spec_manifest_sha256=manifest.manifest_sha256,
        apps=apps,
        fingerprint="",
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_sort_key)),
    )
    snapshot = CatalogSnapshot(
        catalog_schema_version=snapshot.catalog_schema_version,
        generated_at_utc=snapshot.generated_at_utc,
        raw_spec_manifest_sha256=snapshot.raw_spec_manifest_sha256,
        apps=snapshot.apps,
        fingerprint=payload_fingerprint(
            _snapshot_fingerprint_payload(snapshot)
        ),
        diagnostics=snapshot.diagnostics,
    )
    validate_catalog_snapshot(snapshot)
    return snapshot


def _compile_app_version(
    *,
    repo_root: Path,
    record: RawSpecRecord,
    diagnostics: list[CatalogRawSpecDiagnostic],
    allow_empty_app_versions: bool,
) -> CatalogAppVersion | None:
    """Compile one raw-spec manifest record into an app version.

    Returns:
        The compiled app version.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    payload = _load_raw_spec_payload(repo_root=repo_root, record=record)
    app_payload = _required_object(payload, "app")
    compiled_app_id = app_id(record.app_slug)
    compiled_app_version_id = app_version_id(
        record.app_slug, record.app_version
    )
    modules = _deduplicate_modules(
        modules=tuple(
            sorted(
                _compile_modules(
                    app_payload=app_payload,
                    record=record,
                    compiled_app_version_id=compiled_app_version_id,
                    diagnostics=diagnostics,
                ),
                key=lambda module: module.module_id,
            )
        ),
        record=record,
        diagnostics=diagnostics,
    )

    if not modules:
        message = (
            f"Raw spec {record.relative_path} did not produce any catalog "
            f"modules."
        )
        if not allow_empty_app_versions:
            raise ValueError(message)
        diagnostics.append(
            CatalogRawSpecDiagnostic(
                code="raw_spec.module_collection_empty",
                severity="warning",
                module_id=module_id(
                    app_slug=record.app_slug,
                    app_version=record.app_version,
                    module_kind="unknown",
                    internal_name="__raw_spec_empty__",
                ),
                app_slug=record.app_slug,
                app_version=record.app_version,
                module_kind="unknown",
                internal_name="__raw_spec_empty__",
                field_path=(),
                collection_path=(),
                source_ref=record.relative_path,
                message=message,
            )
        )
        return None
    app_version = CatalogAppVersion(
        app_version_id=compiled_app_version_id,
        app_id=compiled_app_id,
        app_slug=record.app_slug,
        version=record.app_version,
        latest=record.latest,
        manifest_version=record.manifest_version,
        modules=modules,
        raw_spec_sha256=record.sha256,
        fingerprint="",
    )
    return CatalogAppVersion(
        app_version_id=app_version.app_version_id,
        app_id=app_version.app_id,
        app_slug=app_version.app_slug,
        version=app_version.version,
        latest=app_version.latest,
        manifest_version=app_version.manifest_version,
        modules=app_version.modules,
        raw_spec_sha256=app_version.raw_spec_sha256,
        fingerprint=payload_fingerprint(
            _app_version_fingerprint_payload(app_version)
        ),
    )


def _deduplicate_modules(
    *,
    modules: tuple[CatalogModule, ...],
    record: RawSpecRecord,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> tuple[CatalogModule, ...]:
    """Return the computed result for the caller."""
    deduped: list[CatalogModule] = []
    seen: set[str] = set()
    for module in modules:
        if module.module_id in seen:
            diagnostics.append(
                CatalogRawSpecDiagnostic(
                    code="raw_spec.module_duplicate",
                    severity="warning",
                    module_id=module.module_id,
                    app_slug=record.app_slug,
                    app_version=record.app_version,
                    module_kind=module.module_kind,
                    internal_name=module.internal_name,
                    field_path=(),
                    collection_path=(),
                    source_ref=record.relative_path,
                    message=(
                        "Raw module metadata repeats normalized module "
                        "identity "
                        ""
                        f"{module.module_id!r}; the first occurrence was kept."
                    ),
                )
            )
            continue
        seen.add(module.module_id)
        deduped.append(module)
    return tuple(deduped)


def _load_raw_spec_payload(
    *, repo_root: Path, record: RawSpecRecord
) -> JsonObject:
    """Load and verify one raw Make spec payload.

    Returns:
        The verified raw Make spec payload.

    Raises:
        FileNotFoundError: If a SQLite raw-spec payload is missing.
        TypeError: If a value has an invalid type.
        ValueError: If a value violates the expected contract.
    """
    if is_sqlite_raw_spec_ref(record.relative_path):
        bundle = load_sqlite_raw_spec_bundle(
            database_path=repo_root / DEFAULT_RAW_SPEC_SQLITE_DATABASE
        )
        if bundle is None or record.relative_path not in bundle.payloads_by_ref:
            message = (
                f"SQLite raw spec payload is missing: {record.relative_path}"
            )
            raise FileNotFoundError(message)
        return bundle.payloads_by_ref[record.relative_path]

    path = resolve_repo_relative_path(repo_root, Path(record.relative_path))
    payload_bytes = path.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    if digest != record.sha256:
        message = f"Raw spec hash mismatch for {path}."
        raise ValueError(message)
    payload = cast("object", json.loads(payload_bytes.decode("utf-8")))
    if not isinstance(payload, dict):
        message = f"Raw spec {path} must contain a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _compile_modules(
    *,
    app_payload: JsonObject,
    record: RawSpecRecord,
    compiled_app_version_id: str,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> Iterable[CatalogModule]:
    """Yield catalog modules from one raw app payload.

    Raises:
        TypeError: If a value has an invalid type.
    """
    for collection_key, module_kind in MODULE_COLLECTIONS:
        collection = app_payload.get(collection_key)
        if collection is None:
            continue
        if not isinstance(collection, list):
            message = (
                f"Raw spec module collection {collection_key!r} must be a list."
            )
            raise TypeError(message)
        for index, item in enumerate(cast("list[object]", collection)):
            module_payload = _module_payload(collection_key, index, item)
            yield _compile_module(
                module_payload=module_payload,
                module_kind=module_kind,
                record=record,
                compiled_app_version_id=compiled_app_version_id,
                diagnostics=diagnostics,
            )


def _module_payload(
    collection_key: str, index: int, item: object
) -> JsonObject:
    """Return one raw module object from a collection item.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if not isinstance(item, dict):
        message = f"Module {collection_key}[{index}] must be a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", item))


def _compile_module(
    *,
    module_payload: JsonObject,
    module_kind: CatalogModuleKind,
    record: RawSpecRecord,
    compiled_app_version_id: str,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> CatalogModule:
    """Compile one raw module into a catalog module.

    Returns:
        The catalog module.
    """
    internal_name = _required_text(module_payload, "name")
    display_name = _optional_text(module_payload, "label") or internal_name
    compiled_module_id = module_id(
        app_slug=record.app_slug,
        app_version=record.app_version,
        module_kind=module_kind,
        internal_name=internal_name,
    )
    diagnostic_context = RawFieldDiagnosticContext(
        diagnostics=diagnostics,
        compiled_module_id=compiled_module_id,
        record=record,
        module_kind=module_kind,
        internal_name=internal_name,
    )
    fields_by_direction = _compile_field_groups(
        module_payload=module_payload,
        diagnostic_context=diagnostic_context,
    )
    rpc_dependencies = tuple(
        sorted(
            {
                *extract_rpc_dependencies(module_payload),
                *(
                    rpc_dependency
                    for fields in fields_by_direction.values()
                    for field in fields
                    for rpc_dependency in field.rpc_dependencies
                ),
            }
        )
    )
    module = CatalogModule(
        module_id=compiled_module_id,
        app_version_id=compiled_app_version_id,
        app_slug=record.app_slug,
        app_version=record.app_version,
        module_kind=module_kind,
        internal_name=internal_name,
        display_name=display_name,
        external_id=(
            f"{record.app_slug}:{record.app_version}:{module_kind}:{internal_name}"
        ),
        deprecated=_bool_value(module_payload.get("deprecated")),
        parameters=fields_by_direction["parameter"],
        expect_schema=fields_by_direction["expect"],
        interface_schema=fields_by_direction["interface"],
        rpc_dependencies=rpc_dependencies,
        raw_spec_sha256=record.sha256,
        fingerprint="",
    )
    return CatalogModule(
        module_id=module.module_id,
        app_version_id=module.app_version_id,
        app_slug=module.app_slug,
        app_version=module.app_version,
        module_kind=module.module_kind,
        internal_name=module.internal_name,
        display_name=module.display_name,
        external_id=module.external_id,
        deprecated=module.deprecated,
        parameters=module.parameters,
        expect_schema=module.expect_schema,
        interface_schema=module.interface_schema,
        rpc_dependencies=module.rpc_dependencies,
        raw_spec_sha256=module.raw_spec_sha256,
        fingerprint=payload_fingerprint(_module_fingerprint_payload(module)),
    )


def _compile_field_groups(
    *,
    module_payload: JsonObject,
    diagnostic_context: RawFieldDiagnosticContext,
) -> dict[CatalogFieldDirection, tuple[CatalogField, ...]]:
    """Return compiled fields grouped by direction."""
    fields_by_direction: dict[
        CatalogFieldDirection, tuple[CatalogField, ...]
    ] = {
        "parameter": (),
        "expect": (),
        "interface": (),
    }
    for collection_key, direction in FIELD_COLLECTIONS:
        fields_by_direction[direction] = tuple(
            sorted(
                _compile_field_collection(
                    collection=module_payload.get(collection_key),
                    collection_key=collection_key,
                    direction=direction,
                    diagnostic_context=diagnostic_context,
                ),
                key=lambda field: field.field_id,
            )
        )
    return fields_by_direction


def _compile_field_collection(
    *,
    collection: object,
    collection_key: str,
    direction: CatalogFieldDirection,
    diagnostic_context: RawFieldDiagnosticContext,
) -> Iterable[CatalogField]:
    """Yield fields from one raw field collection.

    Returns:
        The documented result.

    """
    if collection is None:
        return ()
    if not isinstance(collection, list):
        _append_field_diagnostic(
            context=diagnostic_context,
            issue=RawFieldIssue(
                code="raw_spec.field_collection_shape_invalid",
                field_path=(),
                collection_path=(collection_key,),
                message=(
                    f"Raw field collection {collection_key!r} must be a list."
                ),
            ),
        )
        return ()
    fields: list[CatalogField] = []
    for index, item in enumerate(cast("list[object]", collection)):
        field_payload = _field_payload(
            item=item,
            context=diagnostic_context,
            issue=RawFieldIssue(
                code="raw_spec.field_item_shape_invalid",
                field_path=(),
                collection_path=(collection_key, index),
                message=(
                    f"Field {collection_key}[{index}] must be a JSON object."
                ),
            ),
        )
        if field_payload is None:
            continue
        fields.extend(
            _compile_field_tree(
                field_payload=field_payload,
                direction=direction,
                parent_path=(),
                collection_path=(collection_key, index),
                diagnostic_context=diagnostic_context,
            )
        )
    return _deduplicate_fields(
        fields,
        collection_key=collection_key,
        diagnostic_context=diagnostic_context,
    )


def _deduplicate_fields(
    fields: list[CatalogField],
    *,
    collection_key: str,
    diagnostic_context: RawFieldDiagnosticContext,
) -> tuple[CatalogField, ...]:
    """Return fields after quarantining duplicate Make raw field paths."""
    unique_fields: list[CatalogField] = []
    seen_field_ids: set[str] = set()
    for field in fields:
        if field.field_id in seen_field_ids:
            _append_field_diagnostic(
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.field_duplicate",
                    field_path=field.path,
                    collection_path=(collection_key,),
                    message=(
                        "Raw field metadata repeats the normalized field path "
                        f"{'.'.join(field.path)!r}; the first occurrence "
                        f"was kept."
                    ),
                ),
            )
            continue
        seen_field_ids.add(field.field_id)
        unique_fields.append(field)
    return tuple(unique_fields)


def _field_payload(
    *,
    item: object,
    context: RawFieldDiagnosticContext,
    issue: RawFieldIssue,
) -> JsonObject | None:
    """Return one raw field object, or quarantine malformed field metadata."""
    if not isinstance(item, dict):
        _append_field_diagnostic(context=context, issue=issue)
        return None
    return normalize_json_object(cast("Mapping[str, object]", item))


def _compile_field_tree(
    *,
    field_payload: JsonObject,
    direction: CatalogFieldDirection,
    parent_path: tuple[str, ...],
    collection_path: tuple[str | int, ...],
    diagnostic_context: RawFieldDiagnosticContext,
) -> tuple[CatalogField, ...]:
    """Compile one field and its nested field surfaces.

    Returns:
        The field surfaces.
    """
    raw_field_name = field_payload.get("name")
    field_name = (
        raw_field_name.strip() if isinstance(raw_field_name, str) else None
    )
    if field_name is None:
        _append_field_diagnostic(
            context=diagnostic_context,
            issue=RawFieldIssue(
                code="raw_spec.field_name_missing",
                field_path=parent_path,
                collection_path=collection_path,
                message="Raw field metadata is missing a non-empty name.",
            ),
        )
        return ()
    current_path = (*parent_path, field_name)
    current_field = _compile_field(
        field_payload=field_payload,
        direction=direction,
        compiled_module_id=diagnostic_context.compiled_module_id,
        current_path=current_path,
    )
    children: list[CatalogField] = [current_field]
    for nested_key in sorted(NESTED_FIELD_KEYS):
        nested = field_payload.get(nested_key)
        if nested is None:
            continue
        if not isinstance(nested, list):
            _append_field_diagnostic(
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.nested_field_collection_shape_invalid",
                    field_path=current_path,
                    collection_path=(*collection_path, nested_key),
                    message=(
                        f"Nested field collection {nested_key!r} under "
                        f"{'.'.join(current_path)} must be a list."
                    ),
                ),
            )
            continue
        for index, item in enumerate(cast("list[object]", nested)):
            nested_payload = _field_payload(
                item=item,
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.nested_field_item_shape_invalid",
                    field_path=current_path,
                    collection_path=(*collection_path, nested_key, index),
                    message=(
                        f"Nested field {nested_key}[{index}] under "
                        f"{'.'.join(current_path)} must be a JSON object."
                    ),
                ),
            )
            if nested_payload is None:
                continue
            children.extend(
                _compile_field_tree(
                    field_payload=nested_payload,
                    direction=direction,
                    parent_path=current_path,
                    collection_path=(*collection_path, nested_key, index),
                    diagnostic_context=diagnostic_context,
                )
            )
    return tuple(children)


def _compile_field(
    *,
    field_payload: JsonObject,
    direction: CatalogFieldDirection,
    compiled_module_id: str,
    current_path: tuple[str, ...],
) -> CatalogField:
    """Compile one raw field object.

    Returns:
        The catalog field.
    """
    compiled_field_id = field_id(
        parent_module_id=compiled_module_id,
        direction=direction,
        path=current_path,
    )
    constraints = _compile_constraints(
        raw_schema=field_payload,
        compiled_field_id=compiled_field_id,
    )
    field = CatalogField(
        field_id=compiled_field_id,
        module_id=compiled_module_id,
        direction=direction,
        path=current_path,
        label=_optional_text(field_payload, "label") or current_path[-1],
        required=_bool_value(field_payload.get("required")),
        field_type=canonicalize_catalog_field_type(
            _optional_text(field_payload, "type")
        ),
        advanced=_optional_bool(field_payload, "advanced"),
        external_id=f"{compiled_module_id}:{direction}:{'.'.join(current_path)}",
        rpc_dependencies=extract_rpc_dependencies(field_payload),
        raw_schema=field_payload,
        constraints=constraints,
        fingerprint="",
    )
    return CatalogField(
        field_id=field.field_id,
        module_id=field.module_id,
        direction=field.direction,
        path=field.path,
        label=field.label,
        required=field.required,
        field_type=field.field_type,
        advanced=field.advanced,
        external_id=field.external_id,
        rpc_dependencies=field.rpc_dependencies,
        raw_schema=field.raw_schema,
        constraints=field.constraints,
        fingerprint=payload_fingerprint(_field_fingerprint_payload(field)),
    )


def _append_field_diagnostic(
    *,
    context: RawFieldDiagnosticContext,
    issue: RawFieldIssue,
) -> None:
    """Record one quarantined raw-spec field metadata issue."""
    context.diagnostics.append(
        CatalogRawSpecDiagnostic(
            code=issue.code,
            severity="warning",
            module_id=context.compiled_module_id,
            app_slug=context.record.app_slug,
            app_version=context.record.app_version,
            module_kind=context.module_kind,
            internal_name=context.internal_name,
            field_path=issue.field_path,
            collection_path=issue.collection_path,
            source_ref=context.record.relative_path,
            message=issue.message,
        )
    )


def _compile_constraints(
    *,
    raw_schema: JsonObject,
    compiled_field_id: str,
) -> tuple[CatalogConstraint, ...]:
    """Compile normalized constraints for one field.

    Returns:
        The normalized field constraints.
    """
    constraint_payloads: list[tuple[str, JsonObject]] = []
    if isinstance(raw_schema.get("required"), bool):
        constraint_payloads.append(
            ("required", {"required": raw_schema["required"]})
        )
    field_type = canonicalize_catalog_field_type(
        _optional_text(raw_schema, "type")
    )
    if field_type is not None:
        constraint_payloads.append(("type", {"type": field_type}))
    enum_value = raw_schema.get("enum")
    if isinstance(enum_value, list):
        constraint_payloads.append(("enum", {"values": enum_value}))
    constraint_payloads.extend(_field_constraint_payloads(raw_schema))
    constraint_payloads.extend(
        ("rpc_dependency", {"dependency": rpc_dependency})
        for rpc_dependency in extract_rpc_dependencies(raw_schema)
    )

    constraints: list[CatalogConstraint] = []
    for key, value in constraint_payloads:
        stable_key = _stable_constraint_key(key, len(constraints))
        compiled_constraint_id = constraint_id(
            parent_field_id=compiled_field_id,
            key=stable_key,
        )
        constraint = CatalogConstraint(
            constraint_id=compiled_constraint_id,
            field_id=compiled_field_id,
            key=stable_key,
            value=value,
            fingerprint="",
        )
        constraints.append(
            CatalogConstraint(
                constraint_id=constraint.constraint_id,
                field_id=constraint.field_id,
                key=constraint.key,
                value=constraint.value,
                fingerprint=payload_fingerprint(
                    _constraint_fingerprint_payload(constraint)
                ),
            )
        )
    return tuple(constraints)


def _field_constraint_payloads(
    raw_schema: JsonObject,
) -> tuple[tuple[str, JsonObject], ...]:
    """Return additional raw field constraints as canonical payloads."""
    payloads: list[tuple[str, JsonObject]] = [
        (key, {key: raw_schema[key]})
        for key in sorted(FIELD_CONSTRAINT_KEYS)
        if key in raw_schema
    ]
    validate = raw_schema.get("validate")
    if isinstance(validate, dict):
        validate_payload = normalize_json_object(
            cast("Mapping[str, object]", validate)
        )
        payloads.extend(
            (key, {key: validate_payload[key]})
            for key in sorted(VALIDATE_CONSTRAINT_KEYS)
            if key in validate_payload and key not in raw_schema
        )
    return tuple(payloads)


def extract_rpc_dependencies(value: object) -> tuple[str, ...]:
    """Return sorted RPC dependency references found in a JSON-like value."""
    dependencies = sorted(set(_iter_rpc_dependencies(value)))
    return tuple(dependencies)


def _iter_rpc_dependencies(value: object) -> Iterable[str]:
    """Yield RPC dependency references from a JSON-like value."""
    if isinstance(value, str):
        if value.startswith(RPC_PREFIX):
            yield value
        return
    if isinstance(value, dict):
        for item_key, item_value in cast(
            "Mapping[object, object]", value
        ).items():
            key_text = str(item_key)
            if (
                "rpc" in key_text.lower()
                and isinstance(item_value, str)
                and item_value.strip()
            ):
                yield item_value
            yield from _iter_rpc_dependencies(item_value)
        return
    if isinstance(value, list):
        for item in cast("list[object]", value):
            yield from _iter_rpc_dependencies(item)


def _group_app_versions(
    app_versions: tuple[CatalogAppVersion, ...],
) -> tuple[CatalogApp, ...]:
    """Group app versions under durable app identities.

    Returns:
        The grouped app versions under durable app identities.
    """
    versions_by_app: dict[str, list[CatalogAppVersion]] = defaultdict(list)
    for version in app_versions:
        versions_by_app[version.app_slug].append(version)

    apps: list[CatalogApp] = []
    for app_slug, versions in sorted(versions_by_app.items()):
        ordered_versions = tuple(
            sorted(
                versions,
                key=lambda version: module_version_sort_key(version.version),
            )
        )
        app = CatalogApp(
            app_id=app_id(app_slug),
            app_slug=app_slug,
            label=app_slug,
            external_id=app_slug,
            deprecated=all(
                module.deprecated
                for version in ordered_versions
                for module in version.modules
            ),
            versions=ordered_versions,
            fingerprint="",
        )
        apps.append(
            CatalogApp(
                app_id=app.app_id,
                app_slug=app.app_slug,
                label=app.label,
                external_id=app.external_id,
                deprecated=app.deprecated,
                versions=app.versions,
                fingerprint=payload_fingerprint(_app_fingerprint_payload(app)),
            )
        )
    return tuple(apps)


def _diagnostic_sort_key(
    diagnostic: CatalogRawSpecDiagnostic,
) -> tuple[str, str, str, str, tuple[str, ...], str]:
    """Return the deterministic ordering key for raw-spec diagnostics."""
    return (
        diagnostic.module_id,
        diagnostic.code,
        diagnostic.source_ref,
        ".".join(diagnostic.field_path),
        tuple(str(part) for part in diagnostic.collection_path),
        diagnostic.message,
    )


def _snapshot_fingerprint_payload(snapshot: CatalogSnapshot) -> JsonObject:
    """Return the fingerprint payload for a snapshot."""
    return {
        "catalog_schema_version": snapshot.catalog_schema_version,
        "raw_spec_manifest_sha256": snapshot.raw_spec_manifest_sha256,
        "apps": [
            {"app_id": app.app_id, "fingerprint": app.fingerprint}
            for app in snapshot.apps
        ],
    }


def _app_fingerprint_payload(app: CatalogApp) -> JsonObject:
    """Return the fingerprint payload for an app."""
    return {
        "app_id": app.app_id,
        "app_slug": app.app_slug,
        "label": app.label,
        "external_id": app.external_id,
        "deprecated": app.deprecated,
        "versions": [
            {
                "app_version_id": version.app_version_id,
                "fingerprint": version.fingerprint,
            }
            for version in app.versions
        ],
    }


def _app_version_fingerprint_payload(version: CatalogAppVersion) -> JsonObject:
    """Return the fingerprint payload for an app version."""
    return {
        "app_version_id": version.app_version_id,
        "app_id": version.app_id,
        "app_slug": version.app_slug,
        "version": version.version,
        "latest": version.latest,
        "manifest_version": version.manifest_version,
        "modules": [
            {"module_id": module.module_id, "fingerprint": module.fingerprint}
            for module in version.modules
        ],
        "raw_spec_sha256": version.raw_spec_sha256,
    }


def _module_fingerprint_payload(module: CatalogModule) -> JsonObject:
    """Return the fingerprint payload for a module."""
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
        "parameters": _field_fingerprints(module.parameters),
        "expect_schema": _field_fingerprints(module.expect_schema),
        "interface_schema": _field_fingerprints(module.interface_schema),
        "rpc_dependencies": list(module.rpc_dependencies),
        "raw_spec_sha256": module.raw_spec_sha256,
    }


def _field_fingerprints(fields: tuple[CatalogField, ...]) -> list[JsonObject]:
    """Return field ID and fingerprint pairs for fingerprint payloads."""
    return [
        {"field_id": field.field_id, "fingerprint": field.fingerprint}
        for field in fields
    ]


def _field_fingerprint_payload(field: CatalogField) -> JsonObject:
    """Return the fingerprint payload for a field."""
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
            {
                "constraint_id": constraint.constraint_id,
                "fingerprint": constraint.fingerprint,
            }
            for constraint in field.constraints
        ],
    }


def _constraint_fingerprint_payload(
    constraint: CatalogConstraint,
) -> JsonObject:
    """Return the fingerprint payload for a constraint."""
    return {
        "constraint_id": constraint.constraint_id,
        "field_id": constraint.field_id,
        "key": constraint.key,
        "value": constraint.value,
    }


def _required_object(payload: JsonObject, key: str) -> JsonObject:
    """Return one required object member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Raw Make spec member {key!r} must be an object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", value))


def _required_text(payload: JsonObject, key: str) -> str:
    """Return one required non-empty text member.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _optional_text(payload, key)
    if value is None:
        message = f"Raw Make spec member {key!r} must be non-empty text."
        raise ValueError(message)
    return value


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional non-empty text member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"Raw Make spec member {key!r} must be text when present."
        raise TypeError(message)
    return value.strip() or None


def _optional_bool(payload: JsonObject, key: str) -> bool | None:
    """Return one optional strict Boolean member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, bool):
        message = (
            f"Raw Make spec member {key!r} must be true or false when present."
        )
        raise TypeError(message)
    return value


def _bool_value(value: object) -> bool:
    """Return a strict Boolean value with false as the absent fallback.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return False
    if not isinstance(value, bool):
        message = "Boolean raw Make spec members must be true or false."
        raise TypeError(message)
    return value


def _stable_constraint_key(kind: str, index: int) -> str:
    """Return a unique deterministic constraint key."""
    return f"{kind}_{index:03d}"


def catalog_snapshot_json(snapshot: CatalogSnapshot) -> JsonObject:
    """Return one validated catalog snapshot JSON payload."""
    validate_catalog_snapshot(snapshot)
    return catalog_snapshot_to_json(snapshot)
