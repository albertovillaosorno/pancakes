# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for static Make scenario rule-surface taxonomy.

Boundary contract:
- Owns: metadata tests for scenario rule-surface evidence and output boundaries.
- Must not: test live Make.com, emit findings, or expose private linter
  mechanics.
- Allows: synthetic metadata assertions against the static taxonomy.
- Split when: scenario surfaces become executable validation behavior.
"""

from __future__ import annotations

import pytest
from blueprints.validation import (
    make_linter_rule_family_by_id,
    scenario_rule_surface_by_id,
    scenario_rule_surface_ids,
    scenario_rule_surfaces,
)

REQUIRED_SCENARIO_RULE_SURFACES = frozenset(
    (
        "aggregator",
        "data_store",
        "data_structure",
        "error_handler",
        "filter",
        "http",
        "human_audit",
        "iterator",
        "json_parse",
        "make_ai",
        "operation_volume_optimization",
        "router",
        "webhook",
    )
)
FORBIDDEN_CUSTOMER_COPY_FRAGMENTS = (
    "finding id",
    "internal",
    "predicate",
    "rule code",
    "source path",
)
OPERATION_SURFACE_IDS = frozenset(
    ("aggregator", "iterator", "operation_volume_optimization")
)


def test_scenario_rule_taxonomy_declares_required_surfaces() -> None:
    """All pending Make scenario surfaces have durable metadata."""
    surface_ids = set(scenario_rule_surface_ids())

    missing = REQUIRED_SCENARIO_RULE_SURFACES.difference(surface_ids)
    assert not missing, f"Scenario rule surfaces are missing: {sorted(missing)}"
    assert len(surface_ids) == len(scenario_rule_surfaces()), (
        f"Scenario rule surface IDs are not unique: {surface_ids}"
    )


def test_scenario_rule_surfaces_separate_customer_copy() -> None:
    """Customer-facing summaries hide linter internals."""
    for surface in scenario_rule_surfaces():
        assert surface.customer_visible_summary.strip(), (
            f"Customer summary is empty: {surface}"
        )
        assert surface.internal_linter_boundary.strip(), (
            f"Internal boundary is empty: {surface}"
        )
        rendered_customer_summary = surface.customer_visible_summary.casefold()
        for fragment in FORBIDDEN_CUSTOMER_COPY_FRAGMENTS:
            assert fragment not in rendered_customer_summary, (
                "Customer summary leaks internal wording "
                f"{fragment!r}: {surface}"
            )
        assert any(
            fragment in surface.internal_linter_boundary.casefold()
            for fragment in ("internal", "do not expose", "keep")
        ), f"Internal boundary does not constrain private details: {surface}"


def test_scenario_rule_surfaces_reference_promoted_linter_families() -> None:
    """Every scenario surface maps to known linter taxonomy families."""
    for surface in scenario_rule_surfaces():
        assert surface.canonical_rule_family_ids, (
            f"Surface lacks canonical rule families: {surface}"
        )
        for family_id in surface.canonical_rule_family_ids:
            family = make_linter_rule_family_by_id(family_id)
            assert family.family_id == family_id, (
                "Surface references wrong linter family "
                f"{family_id!r}: {family}"
            )


def test_operations_surfaces_stay_out_of_other_gates() -> None:
    """Operation optimization remains a separate advisory signal family."""
    operation_surfaces = tuple(
        surface
        for surface in scenario_rule_surfaces()
        if surface.surface_id in OPERATION_SURFACE_IDS
    )

    assert operation_surfaces, "Operation optimization surfaces are missing."
    for surface in operation_surfaces:
        assert surface.signal_domains == ("operations",), (
            f"Operations surface leaked into other signal domains: {surface}"
        )
        assert surface.output_posture == "optimization_only", (
            f"Operations surface must stay optimization-only: {surface}"
        )
        assert surface.canonical_rule_family_ids == (
            "operation_volume_optimization",
        ), f"Operations surface uses non-optimization families: {surface}"


def test_visual_claims_for_notes_and_labels_remain_live_parity_gated() -> None:
    """Visual claims require Make parity evidence."""
    gated_surfaces = (
        scenario_rule_surface_by_id("filter"),
        scenario_rule_surface_by_id("error_handler"),
    )

    for surface in gated_surfaces:
        assert (
            surface.evidence_gate
            == "make_live_parity_required_for_customer_visual_claims"
        ), (
            "Visual customer claims must stay gated by live parity evidence: "
            f"{surface}"
        )


def test_unknown_scenario_rule_surface_ids_fail_closed() -> None:
    """Unknown surface IDs cannot silently pass as supported rule surfaces."""
    with pytest.raises(ValueError, match="Unsupported scenario rule surface"):
        _ = scenario_rule_surface_by_id("make_magic")
