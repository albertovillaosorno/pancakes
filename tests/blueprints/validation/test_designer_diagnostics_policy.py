# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Designer diagnostics policy tests for strict importability handoff.

Boundary contract:
- Owns: focused assertions that designer polish diagnostics stay advisory.
- Must not: call Make.com, refresh catalogs, render PDFs, or claim live
verification.
- Allows: sanitized importability fixtures, strict gate checks, and manifest
surfacing.
- Split when: visual presentation or live Make roundtrip owns its own evidence.
- Merge when: another validation test owns this exact advisory diagnostics
policy.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.ast.layout_analysis import (
    analyze_blueprint_designer_diagnostics,
)
from blueprints.validation import (
    build_handoff_placeholder_manifest,
    validate_blueprint,
)
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from blueprints.validation.handoff_manifest import (
    HandoffEvidenceSource,
    build_handoff_readiness_manifest,
    with_handoff_secondary_diagnostics,
)
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast import MakeAstRoot

REPO_ROOT = repo_root()
FIXTURE_ROOT = REPO_ROOT / "tests" / "blueprints" / "fixtures" / "importability"
ADVISORY_ONLY_FIXTURE = FIXTURE_ROOT / "advisory_designer_warning_only.json"
EXPECTED_ADVISORY_CODES = {
    "designer.branch_crowded",
    "designer.coordinates_overlap",
    "designer.label_missing",
    "designer.module_note_missing",
}


def test_designer_advisory_does_not_block_strict_importability() -> None:
    """Designer polish warnings do not become strict importability blockers."""
    catalog = native_module_snapshot()
    root = parse_fixture(ADVISORY_ONLY_FIXTURE)

    report = validate_blueprint(root=root, catalog=catalog)
    gate = guard_blueprint_for_handoff(root=root, catalog=catalog)
    diagnostics = analyze_blueprint_designer_diagnostics(root)

    assert not (report.has_errors), (
        f"Advisory fixture produced validation errors: {report.findings}"
    )
    assert gate.status == "allowed", (
        f"Strict handoff gate blocked advisory-only diagnostics: {gate}"
    )
    assert gate.importable, (
        f"Strict handoff gate blocked advisory-only diagnostics: {gate}"
    )
    assert not (gate.blockers), (
        f"Designer advisories must not appear as blockers: {gate.blockers}"
    )
    assert {
        diagnostic.code for diagnostic in diagnostics
    } == EXPECTED_ADVISORY_CODES, (
        f"Designer advisory codes drifted: {diagnostics}"
    )
    assert not (
        any(diagnostic.severity != "warning" for diagnostic in diagnostics)
    ), f"Designer diagnostics must stay warning-only: {diagnostics}"


def test_designer_advisory_is_visible_in_handoff_manifest() -> None:
    """Handoff readiness output can surface advisory designer diagnostics."""
    catalog = native_module_snapshot()
    root = parse_fixture(ADVISORY_ONLY_FIXTURE)
    gate = guard_blueprint_for_handoff(root=root, catalog=catalog)
    diagnostics = analyze_blueprint_designer_diagnostics(root)

    manifest = with_handoff_secondary_diagnostics(
        manifest=build_handoff_readiness_manifest(
            report=gate.validation_report,
            placeholders=build_handoff_placeholder_manifest(
                root=root, catalog=catalog
            ),
            importable=gate.importable,
            live_make_called=False,
            evidence_sources=(
                HandoffEvidenceSource(
                    source_id="offline-designer-diagnostics",
                    label="Offline designer diagnostics",
                    detail=(
                        "Static AST layout analysis only; no live Make call was"
                        "made."
                    ),
                ),
            ),
        ),
        secondary_diagnostics=diagnostics,
    )

    assert manifest.importability_status == "importable_candidate", (
        f"Manifest must keep advisory diagnostics nonblocking: {manifest}"
    )
    assert not (manifest.blockers), (
        f"Manifest must keep advisory diagnostics nonblocking: {manifest}"
    )
    manifest_codes = {
        diagnostic.code for diagnostic in manifest.secondary_diagnostics
    }
    assert manifest_codes == EXPECTED_ADVISORY_CODES, (
        f"Manifest lost designer advisory diagnostics: {manifest}"
    )
    assert {
        diagnostic.diagnostic_source
        for diagnostic in manifest.secondary_diagnostics
    } == {"designer_layout_analysis"}, (
        f"Manifest did not preserve diagnostic source: {manifest}"
    )


def test_blocking_layout_error_still_blocks_when_coordinates_are_invalid() -> (
    None
):
    """Malformed designer coordinates remain strict importability blockers."""
    payload = load_fixture(ADVISORY_ONLY_FIXTURE)
    flow = object_list(payload, "flow")
    metadata = object_member(flow[0], "metadata")
    designer = object_member(metadata, "designer")
    designer["x"] = "left"

    gate = guard_blueprint_for_handoff(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )

    assert not (
        "ast.designer_coordinates_invalid" not in gate.validation_report.codes()
    ), f"Invalid designer coordinates were not reported: {gate}"
    assert gate.status == "blocked", (
        f"Strict handoff must block malformed coordinates: {gate}"
    )
    assert not (gate.importable), (
        f"Strict handoff must block malformed coordinates: {gate}"
    )
    assert not (
        "ast.designer_coordinates_invalid"
        not in {blocker.code for blocker in gate.blockers}
    ), f"Coordinate error was not surfaced as a blocker: {gate.blockers}"


def test_structured_designer_label_still_reports_missing_label() -> None:
    """Structured label payloads are not explicit human-authored labels."""
    payload = load_fixture(ADVISORY_ONLY_FIXTURE)
    flow = object_list(payload, "flow")
    flow[0]["label"] = {"text": "Looks labeled"}

    diagnostics = analyze_blueprint_designer_diagnostics(
        parse_make_ast_json_text(json.dumps(payload, sort_keys=True))
    )
    label_diagnostics = tuple(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.code == "designer.label_missing"
        and diagnostic.node_id == "1"
    )

    assert label_diagnostics, (
        f"Structured designer label was treated as explicit text: {diagnostics}"
    )


def parse_fixture(path: Path) -> MakeAstRoot:
    """Parse one JSON fixture into a typed Make AST root.

    Returns:
        The parsed Make AST root.
    """
    return parse_make_ast_json_text(
        json.dumps(load_fixture(path), sort_keys=True)
    )


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded fixture object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    """Return a list of JSON object members."""
    value = payload.get(key)
    assert isinstance(value, list), f"{key} must be a list."
    objects: list[JsonObject] = []
    for item in cast("list[object]", value):
        assert isinstance(item, dict), f"{key} must contain objects."
        objects.append(cast("JsonObject", item))
    return objects


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return a JSON object member."""
    value = payload.get(key)
    assert isinstance(value, dict), f"{key} must be an object."
    return cast("JsonObject", value)
