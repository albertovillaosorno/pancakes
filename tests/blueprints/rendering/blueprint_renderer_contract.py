# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make AST blueprint rendering.

Boundary contract:
- Owns: tests for Make AST rendering, assembly, and importable output gates.
- Must not: test raw scraper ingestion or generic validation policy.
- Allows: catalog-backed blueprint fixtures and rendered JSON assertions.
- Split when: assembly and rendering behavior need separate modules.
- Merge when: another renderer test duplicates these importable-output checks.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import (
    BlueprintAssemblySpec,
    BlueprintCompileRequest,
    BlueprintNodeAssemblySpec,
    assemble_blueprint_from_catalog,
    compile_blueprint_from_module_ids,
    parse_make_ast_json_text,
    require_ast_node,
)
from blueprints.validation import validate_blueprint
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from catalog.knowledge import KnowledgeRuleFact, KnowledgeStoreQuery
from languages.make.blueprint_export import (
    MakeBlueprintRenderError,
    MakeBlueprintRenderMode,
    render_make_blueprint_json_text,
    render_make_blueprint_payload,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogSnapshot

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
AST_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "make_ast"
    / "lead_routing_blueprint.json"
)
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
HTTP_REQUEST_MODULE = "http:" + "MakeRequest"
MIXED_ALIAS_ERROR_HANDLER_COUNT = 2


def test_make_ast_renderer_round_trips_draft_fixture_semantics() -> None:
    """Draft rendering preserves fixture structure even when unresolved nodes.

    exist.
    """
    root = parse_make_ast_json_text(AST_FIXTURE.read_text(encoding="utf-8"))
    result = render_make_blueprint_payload(
        root=root,
        catalog=load_catalog_fixture(),
        mode="draft",
    )
    rendered_root = parse_make_ast_json_text(json.dumps(result.payload))

    assert not (result.importable), (
        "Draft rendering must not be marked importable."
    )
    assert result.gate.blockers, (
        "Fixture draft should retain validation blockers for unresolved "
        "modules."
    )
    assert (
        require_ast_node(rendered_root, "3").module_token == HTTP_REQUEST_MODULE
    ), "Rendered fixture lost the HTTP module token."
    assert require_ast_node(rendered_root, "2").routes, (
        "Rendered fixture lost router route structure."
    )
    assert (
        require_ast_node(rendered_root, "3").unknown_fields.get(
            "x-vendor-extra"
        )
        is not None
    ), "Rendered fixture lost unknown node fields."
    metadata = result.payload.get("metadata")
    assert isinstance(metadata, dict), (
        f"Rendered fixture lost root metadata: {result.payload}"
    )
    typed_metadata = cast("JsonObject", metadata)
    notes_value = typed_metadata.get("notes")
    assert isinstance(notes_value, list), (
        f"Rendered fixture lost Make-native notes: {typed_metadata}"
    )
    notes = cast("list[object]", notes_value)
    assert len(notes) == 1, (
        f"Rendered fixture lost Make-native notes: {metadata}"
    )


def test_make_ast_renderer_refuses_unresolved_importable_blueprint() -> None:
    """Importable rendering fails when the validation gate blocks the AST."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "unresolved",
                "flow": [{"id": 1, "module": "unknown-service:MissingAction"}],
            }
        )
    )

    with pytest.raises(MakeBlueprintRenderError) as error:
        _ = render_make_blueprint_payload(
            root=root, catalog=load_catalog_fixture()
        )

    blockers = error.value.blockers
    assert blockers, (
        f"Renderer did not expose unsupported-module blocker: {blockers}"
    )
    assert blockers[0].code == "generation.unsupported_module", (
        f"Renderer did not expose unsupported-module blocker: {blockers}"
    )


def test_make_ast_renderer_applies_knowledge_backed_gate_errors() -> None:
    """Importable rendering uses promoted knowledge when the caller.

    supplies it.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "sequential-webhook-response-render",
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "response": {"status": 200},
                        "parameters": {"processing": "sequential"},
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )

    with pytest.raises(MakeBlueprintRenderError) as error:
        _ = render_make_blueprint_payload(
            root=root,
            catalog=load_catalog_fixture(),
            knowledge=webhook_knowledge_query(),
        )

    assert any(
        blocker.code == "generation.validation_failed"
        and "webhook.sequential_response_conflict" in blocker.blocker_id
        for blocker in error.value.blockers
    ), (
        f"Renderer did not expose the promoted webhook blocker: "
        f"{error.value.blockers}"
    )


def test_make_ast_renderer_rejects_invalid_mode_before_validation() -> None:
    """Render mode validation is not hidden by blueprint blockers."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "unresolved",
                "flow": [{"id": 1, "module": "unknown-service:MissingAction"}],
            }
        )
    )
    invalid_mode = cast("MakeBlueprintRenderMode", "preview")

    with pytest.raises(
        ValueError, match="Unsupported Make blueprint render mode"
    ):
        _ = render_make_blueprint_payload(
            root=root,
            catalog=load_catalog_fixture(),
            mode=invalid_mode,
        )


def test_make_ast_renderer_emits_importable_json_after_validation_gate() -> (
    None
):
    """Importable render output parses and validates without blocking.

    findings.
    """
    catalog = load_catalog_fixture()
    root = parse_make_ast_json_text(json.dumps(importable_http_blueprint()))
    rendered_text = render_make_blueprint_json_text(root=root, catalog=catalog)
    rendered_root = parse_make_ast_json_text(rendered_text)
    report = validate_blueprint(root=rendered_root, catalog=catalog)

    assert not (report.has_errors), (
        f"Rendered importable JSON should validate: {report}"
    )
    assert require_ast_node(rendered_root, "1").raw_payload.get(
        "parameters"
    ) == {
        "method": "POST ",
        "url": "https://example.invalid",
    }, "Rendered JSON did not preserve module parameters."


def test_make_ast_renderer_does_not_duplicate_error_handler_aliases() -> None:
    """Rendering mixed direct error-handler aliases emits one handler.

    container.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "mixed-error-handler-aliases",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "onerror": [{"id": 2, "module": "builtin:Ignore"}],
                        "on_error": [{"id": 3, "module": "builtin:Break"}],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    typed_flow = cast("list[object]", flow)
    node_payload = typed_flow[0]
    assert isinstance(node_payload, dict), (
        f"Rendered node is invalid: {node_payload}"
    )
    rendered_node = cast("JsonObject", node_payload)

    assert "on_error" not in rendered_node, (
        f"Renderer left a stale direct-error alias: {rendered_node}"
    )
    handlers = rendered_node.get("onerror")
    assert isinstance(handlers, list), (
        f"Renderer did not consolidate direct error handlers: {rendered_node}"
    )
    typed_handlers = cast("list[object]", handlers)
    assert len(typed_handlers) == MIXED_ALIAS_ERROR_HANDLER_COUNT, (
        f"Renderer did not consolidate direct error handlers: {rendered_node}"
    )


def test_make_ast_renderer_preserves_single_error_handler_object_shape() -> (
    None
):
    """A single object-shaped direct error handler stays object-shaped."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "object-error-handler",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "onerror": {"id": 2, "module": "builtin:Ignore"},
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    typed_flow = cast("list[object]", flow)
    node_payload = typed_flow[0]
    assert isinstance(node_payload, dict), (
        f"Rendered node is invalid: {node_payload}"
    )
    rendered_node = cast("JsonObject", node_payload)

    handler = rendered_node.get("onerror")
    assert isinstance(handler, dict), (
        f"Single direct error handler shape changed: {rendered_node}"
    )
    assert cast("JsonObject", handler).get("module") == "builtin:Ignore", (
        f"Single direct error handler payload changed: {rendered_node}"
    )


def test_make_ast_renderer_preserves_filter_alias_shape() -> None:
    """Alias-only route filters do not gain synthetic canonical fields."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "filter-alias-shape",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {"condition": "{{1.amount}} > 500"},
                                "flow": [
                                    {"id": 2, "module": "http:MakeRequest"}
                                ],
                            }
                        ],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    router = cast("JsonObject", cast("list[object]", flow)[0])
    routes = router.get("routes")
    assert isinstance(routes, list), f"Rendered routes are missing: {router}"
    route = cast("JsonObject", cast("list[object]", routes)[0])
    filter_payload = route.get("filter")
    assert isinstance(filter_payload, dict), (
        f"Rendered filter is missing: {route}"
    )
    rendered_filter = cast("JsonObject", filter_payload)

    assert rendered_filter == {"condition": "{{1.amount}} > 500"}, (
        f"Renderer changed alias-only filter shape: {rendered_filter}"
    )


def test_make_ast_renderer_preserves_mixed_filter_condition_shape() -> None:
    """Filters with condition operators keep their raw conditions list."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "mixed-filter-condition-shape",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {
                                    "condition": "and",
                                    "conditions": [
                                        {
                                            "a": "{{1.amount}}",
                                            "operator": "gt",
                                            "b": 500,
                                        }
                                    ],
                                },
                                "flow": [
                                    {"id": 2, "module": "http:MakeRequest"}
                                ],
                            }
                        ],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    router = cast("JsonObject", cast("list[object]", flow)[0])
    routes = router.get("routes")
    assert isinstance(routes, list), f"Rendered routes are missing: {router}"
    route = cast("JsonObject", cast("list[object]", routes)[0])
    filter_payload = route.get("filter")
    assert isinstance(filter_payload, dict), (
        f"Rendered filter is missing: {route}"
    )
    rendered_filter = cast("JsonObject", filter_payload)

    conditions = rendered_filter.get("conditions")
    assert isinstance(conditions, list), (
        f"Renderer replaced the raw conditions list: {rendered_filter}"
    )
    assert rendered_filter.get("condition") == "and", (
        f"Renderer lost the filter condition operator: {rendered_filter}"
    )


def test_make_ast_renderer_preserves_raw_filter_conditions_list() -> None:
    """Raw conditions lists without aliases stay list-shaped."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "raw-filter-conditions-list",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {
                                    "conditions": [
                                        {
                                            "a": "{{1.amount}}",
                                            "operator": "gt",
                                            "b": 500,
                                        }
                                    ],
                                },
                                "flow": [
                                    {"id": 2, "module": "http:MakeRequest"}
                                ],
                            }
                        ],
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    router = cast("JsonObject", cast("list[object]", flow)[0])
    routes = router.get("routes")
    assert isinstance(routes, list), f"Rendered routes are missing: {router}"
    route = cast("JsonObject", cast("list[object]", routes)[0])
    filter_payload = route.get("filter")
    assert isinstance(filter_payload, dict), (
        f"Rendered filter is missing: {route}"
    )
    rendered_filter = cast("JsonObject", filter_payload)

    conditions = rendered_filter.get("conditions")
    assert isinstance(conditions, list), (
        f"Renderer replaced the raw conditions list: {rendered_filter}"
    )


def test_make_ast_renderer_preserves_padded_string_node_ids() -> None:
    """Numeric-looking string IDs remain strings when conversion would change.

    identity.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "padded-node-id",
                "flow": [{"id": "01", "module": "http:MakeRequest"}],
                "metadata": {"schedule": {"id": "schedule:daily"}},
            }
        )
    )
    result = render_make_blueprint_payload(
        root=root, catalog=load_catalog_fixture(), mode="draft"
    )
    flow = result.payload.get("flow")
    assert isinstance(flow, list), f"Rendered flow is missing: {result.payload}"
    typed_flow = cast("list[object]", flow)
    node_payload = typed_flow[0]
    assert isinstance(node_payload, dict), (
        f"Rendered node is invalid: {node_payload}"
    )
    rendered_node = cast("JsonObject", node_payload)

    assert rendered_node.get("id") == "01", (
        f"Renderer changed padded node identity: {rendered_node}"
    )


def test_make_ast_assembler_builds_catalog_backed_importable_blueprint() -> (
    None
):
    """Catalog-backed assembly emits an AST that can render without invented.

    modules.
    """
    catalog = load_catalog_fixture()
    root = assemble_blueprint_from_catalog(
        spec=BlueprintAssemblySpec(
            name="assembled-http",
            nodes=(
                BlueprintNodeAssemblySpec(
                    module_id="module:http:1.0:action:makeRequest",
                    parameters={
                        "method": "POST ",
                        "url": "https://example.invalid",
                    },
                ),
            ),
        ),
        catalog=catalog,
    )
    rendered_text = render_make_blueprint_json_text(root=root, catalog=catalog)
    rendered_root = parse_make_ast_json_text(rendered_text)
    report = validate_blueprint(root=rendered_root, catalog=catalog)

    assert not (report.has_errors), (
        f"Assembled blueprint should validate: {report}"
    )
    node_payload = require_ast_node(rendered_root, "1").raw_payload
    assert (
        require_ast_node(rendered_root, "1").raw_spec_binding.catalog_module_id
        is None
    ), (
        "Importable Make output must not leak Pancakes raw-spec catalog "
        "bindings."
    )
    assert node_payload.get("version") == 1, (
        f"Assembler emitted an invalid node version: {node_payload}"
    )
    node_metadata = node_payload.get("metadata")
    assert isinstance(node_metadata, dict), (
        f"Assembler lost node metadata: {node_payload}"
    )
    assert "raw_spec" not in node_metadata, (
        f"Importable Make output leaked raw-spec metadata: {node_metadata}"
    )
    node_designer = cast("JsonObject", node_metadata).get("designer")
    assert isinstance(node_designer, dict), (
        f"Assembler lost node designer metadata: {node_metadata}"
    )

    root_metadata = rendered_root.raw_payload.get("metadata")
    assert isinstance(root_metadata, dict), (
        f"Assembler lost root metadata: {rendered_root.raw_payload}"
    )
    typed_root_metadata = cast("JsonObject", root_metadata)
    for key in ("scenario", "designer", "notes", "version"):
        assert not (key not in typed_root_metadata), (
            f"Assembler metadata is missing {key}: {typed_root_metadata}"
        )
    for key in ("placeholder_registry", "schedule"):
        assert key not in typed_root_metadata, (
            f"Importable Make output leaked draft metadata {key}: "
            f"{typed_root_metadata}"
        )


def test_make_ast_compiler_rejects_unknown_catalog_module_ids() -> None:
    """Compile requests cannot invent modules absent from the catalog."""
    catalog = load_catalog_fixture()
    request = BlueprintCompileRequest(
        name="unknown-module",
        goal="Use a module that is not catalog-backed.",
        module_ids=("module:missing:1.0:action:invented",),
    )

    with pytest.raises(LookupError, match="does not exist"):
        _ = compile_blueprint_from_module_ids(request=request, catalog=catalog)


def importable_http_blueprint() -> JsonObject:
    """Return a minimal catalog-backed blueprint payload."""
    return {
        "name": "importable-http",
        "flow": [
            {
                "id": 1,
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:http:1.0:action:makeRequest"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "1" * 64,
                        "status": "resolved",
                    }
                },
                "module": HTTP_REQUEST_MODULE,
                "parameters": {
                    "method": "POST ",
                    "url": "https://example.invalid",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def webhook_knowledge_query() -> KnowledgeStoreQuery:
    """Return a minimal knowledge projection with a promoted webhook rule."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-webhook-sequential-response-conflict",
                domain="webhooks",
                rule_code="webhook.sequential_response_conflict",
                severity="error",
                description=(
                    "Sequential webhook processing conflicts with webhook "
                    "responses."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

    Returns:
        The loaded value.
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
