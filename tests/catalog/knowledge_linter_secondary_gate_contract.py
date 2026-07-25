# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for secondary Make linter result shaping.

Boundary contract:
- Owns: low-weight secondary linter result contracts from Make designer
messages.
- Must not: contact Make.com, require credentials, or replace offline
validation.
- Allows: synthetic documented blueprint response payloads and warning-only
checks.
- Split when: live HTTP adapters or MCP payload shaping need separate contracts.
- Merge when: knowledge_linter_probe_contract owns the same secondary result
behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.knowledge import (
    MAKE_DESIGNER_WARNING_PREFIX,
    MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT,
    MAKE_SECONDARY_LINTER_SOURCE,
    normalize_linter_findings,
    secondary_linter_result_from_findings,
    secondary_linter_unavailable,
)

if TYPE_CHECKING:
    from languages.make.raw_specs.models import JsonObject

FIXED_CAPTURED_AT = "2026-05-06T00:00:00+00:00"
CONFIDENCE_WEIGHT_TOLERANCE = 1e-9


def test_secondary_linter_reports_unavailable_when_api_evidence_is_absent() -> (
    None
):
    """Missing Make API evidence is reported instead of fabricated as clean."""
    result = secondary_linter_unavailable()

    payload = result.to_json()
    assert payload.get("status") == "secondary_linter_unavailable", (
        f"Missing evidence must be explicit: {payload}"
    )
    assert payload.get("source") == MAKE_SECONDARY_LINTER_SOURCE, (
        f"Secondary linter source drifted: {payload}"
    )
    assert payload.get("warnings") == [], (
        f"Unavailable secondary linter must not invent warnings: {payload}"
    )
    assert_confidence_weight(payload, 0.0)


def test_secondary_linter_reports_low_weight_pass_for_empty_api_result() -> (
    None
):
    """An available API response with no designer messages is a low-weight.

    pass.
    """
    result = secondary_linter_result_from_findings(())

    payload = result.to_json()
    assert payload.get("status") == "secondary_linter_passed", (
        f"Empty API result should be an explicit pass: {payload}"
    )
    assert_confidence_weight(payload, MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT)
    assert payload.get("warnings") == [], (
        f"Empty API result should not fabricate warnings: {payload}"
    )


def test_secondary_linter_converts_designer_messages_to_warnings_only() -> None:
    """Make designer messages remain warning-only in the secondary result."""
    findings = normalize_linter_findings(
        payload=blueprint_response_with_designer_warning(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    result = secondary_linter_result_from_findings(findings)
    payload = result.to_json()
    warnings = result.warnings

    assert payload.get("status") == "secondary_linter_warning", (
        f"Designer messages should be secondary warnings: {payload}"
    )
    assert payload.get("source") == MAKE_SECONDARY_LINTER_SOURCE, (
        f"Secondary linter source drifted: {payload}"
    )
    assert_confidence_weight(payload, MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT)
    assert len(warnings) == 1, f"Expected one secondary warning: {payload}"
    warning = warnings[0]
    assert warning.get("severity") == "warning", (
        f"Secondary linter must not emit errors: {warning}"
    )
    assert warning.get("source_prefix") == MAKE_DESIGNER_WARNING_PREFIX, (
        f"Designer warning prefix was not preserved: {warning}"
    )
    assert warning.get("source_system") == "make_designer", (
        f"Designer warning source system drifted: {warning}"
    )


def blueprint_response_with_designer_warning() -> JsonObject:
    """Return a synthetic documented blueprint payload with one designer.

    warning.
    """
    return {
        "response": {
            "blueprint": {
                "name": "secondary-linter-warning",
                "flow": [
                    {
                        "id": 2,
                        "module": "json:ParseJSON",
                        "metadata": {
                            "designer": {
                                "messages": [
                                    {
                                        "category": "last ",
                                        "severity": "warning",
                                        "message": (
                                            "A transformer should not be the "
                                            "last module "
                                            "in the route."
                                        ),
                                    }
                                ]
                            }
                        },
                    }
                ],
            }
        }
    }


def assert_confidence_weight(payload: JsonObject, expected: float) -> None:
    """Assert one secondary linter confidence weight without exact float.

    comparison.
    """
    value = payload.get("confidence_weight")
    assert isinstance(value, int | float), (
        f"Secondary linter confidence drifted: {payload}"
    )
    assert not (abs(float(value) - expected) > CONFIDENCE_WEIGHT_TOLERANCE), (
        f"Secondary linter confidence drifted: {payload}"
    )
