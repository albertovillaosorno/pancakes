# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.schema-policy
# - 001043#repo.make-catalog.drift-revalidation-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog drift detection and fixture revalidation command boundary.

Boundary contract:
- Owns: snapshot drift comparison and dependent target revalidation reports.
- Must not: compile raw specs, scrape data, repair blueprints, or perform IO.
- Allows: fail-closed fallback reasons derived from typed catalog snapshots.
- Split when: drift handling mutates fixtures or calls external refresh tools.
- Merge when: another drift module reports the same catalog change classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from catalog.models import (
    CatalogDriftReport,
    CatalogEntityChange,
    CatalogModule,
    CatalogRevalidationIssue,
    CatalogRevalidationReport,
    CatalogRevalidationTarget,
    CatalogSnapshot,
    JsonObject,
)
from catalog.validation import validate_catalog_snapshot

if TYPE_CHECKING:
    from collections.abc import Mapping

NO_FALLBACK_REASON: Final = "none"
BASELINE_REASON: Final = "baseline_without_previous_snapshot"
RAW_SPECS_UNAVAILABLE_REASON: Final = "raw_specs_unavailable"
CATALOG_DRIFT_REASON: Final = "catalog_drift"
VALIDATION_FAILED_REASON: Final = "validation_failed"
STATUS_VALID: Final = "valid"
STATUS_FAIL: Final = "fail"
STATUS_FALLBACK: Final = "fallback_required"


def detect_catalog_drift(
    *,
    previous_snapshot: CatalogSnapshot | None,
    current_snapshot: CatalogSnapshot,
) -> CatalogDriftReport:
    """Return deterministic module and parameter drift between two snapshots."""
    validate_catalog_snapshot(current_snapshot)
    if previous_snapshot is None:
        return CatalogDriftReport(
            previous_snapshot_fingerprint=None,
            current_snapshot_fingerprint=current_snapshot.fingerprint,
            added_modules=(),
            removed_modules=(),
            changed_modules=(),
            added_parameters=(),
            removed_parameters=(),
            changed_parameters=(),
            baseline=True,
        )

    validate_catalog_snapshot(previous_snapshot)
    previous_modules = _module_map(previous_snapshot)
    current_modules = _module_map(current_snapshot)
    previous_parameters = _parameter_map(previous_snapshot)
    current_parameters = _parameter_map(current_snapshot)
    return CatalogDriftReport(
        previous_snapshot_fingerprint=previous_snapshot.fingerprint,
        current_snapshot_fingerprint=current_snapshot.fingerprint,
        added_modules=_added_ids(previous_modules, current_modules),
        removed_modules=_removed_ids(previous_modules, current_modules),
        changed_modules=_changed_entities(previous_modules, current_modules),
        added_parameters=_added_ids(previous_parameters, current_parameters),
        removed_parameters=_removed_ids(
            previous_parameters, current_parameters
        ),
        changed_parameters=_changed_entities(
            previous_parameters, current_parameters
        ),
        baseline=False,
    )


def revalidate_catalog_targets(
    *,
    current_snapshot: CatalogSnapshot,
    previous_snapshot: CatalogSnapshot | None,
    targets: tuple[CatalogRevalidationTarget, ...],
    raw_specs_available: bool = True,
) -> CatalogRevalidationReport:
    """Revalidate dependent fixture targets against current catalog truth.

    Returns:
        The result produced by revalidate dependent fixture targets against
        current catalog truth.
    """
    drift_report = detect_catalog_drift(
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    )
    modules = _module_map(current_snapshot)
    issues = _collect_revalidation_issues(targets=targets, modules=modules)
    fallback_reason = _fallback_reason(
        raw_specs_available=raw_specs_available,
        has_drift=drift_report.has_drift,
        has_issues=bool(issues),
        baseline=drift_report.baseline,
    )
    return CatalogRevalidationReport(
        current_snapshot_fingerprint=current_snapshot.fingerprint,
        previous_snapshot_fingerprint=drift_report.previous_snapshot_fingerprint,
        raw_specs_available=raw_specs_available,
        drift_report=drift_report,
        issues=issues,
        status=_status_for_report(
            fallback_reason=fallback_reason, has_issues=bool(issues)
        ),
        fallback_required=fallback_reason != NO_FALLBACK_REASON,
        fallback_reason=fallback_reason,
    )


def drift_report_to_json(report: CatalogDriftReport) -> JsonObject:
    """Return a deterministic JSON payload for a drift report."""
    return {
        "previous_snapshot_fingerprint": report.previous_snapshot_fingerprint,
        "current_snapshot_fingerprint": report.current_snapshot_fingerprint,
        "baseline": report.baseline,
        "has_drift": report.has_drift,
        "added_modules": list(report.added_modules),
        "removed_modules": list(report.removed_modules),
        "changed_modules": [
            _change_to_json(change) for change in report.changed_modules
        ],
        "added_parameters": list(report.added_parameters),
        "removed_parameters": list(report.removed_parameters),
        "changed_parameters": [
            _change_to_json(change) for change in report.changed_parameters
        ],
    }


def revalidation_report_to_json(
    report: CatalogRevalidationReport,
) -> JsonObject:
    """Return a deterministic JSON payload for a revalidation report."""
    return {
        "current_snapshot_fingerprint": report.current_snapshot_fingerprint,
        "previous_snapshot_fingerprint": report.previous_snapshot_fingerprint,
        "raw_specs_available": report.raw_specs_available,
        "status": report.status,
        "fallback_required": report.fallback_required,
        "fallback_reason": report.fallback_reason,
        "drift_report": drift_report_to_json(report.drift_report),
        "issues": [_issue_to_json(issue) for issue in report.issues],
    }


def _collect_revalidation_issues(
    *,
    targets: tuple[CatalogRevalidationTarget, ...],
    modules: dict[str, CatalogModule],
) -> tuple[CatalogRevalidationIssue, ...]:
    """Return sorted revalidation issues for fixture targets."""
    issues: list[CatalogRevalidationIssue] = []
    for target in sorted(targets, key=lambda item: item.target_id):
        module = modules.get(target.module_id)
        if module is None:
            issues.append(
                CatalogRevalidationIssue(
                    issue_type="unknown_module",
                    target_id=target.target_id,
                    module_id=target.module_id,
                    detail=(
                        "Target module is not present in the current catalog."
                    ),
                )
            )
            continue
        issues.extend(_stale_module_issues(target, module))
        issues.extend(_missing_parameter_issues(target, module))
    return tuple(sorted(issues, key=_issue_sort_key))


def _stale_module_issues(
    target: CatalogRevalidationTarget,
    module: CatalogModule,
) -> tuple[CatalogRevalidationIssue, ...]:
    """Return stale module issues for one target."""
    if target.expected_module_fingerprint is None:
        return ()
    if target.expected_module_fingerprint == module.fingerprint:
        return ()
    return (
        CatalogRevalidationIssue(
            issue_type="stale_module",
            target_id=target.target_id,
            module_id=target.module_id,
            detail=(
                "Target module fingerprint differs from the current catalog."
            ),
        ),
    )


def _missing_parameter_issues(
    target: CatalogRevalidationTarget,
    module: CatalogModule,
) -> tuple[CatalogRevalidationIssue, ...]:
    """Return missing required parameter issues for one target."""
    current_parameter_ids = {field.field_id for field in module.parameters}
    missing_parameter_ids = sorted(
        set(target.required_parameter_ids).difference(current_parameter_ids)
    )
    return tuple(
        CatalogRevalidationIssue(
            issue_type="missing_parameter",
            target_id=target.target_id,
            module_id=target.module_id,
            detail=parameter_id,
        )
        for parameter_id in missing_parameter_ids
    )


def _fallback_reason(
    *,
    raw_specs_available: bool,
    has_drift: bool,
    has_issues: bool,
    baseline: bool,
) -> str:
    """Return the deterministic fallback reason for a report."""
    if has_issues:
        return VALIDATION_FAILED_REASON
    if not raw_specs_available:
        return RAW_SPECS_UNAVAILABLE_REASON
    if has_drift:
        return CATALOG_DRIFT_REASON
    if baseline:
        return BASELINE_REASON
    return NO_FALLBACK_REASON


def _status_for_report(*, fallback_reason: str, has_issues: bool) -> str:
    """Return the report status from fallback and issue state."""
    if has_issues:
        return STATUS_FAIL
    if fallback_reason != NO_FALLBACK_REASON:
        return STATUS_FALLBACK
    return STATUS_VALID


def _module_map(snapshot: CatalogSnapshot) -> dict[str, CatalogModule]:
    """Return modules keyed by module ID."""
    return {
        module.module_id: module
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    }


def _parameter_map(snapshot: CatalogSnapshot) -> dict[str, str]:
    """Return parameter fingerprints keyed by field ID."""
    return {
        field.field_id: field.fingerprint
        for module in _module_map(snapshot).values()
        for field in module.parameters
    }


def _added_ids(
    previous_items: Mapping[str, object],
    current_items: Mapping[str, object],
) -> tuple[str, ...]:
    """Return IDs added in the current item map."""
    return tuple(sorted(set(current_items).difference(previous_items)))


def _removed_ids(
    previous_items: Mapping[str, object],
    current_items: Mapping[str, object],
) -> tuple[str, ...]:
    """Return IDs removed from the current item map."""
    return tuple(sorted(set(previous_items).difference(current_items)))


def _changed_entities(
    previous_items: Mapping[str, object],
    current_items: Mapping[str, object],
) -> tuple[CatalogEntityChange, ...]:
    """Return entities whose fingerprints changed under a stable ID."""
    changes: list[CatalogEntityChange] = []
    for entity_id in sorted(set(previous_items).intersection(current_items)):
        previous_fingerprint = _fingerprint(previous_items[entity_id])
        current_fingerprint = _fingerprint(current_items[entity_id])
        if previous_fingerprint == current_fingerprint:
            continue
        changes.append(
            CatalogEntityChange(
                entity_id=entity_id,
                previous_fingerprint=previous_fingerprint,
                current_fingerprint=current_fingerprint,
            )
        )
    return tuple(changes)


def _fingerprint(value: object) -> str:
    """Return a fingerprint from a catalog entity or raw fingerprint string.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    if isinstance(value, str):
        return value
    fingerprint = getattr(value, "fingerprint", None)
    if not isinstance(fingerprint, str):
        message = f"Catalog entity has no fingerprint: {value!r}"
        raise TypeError(message)
    return fingerprint


def _change_to_json(change: CatalogEntityChange) -> JsonObject:
    """Return JSON for one entity change."""
    return {
        "entity_id": change.entity_id,
        "previous_fingerprint": change.previous_fingerprint,
        "current_fingerprint": change.current_fingerprint,
    }


def _issue_to_json(issue: CatalogRevalidationIssue) -> JsonObject:
    """Return JSON for one revalidation issue."""
    return {
        "issue_type": issue.issue_type,
        "target_id": issue.target_id,
        "module_id": issue.module_id,
        "detail": issue.detail,
    }


def _issue_sort_key(
    issue: CatalogRevalidationIssue,
) -> tuple[str, str, str, str]:
    """Return the deterministic sort key for a revalidation issue."""
    return issue.target_id, issue.issue_type, issue.module_id, issue.detail
