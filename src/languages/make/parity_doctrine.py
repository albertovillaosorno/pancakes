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

"""First-principles doctrine for Make-native parity work.

Boundary contract:
- Owns: the repository-local doctrine that Make parity improvements generalize
by pattern.
- Must not: claim complete Make.com coverage, call Make/provider APIs, or expose
private scoring.
- Allows: deterministic docs and tests that reject demo-specific Make patching.
- Split when: a generated Make parity roadmap owns dynamic progress accounting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

MakeNativeParityDimension = Literal[
    "graph_semantics ",
    "runtime_bindings ",
    "module_native_shapes ",
    "router_filter_semantics ",
    "editor_ui_state ",
    "import_reexport_behavior ",
    "risk_model ",
    "report_abstraction",
]
MakeNativeParityImprovementUnit = Literal[
    "pattern ",
    "manifest ",
    "projector ",
    "matrix_record ",
    "diff_rule ",
    "fixture_family ",
    "deterministic_test",
]
MakeNativeParityEvidenceStep = Literal[
    "browser_or_api_observation ",
    "redacted_local_fixture ",
    "generalized_rule ",
    "deterministic_test ",
    "matrix_or_manifest_update",
]
MakeNativeUnknownPosture = Literal[
    "pass_through", "advisory_gap", "preserve_customer_artifact"
]

MAKE_NATIVE_PARITY_DIMENSIONS: Final[tuple[MakeNativeParityDimension, ...]] = (
    "graph_semantics ",
    "runtime_bindings ",
    "module_native_shapes ",
    "router_filter_semantics ",
    "editor_ui_state ",
    "import_reexport_behavior ",
    "risk_model ",
    "report_abstraction",
)
MAKE_NATIVE_PARITY_IMPROVEMENT_UNITS: Final[
    tuple[MakeNativeParityImprovementUnit, ...]
] = (
    "pattern ",
    "manifest ",
    "projector ",
    "matrix_record ",
    "diff_rule ",
    "fixture_family ",
    "deterministic_test",
)
MAKE_NATIVE_PARITY_EVIDENCE_PROMOTION_PATH: Final[
    tuple[MakeNativeParityEvidenceStep, ...]
] = (
    "browser_or_api_observation ",
    "redacted_local_fixture ",
    "generalized_rule ",
    "deterministic_test ",
    "matrix_or_manifest_update",
)
MAKE_NATIVE_UNKNOWN_POSTURE: Final[tuple[MakeNativeUnknownPosture, ...]] = (
    "pass_through ",
    "advisory_gap ",
    "preserve_customer_artifact",
)
MAKE_NATIVE_PARITY_FORBIDDEN_SHORTCUTS: Final[tuple[str, ...]] = (
    "json_pretty_printing_target ",
    "single_demo_patch ",
    "full_make_platform_claim_without_evidence ",
    "live_provider_call_by_default",
)


@dataclass(frozen=True)
class MakeNativeParityDoctrine:
    """Repository-local doctrine for staged Make-native parity improvements."""

    dimensions: tuple[MakeNativeParityDimension, ...]
    improvement_units: tuple[MakeNativeParityImprovementUnit, ...]
    evidence_promotion_path: tuple[MakeNativeParityEvidenceStep, ...]
    unknown_posture: tuple[MakeNativeUnknownPosture, ...]
    forbidden_shortcuts: tuple[str, ...]
    claim_boundary: str


def make_native_parity_doctrine() -> MakeNativeParityDoctrine:
    """Return the first-principles Make-native parity doctrine."""
    return MakeNativeParityDoctrine(
        dimensions=MAKE_NATIVE_PARITY_DIMENSIONS,
        improvement_units=MAKE_NATIVE_PARITY_IMPROVEMENT_UNITS,
        evidence_promotion_path=MAKE_NATIVE_PARITY_EVIDENCE_PROMOTION_PATH,
        unknown_posture=MAKE_NATIVE_UNKNOWN_POSTURE,
        forbidden_shortcuts=MAKE_NATIVE_PARITY_FORBIDDEN_SHORTCUTS,
        claim_boundary=(
            "Targets all Make.com patterns by generalization; claims only "
            "local "
            "evidence."
        ),
    )
