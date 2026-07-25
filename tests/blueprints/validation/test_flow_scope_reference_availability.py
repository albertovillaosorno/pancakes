# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Flow-scope reference availability validation tests.

Boundary contract:
- Owns: importability coverage for references available on the current execution
path.
- Must not: duplicate output-field schema validation or contact live Make
services.
- Allows: sanitized branch fixtures, inline downstream cases, and exact source
paths.
- Split when: execution-path availability becomes a standalone AST test suite.
- Merge when: another validation test owns this exact flow-scope reference
behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.validation import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

REFERENCE_UNAVAILABLE_CODE = "importability.reference_unavailable"
FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
VALID_BRANCH_REFERENCE_FIXTURE = (
    FIXTURE_ROOT / "valid_branch_reference_to_webhook.json"
)
INVALID_CROSS_BRANCH_REFERENCE_FIXTURE = (
    FIXTURE_ROOT / "invalid_cross_branch_reference.json"
)


def test_branch_can_reference_upstream_webhook_output() -> None:
    """A branch mapper and filter may reference a webhook before the router."""
    report = validate_fixture(VALID_BRANCH_REFERENCE_FIXTURE)

    unavailable = tuple(
        finding
        for finding in report.findings
        if finding.code == REFERENCE_UNAVAILABLE_CODE
    )
    assert not (unavailable), (
        f"Upstream webhook references were rejected: {unavailable}"
    )


def test_branch_cannot_reference_sibling_branch_module_output() -> None:
    """A branch cannot reference a module that only exists in a sibling.

    branch.
    """
    report = validate_fixture(INVALID_CROSS_BRANCH_REFERENCE_FIXTURE)

    _ = require_finding(report, REFERENCE_UNAVAILABLE_CODE)


def test_node_cannot_reference_downstream_module_output() -> None:
    """A linear node cannot reference a later module on the same path."""
    report = validate_payload(downstream_reference_payload())
    finding = require_finding(report, REFERENCE_UNAVAILABLE_CODE)

    assert finding.source_path == ("flow", 0, "mapper", "email"), (
        f"Downstream reference path drifted: {finding}"
    )


def test_reference_availability_finding_points_to_mapper_or_filter_path() -> (
    None
):
    """Reference availability findings preserve mapper and filter expression.

    paths.
    """
    report = validate_fixture(INVALID_CROSS_BRANCH_REFERENCE_FIXTURE)
    paths = {
        finding.source_path
        for finding in report.findings
        if finding.code == REFERENCE_UNAVAILABLE_CODE
    }

    expected_paths = {
        ("flow", 1, "routes", 1, "filter", "conditions", "expression"),
        ("flow", 1, "routes", 1, "flow", 0, "mapper", "email"),
    }
    assert expected_paths.issubset(paths), (
        f"Reference availability paths drifted: {paths}"
    )


def downstream_reference_payload() -> JsonObject:
    """Return a sanitized linear flow with a downstream reference."""
    return {
        "flow": [
            {
                "id": 1,
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:datastore:2.0.5:action:AddRecord"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "c" * 64,
                        "status": "resolved",
                    }
                },
                "module": "datastore:AddRecord",
                "parameters": {"datastore": "first-store"},
                "mapper": {"email": "{{2.email}}"},
            },
            {
                "id": 2,
                "interface": [{"name": "email", "type": "text"}],
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:datastore:2.0.5:action:AddRecord"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "c" * 64,
                        "status": "resolved",
                    }
                },
                "module": "datastore:AddRecord",
                "parameters": {"datastore": "second-store"},
                "mapper": {"email": "later@example.invalid"},
            },
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
        "name": "invalid-downstream-reference",
    }


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized flow-scope fixture.

    Returns:
        The validation report.
    """
    return validate_payload(load_fixture(path))


def validate_payload(payload: JsonObject) -> BlueprintValidationReport:
    """Validate one sanitized flow-scope payload.

    Returns:
        The validation report.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def require_finding(
    report: BlueprintValidationReport,
    code: str,
) -> BlueprintValidationFinding:
    """Return one validation finding by code.

    Returns:
        The matching validation finding.
    """
    for finding in report.findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {report.findings}"
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
