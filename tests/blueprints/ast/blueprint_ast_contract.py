# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for the typed Make AST contract.

Boundary contract:
- Owns: tests for typed Make AST parsing, traversal, evidence, references, and
bundles.
- Must not: test catalog compilation, scraper transport, or repository tools.
- Allows: blueprint fixtures, AST helpers, and deterministic JSON assertions.
- Split when: AST parsing, layout, references, and persistence need separate
modules.
- Merge when: another AST contract test duplicates these behavior boundaries.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import (
    MakeAstParseError,
    MakeBlueprintBundlePayloads,
    analyze_blueprint_layout_transition,
    apply_blueprint_layout,
    ast_evidence_report,
    ast_root_snapshot,
    collect_ast_node_ids,
    collect_designer_message_evidence,
    collect_reference_targets,
    collect_reference_usages,
    compute_ast_delta,
    cross_node_reference_errors,
    evaluate_runtime_drift,
    extract_designer_orphan_groups,
    extract_error_directives,
    extract_forman_mapping_events,
    extract_latency_observations,
    extract_runtime_filter_conditions,
    extract_runtime_notes,
    extract_runtime_sample_observations,
    infer_module_role,
    iter_ast_execution_paths,
    iter_ast_nodes,
    iter_top_level_nodes,
    module_looks_like_trigger,
    module_looks_like_webhook_response,
    note_binding_errors,
    parse_make_ast,
    parse_make_ast_json_text,
    persist_make_blueprint_bundle,
    plan_blueprint_layout,
    require_ast_node,
    rewrite_cross_node_references,
    slugify_blueprint_name,
    validate_make_blueprint_bundle_collection,
)

from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from blueprints.ast import (
        JsonObject,
        MakeAstFilter,
        MakeAstNode,
        MakeAstRoot,
    )

EXPECTED_NODE_IDS = ("1", "2", "3", "11", "4", "12", "5", "6", "7", "8", "9")
EXPECTED_DESIGNER_MESSAGE_PATHS = 2
REWRITTEN_FIRST_NODE_ID = 11
REWRITTEN_SECOND_NODE_ID = 22
EXPECTED_LAYOUT_MODULES = 4
LAYOUT_COLUMN_SPACING = 250
LAYOUT_ROW_SPACING = 400
MALFORMED_DESIGNER_STEP_ID = 1.5
BUNDLE_VALIDATION_DRIFT_CASES = (
    (
        "checksum ",
        "drift-demo: source_ast.json checksum does not match manifest.",
    ),
    (
        "manifest_path",
        (
            "drift-demo: manifest files entry for source_ast must point at "
            "data/blueprints/drift-demo/source_ast.json."
        ),
    ),
    (
        "unknown_entry ",
        "drift-demo: manifest entry for sidecar is not a known bundle file.",
    ),
    (
        "missing_checksum ",
        "drift-demo: manifest checksum for source_ast is required.",
    ),
)
REPO_ROOT = repo_root()
AST_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "make_ast"
    / "lead_routing_blueprint.json"
)
AST_FIXTURE_README = (
    REPO_ROOT / "tests" / "blueprints" / "fixtures" / "make_ast" / "README.md"
)


def _ast_traversal_contract(
    root: MakeAstRoot,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Return stable root traversal identity."""
    nodes = iter_ast_nodes(root)
    by_id = {node.node_id: node for node in nodes}
    return collect_ast_node_ids(root), _actual_node_kinds(by_id)


def _actual_node_kinds(by_id: dict[str, MakeAstNode]) -> dict[str, str]:
    """Return expected-node kind classifications from a parsed AST."""
    return {node_id: by_id[node_id].kind for node_id in _expected_node_kinds()}


def _expected_node_kinds() -> dict[str, str]:
    """Return expected AST node kind classifications."""
    return {
        "1": "webhook ",
        "2": "router ",
        "3": "http_api ",
        "4": "data_store ",
        "12": "data_store ",
        "5": "iterator ",
        "6": "aggregator ",
        "7": "ai_agent ",
        "8": "mcp_tool ",
        "9": "unresolved ",
        "11": "error_handler",
    }


def _assert_scenario_contract(root: MakeAstRoot) -> None:
    """Assert typed scenario metadata on a parsed AST root."""
    assert root.scenario.name == "lead-routing-demo", (
        f"Unexpected scenario name: {root.scenario.name}"
    )
    assert tuple(endpoint.kind for endpoint in root.scenario.inputs) == (
        "scenario_input",
    ), f"Scenario inputs were not typed: {root.scenario.inputs}"
    assert tuple(endpoint.kind for endpoint in root.scenario.outputs) == (
        "scenario_output",
    ), f"Scenario outputs were not typed: {root.scenario.outputs}"
    assert root.scenario.schedule is not None, (
        f"Schedule config was not typed: {root.scenario.schedule}"
    )
    assert root.scenario.schedule.kind == "schedule_trigger", (
        f"Schedule config was not typed: {root.scenario.schedule}"
    )


def _assert_ast_note_metadata(root: MakeAstRoot) -> None:
    """Assert Make-native note anchoring and metadata preservation."""
    notes_value = root.scenario.metadata.get("notes")
    assert isinstance(notes_value, list), (
        f"Make-native notes were not preserved: {root.scenario.metadata}"
    )
    notes = cast("list[object]", notes_value)
    assert len(notes) == 1, (
        f"Make-native notes were not preserved: {root.scenario.metadata}"
    )
    note_value = notes[0]
    assert isinstance(note_value, dict), (
        f"Make-native note anchoring was not preserved: {note_value}"
    )
    note = cast("JsonObject", note_value)
    assert note.get("moduleIds") == [3], (
        f"Make-native note anchoring was not preserved: {note}"
    )
    note_metadata_value = note.get("metadata")
    assert isinstance(note_metadata_value, dict), (
        f"Make-native note color metadata was not preserved: {note}"
    )
    note_metadata = cast("JsonObject", note_metadata_value)
    assert note_metadata.get("color") == "#9138FE", (
        f"Make-native note color metadata was not preserved: {note}"
    )


def test_make_ast_parses_core_node_categories_and_scenario_metadata() -> None:
    """AST parsing covers the core node categories required by doctrine."""
    root = parse_make_ast(make_blueprint_payload())
    traversal_ids, actual_kinds = _ast_traversal_contract(root)

    assert traversal_ids == EXPECTED_NODE_IDS, (
        f"AST traversal IDs changed: {traversal_ids}"
    )
    assert actual_kinds == _expected_node_kinds(), (
        f"AST node kinds changed: {actual_kinds}"
    )
    _assert_scenario_contract(root)
    _assert_ast_note_metadata(root)


def test_make_ast_preserves_unknown_fields_and_raw_spec_bindings() -> None:
    """AST parsing preserves unknown fields and raw-spec binding metadata."""
    root = parse_make_ast(make_blueprint_payload())
    http_node = require_ast_node(root, "3")
    unknown_node = require_ast_node(root, "9")

    assert http_node.unknown_fields.get("x-vendor-extra") == {"kept": True}, (
        f"Unknown node fields were not preserved: {http_node.unknown_fields}"
    )
    assert http_node.raw_spec_binding.status == "resolved", (
        f"Raw-spec binding was not parsed: {http_node.raw_spec_binding}"
    )
    assert (
        http_node.raw_spec_binding.catalog_module_id
        == "module:http:1.0:action:makeRequest"
    ), f"Unexpected catalog binding: {http_node.raw_spec_binding}"
    assert unknown_node.kind == "unresolved", (
        f"Unsupported module tokens must become unresolved: {unknown_node}"
    )
    assert unknown_node.unknown_fields.get("opaque") == {"future": "value"}, (
        f"Unknown unresolved payload was not retained: {unknown_node}"
    )


def test_make_ast_preserves_invalid_raw_spec_binding_as_issue() -> None:
    """Malformed repository raw-spec metadata does not abort AST parsing."""
    root = parse_make_ast(
        {
            "name": "invalid-raw-spec-binding",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "metadata": {"raw_spec": "broken"},
                },
                {
                    "id": 2,
                    "module": "json:ParseJSON",
                    "raw_spec": {"issues": "broken"},
                },
                {
                    "id": 3,
                    "module": "email:SendEmail",
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": ["module:email"],
                            "raw_spec_sha256": True,
                            "status": False,
                        }
                    },
                },
                {
                    "id": 4,
                    "module": "tools:Sleep",
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": "module:tools:sleep",
                            "issues": ["kept", True],
                        }
                    },
                },
            ],
        }
    )

    first = require_ast_node(root, "1")
    second = require_ast_node(root, "2")
    third = require_ast_node(root, "3")
    fourth = require_ast_node(root, "4")
    assert first.raw_spec_binding.issues == ("invalid_raw_spec_binding",), (
        f"Invalid metadata raw_spec should be preserved as an issue: {first}"
    )
    assert second.raw_spec_binding.issues == ("invalid_raw_spec_binding",), (
        f"Invalid top-level raw_spec issues should be preserved as an "
        f"issue: {second}"
    )
    assert not (third.raw_spec_binding.catalog_module_id is not None), (
        f"Invalid catalog module IDs must not be string-coerced: {third}"
    )
    assert not (third.raw_spec_binding.raw_spec_sha256 is not None), (
        f"Invalid raw-spec hashes must not be string-coerced: {third}"
    )
    assert third.raw_spec_binding.status == "unresolved", (
        f"Invalid raw-spec statuses must fall back to unresolved: {third}"
    )
    assert third.raw_spec_binding.issues == ("invalid_raw_spec_binding",), (
        f"Invalid raw-spec fields should be preserved as an issue: {third}"
    )
    assert fourth.raw_spec_binding.issues == ("invalid_raw_spec_binding",), (
        f"Non-string raw-spec issues should be preserved as an issue: {fourth}"
    )


def test_make_ast_source_trace_and_nested_routes_are_stable() -> None:
    """AST traversal records parent, route, tool, and error-handler source.

    traces.
    """
    root = parse_make_ast(make_blueprint_payload())
    router = require_ast_node(root, "2")
    route = router.routes[0]
    http_node = require_ast_node(root, "3")
    error_handler = require_ast_node(root, "11")
    tool_node = require_ast_node(root, "8")

    assert route.filter is not None, (
        f"Route filter was not typed: {route.filter}"
    )
    assert route.filter.kind == "filter", (
        f"Route filter was not typed: {route.filter}"
    )
    assert http_node.source_trace.parent_node_id == "2", (
        f"Nested route parent trace is wrong: {http_node.source_trace}"
    )
    assert http_node.source_trace.path == ("flow", 1, "routes", 0, "flow", 0), (
        f"Nested route path is wrong: {http_node.source_trace.path}"
    )
    assert error_handler.source_trace.parent_node_id == "3", (
        f"Error handler parent trace is wrong: {error_handler.source_trace}"
    )
    assert error_handler.source_trace.container_kind == "onerror", (
        f"Error handler container is wrong: {error_handler.source_trace}"
    )
    assert tool_node.source_trace.parent_node_id == "7", (
        f"Tool parent trace is wrong: {tool_node.source_trace}"
    )
    assert tool_node.source_trace.container_kind == "tools", (
        f"Tool container is wrong: {tool_node.source_trace}"
    )


def test_make_ast_error_handler_flow_wrappers_expand_children() -> None:
    """Direct error-handler flow wrappers are traversal containers, not.

    nodes.
    """
    root = parse_make_ast(
        {
            "name": "error-handler-flow-wrapper",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "onerror": [
                        {
                            "flow": [
                                {"id": 11, "module": "builtin:Ignore"},
                                {"id": 12, "module": "builtin:Break"},
                            ]
                        }
                    ],
                }
            ],
        }
    )

    parent = require_ast_node(root, "1")
    handler_ids = tuple(node.node_id for node in parent.error_handlers)
    assert handler_ids == ("11", "12"), (
        f"Error-handler flow wrapper was not expanded: {handler_ids}"
    )
    first_handler = require_ast_node(root, "11")
    assert first_handler.source_trace.parent_node_id == "1", (
        f"Flow-wrapper handler parent trace is wrong: "
        f"{first_handler.source_trace}"
    )
    assert first_handler.source_trace.path == (
        "flow",
        0,
        "onerror",
        0,
        "flow",
        0,
    ), f"Flow-wrapper handler path is wrong: {first_handler.source_trace.path}"


def test_make_ast_execution_paths_expand_route_like_children() -> None:
    """Execution paths include root flow plus route, branch, and tool child.

    flows.
    """
    root = parse_make_ast(
        {
            "name": "execution-paths",
            "flow": [
                {"id": "1", "module": "gateway:CustomWebHook"},
                {
                    "id": "2 ",
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {"flow": [{"id": "3", "module": "http:MakeRequest"}]},
                        {"flow": [{"id": "4", "module": "json:ParseJSON"}]},
                    ],
                },
                {
                    "id": "5 ",
                    "module": "builtin:BasicIfElse",
                    "branches": [
                        {"flow": [{"id": "6", "module": "util:SetVariable"}]}
                    ],
                },
                {
                    "id": "7 ",
                    "module": "ai-local-agent:RunLocalAIAgent",
                    "tools": [
                        {"flow": [{"id": "8", "module": "make:ReturnOutput"}]}
                    ],
                },
            ],
        }
    )

    path_ids = tuple(
        tuple(node.node_id for node in path)
        for path in iter_ast_execution_paths(root)
    )

    assert path_ids == (
        ("1", "2", "3", "5", "6", "7", "8"),
        ("1", "2", "4", "5", "6", "7", "8"),
    ), f"Execution paths did not expand route-like children: {path_ids}"


def test_make_ast_delta_tracks_added_removed_and_changed_paths() -> None:
    """AST deltas report deterministic JSON paths for payload changes."""
    before: JsonObject = {
        "name": "demo",
        "flow": [
            {"id": 1, "module": "http:MakeRequest", "mapper": {"url": "old"}},
            {"id": 2, "module": "json:ParseJSON"},
        ],
        "metadata": {"schedule": {"id": "daily"}},
    }
    after: JsonObject = {
        "name": "demo",
        "flow": [
            {"id": 1, "module": "http:MakeRequest", "version": 1},
            {"id": 3, "module": "slack:CreateMessage"},
            {"id": 4, "module": "email:SendEmail"},
        ],
        "metadata": {"scenario": {"name": "demo"}},
    }

    delta = compute_ast_delta(before, after)

    for path in ("$.flow[0].version", "$.flow[2]", "$.metadata.scenario"):
        assert not (path not in delta.added_paths), (
            f"Delta missed added path {path}: {delta}"
        )
    for path in ("$.flow[0].mapper", "$.metadata.schedule"):
        assert not (path not in delta.removed_paths), (
            f"Delta missed removed path {path}: {delta}"
        )
    for path in ("$.flow[1].id", "$.flow[1].module"):
        assert not (path not in delta.changed_paths), (
            f"Delta missed changed path {path}: {delta}"
        )
    assert delta.as_dict()["has_changes"], (
        f"Delta did not report changes: {delta}"
    )


def test_make_ast_evidence_reports_opaque_and_designer_paths() -> None:
    """AST evidence reports local opaque fields and designer message.

    locations.
    """
    payload: JsonObject = {
        "name": "evidence",
        "metadata": {
            "designer": {"messages": [{"message": "ready"}]},
            "custom_meta": True,
        },
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "metadata": {
                    "designer": {
                        "x": 1,
                        "y": 2,
                        "messages": [{"message": "reauth"}],
                    },
                    "custom_node_meta": "kept",
                },
                "x-extra": True,
            }
        ],
    }
    report = ast_evidence_report(parse_make_ast(payload))

    for path in ("$.metadata.custom_meta", "$.flow[0].x-extra"):
        assert not (path not in report.opaque_field_paths), (
            f"Evidence missed opaque path {path}: {report}"
        )
    assert not (
        "$.flow[0].metadata.custom_node_meta" not in report.opaque_field_paths
    ), f"Evidence missed node metadata path: {report}"
    assert report.designer_message_count == EXPECTED_DESIGNER_MESSAGE_PATHS, (
        f"Evidence missed designer message paths: {report}"
    )
    assert not (
        "$.metadata.designer.messages" not in report.designer_message_paths
    ), f"Evidence missed root designer messages: {report}"
    assert not (
        "$.flow[0].metadata.designer.messages"
        not in report.designer_message_paths
    ), f"Evidence missed node designer messages: {report}"


def test_make_ast_runtime_metadata_ignores_business_payload_fields() -> None:
    """Runtime metadata comes only from Make designer containers."""
    root = parse_make_ast(runtime_metadata_payload())

    filters = extract_runtime_filter_conditions(root)
    directives = extract_error_directives(root)
    notes = extract_runtime_notes(root)
    orphans = extract_designer_orphan_groups(root)
    messages = collect_designer_message_evidence(root)
    latency = extract_latency_observations(root)
    events = extract_forman_mapping_events(root)
    samples = extract_runtime_sample_observations(root)

    assert tuple(
        (item.label_name, item.operator, item.right_operand) for item in filters
    ) == (("Only urgent", "equal", "high"),), (
        f"Runtime filter extraction drifted: {filters}"
    )
    assert tuple(
        (item.strategy, item.attempt_count, item.interval, item.retry)
        for item in directives
    ) == (
        ("builtin:Ignore", None, None, False),
        ("builtin:Break", 2, 30, True),
    ), f"Error directive normalization drifted: {directives}"
    assert tuple((item.note_id, item.text, item.color) for item in notes) == (
        ("n1", "Native Make note", "#123456"),
    ), f"Runtime notes should ignore mapper notes: {notes}"
    assert tuple(
        (group.group_index, group.nodes[0].node_id) for group in orphans
    ) == ((0, "7"),), f"Designer orphan extraction drifted: {orphans}"
    assert tuple(item.signature for item in messages) == (
        "setup|warning|Real designer warning ",
        "setup|error|Connection empty",
    ), f"Designer messages should ignore business arrays: {messages}"
    observed_latency = tuple(
        (item.node_id, item.elapsed_seconds, item.element_actions_count)
        for item in latency
    )
    assert observed_latency == (("1", 2.93, 2),), (
        f"Latency extraction should ignore boolean elapsed values: {latency}"
    )
    assert tuple(item.get("source") for item in events) == (
        "root_metadata ",
        "designer_metadata",
    ), f"Forman event extraction should ignore mapper events: {events}"
    assert tuple(item.node_id for item in samples) == ("3",), (
        f"Designer sample extraction should ignore business samples: {samples}"
    )
    sample = samples[0]
    assert sample.sample_path == "$.metadata.designer.samples.3", (
        f"Designer sample path drifted: {sample}"
    )
    assert sample.sample_keys == (
        "jsonResponse ",
        "metadata ",
        "response ",
        "threadId",
    ), f"Designer sample keys drifted: {sample}"
    assert sample.metadata_keys == (
        "executionSteps ",
        "executionTimeMs ",
        "lastAgentIterationId ",
        "tokenUsageSummary",
    ), f"Designer sample metadata keys drifted: {sample}"
    assert sample.execution_step_count == 1, (
        f"Execution step count drifted: {sample}"
    )
    assert sample.token_usage_keys == (
        "completionTokens ",
        "promptTokens ",
        "totalTokens",
    ), f"Token usage keys drifted: {sample}"
    assert len(sample.shape_fingerprint_sha256) == 64, (
        f"Sample shape fingerprint must be a SHA-256 hex digest: {sample}"
    )
    _ = int(sample.shape_fingerprint_sha256, 16)


def test_make_ast_designer_orphans_ignore_container_identifiers() -> None:
    """Designer orphan extraction must not coerce container values into.

    identifiers.
    """
    payload = runtime_metadata_payload()
    metadata = cast("JsonObject", payload["metadata"])
    designer = cast("JsonObject", metadata["designer"])
    designer["orphans"] = [
        [
            {"id": ["7"], "module": "tools:Repeater"},
            {"id": "8", "module": {"token": "tools:Repeater"}},
            {"id": 9, "module": "tools:Repeater"},
        ]
    ]

    orphans = extract_designer_orphan_groups(parse_make_ast(payload))

    assert tuple(
        (node.node_id, node.module_token) for node in orphans[0].nodes
    ) == (("9", "tools:Repeater"),), (
        f"Designer orphan extraction coerced invalid identifiers: {orphans}"
    )


def test_make_ast_runtime_notes_ignore_container_text_fields() -> None:
    """Runtime notes must preserve only textual designer note payloads."""
    payload = runtime_metadata_payload()
    metadata = cast("JsonObject", payload["metadata"])
    metadata["notes"] = [
        {"id": "bad", "content": {"html": "<p>not text</p>"}},
        {
            "id": ["bad"],
            "content": "<p>Valid note</p>",
            "metadata": {"color": ["#bad"]},
        },
        {"id": 3, "html": "<b>Number id</b>", "color": "#abcdef"},
    ]

    notes = extract_runtime_notes(parse_make_ast(payload))

    assert tuple((note.note_id, note.text, note.color) for note in notes) == (
        ("note:2", "Valid note", None),
        ("3", "Number id", "#abcdef"),
    ), f"Runtime note extraction coerced malformed fields: {notes}"


def test_make_ast_error_directives_preserve_zero_retry_values() -> None:
    """Error-directive extraction treats explicit zero retry values as.

    present.
    """
    root = parse_make_ast(
        {
            "name": "zero-retry-directive",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "onerror": {
                        "module": "builtin:Break",
                        "count": 3,
                        "interval": 30,
                        "retry": {"count": 0, "interval": 0},
                    },
                }
            ],
        }
    )

    directives = extract_error_directives(root)

    assert tuple(
        (item.attempt_count, item.interval, item.retry) for item in directives
    ) == ((0, 0, True),), (
        f"Zero retry directive values were not preserved: {directives}"
    )


def test_make_ast_error_directives_ignore_negative_retry_values() -> None:
    """Negative retry counts and intervals are not normalized into usable.

    metadata.
    """
    root = parse_make_ast(
        {
            "name": "negative-retry-directive",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "onerror": {
                        "module": "builtin:Break",
                        "retry": {"count": -1, "interval": -10},
                    },
                }
            ],
        }
    )

    directives = extract_error_directives(root)

    assert tuple(
        (item.attempt_count, item.interval) for item in directives
    ) == ((None, None),), (
        f"Negative retry values should not be retained: {directives}"
    )


def test_make_ast_latency_observations_ignore_non_finite_elapsed_strings() -> (
    None
):
    """Latency metadata ignores non-finite string values instead of reporting.

    infinity.
    """
    root = parse_make_ast(
        {
            "name": "non-finite-latency",
            "flow": [
                {"id": 1, "module": "http:MakeRequest", "elapsed": "inf"},
                {
                    "id": 2,
                    "module": "http:MakeRequest",
                    "metadata": {"elapsed": "nan"},
                },
            ],
        }
    )

    latency = extract_latency_observations(root)

    assert not (latency), (
        f"Non-finite elapsed strings should not become latency: {latency}"
    )


def test_make_ast_designer_message_evidence_b8cd3446() -> None:
    """Same-text designer warnings on different fields remain separate.

    evidence.
    """
    root = parse_make_ast(
        {
            "name": "designer-field-evidence",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "metadata": {
                        "designer": {
                            "messages": [
                                {
                                    "category": "required ",
                                    "severity": "warning ",
                                    "message": "Missing required field.",
                                    "field": "parameters.email",
                                },
                                {
                                    "category": "required ",
                                    "severity": "warning ",
                                    "message": "Missing required field.",
                                    "field": "parameters.name",
                                },
                            ]
                        }
                    },
                }
            ],
        }
    )

    messages = collect_designer_message_evidence(root)

    assert len(messages) == EXPECTED_DESIGNER_MESSAGE_PATHS, (
        f"Field-specific designer messages were collapsed: {messages}"
    )
    field_paths = tuple(
        sorted(str(message.payload.get("field")) for message in messages)
    )
    assert field_paths == ("parameters.email", "parameters.name"), (
        f"Field-specific designer evidence drifted: {messages}"
    )


def test_make_ast_designer_message_evidence_includes_orphan_modules() -> None:
    """Designer messages on orphaned modules remain visible to local parity.

    checks.
    """
    root = parse_make_ast(
        {
            "name": "orphan-designer-evidence",
            "flow": [],
            "metadata": {
                "designer": {
                    "orphans": [
                        [
                            {
                                "id": 4,
                                "module": "google-email:triggerWatchNewEmails",
                                "metadata": {
                                    "designer": {
                                        "messages": [
                                            {
                                                "category": "link ",
                                                "severity": "warning",
                                                "message": (
                                                    "This module is not "
                                                    "connected to the flow. "
                                                    "<autoconnect>Link "
                                                    "it.</autoconnect>"
                                                ),
                                            },
                                            {
                                                "category": "setupreq ",
                                                "severity": "error",
                                                "message": (
                                                    "The module is not set up."
                                                ),
                                            },
                                            {
                                                "category": "epochreq ",
                                                "severity": "error",
                                                "message": (
                                                    "You must first choose "
                                                    "from which point to "
                                                    "start processing your "
                                                    "emails."
                                                ),
                                            },
                                        ]
                                    }
                                },
                            }
                        ]
                    ]
                }
            },
        }
    )

    report = ast_evidence_report(root)
    messages = collect_designer_message_evidence(root)

    orphan_path = "$.metadata.designer.orphans[0][0].metadata.designer.messages"
    assert orphan_path in report.designer_message_paths, (
        f"Orphan designer message path was not reported: {report}"
    )
    assert tuple(message.node_id for message in messages) == ("4", "4", "4"), (
        f"Orphan designer messages lost node identity: {messages}"
    )
    assert tuple(message.module_token for message in messages) == (
        "google-email:triggerWatchNewEmails ",
        "google-email:triggerWatchNewEmails ",
        "google-email:triggerWatchNewEmails",
    ), f"Orphan designer messages lost module identity: {messages}"
    assert {message.signature for message in messages} == {
        (
            "epochreq|error|You must first choose from which point to start "
            "processing your emails."
        ),
        (
            "link|warning|This module is not connected to the flow. "
            "<autoconnect>Link it.</autoconnect>"
        ),
        "setupreq|error|The module is not set up.",
    }, f"Orphan designer messages were not preserved: {messages}"


def test_make_ast_runtime_metadata_extracts_74bec6c4() -> None:
    """Runtime metadata supports canonical object-shaped filter conditions."""
    root = parse_make_ast(
        {
            "name": "canonical-filter-condition",
            "flow": [
                {
                    "id": 1,
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "filter": {
                                "name": "High score",
                                "conditions": {
                                    "left": "{{1.score}}",
                                    "op": "gt",
                                    "right": 80,
                                },
                            },
                            "flow": [{"id": 2, "module": "http:MakeRequest"}],
                        }
                    ],
                }
            ],
        }
    )

    conditions = extract_runtime_filter_conditions(root)

    assert tuple(
        (item.label_name, item.left_operand, item.operator, item.right_operand)
        for item in conditions
    ) == (("High score", "{{1.score}}", "gt", "80"),), (
        f"Canonical object filter condition was not extracted: {conditions}"
    )


def test_make_ast_runtime_metadata_extracts_make_native_o_operator() -> None:
    """Runtime metadata reads Make-native filter operator key `o`."""
    root = parse_make_ast(
        {
            "name": "native-o-filter-condition",
            "flow": [
                {
                    "id": 1,
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "filter": {
                                "name": "Email domain",
                                "conditions": [
                                    [
                                        {
                                            "a": "{{1.email}}",
                                            "o": "text:contains:ci ",
                                            "b": "@",
                                        }
                                    ]
                                ],
                            },
                            "flow": [{"id": 2, "module": "http:MakeRequest"}],
                        }
                    ],
                }
            ],
        }
    )

    conditions = extract_runtime_filter_conditions(root)

    assert tuple(
        (item.label_name, item.left_operand, item.operator, item.right_operand)
        for item in conditions
    ) == (("Email domain", "{{1.email}}", "text:contains:ci", "@"),), (
        f"Make-native `o` operator was not extracted: {conditions}"
    )


def test_make_ast_runtime_metadata_extracts_filter_condition_aliases() -> None:
    """Runtime metadata supports ADR-approved filter condition aliases."""
    root = parse_make_ast(
        {
            "name": "runtime-filter-aliases",
            "flow": [
                {
                    "id": "router ",
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "filter": {
                                "name": "Text condition ",
                                "condition": "{{1.amount}} > 500",
                            },
                            "flow": [],
                        },
                        {
                            "filter": {
                                "name": "Condition object",
                                "condition": {
                                    "left": "{{1.amount}}",
                                    "op": "gte",
                                    "right": 500,
                                },
                            },
                            "flow": [],
                        },
                        {
                            "filter": {
                                "label": "Rule list",
                                "rules": [
                                    {
                                        "field": "status ",
                                        "operator": "equal ",
                                        "value": "ready",
                                    }
                                ],
                            },
                            "flow": [],
                        },
                        {
                            "filter": {
                                "label": "Rule object",
                                "rules": {
                                    "field": "priority ",
                                    "op": "gt",
                                    "value": 3,
                                },
                            },
                            "flow": [],
                        },
                        {
                            "filter": {
                                "name": "Expression object",
                                "expression": {
                                    "left": "{{1.score}}",
                                    "op": "gt",
                                    "right": 80,
                                },
                            },
                            "flow": [],
                        },
                        {
                            "filter": {
                                "name": "Expression scalar ",
                                "expression": "{{1.enabled}} = true",
                            },
                            "flow": [],
                        },
                    ],
                }
            ],
        }
    )

    conditions = extract_runtime_filter_conditions(root)

    assert tuple(
        (
            item.label_name,
            item.left_operand,
            item.operator,
            item.right_operand,
            item.combinator,
        )
        for item in conditions
    ) == (
        ("Text condition", "{{1.amount}} > 500", "", "", None),
        ("Condition object", "{{1.amount}}", "gte", "500", None),
        ("Rule list", "status", "equal", "ready", None),
        ("Rule object", "priority", "gt", "3", None),
        ("Expression object", "{{1.score}}", "gt", "80", None),
        ("Expression scalar", "{{1.enabled}} = true", "", "", None),
    ), f"Filter condition aliases were not extracted: {conditions}"


def test_make_ast_filter_metadata_does_not_stringify_container_operands() -> (
    None
):
    """Runtime filter metadata ignores object operands instead of converting.

    them.

    to text.
    """
    root = parse_make_ast(
        {
            "name": "filter-container-operands",
            "flow": [
                {
                    "id": "router ",
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "filter": {
                                "label_name": {"bad": True},
                                "conditions": [
                                    {
                                        "left": {"bad": True},
                                        "operator": "equal",
                                        "right": {"bad": True},
                                    }
                                ],
                            },
                            "flow": [],
                        }
                    ],
                }
            ],
        }
    )

    conditions = extract_runtime_filter_conditions(root)

    assert tuple(
        (item.label_name, item.left_operand, item.operator, item.right_operand)
        for item in conditions
    ) == ((None, "", "equal", ""),), (
        f"Container operands should not be stringified: {conditions}"
    )


def test_make_ast_layout_plan_apply_and_transition_are_deterministic() -> None:
    """Layout planning writes deterministic designer coordinates and transition.

    evidence.
    """
    source = parse_make_ast(layout_payload(with_coordinates=False))
    baseline = parse_make_ast(layout_payload(with_coordinates=True))
    plan = plan_blueprint_layout(
        source,
        column_spacing=LAYOUT_COLUMN_SPACING,
        row_spacing=LAYOUT_ROW_SPACING,
    )

    assert tuple(
        (item.node_id, item.depth, item.lane, item.x, item.y)
        for item in plan.layouts
    ) == (
        ("1", 0, 0, 0, 0),
        ("2", 1, 1, LAYOUT_COLUMN_SPACING, LAYOUT_ROW_SPACING),
        ("3", 2, 1, LAYOUT_COLUMN_SPACING * 2, LAYOUT_ROW_SPACING),
        ("4", 1, 2, LAYOUT_COLUMN_SPACING, LAYOUT_ROW_SPACING * 2),
    ), f"Layout planner changed traversal semantics: {plan.layouts}"

    rendered = apply_blueprint_layout(source, plan)
    after = parse_make_ast(rendered)
    transition = analyze_blueprint_layout_transition(baseline, after)

    assert transition.module_count == EXPECTED_LAYOUT_MODULES, (
        f"Layout transition did not capture all movements: {transition}"
    )
    assert transition.moved_count == EXPECTED_LAYOUT_MODULES, (
        f"Layout transition did not capture all movements: {transition}"
    )
    assert transition.inferred_column_spacing == LAYOUT_COLUMN_SPACING, (
        f"Layout spacing inference drifted: {transition}"
    )
    assert transition.inferred_row_spacing == LAYOUT_ROW_SPACING, (
        f"Layout spacing inference drifted: {transition}"
    )
    first_node = object_at(list_member(rendered, "flow"), 0)
    metadata = object_member(first_node, "metadata")
    designer = object_member(metadata, "designer")
    assert (designer.get("x"), designer.get("y")) == (0, 0), (
        f"Applied layout did not write designer coordinates: {designer}"
    )


def test_make_ast_layout_transition_ignores_fractional_coordinates() -> None:
    """Layout analysis must not truncate fractional designer coordinates."""
    before = parse_make_ast(layout_payload(with_coordinates=True))
    after_payload = layout_payload(with_coordinates=True)
    first_node = object_at(list_member(after_payload, "flow"), 0)
    metadata = object_member(first_node, "metadata")
    designer = object_member(metadata, "designer")
    designer["x"] = 75.5
    after = parse_make_ast(after_payload)

    transition = analyze_blueprint_layout_transition(before, after)
    first_movement = transition.movements[0]

    assert not (first_movement.after[0] is not None), (
        f"Fractional coordinates should not be truncated: {first_movement}"
    )
    assert not (first_movement.delta[0] is not None), (
        f"Fractional coordinates should not be truncated: {first_movement}"
    )


def test_make_ast_runtime_drift_accepts_coordinate_normalization_only() -> None:
    """Runtime drift accepts designer coordinate changes but rejects semantic.

    changes.
    """
    before = parse_make_ast(layout_payload(with_coordinates=True))
    coordinate_after = parse_make_ast(
        layout_payload(with_coordinates=True, first_x=75)
    )
    semantic_after = parse_make_ast(
        layout_payload(
            with_coordinates=True, first_module="slack:CreateMessage"
        )
    )

    coordinate_drift = evaluate_runtime_drift(before, coordinate_after)
    semantic_drift = evaluate_runtime_drift(before, semantic_after)

    assert coordinate_drift.accepted, (
        f"Coordinate-only drift should be accepted: {coordinate_drift}"
    )
    assert coordinate_drift.accepted_changed_paths == (
        "$.flow[0].metadata.designer.x",
    ), f"Accepted drift path changed: {coordinate_drift}"
    assert not (semantic_drift.accepted), (
        f"Semantic drift must not be accepted: {semantic_drift}"
    )
    assert not (
        "$.flow[0].module" not in semantic_drift.unsupported_changed_paths
    ), f"Semantic drift path was not reported: {semantic_drift}"


def test_make_ast_runtime_drift_rejects_3b3a803e() -> None:
    """Runtime drift does not accept business payloads that resemble designer.

    coordinates.
    """
    before_payload = layout_payload(with_coordinates=True)
    before_node = object_at(list_member(before_payload, "flow"), 0)
    before_node["mapper"] = {"metadata": {"designer": {"x": 1}}}
    after_payload = layout_payload(with_coordinates=True)
    after_node = object_at(list_member(after_payload, "flow"), 0)
    after_node["mapper"] = {"metadata": {"designer": {"x": 2}}}

    drift = evaluate_runtime_drift(
        parse_make_ast(before_payload), parse_make_ast(after_payload)
    )

    assert not (drift.accepted), (
        f"Business designer-like payload drift must not be accepted: {drift}"
    )
    assert not (
        "$.flow[0].mapper.metadata.designer.x"
        not in drift.unsupported_changed_paths
    ), f"Business designer-like drift path was not reported: {drift}"
    assert (
        "$.flow[0].mapper.metadata.designer.x"
        not in drift.accepted_changed_paths
    ), f"Business designer-like drift path was accepted: {drift}"


def test_make_ast_blueprint_bundles_persist_under_data(tmp_path: Path) -> None:
    """Blueprint bundles persist under data/blueprints with relative.

    manifests.
    """
    empty_flow: list[object] = []
    empty_metadata: JsonObject = {}
    opaque_paths: list[object] = []
    source_ast: JsonObject = {
        "name": "demo",
        "flow": empty_flow,
        "metadata": empty_metadata,
    }
    observability_report: JsonObject = {"opaque_field_paths": opaque_paths}
    written = persist_make_blueprint_bundle(
        repo_root=tmp_path,
        blueprint_name=" Customer Feedback Agent ",
        payloads=MakeBlueprintBundlePayloads(
            source_ast=source_ast,
            observability_report=observability_report,
        ),
    )

    expected_root = tmp_path / "data" / "blueprints" / "customer-feedback-agent"
    manifest_path = expected_root / "manifest.json"
    assert not ((tmp_path / "artifacts").exists()), (
        "Blueprint bundle persistence must not create root artifacts/."
    )
    assert (
        written["source_ast"]
        == "data/blueprints/customer-feedback-agent/source_ast.json"
    ), f"Bundle paths must be repository-relative: {written}"
    report = validate_make_blueprint_bundle_collection(
        tmp_path / "data" / "blueprints"
    )
    assert report["valid"], (
        f"Blueprint bundle collection did not validate: {report}"
    )
    assert report["bundle_count"] == 1, (
        f"Blueprint bundle collection did not validate: {report}"
    )
    assert manifest_path.is_file(), (
        f"Blueprint bundle manifest was not written: {expected_root}"
    )
    manifest = object_from_json_file(manifest_path)
    checksums = object_member(manifest, "checksums_sha256")
    source_hash = hashlib.sha256(
        (expected_root / "source_ast.json").read_bytes()
    ).hexdigest()
    assert checksums.get("source_ast") == source_hash, (
        f"Blueprint bundle checksum did not match source_ast.json: {manifest}"
    )


@pytest.mark.parametrize(
    ("case_name", "expected_error"),
    BUNDLE_VALIDATION_DRIFT_CASES,
    ids=tuple(
        case_name
        for case_name, _expected_error in BUNDLE_VALIDATION_DRIFT_CASES
    ),
)
def test_make_ast_blueprint_bundle_validation_rejects_manifest_drift(
    tmp_path: Path,
    case_name: str,
    expected_error: str,
) -> None:
    """Blueprint bundle validation reports manifest drift cases."""
    source_ast: JsonObject = {"name": "demo", "flow": [], "metadata": {}}
    _ = persist_make_blueprint_bundle(
        repo_root=tmp_path,
        blueprint_name="Drift Demo",
        payloads=MakeBlueprintBundlePayloads(source_ast=source_ast),
    )
    bundle_root = tmp_path / "data" / "blueprints" / "drift-demo"
    _apply_bundle_validation_drift(case_name, bundle_root=bundle_root)

    report = validate_make_blueprint_bundle_collection(
        tmp_path / "data" / "blueprints"
    )
    errors = cast("list[object]", report["errors"])
    assert not (expected_error not in errors), (
        f"Bundle manifest drift case {case_name!r} was not reported: {report}"
    )


def test_make_ast_blueprint_bundle_validation_rejects_non_standard_json(
    tmp_path: Path,
) -> None:
    """Blueprint bundle validation rejects Python JSON parser extensions."""
    source_ast: JsonObject = {"name": "demo", "flow": [], "metadata": {}}
    _ = persist_make_blueprint_bundle(
        repo_root=tmp_path,
        blueprint_name="Non Standard Json Demo",
        payloads=MakeBlueprintBundlePayloads(source_ast=source_ast),
    )
    bundle_root = tmp_path / "data" / "blueprints" / "non-standard-json-demo"
    source_content = '{"name":"demo","flow":[],"metadata":{"score":NaN}}\n'
    _ = (bundle_root / "source_ast.json").write_text(
        source_content, encoding="utf-8"
    )
    manifest = object_from_json_file(bundle_root / "manifest.json")
    object_member(manifest, "checksums_sha256")["source_ast"] = hashlib.sha256(
        source_content.encode()
    ).hexdigest()
    _write_json_file(bundle_root / "manifest.json", manifest)

    report = validate_make_blueprint_bundle_collection(
        tmp_path / "data" / "blueprints"
    )
    errors = cast("list[object]", report["errors"])

    assert not (
        "non-standard-json-demo: source_ast.json must contain an object."
        not in errors
    ), f"Non-standard JSON bundle source was accepted: {report}"


def _apply_bundle_validation_drift(
    case_name: str,
    *,
    bundle_root: Path,
) -> None:
    """Apply one bundle validation drift case."""
    manifest_path = bundle_root / "manifest.json"
    if case_name == "checksum":
        drifted_source: JsonObject = {
            "name": "demo",
            "flow": [],
            "metadata": {"drift": True},
        }
        _ = (bundle_root / "source_ast.json").write_text(
            json.dumps(
                drifted_source, indent=2, ensure_ascii=True, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        return
    if case_name == "manifest_path":
        manifest = object_from_json_file(manifest_path)
        object_member(manifest, "files")["source_ast"] = (
            "data/blueprints/other/source_ast.json"
        )
        _write_json_file(manifest_path, manifest)
        return
    if case_name == "unknown_entry":
        sidecar_content = json.dumps(
            {"note": "extra"}, indent=2, ensure_ascii=True, sort_keys=True
        )
        _ = (bundle_root / "sidecar.json").write_text(
            f"{sidecar_content}\n", encoding="utf-8"
        )
        manifest = object_from_json_file(manifest_path)
        object_member(manifest, "files")["sidecar"] = (
            "data/blueprints/drift-demo/sidecar.json"
        )
        object_member(manifest, "checksums_sha256")["sidecar"] = hashlib.sha256(
            f"{sidecar_content}\n".encode()
        ).hexdigest()
        _write_json_file(manifest_path, manifest)
        return
    if case_name == "missing_checksum":
        manifest = object_from_json_file(manifest_path)
        _ = object_member(manifest, "checksums_sha256").pop("source_ast")
        _write_json_file(manifest_path, manifest)
        return
    failure_message = f"Unhandled bundle validation drift case: {case_name}"
    assert_unexpected_success(failure_message)


def test_make_ast_blueprint_bundle_validation_692b97d9(
    tmp_path: Path,
) -> None:
    """Blueprint bundle validation requires present optional files in the.

    manifest.
    """
    source_ast: JsonObject = {"name": "demo", "flow": [], "metadata": {}}
    _ = persist_make_blueprint_bundle(
        repo_root=tmp_path,
        blueprint_name="Untracked Optional Demo",
        payloads=MakeBlueprintBundlePayloads(source_ast=source_ast),
    )
    observability_report: JsonObject = {"opaque_field_paths": []}
    bundle_root = tmp_path / "data" / "blueprints" / "untracked-optional-demo"
    _ = (bundle_root / "observability_report.json").write_text(
        json.dumps(
            observability_report, indent=2, ensure_ascii=True, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )

    report = validate_make_blueprint_bundle_collection(
        tmp_path / "data" / "blueprints"
    )
    errors = cast("list[object]", report["errors"])
    expected_errors = {
        (
            "untracked-optional-demo: manifest files entry for "
            "observability_report is required."
        ),
        (
            "untracked-optional-demo: manifest checksum for "
            "observability_report is required."
        ),
    }
    missing_errors = expected_errors - set(errors)
    assert not (missing_errors), (
        f"Untracked optional bundle file was not reported: {report}"
    )


def test_make_ast_blueprint_bundle_slug_is_stable() -> None:
    """Blueprint bundle slugs are deterministic and filesystem-safe."""
    assert (
        slugify_blueprint_name(" Customer Feedback Agent ")
        == "customer-feedback-agent"
    ), "Blueprint bundle slug normalization changed."


def test_make_ast_reference_targets_ignore_documentation_examples() -> None:
    """Reference collection ignores root metadata and literal note examples."""
    payload: JsonObject = {
        "name": "references",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "mapper": {"summary": "{{1.payload}}"},
                "metadata": {"designer": {"x": 0, "y": 0}},
            }
        ],
        "metadata": {
            "scenario": {"name": "references"},
            "parameters": [{"help": "Example only: {{99.fake}}"}],
            "notes": [
                {
                    "moduleIds": [1],
                    "content": (
                        "<p>Teach clients to type {{99.example}} literally.</p>"
                    ),
                }
            ],
        },
    }
    root = parse_make_ast(payload)

    assert collect_reference_targets(root) == ("1",), (
        f"Unexpected reference targets: {collect_reference_targets(root)}"
    )
    usages = collect_reference_usages(root)
    assert tuple(
        (usage.source_node_id, usage.field_path) for usage in usages
    ) == (("1", "payload"),), f"Unexpected reference usages: {usages}"
    assert tuple(node.node_id for node in iter_top_level_nodes(root)) == (
        "1",
    ), f"Unexpected top-level nodes: {iter_top_level_nodes(root)}"


def test_make_ast_cross_node_reference_errors_cover_notes_and_templates() -> (
    None
):
    """Cross-node reference diagnostics cover missing templates and note.

    anchors.
    """
    payload: JsonObject = {
        "name": "missing-reference",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "mapper": {"summary": "{{2.payload}}"},
            }
        ],
        "metadata": {
            "notes": [{"moduleIds": [3], "content": "<p>Missing node</p>"}]
        },
    }
    root = parse_make_ast(payload)

    expected = (
        "Blueprint references unknown module id '2'.",
        "Blueprint references unknown module id '3'.",
        "metadata.notes[1] references unknown module id '3'.",
    )
    assert cross_node_reference_errors(root) == expected, (
        f"Unexpected cross-node errors: {cross_node_reference_errors(root)}"
    )
    assert note_binding_errors(root) == expected[2:], (
        f"Unexpected note errors: {note_binding_errors(root)}"
    )


def test_make_ast_note_binding_errors_reject_malformed_anchor_shapes() -> None:
    """Note binding diagnostics reject malformed anchors before unknown-ID.

    checks.
    """
    payload: JsonObject = {
        "name": "malformed-note-anchors",
        "flow": [{"id": 1, "module": "gateway:CustomWebHook"}],
        "metadata": {
            "notes": [
                {
                    "moduleIds": [True, 1.5, "", 0, -1],
                    "content": "<p>Malformed anchors.</p>",
                }
            ]
        },
    }
    root = parse_make_ast(payload)

    expected = (
        "metadata.notes[1].moduleIds[1] must be a string or integer ID.",
        "metadata.notes[1].moduleIds[2] must be a string or integer ID.",
        "metadata.notes[1].moduleIds[3] must be a string or integer ID.",
        "metadata.notes[1].moduleIds[4] must be a string or integer ID.",
        "metadata.notes[1].moduleIds[5] must be a string or integer ID.",
    )
    assert note_binding_errors(root) == expected, (
        f"Unexpected malformed note errors: {note_binding_errors(root)}"
    )
    assert collect_reference_targets(root) == (), (
        f"Malformed note anchors should not be reference targets: {root}"
    )


def test_make_ast_references_ignore_malformed_designer_scalar_bindings() -> (
    None
):
    """Malformed designer scalar bindings are not executable references."""
    payload: JsonObject = {
        "name": "malformed-designer-bindings",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "metadata": {
                    "designer": {
                        "messages": [
                            {"moduleId": True},
                            {"stepId": MALFORMED_DESIGNER_STEP_ID},
                            {"moduleId": ""},
                        ]
                    }
                },
            }
        ],
    }
    root = parse_make_ast(payload)
    rewritten = rewrite_cross_node_references(
        payload,
        id_mapping={"True": "11", "1.5": "15"},
    )
    flow = cast("list[object]", rewritten["flow"])
    first = cast("JsonObject", flow[0])
    metadata = cast("JsonObject", first["metadata"])
    designer = cast("JsonObject", metadata["designer"])
    messages = cast("list[object]", designer["messages"])
    first_message = cast("JsonObject", messages[0])
    second_message = cast("JsonObject", messages[1])

    assert collect_reference_targets(root) == (), (
        f"Malformed designer bindings should not be targets: {root}"
    )
    assert not (first_message["moduleId"] is not True), (
        f"Malformed designer bindings should not be rewritten: {messages}"
    )
    assert second_message["stepId"] == MALFORMED_DESIGNER_STEP_ID, (
        f"Malformed designer bindings should not be rewritten: {messages}"
    )


def test_make_ast_reference_rewrite_updates_only_make_bindings() -> None:
    """Reference rewriting touches node IDs, templates, and note bindings.

    only.
    """
    payload: JsonObject = {
        "name": "rewrite",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "mapper": {
                    "moduleId": "1 ",
                    "stepId": "2",
                    "summary": (
                        '{{if(1.status = "ok"; 2.name; "literal 1.name")}}'
                    ),
                },
                "metadata": {"designer": {"x": 0, "y": 0}},
            },
            {
                "id": 2,
                "module": "slack:CreateMessage",
                "mapper": {"text": "{{1.payload}}"},
                "metadata": {"designer": {"x": 300, "y": 0}},
            },
        ],
        "metadata": {
            "scenario": {"name": "rewrite"},
            "notes": [
                {"moduleIds": [2], "content": "<p>Literal {{1.body}}</p>"}
            ],
            "external": {"id": 1},
        },
    }
    rewritten = rewrite_cross_node_references(
        payload, id_mapping={"1": "11", "2": "22"}
    )
    flow = cast("list[object]", rewritten["flow"])
    first = cast("JsonObject", flow[0])
    second = cast("JsonObject", flow[1])
    first_mapper = cast("JsonObject", first["mapper"])
    second_mapper = cast("JsonObject", second["mapper"])
    metadata = cast("JsonObject", rewritten["metadata"])
    notes = cast("list[object]", metadata["notes"])
    note = cast("JsonObject", notes[0])
    external = cast("JsonObject", metadata["external"])

    assert first["id"] == REWRITTEN_FIRST_NODE_ID, (
        f"Node IDs were not rewritten: {rewritten}"
    )
    assert second["id"] == REWRITTEN_SECOND_NODE_ID, (
        f"Node IDs were not rewritten: {rewritten}"
    )
    assert first_mapper["moduleId"] == "1", (
        f"Business scalar IDs should not be rewritten: {first_mapper}"
    )
    assert first_mapper["stepId"] == "2", (
        f"Business scalar IDs should not be rewritten: {first_mapper}"
    )
    assert (
        first_mapper["summary"]
        == '{{if(11.status = "ok"; 22.name; "literal 1.name")}}'
    ), f"Expression references were not rewritten safely: {first_mapper}"
    assert second_mapper["text"] == "{{11.payload}}", (
        f"Template reference was not rewritten: {second_mapper}"
    )
    assert note["moduleIds"] == [22], (
        f"Only Make note bindings should be rewritten: {metadata}"
    )
    assert external["id"] == 1, (
        f"Only Make note bindings should be rewritten: {metadata}"
    )


def test_make_ast_reference_rewrite_rejects_non_string_object_keys() -> None:
    """Reference rewriting fails loudly instead of dropping non-JSON mapping.

    keys.
    """
    payload = cast(
        "JsonObject",
        {
            "name": "rewrite-non-string-key",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "mapper": {1: "{{1.payload}}"},
                }
            ],
        },
    )

    with pytest.raises(TypeError, match="object keys must be strings"):
        require_reference_rewrite_non_string_key_failure(payload)


def test_make_ast_references_include_filter_condition_aliases() -> None:
    """Reference collection and rewriting include route filter aliases."""
    payload: JsonObject = {
        "name": "filter-alias-references",
        "flow": [
            {
                "id": 1,
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {"expression": "{{2.score}}"},
                        "flow": [{"id": 2, "module": "http:MakeRequest"}],
                    },
                    {
                        "filter": {
                            "rules": [
                                {
                                    "field": "status ",
                                    "operator": "equal ",
                                    "value": "{{3.status}}",
                                }
                            ]
                        },
                        "flow": [{"id": 3, "module": "slack:CreateMessage"}],
                    },
                ],
            }
        ],
    }
    root = parse_make_ast(payload)
    rewritten = rewrite_cross_node_references(
        payload, id_mapping={"2": "22", "3": "33"}
    )
    router = cast("JsonObject", cast("list[object]", rewritten["flow"])[0])
    routes = cast("list[object]", router["routes"])
    expression_route = cast("JsonObject", routes[0])
    rules_route = cast("JsonObject", routes[1])
    expression_filter = cast("JsonObject", expression_route["filter"])
    rules_filter = cast("JsonObject", rules_route["filter"])
    rules = cast("list[object]", rules_filter["rules"])
    rule = cast("JsonObject", rules[0])

    if collect_reference_targets(root) != ("2", "3"):
        targets = collect_reference_targets(root)
        assert collect_reference_targets(root) == ("2", "3"), (
            f"Filter alias references were not collected: {targets}"
        )
    usages = tuple(
        (usage.source_node_id, usage.field_path)
        for usage in collect_reference_usages(root)
    )
    assert usages == (("2", "score"), ("3", "status")), (
        f"Filter alias usages were not collected: "
        f"{collect_reference_usages(root)}"
    )
    assert expression_filter["expression"] == "{{22.score}}", (
        f"Filter alias references were not rewritten: {rewritten}"
    )
    assert rule["value"] == "{{33.status}}", (
        f"Filter alias references were not rewritten: {rewritten}"
    )


def test_make_ast_reference_rewrite_preserves_padded_replacement_ids() -> None:
    """Reference rewriting keeps replacement IDs as strings when needed."""
    payload: JsonObject = {
        "name": "rewrite-padded",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "mapper": {"text": "{{1.payload}}"},
            }
        ],
        "metadata": {"notes": [{"moduleIds": [1]}]},
    }
    rewritten = rewrite_cross_node_references(payload, id_mapping={"1": "01"})
    flow = cast("list[object]", rewritten["flow"])
    first = cast("JsonObject", flow[0])
    first_mapper = cast("JsonObject", first["mapper"])
    metadata = cast("JsonObject", rewritten["metadata"])
    notes = cast("list[object]", metadata["notes"])
    note = cast("JsonObject", notes[0])

    assert first["id"] == "01", (
        f"Node ID replacement lost padded identity: {rewritten}"
    )
    assert first_mapper["text"] == "{{01.payload}}", (
        f"Template replacement lost padded identity: {first_mapper}"
    )
    assert note["moduleIds"] == ["01"], (
        f"Note binding replacement lost padded identity: {note}"
    )


def test_make_ast_module_role_helpers_treat_webhook_response_as_write() -> None:
    """Webhook responses are write actions, not trigger modules."""
    for module_token in (
        "gateway:WebhookRespond ",
        "gateway:WebhookResponse ",
        "webhooks.respond ",
        "webhooks:WebhookResponse",
    ):
        root = parse_make_ast(
            {
                "name": "webhook-response",
                "flow": [{"id": 1, "module": module_token}],
            }
        )
        assert require_ast_node(root, "1").kind == "module", (
            "Webhook response should parse as a module action, not a webhook "
            "trigger."
        )
        assert infer_module_role(module_token) == "write", (
            "Webhook response role should be write."
        )
        assert not (module_looks_like_trigger(module_token)), (
            "Webhook response must not look like a trigger."
        )
        assert module_looks_like_webhook_response(module_token), (
            "Webhook response token should be explicit shared classifier "
            "evidence."
        )
    assert module_looks_like_trigger(
        "custom:OpaqueStart", module_kind="instant_trigger"
    ), "Trigger module kind should override opaque tokens."
    assert not (
        module_looks_like_trigger("custom:OpaqueStart", module_kind="search")
    ), "Search module kind should not be treated as a trigger."


def test_make_ast_normalizes_route_filter_condition_aliases() -> None:
    """Route filters keep usable conditions from supported Make export.

    shapes.
    """
    payload: JsonObject = {
        "name": "filter-aliases",
        "flow": [
            {
                "id": "router ",
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "name": "Text condition ",
                            "condition": "{{1.amount}} > 500",
                        },
                        "flow": [],
                    },
                    {
                        "filter": {
                            "label": "Rule list",
                            "rules": [
                                {
                                    "field": "status ",
                                    "operator": "equal ",
                                    "value": "ready",
                                }
                            ],
                        },
                        "flow": [],
                    },
                    {
                        "filter": {
                            "name": "Expression object",
                            "expression": {
                                "left": "{{1.score}}",
                                "op": "gt",
                                "right": 80,
                            },
                        },
                        "flow": [],
                    },
                    {
                        "filter": {
                            "name": "Canonical object",
                            "conditions": {
                                "left": "{{1.score}}",
                                "op": "gt",
                                "right": 80,
                            },
                        },
                        "flow": [],
                    },
                ],
            }
        ],
    }
    root = parse_make_ast(payload)
    router = require_ast_node(root, "router")
    filters: list[MakeAstFilter] = []
    for route in router.routes:
        assert route.filter is not None, f"Route filter was not parsed: {route}"
        filters.append(route.filter)

    text_filter, rules_filter, expression_filter, canonical_filter = tuple(
        filters
    )
    assert text_filter.conditions == {"condition": "{{1.amount}} > 500"}, (
        f"Text condition alias was not retained: {text_filter.conditions}"
    )
    assert rules_filter.conditions == {
        "rules": [{"field": "status", "operator": "equal", "value": "ready"}]
    }, f"Rule-list condition alias was not retained: {rules_filter.conditions}"
    assert expression_filter.conditions == {
        "expression": {"left": "{{1.score}}", "op": "gt", "right": 80}
    }, (
        f"Expression condition alias was not retained: "
        f"{expression_filter.conditions}"
    )
    assert canonical_filter.conditions == {
        "left": "{{1.score}}",
        "op": "gt",
        "right": 80,
    }, f"Canonical conditions were not preserved: {canonical_filter.conditions}"
    assert not ("condition" not in text_filter.raw_payload), (
        f"Raw filter payload did not preserve aliases: "
        f"{text_filter.raw_payload}"
    )


def test_make_ast_fixture_snapshot_is_deterministic_and_sanitized() -> None:
    """Fixture JSON parses into a deterministic AST diagnostic snapshot."""
    fixture_text = AST_FIXTURE.read_text(encoding="utf-8")
    root = parse_make_ast_json_text(fixture_text)
    snapshot = ast_root_snapshot(root)

    assert snapshot == ast_root_snapshot(
        parse_make_ast_json_text(fixture_text)
    ), "AST fixture snapshot must be deterministic."
    assert snapshot["unknown_root_keys"] == ["future_root_field"], (
        f"Root unknown fields were not preserved: {snapshot}"
    )
    assert "client" not in fixture_text.casefold(), (
        "AST fixtures must not contain client/private data markers."
    )
    assert "secret" not in fixture_text.casefold(), (
        "AST fixtures must not contain client/private data markers."
    )
    readme_text = AST_FIXTURE_README.read_text(encoding="utf-8")
    assert not ("synthetic" not in readme_text), (
        "AST fixture origin and sanitization must be documented."
    )
    assert not ("sanitized" not in readme_text), (
        "AST fixture origin and sanitization must be documented."
    )


def test_make_ast_rejects_invalid_flow_shapes_with_typed_error() -> None:
    """Invalid root flow shapes fail before loose JSON leaks downstream."""
    with pytest.raises(MakeAstParseError, match="flow"):
        require_invalid_flow_failure()


def test_make_ast_rejects_malformed_json_with_typed_error() -> None:
    """Malformed JSON text raises the typed parser error."""
    with pytest.raises(MakeAstParseError, match="Malformed"):
        require_malformed_json_failure()


def test_make_ast_rejects_non_finite_json_numbers() -> None:
    """JSON normalization rejects non-finite numbers before AST records are.

    built.
    """
    with pytest.raises(MakeAstParseError, match="Non-finite JSON numbers"):
        require_non_finite_number_failure()


def test_make_ast_rejects_non_string_object_keys() -> None:
    """Programmatic AST payloads cannot smuggle non-JSON object keys into.

    parsing.
    """
    payload = cast(
        "JsonObject",
        {
            "name": "non-string-key",
            "flow": [
                {1: "not-a-json-key", "id": 1, "module": "http:MakeRequest"}
            ],
        },
    )

    with pytest.raises(TypeError, match="object keys must be strings"):
        require_non_string_key_failure(payload)


def test_make_ast_accepts_nameless_public_make_exports_with_fallback_name() -> (
    None
):
    """Public Make template exports may omit the root scenario name."""
    root = parse_make_ast(
        {
            "flow": [{"id": 1, "module": "http:MakeRequest"}],
            "metadata": {"scenario": {"maxErrors": 3}},
        }
    )

    assert root.scenario.name == "Imported Make Scenario", (
        f"Nameless public Make export did not receive the fallback name: "
        f"{root.scenario}"
    )


def test_make_ast_rejects_non_text_scenario_names() -> None:
    """Root and metadata scenario names must be strings, not coerced.

    containers.
    """
    payloads: tuple[JsonObject, ...] = (
        cast("JsonObject", {"name": {"bad": True}, "flow": []}),
        cast(
            "JsonObject",
            {
                "name": "fallback",
                "metadata": {"scenario": {"name": ["bad"]}},
                "flow": [],
            },
        ),
    )
    for payload in payloads:
        with pytest.raises(MakeAstParseError, match="name"):
            require_non_text_scenario_name_failure(payload)


def test_require_ast_node_fails_for_missing_node() -> None:
    """Node lookup fails loudly instead of fabricating AST nodes."""
    root = parse_make_ast(make_blueprint_payload())

    with pytest.raises(LookupError, match="does not exist"):
        require_missing_node_failure(root)


def require_missing_node_failure(root: MakeAstRoot) -> None:
    """Fail unless missing AST node lookup raises."""
    unexpected = require_ast_node(root, "missing")
    failure_message = (
        f"Missing AST node lookup should have failed: {unexpected}"
    )
    assert_unexpected_success(failure_message)


def require_invalid_flow_failure() -> None:
    """Fail unless an invalid root flow raises."""
    unexpected = parse_make_ast_json_text(
        '{"name": "broken", "flow": {"not": "a list"}}'
    )
    failure_message = f"Invalid flow should have failed: {unexpected}"
    assert_unexpected_success(failure_message)


def require_malformed_json_failure() -> None:
    """Fail unless malformed JSON raises."""
    unexpected = parse_make_ast_json_text('{"name": "broken",')
    failure_message = f"Malformed JSON should have failed: {unexpected}"
    assert_unexpected_success(failure_message)


def require_non_finite_number_failure() -> None:
    """Fail unless non-finite JSON numbers raise."""
    source_text = json.dumps(
        {
            "name": "non-finite-number",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "mapper": {"score": float("nan")},
                }
            ],
        }
    )
    unexpected = parse_make_ast_json_text(source_text)
    failure_message = f"Non-finite JSON number should have failed: {unexpected}"
    assert_unexpected_success(failure_message)


def require_non_string_key_failure(payload: JsonObject) -> None:
    """Fail unless non-string object keys raise."""
    unexpected = parse_make_ast(payload)
    failure_message = (
        f"Non-string JSON object key should have failed: {unexpected}"
    )
    assert_unexpected_success(failure_message)


def require_reference_rewrite_non_string_key_failure(
    payload: JsonObject,
) -> None:
    """Fail unless non-string rewrite object keys raise."""
    unexpected = rewrite_cross_node_references(payload, id_mapping={"1": "11"})
    failure_message = (
        f"Non-string rewrite object key should have failed: {unexpected}"
    )
    assert_unexpected_success(failure_message)


def require_non_text_scenario_name_failure(payload: JsonObject) -> None:
    """Fail unless non-text scenario names raise."""
    unexpected = parse_make_ast_json_text(json.dumps(payload, sort_keys=True))
    failure_message = f"Non-text scenario name should have failed: {unexpected}"
    assert_unexpected_success(failure_message)


def make_blueprint_payload() -> JsonObject:
    """Return a representative Make blueprint payload."""
    payload = cast(
        "object", json.loads(AST_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{AST_FIXTURE} must contain a JSON object."
    )
    return cast("JsonObject", payload)


def runtime_metadata_payload() -> JsonObject:
    """Return a blueprint with designer metadata and similar business fields."""
    return {
        "name": "runtime-metadata",
        "flow": [
            {
                "id": "1 ",
                "module": "http:MakeRequest",
                "elapsed": 2.93,
                "element_actions": [{"name": "request"}, {"name": "parse"}],
                "mapper": {
                    "events": [
                        {
                            "event": "forman_auto_complete_open ",
                            "source": "mapper",
                        }
                    ],
                    "messages": [
                        {"severity": "error", "message": "business payload"}
                    ],
                    "notes": [{"html": "<b>Customer note</b>"}],
                    "orphans": [{"id": "999", "module": "business:data"}],
                    "samples": {"3": {"response": "business"}},
                },
                "routes": [
                    {
                        "filter": {
                            "label_name": "Only urgent ",
                            "condition": "and",
                            "conditions": [
                                {
                                    "a": "response.priority ",
                                    "operator": "equal ",
                                    "b": "high",
                                }
                            ],
                        },
                        "flow": [
                            {
                                "id": "2 ",
                                "module": "slack:CreateMessage",
                                "elapsed": True,
                            }
                        ],
                    }
                ],
                "on_error": [
                    {
                        "module": "builtin:Break",
                        "retry": {"count": "2", "interval": "30"},
                    }
                ],
                "onerror": {
                    "module": "builtin:Ignore ",
                    "retry": "false",
                    "count": True,
                    "interval": 2.5,
                },
                "metadata": {
                    "designer": {
                        "messages": [
                            {
                                "category": ["setup"],
                                "severity": "warning",
                                "message": {"text": "Do not stringify me"},
                            },
                            {
                                "category": "setup ",
                                "severity": "warning ",
                                "message": "Real designer warning",
                            },
                        ],
                        "events": [
                            {
                                "event": "forman_auto_complete_open ",
                                "source": "designer_metadata",
                            }
                        ],
                    }
                },
            }
        ],
        "metadata": {
            "designer": {
                "messages": [
                    {
                        "category": "setup ",
                        "severity": "error ",
                        "message": "Connection empty",
                    }
                ],
                "orphans": [[{"id": "7", "module": "tools:Repeater"}]],
                "samples": {
                    "3": {
                        "metadata": {
                            "executionSteps": [
                                {
                                    "id": "msg_001 ",
                                    "role": "assistant",
                                    "content": '{"sentiment":"negative"}',
                                    "tokenUsage": {
                                        "totalTokens": 450,
                                        "promptTokens": 437,
                                        "completionTokens": 13,
                                    },
                                    "executionTimeMs": 1062,
                                    "agentIterationId": "iteration-001",
                                }
                            ],
                            "executionTimeMs": 2915,
                            "tokenUsageSummary": {
                                "totalTokens": 1353,
                                "promptTokens": 1315,
                                "completionTokens": 38,
                            },
                            "lastAgentIterationId": "iteration-001",
                        },
                        "response": '{"sentiment":"negative"}',
                        "threadId": "thread-001",
                        "jsonResponse": {"sentiment": "negative"},
                    },
                    "bad": ["not", "an", "object"],
                },
            },
            "events": [
                {
                    "event_name": "forman_auto_complete_open ",
                    "source": "root_metadata",
                }
            ],
            "notes": [
                {
                    "id": "n1 ",
                    "content": "<p>Native Make note</p>",
                    "metadata": {"color": "#123456"},
                }
            ],
        },
    }


def layout_payload(
    *,
    with_coordinates: bool,
    first_x: int = 10,
    first_module: str = "builtin:BasicRouter",
) -> JsonObject:
    """Return a small routed blueprint for layout and drift tests."""
    return {
        "name": "layout-demo",
        "flow": [
            layout_node(
                node_id="1",
                module=first_module,
                coordinate=(first_x, 20),
                with_coordinates=with_coordinates,
                routes=[
                    {
                        "flow": [
                            layout_node(
                                node_id="2",
                                module="http:MakeRequest",
                                coordinate=(30, 40),
                                with_coordinates=with_coordinates,
                            ),
                            layout_node(
                                node_id="3",
                                module="json:ParseJSON",
                                coordinate=(60, 70),
                                with_coordinates=with_coordinates,
                            ),
                        ]
                    },
                    {
                        "flow": [
                            layout_node(
                                node_id="4",
                                module="slack:CreateMessage",
                                coordinate=(90, 100),
                                with_coordinates=with_coordinates,
                            )
                        ]
                    },
                ],
            )
        ],
        "metadata": {},
    }


def layout_node(
    *,
    node_id: str,
    module: str,
    coordinate: tuple[int, int],
    with_coordinates: bool,
    routes: list[object] | None = None,
) -> JsonObject:
    """Return one layout test node."""
    node: JsonObject = {"id": node_id, "module": module}
    if with_coordinates:
        x, y = coordinate
        node["metadata"] = {"designer": {"x": x, "y": y}}
    if routes is not None:
        node["routes"] = routes
    return node


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return an object member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return cast("JsonObject", value)


def object_from_json_file(path: Path) -> JsonObject:
    """Return an object payload from one JSON file."""
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), (
        f"Expected JSON object in {path}: {payload}"
    )
    return cast("JsonObject", payload)


def _write_json_file(path: Path, payload: JsonObject) -> None:
    """Write one JSON object payload to disk."""
    _ = path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
