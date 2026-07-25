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

"""Validation and query helpers for Make catalog snapshots.

Boundary contract:
- Owns: structural catalog validation and exact module lookup.
- Must not: compile raw specs, rank candidates, mutate snapshots, or perform IO.
- Allows: fail-closed checks over typed catalog entities.
- Split when: lookup becomes fuzzy, stateful, or planning-specific.
- Merge when: another validator enforces the same catalog invariants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from languages.make.raw_specs.local_stubs import (
    find_operator_approved_raw_spec_stub,
)

from catalog.identifiers import (
    module_token_match_keys,
    module_token_parts,
    module_version_sort_key,
)
from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    FIELD_DIRECTIONS,
    MODULE_KINDS,
    CatalogApp,
    CatalogAppVersion,
    CatalogConstraint,
    CatalogField,
    CatalogModule,
    CatalogModuleQueryReport,
    CatalogModuleTokenResolution,
    CatalogRawSpecDiagnostic,
    CatalogSnapshot,
)

SHA256_HEX_LENGTH: Final = 64
OPERATOR_APPROVED_STUB_ISSUE: Final = "operator_approved_stub"
OPERATOR_APPROVED_STUB_STRICT_HANDOFF_ISSUE: Final = (
    "operator_approved_stub_strict_handoff_blocked"
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from languages.make.raw_specs.local_stubs import OperatorApprovedRawSpecStub


def validate_catalog_snapshot(snapshot: CatalogSnapshot) -> None:
    """Validate a catalog snapshot and fail closed on structural errors.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    if snapshot.catalog_schema_version != CATALOG_SCHEMA_VERSION:
        message = (
            f"Unsupported catalog schema version:"
            f"{snapshot.catalog_schema_version}"
        )
        raise ValueError(message)
    _require_text(snapshot.generated_at_utc, "generated_at_utc")
    _require_sha256(
        snapshot.raw_spec_manifest_sha256, "raw_spec_manifest_sha256"
    )
    _require_sha256(snapshot.fingerprint, "fingerprint")
    _require_unique("app_id", (app.app_id for app in snapshot.apps))
    for app in snapshot.apps:
        _validate_app(app)
    for diagnostic in snapshot.diagnostics:
        _validate_raw_spec_diagnostic(diagnostic)


def require_catalog_module(
    snapshot: CatalogSnapshot,
    target_module_id: str,
) -> CatalogModuleQueryReport:
    """Return one catalog module or fail loudly when it is not canonical.

    Raises:
        LookupError: If the documented operation cannot be completed.
    """
    for app in snapshot.apps:
        for version in app.versions:
            for module in version.modules:
                if module.module_id == target_module_id:
                    return CatalogModuleQueryReport(module=module)
    message = f"Catalog module does not exist: {target_module_id}"
    raise LookupError(message)


def resolve_module_token(
    snapshot: CatalogSnapshot,
    module_token: str,
    *,
    operator_approved_stubs: tuple[OperatorApprovedRawSpecStub, ...] = (),
    offline_development: bool = False,
) -> CatalogModuleTokenResolution:
    """Resolve one Make `app:module` token from catalog evidence.

    Returns:
        A catalog-backed known or unknown resolution without guessing versions.
    """
    validate_catalog_snapshot(snapshot)
    try:
        app_slug, raw_module_name = module_token_parts(module_token)
    except ValueError:
        return _unknown_token(
            module_token=module_token,
            app_slug=None,
            available_versions=(),
            issue="module_token_shape_invalid",
        )

    app_versions = _catalog_app_versions(snapshot=snapshot, app_slug=app_slug)
    candidates = _candidate_modules_for_token(
        snapshot=snapshot,
        app_slug=app_slug,
        raw_module_name=raw_module_name,
    )
    if len(candidates) == 1:
        return _known_token(
            module_token=module_token,
            module=candidates[0],
            app_versions=app_versions,
        )
    if len(candidates) > 1:
        return _unknown_token(
            module_token=module_token,
            app_slug=app_slug,
            available_versions=app_versions,
            issue="module_token_ambiguous",
        )
    stub = find_operator_approved_raw_spec_stub(
        module_token=module_token,
        stubs=operator_approved_stubs,
    )
    if stub is not None:
        return _operator_approved_stub_token(
            module_token=module_token,
            app_slug=app_slug,
            available_versions=app_versions,
            offline_development=offline_development,
        )
    return _unknown_token(
        module_token=module_token,
        app_slug=app_slug,
        available_versions=app_versions,
        issue="module_token_unknown",
    )


def _operator_approved_stub_token(
    *,
    module_token: str,
    app_slug: str,
    available_versions: tuple[str, ...],
    offline_development: bool,
) -> CatalogModuleTokenResolution:
    """Return an unconfirmed local-stub token resolution."""
    return CatalogModuleTokenResolution(
        module_token=module_token,
        known=False,
        catalog_module_id=None,
        app_slug=app_slug,
        app_version=None,
        module_kind=None,
        internal_name=None,
        raw_spec_sha256=None,
        available_versions=available_versions,
        issue=(
            OPERATOR_APPROVED_STUB_ISSUE
            if offline_development
            else OPERATOR_APPROVED_STUB_STRICT_HANDOFF_ISSUE
        ),
    )


def _validate_app(app: CatalogApp) -> None:
    """Validate one app entity.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    _require_text(app.app_id, "app_id")
    _require_text(app.app_slug, "app_slug")
    _require_text(app.label, "label")
    _require_text(app.external_id, "external_id")
    _require_sha256(app.fingerprint, "app.fingerprint")
    if not app.versions:
        message = f"Catalog app {app.app_id} has no versions."
        raise ValueError(message)
    _require_unique(
        "app_version_id", (version.app_version_id for version in app.versions)
    )
    for version in app.versions:
        _validate_app_version(app, version)


def _catalog_app_versions(
    *, snapshot: CatalogSnapshot, app_slug: str
) -> tuple[str, ...]:
    """Return catalog versions available for one app slug."""
    return tuple(
        sorted(
            {
                version.version
                for app in snapshot.apps
                if app.app_slug.casefold() == app_slug.casefold()
                for version in app.versions
            },
            key=module_version_sort_key,
        )
    )


def _candidate_modules_for_token(
    *,
    snapshot: CatalogSnapshot,
    app_slug: str,
    raw_module_name: str,
) -> tuple[CatalogModule, ...]:
    """Return catalog modules matching a Make app:module token."""
    token_keys = module_token_match_keys(raw_module_name)
    candidates = [
        module
        for app in snapshot.apps
        if app.app_slug.casefold() == app_slug.casefold()
        for version in app.versions
        for module in version.modules
        if token_keys
        & (
            module_token_match_keys(module.internal_name)
            | module_token_match_keys(module.display_name)
        )
    ]
    return tuple(sorted(candidates, key=lambda module: module.module_id))


def _known_token(
    *,
    module_token: str,
    module: CatalogModule,
    app_versions: tuple[str, ...],
) -> CatalogModuleTokenResolution:
    """Return a known catalog token resolution."""
    return CatalogModuleTokenResolution(
        module_token=module_token,
        known=True,
        catalog_module_id=module.module_id,
        app_slug=module.app_slug,
        app_version=module.app_version,
        module_kind=module.module_kind,
        internal_name=module.internal_name,
        raw_spec_sha256=module.raw_spec_sha256,
        available_versions=app_versions,
        issue=None,
    )


def _unknown_token(
    *,
    module_token: str,
    app_slug: str | None,
    available_versions: tuple[str, ...],
    issue: str,
) -> CatalogModuleTokenResolution:
    """Return an unknown catalog token resolution without fabricated version.

    evidence.
    """
    return CatalogModuleTokenResolution(
        module_token=module_token,
        known=False,
        catalog_module_id=None,
        app_slug=app_slug,
        app_version=None,
        module_kind=None,
        internal_name=None,
        raw_spec_sha256=None,
        available_versions=available_versions,
        issue=issue,
    )


def _validate_app_version(app: CatalogApp, version: CatalogAppVersion) -> None:
    """Validate one app version entity.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    _require_text(version.app_version_id, "app_version_id")
    if version.app_id != app.app_id or version.app_slug != app.app_slug:
        message = (
            f"App version {version.app_version_id} is attached to the wrongapp."
        )
        raise ValueError(message)
    _require_text(version.version, "version")
    if version.manifest_version <= 0:
        message = (
            f"App version {version.app_version_id} has an invalid manifest"
            f"version."
        )
        raise ValueError(message)
    _require_sha256(version.raw_spec_sha256, "raw_spec_sha256")
    _require_sha256(version.fingerprint, "app_version.fingerprint")
    if not version.modules:
        message = f"App version {version.app_version_id} has no modules."
        raise ValueError(message)
    _require_unique(
        "module_id", (module.module_id for module in version.modules)
    )
    for module in version.modules:
        _validate_module(version, module)


def _validate_module(version: CatalogAppVersion, module: CatalogModule) -> None:
    """Validate one module entity.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    _require_text(module.module_id, "module_id")
    if module.app_version_id != version.app_version_id:
        message = (
            f"Module {module.module_id} is attached to the wrong app version."
        )
        raise ValueError(message)
    if (
        module.app_slug != version.app_slug
        or module.app_version != version.version
    ):
        message = f"Module {module.module_id} has inconsistent app identity."
        raise ValueError(message)
    if module.module_kind not in MODULE_KINDS:
        message = (
            f"Module {module.module_id} has unsupported kind"
            f"{module.module_kind!r}."
        )
        raise ValueError(message)
    _require_text(module.internal_name, "module.internal_name")
    _require_text(module.display_name, "module.display_name")
    _require_text(module.external_id, "module.external_id")
    _require_sha256(module.raw_spec_sha256, "module.raw_spec_sha256")
    _require_sha256(module.fingerprint, "module.fingerprint")
    _require_unique("field_id", _iter_module_field_ids(module))
    for field in (
        *module.parameters,
        *module.expect_schema,
        *module.interface_schema,
    ):
        _validate_field(module, field)


def _validate_field(module: CatalogModule, field: CatalogField) -> None:
    """Validate one field entity.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    _require_text(field.field_id, "field_id")
    if field.module_id != module.module_id:
        message = f"Field {field.field_id} is attached to the wrong module."
        raise ValueError(message)
    if field.direction not in FIELD_DIRECTIONS:
        message = (
            f"Field {field.field_id} has unsupported direction"
            f"{field.direction!r}."
        )
        raise ValueError(message)
    if not field.path:
        message = f"Field {field.field_id} must have a stable path."
        raise ValueError(message)
    for part in field.path:
        _require_text(part, "field.path")
    _require_text(field.label, "field.label")
    _require_optional_bool(field.advanced, "field.advanced")
    _require_text(field.external_id, "field.external_id")
    _require_sha256(field.fingerprint, "field.fingerprint")
    _require_unique(
        "constraint_id", (item.constraint_id for item in field.constraints)
    )
    for constraint in field.constraints:
        _validate_constraint(field, constraint)


def _validate_constraint(
    field: CatalogField, constraint: CatalogConstraint
) -> None:
    """Validate one field constraint entity.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    _require_text(constraint.constraint_id, "constraint_id")
    if constraint.field_id != field.field_id:
        message = (
            f"Constraint {constraint.constraint_id} is attached to the wrong"
            f"field."
        )
        raise ValueError(message)
    _require_text(constraint.key, "constraint.key")
    if not constraint.value:
        message = (
            f"Constraint {constraint.constraint_id} must carry a value payload."
        )
        raise ValueError(message)
    _require_sha256(constraint.fingerprint, "constraint.fingerprint")


def _validate_raw_spec_diagnostic(diagnostic: CatalogRawSpecDiagnostic) -> None:
    """Validate one raw-spec ingestion diagnostic.

    Raises:
        TypeError: If a value has an invalid type.
        ValueError: If a value violates the expected contract.
    """
    _require_text(diagnostic.code, "diagnostic.code")
    if diagnostic.severity not in {"warning", "error"}:
        message = (
            f"Raw-spec diagnostic has unsupported severity"
            f"{diagnostic.severity!r}."
        )
        raise ValueError(message)
    _require_text(diagnostic.module_id, "diagnostic.module_id")
    _require_text(diagnostic.app_slug, "diagnostic.app_slug")
    _require_text(diagnostic.app_version, "diagnostic.app_version")
    if diagnostic.module_kind not in MODULE_KINDS:
        message = (
            f"Raw-spec diagnostic has unsupported module kind"
            f"{diagnostic.module_kind!r}."
        )
        raise ValueError(message)
    _require_text(diagnostic.internal_name, "diagnostic.internal_name")
    _require_text(diagnostic.source_ref, "diagnostic.source_ref")
    _require_text(diagnostic.message, "diagnostic.message")
    for part in diagnostic.field_path:
        _require_text(part, "diagnostic.field_path")
    for part in diagnostic.collection_path:
        if isinstance(part, bool):
            message = (
                "Raw-spec diagnostic collection_path must contain strings and"
                "integers."
            )
            raise TypeError(message)


def _iter_module_field_ids(module: CatalogModule) -> tuple[str, ...]:
    """Return all field IDs for one module."""
    return tuple(
        field.field_id
        for field in (
            *module.parameters,
            *module.expect_schema,
            *module.interface_schema,
        )
    )


def _require_unique(label: str, values: Iterable[object]) -> None:
    """Fail unless all values are unique.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    strings = tuple(str(value) for value in values)
    duplicate_count = len(strings) - len(set(strings))
    if duplicate_count:
        message = f"Catalog contains duplicate {label} values."
        raise ValueError(message)


def _require_text(value: str, label: str) -> None:
    """Fail unless a string is non-empty.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    if not value.strip():
        message = f"Catalog member {label!r} must be non-empty text."
        raise ValueError(message)


def _require_optional_bool(value: object, label: str) -> None:
    """Fail unless a value is a boolean or explicit null.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is not None and not isinstance(value, bool):
        message = f"Catalog member {label!r} must be a boolean or null."
        raise TypeError(message)


def _require_sha256(value: str, label: str) -> None:
    """Fail unless a string looks like a SHA-256 digest.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    if len(value) != SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        message = f"Catalog member {label!r} must be a SHA-256 hex digest."
        raise ValueError(message)
