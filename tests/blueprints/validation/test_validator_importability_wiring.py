# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Validator wiring tests for focused importability modules.

Boundary contract:
- Owns: importability module extraction and validator aggregation tests.
- Must not: duplicate full validation contract coverage or call live Make
services.
- Allows: sanitized inline AST payloads and direct focused-module assertions.
- Split when: each importability submodule gains an independent contract file.
- Merge when: another validation test owns this exact validator wiring behavior.
"""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, iter_ast_nodes, parse_make_ast_json_text
from blueprints.validation import BlueprintValidationReport, validate_blueprint
from blueprints.validation.importability import (
    IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
    validate_importability,
)
from blueprints.validation.placeholders import (
    validate_importability_placeholders,
)
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object

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


def test_validator_aggregates_importability_findings_from_focused_module() -> (
    None
):
    """The main validator includes findings emitted by focused importability.

    modules.
    """
    root = parse_make_ast_json_text(json.dumps(placeholder_payload()))
    report = validate_blueprint(root=root, catalog=load_catalog_fixture())
    focused_findings = tuple(
        finding
        for node in iter_ast_nodes(root)
        for finding in validate_importability_placeholders(node)
    )

    assert not (IMPORTABILITY_PLACEHOLDER_UNRESOLVED not in report.codes()), (
        f"Validator did not aggregate importability findings: {report.findings}"
    )
    assert focused_findings, (
        "Focused placeholder finding was not preserved by validator "
        "aggregation."
    )
    assert not (
        focused_findings[0].finding_id
        not in {finding.finding_id for finding in report.findings}
    ), "Focused placeholder finding was not preserved by validator aggregation."


def test_focused_importability_module_can_be_0405e82e() -> None:
    """Focused importability modules can run directly from parsed AST nodes."""
    root = parse_make_ast_json_text(json.dumps(placeholder_payload()))
    findings = tuple(
        finding
        for node in iter_ast_nodes(root)
        for finding in validate_importability_placeholders(node)
    )

    assert tuple(finding.code for finding in findings) == (
        IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
    ), f"Focused placeholder module did not emit stable findings: {findings}"
    assert findings[0].source_path == ("flow", 0, "parameters", "url"), (
        f"Focused placeholder module lost source path: {findings[0]}"
    )


def test_validator_public_api_remains_backward_compatible() -> None:
    """The public validator signature and report contract remain stable."""
    root = parse_make_ast_json_text(json.dumps(placeholder_payload()))
    report: object = validate_blueprint(
        root=root, catalog=load_catalog_fixture()
    )
    signature = inspect.signature(validate_blueprint)

    assert tuple(signature.parameters) == ("root", "catalog", "knowledge"), (
        f"validate_blueprint signature drifted: {signature}"
    )
    assert not (type(report) is not BlueprintValidationReport), (
        f"validate_blueprint returned the wrong contract: {report}"
    )
    assert (
        validate_importability(iter_ast_nodes(root))[0].code
        == IMPORTABILITY_PLACEHOLDER_UNRESOLVED
    ), (
        "Focused importability orchestration no longer exposes placeholder "
        "findings."
    )


def placeholder_payload() -> JsonObject:
    """Return a catalog-backed payload with one unresolved handoff placeholder.

    Returns:
        The sanitized blueprint payload.
    """
    return {
        "name": "validator-importability-wiring",
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
