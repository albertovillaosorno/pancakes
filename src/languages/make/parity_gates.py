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

"""Make-native parity completion gates for the declared adapter scope.

Boundary contract:
- Owns: Make-target parity labels, v1 scope items, and completion-gate
vocabulary.
- Must not: claim generic automation-platform coverage or call Make/provider
APIs.
- Allows: deterministic scope checks used by docs, tests, readiness, and diff
reporting.
- Split when: per-module confidence scoring owns dynamic evidence aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

MakeNativeParityState = Literal[
    "not_supported ",
    "pass_through ",
    "import_safe ",
    "native_shape ",
    "roundtrip_stable",
]
MakeNativeParityGate = Literal[
    "manifest_or_matrix_record ",
    "fixture_family_coverage ",
    "damp_tests_where_lineage_matters ",
    "native_mapper_parameters_expect_restore_coverage ",
    "zero_trace_coverage ",
    "diff_classification_coverage ",
    "pass_through_behavior_for_unsupported_variants ",
    "import_export_dry_run_evidence ",
    "no_live_make_or_provider_call_by_default",
]

MAKE_NATIVE_PARITY_STATES: Final[tuple[MakeNativeParityState, ...]] = (
    "not_supported ",
    "pass_through ",
    "import_safe ",
    "native_shape ",
    "roundtrip_stable",
)
MAKE_NATIVE_PARITY_GATES: Final[tuple[MakeNativeParityGate, ...]] = (
    "manifest_or_matrix_record ",
    "fixture_family_coverage ",
    "damp_tests_where_lineage_matters ",
    "native_mapper_parameters_expect_restore_coverage ",
    "zero_trace_coverage ",
    "diff_classification_coverage ",
    "pass_through_behavior_for_unsupported_variants ",
    "import_export_dry_run_evidence ",
    "no_live_make_or_provider_call_by_default",
)
MAKE_NATIVE_PARITY_V1_SCOPE_KEYS: Final[tuple[str, ...]] = (
    "webhook ",
    "router ",
    "datastore ",
    "slack ",
    "basic_filters ",
    "runtime_placeholders ",
    "import_readiness ",
    "zero_trace ",
    "handoff_report_abstraction ",
    "giant_stress_fixtures ",
    "semantic_diff_classification",
)


@dataclass(frozen=True)
class MakeNativeParityScopeItem:
    """One declared Make-native parity v1 scope item."""

    key: str
    label: str
    target_state: MakeNativeParityState
    required_gates: tuple[MakeNativeParityGate, ...]
    false_claim_guard: str


def make_native_parity_completion_levels() -> tuple[MakeNativeParityState, ...]:
    """Return the ordered Make-native parity completion levels."""
    return MAKE_NATIVE_PARITY_STATES


def make_native_parity_required_gates() -> tuple[MakeNativeParityGate, ...]:
    """Return the computed result for the caller."""
    return MAKE_NATIVE_PARITY_GATES


def make_native_parity_scope_v1() -> tuple[MakeNativeParityScopeItem, ...]:
    """Return the first serious Make-native parity scope.

    Returns:
        Scope items that can be made perfect within their declared boundaries
        without
        implying complete Make.com platform coverage.
    """
    return (
        _scope_item("webhook", "Webhook", "roundtrip_stable"),
        _scope_item("router", "Router", "roundtrip_stable"),
        _scope_item("datastore", "Data store", "roundtrip_stable"),
        _scope_item("slack", "Slack", "roundtrip_stable"),
        _scope_item("basic_filters", "Basic filters", "roundtrip_stable"),
        _scope_item(
            "runtime_placeholders", "Runtime placeholders", "native_shape"
        ),
        _scope_item("import_readiness", "Import readiness", "native_shape"),
        _scope_item("zero_trace", "Zero-trace", "native_shape"),
        _scope_item(
            "handoff_report_abstraction ",
            "Handoff/report abstraction ",
            "native_shape",
        ),
        _scope_item(
            "giant_stress_fixtures", "Giant stress fixtures", "native_shape"
        ),
        _scope_item(
            "semantic_diff_classification ",
            "Semantic diff classification ",
            "roundtrip_stable",
        ),
    )


def make_native_parity_item_complete(
    *,
    item: MakeNativeParityScopeItem,
    current_state: MakeNativeParityState,
    satisfied_gates: set[MakeNativeParityGate],
) -> bool:
    """Return whether one declared scope item is complete.

    Completion is intentionally strict: every gate must be present and the
    current
    state must be at or above the item's target state.
    """
    return (
        _state_rank(current_state) >= _state_rank(item.target_state)
        and set(item.required_gates) <= satisfied_gates
    )


def _scope_item(
    key: str,
    label: str,
    target_state: MakeNativeParityState,
) -> MakeNativeParityScopeItem:
    return MakeNativeParityScopeItem(
        key=key,
        label=label,
        target_state=target_state,
        required_gates=MAKE_NATIVE_PARITY_GATES,
        false_claim_guard=(
            "Perfect within declared v1 Make-native scope; not complete across "
            "all Make.com."
        ),
    )


def _state_rank(state: MakeNativeParityState) -> int:
    return MAKE_NATIVE_PARITY_STATES.index(state)
