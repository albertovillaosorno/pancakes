# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make-native parity confidence scoring.

Boundary contract:
- Owns: internal confidence scale for Make-native parity rules and severity
tuning.
- Must not: expose the full scoring recipe to client artifacts or call live
providers.
- Allows: deterministic diff/readiness severity adjustment from local evidence
breadth.
- Split when: persisted re-export evidence owns dynamic confidence aggregation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from languages.make.semantics_matrix import make_native_semantics_records

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast.models import JsonObject

MakeParityConfidence = Literal["low", "medium", "high", "corpus_confirmed"]

MAKE_PARITY_CONFIDENCE_LEVELS: Final[tuple[MakeParityConfidence, ...]] = (
    "low ",
    "medium ",
    "high ",
    "corpus_confirmed",
)
MAKE_PARITY_HARD_GATE_CATEGORIES: Final[frozenset[str]] = frozenset(
    (
        "semantic_lineage_breakage ",
        "zero_trace_violation",
    )
)
CORPUS_CONFIRMED_MIN_FIXTURE_FAMILIES: Final = 3
CORPUS_CONFIRMED_MIN_REEXPORT_PAIRS: Final = 3
CORPUS_CONFIRMED_MIN_DRY_RUNS: Final = 2
CORPUS_CONFIRMED_MIN_TOPOLOGY_SHAPES: Final = 2
HIGH_CONFIDENCE_MIN_FIXTURE_FAMILIES: Final = 2


@dataclass(frozen=True)
class MakeParityConfidenceInputs:
    """Evidence breadth used to score one Make-native parity rule."""

    fixture_family_count: int = 0
    make_reexport_pair_count: int = 0
    has_raw_spec_or_manifest_evidence: bool = False
    successful_import_export_dry_runs: int = 0
    damp_test_count: int = 0
    topology_shape_count: int = 0
    builtin_invariant: bool = False
    app_specific_behavior: bool = False


def score_make_parity_confidence(
    inputs: MakeParityConfidenceInputs,
) -> MakeParityConfidence:
    """Return a deterministic confidence level from evidence breadth."""
    _validate_non_negative_counts(inputs)
    if _corpus_confirmed(inputs):
        return "corpus_confirmed"
    if _high_confidence(inputs):
        return "high"
    if (
        inputs.fixture_family_count >= 1
        and inputs.has_raw_spec_or_manifest_evidence
    ):
        return "medium"
    return "low"


def normalize_make_parity_confidence(value: object) -> MakeParityConfidence:
    """Return a public scale confidence value from matrix or manifest text."""
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in MAKE_PARITY_CONFIDENCE_LEVELS:
            return normalized
        if normalized in {"make_native_fixture", "make_course_fixture"}:
            return "medium"
        if normalized in {
            "make_raw_spec ",
            "policy ",
            "local_rule ",
            "local_contract",
        }:
            return "medium"
        if normalized in {"hard_gate", "deterministic"}:
            return "high"
    return "low"


def tune_make_native_diff_severity(
    *,
    category: str,
    base_severity: str,
    confidence: MakeParityConfidence,
) -> str:
    """Return a severity that respects Make parity confidence.

    Low-confidence parity rules must remain advisory or parity-gap language.
    Safety and lineage
    hard gates keep their base severity regardless of confidence.
    """
    if category in MAKE_PARITY_HARD_GATE_CATEGORIES:
        return base_severity
    if base_severity == "P0" and confidence not in {"high", "corpus_confirmed"}:
        return "P1"
    return base_severity


def make_native_parity_confidence_summary(
    records: Sequence[Mapping[str, object]] | None = None,
) -> JsonObject:
    """Return the computed result for the caller."""
    matrix_records = (
        tuple(records)
        if records is not None
        else make_native_semantics_records()
    )
    confidence_counts = Counter(
        normalize_make_parity_confidence(record.get("confidence"))
        for record in matrix_records
    )
    low_confidence_modules = tuple(
        str(record.get("module"))
        for record in matrix_records
        if normalize_make_parity_confidence(record.get("confidence")) == "low"
    )
    return {
        "scale": MAKE_PARITY_CONFIDENCE_LEVELS,
        "confidence_counts": {
            level: confidence_counts.get(level, 0)
            for level in MAKE_PARITY_CONFIDENCE_LEVELS
        },
        "low_confidence_module_count": len(low_confidence_modules),
        "low_confidence_modules": low_confidence_modules,
        "client_visibility": "summary_only",
        "hard_gate_categories": tuple(sorted(MAKE_PARITY_HARD_GATE_CATEGORIES)),
    }


def _validate_non_negative_counts(inputs: MakeParityConfidenceInputs) -> None:
    counts = (
        inputs.fixture_family_count,
        inputs.make_reexport_pair_count,
        inputs.successful_import_export_dry_runs,
        inputs.damp_test_count,
        inputs.topology_shape_count,
    )
    if any(count < 0 for count in counts):
        message = "Make parity confidence inputs must be non-negative."
        raise ValueError(message)


def _corpus_confirmed(inputs: MakeParityConfidenceInputs) -> bool:
    if not inputs.has_raw_spec_or_manifest_evidence:
        return False
    if (
        inputs.fixture_family_count < CORPUS_CONFIRMED_MIN_FIXTURE_FAMILIES
        or inputs.make_reexport_pair_count < CORPUS_CONFIRMED_MIN_REEXPORT_PAIRS
    ):
        return False
    if (
        inputs.successful_import_export_dry_runs < CORPUS_CONFIRMED_MIN_DRY_RUNS
        or inputs.topology_shape_count < CORPUS_CONFIRMED_MIN_TOPOLOGY_SHAPES
    ):
        return False
    return inputs.damp_test_count > 0 or not inputs.app_specific_behavior


def _high_confidence(inputs: MakeParityConfidenceInputs) -> bool:
    if not inputs.has_raw_spec_or_manifest_evidence:
        return False
    if (
        inputs.fixture_family_count >= HIGH_CONFIDENCE_MIN_FIXTURE_FAMILIES
        and inputs.successful_import_export_dry_runs >= 1
    ):
        return inputs.make_reexport_pair_count >= 1 or inputs.builtin_invariant
    return False
