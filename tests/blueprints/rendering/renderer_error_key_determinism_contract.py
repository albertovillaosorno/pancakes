# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Renderer contract tests for direct error-handler alias determinism.

Boundary contract:
- Owns: focused renderer coverage for onerror/on_error alias selection.
- Must not: validate live Make behavior, contact services, or test repair
policy.
- Allows: sanitized inline AST payloads and deterministic draft rendering
assertions.
- Split when: broader renderer importability or validation-gate behavior
changes.
- Merge when: the main renderer contract owns these exact alias-determinism
cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from languages.make.blueprint_export import (
    render_make_blueprint_json_text,
    render_make_blueprint_payload,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogSnapshot

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
DIRECT_ERROR_KEY = "on" + "error"
DIRECT_ERROR_ALIAS_KEY = "on_" + "error"


def test_renderer_preserves_onerror_alias_when_it_is_the_only_raw_key() -> None:
    """A blueprint with only onerror renders back through onerror."""
    rendered_node = _rendered_first_node(
        _blueprint_with_handlers(DIRECT_ERROR_KEY)
    )

    assert not (DIRECT_ERROR_KEY not in rendered_node), (
        f"Renderer lost the direct error key: {rendered_node}"
    )
    assert DIRECT_ERROR_ALIAS_KEY not in rendered_node, (
        f"Renderer introduced the alias key: {rendered_node}"
    )


def test_renderer_preserves_on_error_alias_when_it_is_the_only_raw_key() -> (
    None
):
    """A blueprint with only on_error renders back through on_error."""
    rendered_node = _rendered_first_node(
        _blueprint_with_handlers(DIRECT_ERROR_ALIAS_KEY)
    )

    assert not (DIRECT_ERROR_ALIAS_KEY not in rendered_node), (
        f"Renderer lost the direct error alias key: {rendered_node}"
    )
    assert DIRECT_ERROR_KEY not in rendered_node, (
        f"Renderer rewrote the only raw alias key: {rendered_node}"
    )


def test_renderer_prefers_onerror_when_both_error_handler_aliases_exist() -> (
    None
):
    """Mixed direct error-handler aliases render through the canonical ordered.

    key.
    """
    rendered_node = _rendered_first_node(_blueprint_with_both_handler_aliases())

    assert DIRECT_ERROR_ALIAS_KEY not in rendered_node, (
        f"Renderer left a stale direct error alias: {rendered_node}"
    )
    handlers = rendered_node.get(DIRECT_ERROR_KEY)
    assert isinstance(handlers, list), (
        f"Renderer did not consolidate mixed aliases: {rendered_node}"
    )
    typed_handlers = cast("list[object]", handlers)
    handler_ids = tuple(
        cast("JsonObject", handler).get("id")
        for handler in typed_handlers
        if isinstance(handler, dict)
    )
    assert handler_ids == (2, 3), (
        f"Renderer changed direct handler order: {rendered_node}"
    )


def test_renderer_repeated_json_output_uses_identical_error_handler_key() -> (
    None
):
    """Repeated rendering of mixed aliases produces byte-identical JSON text."""
    root = parse_make_ast_json_text(
        json.dumps(_blueprint_with_both_handler_aliases())
    )
    catalog = load_catalog_fixture()

    rendered_texts = tuple(
        render_make_blueprint_json_text(
            root=root, catalog=catalog, mode="draft"
        )
        for _ in range(5)
    )

    assert len(set(rendered_texts)) == 1, (
        f"Renderer output changed across repeated calls: {rendered_texts}"
    )
    rendered_payload = cast("JsonObject", json.loads(rendered_texts[0]))
    flow = rendered_payload.get("flow")
    assert isinstance(flow, list), (
        f"Rendered flow is missing: {rendered_payload}"
    )
    rendered_node = cast("JsonObject", cast("list[object]", flow)[0])
    assert not (DIRECT_ERROR_KEY not in rendered_node), (
        f"Renderer used an unstable direct error key: {rendered_node}"
    )
    assert DIRECT_ERROR_ALIAS_KEY not in rendered_node, (
        f"Renderer used an unstable direct error key: {rendered_node}"
    )


def _rendered_first_node(payload: JsonObject) -> JsonObject:
    """Render a payload in draft mode and return its first node payload.

    Returns:
        The first rendered node payload.
    """
    root = parse_make_ast_json_text(json.dumps(payload))
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
    return cast("JsonObject", node_payload)


def _blueprint_with_handlers(error_key: str) -> JsonObject:
    """Return a sanitized blueprint with one direct error-handler alias."""
    return {
        "name": f"{error_key.replace('_', '-')}-determinism",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                error_key: [{"id": 2, "module": "builtin:Ignore"}],
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def _blueprint_with_both_handler_aliases() -> JsonObject:
    """Return a sanitized blueprint with both direct error-handler aliases."""
    return {
        "name": "mixed-error-handler-key-determinism",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                DIRECT_ERROR_KEY: [{"id": 2, "module": "builtin:Ignore"}],
                DIRECT_ERROR_ALIAS_KEY: [{"id": 3, "module": "builtin:Break"}],
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

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
