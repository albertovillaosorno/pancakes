# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.knowledge-store-authority-chain
# - 001064#repo.make-knowledge.runtime-source-label
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Pure catalog projections from loaded Make knowledge-store facts.

Boundary contract:
- Owns: deterministic conversion from knowledge query facts to catalog read
models.
- Must not: open databases, read raw specs, shape MCP responses, or validate
blueprints.
- Allows: filtering loaded structural facts and deriving catalog entity
groupings.
- Split when: projections target a non-catalog read model.
- Merge when: another module owns the same pure knowledge-to-catalog projection.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import TYPE_CHECKING, cast

from catalog.identifiers import (
    app_id,
    app_version_id,
    module_token_match_keys,
    module_version_sort_key,
)
from catalog.json_payloads import payload_fingerprint
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
    CatalogSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog.knowledge.models import (
        KnowledgeConstraintFact,
        KnowledgeFieldFact,
        KnowledgeModuleFact,
        KnowledgeStoreQuery,
    )
    from catalog.models import JsonObject


def knowledge_query_to_catalog_snapshot(
    *,
    query: KnowledgeStoreQuery,
    module_ids: tuple[str, ...] = (),
    diagnostics: tuple[CatalogRawSpecDiagnostic, ...] = (),
    generated_at_utc: str = "knowledge-store",
) -> CatalogSnapshot:
    """Project loaded structural knowledge facts into a catalog snapshot.

    Returns:
        A deterministic catalog snapshot containing the selected knowledge
        modules.
    """
    requested = frozenset(module_ids)
    selected_modules = tuple(
        module
        for module in query.modules
        if not requested or module.module_id in requested
    )
    selected_module_ids = {module.module_id for module in selected_modules}
    fields_by_module: dict[str, list[KnowledgeFieldFact]] = defaultdict(list)
    for field in query.fields:
        if field.module_id not in selected_module_ids:
            continue
        fields_by_module[field.module_id].append(field)
    selected_field_ids = {
        field.field_id
        for module_fields in fields_by_module.values()
        for field in module_fields
    }
    constraints_by_field: dict[str, list[KnowledgeConstraintFact]] = (
        defaultdict(list)
    )
    for constraint in query.constraints:
        if constraint.field_id not in selected_field_ids:
            continue
        constraints_by_field[constraint.field_id].append(constraint)
    modules = tuple(
        _catalog_module_from_knowledge(
            module=module,
            fields=tuple(fields_by_module.get(module.module_id, ())),
            constraints_by_field=constraints_by_field,
        )
        for module in selected_modules
    )
    return CatalogSnapshot(
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        raw_spec_manifest_sha256=query.fingerprint,
        apps=_catalog_apps_from_modules(modules),
        fingerprint=query.fingerprint,
        diagnostics=diagnostics,
    )


def knowledge_module_ids_for_token(
    *,
    query: KnowledgeStoreQuery,
    module_token: str,
) -> tuple[str, ...]:
    """Return knowledge-store module IDs that can resolve one AST module token.

    Returns:
        Matching module IDs sorted deterministically, or an empty tuple.
    """
    token = module_token.strip()
    if token.startswith("module:"):
        return (token,)
    if ":" not in token:
        return ()
    app_slug, raw_action = token.split(":", maxsplit=1)
    app_slug_key = app_slug.casefold()
    action_keys = module_token_match_keys(raw_action)
    matches = [
        module.module_id
        for module in query.modules
        if module.app_slug.casefold() == app_slug_key
        and action_keys
        & (
            module_token_match_keys(module.internal_name)
            | module_token_match_keys(module.display_name)
        )
    ]
    return tuple(sorted(matches))


def dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return non-empty text values in source order without duplicates.

    Returns:
        The deterministic de-duplicated text tuple.
    """
    deduped: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in deduped:
            deduped.append(text)
    return tuple(deduped)


def _catalog_module_from_knowledge(
    *,
    module: KnowledgeModuleFact,
    fields: tuple[KnowledgeFieldFact, ...],
    constraints_by_field: Mapping[str, list[KnowledgeConstraintFact]],
) -> CatalogModule:
    """Return one catalog module projected from knowledge-store facts."""
    catalog_fields = tuple(
        _catalog_field_from_knowledge(
            field=field,
            constraints=tuple(constraints_by_field.get(field.field_id, ())),
        )
        for field in fields
    )
    parameters = tuple(
        field for field in catalog_fields if field.direction == "parameter"
    )
    expect_schema = tuple(
        field for field in catalog_fields if field.direction == "expect"
    )
    interface_schema = tuple(
        field for field in catalog_fields if field.direction == "interface"
    )
    rpc_dependencies = tuple(
        sorted(
            {
                dependency
                for field in catalog_fields
                for dependency in field.rpc_dependencies
            }
        )
    )
    return CatalogModule(
        module_id=module.module_id,
        app_version_id=app_version_id(module.app_slug, module.app_version),
        app_slug=module.app_slug,
        app_version=module.app_version,
        module_kind=cast("CatalogModuleKind", module.module_kind),
        internal_name=module.internal_name,
        display_name=module.display_name,
        external_id=module.module_id,
        deprecated=module.deprecated,
        parameters=parameters,
        expect_schema=expect_schema,
        interface_schema=interface_schema,
        rpc_dependencies=rpc_dependencies,
        raw_spec_sha256=module.fingerprint,
        fingerprint=module.fingerprint,
    )


def _catalog_field_from_knowledge(
    *,
    field: KnowledgeFieldFact,
    constraints: tuple[KnowledgeConstraintFact, ...],
) -> CatalogField:
    """Return one catalog field projected from knowledge-store facts."""
    catalog_constraints = tuple(
        _catalog_constraint_from_knowledge(item) for item in constraints
    )
    advanced = _advanced_setting_from_constraints(catalog_constraints)
    rpc_dependencies = tuple(
        sorted(
            {
                value
                for constraint in constraints
                for value in _rpc_dependencies_from_text(constraint.value_json)
            }
        )
    )
    return CatalogField(
        field_id=field.field_id,
        module_id=field.module_id,
        direction=cast("CatalogFieldDirection", field.direction),
        path=field.path,
        label=field.label,
        required=field.required,
        field_type=field.field_type,
        advanced=advanced,
        external_id=field.field_id,
        rpc_dependencies=rpc_dependencies,
        raw_schema=_field_raw_schema(field=field, advanced=advanced),
        constraints=catalog_constraints,
        fingerprint=field.fingerprint,
    )


def _field_raw_schema(
    *, field: KnowledgeFieldFact, advanced: bool | None
) -> JsonObject:
    """Return the projected raw-schema summary for one knowledge field."""
    schema: JsonObject = {
        "path": list(field.path),
        "label": field.label,
        "required": field.required,
        "type": field.field_type,
    }
    if advanced is not None:
        schema["advanced"] = advanced
    return schema


def _advanced_setting_from_constraints(
    constraints: tuple[CatalogConstraint, ...],
) -> bool | None:
    """Return the advanced setting preserved in field constraints."""
    for constraint in constraints:
        if constraint.key != "advanced":
            continue
        value = constraint.value.get("advanced")
        if isinstance(value, bool):
            return value
    return None


def _catalog_constraint_from_knowledge(
    constraint: KnowledgeConstraintFact,
) -> CatalogConstraint:
    """Return one catalog constraint projected from knowledge-store facts."""
    return CatalogConstraint(
        constraint_id=constraint.constraint_id,
        field_id=constraint.field_id,
        key=constraint.constraint_key,
        value=_constraint_value(constraint.value_json),
        fingerprint=constraint.fingerprint,
    )


def _constraint_value(value_json: str) -> JsonObject:
    """Return a non-empty JSON object for one stored constraint value."""
    try:
        parsed = cast("object", json.loads(value_json))
    except json.JSONDecodeError:
        return {"value": value_json}
    if isinstance(parsed, dict) and parsed:
        return {
            str(key): value
            for key, value in cast("Mapping[object, object]", parsed).items()
        }
    return {"value": parsed}


def _rpc_dependencies_from_text(value_json: str) -> tuple[str, ...]:
    """Return raw RPC references visible in one stored constraint payload."""
    return tuple(sorted(set(re.findall(r'rpc://[^"\s,}\]]+', value_json))))


def _catalog_apps_from_modules(
    modules: tuple[CatalogModule, ...],
) -> tuple[CatalogApp, ...]:
    """Group catalog modules by app and version.

    Returns:
        Catalog apps with versions and modules grouped deterministically.
    """
    grouped: dict[str, dict[str, list[CatalogModule]]] = {}
    for module in modules:
        grouped.setdefault(module.app_slug, {}).setdefault(
            module.app_version, []
        ).append(module)
    apps: list[CatalogApp] = []
    for slug, versions_by_number in sorted(grouped.items()):
        ordered_versions = tuple(
            sorted(
                versions_by_number.items(),
                key=lambda item: module_version_sort_key(item[0]),
            )
        )
        versions = tuple(
            _catalog_app_version_from_modules(
                slug=slug,
                version=version,
                modules=version_modules,
                latest=index == 0,
            )
            for index, (version, version_modules) in enumerate(ordered_versions)
        )
        apps.append(
            CatalogApp(
                app_id=app_id(slug),
                app_slug=slug,
                label=slug.replace("-", " ").title(),
                external_id=slug,
                deprecated=all(
                    module.deprecated for module in _flatten_versions(versions)
                ),
                versions=versions,
                fingerprint=payload_fingerprint(
                    {
                        "app_slug": slug,
                        "versions": [
                            version.app_version_id for version in versions
                        ],
                    }
                ),
            )
        )
    return tuple(apps)


def _catalog_app_version_from_modules(
    *,
    slug: str,
    version: str,
    modules: list[CatalogModule],
    latest: bool,
) -> CatalogAppVersion:
    """Return one catalog app version from grouped modules."""
    sorted_modules = tuple(sorted(modules, key=lambda module: module.module_id))
    fingerprint = payload_fingerprint(
        {
            "app_slug": slug,
            "version": version,
            "modules": [module.module_id for module in sorted_modules],
        }
    )
    return CatalogAppVersion(
        app_version_id=app_version_id(slug, version),
        app_id=app_id(slug),
        app_slug=slug,
        version=version,
        latest=latest,
        manifest_version=1,
        modules=sorted_modules,
        raw_spec_sha256=fingerprint,
        fingerprint=fingerprint,
    )


def _flatten_versions(
    versions: tuple[CatalogAppVersion, ...],
) -> tuple[CatalogModule, ...]:
    """Return modules from app versions."""
    return tuple(module for version in versions for module in version.modules)
