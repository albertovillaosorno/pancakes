# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for repository artifact phase boundaries.

Boundary contract:
- Owns: classification tests for source drafts versus importable/live claims.
- Must not: test renderer payloads, live Make imports, or migration workspace
  behavior.
- Allows: offline project assets and explicit artifact phase metadata
  assertions.
- Split when: artifact phase policy grows beyond source/importable/live
  boundaries.
- Merge when: another validation test duplicates the same phase claim contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast.artifacts import (
    assess_blueprint_artifact_phase_claim,
    classify_blueprint_artifact_phase,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast.models import JsonObject


PROJECT_SOURCE_DRAFT = (
    repo_root()
    / "tests"
    / "blueprints"
    / "fixtures"
    / "portfolio_projects"
    / "lead-routing-data-store-mvp"
    / "scenario.json"
)


def test_source_draft_is_not_reported_as_live_importable() -> None:
    """A project source draft cannot be an importable candidate."""
    payload = _load_json_object(PROJECT_SOURCE_DRAFT)

    assessment = assess_blueprint_artifact_phase_claim(
        payload=payload,
        claimed_phase="importable_candidate",
    )

    assert assessment.artifact_phase == "source_draft", (
        f"Project asset was not classified as a source draft: {assessment}"
    )
    assert not (assessment.claim_allowed), (
        f"Source draft claim was allowed as importable: {assessment}"
    )
    assert assessment.diagnostic is not None, (
        "Blocked source draft importable claim did not include a diagnostic."
    )
    assert assessment.diagnostic.get("artifact_phase") == "source_draft", (
        f"Diagnostic did not expose artifact phase: {assessment.diagnostic}"
    )


def test_importable_candidate_can_be_distinguished_from_source_draft() -> None:
    """Importable candidate metadata must not look like source state."""
    payload: JsonObject = {
        "name": "importable candidate",
        "flow": [],
        "metadata": {
            "artifact_phase": "importable_candidate",
            "schedule": {"id": "schedule:manual"},
        },
    }

    assert (
        classify_blueprint_artifact_phase(payload) == "importable_candidate"
    ), "Explicit importable candidate metadata was not classified."

    assessment = assess_blueprint_artifact_phase_claim(
        payload=payload,
        claimed_phase="importable_candidate",
    )

    assert assessment.claim_allowed, (
        f"Importable candidate claim was blocked: {assessment}"
    )
    assert not (assessment.diagnostic is not None), (
        "Allowed importable candidate claim produced a diagnostic: "
        f"{assessment}"
    )


def _load_json_object(path: Path) -> JsonObject:
    """Load a JSON object fixture.

    Returns:
        The loaded JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return cast("JsonObject", cast("Mapping[str, object]", payload))
