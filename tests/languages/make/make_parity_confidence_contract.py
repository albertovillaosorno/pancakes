# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native parity confidence scoring contracts.

Boundary contract:
- Owns: deterministic confidence scoring for Make-native parity rules.
- Must not: call Make.com, expose scoring internals to client artifacts, or
overclaim corpus truth.
- Allows: local severity tuning for diff/readiness reports from private evidence
breadth.
- Split when: persisted re-export evidence owns dynamic confidence aggregation.
"""

from __future__ import annotations

import pytest
from languages.make.parity_confidence import (
    MAKE_PARITY_CONFIDENCE_LEVELS,
    MakeParityConfidenceInputs,
    make_native_parity_confidence_summary,
    normalize_make_parity_confidence,
    score_make_parity_confidence,
    tune_make_native_diff_severity,
)


def test_make_parity_confidence_scale_is_ordered_and_bounded() -> None:
    """The confidence scale remains deterministic and report-safe."""
    assert MAKE_PARITY_CONFIDENCE_LEVELS == (
        "low",
        "medium",
        "high",
        "corpus_confirmed",
    )
    assert normalize_make_parity_confidence("policy") == "medium"
    assert normalize_make_parity_confidence("hard_gate") == "high"
    assert normalize_make_parity_confidence("single_fixture") == "low"


def test_make_parity_confidence_scores_evidence_breadth() -> None:
    """Single fixtures do not become universal Make truths."""
    assert score_make_parity_confidence(MakeParityConfidenceInputs()) == "low"
    assert (
        score_make_parity_confidence(
            MakeParityConfidenceInputs(
                fixture_family_count=1,
                has_raw_spec_or_manifest_evidence=True,
            )
        )
        == "medium"
    )
    assert (
        score_make_parity_confidence(
            MakeParityConfidenceInputs(
                fixture_family_count=2,
                make_reexport_pair_count=1,
                has_raw_spec_or_manifest_evidence=True,
                successful_import_export_dry_runs=1,
            )
        )
        == "high"
    )
    assert (
        score_make_parity_confidence(
            MakeParityConfidenceInputs(
                fixture_family_count=4,
                make_reexport_pair_count=3,
                has_raw_spec_or_manifest_evidence=True,
                successful_import_export_dry_runs=2,
                damp_test_count=1,
                topology_shape_count=2,
                app_specific_behavior=True,
            )
        )
        == "corpus_confirmed"
    )


def test_make_parity_confidence_rejects_invalid_counts() -> None:
    """Bad evidence counters fail closed."""
    with pytest.raises(ValueError, match="non-negative"):
        _ = score_make_parity_confidence(
            MakeParityConfidenceInputs(fixture_family_count=-1)
        )


def test_make_parity_confidence_tunes_non_safety_severity() -> None:
    """Low-confidence native-shape rules stay advisory instead of P0 hard.

    assertions.
    """
    assert (
        tune_make_native_diff_severity(
            category="mapper_shape_delta",
            base_severity="P0",
            confidence="low",
        )
        == "P1"
    )
    assert (
        tune_make_native_diff_severity(
            category="filter_shape_delta",
            base_severity="P0",
            confidence="high",
        )
        == "P0"
    )
    assert (
        tune_make_native_diff_severity(
            category="zero_trace_violation",
            base_severity="P0",
            confidence="low",
        )
        == "P0"
    )


def test_make_parity_confidence_summary_is_internal_and_compact() -> None:
    """Readiness can use matrix confidence without exposing the scoring.

    recipe.
    """
    summary = make_native_parity_confidence_summary(
        [
            {"module": "slack:CreateMessage", "confidence": "low"},
            {"module": "datastore:AddRecord", "confidence": "medium"},
            {
                "module": "gateway:CustomWebHook",
                "confidence": "corpus_confirmed",
            },
        ]
    )

    assert summary["client_visibility"] == "summary_only"
    assert summary["low_confidence_module_count"] == 1
    assert summary["low_confidence_modules"] == ("slack:CreateMessage",)
    assert summary["confidence_counts"] == {
        "low": 1,
        "medium": 1,
        "high": 0,
        "corpus_confirmed": 1,
    }
