# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001045#repo.make-ast.module-resolution.family-lineage
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog module lineage summaries.

Boundary contract:
- Owns: deterministic lineage groups across catalog module versions.
- Must not: detect drift, validate snapshots, query candidates, or perform IO.
- Allows: normalized keys and latest-version grouping from typed catalog data.
- Split when: lineage needs graph state, fuzzy matching, or mutation policy.
- Merge when: another lineage module groups the same catalog module families.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from catalog.identifiers import (
    module_token_parts,
    module_token_resolution_key,
    module_version_sort_key,
)

if TYPE_CHECKING:
    from languages.make.raw_specs.local_stubs import OperatorApprovedRawSpecStub

    from catalog.models import CatalogModule, CatalogSnapshot

type CatalogModuleEntry = tuple[CatalogModule, bool]


class CatalogModuleLineage(NamedTuple):
    """One normalized module lineage across catalog versions."""

    lineage_id: str
    app_slug: str
    module_kind: str
    module_key: str
    module_ids: tuple[str, ...]
    versions: tuple[str, ...]
    deprecated_module_ids: tuple[str, ...]
    latest_module_ids: tuple[str, ...]


class CatalogLineageReport(NamedTuple):
    """Catalog lineage report for a snapshot."""

    catalog_fingerprint: str
    lineages: tuple[CatalogModuleLineage, ...]


class OperatorApprovedRawSpecStubLineage(NamedTuple):
    """One provenance lineage row for an operator-approved local stub."""

    module_token: str
    app_slug: str
    module_key: str
    source: str
    approval_timestamp: str
    operator_note: str
    unsupported_fields: tuple[str, ...]
    evidence_status: str


class OperatorApprovedRawSpecStubLineageReport(NamedTuple):
    """Deterministic provenance report for local raw-spec stubs."""

    stubs: tuple[OperatorApprovedRawSpecStubLineage, ...]


def build_catalog_lineage_report(
    snapshot: CatalogSnapshot,
) -> CatalogLineageReport:
    """Return deterministic module lineage groups for one catalog snapshot."""
    grouped: dict[str, list[CatalogModuleEntry]] = {}
    for module, latest in _catalog_module_entries(snapshot):
        grouped.setdefault(_lineage_id(module), []).append((module, latest))
    lineages = tuple(
        _lineage(
            lineage_id,
            tuple(sorted(entries, key=lambda item: item[0].module_id)),
        )
        for lineage_id, entries in sorted(grouped.items())
    )
    return CatalogLineageReport(
        catalog_fingerprint=snapshot.fingerprint,
        lineages=lineages,
    )


def build_operator_approved_stub_lineage(
    stubs: tuple[OperatorApprovedRawSpecStub, ...],
) -> OperatorApprovedRawSpecStubLineageReport:
    """Return provenance lineage for operator-approved local raw-spec stubs."""
    return OperatorApprovedRawSpecStubLineageReport(
        stubs=tuple(
            sorted(
                (_stub_lineage(stub) for stub in stubs),
                key=lambda lineage: lineage.module_token.casefold(),
            )
        )
    )


def _lineage(
    lineage_id: str, entries: tuple[CatalogModuleEntry, ...]
) -> CatalogModuleLineage:
    """Return one lineage summary."""
    modules = tuple(module for module, _latest in entries)
    first = modules[0]
    latest_module_ids = tuple(
        module.module_id for module, latest in entries if latest
    )
    return CatalogModuleLineage(
        lineage_id=lineage_id,
        app_slug=first.app_slug,
        module_kind=first.module_kind,
        module_key=_module_key(first),
        module_ids=tuple(module.module_id for module in modules),
        versions=tuple(
            sorted(
                {module.app_version for module in modules},
                key=module_version_sort_key,
            )
        ),
        deprecated_module_ids=tuple(
            module.module_id for module in modules if module.deprecated
        ),
        latest_module_ids=latest_module_ids,
    )


def _stub_lineage(
    stub: OperatorApprovedRawSpecStub,
) -> OperatorApprovedRawSpecStubLineage:
    """Return one local stub lineage row."""
    app_slug, internal_name = module_token_parts(stub.module_token)
    return OperatorApprovedRawSpecStubLineage(
        module_token=stub.module_token,
        app_slug=app_slug,
        module_key=module_token_resolution_key(internal_name),
        source=stub.source,
        approval_timestamp=stub.approval_timestamp,
        operator_note=stub.operator_note,
        unsupported_fields=stub.unsupported_fields,
        evidence_status="operator_approved_stub",
    )


def _catalog_module_entries(
    snapshot: CatalogSnapshot,
) -> tuple[CatalogModuleEntry, ...]:
    """Return all catalog modules with latest-version flags."""
    return tuple(
        (module, version.latest)
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    )


def _lineage_id(module: CatalogModule) -> str:
    """Return a stable lineage identifier."""
    return f"{module.app_slug}:{module.module_kind}:{_module_key(module)}"


def _module_key(module: CatalogModule) -> str:
    """Return a normalized module key across versions."""
    return _normalize_key(
        module.internal_name or module.display_name or module.external_id
    )


def _normalize_key(value: str) -> str:
    """Return a loose alphanumeric key."""
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )
