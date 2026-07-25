# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the catalog quality audit sampling gate.

Boundary contract:
- Owns: representative catalog-quality sample coverage and follow-up record
tests.
- Must not: author catalog answers, inspect live providers, or mutate catalog
storage.
- Allows: synthetic audit units and deterministic readiness/follow-up
assertions.
- Split when: persisted audit storage or operator review tooling gets separate
coverage.
- Merge when: generation audit tests own the same catalog-strength readiness
gate.
"""

from __future__ import annotations

import pytest
from catalog.quality_audit import (
    CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE,
    CatalogQualityAuditUnit,
    CatalogQualityCheckStatus,
    CatalogQualitySampleStratum,
    build_catalog_quality_audit_report,
)

REQUIRED_STRATA: tuple[CatalogQualitySampleStratum, ...] = (
    "built_in",
    "control_surface",
    "make_ai",
    "popular_app",
    "heavy_spec",
    "random_app",
    "graph_edge",
    "field_schema",
)
FINDING_CLASSES = (
    "semantic_usefulness",
    "graph_usefulness",
    "field_coverage",
    "evidence_gap",
    "ranking",
)


def test_catalog_quality_audit_requires_100_representative_units() -> None:
    """A clean catalog-quality audit becomes ready only after full.

    representative coverage.
    """
    units = _audit_units(CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE)

    report = build_catalog_quality_audit_report(audit_units=units)

    assert report.status == "ready"
    assert report.requested_sample_size == CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE
    assert report.minimum_sample_size == CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE
    assert report.audited_unit_count == CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE
    assert report.required_strata == REQUIRED_STRATA
    assert report.covered_strata == REQUIRED_STRATA
    assert not (report.missing_strata)
    assert all(count > 0 for _, count in report.sample_counts_by_stratum)
    assert report.pass_counts_by_class == tuple(
        (finding_class, CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE)
        for finding_class in FINDING_CLASSES
    )
    assert report.fail_counts_by_class == tuple(
        (finding_class, 0) for finding_class in FINDING_CLASSES
    )
    assert not (report.follow_up_records)
    assert not (report.blockers)
    assert report.catalog_answers_authored is False
    assert report.live_provider_called is False
    assert report.external_model_called is False


def test_catalog_quality_audit_blocks_small_or_unrepresentative_samples() -> (
    None
):
    """The gate blocks fewer than 100 units and missing required audit.

    strata.
    """
    units = _audit_units(
        CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE - 1, omitted_strata=("make_ai",)
    )

    report = build_catalog_quality_audit_report(audit_units=units)
    blocker_codes = {blocker.code for blocker in report.blockers}

    assert report.status == "blocked"
    assert report.audited_unit_count == CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE - 1
    assert "make_ai" in report.missing_strata
    assert blocker_codes == {
        "catalog_quality.sample_size_below_gate",
        "catalog_quality.sample_stratum_missing",
    }


def test_catalog_quality_audit_records_follow_up_for_each_failed_class() -> (
    None
):
    """Failed semantic, graph, field, evidence, and ranking checks get typed.

    records.
    """
    failed_unit = _audit_unit(index=0, stratum="built_in", status="fail")
    units = (
        failed_unit,
        *_audit_units(CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE - 1, offset=1),
    )

    report = build_catalog_quality_audit_report(audit_units=units)
    records_by_class = {
        record.finding_class: record for record in report.follow_up_records
    }

    assert report.status == "needs_follow_up"
    assert report.fail_counts_by_class == tuple(
        (finding_class, 1) for finding_class in FINDING_CLASSES
    )
    assert set(records_by_class) == set(FINDING_CLASSES)
    for finding_class in FINDING_CLASSES:
        record = records_by_class[finding_class]
        assert record.status == "open"
        assert record.severity == "error"
        assert record.unit_id == failed_unit.unit_id
        assert record.stratum == "built_in"
        assert record.record_id.startswith(f"catalog-quality:{finding_class}:")
        assert record.evidence_refs == failed_unit.evidence_refs
        assert record.recommended_action


def test_catalog_quality_audit_rejects_lower_operator_sample_size() -> None:
    """A later caller cannot silently lower the 100-unit catalog audit floor."""
    with pytest.raises(ValueError, match="cannot be below"):
        _ = build_catalog_quality_audit_report(
            audit_units=_audit_units(CATALOG_QUALITY_MINIMUM_SAMPLE_SIZE),
            requested_sample_size=99,
        )


def _audit_units(
    count: int,
    *,
    offset: int = 0,
    omitted_strata: tuple[CatalogQualitySampleStratum, ...] = (),
) -> tuple[CatalogQualityAuditUnit, ...]:
    strata: tuple[CatalogQualitySampleStratum, ...] = tuple(
        stratum for stratum in REQUIRED_STRATA if stratum not in omitted_strata
    )
    return tuple(
        _audit_unit(index=index + offset, stratum=strata[index % len(strata)])
        for index in range(count)
    )


def _audit_unit(
    *,
    index: int,
    stratum: CatalogQualitySampleStratum,
    status: CatalogQualityCheckStatus = "pass",
) -> CatalogQualityAuditUnit:
    return CatalogQualityAuditUnit(
        unit_id=f"audit-unit-{index:03d}",
        stratum=stratum,
        module_id=f"module:test:{index:03d}",
        app_slug=f"app-{index % 7}",
        semantic_usefulness=status,
        graph_usefulness=status,
        field_coverage=status,
        evidence_gap=status,
        ranking=status,
        evidence_refs=(f"catalog-audit-evidence-{index:03d}",),
        reviewer_note="Synthetic audit row for deterministic gate coverage.",
    )
