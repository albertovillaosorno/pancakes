# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Router topology repair diagnostics tests.

Boundary contract:
- Owns: explicit offline repair guidance for non-router-owned route branches.
- Must not: apply hidden blueprint mutation, call live services, or test
renderer output.
- Allows: sanitized fixtures, validation findings, and repair candidate
assertions.
- Split when: explicit mutating repair application is implemented as a separate
workflow.
- Merge when: repair diagnostics own all router topology candidate coverage
directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.repair import (
    propose_repair_candidates,
    repair_blueprint_offline,
)
from blueprints.validation import validate_blueprint
from blueprints.validation.findings import ROUTES_ON_NON_ROUTER_CODE
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.repair import RepairCandidate
    from blueprints.validation import BlueprintValidationReport

FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE = (
    FIXTURE_ROOT / "invalid_webhook_owned_routes.json"
)


def test_router_topology_repair_candidate_proposes_basic_router_insertion() -> (
    None
):
    """Non-router route ownership produces explicit BasicRouter repair.

    guidance.
    """
    candidate = require_candidate(
        validate_fixture(INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE),
        ROUTES_ON_NON_ROUTER_CODE,
    )

    assert candidate.category == "incomplete_execution_risk", (
        f"Router topology should be incomplete execution risk: {candidate}"
    )
    assert not ("BasicRouter" not in candidate.client_explanation), (
        f"Router topology guidance must name BasicRouter: {candidate}"
    )
    assert any(
        "Branch filters and flow payloads are preserved" in item
        for item in candidate.preconditions
    ), f"Router topology guidance must preserve branch payloads: {candidate}"


def test_router_topology_repair_candidate_is_explicit_and_non_mutating() -> (
    None
):
    """Router topology repair guidance does not claim automatic mutation."""
    candidate = require_candidate(
        validate_fixture(INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE),
        ROUTES_ON_NON_ROUTER_CODE,
    )

    assert not (candidate.applies_automatically), (
        f"Router topology repair must remain explicit: {candidate}"
    )
    assert not (
        "No blueprint mutation is performed by diagnostics."
        not in candidate.rollback_notes
    ), f"Router topology repair needs diagnostic rollback notes: {candidate}"


def test_offline_repair_preserves_validation_blocker_cea314e5() -> None:
    """Offline repair reports the blocker without inserting a router during.

    validation.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            load_fixture(INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE), sort_keys=True
        )
    )
    outcome = repair_blueprint_offline(
        root=root, catalog=native_module_snapshot()
    )
    first_node = object_at(list_member(root.raw_payload, "flow"), 0)

    assert not (
        ROUTES_ON_NON_ROUTER_CODE not in outcome.validation_report.codes()
    ), f"Offline repair dropped the router topology blocker: {outcome}"
    assert outcome.status == "rejected_with_reasons", (
        f"Invalid router topology should remain rejected: {outcome}"
    )
    assert first_node.get("module") != "builtin:BasicRouter", (
        f"Offline repair silently rewrote the source AST: {root.raw_payload}"
    )
    assert not ("routes" not in first_node), (
        f"Offline repair removed the original misplaced routes: "
        f"{root.raw_payload}"
    )


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized router topology fixture.

    Returns:
        The validation report.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(load_fixture(path), sort_keys=True)
        ),
        catalog=native_module_snapshot(),
    )


def require_candidate(
    report: BlueprintValidationReport,
    source_code: str,
) -> RepairCandidate:
    """Return the repair candidate for one validation finding code.

    Returns:
        The matching repair candidate.
    """
    diagnostics = propose_repair_candidates(report)
    for candidate in diagnostics.candidates:
        if candidate.source_finding_code == source_code:
            return candidate
    failure_message = (
        f"Expected repair candidate for {source_code!r}: {diagnostics}"
    )
    assert_unexpected_success(failure_message)
    return None


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded fixture payload.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return a list member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_at(items: list[object], index: int) -> JsonObject:
    """Return one object item from a JSON list."""
    item = items[index]
    assert isinstance(item, dict), (
        f"Expected object list item at {index}: {items}"
    )
    return cast("JsonObject", item)
