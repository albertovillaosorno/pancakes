# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native parity completion gate contracts.

Boundary contract:
- Owns: declared-scope completion vocabulary for Make-native parity.
- Must not: claim complete Make.com platform support or use live Make/provider
calls.
- Allows: deterministic scope evidence for readiness, diff, and docs surfaces.
- Split when: dynamic parity confidence scoring owns per-module evidence
aggregation.
"""

from __future__ import annotations

from pathlib import Path

from languages.make.parity_gates import (
    MAKE_NATIVE_PARITY_GATES,
    MAKE_NATIVE_PARITY_STATES,
    MAKE_NATIVE_PARITY_V1_SCOPE_KEYS,
    make_native_parity_item_complete,
    make_native_parity_required_gates,
    make_native_parity_scope_v1,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_make_native_parity_completion_levels_are_explicit() -> None:
    """Completion levels separate unsupported, importable, native, and stable.

    states.
    """
    assert MAKE_NATIVE_PARITY_STATES == (
        "not_supported",
        "pass_through",
        "import_safe",
        "native_shape",
        "roundtrip_stable",
    )


def test_make_native_parity_v1_scope_is_declared_without_full_make_claims() -> (
    None
):
    """The v1 scope is serious but bounded to known adapter surfaces."""
    scope = make_native_parity_scope_v1()

    assert tuple(item.key for item in scope) == MAKE_NATIVE_PARITY_V1_SCOPE_KEYS
    assert MAKE_NATIVE_PARITY_V1_SCOPE_KEYS == (
        "webhook",
        "router",
        "datastore",
        "slack",
        "basic_filters",
        "runtime_placeholders",
        "import_readiness",
        "zero_trace",
        "handoff_report_abstraction",
        "giant_stress_fixtures",
        "semantic_diff_classification",
    )
    for item in scope:
        assert "not complete across all Make.com" in item.false_claim_guard


def test_scope_items_require_all_completion_gates() -> None:
    """Every scope item needs evidence before Pancakes calls it complete."""
    scope = make_native_parity_scope_v1()

    assert make_native_parity_required_gates() == MAKE_NATIVE_PARITY_GATES
    assert MAKE_NATIVE_PARITY_GATES == (
        "manifest_or_matrix_record",
        "fixture_family_coverage",
        "damp_tests_where_lineage_matters",
        "native_mapper_parameters_expect_restore_coverage",
        "zero_trace_coverage",
        "diff_classification_coverage",
        "pass_through_behavior_for_unsupported_variants",
        "import_export_dry_run_evidence",
        "no_live_make_or_provider_call_by_default",
    )
    for item in scope:
        assert item.required_gates == MAKE_NATIVE_PARITY_GATES


def test_completion_requires_target_state_and_all_gates() -> None:
    """A partial evidence set cannot be reported as perfect for scope."""
    item = make_native_parity_scope_v1()[0]
    all_gates = set(MAKE_NATIVE_PARITY_GATES)
    missing_gate = set(MAKE_NATIVE_PARITY_GATES[:-1])

    assert make_native_parity_item_complete(
        item=item,
        current_state="roundtrip_stable",
        satisfied_gates=all_gates,
    )
    assert not make_native_parity_item_complete(
        item=item,
        current_state="native_shape",
        satisfied_gates=all_gates,
    )
    assert not make_native_parity_item_complete(
        item=item,
        current_state="roundtrip_stable",
        satisfied_gates=missing_gate,
    )


def test_make_native_parity_gate_adr_records_same_contract() -> None:
    """The docs surface states the same scope, states, and false-claim guard."""
    adr = (
        REPO_ROOT / "docs/adr/make-native-parity-completion-gates-policy.md"
    ).read_text(
        encoding="utf-8",
    )

    for state in MAKE_NATIVE_PARITY_STATES:
        assert f"`{state}`" in adr
    for scope_key in MAKE_NATIVE_PARITY_V1_SCOPE_KEYS:
        assert f"`{scope_key}`" in adr
    for gate in MAKE_NATIVE_PARITY_GATES:
        assert f"`{gate}`" in adr
    assert "perfect within declared scope" in adr
    assert "not complete across all of Make.com" in adr
