# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Router topology importability tests.

Boundary contract:
- Owns: route-owner validation over sanitized router topology fixtures.
- Must not: repair scenarios, mutate project assets, or call live Make services.
- Allows: offline fixture parsing, route validator assertions, and validator
aggregation checks.
- Split when: automatic router insertion becomes an explicit repair workflow.
- Merge when: another test module owns these exact fixture-level topology
assertions.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, iter_ast_nodes, parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from blueprints.validation.findings import (
    MISSING_ROUTER_FANOUT_CODE,
    ROUTES_ON_NON_ROUTER_CODE,
)
from blueprints.validation.route_validation import (
    EVENT_TYPE_FALLBACK_MISSING_CODE,
    validate_routes,
)
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation.models import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
VALID_ROUTER_OWNED_ROUTES_FIXTURE = (
    FIXTURE_ROOT / "valid_router_owned_routes.json"
)
INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE = (
    FIXTURE_ROOT / "invalid_webhook_owned_routes.json"
)


def test_routes_owned_by_builtin_router_are_valid() -> None:
    """A webhook-to-BasicRouter topology keeps route ownership on the router.

    node.
    """
    root = load_ast_fixture(VALID_ROUTER_OWNED_ROUTES_FIXTURE)
    report = validate_ast(root)
    route_findings = validate_routes(tuple(iter_ast_nodes(root)))

    forbidden_codes = {ROUTES_ON_NON_ROUTER_CODE, MISSING_ROUTER_FANOUT_CODE}
    emitted_codes = {
        finding.code for finding in (*report.findings, *route_findings)
    }
    unexpected_codes = emitted_codes & forbidden_codes
    assert not (unexpected_codes), (
        f"Router-owned routes emitted topology findings: {unexpected_codes}"
    )


def test_routes_owned_by_webhook_report_non_router_route_owner() -> None:
    """Routes directly under a webhook emit the deterministic route-owner.

    blocker.
    """
    report = validate_ast(
        load_ast_fixture(INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE)
    )

    finding = require_finding(report, ROUTES_ON_NON_ROUTER_CODE)

    assert finding.severity == "error", (
        f"Webhook-owned routes must be blocking, got {finding.severity!r}"
    )


def test_router_topology_finding_points_to_offending_node_path() -> None:
    """The route-owner finding reports the offending webhook route container.

    path.
    """
    root = load_ast_fixture(INVALID_WEBHOOK_OWNED_ROUTES_FIXTURE)
    finding = require_route_finding(
        validate_routes(tuple(iter_ast_nodes(root))),
        ROUTES_ON_NON_ROUTER_CODE,
    )

    assert finding.node_id == "1", (
        f"Expected finding to attach to webhook node '1', got "
        f"{finding.node_id!r}"
    )
    assert finding.source_path == ("flow", 0, "routes"), (
        f"Expected offending route path, got {finding.source_path!r}"
    )


def test_webhook_event_type_router_warns_without_fallback() -> None:
    """Webhook-fed event-type routers warn when no fallback route is present."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "event-router-missing-fallback",
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "parameters": {},
                    },
                    {
                        "id": 2,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {
                                    "name": "Created",
                                    "conditions": {
                                        "expression": (
                                            "{{1.event_type}} = "
                                            '"invoice.created"'
                                        )
                                    },
                                },
                                "flow": [
                                    {"id": 3, "module": "datastore:AddRecord"}
                                ],
                            },
                            {
                                "filter": {
                                    "name": "Deleted",
                                    "conditions": {
                                        "expression": (
                                            "{{1.event_type}} = "
                                            '"invoice.deleted"'
                                        )
                                    },
                                },
                                "flow": [
                                    {"id": 4, "module": "datastore:AddRecord"}
                                ],
                            },
                        ],
                    },
                ],
                "metadata": {"schedule": {"id": "schedule:manual"}},
            }
        )
    )

    finding = require_route_finding(
        validate_routes(tuple(iter_ast_nodes(root))),
        EVENT_TYPE_FALLBACK_MISSING_CODE,
    )

    assert finding.severity == "warning", (
        f"Event-type fallback finding should warn, got {finding.severity!r}"
    )


def test_webhook_event_type_router_allows_unfiltered_fallback() -> None:
    """Webhook-fed event-type routers accept an unfiltered fallback route."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "event-router-with-fallback",
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "parameters": {},
                    },
                    {
                        "id": 2,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {
                                    "name": "Created",
                                    "conditions": {
                                        "expression": (
                                            "{{1.event_type}} = "
                                            '"invoice.created"'
                                        )
                                    },
                                },
                                "flow": [
                                    {"id": 3, "module": "datastore:AddRecord"}
                                ],
                            },
                            {
                                "name": "Fallback",
                                "flow": [
                                    {"id": 4, "module": "datastore:AddRecord"}
                                ],
                            },
                        ],
                    },
                ],
                "metadata": {"schedule": {"id": "schedule:manual"}},
            }
        )
    )

    emitted_codes = {
        finding.code for finding in validate_routes(tuple(iter_ast_nodes(root)))
    }
    assert EVENT_TYPE_FALLBACK_MISSING_CODE not in emitted_codes, (
        f"Fallback route should satisfy event router review: {emitted_codes}"
    )


def validate_ast(root: MakeAstRoot) -> BlueprintValidationReport:
    """Validate one AST fixture with the local native-module catalog.

    Returns:
        The validation report for the AST fixture.
    """
    return validate_blueprint(root=root, catalog=native_module_snapshot())


def require_finding(
    report: BlueprintValidationReport,
    code: str,
) -> BlueprintValidationFinding:
    """Return one report finding by stable code or fail with the full report.

    Returns:
        The matching validation finding.
    """
    return require_route_finding(report.findings, code)


def require_route_finding(
    findings: tuple[BlueprintValidationFinding, ...],
    code: str,
) -> BlueprintValidationFinding:
    """Return one route finding by stable code or fail with the full finding.

    list.

    Returns:
        The matching validation finding.
    """
    for finding in findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {findings}"
    assert_unexpected_success(failure_message)
    return None


def load_ast_fixture(path: Path) -> MakeAstRoot:
    """Load one sanitized fixture as a Make AST root.

    Returns:
        The parsed AST fixture.
    """
    return parse_make_ast_json_text(
        json.dumps(load_fixture(path), sort_keys=True)
    )


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded fixture payload.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))
