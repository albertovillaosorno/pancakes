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

"""Typed Make catalog entity schema.

Boundary contract:
- Owns: immutable catalog entity typed records and catalog type aliases.
- Must not: parse raw specs, serialize JSON, perform IO, or validate flows.
- Allows: lightweight computed properties derived from model fields.
- Split when: behavior mutates, queries, serializes, or validates catalog data.
- Merge when: another module defines the same canonical catalog entity type.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

CATALOG_SCHEMA_VERSION: Final = 1

type JsonScalar = str | int | float | bool | None
type JsonValue = object
type JsonObject = dict[str, object]
type JsonArray = list[object]
type CatalogModuleKind = Literal[
    "action",
    "search",
    "trigger",
    "router",
    "transformer",
    "aggregator",
    "agent",
    "custom",
    "unknown",
]
type CatalogFieldDirection = Literal["parameter", "expect", "interface"]
type CatalogRawSpecDiagnosticCode = Literal[
    "raw_spec.field_collection_shape_invalid",
    "raw_spec.field_duplicate",
    "raw_spec.field_item_shape_invalid",
    "raw_spec.module_collection_empty",
    "raw_spec.module_duplicate",
    "raw_spec.nested_field_collection_shape_invalid",
    "raw_spec.nested_field_item_shape_invalid",
    "raw_spec.field_name_missing",
]
type CatalogRawSpecDiagnosticSeverity = Literal["warning", "error"]

MODULE_KINDS: Final[frozenset[str]] = frozenset(
    (
        "action",
        "search",
        "trigger",
        "router",
        "transformer",
        "aggregator",
        "agent",
        "custom",
        "unknown",
    )
)
FIELD_DIRECTIONS: Final[frozenset[str]] = frozenset(
    ("parameter", "expect", "interface")
)


class CatalogConstraint(NamedTuple):
    """One normalized rule attached to a catalog field."""

    constraint_id: str
    field_id: str
    key: str
    value: JsonObject
    fingerprint: str


class CatalogField(NamedTuple):
    """One addressable field surface on a Make module."""

    field_id: str
    module_id: str
    direction: CatalogFieldDirection
    path: tuple[str, ...]
    label: str
    required: bool
    field_type: str | None
    advanced: bool | None
    external_id: str
    rpc_dependencies: tuple[str, ...]
    raw_schema: JsonObject
    constraints: tuple[CatalogConstraint, ...]
    fingerprint: str


class CatalogModule(NamedTuple):
    """One version-scoped Make module capability."""

    module_id: str
    app_version_id: str
    app_slug: str
    app_version: str
    module_kind: CatalogModuleKind
    internal_name: str
    display_name: str
    external_id: str
    deprecated: bool
    parameters: tuple[CatalogField, ...]
    expect_schema: tuple[CatalogField, ...]
    interface_schema: tuple[CatalogField, ...]
    rpc_dependencies: tuple[str, ...]
    raw_spec_sha256: str
    fingerprint: str


class CatalogAppVersion(NamedTuple):
    """One versioned Make app surface."""

    app_version_id: str
    app_id: str
    app_slug: str
    version: str
    latest: bool
    manifest_version: int
    modules: tuple[CatalogModule, ...]
    raw_spec_sha256: str
    fingerprint: str


class CatalogApp(NamedTuple):
    """One durable Make app identity."""

    app_id: str
    app_slug: str
    label: str
    external_id: str
    deprecated: bool
    versions: tuple[CatalogAppVersion, ...]
    fingerprint: str


class CatalogRawSpecDiagnostic(NamedTuple):
    """One structured diagnostic emitted for raw-spec field metadata."""

    code: CatalogRawSpecDiagnosticCode
    severity: CatalogRawSpecDiagnosticSeverity
    module_id: str
    app_slug: str
    app_version: str
    module_kind: CatalogModuleKind
    internal_name: str
    field_path: tuple[str, ...]
    collection_path: tuple[str | int, ...]
    source_ref: str
    message: str


class CatalogSnapshot(NamedTuple):
    """One deterministic Make catalog materialization."""

    catalog_schema_version: int
    generated_at_utc: str
    raw_spec_manifest_sha256: str
    apps: tuple[CatalogApp, ...]
    fingerprint: str
    diagnostics: tuple[CatalogRawSpecDiagnostic, ...] = ()


class CatalogModuleQueryReport(NamedTuple):
    """Result for one catalog module lookup."""

    module: CatalogModule


class CatalogModuleTokenResolution(NamedTuple):
    """Catalog-backed resolution evidence for one Make module token."""

    module_token: str
    known: bool
    catalog_module_id: str | None
    app_slug: str | None
    app_version: str | None
    module_kind: CatalogModuleKind | None
    internal_name: str | None
    raw_spec_sha256: str | None
    available_versions: tuple[str, ...]
    issue: str | None


class CatalogEntityChange(NamedTuple):
    """Fingerprint change for one stable catalog entity."""

    entity_id: str
    previous_fingerprint: str
    current_fingerprint: str


class CatalogDriftReport(NamedTuple):
    """Deterministic module and parameter drift between catalog snapshots."""

    previous_snapshot_fingerprint: str | None
    current_snapshot_fingerprint: str
    added_modules: tuple[str, ...]
    removed_modules: tuple[str, ...]
    changed_modules: tuple[CatalogEntityChange, ...]
    added_parameters: tuple[str, ...]
    removed_parameters: tuple[str, ...]
    changed_parameters: tuple[CatalogEntityChange, ...]
    baseline: bool

    @property
    def has_drift(self) -> bool:
        """Return whether this report contains any entity drift."""
        return any(
            (
                self.added_modules,
                self.removed_modules,
                self.changed_modules,
                self.added_parameters,
                self.removed_parameters,
                self.changed_parameters,
            )
        )


class CatalogRevalidationTarget(NamedTuple):
    """One dependent fixture or blueprint target to revalidate."""

    target_id: str
    module_id: str
    expected_module_fingerprint: str | None = None
    required_parameter_ids: tuple[str, ...] = ()


class CatalogRevalidationIssue(NamedTuple):
    """One deterministic revalidation issue."""

    issue_type: str
    target_id: str
    module_id: str
    detail: str


class CatalogRevalidationReport(NamedTuple):
    """Revalidation result for dependent fixtures or blueprints."""

    current_snapshot_fingerprint: str
    previous_snapshot_fingerprint: str | None
    raw_specs_available: bool
    drift_report: CatalogDriftReport
    issues: tuple[CatalogRevalidationIssue, ...]
    status: str
    fallback_required: bool
    fallback_reason: str
