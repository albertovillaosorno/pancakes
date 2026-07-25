# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for secondary Make linter behavior at the generation gate.

Boundary contract:
- Owns: pre-render gate interaction with low-weight Make designer warnings.
- Must not: contact Make.com, render blueprints, or let linter warnings clear
blockers.
- Allows: synthetic AST, catalog, and reviewed designer-message evidence
fixtures.
- Split when: MCP payload shaping needs independent secondary linter contracts.
- Merge when: blueprint_validation_contract owns the same generation-gate
behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation import guard_blueprint_for_render
from catalog import CatalogSnapshot
from catalog.knowledge import (
    MAKE_DESIGNER_WARNING_PREFIX,
    MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT,
    MAKE_SECONDARY_LINTER_SOURCE,
    KnowledgeDesignerMessageEvidence,
    KnowledgeStoreQuery,
)

if TYPE_CHECKING:
    from languages.make.raw_specs.models import JsonObject

CONFIDENCE_WEIGHT_TOLERANCE = 1e-9


def test_secondary_linter_warning_cannot_clear_offline_generation_blocker() -> (
    None
):
    """Designer warnings are surfaced but unresolved modules still block.

    rendering.
    """
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "secondary-linter-blocked",
                    "flow": [
                        {"id": 1, "module": "unknown-service:MissingAction"}
                    ],
                }
            )
        ),
        catalog=empty_catalog_snapshot(),
        knowledge=designer_warning_knowledge(),
    )

    assert result.status == "blocked", (
        f"Offline blockers must still stop rendering: {result}"
    )
    assert not (result.can_render), (
        f"Offline blockers must still stop rendering: {result}"
    )
    assert result.blockers, (
        f"Unresolved module blocker was not preserved: {result.blockers}"
    )
    assert result.blockers[0].code == "generation.unsupported_module", (
        f"Unresolved module blocker was not preserved: {result.blockers}"
    )
    secondary_linter = result.secondary_linter
    assert secondary_linter is not None, (
        f"Generation gate did not return a secondary linter result: {result}"
    )
    payload = secondary_linter.to_json()
    warnings = secondary_linter.warnings
    assert payload.get("status") == "secondary_linter_warning", (
        f"Designer evidence should surface as secondary warning: {payload}"
    )
    assert payload.get("source") == MAKE_SECONDARY_LINTER_SOURCE, (
        f"Secondary linter source drifted: {payload}"
    )
    assert_confidence_weight(payload, MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT)
    assert len(warnings) == 1, (
        f"Secondary linter warnings must stay warning-only: {payload}"
    )
    assert warnings[0].get("severity") == "warning", (
        f"Secondary linter warnings must stay warning-only: {payload}"
    )
    assert warnings[0].get("source_prefix") == MAKE_DESIGNER_WARNING_PREFIX, (
        f"Designer warning prefix was not preserved: {payload}"
    )


def test_secondary_linter_is_unavailable_when_api_evidence_is_absent() -> None:
    """The generation gate reports absent API evidence instead of a clean.

    linter.

    pass.
    """
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "secondary-linter-unavailable",
                    "flow": [
                        {"id": 1, "module": "unknown-service:MissingAction"}
                    ],
                }
            )
        ),
        catalog=empty_catalog_snapshot(),
    )

    assert result.status == "blocked", (
        f"Offline blocker should remain active: {result}"
    )
    secondary_linter = result.secondary_linter
    assert secondary_linter is not None, (
        f"Generation gate did not return a secondary linter result: {result}"
    )
    payload = secondary_linter.to_json()
    assert payload.get("status") == "secondary_linter_unavailable", (
        f"Missing API evidence should be explicit: {payload}"
    )
    assert payload.get("warnings") == [], (
        f"Unavailable secondary linter must not invent warnings: {payload}"
    )
    assert_confidence_weight(payload, 0.0)


def empty_catalog_snapshot() -> CatalogSnapshot:
    """Return a catalog with no modules so the offline gate must block."""
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-06T00:00:00Z",
        raw_spec_manifest_sha256="0" * 64,
        apps=(),
        fingerprint="0" * 64,
    )


def designer_warning_knowledge() -> KnowledgeStoreQuery:
    """Return reviewed designer-message evidence for the synthetic unresolved.

    node.
    """
    return KnowledgeStoreQuery(
        fingerprint="knowledge:secondary-linter",
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        designer_messages=(
            KnowledgeDesignerMessageEvidence(
                finding_id="designer-message-secondary-linter",
                node_id="1",
                module_slug="unknown-service:MissingAction",
                severity="warning",
                message="The selected module still needs Make designer review.",
                category="mapping",
                field_path="parameters.url",
                review_status="reviewed",
                source_kind="designer_message",
                source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
                fingerprint="designer-message-secondary-linter",
                adr_anchor="001066#repo.make-linter.documented-designer-message-signal",
            ),
        ),
    )


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
