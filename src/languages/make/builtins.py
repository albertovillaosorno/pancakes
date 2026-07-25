# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make-native built-in module manifests.

Boundary contract:
- Owns: Make target built-ins that are part of scenario topology rather than
provider apps.
- Must not: call Make.com, scrape raw specs, define generic AST semantics, or
persist artifacts.
- Allows: deterministic local manifest facts for Make export, validation, and
MCP reporting.
- Split when: another target language gains its own built-in manifest registry.
- Merge when: another Make module defines the same built-in registry.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.knowledge.models import KnowledgeModuleFact
from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    CatalogApp,
    CatalogAppVersion,
    CatalogField,
    CatalogModule,
    CatalogSnapshot,
)

from languages.make.tokens import module_token_resolution_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from catalog.models import CatalogFieldDirection, CatalogModuleKind

SOURCE_LABEL_MAKE_BUILTIN_MANIFEST: Final = "make_builtin_manifest"
SOURCE_RANK_MAKE_BUILTIN_MANIFEST: Final = 5
MAKE_BUILTIN_GENERATED_AT: Final = "make-builtin-manifest"
MAKE_BUILTIN_BASIC_ROUTER_MODULE_ID: Final = (
    "module:builtin:1.8.3:router:BasicRouter"
)
MAKE_BUILTIN_ITERATOR_MODULE_ID: Final = (
    "module:builtin:1.8.3:transformer:Iterator"
)
MAKE_BUILTIN_ARRAY_AGGREGATOR_MODULE_ID: Final = (
    "module:builtin:1.8.3:aggregator:BasicAggregator"
)
MAKE_BUILTIN_TEXT_AGGREGATOR_MODULE_ID: Final = (
    "module:util:1.11.14:aggregator:TextAggregator"
)
MAKE_BUILTIN_REPEATER_MODULE_ID: Final = (
    "module:builtin:1.8.3:action:BasicRepeater"
)
MAKE_BUILTIN_SLEEP_MODULE_ID: Final = "module:util:1.11.14:action:FunctionSleep"
MAKE_BUILTIN_SET_VARIABLE_MODULE_ID: Final = (
    "module:util:1.11.14:action:SetVariable2"
)
MAKE_BUILTIN_GET_VARIABLE_MODULE_ID: Final = (
    "module:util:1.11.14:action:GetVariable2"
)
MAKE_BUILTIN_INCREMENT_FUNCTION_MODULE_ID: Final = (
    "module:util:1.11.14:action:FunctionIncrement"
)


class MakeBuiltinModuleManifest(NamedTuple):
    """One Make built-in module manifest."""

    module_id: str
    module_ref: str
    app_slug: str
    app_label: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    native_version: int
    topology_role: str
    route_container: bool
    supports_route_filters: bool
    confidence: str
    provenance: str
    aliases: tuple[str, ...] = ()
    parameter_names: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        """Return a deterministic manifest fingerprint."""
        return _fingerprint(
            {
                "module_id": self.module_id,
                "module_ref": self.module_ref,
                "app_version": self.app_version,
                "module_kind": self.module_kind,
                "native_version": self.native_version,
                "topology_role": self.topology_role,
                "confidence": self.confidence,
                "provenance": self.provenance,
                "aliases": self.aliases,
                "parameter_names": self.parameter_names,
            }
        )


MAKE_BUILTIN_MODULE_MANIFESTS: Final[tuple[MakeBuiltinModuleManifest, ...]] = (
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_BASIC_ROUTER_MODULE_ID,
        module_ref="builtin:BasicRouter",
        app_slug="builtin",
        app_label="Make built-ins",
        app_version="1.8.3",
        module_kind="router",
        internal_name="BasicRouter",
        display_name="Router",
        native_version=1,
        topology_role="route_container",
        route_container=True,
        supports_route_filters=True,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_ITERATOR_MODULE_ID,
        module_ref="builtin:Iterator",
        app_slug="builtin",
        app_label="Make built-ins",
        app_version="1.8.3",
        module_kind="transformer",
        internal_name="Iterator",
        display_name="Iterator",
        native_version=1,
        topology_role="array_iterator",
        route_container=False,
        supports_route_filters=False,
        confidence="make_course_fixture",
        provenance="local_make_builtin_manifest",
        aliases=(
            "builtin:BasicFeeder",
            "util:Iterator",
            "tools:Iterator",
            "builtin.iterator",
            "iterator",
        ),
        parameter_names=("array",),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_ARRAY_AGGREGATOR_MODULE_ID,
        module_ref="builtin:BasicAggregator",
        app_slug="builtin",
        app_label="Make built-ins",
        app_version="1.8.3",
        module_kind="aggregator",
        internal_name="BasicAggregator",
        display_name="Array aggregator",
        native_version=1,
        topology_role="array_aggregator",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=(
            "array aggregator",
            "builtin:ArrayAggregator",
            "builtin.array_aggregator",
            "builtin:BasicAggregator",
        ),
        parameter_names=("feeder",),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_TEXT_AGGREGATOR_MODULE_ID,
        module_ref="util:TextAggregator",
        app_slug="util",
        app_label="Tools",
        app_version="1.11.14",
        module_kind="aggregator",
        internal_name="TextAggregator",
        display_name="Text aggregator",
        native_version=1,
        topology_role="text_aggregator",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=(
            "text aggregator",
            "tools:TextAggregator",
            "util.TextAggregator",
        ),
        parameter_names=("feeder",),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_REPEATER_MODULE_ID,
        module_ref="builtin:BasicRepeater",
        app_slug="builtin",
        app_label="Make built-ins",
        app_version="1.8.3",
        module_kind="action",
        internal_name="BasicRepeater",
        display_name="Repeater",
        native_version=1,
        topology_role="flow_control_repeater",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=("repeater", "builtin:Repeater", "repeat"),
        parameter_names=("start", "repeats", "step"),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_SLEEP_MODULE_ID,
        module_ref="util:FunctionSleep",
        app_slug="util",
        app_label="Tools",
        app_version="1.11.14",
        module_kind="action",
        internal_name="FunctionSleep",
        display_name="Sleep",
        native_version=1,
        topology_role="flow_control_sleep",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=("sleep", "delay", "tools:Sleep", "util:Sleep"),
        parameter_names=("duration",),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_SET_VARIABLE_MODULE_ID,
        module_ref="util:SetVariable2",
        app_slug="util",
        app_label="Tools",
        app_version="1.11.14",
        module_kind="action",
        internal_name="SetVariable2",
        display_name="Set variable",
        native_version=1,
        topology_role="flow_control_set_variable",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=("set variable", "util:SetVariable", "tools:SetVariable"),
        parameter_names=("name", "scope"),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_GET_VARIABLE_MODULE_ID,
        module_ref="util:GetVariable2",
        app_slug="util",
        app_label="Tools",
        app_version="1.11.14",
        module_kind="action",
        internal_name="GetVariable2",
        display_name="Get variable",
        native_version=1,
        topology_role="flow_control_get_variable",
        route_container=False,
        supports_route_filters=False,
        confidence="make_raw_spec",
        provenance="local_make_builtin_manifest",
        aliases=("get variable", "util:GetVariable", "tools:GetVariable"),
        parameter_names=("name",),
    ),
    MakeBuiltinModuleManifest(
        module_id=MAKE_BUILTIN_INCREMENT_FUNCTION_MODULE_ID,
        module_ref="util:FunctionIncrement",
        app_slug="util",
        app_label="Tools",
        app_version="1.11.14",
        module_kind="action",
        internal_name="FunctionIncrement",
        display_name="Increment function",
        native_version=1,
        topology_role="flow_control_increment",
        route_container=False,
        supports_route_filters=False,
        confidence="make_native_fixture",
        provenance="local_make_builtin_manifest",
        aliases=("increment", "increment function", "tools:Increment"),
        parameter_names=("reset",),
    ),
)


def make_builtin_module_ids_for_token(module_token: str) -> tuple[str, ...]:
    """Return known Make built-in module IDs for a module token."""
    manifest = make_builtin_manifest_for_token(module_token)
    return () if manifest is None else (manifest.module_id,)


def make_builtin_module_ids_for_tokens(
    module_tokens: tuple[str, ...],
) -> tuple[str, ...]:
    """Return known Make built-in module IDs for module tokens."""
    return _dedupe(
        module_id
        for module_token in module_tokens
        for module_id in make_builtin_module_ids_for_token(module_token)
    )


def make_builtin_manifest_for_module_id(
    module_id: str,
) -> MakeBuiltinModuleManifest | None:
    """Return the built-in manifest for one module ID, if known."""
    normalized = module_id.casefold().strip()
    for manifest in MAKE_BUILTIN_MODULE_MANIFESTS:
        if manifest.module_id.casefold() == normalized:
            return manifest
    return None


def make_builtin_manifest_for_token(
    module_token: str,
) -> MakeBuiltinModuleManifest | None:
    """Return the built-in manifest for one Make module token, if known."""
    normalized = module_token_resolution_key(module_token)
    for manifest in MAKE_BUILTIN_MODULE_MANIFESTS:
        if normalized in {
            module_token_resolution_key(manifest.module_ref),
            module_token_resolution_key(manifest.internal_name),
            module_token_resolution_key(manifest.display_name),
            *(module_token_resolution_key(alias) for alias in manifest.aliases),
        }:
            return manifest
    return None


def make_builtin_requested_module_ids(
    module_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return requested module IDs that have local Make built-in manifests."""
    return tuple(
        module_id
        for module_id in _dedupe(module_ids)
        if make_builtin_manifest_for_module_id(module_id) is not None
    )


def unknown_make_builtin_module_ids(
    module_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return requested Make built-in module IDs with no local manifest."""
    return tuple(
        module_id
        for module_id in _dedupe(module_ids)
        if module_id.casefold().startswith("module:builtin:")
        and make_builtin_manifest_for_module_id(module_id) is None
    )


def make_builtin_knowledge_module_fact(
    manifest: MakeBuiltinModuleManifest,
) -> KnowledgeModuleFact:
    """Return a knowledge-store shaped module fact for one built-in manifest."""
    return KnowledgeModuleFact(
        module_id=manifest.module_id,
        app_slug=manifest.app_slug,
        app_version=manifest.app_version,
        module_kind=manifest.module_kind,
        internal_name=manifest.internal_name,
        display_name=manifest.display_name,
        deprecated=False,
        fingerprint=manifest.fingerprint,
        adr_anchor=manifest.provenance,
    )


def make_builtin_catalog_snapshot(
    module_ids: tuple[str, ...] = (),
) -> CatalogSnapshot:
    """Return a catalog snapshot containing local Make built-in manifests."""
    manifests = _selected_manifests(module_ids)
    return CatalogSnapshot(
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        generated_at_utc=MAKE_BUILTIN_GENERATED_AT,
        raw_spec_manifest_sha256=_fingerprint(
            {"make_builtin_manifests": "none"}
        ),
        apps=_catalog_apps_for_manifests(manifests),
        fingerprint=_fingerprint(
            {"module_ids": [manifest.module_id for manifest in manifests]}
        ),
        diagnostics=(),
    )


def with_make_builtin_modules(
    snapshot: CatalogSnapshot,
    *,
    module_ids: tuple[str, ...] = (),
) -> CatalogSnapshot:
    """Return the computed result for the caller."""
    manifests = tuple(
        manifest
        for manifest in _selected_manifests(module_ids)
        if manifest.module_id not in _snapshot_module_ids(snapshot)
    )
    if not manifests:
        return snapshot
    apps = _merge_catalog_apps_with_manifests(snapshot.apps, manifests)
    return snapshot._replace(
        apps=apps,
        fingerprint=_fingerprint(
            {
                "base": snapshot.fingerprint,
                "make_builtin_module_ids": [
                    manifest.module_id for manifest in manifests
                ],
            }
        ),
    )


def _merge_catalog_apps_with_manifests(
    apps: tuple[CatalogApp, ...],
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> tuple[CatalogApp, ...]:
    remaining = list(manifests)
    merged_apps: list[CatalogApp] = []
    for app in apps:
        app_manifests = tuple(
            manifest
            for manifest in remaining
            if manifest.app_slug == app.app_slug
            or f"app:{manifest.app_slug}" == app.app_id
        )
        if not app_manifests:
            merged_apps.append(app)
            continue
        merged_apps.append(
            _merge_catalog_app_with_manifests(app, app_manifests)
        )
        consumed = {manifest.module_id for manifest in app_manifests}
        remaining = [
            manifest
            for manifest in remaining
            if manifest.module_id not in consumed
        ]
    return (*merged_apps, *_catalog_apps_for_manifests(tuple(remaining)))


def _merge_catalog_app_with_manifests(
    app: CatalogApp,
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> CatalogApp:
    remaining = list(manifests)
    versions: list[CatalogAppVersion] = []
    for version in app.versions:
        version_manifests = tuple(
            manifest
            for manifest in remaining
            if manifest.app_slug == version.app_slug
            and manifest.app_version == version.version
        )
        if not version_manifests:
            versions.append(version)
            continue
        versions.append(
            _merge_catalog_app_version_with_manifests(
                version, version_manifests
            )
        )
        consumed = {manifest.module_id for manifest in version_manifests}
        remaining = [
            manifest
            for manifest in remaining
            if manifest.module_id not in consumed
        ]
    versions.extend(_catalog_app_versions_for_manifests(tuple(remaining)))
    return app._replace(
        versions=tuple(versions),
        fingerprint=_fingerprint(
            {
                "base": app.fingerprint,
                "make_builtin_module_ids": [
                    manifest.module_id for manifest in manifests
                ],
            }
        ),
    )


def _merge_catalog_app_version_with_manifests(
    version: CatalogAppVersion,
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> CatalogAppVersion:
    existing_module_ids = {module.module_id for module in version.modules}
    modules = (
        *version.modules,
        *(
            _catalog_module(manifest)
            for manifest in manifests
            if manifest.module_id not in existing_module_ids
        ),
    )
    return version._replace(
        modules=modules,
        raw_spec_sha256=_fingerprint(
            {
                "base": version.raw_spec_sha256,
                "make_builtin_module_ids": [
                    manifest.module_id for manifest in manifests
                ],
            }
        ),
        fingerprint=_fingerprint(
            {
                "base": version.fingerprint,
                "module_ids": [module.module_id for module in modules],
            }
        ),
    )


def make_builtin_manifest_payload(
    manifest: MakeBuiltinModuleManifest,
) -> dict[str, object]:
    """Return a JSON-ready manifest summary for MCP reporting."""
    return {
        "module_id": manifest.module_id,
        "token": manifest.module_ref,
        "app_slug": manifest.app_slug,
        "app_version": manifest.app_version,
        "module_kind": manifest.module_kind,
        "internal_name": manifest.internal_name,
        "display_name": manifest.display_name,
        "native_version": manifest.native_version,
        "topology_role": manifest.topology_role,
        "route_container": manifest.route_container,
        "supports_route_filters": manifest.supports_route_filters,
        "confidence": manifest.confidence,
        "provenance": manifest.provenance,
        "source_label": SOURCE_LABEL_MAKE_BUILTIN_MANIFEST,
        "source_rank": SOURCE_RANK_MAKE_BUILTIN_MANIFEST,
        "aliases": list(manifest.aliases),
        "required_parameters": list(manifest.parameter_names),
    }


def _selected_manifests(
    module_ids: tuple[str, ...],
) -> tuple[MakeBuiltinModuleManifest, ...]:
    if not module_ids:
        return MAKE_BUILTIN_MODULE_MANIFESTS
    requested = set(make_builtin_requested_module_ids(module_ids))
    return tuple(
        manifest
        for manifest in MAKE_BUILTIN_MODULE_MANIFESTS
        if manifest.module_id in requested
    )


def _catalog_apps_for_manifests(
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> tuple[CatalogApp, ...]:
    if not manifests:
        return ()
    grouped: dict[str, list[MakeBuiltinModuleManifest]] = {}
    for manifest in manifests:
        grouped.setdefault(manifest.app_slug, []).append(manifest)
    return tuple(
        _catalog_app_for_manifests(tuple(group))
        for _, group in sorted(grouped.items())
    )


def _catalog_app_for_manifests(
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> CatalogApp:
    manifest = manifests[0]
    versions = _catalog_app_versions_for_manifests(manifests)
    fingerprint = _fingerprint(
        {
            "make_builtin_app_slug": manifest.app_slug,
            "make_builtin_versions": [
                version.fingerprint for version in versions
            ],
        }
    )
    return CatalogApp(
        app_id=f"app:{manifest.app_slug}",
        app_slug=manifest.app_slug,
        label=manifest.app_label,
        external_id=f"make:{manifest.app_slug}",
        deprecated=False,
        versions=versions,
        fingerprint=fingerprint,
    )


def _catalog_app_versions_for_manifests(
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> tuple[CatalogAppVersion, ...]:
    grouped: dict[tuple[str, str], list[MakeBuiltinModuleManifest]] = {}
    for manifest in manifests:
        grouped.setdefault(
            (manifest.app_slug, manifest.app_version), []
        ).append(manifest)
    return tuple(
        _catalog_app_version_for_manifests(tuple(group))
        for _, group in sorted(grouped.items())
    )


def _catalog_app_version_for_manifests(
    manifests: tuple[MakeBuiltinModuleManifest, ...],
) -> CatalogAppVersion:
    manifest = manifests[0]
    modules = tuple(_catalog_module(item) for item in manifests)
    fingerprint = _fingerprint(
        {"modules": [module.fingerprint for module in modules]}
    )
    return CatalogAppVersion(
        app_version_id=f"app-version:{manifest.app_slug}:{manifest.app_version}",
        app_id=f"app:{manifest.app_slug}",
        app_slug=manifest.app_slug,
        version=manifest.app_version,
        latest=True,
        manifest_version=1,
        modules=modules,
        raw_spec_sha256=_fingerprint(
            {"make_builtin_module_ids": [item.module_id for item in manifests]}
        ),
        fingerprint=fingerprint,
    )


def _catalog_module(manifest: MakeBuiltinModuleManifest) -> CatalogModule:
    return CatalogModule(
        module_id=manifest.module_id,
        app_version_id=f"app-version:{manifest.app_slug}:{manifest.app_version}",
        app_slug=manifest.app_slug,
        app_version=manifest.app_version,
        module_kind=cast("CatalogModuleKind", manifest.module_kind),
        internal_name=manifest.internal_name,
        display_name=manifest.display_name,
        external_id=f"make:{manifest.module_ref}",
        deprecated=False,
        parameters=tuple(
            _catalog_parameter_field(manifest, name)
            for name in manifest.parameter_names
        ),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=manifest.fingerprint,
        fingerprint=manifest.fingerprint,
    )


def _catalog_parameter_field(
    manifest: MakeBuiltinModuleManifest,
    name: str,
) -> CatalogField:
    field_type = _catalog_parameter_field_type(name)
    raw_schema: dict[str, object] = {
        "name": name,
        "required": True,
        "type": field_type,
    }
    fingerprint = _fingerprint(
        {
            "module_id": manifest.module_id,
            "field_name": name,
            "field_type": field_type,
        }
    )
    return CatalogField(
        field_id=f"{manifest.module_id}:parameter:{name}",
        module_id=manifest.module_id,
        direction=cast("CatalogFieldDirection", "parameter"),
        path=(name,),
        label=_catalog_parameter_label(name),
        required=True,
        field_type=field_type,
        advanced=False,
        external_id=name,
        rpc_dependencies=(),
        raw_schema=raw_schema,
        constraints=(),
        fingerprint=fingerprint,
    )


def _catalog_parameter_field_type(name: str) -> str:
    return {
        "array": "array",
        "duration": "uinteger",
        "feeder": "uinteger",
        "name": "text",
        "repeats": "number",
        "reset": "select",
        "scope": "select",
        "start": "number",
        "step": "number",
        "value": "any",
    }.get(name, "text")


def _catalog_parameter_label(name: str) -> str:
    return {
        "array": "Array",
        "duration": "Delay",
        "feeder": "Source module",
        "name": "Variable name",
        "repeats": "Repeats",
        "reset": "Reset a value",
        "scope": "Variable lifetime",
        "start": "Initial value",
        "step": "Step",
        "value": "Variable value",
    }.get(name, name.replace("_", " ").capitalize())


def _snapshot_module_ids(snapshot: CatalogSnapshot) -> frozenset[str]:
    return frozenset(
        module.module_id
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    )


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return tuple(deduped)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
