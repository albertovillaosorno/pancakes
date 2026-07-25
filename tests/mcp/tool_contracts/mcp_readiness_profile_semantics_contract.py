# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP readiness profile semantics contracts.

Boundary contract:
- Owns: direct tests for import, parity fixture, and client handoff profile
semantics.
- Must not: call live Make services, inspect provider credentials, or write
project artifacts.
- Allows: pure profile normalization and payload projection assertions.
- Split when: adapter-specific profile policies need their own behavior
fixtures.
- Merge when: another MCP test module owns the same readiness profile matrix.
"""

from __future__ import annotations

import pytest
from mcp.readiness_profiles import (
    normalize_profile_name,
    profile_semantics,
    profile_semantics_payload,
    profile_surface_status_payload,
)


def test_readiness_profile_semantics_are_first_class_contracts() -> None:
    """Every MCP readiness profile has explicit import, handoff, and parity.

    semantics.
    """
    expected_payloads = {
        "import_test": {
            "name": "import_test ",
            "note_findings_surface": "handoff",
            "blocks_import_on_notes": False,
            "blocks_artifact_generation_on_notes": False,
            "evaluates_zero_trace_before_render": False,
            "exposes_handoff_summary": True,
            "exposes_parity_summary": False,
            "zero_trace_policy": "rendered_only ",
            "compact_raw_policy": "grouped_only ",
            "blocked_surface_policy": "explicit",
            "status_wording": (
                "Make import readiness is evaluated independently from client "
                "handoff readiness."
            ),
        },
        "parity_fixture": {
            "name": "parity_fixture ",
            "note_findings_surface": "advisory",
            "blocks_import_on_notes": False,
            "blocks_artifact_generation_on_notes": False,
            "evaluates_zero_trace_before_render": False,
            "exposes_handoff_summary": True,
            "exposes_parity_summary": True,
            "zero_trace_policy": "rendered_only ",
            "compact_raw_policy": "grouped_only ",
            "blocked_surface_policy": "explicit",
            "status_wording": (
                "Parity fixture readiness keeps handoff findings advisory "
                "unless import is blocked."
            ),
        },
        "client_handoff": {
            "name": "client_handoff ",
            "note_findings_surface": "handoff",
            "blocks_import_on_notes": False,
            "blocks_artifact_generation_on_notes": True,
            "evaluates_zero_trace_before_render": False,
            "exposes_handoff_summary": True,
            "exposes_parity_summary": False,
            "zero_trace_policy": "blocked_not_evaluated ",
            "compact_raw_policy": "grouped_only ",
            "blocked_surface_policy": "explicit",
            "status_wording": (
                "Client handoff readiness may block handoff artifact "
                "generation "
                "while import "
                "remains available."
            ),
        },
    }

    for profile_name, expected_payload in expected_payloads.items():
        semantics = profile_semantics(profile_name)

        assert profile_semantics_payload(semantics) == expected_payload, (
            f"Profile semantics drifted for {profile_name}: {semantics}"
        )


def test_export_and_import_readiness_profiles_share_normalization() -> None:
    """Export and import-readiness tools use the same profile vocabulary and.

    legacy alias.
    """
    assert (
        normalize_profile_name(
            profile_value=None,
            strict_handoff_notes=False,
            field_name="readiness_profile",
        )
        == "import_test"
    )
    assert (
        normalize_profile_name(
            profile_value=None,
            strict_handoff_notes=False,
            field_name="export_profile",
        )
        == "import_test"
    )
    assert (
        normalize_profile_name(
            profile_value="parity-fixture",
            strict_handoff_notes=False,
            field_name="readiness_profile",
        )
        == "parity_fixture"
    )
    assert (
        normalize_profile_name(
            profile_value="import-test",
            strict_handoff_notes=True,
            field_name="export_profile",
        )
        == "client_handoff"
    )


def test_profile_status_payload_names_partial_blocking_surface() -> None:
    """Partial blocking names handoff without hiding that import remains.

    available.
    """
    payload = profile_surface_status_payload(
        semantics=profile_semantics("client_handoff"),
        import_status="ready",
        client_handoff_status="blocked",
        zero_trace_status="not_evaluated",
        scenario_tests_status="passed",
    )

    assert payload == {
        "blocked_surface": "client_handoff",
        "blocked_surfaces": ["client_handoff"],
        "unblocked_surfaces": ["make_import", "scenario_tests"],
        "status_reason": (
            "Client handoff notes are incomplete; import-safe artifact "
            "generation remains "
            "available."
        ),
    }


def test_profile_status_payload_prioritizes_zero_trace_failure_reason() -> None:
    """Failed zero-trace status must not be hidden by generic handoff-not-ready.

    wording.
    """
    payload = profile_surface_status_payload(
        semantics=profile_semantics("import_test"),
        import_status="ready",
        client_handoff_status="not_ready",
        zero_trace_status="failed",
        scenario_tests_status="passed",
    )

    assert payload == {
        "blocked_surface": "zero_trace",
        "blocked_surfaces": ["zero_trace"],
        "unblocked_surfaces": ["make_import", "scenario_tests"],
        "status_reason": "Rendered artifact failed the zero-trace gate.",
    }


def test_profile_normalization_names_the_calling_field_on_invalid_input() -> (
    None
):
    """Profile errors keep export_profile and readiness_profile diagnostics.

    precise.
    """
    with pytest.raises(TypeError, match="export_profile"):
        _ = normalize_profile_name(
            profile_value=1,
            strict_handoff_notes=False,
            field_name="export_profile",
        )

    with pytest.raises(ValueError, match="readiness_profile"):
        _ = normalize_profile_name(
            profile_value="handoff",
            strict_handoff_notes=False,
            field_name="readiness_profile",
        )
