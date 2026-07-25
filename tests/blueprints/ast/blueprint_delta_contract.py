# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for structured Make blueprint delta reports.

Boundary contract:
- Owns: classified blueprint delta report behavior for synthetic AST payloads.
- Must not: test MCP execution, catalog validation, or live Make exports.
- Allows: compact in-memory blueprints and deterministic category assertions.
- Split when: report rendering, validation, or repair context gets separate
APIs.
- Merge when: the main AST contract owns these exact classified-delta cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast.delta import compare_blueprints, compute_ast_delta
from blueprints.validation import BLUEPRINT_DELTA_CATEGORIES

from tests.conftest import REPO_ROOT
from tests.support.assertions import assert_unexpected_success

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject

DESIGNER_COORDINATE_CHANGE_COUNT = 2
DIFF_FIXTURE_ROOT = (
    REPO_ROOT / "tests" / "blueprints" / "fixtures" / "diff_blueprint"
)


def test_blueprint_delta_ignores_key_order_and_classifies_layout_changes() -> (
    None
):
    """Structured blueprint comparison ignores JSON key order but reports.

    layout.

    drift.
    """
    generated: JsonObject = {
        "flow": [
            {
                "metadata": {"designer": {"x": 10, "y": 20}},
                "module": "http:MakeRequest",
                "id": 1,
            }
        ],
        "name": "demo",
    }
    exported: JsonObject = {
        "name": "demo",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "metadata": {"designer": {"y": 80, "x": 40}},
            }
        ],
    }

    report = compare_blueprints(
        generated, exported, label="generated_vs_exported"
    )
    categories = report.summary.get("categories")

    assert (
        report.summary["finding_count"] == DESIGNER_COORDINATE_CHANGE_COUNT
    ), f"Expected only designer coordinate drift: {report.as_dict()}"
    assert isinstance(categories, list), (
        f"Designer categories should be a list: {report.as_dict()}"
    )
    category_set = {str(item) for item in cast("list[object]", categories)}
    assert category_set == {"designer-layout"}, (
        f"Designer changes were not isolated: {report.as_dict()}"
    )
    assert not (report.semantic_findings), (
        f"Designer layout should not be semantic drift: {report.as_dict()}"
    )
    assert len(report.layout_findings) == DESIGNER_COORDINATE_CHANGE_COUNT, (
        f"Designer layout findings were not exposed: {report.as_dict()}"
    )
    assert (
        report.summary["layout_finding_count"]
        == DESIGNER_COORDINATE_CHANGE_COUNT
    ), f"Designer layout summary count drifted: {report.as_dict()}"
    assert report.as_dict()["layout_changes"], (
        f"Designer layout report omitted layout_changes: {report.as_dict()}"
    )


def test_blueprint_delta_classifies_note_placement_as_layout_only() -> None:
    """Root note placement is layout parity evidence, not semantic drift."""
    before: JsonObject = {
        "name": "note-layout",
        "flow": [{"id": 1, "module": "http:MakeRequest"}],
        "metadata": {
            "notes": [
                {
                    "text": "Handoff note",
                    "x": 10,
                    "y": 20,
                    "moduleIds": ["1"],
                }
            ]
        },
    }
    after: JsonObject = {
        "name": "note-layout",
        "flow": [{"id": 1, "module": "http:MakeRequest"}],
        "metadata": {
            "notes": [
                {
                    "text": "Handoff note",
                    "x": 110,
                    "y": 20,
                    "moduleIds": ["1"],
                }
            ]
        },
    }

    report = compare_blueprints(before, after, label="note_layout")

    assert not (report.semantic_findings), (
        f"Note placement should not be semantic drift: {report.as_dict()}"
    )
    assert report.layout_findings, (
        f"Note placement should be layout drift: {report.as_dict()}"
    )
    assert all(
        finding.path.startswith("$.metadata.notes")
        for finding in report.layout_findings
    ), f"Note placement paths were not preserved: {report.as_dict()}"


def test_blueprint_delta_classifies_semantic_categories() -> None:
    """Blueprint deltas classify module, routing, mapping, and placeholder.

    changes.
    """
    generated: JsonObject = {
        "name": "demo",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "version": 1,
                "mapper": {"url": "{{customer_url}}"},
                "routes": [
                    {"filter": {"condition": "{{1.score}} > 10"}, "flow": []}
                ],
            }
        ],
        "metadata": {
            "scenario": {"name": "demo"},
            "expect": "old",
            "notes": "old",
        },
    }
    known_good: JsonObject = {
        "name": "demo",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "version": 2,
                "mapper": {"url": "https://example.invalid/api"},
                "routes": [
                    {"filter": {"condition": "{{1.score}} > 80"}, "flow": []}
                ],
            },
            {"id": 2, "module": "datastore:AddRecord"},
        ],
        "metadata": {
            "scenario": {"name": "demo"},
            "expect": "new",
            "notes": "new",
            "restore": {"parameters": {"account": {"label": "Connection"}}},
        },
    }

    report = compare_blueprints(
        generated, known_good, label="generated_vs_known_good"
    )
    payload = report.as_dict()
    findings = cast("list[JsonObject]", payload["findings"])
    categories = {
        str(finding["category"])
        for finding in findings
        if "category" in finding
    }

    expected = {
        "connection",
        "metadata",
        "module-version",
        "placeholder",
        "route/filter",
    }
    assert expected.issubset(categories), (
        f"Missing classified delta categories: {payload}"
    )
    assert categories <= set(BLUEPRINT_DELTA_CATEGORIES), (
        f"Unexpected category outside model contract: {categories}"
    )
    assert payload["mapping_changes"], (
        f"Report omitted ADR-required grouped sections: {payload}"
    )
    assert payload["control_flow_changes"], (
        f"Report omitted ADR-required grouped sections: {payload}"
    )
    assert payload["filter_shape_delta"], (
        f"Report omitted filter_shape_delta: {payload}"
    )
    assert payload["mapper_shape_delta"], (
        f"Report omitted mapper_shape_delta: {payload}"
    )
    assert payload["metadata_expect_missing"], (
        f"Report omitted metadata_expect_missing: {payload}"
    )
    assert payload["restore_missing"], (
        f"Report omitted restore_missing: {payload}"
    )
    assert payload["runtime_resource_placeholder"], (
        f"Report omitted runtime_resource_placeholder: {payload}"
    )
    assert payload["native_parity_gap"], (
        f"Report omitted native_parity_gap: {payload}"
    )


def test_blueprint_delta_reports_zero_trace_violation_bucket_with_values() -> (
    None
):
    """Diff reports can isolate private export traces when values are.

    requested.
    """
    generated: JsonObject = {
        "name": "zero-trace",
        "flow": [],
        "metadata": {
            "notes": [{"content": "Local-only Pancakes source_draft note."}],
        },
    }
    known_good: JsonObject = {
        "name": "zero-trace",
        "flow": [],
        "metadata": {"notes": []},
    }

    report = compare_blueprints(generated, known_good, label="zero_trace")
    payload = report.as_dict(include_values=True)

    assert payload["zero_trace_violation"], (
        f"Report omitted zero_trace_violation bucket: {payload}"
    )


def test_blueprint_delta_classifies_route_structure_7b11c18c() -> None:
    """Route shape changes remain semantic even when layout comparison.

    exists.
    """
    before: JsonObject = {
        "name": "route-layout",
        "flow": [
            {
                "id": 1,
                "module": "builtin:BasicRouter",
                "routes": [{"filter": {"name": "Accepted"}, "flow": []}],
            }
        ],
    }
    after: JsonObject = {
        "name": "route-layout",
        "flow": [
            {
                "id": 1,
                "module": "builtin:BasicRouter",
                "routes": [{"filter": {"name": "Rejected"}, "flow": []}],
            }
        ],
    }

    report = compare_blueprints(before, after, label="route_structure")
    payload = report.as_dict()

    assert report.semantic_findings, (
        f"Route structure should remain semantic drift: {payload}"
    )
    assert payload["control_flow_changes"], (
        f"Route structure should be reported as control flow: {payload}"
    )


def test_blueprint_delta_fixture_triplet_covers_diff_categories() -> None:
    """The known-good triplet covers semantic and non-semantic diff.

    categories.
    """
    generated = _json_fixture("generated_router.json")
    known_good = _json_fixture("known_good_router.json")

    report = compare_blueprints(generated, known_good, label="fixture_triplet")
    payload = report.as_dict()
    categories = {
        str(finding["category"])
        for finding in cast("list[JsonObject]", payload["findings"])
        if "category" in finding
    }

    expected_categories = {
        "connection",
        "designer-layout",
        "metadata",
        "route/filter",
    }
    assert expected_categories.issubset(categories), (
        f"Diff fixture triplet missed categories: {payload}"
    )
    assert report.semantic_findings, (
        f"Diff fixture triplet should include semantic drift: {payload}"
    )
    assert any(not finding.is_semantic for finding in report.findings), (
        f"Diff fixture triplet should include non-semantic drift: {payload}"
    )


def test_blueprint_delta_rejects_non_string_object_keys() -> None:
    """Blueprint delta comparison rejects non-JSON mapping keys before path.

    reporting.
    """
    before = cast("JsonObject", {"name": "bad-key", "flow": [{1: "not-json"}]})
    after: JsonObject = {"name": "bad-key", "flow": []}

    with pytest.raises(TypeError, match="object keys must be strings"):
        require_non_string_delta_key_failure(before, after)


def test_blueprint_delta_rejects_non_finite_numbers() -> None:
    """Blueprint delta comparison rejects non-finite numbers before path.

    reporting.
    """
    before: JsonObject = {"name": "bad-number", "flow": []}
    after = cast(
        "JsonObject", {"name": "bad-number", "flow": [], "score": float("inf")}
    )

    with pytest.raises(TypeError, match="numbers must be finite"):
        require_non_finite_delta_number_failure(before, after)


def test_blueprint_delta_ignores_boolean_node_ids_in_reports() -> None:
    """Malformed boolean node IDs must not be rendered as stable module IDs."""
    before: JsonObject = {
        "name": "boolean-node-id",
        "flow": [{"id": True, "module": "http:MakeRequest"}],
    }
    after: JsonObject = {"name": "boolean-node-id", "flow": []}

    report = compare_blueprints(before, after, label="boolean_id")

    assert not (report.findings[0].node_id is not None), (
        f"Boolean node ID leaked into delta report: {report.as_dict()}"
    )


def require_non_string_delta_key_failure(
    before: JsonObject, after: JsonObject
) -> None:
    """Fail unless delta comparison rejects non-string object keys."""
    unexpected = compute_ast_delta(before, after)
    failure_message = (
        f"Non-string delta object key should have failed: {unexpected}"
    )
    assert_unexpected_success(failure_message)


def require_non_finite_delta_number_failure(
    before: JsonObject, after: JsonObject
) -> None:
    """Fail unless delta comparison rejects non-finite numbers."""
    unexpected = compute_ast_delta(before, after)
    failure_message = (
        f"Non-finite delta number should have failed: {unexpected}"
    )
    assert_unexpected_success(failure_message)


def _json_fixture(filename: str) -> JsonObject:
    return cast(
        "JsonObject",
        json.loads((DIFF_FIXTURE_ROOT / filename).read_text(encoding="utf-8")),
    )
