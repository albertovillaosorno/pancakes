# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Integration tests for rendering plus importability validation composition.

Boundary contract:
- Owns: composed render-and-validate behavior over existing AST and validation
APIs.
- Must not: test live Make imports, renderer internals, or individual validation
rules.
- Allows: sanitized inline payloads and catalog-backed offline integration
assertions.
- Split when: MCP or handoff flows need caller-specific composition tests.
- Merge when: a broader integration contract owns this exact render preflight
flow.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from languages.make.blueprint_export import render_make_blueprint_payload
from languages.make.render_validation import render_and_validate_blueprint

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.ast import JsonObject
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
HTTP_REQUEST_MODULE = "http:" + "MakeRequest"


def test_render_and_validate_returns_payload_422afd9c() -> None:
    """Strict composition returns rendered payload and clean importability.

    state.
    """
    root = parse_make_ast_json_text(json.dumps(valid_http_payload()))
    result = render_and_validate_blueprint(
        root=root, catalog=load_catalog_fixture()
    )

    assert result.importable, f"Valid fixture should be importable: {result}"
    assert not (result.generation_gate.blockers), (
        f"Valid fixture produced blockers: {result.generation_gate.blockers}"
    )
    assert not (result.diagnostics), (
        f"Valid fixture produced render diagnostics: {result.diagnostics}"
    )
    assert result.artifact_phase == "compiled_blueprint", (
        f"Unexpected rendered artifact phase: {result.artifact_phase}"
    )
    assert result.rendered_payload.get("name") == "valid-render-composition", (
        f"Rendered payload is missing scenario identity: "
        f"{result.rendered_payload}"
    )


def test_render_and_validate_returns_payload_e9711bd6() -> None:
    """Draft composition returns payload plus blockers for invalid topology."""
    root = parse_make_ast_json_text(
        json.dumps(invalid_router_topology_payload())
    )
    result = render_and_validate_blueprint(
        root=root,
        catalog=load_catalog_fixture(),
        mode="draft",
    )

    assert not (result.importable), (
        f"Invalid draft fixture must not be importable: {result}"
    )
    assert result.rendered_payload.get("flow"), (
        f"Draft composition did not return a rendered payload: {result}"
    )
    blocker_codes = tuple(
        blocker.code for blocker in result.generation_gate.blockers
    )
    assert not ("generation.validation_failed" not in blocker_codes), (
        f"Invalid topology did not produce validation blockers: {blocker_codes}"
    )
    diagnostic_codes = tuple(
        diagnostic.code for diagnostic in result.diagnostics
    )
    assert not ("router.routes_missing" not in diagnostic_codes), (
        f"Invalid topology did not expose render diagnostics: "
        f"{diagnostic_codes}"
    )


def test_renderer_output_is_unchanged_by_validation_composition() -> None:
    """Validation composition returns the same payload as the focused.

    renderer.
    """
    root = parse_make_ast_json_text(json.dumps(valid_http_payload()))
    catalog = load_catalog_fixture()
    renderer_result = render_make_blueprint_payload(root=root, catalog=catalog)
    composition_result = render_and_validate_blueprint(
        root=root, catalog=catalog
    )

    if composition_result.rendered_payload != renderer_result.payload:
        message = (
            f"Render-and-validate composition changed renderer output: "
            f"{composition_result.rendered_payload}"
        )
        assert composition_result.rendered_payload == renderer_result.payload, (
            message
        )


def valid_http_payload() -> JsonObject:
    """Return a sanitized catalog-backed importable HTTP payload."""
    return {
        "name": "valid-render-composition",
        "flow": [
            {
                "id": 1,
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:http:1.0:action:makeRequest"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "1" * 64,
                        "status": "resolved",
                    }
                },
                "module": HTTP_REQUEST_MODULE,
                "parameters": {
                    "method": "POST",
                    "url": "https://example.invalid",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def invalid_router_topology_payload() -> JsonObject:
    """Return a sanitized payload with a router missing route fanout."""
    return {
        "name": "invalid-render-composition",
        "flow": [{"id": 1, "module": "builtin:BasicRouter"}],
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
