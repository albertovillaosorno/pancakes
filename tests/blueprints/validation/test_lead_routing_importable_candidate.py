# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Validation tests for the lead-routing importable candidate fixture.

Boundary contract:
- Owns: strict offline importability assertions for the lead-routing candidate.
- Must not: call Make.com, mutate project assets, or claim live verification.
- Allows: sanitized fixture loading, router topology checks, and handoff
placeholders.
- Split when: project asset cleanup or live roundtrip evidence needs separate
tests.
- Merge when: another validation test owns this exact candidate fixture
behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import (
    build_handoff_placeholder_manifest,
    validate_blueprint,
)
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast import MakeAstRoot

REPO_ROOT = repo_root()
FIXTURE_ROOT = REPO_ROOT / "tests" / "blueprints" / "fixtures" / "importability"
IMPORTABLE_CANDIDATE = (
    FIXTURE_ROOT / "valid_lead_routing_importable_candidate.json"
)
SOURCE_PROJECT_ASSET = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "portfolio_projects"
    / "lead-routing-data-store-mvp"
    / "scenario.json"
)
EXPECTED_PLACEHOLDER_PATHS = {
    "runtime_datastore_incomplete_leads": (
        "/flow/1/routes/1/flow/0/parameters/datastore"
    ),
    "runtime_datastore_qualified_leads": (
        "/flow/1/routes/0/flow/0/parameters/datastore"
    ),
    "runtime_webhook_lead_intake_hook": "/flow/0/parameters/hook",
}


def test_lead_routing_importable_candidate_passes_5a965609() -> None:
    """The sanitized lead-routing candidate passes the strict offline handoff.

    gate.
    """
    root = parse_fixture(IMPORTABLE_CANDIDATE)
    report = validate_blueprint(root=root, catalog=native_module_snapshot())
    gate = guard_blueprint_for_handoff(
        root=root, catalog=native_module_snapshot()
    )

    assert not (report.has_errors), (
        f"Importable candidate produced validation errors: {report.findings}"
    )
    assert gate.status == "allowed", (
        f"Strict handoff gate did not accept the candidate: {gate}"
    )
    assert gate.importable, (
        f"Strict handoff gate did not accept the candidate: {gate}"
    )


def test_lead_routing_candidate_has_router_between_webhook_and_branches() -> (
    None
):
    """The candidate uses webhook -> router -> route branch flow ownership."""
    payload = load_fixture(IMPORTABLE_CANDIDATE)
    flow = object_list(payload, "flow")

    assert module_token(flow[0]) == "gateway:CustomWebHook", (
        f"Lead intake must start with the webhook trigger: {flow[0]}"
    )
    assert "routes" not in flow[0], (
        f"Webhook must not own route branches directly: {flow[0]}"
    )
    router = flow[1]
    assert module_token(router) == "builtin:BasicRouter", (
        f"Second node must be the route owner: {router}"
    )

    routes = object_list(router, "routes")
    route_names = {
        string_member(object_member(route, "filter"), "name")
        for route in routes
    }
    assert route_names == {"Qualified", "Incomplete"}, (
        f"Lead-routing candidate routes drifted: {route_names}"
    )
    for route in routes:
        route_flow = object_list(route, "flow")
        assert len(route_flow) == 1, (
            f"Each route must write exactly one Data Store record: {route}"
        )
        assert module_token(route_flow[0]) == "datastore:AddRecord", (
            f"Each route must write exactly one Data Store record: {route}"
        )


def test_lead_routing_candidate_lists_runtime_placeholders_for_handoff() -> (
    None
):
    """Runtime setup placeholders from the fixture registry reach handoff.

    output.
    """
    manifest = build_handoff_placeholder_manifest(
        root=parse_fixture(IMPORTABLE_CANDIDATE),
        catalog=native_module_snapshot(),
    )
    by_key = {placeholder.key: placeholder for placeholder in manifest}

    assert set(by_key) == set(EXPECTED_PLACEHOLDER_PATHS), (
        f"Unexpected handoff placeholder keys: {manifest}"
    )
    for key, expected_path in EXPECTED_PLACEHOLDER_PATHS.items():
        placeholder = by_key[key]
        paths = tuple(
            path.json_pointer for path in placeholder.replacement_paths
        )
        assert paths == (expected_path,), (
            f"Placeholder path drifted for {key}: {placeholder}"
        )
        assert placeholder.required, (
            f"Runtime setup placeholder must be required in Make: {placeholder}"
        )
        assert placeholder.bind_in_make, (
            f"Runtime setup placeholder must be required in Make: {placeholder}"
        )
        assert not ("{{runtime." not in str(placeholder.seed_value)), (
            f"Placeholder seed must not imply credentials are present: "
            f"{placeholder}"
        )


def test_source_project_asset_is_not_436d10ff() -> None:
    """The source project asset stays blocked until a dedicated cleanup TODO.

    updates it.
    """
    root = parse_fixture(SOURCE_PROJECT_ASSET)
    gate = guard_blueprint_for_handoff(
        root=root, catalog=native_module_snapshot()
    )
    codes = gate.validation_report.codes()

    assert gate.status == "blocked", (
        f"Source project asset must not be claimed importable: {gate}"
    )
    assert not (gate.importable), (
        f"Source project asset must not be claimed importable: {gate}"
    )
    expected_blockers = {
        "route.routes_on_non_router",
        "importability.placeholder_registry_incomplete",
        "importability.placeholder_unregistered",
    }
    assert expected_blockers.intersection(codes), (
        f"Source asset lost its expected cleanup blockers: {codes}"
    )


def parse_fixture(path: Path) -> MakeAstRoot:
    """Parse one JSON fixture into the Make AST.

    Returns:
        The parsed Make AST root.
    """
    return parse_make_ast_json_text(
        json.dumps(load_fixture(path), sort_keys=True)
    )


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    """Return a list of JSON objects from a fixture object."""
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
    """Return a JSON object member."""
    value = payload.get(key)
    assert isinstance(value, dict), f"{key} must be an object."
    return normalize_json_object(cast("Mapping[str, object]", value))


def string_member(payload: JsonObject, key: str) -> str:
    """Return a string member."""
    value = payload.get(key)
    assert isinstance(value, str), f"{key} must be a string."
    return value


def module_token(payload: JsonObject) -> str:
    """Return a fixture node module token."""
    return string_member(payload, "module")
