# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Validation tests for the sanitized lead-routing demo fixtures.

Boundary contract:
- Owns: tests for the lead-routing demo fixture and publication blockers.
- Must not: validate unrelated blueprints or repository tool policy.
- Allows: lead-routing fixture data, catalog lookups, and validation blockers.
- Split when: fixture loading and validation behavior need separate modules.
- Merge when: another lead-routing fixture test covers the same scenario.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from blueprints.ast import (
    iter_ast_nodes,
    parse_make_ast_json_text,
    require_module_resolution,
    resolve_ast_modules,
)
from blueprints.validation import guard_blueprint_for_render, validate_blueprint
from catalog import catalog_snapshot_from_json, compile_catalog_from_manifest
from catalog.json_payloads import normalize_json_object
from languages.make.raw_specs import load_raw_spec_manifest

from tests.catalog.fixtures.raw_spec_manifest import (
    materialize_minimal_raw_spec_manifest_fixture,
)
from tests.support.json_payloads import json_object_from_path
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog import CatalogSnapshot

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
DEMO_FIXTURE_DIR = (
    REPO_ROOT / "tests" / "blueprints" / "fixtures" / "lead_routing_demo"
)
AST_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "make_ast"
    / "lead_routing_blueprint.json"
)
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
SECRET_PATTERN = re.compile(
    r"(api[_ -]?key|secret|token|account[_ -]?id|https://hooks\.make\.com)",
    re.IGNORECASE,
)
FORBIDDEN_PUBLIC_WORDS = ("product", "template", "client system")
DATASTORE_ADD_RECORD_MODULE_ID = "module:datastore:2.0.5:action:AddRecord"
DATASTORE_ADD_RECORD_MODULE_SLUG = "datastore:AddRecord"
EXPECTED_DATASTORE_NODE_COUNT = 2


def test_scenario_plan_defines_required_lead_routing_workflow() -> None:
    """Scenario plan covers the required lead-routing demo flow."""
    plan = load_json_fixture("scenario_plan.json")
    intake = object_member(plan, "intake")
    required_fields = string_list(intake, "required_fields")
    missing_fields = {"email", "company", "source"} - set(required_fields)
    assert not (missing_fields), (
        f"Scenario plan is missing required fields: {missing_fields}"
    )
    assert string_member(intake, "kind") == "webhook_or_form", (
        f"Scenario must intake by webhook/form: {intake}"
    )

    routes = {
        string_member(route, "route_id"): route
        for route in object_list(plan, "routes")
    }
    assert set(routes) == {"qualified", "incomplete"}, (
        f"Scenario must define qualified and incomplete routes: {routes}"
    )
    for route in routes.values():
        destination = string_member(route, "destination")
        notification = string_member(route, "notification")
        assert destination.startswith("demo_datastore_"), (
            f"Route must target a fake Data Store demo destination: {route}"
        )
        assert notification.startswith("demo_"), (
            f"Route must define a demo notification target: {route}"
        )
        assert not ("notification" not in notification), (
            f"Route must define a demo notification target: {route}"
        )


def test_lead_routing_demo_uses_fake_data_only() -> None:
    """Demo fixtures contain fake data and no credential-like strings."""
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(DEMO_FIXTURE_DIR.glob("*.json"))
    )
    assert not (SECRET_PATTERN.search(fixture_text)), (
        "Lead-routing demo fixtures expose credential-like text."
    )

    input_payload = load_json_fixture("input_leads.json")
    leads = object_list(input_payload, "leads")
    for lead in leads:
        email = string_member(lead, "email")
        if email:
            assert email.endswith("@example.invalid"), (
                f"Lead fixture must use example.invalid email: {lead}"
            )


def test_expected_outputs_cover_each_fake_input_lead() -> None:
    """Expected route outputs cover every fake input lead exactly once."""
    leads = object_list(load_json_fixture("input_leads.json"), "leads")
    outputs = [
        *object_list(load_json_fixture("expected_outputs.json"), "qualified"),
        *object_list(load_json_fixture("expected_outputs.json"), "incomplete"),
    ]
    lead_ids = {string_member(lead, "lead_id") for lead in leads}
    output_ids = {string_member(output, "lead_id") for output in outputs}

    assert lead_ids == output_ids, (
        f"Expected outputs must match fake inputs: {lead_ids} != {output_ids}"
    )
    assert len(outputs) == len(output_ids), (
        f"Each fake lead must have exactly one expected route: {outputs}"
    )


def test_public_scenario_details_are_portfolio_demo_only() -> None:
    """Public scenario fields stay sanitized and non-commercial."""
    details = load_json_fixture("public_scenario_details.json")
    combined = " ".join(
        string_member(details, key)
        for key in ("title", "description", "additional_info")
    )
    lowered = combined.casefold()

    assert not ("portfolio demo" not in lowered), (
        f"Public details must identify a portfolio demo: {details}"
    )
    for forbidden in FORBIDDEN_PUBLIC_WORDS:
        assert forbidden not in lowered, (
            f"Public details must not claim {forbidden!r}: {details}"
        )
    assert details.get("publication_status") == "draft_not_publishable", (
        f"Demo must stay draft until validation passes: {details}"
    )


def test_lead_routing_demo_ast_uses_datastore_mvp_modules(
    tmp_path: Path,
) -> None:
    """AST fixture routes lead records into catalog-backed modules."""
    root = parse_make_ast_json_text(AST_FIXTURE.read_text(encoding="utf-8"))
    datastore_nodes = tuple(
        node
        for node in iter_ast_nodes(root)
        if node.module_token == DATASTORE_ADD_RECORD_MODULE_SLUG
    )
    assert len(datastore_nodes) == EXPECTED_DATASTORE_NODE_COUNT, (
        f"Routes must use Data Store add modules: {datastore_nodes}"
    )
    destinations: set[str] = set()
    for node in datastore_nodes:
        parameters = object_member(node.raw_payload, "parameters")
        destinations.add(string_member(parameters, "datastore"))
        assert (
            node.raw_spec_binding.catalog_module_id
            == DATASTORE_ADD_RECORD_MODULE_ID
        ), f"Data Store binding drifted: {node.raw_spec_binding}"
    assert destinations == {
        "demo_datastore_qualified_leads",
        "demo_datastore_review_queue",
    }, f"Destinations drifted: {destinations}"

    resolution_report = resolve_ast_modules(
        root=root,
        catalog=load_catalog_with_datastore_fixture(tmp_path),
    )
    for node_id in ("4", "12"):
        resolution = require_module_resolution(resolution_report, node_id)
        assert resolution.status == "resolved", (
            f"Data Store node unresolved: {resolution}"
        )
        assert resolution.catalog_module_id == DATASTORE_ADD_RECORD_MODULE_ID, (
            f"Data Store node unresolved: {resolution}"
        )

    fixture_text = "\n".join(
        [
            AST_FIXTURE.read_text(encoding="utf-8"),
            *(
                path.read_text(encoding="utf-8")
                for path in sorted(DEMO_FIXTURE_DIR.glob("*.json"))
            ),
        ]
    ).casefold()
    assert "google sheets" not in fixture_text, (
        "Data Store MVP fixtures must not depend on Google Sheets."
    )
    assert "google-sheets" not in fixture_text, (
        "Data Store MVP fixtures must not depend on Google Sheets."
    )


def test_lead_routing_demo_validation_blocks_32c18769() -> None:
    """Draft scenario stays blocked until catalog coverage exists."""
    root = parse_make_ast_json_text(AST_FIXTURE.read_text(encoding="utf-8"))
    catalog = load_catalog_fixture()
    report = validate_blueprint(root=root, catalog=catalog)
    gate = guard_blueprint_for_render(root=root, catalog=catalog)
    asset_plan = load_json_fixture("asset_plan.json")

    assert report.findings, (
        "Demo validation should produce evidence before publication."
    )
    assert not (gate.can_render), (
        "Demo should not be importable until all modules are catalog-backed."
    )
    assert not ("module.unresolved" not in report.codes()), (
        f"Expected catalog blockers for draft demo: {report.codes()}"
    )
    public_link = next(
        asset
        for asset in object_list(asset_plan, "assets")
        if asset.get("asset_id") == "public_scenario_link"
    )
    assert public_link.get("status") == "blocked_until_validation_passes", (
        f"Public link must remain blocked: {public_link}"
    )


def load_json_fixture(name: str) -> JsonObject:
    """Load one lead-routing demo JSON fixture.

    Returns:
        The loaded value.
    """
    return json_object_from_path(DEMO_FIXTURE_DIR / name, name)


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

    Returns:
        The loaded value.
    """
    return catalog_snapshot_from_json(json_object_from_path(CATALOG_FIXTURE))


def load_catalog_with_datastore_fixture(
    raw_spec_repo_root: Path,
) -> CatalogSnapshot:
    """Load the sample catalog plus the raw-spec-backed Data Store add module.

    Returns:
        The augmented catalog snapshot for the Data Store MVP fixture test.
    """
    base_catalog = load_catalog_fixture()
    fixture = materialize_minimal_raw_spec_manifest_fixture(raw_spec_repo_root)
    manifest = load_raw_spec_manifest(fixture.manifest_path)
    datastore_catalog = compile_catalog_from_manifest(
        repo_root=fixture.repo_root,
        manifest=manifest,
    )
    return base_catalog._replace(
        apps=tuple(
            sorted(
                (*base_catalog.apps, *datastore_catalog.apps),
                key=lambda app: app.app_id,
            )
        ),
    )


def object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    """Return a list of objects from a fixture."""
    value = payload.get(key)
    assert isinstance(value, list), f"{key} must be a list."
    objects: list[JsonObject] = []
    for item in cast("list[object]", value):
        assert isinstance(item, dict), f"{key} must contain objects."
        objects.append(
            normalize_json_object(cast("Mapping[str, object]", item))
        )
    return objects


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return an object member from a fixture object."""
    value = payload.get(key)
    assert isinstance(value, dict), f"{key} must be an object."
    return normalize_json_object(cast("Mapping[str, object]", value))


def string_list(payload: JsonObject, key: str) -> list[str]:
    """Return a list of strings from a fixture object."""
    value = payload.get(key)
    assert isinstance(value, list), f"{key} must be a list."
    strings: list[str] = []
    for item in cast("list[object]", value):
        assert isinstance(item, str), f"{key} must contain strings."
        strings.append(item)
    return strings


def string_member(payload: JsonObject, key: str) -> str:
    """Return a string member from a fixture object."""
    value = payload.get(key)
    assert isinstance(value, str), f"{key} must be a string."
    return value
