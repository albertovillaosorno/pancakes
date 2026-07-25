# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Filter expression importability validation tests.

Boundary contract:
- Owns: conservative route-filter expression and reference validation.
- Must not: implement a full Make expression compiler or call live Make
services.
- Allows: sanitized fixtures, tiny supported filter subsets, and exact path
assertions.
- Split when: full Make formula compilation becomes its own tested parser.
- Merge when: route validation owns all filter expression contract coverage
directly.
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

FILTER_UNSUPPORTED_CODE = "filter.expression_unsupported"
FILTER_LABEL_MISSING_CODE = "filter.label_missing"
FILTER_LABEL_OVERLONG_CODE = "filter.label_overlong"
FILTER_NOT_UPSTREAM_CODE = "filter.reference_not_upstream"
FILTER_OPERATOR_UNSUPPORTED_CODE = "filter.operator_unsupported"
FILTER_UNKNOWN_FIELD_CODE = "filter.reference_unknown_field"
FILTER_EMPTY_CONDITIONS_CODE = "filter.empty_conditions"
FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
INVALID_FILTER_UNKNOWN_REFERENCE_FIXTURE = (
    FIXTURE_ROOT / "invalid_filter_unknown_reference.json"
)
INVALID_FILTER_UNSUPPORTED_EXPRESSION_FIXTURE = (
    FIXTURE_ROOT / "invalid_filter_unsupported_expression.json"
)


def test_filter_reference_to_upstream_webhook_15872267() -> None:
    """A tiny supported filter subset may reference declared upstream webhook.

    fields.
    """
    report = validate_payload(valid_filter_payload())

    blocked_codes = {
        FILTER_UNSUPPORTED_CODE,
        FILTER_NOT_UPSTREAM_CODE,
        FILTER_UNKNOWN_FIELD_CODE,
        "semantic.output_field_unknown",
    }
    actual_blocked_codes = blocked_codes.intersection(report.codes())
    assert not (actual_blocked_codes), (
        f"Supported declared filter was rejected: {actual_blocked_codes}"
    )


def test_filter_reference_to_dynamic_upstream_output_child_is_accepted() -> (
    None
):
    """Dynamic upstream output objects allow filter references to child.

    fields.
    """
    payload = valid_filter_payload()
    source = object_at(list_member(payload, "flow"), 0)
    source["interface"] = [{"name": "payload", "type": "collection"}]
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    conditions = object_member(filter_payload, "conditions")
    conditions["expression"] = '{{1.payload.email}} = "ada@example.invalid"'
    branch_node = object_at(list_member(route, "flow"), 0)
    mapper = object_member(branch_node, "mapper")
    mapper["company"] = "{{1.payload.company}}"
    mapper["email"] = "{{1.payload.email}}"
    mapper["score"] = "{{1.payload.score}}"
    mapper["source"] = "{{1.payload.source}}"

    report = validate_payload(payload)

    assert FILTER_UNKNOWN_FIELD_CODE not in report.codes(), (
        f"Dynamic upstream output child was rejected: {report.findings}"
    )


def test_filter_reference_to_mapping_style_08dcd221() -> None:
    """Mapping-style output contracts also allow dynamic child filter.

    references.
    """
    payload = valid_filter_payload()
    source = object_at(list_member(payload, "flow"), 0)
    source["interface"] = {"payload": {"type": "collection"}}
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    conditions = object_member(filter_payload, "conditions")
    conditions["expression"] = '{{1.payload.email}} = "ada@example.invalid"'
    branch_node = object_at(list_member(route, "flow"), 0)
    mapper = object_member(branch_node, "mapper")
    mapper["company"] = "{{1.payload.company}}"
    mapper["email"] = "{{1.payload.email}}"
    mapper["score"] = "{{1.payload.score}}"
    mapper["source"] = "{{1.payload.source}}"

    report = validate_payload(payload)

    assert FILTER_UNKNOWN_FIELD_CODE not in report.codes(), (
        f"Mapping-style dynamic output child was rejected: {report.findings}"
    )


def test_filter_reference_to_non_upstream_module_is_rejected() -> None:
    """Route filters cannot reference modules inside their own branch flow."""
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    conditions = object_member(filter_payload, "conditions")
    conditions["expression"] = '{{3.email}} = "review"'
    report = validate_payload(payload)

    finding = require_finding(report, FILTER_NOT_UPSTREAM_CODE)

    assert finding.source_path == (
        "flow",
        1,
        "routes",
        0,
        "filter",
        "conditions",
        "expression",
    ), f"Non-upstream filter finding path drifted: {finding}"


def test_unsupported_filter_string_reports_blocker_instead_of_passing() -> None:
    """Plain-English filter text is blocked instead of treated as Make.

    syntax.
    """
    report = validate_fixture(INVALID_FILTER_UNSUPPORTED_EXPRESSION_FIXTURE)

    finding = require_finding(report, FILTER_UNSUPPORTED_CODE)

    assert finding.severity == "error", (
        f"Unsupported filter expressions must be blocking: {finding}"
    )


def test_unsupported_filter_expression_redacts_raw_text() -> None:
    """Unsupported filter diagnostics do not echo raw expressions or mapped.

    fields.
    """
    raw_expression = "{{1.payload.access_token"
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    conditions = object_member(filter_payload, "conditions")
    conditions["expression"] = raw_expression

    report = validate_payload(payload)
    finding = require_finding(report, FILTER_UNSUPPORTED_CODE)

    leaked_messages = tuple(
        message
        for message in (finding.client_message, finding.internal_message)
        if raw_expression in message or "access_token" in message
    )
    assert not leaked_messages, (
        f"Unsupported filter expression leaked raw text: {leaked_messages}"
    )


def test_filter_finding_points_to_route_condition_path() -> None:
    """Unsupported filters report the exact route condition source path."""
    report = validate_fixture(INVALID_FILTER_UNSUPPORTED_EXPRESSION_FIXTURE)
    finding = require_finding(report, FILTER_UNSUPPORTED_CODE)

    expected_path = (
        "flow",
        1,
        "routes",
        0,
        "filter",
        "conditions",
        "expression",
    )
    assert finding.source_path == expected_path, (
        f"Unsupported filter path drifted: {finding}"
    )


def test_filter_reference_to_unknown_declared_field_is_rejected() -> None:
    """Filter references honor declared webhook output fields when evidence.

    exists.
    """
    report = validate_fixture(INVALID_FILTER_UNKNOWN_REFERENCE_FIXTURE)

    finding = require_finding(report, FILTER_UNKNOWN_FIELD_CODE)

    assert finding.node_id == "2", (
        f"Unknown filter field should attach to the router node: {finding}"
    )


def test_boolean_filter_conditions_do_not_bypass_empty_filter_validation() -> (
    None
):
    """Boolean route-filter conditions are not executable Make condition.

    payloads.
    """
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    filter_payload["conditions"] = False

    report = validate_payload(payload)

    finding = require_finding(report, FILTER_EMPTY_CONDITIONS_CODE)
    assert finding.source_path == ("flow", 1, "routes", 0, "filter"), (
        f"Boolean empty-filter finding path drifted: {finding}"
    )


def test_numeric_filter_conditions_do_not_bypass_empty_filter_validation() -> (
    None
):
    """Bare numeric route-filter conditions are not executable Make condition.

    payloads.
    """
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    filter_payload["conditions"] = 0

    report = validate_payload(payload)

    assert not (FILTER_EMPTY_CONDITIONS_CODE not in report.codes()), (
        f"Numeric empty-filter condition was not rejected: {report.findings}"
    )


def test_make_native_filter_condition_groups_accept_text_operators() -> None:
    """Make-native AND/OR condition groups keep basic and text operator.

    families.
    """
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    filter_payload["conditions"] = [
        [
            {"a": "{{1.email}}", "o": "exist"},
            {
                "a": "{{1.email}}",
                "o": "text:contains:ci",
                "b": "@example.invalid",
            },
        ],
        [{"a": "{{1.company}}", "o": "text:notequal", "b": "Blocked Co"}],
    ]

    report = validate_payload(payload)

    unexpected_codes = {
        FILTER_UNSUPPORTED_CODE,
        FILTER_NOT_UPSTREAM_CODE,
        FILTER_OPERATOR_UNSUPPORTED_CODE,
        FILTER_UNKNOWN_FIELD_CODE,
    }.intersection(report.codes())
    assert not unexpected_codes, (
        f"Make-native condition groups were rejected: {unexpected_codes}; "
        f"{report.findings}"
    )


def test_make_native_filter_condition_rejects_unsupported_operator() -> None:
    """Unknown native Make filter operators stay blocking until promoted."""
    payload = valid_filter_payload()
    route = object_at(
        list_member(object_at(list_member(payload, "flow"), 1), "routes"),
        0,
    )
    filter_payload = object_member(route, "filter")
    filter_payload["conditions"] = [
        [{"a": "{{1.email}}", "o": "text:regex", "b": ".*"}]
    ]

    report = validate_payload(payload)
    finding = require_finding(report, FILTER_OPERATOR_UNSUPPORTED_CODE)

    assert finding.severity == "error", (
        f"Unsupported filter operator must block: {finding}"
    )
    assert finding.source_path == (
        "flow",
        1,
        "routes",
        0,
        "filter",
        "conditions",
        0,
        0,
    ), f"Unsupported native operator path drifted: {finding}"


def test_filter_label_constraints_follow_make_dialog_limit() -> None:
    """Route filters require labels within Make's 120-character UI limit."""
    missing_payload = valid_filter_payload()
    missing_route = object_at(
        list_member(
            object_at(list_member(missing_payload, "flow"), 1), "routes"
        ),
        0,
    )
    missing_filter = object_member(missing_route, "filter")
    _ = missing_filter.pop("name", None)

    missing_report = validate_payload(missing_payload)
    missing_finding = require_finding(missing_report, FILTER_LABEL_MISSING_CODE)

    overlong_payload = valid_filter_payload()
    overlong_route = object_at(
        list_member(
            object_at(list_member(overlong_payload, "flow"), 1), "routes"
        ),
        0,
    )
    overlong_filter = object_member(overlong_route, "filter")
    overlong_filter["name"] = "x" * 121

    overlong_report = validate_payload(overlong_payload)
    overlong_finding = require_finding(
        overlong_report, FILTER_LABEL_OVERLONG_CODE
    )

    assert missing_finding.severity == "warning", (
        f"Missing filter labels should be warnings: {missing_finding}"
    )
    assert overlong_finding.severity == "warning", (
        f"Overlong filter labels should be warnings: {overlong_finding}"
    )


def valid_filter_payload() -> JsonObject:
    """Return a sanitized payload using the first supported filter subset."""
    return {
        "flow": [
            {
                "id": 1,
                "interface": [
                    {"name": "email", "type": "text"},
                    {"name": "company", "type": "text"},
                    {"name": "source", "type": "text"},
                    {"name": "score", "type": "number"},
                ],
                "module": "gateway:CustomWebHook",
                "parameters": {},
            },
            {
                "id": 2,
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "conditions": {
                                "expression": "not empty({{1.email}}) and "
                                "{{1.score}} >= 80"
                            },
                            "name": "Qualified",
                        },
                        "flow": [
                            {
                                "id": 3,
                                "mapper": {
                                    "company": "{{1.company}}",
                                    "email": "{{1.email}}",
                                    "route": "qualified",
                                    "score": "{{1.score}}",
                                    "source": "{{1.source}}",
                                },
                                "module": "datastore:AddRecord",
                                "parameters": {
                                    "datastore": (
                                        "demo_datastore_qualified_leads"
                                    )
                                },
                            }
                        ],
                    }
                ],
            },
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
        "name": "valid-filter-expression",
    }


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized filter expression fixture.

    Returns:
        The validation report.
    """
    return validate_payload(load_fixture(path))


def validate_payload(payload: JsonObject) -> BlueprintValidationReport:
    """Validate one sanitized filter expression payload.

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


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return a list member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return an object member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return cast("JsonObject", value)


def object_at(items: list[object], index: int) -> JsonObject:
    """Return one object item from a JSON list."""
    item = items[index]
    assert isinstance(item, dict), (
        f"Expected object list item at {index}: {items}"
    )
    return cast("JsonObject", item)
