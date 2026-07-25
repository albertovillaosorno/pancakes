# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Validation pattern tests for recurrent Make blueprint failures.

Boundary contract:
- Owns: stable validation pattern identity assertions for recurrent
importability failures.
- Must not: assert fragile English diagnostic text, repair blueprints, or call
Make.com.
- Allows: small sanitized payloads, exact finding-code checks, and deterministic
path checks.
- Split when: pattern IDs become a public MCP or client contract.
- Merge when: another validation test owns the same pattern identity contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from blueprints.validation.findings import (
    AST_METADATA_INVALID_CODE,
    INVALID_FILTER_EXPRESSION_CODE,
    MALFORMED_NOTE_CODE,
    MISSING_ROUTER_FANOUT_CODE,
    PATTERN_INVALID_FILTER_EXPRESSION,
    PATTERN_MALFORMED_NOTE,
    PATTERN_METADATA_RESTORE_SHAPE,
    PATTERN_MISSING_ROUTER_FANOUT,
    PATTERN_ROUTES_ON_NON_ROUTER,
    PATTERN_UNRESOLVED_PLACEHOLDER,
    ROUTES_ON_NON_ROUTER_CODE,
    UNRESOLVED_PLACEHOLDER_CODE,
    validation_pattern_for_finding,
)

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success

if TYPE_CHECKING:
    from blueprints.validation.models import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )


def test_routes_on_non_router_pattern_has_stable_code_and_path() -> None:
    """A non-router route container emits a stable route-pattern finding."""
    report = validate_payload(
        cast(
            "JsonObject",
            {
                "name": "routes-on-non-router",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "routes": [{"flow": []}],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            },
        )
    )

    finding = require_finding(report, ROUTES_ON_NON_ROUTER_CODE)

    expect_source_path(finding, ("flow", 0, "routes"))
    expect_pattern_id(finding, PATTERN_ROUTES_ON_NON_ROUTER)


def test_missing_router_fanout_pattern_has_stable_code_and_path() -> None:
    """Routers without route fanout emit a stable pattern finding."""
    report = validate_payload(
        {
            "name": "missing-router-fanout",
            "flow": [{"id": 1, "module": "builtin:BasicRouter"}],
            "metadata": {"schedule": {"id": "schedule:daily"}},
        }
    )

    finding = require_finding(report, MISSING_ROUTER_FANOUT_CODE)

    expect_source_path(finding, ("flow", 0))
    expect_pattern_id(finding, PATTERN_MISSING_ROUTER_FANOUT)


def test_unresolved_placeholder_pattern_has_stable_code_and_path() -> None:
    """Unresolved placeholders emit a stable importability pattern finding."""
    report = validate_payload(
        {
            "name": "unresolved-placeholder",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "parameters": {"url": "{{TODO:client-webhook-url}}"},
                }
            ],
            "metadata": {"schedule": {"id": "schedule:daily"}},
        }
    )

    finding = require_finding(report, UNRESOLVED_PLACEHOLDER_CODE)

    expect_source_path(finding, ("flow", 0, "parameters", "url"))
    expect_pattern_id(finding, PATTERN_UNRESOLVED_PLACEHOLDER)


def test_invalid_filter_expression_pattern_has_stable_code_and_path() -> None:
    """Empty filter expressions emit a stable filter-pattern finding."""
    report = validate_payload(
        {
            "name": "invalid-filter-expression",
            "flow": [
                {
                    "id": 1,
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "filter": {"rules": []},
                            "flow": [{"id": 2, "module": "http:MakeRequest"}],
                        }
                    ],
                }
            ],
            "metadata": {"schedule": {"id": "schedule:daily"}},
        }
    )

    finding = require_finding(report, INVALID_FILTER_EXPRESSION_CODE)

    expect_source_path(finding, ("flow", 0, "routes", 0, "filter"))
    expect_pattern_id(finding, PATTERN_INVALID_FILTER_EXPRESSION)


def test_malformed_note_pattern_has_stable_code_and_path() -> None:
    """Malformed Make metadata notes keep a stable pattern identity."""
    report = validate_payload(
        {
            "name": "malformed-note",
            "flow": [{"id": 1, "module": "http:MakeRequest"}],
            "metadata": {
                "notes": ["note text must be an object"],
                "schedule": {"id": "schedule:daily"},
            },
        }
    )

    finding = require_finding(report, MALFORMED_NOTE_CODE)

    expect_source_path(finding, ("metadata", "notes", 0))
    expect_pattern_id(finding, PATTERN_MALFORMED_NOTE)


def test_metadata_restore_shape_pattern_has_stable_code_and_path() -> None:
    """Invalid metadata containers emit a stable restore-shape pattern."""
    report = validate_payload(
        {
            "name": "metadata-restore-shape",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "metadata": "metadata must be an object",
                }
            ],
            "metadata": {"schedule": {"id": "schedule:daily"}},
        }
    )

    finding = require_finding(report, AST_METADATA_INVALID_CODE)

    expect_source_path(finding, ("flow", 0))
    expect_pattern_id(finding, PATTERN_METADATA_RESTORE_SHAPE)


def test_pattern_order_is_deterministic_when_multiple_failures_exist() -> None:
    """Overlapping route and placeholder failures preserve validator.

    ordering.
    """
    report = validate_payload(
        cast(
            "JsonObject",
            {
                "name": "multiple-patterns",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "parameters": {"url": "{{TODO:client-webhook-url}}"},
                        "routes": [{"flow": []}],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            },
        )
    )

    pattern_ids = tuple(
        pattern.pattern_id
        for finding in report.findings
        if (pattern := validation_pattern_for_finding(finding)) is not None
    )

    expected_pattern_ids = (
        PATTERN_ROUTES_ON_NON_ROUTER,
        PATTERN_UNRESOLVED_PLACEHOLDER,
    )
    assert pattern_ids == expected_pattern_ids, (
        f"Unexpected pattern ordering: {pattern_ids}"
    )


def validate_payload(payload: JsonObject) -> BlueprintValidationReport:
    """Validate one small sanitized payload.

    Returns:
        The validation report for the payload.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def require_finding(
    report: BlueprintValidationReport,
    code: str,
) -> BlueprintValidationFinding:
    """Return one finding by stable code or fail with the full report.

    Returns:
        The matching validation finding.
    """
    for finding in report.findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {report.findings}"
    assert_unexpected_success(failure_message)
    return None


def expect_source_path(
    finding: BlueprintValidationFinding,
    expected: tuple[str | int, ...],
) -> None:
    """Fail if the finding source path differs from the expected path."""
    assert finding.source_path == expected, (
        f"Expected path {expected!r}; got {finding.source_path!r}"
    )


def expect_pattern_id(
    finding: BlueprintValidationFinding, expected: str
) -> None:
    """Fail if the finding does not expose the expected validation pattern."""
    pattern = validation_pattern_for_finding(finding)
    assert pattern is not None, (
        f"Finding {finding.code!r} has no validation pattern."
    )
    assert pattern.pattern_id == expected, (
        f"Expected pattern {expected!r}; got {pattern.pattern_id!r}"
    )
