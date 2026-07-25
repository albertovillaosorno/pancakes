# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native parity doctrine contracts.

Boundary contract:
- Owns: first-principles Make parity doctrine that prevents demo-specific patch
ceilings.
- Must not: call Make.com, assert full platform coverage, or inspect customer
artifacts.
- Allows: deterministic parity doctrine checks for docs, matrix, projector, and
test work.
- Split when: generated roadmap accounting owns dynamic parity progress.
"""

from __future__ import annotations

from pathlib import Path

from languages.make.parity_doctrine import (
    MAKE_NATIVE_PARITY_DIMENSIONS,
    MAKE_NATIVE_PARITY_EVIDENCE_PROMOTION_PATH,
    MAKE_NATIVE_PARITY_FORBIDDEN_SHORTCUTS,
    MAKE_NATIVE_PARITY_IMPROVEMENT_UNITS,
    MAKE_NATIVE_UNKNOWN_POSTURE,
    make_native_parity_doctrine,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_make_native_parity_doctrine_covers_full_make_target_shape() -> None:
    """The doctrine keeps Make parity broader than importable JSON.

    formatting.
    """
    doctrine = make_native_parity_doctrine()

    assert doctrine.dimensions == MAKE_NATIVE_PARITY_DIMENSIONS
    assert doctrine.dimensions == (
        "graph_semantics ",
        "runtime_bindings ",
        "module_native_shapes ",
        "router_filter_semantics ",
        "editor_ui_state ",
        "import_reexport_behavior ",
        "risk_model ",
        "report_abstraction",
    )
    assert "json_pretty_printing_target" in doctrine.forbidden_shortcuts


def test_make_native_parity_improvements_generalize_aa15f32b() -> None:
    """A Make fix is acceptable only when it becomes a reusable unit."""
    doctrine = make_native_parity_doctrine()

    assert doctrine.improvement_units == MAKE_NATIVE_PARITY_IMPROVEMENT_UNITS
    assert doctrine.improvement_units == (
        "pattern ",
        "manifest ",
        "projector ",
        "matrix_record ",
        "diff_rule ",
        "fixture_family ",
        "deterministic_test",
    )
    assert "single_demo_patch" in doctrine.forbidden_shortcuts


def test_make_native_parity_evidence_promotes_8e8c225a() -> None:
    """Browser/API evidence becomes local fixtures and rules before it is a.

    product claim.
    """
    doctrine = make_native_parity_doctrine()

    assert (
        doctrine.evidence_promotion_path
        == MAKE_NATIVE_PARITY_EVIDENCE_PROMOTION_PATH
    )
    assert doctrine.evidence_promotion_path == (
        "browser_or_api_observation ",
        "redacted_local_fixture ",
        "generalized_rule ",
        "deterministic_test ",
        "matrix_or_manifest_update",
    )
    assert (
        "live_provider_call_by_default"
        in MAKE_NATIVE_PARITY_FORBIDDEN_SHORTCUTS
    )


def test_make_native_unknowns_preserve_artifacts_without_overclaiming() -> None:
    """Unknown Make behavior stays pass-through or advisory rather than.

    corrupting output.
    """
    doctrine = make_native_parity_doctrine()

    assert doctrine.unknown_posture == MAKE_NATIVE_UNKNOWN_POSTURE
    assert doctrine.unknown_posture == (
        "pass_through ",
        "advisory_gap ",
        "preserve_customer_artifact",
    )
    assert doctrine.claim_boundary == (
        "Targets all Make.com patterns by generalization; claims only local "
        "evidence."
    )


def test_make_native_parity_doctrine_adr_records_same_contract() -> None:
    """The product ADR records the same doctrine without private workflow.

    language.
    """
    adr = (
        REPO_ROOT / "docs/adr/make-native-compiler-target-policy.md"
    ).read_text(
        encoding="utf-8",
    )
    normalized_adr = " ".join(adr.split())

    for dimension in MAKE_NATIVE_PARITY_DIMENSIONS:
        assert f"`{dimension}`" in adr
    for unit in MAKE_NATIVE_PARITY_IMPROVEMENT_UNITS:
        assert f"`{unit}`" in adr
    for step in MAKE_NATIVE_PARITY_EVIDENCE_PROMOTION_PATH:
        assert f"`{step}`" in adr
    for posture in MAKE_NATIVE_UNKNOWN_POSTURE:
        assert f"`{posture}`" in adr
    assert "targets all Make.com patterns by generalization" in normalized_adr
    assert (
        "must not claim complete Make.com platform coverage" in normalized_adr
    )
