# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001061#repo.delivery.claims.exact-dynamic-surface-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Offline catalog quality audit sampling gate.

Boundary contract:
- Owns: deterministic catalog-quality audit sampling reports and follow-up
records.
- Must not: author catalog answers, call providers, read live Make.com, or
mutate storage.
- Allows: typed sample coverage checks, pass/fail class counts, and
backlog-style records.
- Split when: persisted audit storage or interactive review tooling owns this
workflow.
- Merge when: generation audit owns the same catalog-strength readiness gate.
"""

from __future__ import annotations

import hashlib
from typing import Final, Literal, NamedTuple

type CatalogQualitySampleStratum = Literal[
    "built_in",
    "control_surface",
    "make_ai",
    "popular_app",
    "heavy_spec",
    "random_app",
    "graph_edge",
    "field_schema",
]
type CatalogQualityFindingClass = Literal[
    "semantic_usefulness",
    "graph_usefulness",
    "field_coverage",
    "evidence_gap",
    "ranking",
]
type CatalogQualityCheckStatus = Literal["pass", "fail"]
type CatalogQualityAuditStatus = Literal["ready", "needs_follow_up", "blocked"]
type CatalogQualityFollowUpStatus = Literal["open"]
type CatalogQualitySeverity = Literal["error"]

CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE: Final = 100
CATALOG_QUALITY_REQUIRED_STRATA: Final[frozenset[str]] = frozenset(
    (
        "built_in",
        "control_surface",
        "make_ai",
        "popular_app",
        "heavy_spec",
        "random_app",
        "graph_edge",
        "field_schema",
    )
)
CATALOG_QUALITY_FINDING_CLASSES: Final[frozenset[str]] = frozenset(
    (
        "semantic_usefulness",
        "graph_usefulness",
        "field_coverage",
        "evidence_gap",
        "ranking",
    )
)


class CatalogQualityAuditUnit(NamedTuple):
    """One representative catalog-quality audit unit."""

    unit_id: str
    stratum: CatalogQualitySampleStratum
    module_id: str
    app_slug: str
    semantic_usefulness: CatalogQualityCheckStatus
    graph_usefulness: CatalogQualityCheckStatus
    field_coverage: CatalogQualityCheckStatus
    evidence_gap: CatalogQualityCheckStatus
    ranking: CatalogQualityCheckStatus
    evidence_refs: tuple[str, ...]
    reviewer_note: str


class CatalogQualityAuditBlocker(NamedTuple):
    """One hard blocker before catalog quality can be treated as strong.

    authority.
    """

    code: str
    severity: CatalogQualitySeverity
    message: str
    required_action: str


class CatalogQualityFollowUpRecord(NamedTuple):
    """One typed follow-up record for a systemic catalog-quality defect."""

    record_id: str
    status: CatalogQualityFollowUpStatus
    severity: CatalogQualitySeverity
    unit_id: str
    stratum: CatalogQualitySampleStratum
    module_id: str
    app_slug: str
    finding_class: CatalogQualityFindingClass
    summary: str
    recommended_action: str
    evidence_refs: tuple[str, ...]


class CatalogQualityAuditReport(NamedTuple):
    """Read-only report for the catalog quality sampling gate."""

    status: CatalogQualityAuditStatus
    requested_sample_size: int
    minimum_sample_size: int
    audited_unit_count: int
    required_strata: tuple[CatalogQualitySampleStratum, ...]
    covered_strata: tuple[CatalogQualitySampleStratum, ...]
    missing_strata: tuple[CatalogQualitySampleStratum, ...]
    sample_counts_by_stratum: tuple[
        tuple[CatalogQualitySampleStratum, int], ...
    ]
    pass_counts_by_class: tuple[tuple[CatalogQualityFindingClass, int], ...]
    fail_counts_by_class: tuple[tuple[CatalogQualityFindingClass, int], ...]
    follow_up_records: tuple[CatalogQualityFollowUpRecord, ...]
    blockers: tuple[CatalogQualityAuditBlocker, ...]
    catalog_answers_authored: bool
    live_provider_called: bool
    external_model_called: bool


def build_catalog_quality_audit_report(
    *,
    audit_units: tuple[CatalogQualityAuditUnit, ...],
    requested_sample_size: int = CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE,
) -> CatalogQualityAuditReport:
    """Return a deterministic catalog-strength readiness audit report."""
    _require_requested_sample_size(requested_sample_size)
    ordered_units = tuple(
        sorted(audit_units, key=lambda unit: unit.unit_id.casefold())
    )
    blockers = _audit_blockers(
        audit_units=ordered_units,
        requested_sample_size=requested_sample_size,
    )
    follow_ups = _follow_up_records(ordered_units)
    return CatalogQualityAuditReport(
        status=_audit_status(blockers=blockers, follow_up_records=follow_ups),
        requested_sample_size=requested_sample_size,
        minimum_sample_size=CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE,
        audited_unit_count=len(ordered_units),
        required_strata=_required_strata(),
        covered_strata=_covered_strata(ordered_units),
        missing_strata=_missing_strata(ordered_units),
        sample_counts_by_stratum=_sample_counts_by_stratum(ordered_units),
        pass_counts_by_class=_class_counts(ordered_units, status="pass"),
        fail_counts_by_class=_class_counts(ordered_units, status="fail"),
        follow_up_records=follow_ups,
        blockers=blockers,
        catalog_answers_authored=False,
        live_provider_called=False,
        external_model_called=False,
    )


def _require_requested_sample_size(requested_sample_size: int) -> None:
    if requested_sample_size < CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE:
        message = (
            "Catalog quality audit sample size cannot be below "
            f"{CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE}."
        )
        raise ValueError(message)


def _audit_blockers(
    *,
    audit_units: tuple[CatalogQualityAuditUnit, ...],
    requested_sample_size: int,
) -> tuple[CatalogQualityAuditBlocker, ...]:
    blockers: list[CatalogQualityAuditBlocker] = []
    if len(audit_units) < requested_sample_size:
        blockers.append(
            CatalogQualityAuditBlocker(
                code="catalog_quality.sample_size_below_gate",
                severity="error",
                message=(
                    "Catalog quality audit has fewer than the required sample"
                    "units."
                ),
                required_action=(
                    "Audit at least 100 representative catalog units."
                ),
            )
        )
    blockers.extend(
        CatalogQualityAuditBlocker(
            code="catalog_quality.sample_stratum_missing",
            severity="error",
            message=f"Catalog quality audit is missing stratum {stratum}.",
            required_action=(
                "Add representative units for every required audit stratum."
            ),
        )
        for stratum in _missing_strata(audit_units)
    )
    duplicate_unit_ids = _duplicate_unit_ids(audit_units)
    blockers.extend(
        CatalogQualityAuditBlocker(
            code="catalog_quality.duplicate_unit",
            severity="error",
            message=(
                f"Catalog quality audit unit {unit_id} appears more than once."
            ),
            required_action=(
                "Deduplicate audit units before treating the catalog as strong."
            ),
        )
        for unit_id in duplicate_unit_ids
    )
    return tuple(blockers)


def _follow_up_records(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
) -> tuple[CatalogQualityFollowUpRecord, ...]:
    follow_ups: list[CatalogQualityFollowUpRecord] = []
    for unit in audit_units:
        _require_audit_unit(unit)
        for finding_class, status in _unit_class_statuses(unit):
            if status == "pass":
                continue
            follow_ups.append(
                _follow_up_record(unit=unit, finding_class=finding_class)
            )
    return tuple(follow_ups)


def _follow_up_record(
    *,
    unit: CatalogQualityAuditUnit,
    finding_class: CatalogQualityFindingClass,
) -> CatalogQualityFollowUpRecord:
    return CatalogQualityFollowUpRecord(
        record_id=_follow_up_id(unit=unit, finding_class=finding_class),
        status="open",
        severity="error",
        unit_id=unit.unit_id,
        stratum=unit.stratum,
        module_id=unit.module_id,
        app_slug=unit.app_slug,
        finding_class=finding_class,
        summary=f"{unit.unit_id} failed catalog quality class {finding_class}.",
        recommended_action=_recommended_action(finding_class),
        evidence_refs=unit.evidence_refs,
    )


def _recommended_action(finding_class: CatalogQualityFindingClass) -> str:
    actions: dict[CatalogQualityFindingClass, str] = {
        "semantic_usefulness": (
            "Review semantic guidance before generation use."
        ),
        "graph_usefulness": (
            "Repair graph nodes or edges before graph-backed generation."
        ),
        "field_coverage": "Fill or quarantine missing field-schema coverage.",
        "evidence_gap": (
            "Attach stronger source evidence or downgrade authority."
        ),
        "ranking": (
            "Repair retrieval ranking or source precedence before promotion."
        ),
    }
    return actions[finding_class]


def _follow_up_id(
    *,
    unit: CatalogQualityAuditUnit,
    finding_class: CatalogQualityFindingClass,
) -> str:
    evidence_refs = ",".join(unit.evidence_refs)
    payload = (
        f"{unit.unit_id}\n{unit.module_id}\n{finding_class}\n{evidence_refs}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"catalog-quality:{finding_class}:{digest}"


def _audit_status(
    *,
    blockers: tuple[CatalogQualityAuditBlocker, ...],
    follow_up_records: tuple[CatalogQualityFollowUpRecord, ...],
) -> CatalogQualityAuditStatus:
    if blockers:
        return "blocked"
    if follow_up_records:
        return "needs_follow_up"
    return "ready"


def _sample_counts_by_stratum(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
) -> tuple[tuple[CatalogQualitySampleStratum, int], ...]:
    return tuple(
        (stratum, sum(1 for unit in audit_units if unit.stratum == stratum))
        for stratum in _required_strata()
    )


def _class_counts(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
    *,
    status: CatalogQualityCheckStatus,
) -> tuple[tuple[CatalogQualityFindingClass, int], ...]:
    return tuple(
        (
            finding_class,
            sum(
                1
                for unit in audit_units
                for unit_class, unit_status in _unit_class_statuses(unit)
                if unit_class == finding_class and unit_status == status
            ),
        )
        for finding_class in _finding_classes()
    )


def _unit_class_statuses(
    unit: CatalogQualityAuditUnit,
) -> tuple[tuple[CatalogQualityFindingClass, CatalogQualityCheckStatus], ...]:
    return (
        ("semantic_usefulness", unit.semantic_usefulness),
        ("graph_usefulness", unit.graph_usefulness),
        ("field_coverage", unit.field_coverage),
        ("evidence_gap", unit.evidence_gap),
        ("ranking", unit.ranking),
    )


def _require_audit_unit(unit: CatalogQualityAuditUnit) -> None:
    if unit.stratum not in CATALOG_QUALITY_REQUIRED_STRATA:
        message = f"Unsupported catalog quality audit stratum: {unit.stratum}"
        raise ValueError(message)
    if (
        not unit.unit_id.strip()
        or not unit.module_id.strip()
        or not unit.app_slug.strip()
    ):
        message = (
            "Catalog quality audit units require stable unit, module, and app"
            "IDs."
        )
        raise ValueError(message)
    if not unit.evidence_refs:
        message = (
            "Catalog quality audit units require at least one evidence"
            "reference."
        )
        raise ValueError(message)
    for finding_class, status in _unit_class_statuses(unit):
        if finding_class not in CATALOG_QUALITY_FINDING_CLASSES:
            message = (
                f"Unsupported catalog quality finding class: {finding_class}"
            )
            raise ValueError(message)
        if status not in {"pass", "fail"}:
            message = f"Unsupported catalog quality status: {status}"
            raise ValueError(message)


def _covered_strata(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
) -> tuple[CatalogQualitySampleStratum, ...]:
    present = {unit.stratum for unit in audit_units}
    return tuple(
        stratum for stratum in _required_strata() if stratum in present
    )


def _missing_strata(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
) -> tuple[CatalogQualitySampleStratum, ...]:
    present = {unit.stratum for unit in audit_units}
    return tuple(
        stratum for stratum in _required_strata() if stratum not in present
    )


def _duplicate_unit_ids(
    audit_units: tuple[CatalogQualityAuditUnit, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for unit in audit_units:
        normalized = unit.unit_id.casefold()
        if normalized in seen:
            duplicates.add(unit.unit_id)
        seen.add(normalized)
    return tuple(sorted(duplicates))


def _required_strata() -> tuple[CatalogQualitySampleStratum, ...]:
    return (
        "built_in",
        "control_surface",
        "make_ai",
        "popular_app",
        "heavy_spec",
        "random_app",
        "graph_edge",
        "field_schema",
    )


def _finding_classes() -> tuple[CatalogQualityFindingClass, ...]:
    return (
        "semantic_usefulness",
        "graph_usefulness",
        "field_coverage",
        "evidence_gap",
        "ranking",
    )
