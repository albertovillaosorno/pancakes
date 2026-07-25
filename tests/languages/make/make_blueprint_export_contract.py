# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native blueprint export contract tests.

Boundary contract:
- Owns: Make adapter export shape, token/version translation, and zero-trace
privacy checks.
- Must not: test generic AST traversal, live Make APIs, or non-Make provider
behavior.
- Allows: small synthetic catalogs that prove Make import-shape behavior without
provider calls.
- Split when: another language adapter gains its own blueprint export contract.
- Merge when: another Make export test covers the same zero-trace behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple, cast

import pytest
from blueprints.ast import parse_make_ast_json_text
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogField,
    CatalogModule,
    CatalogSnapshot,
)
from languages.make.blueprint_export import (
    MakeBlueprintPrivateMetadataLeakError,
    render_make_blueprint_payload,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog.models import CatalogFieldDirection, CatalogModuleKind

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
HTTP_REQUEST_MODULE = "http:" + "MakeRequest"


class CatalogModuleSpec(NamedTuple):
    """Synthetic Make catalog module input for DAMP export tests."""

    app_slug: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    raw_spec_sha256: str
    fingerprint: str
    parameter_paths: tuple[str, ...] = ()
    connection_parameter_path: str | None = None


def test_make_export_transpiles_abstract_draft_to_zero_trace_blueprint() -> (
    None
):
    """Make export emits native module identity, versions, and Make metadata.

    only.
    """
    catalog = transpilation_catalog()
    root = parse_make_ast_json_text(
        json.dumps(abstract_project_draft_blueprint())
    )

    result = render_make_blueprint_payload(root=root, catalog=catalog)

    assert result.importable, (
        f"Transpiled draft should be importable: {result.gate}"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    gateway = cast("JsonObject", cast("list[object]", flow)[0])
    router = cast("JsonObject", cast("list[object]", flow)[1])
    routes = router.get("routes")
    assert isinstance(routes, list), (
        f"Rendered router routes are missing: {router}"
    )
    first_route = cast("JsonObject", cast("list[object]", routes)[0])
    route_flow = first_route.get("flow")
    assert isinstance(route_flow, list), (
        f"Rendered route flow is missing: {first_route}"
    )
    slack = cast("JsonObject", cast("list[object]", route_flow)[0])

    assert gateway.get("module") == "gateway:CustomWebHook", (
        f"Gateway token changed unexpectedly: {gateway}"
    )
    assert gateway.get("version") == 1, (
        f"Gateway version was not injected: {gateway}"
    )
    assert router.get("module") == "builtin:BasicRouter", (
        f"Router token changed unexpectedly: {router}"
    )
    assert router.get("version") == 1, (
        f"Router version was not refreshed: {router}"
    )
    assert slack.get("module") == "slack:CreateMessage", (
        f"Slack legacy token was not transpiled: {slack}"
    )
    assert slack.get("version") == 4, (
        f"Slack current version was not injected: {slack}"
    )
    _assert_slack_native_connection(slack)

    for node_payload in (gateway, router, slack):
        metadata = node_payload.get("metadata")
        assert isinstance(metadata, dict), (
            f"Node metadata is missing: {node_payload}"
        )
        designer = cast("JsonObject", metadata).get("designer")
        assert isinstance(designer, dict), (
            f"Designer metadata is missing: {metadata}"
        )
        assert {"x", "y"} <= set(cast("JsonObject", designer)), (
            f"Designer coordinates were not generated: {designer}"
        )

    slack_metadata = cast("JsonObject", slack["metadata"])
    assert "parameters" in slack_metadata, (
        f"Slack Make-native schema metadata was not projected: {slack_metadata}"
    )
    root_metadata = result.payload.get("metadata")
    assert isinstance(root_metadata, dict), (
        f"Root metadata is missing: {result.payload}"
    )
    typed_root_metadata = cast("JsonObject", root_metadata)
    assert typed_root_metadata.get("instant") is True, (
        f"Root instant metadata was not inferred: {typed_root_metadata}"
    )
    assert typed_root_metadata.get("version") == 1, (
        f"Root Make metadata version was not injected: {typed_root_metadata}"
    )

    for private_key in (
        "placeholder_registry ",
        "raw_spec ",
        "error_handling ",
        "runtime_connection ",
        "rollback_posture",
    ):
        assert not _json_contains_key(result.payload, private_key), (
            f"Importable output leaked private key {private_key!r}: "
            f"{result.payload}"
        )


def test_make_export_uses_builtin_manifest_3e26db8c() -> None:
    """BasicRouter export should use the Make built-in manifest without.

    raw-spec.

    catalog facts.
    """
    root = parse_make_ast_json_text(
        json.dumps(abstract_project_draft_blueprint())
    )

    result = render_make_blueprint_payload(
        root=root, catalog=transpilation_catalog_without_builtin()
    )

    assert result.importable, (
        f"Built-in router should render importably: {result.gate}"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    router = cast("JsonObject", cast("list[object]", flow)[1])
    assert router.get("module") == "builtin:BasicRouter", (
        f"Built-in router token should remain Make-native: {router}"
    )
    assert router.get("version") == 1, (
        f"Built-in router version should come from the local manifest: {router}"
    )


def test_make_export_keeps_runtime_slack_connection_as_native_placeholder() -> (
    None
):
    """Slack runtime connection aliases project to __IMTCONN__ without fake.

    credentials.
    """
    payload = abstract_project_draft_blueprint()
    slack = _first_route_node(payload)
    slack_parameters = cast("JsonObject", slack["parameters"])
    slack_parameters["account"] = "{{runtime.connection.slack_ops}}"
    registry = cast(
        "list[object]",
        cast("JsonObject", payload["metadata"])["placeholder_registry"],
    )
    registry.append(
        {
            "expected_type": "account:slack2,slack3 ",
            "handoff_instructions": "Connect Slack during Make import.",
            "kind": "runtime_setup ",
            "placeholder": "runtime.connection.slack_ops",
            "required": True,
            "target_path": "/flow/1/routes/0/flow/0/parameters/account",
        }
    )
    root = parse_make_ast_json_text(json.dumps(payload))

    result = render_make_blueprint_payload(
        root=root, catalog=transpilation_catalog()
    )

    rendered_slack = _first_route_node(result.payload)
    parameters = cast("JsonObject", rendered_slack["parameters"])
    mapper = cast("JsonObject", rendered_slack["mapper"])
    metadata = cast("JsonObject", rendered_slack["metadata"])
    metadata_parameters = cast("JsonObject", metadata["parameters"])
    restore = cast("JsonObject", metadata["restore"])
    restore_parameters = cast("JsonObject", restore["parameters"])

    assert rendered_slack["module"] == "slack:CreateMessage"
    assert rendered_slack["version"] == 4
    assert parameters == {"__IMTCONN__": "{{runtime.connection.slack_ops}}"}
    assert mapper["channel"] == "sales-ops"
    assert mapper["text"] == "Qualified lead {{1.email}}"
    assert "account" not in parameters
    assert metadata_parameters["__IMTCONN__"] == {
        "label": "Slack connection ",
        "type": "slack2",
    }
    assert restore_parameters["__IMTCONN__"] == {
        "label": "Slack connection",
        "data": {"connection": "slack2", "scoped": "true"},
    }


def _assert_slack_native_connection(slack: JsonObject) -> None:
    """Assert Slack connection aliases are rendered in Make-native shape."""
    slack_parameters = cast("JsonObject", slack.get("parameters"))
    slack_metadata = cast("JsonObject", slack.get("metadata"))
    metadata_parameters = cast("JsonObject", slack_metadata.get("parameters"))
    assert slack_parameters.get("__IMTCONN__") == "slack-ops-connection", (
        f"Slack connection alias was not projected to native Make "
        f"parameters: {slack}"
    )
    assert metadata_parameters.get("__IMTCONN__") == {
        "label": "Slack connection ",
        "type": "slack2",
    }, f"Slack connection UI metadata was not projected: {slack}"
    assert "account" not in slack_parameters, (
        f"Slack legacy connection alias leaked into native Make parameters: "
        f"{slack}"
    )


def _first_route_node(payload: JsonObject) -> JsonObject:
    flow = cast("list[object]", payload["flow"])
    router = cast("JsonObject", flow[1])
    routes = cast("list[object]", router["routes"])
    first_route = cast("JsonObject", routes[0])
    route_flow = cast("list[object]", first_route["flow"])
    return cast("JsonObject", route_flow[0])


def _node_by_id(payload: JsonObject, node_id: int) -> JsonObject:
    """Return a node payload by id from a blueprint-like object.

    Raises:
        AssertionError: If the node id is absent.
    """
    for node in _walk_nodes(payload):
        if node.get("id") == node_id:
            return node
    msg = f"Missing node id {node_id}: {payload}"
    raise AssertionError(msg)


def _walk_nodes(value: object) -> tuple[JsonObject, ...]:
    """Return module-like node payloads from a blueprint-like object."""
    nodes: list[JsonObject] = []
    if isinstance(value, dict):
        typed = cast("JsonObject", value)
        if "id" in typed and "module" in typed:
            nodes.append(typed)
        for child in typed.values():
            nodes.extend(_walk_nodes(child))
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            nodes.extend(_walk_nodes(child))
    return tuple(nodes)


def test_make_export_fails_closed_on_importable_private_metadata_leak() -> None:
    """Make export refuses payloads that still carry Pancakes traces."""
    root = parse_make_ast_json_text(
        json.dumps(importable_http_blueprint_with_private_designer())
    )

    with pytest.raises(MakeBlueprintPrivateMetadataLeakError) as error:
        _ = render_make_blueprint_payload(
            root=root, catalog=load_catalog_fixture()
        )

    assert "$.flow[0].metadata.designer.pancakes_trace" in error.value.paths, (
        f"Renderer did not expose the private leak path: {error.value.paths}"
    )


def test_make_export_fails_closed_on_importable_private_trace_text() -> None:
    """Zero-trace rejects local provenance text even under Make-native metadata.

    keys.
    """
    root = parse_make_ast_json_text(
        json.dumps(importable_http_blueprint_with_private_trace_text())
    )

    with pytest.raises(MakeBlueprintPrivateMetadataLeakError) as error:
        _ = render_make_blueprint_payload(
            root=root, catalog=load_catalog_fixture()
        )

    assert (
        "$.flow[0].metadata.designer.messages[0].message" in error.value.paths
    ), (
        f"Renderer did not expose the private text leak path: "
        f"{error.value.paths}"
    )


def test_make_export_preserves_manifestless_unknown_71b12d34() -> None:
    """Resolved modules without projectors pass through without invented native.

    metadata.
    """
    catalog = catalog_with_unknown_partner_module()
    for scenario in pass_through_unknown_module_blueprints():
        root = parse_make_ast_json_text(json.dumps(scenario))

        result = render_make_blueprint_payload(root=root, catalog=catalog)

        unknown = _node_by_id(result.payload, 99)
        metadata = cast("JsonObject", unknown["metadata"])
        assert result.importable, (
            f"Pass-through fixture should remain importable: {result.gate}"
        )
        assert result.pass_through_unknown_modules == (
            {
                "node_id": 99,
                "module": "partner:ExperimentalAction",
                "version": 7,
                "preservation_status": "unsupported_but_preserved ",
                "native_parity_category": "pass_through_unknown_module",
            },
        ), f"Renderer must report manifestless pass-through modules: {result}"
        assert unknown["module"] == "partner:ExperimentalAction"
        assert unknown["version"] == 7
        assert unknown["parameters"] == {"safe_mode": "review"}
        assert unknown["mapper"] == {
            "email": "{{1.email}}",
            "score": "{{1.score}}",
        }
        assert unknown["vendorPayload"] == {"shape": {"kept": True}}
        assert cast("JsonObject", metadata["vendorSafe"]) == {
            "note": "preserve"
        }
        assert "expect" not in metadata, (
            f"Unknown modules must not invent expect: {unknown}"
        )
        assert "restore" not in metadata, (
            f"Unknown modules must not invent restore: {unknown}"
        )
        assert "interface" not in metadata, (
            f"Unknown modules must not invent interface: {unknown}"
        )
        assert {"x", "y"} <= set(cast("JsonObject", metadata["designer"])), (
            f"Unknown module still needs Make designer coordinates: {unknown}"
        )


def test_make_export_internal_evidence_traces_c73704aa() -> None:
    """Render report evidence explains native projections without entering the.

    blueprint.
    """
    root = parse_make_ast_json_text(
        json.dumps(pass_through_unknown_module_blueprints()[-1])
    )

    result = render_make_blueprint_payload(
        root=root,
        catalog=catalog_with_unknown_partner_module(),
    )

    ledger = result.internal_evidence_ledger
    assert isinstance(ledger, dict), (
        f"Render report missed internal evidence: {result}"
    )
    entries = cast("tuple[JsonObject, ...]", ledger["entries"])
    evidence_pairs = {
        (entry.get("evidence_type"), entry.get("module"), entry.get("judgment"))
        for entry in entries
    }
    assert (
        "module_projector_manifest ",
        "slack:CreateMessage ",
        "make_native_module_projection",
    ) in evidence_pairs, (
        f"Supported module projection must be evidence-backed: {ledger}"
    )
    assert (
        "pass_through_unknown_module ",
        "partner:ExperimentalAction ",
        "preserve_without_native_parity_claim",
    ) in evidence_pairs, (
        f"Pass-through uncertainty must be evidence-backed: {ledger}"
    )
    encoded_blueprint = json.dumps(result.payload, sort_keys=True)
    assert "internal_evidence" not in encoded_blueprint, (
        f"Make blueprint payload must not leak internal evidence: "
        f"{result.payload}"
    )


def test_make_export_blocks_secret_like_unknown_module_contamination() -> None:
    """Pass-through does not weaken zero-trace for secret-like unknown module.

    fields.
    """
    payload = pass_through_unknown_module_blueprints()[0]
    unknown = _node_by_id(payload, 99)
    parameters = cast("JsonObject", unknown["parameters"])
    parameters["access_" + "token"] = "fixture-placeholder"
    root = parse_make_ast_json_text(json.dumps(payload))

    with pytest.raises(MakeBlueprintPrivateMetadataLeakError) as error:
        _ = render_make_blueprint_payload(
            root=root,
            catalog=catalog_with_unknown_partner_module(),
        )

    assert "$.flow[1].parameters.access_token" in error.value.paths, (
        f"Secret-like pass-through key must block export: {error.value.paths}"
    )


def test_make_export_lowers_router_filters_to_first_route_module() -> None:
    """Make-native export places typed route filters where Make roundtrips.

    them.
    """
    root = parse_make_ast_json_text(
        json.dumps(make_native_parity_draft_blueprint())
    )

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    router = cast("JsonObject", cast("list[object]", result.payload["flow"])[1])
    routes = cast("list[object]", router["routes"])
    first_route = cast("JsonObject", routes[0])
    first_route_node = cast(
        "JsonObject", cast("list[object]", first_route["flow"])[0]
    )
    assert "filter" not in first_route, (
        f"Make-native filter should not stay only on route wrapper: "
        f"{first_route}"
    )
    assert first_route_node.get("filter") == {
        "conditions": [
            [
                {"a": "{{1.email}}", "o": "exist"},
                {"a": "{{1.score}}", "o": "number:greaterorequal", "b": "80"},
            ]
        ],
        "name": "qualified",
    }


def test_make_export_merges_route_filter_with_first_module_filter() -> None:
    """Route lowering preserves existing first-module filters instead of.

    replacing them.
    """
    payload = make_native_parity_draft_blueprint()
    data_store = _first_route_node(payload)
    data_store["filter"] = {
        "conditions": [[{"a": "{{1.request_id}}", "o": "exist"}]],
        "name": "ready_record",
    }
    root = parse_make_ast_json_text(json.dumps(payload))

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    router = cast("JsonObject", cast("list[object]", result.payload["flow"])[1])
    first_route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    first_route_node = cast(
        "JsonObject", cast("list[object]", first_route["flow"])[0]
    )
    assert "filter" not in first_route, (
        f"Make-native route filter should not remain on the route wrapper: "
        f"{first_route}"
    )
    assert first_route_node.get("filter") == {
        "conditions": [
            [
                {"a": "{{1.request_id}}", "o": "exist"},
                {"a": "{{1.email}}", "o": "exist"},
                {"a": "{{1.score}}", "o": "number:greaterorequal", "b": "80"},
            ]
        ],
        "name": "ready_record + qualified",
    }


def test_make_export_lowers_text_filter_expressions_to_native_conditions() -> (
    None
):
    """String comparison and contains filters lower to Make text operator.

    conditions.
    """
    payload = make_native_parity_draft_blueprint()
    router = cast("JsonObject", cast("list[object]", payload["flow"])[1])
    route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    route["filter"] = {
        "expression": (
            '{{1.email}} = "ada@example.invalid" or contains({{1.email}}, "@")'
        ),
        "name": "email review",
    }
    root = parse_make_ast_json_text(json.dumps(payload))

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    rendered_router = cast(
        "JsonObject", cast("list[object]", result.payload["flow"])[1]
    )
    rendered_route = cast(
        "JsonObject", cast("list[object]", rendered_router["routes"])[0]
    )
    route_node = cast(
        "JsonObject", cast("list[object]", rendered_route["flow"])[0]
    )
    assert route_node.get("filter") == {
        "conditions": [
            [
                {
                    "a": "{{1.email}}",
                    "o": "text:equal ",
                    "b": "ada@example.invalid",
                }
            ],
            [{"a": "{{1.email}}", "o": "text:contains", "b": "@"}],
        ],
        "name": "email review",
    }


def test_make_export_projects_datastore_mapper_expect_restore_and_layout() -> (
    None
):
    """Data store exports use Make-native mapper shape, schema metadata, and.

    compact layout.
    """
    root = parse_make_ast_json_text(
        json.dumps(make_native_parity_draft_blueprint())
    )

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    router = cast("JsonObject", cast("list[object]", result.payload["flow"])[1])
    route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    data_store = cast("JsonObject", cast("list[object]", route["flow"])[0])
    metadata = cast("JsonObject", data_store["metadata"])
    mapper = cast("JsonObject", data_store["mapper"])

    assert mapper["key"] == "{{1.request_id}}"
    assert mapper["overwrite"] is False
    assert cast("JsonObject", mapper["data"])["email"] == "{{1.email}}"
    assert "request_id" not in cast("JsonObject", mapper["data"]), (
        f"Data Store record key should not be duplicated into mapper.data: "
        f"{mapper}"
    )
    assert "email" not in mapper, (
        f"Data Store mapper should not stay flat: {mapper}"
    )
    assert len(cast("list[object]", metadata["expect"])) == 3
    data_expect = next(
        cast("JsonObject", item)
        for item in cast("list[object]", metadata["expect"])
        if isinstance(item, dict)
        and cast("JsonObject", item).get("name") == "data"
    )
    data_spec_names = {
        str(cast("JsonObject", item).get("name"))
        for item in cast("list[object]", data_expect["spec"])
        if isinstance(item, dict)
    }
    assert {"email", "score", "status"} <= data_spec_names
    assert "request_id" not in data_spec_names
    assert cast("JsonObject", metadata["restore"]) == {
        "expect": {"overwrite": {"mode": "chose"}},
        "parameters": {"datastore": {"label": "Data store"}},
    }

    gateway = cast(
        "JsonObject", cast("list[object]", result.payload["flow"])[0]
    )
    gateway_metadata = cast("JsonObject", gateway["metadata"])
    gateway_interface_names = {
        str(cast("JsonObject", item).get("name"))
        for item in cast("list[object]", gateway_metadata["interface"])
        if isinstance(item, dict)
    }
    assert gateway["mapper"] == {}
    assert {"email", "request_id", "score"} <= gateway_interface_names
    assert cast(
        "JsonObject",
        cast("JsonObject", gateway_metadata["restore"])["parameters"],
    )["hook"] == {"label": "Webhook", "data": {"editable": "true"}}
    gateway_y = cast(
        "JsonObject", cast("JsonObject", gateway["metadata"])["designer"]
    )["y"]
    router_y = cast(
        "JsonObject", cast("JsonObject", router["metadata"])["designer"]
    )["y"]
    data_store_y = cast("JsonObject", metadata["designer"])["y"]
    assert gateway_y == router_y == 150
    assert data_store_y == 0


def test_make_export_keeps_runtime_placeholders_by_default() -> None:
    """Make export does not invent import-preview IDs unless explicitly.

    requested.
    """
    root = parse_make_ast_json_text(
        json.dumps(make_native_parity_draft_blueprint())
    )

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    payload_text = json.dumps(result.payload, sort_keys=True)
    assert "{{runtime.webhook.lead_intake}}" in payload_text
    assert "{{runtime.datastore.leads}}" in payload_text
    assert "mock-webhook-lead-intake" not in payload_text
    assert "mock-datastore-leads" not in payload_text


def test_make_export_mock_import_values_24cb41ec() -> None:
    """Make export can replace runtime aliases only for local Make UI import.

    previews.
    """
    root = parse_make_ast_json_text(
        json.dumps(make_native_parity_draft_blueprint())
    )

    result = render_make_blueprint_payload(
        root=root,
        catalog=parity_catalog(),
        placeholder_mode="mock_import_values",
    )

    gateway = cast(
        "JsonObject", cast("list[object]", result.payload["flow"])[0]
    )
    router = cast("JsonObject", cast("list[object]", result.payload["flow"])[1])
    route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    data_store = cast("JsonObject", cast("list[object]", route["flow"])[0])
    gateway_parameters = cast("JsonObject", gateway["parameters"])
    data_store_parameters = cast("JsonObject", data_store["parameters"])
    payload_text = json.dumps(result.payload, sort_keys=True)

    assert "{{runtime." not in payload_text
    assert gateway_parameters["hook"] == "mock-webhook-lead-intake"
    assert data_store_parameters["datastore"] == "mock-datastore-leads"
    assert cast("JsonObject", data_store["mapper"])["key"] == "{{1.request_id}}"


def test_make_export_sanitizes_notes_to_zero_trace_palette() -> None:
    """Importable notes keep only safe Make note metadata and approved.

    colors.
    """
    payload = make_native_parity_draft_blueprint()
    raw_notes = cast(
        "list[object]", cast("JsonObject", payload["metadata"])["notes"]
    )
    cast("JsonObject", raw_notes[0])["moduleIds"] = ["1"]
    root = parse_make_ast_json_text(json.dumps(payload))

    result = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    notes = cast(
        "list[object]", cast("JsonObject", result.payload["metadata"])["notes"]
    )
    assert notes, (
        f"Export should retain at least one safe Make note: {result.payload}"
    )
    first_note = cast("JsonObject", notes[0])
    assert first_note.get("moduleIds") == [1], (
        f"Make-native notes must anchor with numeric moduleIds: {first_note}"
    )
    for raw_note in notes:
        note = cast("JsonObject", raw_note)
        metadata = cast("JsonObject", note["metadata"])
        assert set(metadata) == {"color"}
        assert metadata["color"] in {
            "#9138FE",
            "#E34FD4",
            "#22B8B8",
            "#7DBE45",
            "#F5C542",
            "#FF8A80",
        }
        note_text = json.dumps(note, sort_keys=True).casefold()
        for forbidden in (
            "local-only ",
            "source_draft ",
            "pancakes ",
            "runtime placeholder ",
            "schoenwald",
        ):
            assert forbidden not in note_text


def test_make_export_fails_closed_on_private_raw_note_trace() -> None:
    """Zero-trace blocks contaminated notes before note sanitizer can hide.

    them.
    """
    payload = make_native_parity_draft_blueprint()
    notes = cast(
        "list[object]", cast("JsonObject", payload["metadata"])["notes"]
    )
    notes.append(
        {
            "content": (
                "<h2>Internal trace</h2><p>Local-only Pancakes "
                "source_draft note.</p>"
            ),
            "isFilterNote": False,
            "metadata": {"color": "#9138FE", "source": "source_draft"},
            "moduleIds": [1],
        }
    )
    root = parse_make_ast_json_text(json.dumps(payload))

    with pytest.raises(MakeBlueprintPrivateMetadataLeakError) as error:
        _ = render_make_blueprint_payload(root=root, catalog=parity_catalog())

    assert "$.metadata.notes[2].content" in error.value.paths
    assert "$.metadata.notes[2].metadata.source" in error.value.paths


def abstract_project_draft_blueprint() -> JsonObject:
    """Return the computed result for the caller."""
    return cast(
        "JsonObject",
        {
            "name": "enterprise lead operations triage",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {"hook": "enterprise-lead-intake-hook"},
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:gateway:1.14.1:trigger:CustomWebHook"
                            ),
                            "raw_spec_sha256": "1" * 64,
                            "status": "resolved",
                        },
                        "webhook": {"response_behavior": "immediate_ack"},
                        "rollback_posture": "draft-only",
                    },
                },
                {
                    "id": 2,
                    "module": "builtin:BasicRouter",
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:builtin:1.8.2:router:BasicRouter"
                            ),
                            "raw_spec_sha256": "2" * 64,
                            "status": "resolved",
                        },
                        "error_handling": {"mode": "classified"},
                    },
                    "routes": [
                        {
                            "flow": [
                                {
                                    "id": 4,
                                    "module": "slack:ActionCreateMessage",
                                    "parameters": {
                                        "account": "slack-ops-connection ",
                                        "channel": "sales-ops ",
                                        "text": "Qualified lead {{1.email}}",
                                    },
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:slack:2.14.3:action:ActionCreateMessage"
                                            ),
                                            "raw_spec_sha256": "3" * 64,
                                            "status": "resolved",
                                        },
                                        "runtime_connection": (
                                            "slack-ops-connection "
                                        ),
                                        "rollback_posture": "manual-disable",
                                    },
                                }
                            ],
                        }
                    ],
                },
            ],
            "metadata": {
                "placeholder_registry": [],
                "scenario": {"slots": None},
                "notes": [],
            },
        },
    )


def make_native_parity_draft_blueprint() -> JsonObject:
    """Return a synthetic draft that exercises Make-native parity lowering."""
    return cast(
        "JsonObject",
        {
            "name": "native parity draft",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {
                        "hook": "{{runtime.webhook.lead_intake}}",
                        "maxResults": 1,
                    },
                    "mapper": {
                        "email": "{{1.email}}",
                        "request_id": "{{1.request_id}}",
                        "score": "{{1.score}}",
                    },
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:gateway:1.14.1:trigger:CustomWebHook"
                            ),
                            "raw_spec_sha256": "1" * 64,
                            "status": "resolved",
                        },
                        "webhook": {"response_behavior": "immediate_ack"},
                    },
                },
                {
                    "id": 2,
                    "module": "builtin:BasicRouter",
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:builtin:1.8.3:router:BasicRouter"
                            ),
                            "raw_spec_sha256": "2" * 64,
                            "status": "resolved",
                        }
                    },
                    "routes": [
                        {
                            "filter": {
                                "name": "qualified",
                                "conditions": {
                                    "expression": "not empty({{1.email}}) and "
                                    "{{1.score}} >= 80"
                                },
                            },
                            "flow": [
                                {
                                    "id": 3,
                                    "module": "datastore:AddRecord",
                                    "parameters": {
                                        "datastore": "{{runtime.datastore.leads}}"
                                    },
                                    "mapper": {
                                        "email": "{{1.email}}",
                                        "request_id": "{{1.request_id}}",
                                        "score": "{{1.score}}",
                                        "status": "qualified",
                                    },
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:datastore:2.0.0:action:AddRecord"
                                            ),
                                            "raw_spec_sha256": "3" * 64,
                                            "status": "resolved",
                                        },
                                        "rollback_posture": "internal",
                                    },
                                }
                            ],
                        },
                        {
                            "filter": {
                                "name": "needs_remediation",
                                "conditions": {
                                    "expression": "empty({{1.email}})"
                                },
                            },
                            "flow": [
                                {
                                    "id": 4,
                                    "module": "datastore:AddRecord",
                                    "parameters": {
                                        "datastore": "{{runtime.datastore.remediation}}"
                                    },
                                    "mapper": {
                                        "request_id": "{{1.request_id}}"
                                    },
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:datastore:2.0.0:action:AddRecord"
                                            ),
                                            "raw_spec_sha256": "4" * 64,
                                            "status": "resolved",
                                        }
                                    },
                                }
                            ],
                        },
                    ],
                },
            ],
            "metadata": {
                "designer": {
                    "messages": [
                        {
                            "message": "Local-only draft runtime placeholder "
                            "warning."
                        }
                    ]
                },
                "notes": [
                    {
                        "content": (
                            "<h2>Lead intake</h2>"
                            "<p>Confirm the inbound lead contract before "
                            "activation.</p>"
                        ),
                        "isFilterNote": False,
                        "metadata": {"color": "#000000"},
                        "moduleIds": [1],
                    },
                    {
                        "content": (
                            "<h2>Lead intake</h2><p>Review qualified "
                            "lead flow.</p>"
                        ),
                        "isFilterNote": False,
                        "metadata": {"color": "#22B8B8"},
                        "moduleIds": [2],
                    },
                ],
                "placeholder_registry": [
                    {
                        "expected_type": "hook_id ",
                        "handoff_instructions": (
                            "Create the webhook before activation."
                        ),
                        "kind": "runtime_setup ",
                        "placeholder": "runtime.webhook.lead_intake",
                        "required": True,
                        "target_path": "/flow/0/parameters/hook",
                    },
                    {
                        "expected_type": "id ",
                        "handoff_instructions": (
                            "Create the leads data store before activation."
                        ),
                        "kind": "runtime_setup ",
                        "placeholder": "runtime.datastore.leads",
                        "required": True,
                        "target_path": (
                            "/flow/1/routes/0/flow/0/parameters/datastore"
                        ),
                    },
                    {
                        "expected_type": "id ",
                        "handoff_instructions": (
                            "Create the remediation data store before "
                            "activation."
                        ),
                        "kind": "runtime_setup ",
                        "placeholder": "runtime.datastore.remediation",
                        "required": True,
                        "target_path": (
                            "/flow/1/routes/1/flow/0/parameters/datastore"
                        ),
                    },
                ],
            },
        },
    )


def pass_through_unknown_module_blueprints() -> tuple[JsonObject, ...]:
    """Return fixtures where a manifestless module appears in important graph.

    positions.
    """
    return (
        cast(
            "JsonObject",
            {
                "name": "unknown linear",
                "flow": [_gateway_node(1), _unknown_partner_node()],
                "metadata": {"scenario": {"slots": None}},
            },
        ),
        cast(
            "JsonObject",
            {
                "name": "unknown router branch",
                "flow": [
                    _gateway_node(1),
                    {
                        "id": 2,
                        "module": "builtin:BasicRouter",
                        "routes": [{"flow": [_unknown_partner_node()]}],
                    },
                ],
                "metadata": {"scenario": {"slots": None}},
            },
        ),
        cast(
            "JsonObject",
            {
                "name": "unknown between known modules",
                "flow": [
                    _gateway_node(1),
                    _unknown_partner_node(),
                    _datastore_node(3),
                ],
                "metadata": {"scenario": {"slots": None}},
            },
        ),
        cast(
            "JsonObject",
            {
                "name": "unknown next to slack and datastore",
                "flow": [
                    _gateway_node(1),
                    {
                        "id": 2,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "flow": [
                                    _datastore_node(3),
                                    _unknown_partner_node(),
                                    _slack_node(4),
                                ]
                            }
                        ],
                    },
                ],
                "metadata": {"scenario": {"slots": None}},
            },
        ),
    )


def _gateway_node(node_id: int) -> JsonObject:
    return {
        "id": node_id,
        "module": "gateway:CustomWebHook",
        "parameters": {"hook": "lead-intake-hook", "maxResults": 1},
        "mapper": {"email": "{{1.email}}", "score": "{{1.score}}"},
    }


def _datastore_node(node_id: int) -> JsonObject:
    return {
        "id": node_id,
        "module": "datastore:AddRecord",
        "parameters": {"datastore": "leads-store"},
        "mapper": {"request_id": "{{1.request_id}}", "email": "{{1.email}}"},
    }


def _slack_node(node_id: int) -> JsonObject:
    return {
        "id": node_id,
        "module": "slack:CreateMessage",
        "parameters": {"__IMTCONN__": "__IMTCONN__"},
        "mapper": {"channel": "sales-ops", "text": "Lead {{1.email}}"},
    }


def _unknown_partner_node() -> JsonObject:
    return {
        "id": 99,
        "module": "partner:ExperimentalAction",
        "parameters": {"safe_mode": "review"},
        "mapper": {"email": "{{1.email}}", "score": "{{1.score}}"},
        "metadata": {"vendorSafe": {"note": "preserve"}},
        "vendorPayload": {"shape": {"kept": True}},
    }


def importable_http_blueprint_with_private_designer() -> JsonObject:
    """Return an otherwise importable HTTP payload with one private designer.

    key.
    """
    return cast(
        "JsonObject",
        {
            "name": "importable-http",
            "flow": [
                {
                    "id": 1,
                    "metadata": {
                        "designer": {"pancakes_trace": "internal-draft-id"},
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:http:1.0:action:makeRequest"
                            ),
                            "issues": [],
                            "raw_spec_sha256": "1" * 64,
                            "status": "resolved",
                        },
                    },
                    "module": HTTP_REQUEST_MODULE,
                    "parameters": {
                        "method": "POST ",
                        "url": "https://example.invalid",
                    },
                }
            ],
            "metadata": {"schedule": {"id": "schedule:daily"}},
        },
    )


def importable_http_blueprint_with_private_trace_text() -> JsonObject:
    """Return an importable HTTP payload with private trace wording in Make.

    metadata.
    """
    payload = importable_http_blueprint_with_private_designer()
    flow = cast("list[object]", payload["flow"])
    node = cast("JsonObject", flow[0])
    metadata = cast("JsonObject", node["metadata"])
    metadata["designer"] = {
        "messages": [
            {
                "message": (
                    "Schoenwald local draft source_draft "
                    "C:\\Users\\humbe\\pancakes.json"
                )
            }
        ]
    }
    return payload


def load_catalog_fixture() -> CatalogSnapshot:
    """Return the computed result for the caller."""
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )


def empty_catalog() -> CatalogSnapshot:
    """Return an empty catalog for Make built-in manifest fallback tests."""
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="empty-test-catalog",
        raw_spec_manifest_sha256="0" * 64,
        apps=(),
        fingerprint="0" * 64,
    )


def transpilation_catalog_without_builtin() -> CatalogSnapshot:
    """Return the transpilation catalog with provider modules but no built-in.

    modules.
    """
    catalog = transpilation_catalog()
    return catalog._replace(
        apps=tuple(app for app in catalog.apps if app.app_slug != "builtin"),
        fingerprint="a" * 64,
    )


def transpilation_catalog() -> CatalogSnapshot:
    """Return the computed result for the caller."""
    gateway = catalog_module(
        CatalogModuleSpec(
            app_slug="gateway",
            app_version="1.14.1",
            module_kind="trigger",
            internal_name="CustomWebHook",
            display_name="Custom webhook",
            raw_spec_sha256="a" * 64,
            fingerprint="1" * 64,
        )
    )
    builtin_old = catalog_module(
        CatalogModuleSpec(
            app_slug="builtin",
            app_version="1.8.2",
            module_kind="router",
            internal_name="BasicRouter",
            display_name="Basic router",
            raw_spec_sha256="b" * 64,
            fingerprint="2" * 64,
        )
    )
    builtin_current = catalog_module(
        CatalogModuleSpec(
            app_slug="builtin",
            app_version="1.8.3",
            module_kind="router",
            internal_name="BasicRouter",
            display_name="Basic router",
            raw_spec_sha256="c" * 64,
            fingerprint="3" * 64,
        )
    )
    slack_old = catalog_module(
        CatalogModuleSpec(
            app_slug="slack",
            app_version="2.14.3",
            module_kind="action",
            internal_name="ActionCreateMessage",
            display_name="Create a message",
            raw_spec_sha256="d" * 64,
            fingerprint="4" * 64,
        )
    )
    slack_current = catalog_module(
        CatalogModuleSpec(
            app_slug="slack",
            app_version="4.12.22",
            module_kind="action",
            internal_name="CreateMessage",
            display_name="Send a Message",
            raw_spec_sha256="e" * 64,
            fingerprint="5" * 64,
            parameter_paths=("channel", "text"),
            connection_parameter_path="__IMTCONN__",
        )
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-14T00:00:00+00:00",
        raw_spec_manifest_sha256="f" * 64,
        apps=(
            catalog_app(
                "builtin ",
                "Make builtin",
                (builtin_old, builtin_current),
                "6" * 64,
            ),
            catalog_app("gateway", "Webhooks", (gateway,), "7" * 64),
            catalog_app("slack", "Slack", (slack_old, slack_current), "8" * 64),
        ),
        fingerprint="9" * 64,
    )


def parity_catalog() -> CatalogSnapshot:
    """Return a synthetic catalog for Make-native parity projection tests."""
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-14T00:00:00+00:00",
        raw_spec_manifest_sha256="a" * 64,
        apps=(
            catalog_app(
                "builtin ",
                "Make builtin",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="builtin",
                            app_version="1.8.3",
                            module_kind="router",
                            internal_name="BasicRouter",
                            display_name="Basic router",
                            raw_spec_sha256="b" * 64,
                            fingerprint="1" * 64,
                        )
                    ),
                ),
                "2" * 64,
            ),
            catalog_app(
                "datastore ",
                "Data store",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="datastore",
                            app_version="2.0.0",
                            module_kind="action",
                            internal_name="AddRecord",
                            display_name="Add/replace a record",
                            raw_spec_sha256="c" * 64,
                            fingerprint="3" * 64,
                            parameter_paths=("datastore",),
                        )
                    ),
                ),
                "4" * 64,
            ),
            catalog_app(
                "gateway ",
                "Webhooks",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="gateway",
                            app_version="1.14.1",
                            module_kind="trigger",
                            internal_name="CustomWebHook",
                            display_name="Custom webhook",
                            raw_spec_sha256="d" * 64,
                            fingerprint="5" * 64,
                            parameter_paths=("hook", "maxResults"),
                        )
                    ),
                ),
                "6" * 64,
            ),
        ),
        fingerprint="7" * 64,
    )


def catalog_with_unknown_partner_module() -> CatalogSnapshot:
    """Return the computed result for the caller."""
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-14T00:00:00+00:00",
        raw_spec_manifest_sha256="8" * 64,
        apps=(
            catalog_app(
                "builtin ",
                "Make builtin",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="builtin",
                            app_version="1.8.3",
                            module_kind="router",
                            internal_name="BasicRouter",
                            display_name="Basic router",
                            raw_spec_sha256="1" * 64,
                            fingerprint="1" * 64,
                        )
                    ),
                ),
                "1" * 64,
            ),
            catalog_app(
                "datastore ",
                "Data store",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="datastore",
                            app_version="2.0.0",
                            module_kind="action",
                            internal_name="AddRecord",
                            display_name="Add/replace a record",
                            raw_spec_sha256="2" * 64,
                            fingerprint="2" * 64,
                            parameter_paths=("datastore",),
                        )
                    ),
                ),
                "2" * 64,
            ),
            catalog_app(
                "gateway ",
                "Webhooks",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="gateway",
                            app_version="1.14.1",
                            module_kind="trigger",
                            internal_name="CustomWebHook",
                            display_name="Custom webhook",
                            raw_spec_sha256="3" * 64,
                            fingerprint="3" * 64,
                            parameter_paths=("hook", "maxResults"),
                        )
                    ),
                ),
                "3" * 64,
            ),
            catalog_app(
                "partner ",
                "Partner",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="partner",
                            app_version="7.2.0",
                            module_kind="action",
                            internal_name="ExperimentalAction",
                            display_name="Experimental action",
                            raw_spec_sha256="4" * 64,
                            fingerprint="4" * 64,
                        )
                    ),
                ),
                "4" * 64,
            ),
            catalog_app(
                "slack ",
                "Slack",
                (
                    catalog_module(
                        CatalogModuleSpec(
                            app_slug="slack",
                            app_version="4.12.22",
                            module_kind="action",
                            internal_name="CreateMessage",
                            display_name="Send a Message",
                            raw_spec_sha256="5" * 64,
                            fingerprint="5" * 64,
                            parameter_paths=("channel", "text"),
                            connection_parameter_path="__IMTCONN__",
                        )
                    ),
                ),
                "5" * 64,
            ),
        ),
        fingerprint="6" * 64,
    )


def catalog_module(spec: CatalogModuleSpec) -> CatalogModule:
    """Return one synthetic catalog module for Make export tests."""
    module_id = f"module:{spec.app_slug}:{spec.app_version}:{spec.module_kind}:{spec.internal_name}"
    connection_parameters = (
        (
            catalog_connection_field(
                module_id=module_id,
                field_name=spec.connection_parameter_path,
            ),
        )
        if spec.connection_parameter_path is not None
        else ()
    )
    parameters = connection_parameters + tuple(
        catalog_field(module_id=module_id, field_name=field_name)
        for field_name in spec.parameter_paths
    )
    return CatalogModule(
        module_id=module_id,
        app_version_id=f"app-version:{spec.app_slug}:{spec.app_version}",
        app_slug=spec.app_slug,
        app_version=spec.app_version,
        module_kind=cast("CatalogModuleKind", spec.module_kind),
        internal_name=spec.internal_name,
        display_name=spec.display_name,
        external_id=(
            f"{spec.app_slug}:{spec.app_version}:{spec.module_kind}:{spec.internal_name}"
        ),
        deprecated=False,
        parameters=parameters,
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=spec.raw_spec_sha256,
        fingerprint=spec.fingerprint,
    )


def catalog_connection_field(
    *, module_id: str, field_name: str
) -> CatalogField:
    """Return one required synthetic Make connection field."""
    raw_schema: JsonObject = {
        "name": field_name,
        "required": True,
        "type": "account:slack2",
    }
    return CatalogField(
        field_id=f"{module_id}:parameter:{field_name}",
        module_id=module_id,
        direction=cast("CatalogFieldDirection", "parameter"),
        path=(field_name,),
        label="Connection",
        required=True,
        field_type="account:slack2",
        advanced=False,
        external_id=field_name,
        rpc_dependencies=(),
        raw_schema=raw_schema,
        constraints=(),
        fingerprint="0" * 64,
    )


def catalog_field(*, module_id: str, field_name: str) -> CatalogField:
    """Return one required synthetic parameter field."""
    raw_schema: JsonObject = {
        "name": field_name,
        "required": True,
        "type": "text",
    }
    return CatalogField(
        field_id=f"{module_id}:parameter:{field_name}",
        module_id=module_id,
        direction=cast("CatalogFieldDirection", "parameter"),
        path=(field_name,),
        label=field_name,
        required=True,
        field_type="text",
        advanced=False,
        external_id=field_name,
        rpc_dependencies=(),
        raw_schema=raw_schema,
        constraints=(),
        fingerprint="0" * 64,
    )


def catalog_app(
    app_slug: str,
    label: str,
    modules: tuple[CatalogModule, ...],
    fingerprint: str,
) -> CatalogApp:
    """Return one synthetic catalog app with each module in its own version."""
    versions = tuple(
        CatalogAppVersion(
            app_version_id=f"app-version:{app_slug}:{module.app_version}",
            app_id=f"app:{app_slug}",
            app_slug=app_slug,
            version=module.app_version,
            latest=module == modules[-1],
            manifest_version=1,
            modules=(module,),
            raw_spec_sha256=module.raw_spec_sha256,
            fingerprint=module.fingerprint,
        )
        for module in modules
    )
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=label,
        external_id=app_slug,
        deprecated=False,
        versions=versions,
        fingerprint=fingerprint,
    )


def _json_contains_key(value: object, expected_key: str) -> bool:
    """Return whether a JSON-compatible value contains a key anywhere."""
    if isinstance(value, dict):
        typed_value = cast("dict[object, object]", value)
        return any(
            key == expected_key or _json_contains_key(child, expected_key)
            for key, child in typed_value.items()
        )
    return isinstance(value, list) and any(
        _json_contains_key(item, expected_key)
        for item in cast("list[object]", value)
    )
