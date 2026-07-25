# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Deterministic diagnostic snapshots for typed Make AST structures.

Boundary contract:
- Owns: diagnostic snapshots of typed blueprint AST structures.
- Must not: parse payloads, validate semantics, or render importable blueprints.
- Allows: deterministic JSON-ready projection for tests and diagnostics.
- Split when: snapshot formats require independent versioned contracts.
- Merge when: another snapshot file emits the same diagnostic structure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blueprints.ast.models import (
        JsonObject,
        MakeAstFilter,
        MakeAstNode,
        MakeAstRawSpecBinding,
        MakeAstRoot,
        MakeAstRoute,
        MakeAstScenarioEndpoint,
        MakeAstScheduleConfig,
    )


def ast_root_snapshot(root: MakeAstRoot) -> JsonObject:
    """Return a deterministic diagnostic snapshot for one AST root."""
    return {
        "ast_schema_version": root.ast_schema_version,
        "scenario": {
            "name": root.scenario.name,
            "inputs": [
                _endpoint_snapshot(endpoint)
                for endpoint in root.scenario.inputs
            ],
            "outputs": [
                _endpoint_snapshot(endpoint)
                for endpoint in root.scenario.outputs
            ],
            "schedule": _schedule_snapshot(root.scenario.schedule),
        },
        "unknown_root_keys": sorted(root.unknown_fields),
        "flow": [_node_snapshot(node) for node in root.flow],
    }


def _node_snapshot(node: MakeAstNode) -> JsonObject:
    """Return a deterministic diagnostic snapshot for one AST node."""
    return {
        "node_id": node.node_id,
        "kind": node.kind,
        "module_token": node.module_token,
        "label": node.label,
        "path": list(node.source_trace.path),
        "container_kind": node.source_trace.container_kind,
        "parent_node_id": node.source_trace.parent_node_id,
        "raw_spec_binding": _binding_snapshot(node.raw_spec_binding),
        "unknown_keys": sorted(node.unknown_fields),
        "routes": [_route_snapshot(route) for route in node.routes],
        "branches": [_route_snapshot(route) for route in node.branches],
        "tools": [_route_snapshot(route) for route in node.tools],
        "error_handlers": [
            _node_snapshot(handler) for handler in node.error_handlers
        ],
    }


def _route_snapshot(route: MakeAstRoute) -> JsonObject:
    """Return a deterministic diagnostic snapshot for one route."""
    return {
        "route_id": route.route_id,
        "container_kind": route.container_kind,
        "path": list(route.source_trace.path),
        "filter": _filter_snapshot(route.filter),
        "flow": [_node_snapshot(node) for node in route.flow],
    }


def _filter_snapshot(filter_node: MakeAstFilter | None) -> JsonObject | None:
    """Return a deterministic diagnostic snapshot for one filter."""
    if filter_node is None:
        return None
    return {
        "filter_id": filter_node.filter_id,
        "kind": filter_node.kind,
        "name": filter_node.name,
        "conditions": filter_node.conditions,
    }


def _binding_snapshot(binding: MakeAstRawSpecBinding) -> JsonObject:
    """Return a deterministic diagnostic snapshot for raw-spec binding."""
    return {
        "status": binding.status,
        "catalog_module_id": binding.catalog_module_id,
        "raw_spec_sha256": binding.raw_spec_sha256,
        "issues": list(binding.issues),
    }


def _endpoint_snapshot(endpoint: MakeAstScenarioEndpoint) -> JsonObject:
    """Return a deterministic diagnostic snapshot for one scenario endpoint."""
    return {
        "endpoint_id": endpoint.endpoint_id,
        "kind": endpoint.kind,
        "name": endpoint.name,
    }


def _schedule_snapshot(
    schedule: MakeAstScheduleConfig | None,
) -> JsonObject | None:
    """Return a deterministic diagnostic snapshot for a schedule."""
    if schedule is None:
        return None
    return {
        "schedule_id": schedule.schedule_id,
        "kind": schedule.kind,
        "raw_keys": sorted(schedule.raw_payload),
    }
