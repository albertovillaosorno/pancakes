# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Assemble Make AST roots from canonical catalog module IDs.

Boundary contract:
- Owns: assembling AST roots from explicit catalog-backed node specs.
- Must not: select modules, render blueprint JSON, or persist output artifacts.
- Allows: catalog validation, node payload construction, and AST parsing.
- Split when: assembly defaults or routing templates need separate ownership.
- Merge when: another assembler builds the same AST root contract.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog import require_catalog_module, validate_catalog_snapshot

from blueprints.ast.parser import normalize_json_object, parse_make_ast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogModule, CatalogSnapshot

    from blueprints.ast.models import JsonObject, MakeAstRoot


EMPTY_ASSEMBLY_MAPPING: Final = cast(
    "Mapping[str, object]", MappingProxyType({})
)


class BlueprintNodeAssemblySpec(NamedTuple):
    """One catalog-backed node to assemble into a blueprint AST."""

    module_id: str
    parameters: Mapping[str, object] = EMPTY_ASSEMBLY_MAPPING
    mapper: Mapping[str, object] = EMPTY_ASSEMBLY_MAPPING


class BlueprintAssemblySpec(NamedTuple):
    """Catalog-backed blueprint assembly input."""

    name: str
    nodes: tuple[BlueprintNodeAssemblySpec, ...]
    schedule_id: str = "schedule:manual"
    metadata: Mapping[str, object] = EMPTY_ASSEMBLY_MAPPING


def assemble_blueprint_from_catalog(
    *,
    spec: BlueprintAssemblySpec,
    catalog: CatalogSnapshot,
) -> MakeAstRoot:
    """Assemble a Make AST root from canonical catalog module IDs.

    Returns:
        The result produced by assembling a Make AST root from canonical
        catalog module IDs.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    validate_catalog_snapshot(catalog)
    if not spec.nodes:
        message = "Blueprint assembly requires at least one node."
        raise ValueError(message)
    payload: JsonObject = {
        "name": spec.name,
        "flow": [
            _node_payload(index=index, node_spec=node_spec, catalog=catalog)
            for index, node_spec in enumerate(spec.nodes, start=1)
        ],
        "metadata": _metadata_payload(spec),
    }
    return parse_make_ast(payload)


def _node_payload(
    *,
    index: int,
    node_spec: BlueprintNodeAssemblySpec,
    catalog: CatalogSnapshot,
) -> JsonObject:
    module = require_catalog_module(catalog, node_spec.module_id).module
    payload: JsonObject = {
        "id": index,
        "module": _module_token(module),
        "version": 1,
        "metadata": {
            "designer": {
                "x": (index - 1) * 300,
                "y": 0,
                "messages": [],
            },
            "raw_spec": {
                "catalog_module_id": module.module_id,
                "issues": [],
                "raw_spec_sha256": module.raw_spec_sha256,
                "status": "resolved",
            },
        },
    }
    parameters = normalize_json_object(node_spec.parameters)
    mapper = normalize_json_object(node_spec.mapper)
    if parameters:
        payload["parameters"] = parameters
    if mapper:
        payload["mapper"] = mapper
    return payload


def _metadata_payload(spec: BlueprintAssemblySpec) -> JsonObject:
    metadata = normalize_json_object(spec.metadata)
    if "scenario" not in metadata:
        metadata["scenario"] = {"name": spec.name}
    if "designer" not in metadata:
        metadata["designer"] = {"messages": []}
    elif isinstance(metadata["designer"], dict):
        designer = normalize_json_object(
            cast("Mapping[str, object]", metadata["designer"])
        )
        _ = designer.setdefault("messages", [])
        metadata["designer"] = designer
    else:
        metadata["designer"] = {"messages": []}
    if "notes" not in metadata:
        metadata["notes"] = []
    if "placeholder_registry" not in metadata:
        metadata["placeholder_registry"] = []
    if "schedule" not in metadata:
        metadata["schedule"] = {"id": spec.schedule_id}
    return metadata


def _module_token(module: CatalogModule) -> str:
    return f"{module.app_slug}:{module.internal_name}"
