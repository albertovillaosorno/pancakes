# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make AST compiler phase gates.

Boundary contract:
- Owns: focused tests for parser, compiler, and renderer phase-gate diagnostics.
- Must not: duplicate validator rule behavior or assert fragile English text.
- Allows: catalog-backed sanitized payloads and stable phase/path assertions.
- Split when: phase gate result models become a public API contract.
- Merge when: another AST test owns the same phase-transition diagnostics.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.ast.compilation import (
    BlueprintCompileRequest,
    compile_blueprint_from_module_ids,
)
from blueprints.ast.phase_gates import (
    BlueprintPhaseGateError,
    parse_blueprint_phase,
)
from blueprints.validation.importability import (
    IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
)
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from languages.make.blueprint_export import (
    MakeBlueprintRenderError,
    render_make_blueprint_payload,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogSnapshot

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)


def test_parse_phase_reports_parser_errors_without_rendering() -> None:
    """Malformed source JSON is reported as a parse-phase gate failure."""
    with pytest.raises(BlueprintPhaseGateError) as error:
        _ = parse_blueprint_phase(
            '{"name": "broken",',
            blueprint_path=("data", "golden", "broken.json"),
        )

    diagnostic = error.value.diagnostics[0]

    assert error.value.phase == "parse", (
        f"Parser failure did not expose the parse phase: {error.value.phase!r}"
    )
    assert diagnostic.code == "phase.parse_error", (
        f"Parser failure used an unstable diagnostic code: {diagnostic.code!r}"
    )
    assert diagnostic.blueprint_path == ("data", "golden", "broken.json"), (
        f"Parser failure lost the source path: {diagnostic.blueprint_path!r}"
    )


def test_render_phase_runs_importability_gate_before_handoff() -> None:
    """Importable rendering fails on validator errors before emitting a handoff.

    payload.
    """
    root = parse_make_ast_json_text(
        json.dumps(importable_payload_with_placeholder())
    )

    with pytest.raises(MakeBlueprintRenderError) as error:
        _ = render_make_blueprint_payload(
            root=root, catalog=load_catalog_fixture()
        )

    assert error.value.phase == "render", (
        f"Render failure did not expose the render phase: {error.value.phase!r}"
    )
    diagnostic_codes = tuple(
        diagnostic.code for diagnostic in error.value.diagnostics
    )
    assert not (IMPORTABILITY_PLACEHOLDER_UNRESOLVED not in diagnostic_codes), (
        f"Render gate did not reuse validator findings: {diagnostic_codes!r}"
    )


def test_phase_gate_error_includes_phase_name_and_blueprint_path() -> None:
    """Phase gate errors include the phase and actionable blueprint JSON.

    path.
    """
    root = parse_make_ast_json_text(
        json.dumps(importable_payload_with_placeholder())
    )

    with pytest.raises(MakeBlueprintRenderError) as error:
        _ = render_make_blueprint_payload(
            root=root, catalog=load_catalog_fixture()
        )

    message = str(error.value)

    assert not ("render" not in message), (
        f"Phase gate error message omitted the phase name: {message!r}"
    )
    assert not ("$.flow[0].parameters.url" not in message), (
        f"Phase gate error message omitted the blueprint path: {message!r}"
    )


def test_compile_phase_preserves_existing_scenario_metadata() -> None:
    """Compile requests preserve existing scenario audit metadata."""
    compiled = compile_blueprint_from_module_ids(
        request=BlueprintCompileRequest(
            name="compiled-audit-metadata",
            goal="Keep inventory evidence visible.",
            module_ids=("module:http:1.0:action:makeRequest",),
            metadata={
                "scenario": {
                    "catalog_or_ast_fingerprint": "fixture-fingerprint"
                }
            },
        ),
        catalog=load_catalog_fixture(),
    )
    scenario = compiled.root.scenario.metadata.get("scenario")

    assert isinstance(scenario, dict), (
        f"Compiled scenario metadata must remain an object: {scenario!r}"
    )
    scenario_mapping = cast("Mapping[str, object]", scenario)
    assert (
        scenario_mapping.get("catalog_or_ast_fingerprint")
        == "fixture-fingerprint"
    ), f"Compile request lost scenario audit metadata: {scenario!r}"
    assert scenario_mapping.get("goal") == "Keep inventory evidence visible.", (
        f"Compile request lost canonical scenario metadata: {scenario!r}"
    )


def importable_payload_with_placeholder() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "name": "placeholder-blocked",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "parameters": {
                    "method": "POST ",
                    "url": "{{TODO:client-webhook-url}}",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample Make catalog fixture.

    Returns:
        The loaded catalog snapshot.
    """
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )
