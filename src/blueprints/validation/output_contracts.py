# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate references against declared Make node output contracts.

Boundary contract:
- Owns: output-field reference checks against declared node output contracts.
- Must not: validate catalog truth, mutate AST nodes, or repair mappings.
- Allows: AST-backed expression reference usages and deterministic findings.
- Split when: output schema parsing or reference extraction becomes independent.
- Merge when: another checker reports the same output-reference findings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.ast.references import collect_reference_usages
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.models import BlueprintValidationFinding

if TYPE_CHECKING:
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )

OUTPUT_CONTRACT_KEYS: Final = ("interface", "outputs", "output_schema")
FIELD_NAME_KEYS: Final = ("name", "key", "id")
FIELD_CHILD_KEYS: Final = (
    "fields",
    "items",
    "children",
    "properties",
    "schema",
    "spec",
)
FIELD_METADATA_KEYS: Final = frozenset(
    {
        "default",
        "description",
        "help",
        "id",
        "key",
        "label",
        "name",
        "options",
        "required",
        "semantic",
        "type",
    }
)
MODULE_OUTPUT_WRAPPER_ALIASES: Final = {"slackwatchnewevents": ("message",)}


class OutputContract(NamedTuple):
    """Declared output fields plus dynamic object roots."""

    fields: frozenset[str]
    dynamic_parents: frozenset[str]


class OutputReference(NamedTuple):
    """One Make expression reference from a consumer node to a source node.

    field.
    """

    consumer_node: MakeAstNode
    source_node_id: str
    field_path: str
    source_path: tuple[AstPathPart, ...]


def validate_output_references(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for references to undeclared output fields."""
    nodes = iter_ast_nodes(root)
    nodes_by_id = _nodes_grouped_by_id(nodes)
    contracts = {
        node_id: _declared_output_contract(group[0])
        for node_id, group in nodes_by_id.items()
        if len(group) == 1
    }
    findings: list[BlueprintValidationFinding] = []
    seen: set[tuple[str, str, str, tuple[AstPathPart, ...]]] = set()
    duplicate_seen: set[tuple[str, str, tuple[AstPathPart, ...]]] = set()
    for reference in _output_references(root=root, nodes_by_id=nodes_by_id):
        source_nodes = nodes_by_id.get(reference.source_node_id, ())
        if not source_nodes:
            findings.append(_unknown_node_reference_finding(reference))
            continue
        if len(source_nodes) > 1:
            signature = (
                reference.consumer_node.node_id,
                reference.source_node_id,
                reference.source_path,
            )
            if signature in duplicate_seen:
                continue
            duplicate_seen.add(signature)
            findings.append(
                _duplicate_node_reference_finding(
                    reference=reference,
                    source_nodes=source_nodes,
                )
            )
            continue
        if not reference.field_path:
            continue
        contract = contracts.get(reference.source_node_id)
        if contract is None or _contract_allows_field(
            reference.field_path, contract
        ):
            continue
        signature = (
            reference.consumer_node.node_id,
            reference.source_node_id,
            reference.field_path,
            reference.source_path,
        )
        if signature in seen:
            continue
        seen.add(signature)
        findings.append(
            _unknown_output_finding(reference=reference, contract=contract)
        )
    return tuple(findings)


def _output_references(
    *,
    root: MakeAstRoot,
    nodes_by_id: dict[str, tuple[MakeAstNode, ...]],
) -> tuple[OutputReference, ...]:
    references: list[OutputReference] = []
    for usage in collect_reference_usages(root):
        consumer_nodes = nodes_by_id.get(usage.consumer_node_id, ())
        if not consumer_nodes:
            continue
        consumer_node = consumer_nodes[0]
        references.append(
            OutputReference(
                consumer_node=consumer_node,
                source_node_id=usage.source_node_id,
                field_path=usage.field_path,
                source_path=usage.expression_path,
            )
        )
    return tuple(references)


def _nodes_grouped_by_id(
    nodes: tuple[MakeAstNode, ...],
) -> dict[str, tuple[MakeAstNode, ...]]:
    grouped: dict[str, list[MakeAstNode]] = {}
    for node in nodes:
        grouped.setdefault(node.node_id, []).append(node)
    return {node_id: tuple(group) for node_id, group in grouped.items()}


def _declared_output_contract(node: MakeAstNode) -> OutputContract | None:
    fields: set[str] = set()
    dynamic_parents: set[str] = set()
    for contract in _declared_output_contracts(node):
        contract_fields, contract_dynamic_parents = _output_field_names(
            contract, prefix=""
        )
        fields.update(contract_fields)
        dynamic_parents.update(contract_dynamic_parents)
    if not fields:
        return None
    alias_fields, alias_dynamic_parents = _module_output_alias_fields(
        node=node,
        fields=fields,
        dynamic_parents=dynamic_parents,
    )
    fields.update(alias_fields)
    dynamic_parents.update(alias_dynamic_parents)
    return OutputContract(
        fields=frozenset(fields), dynamic_parents=frozenset(dynamic_parents)
    )


def _declared_output_contracts(node: MakeAstNode) -> tuple[object, ...]:
    contracts = [
        node.raw_payload[key]
        for key in OUTPUT_CONTRACT_KEYS
        if key in node.raw_payload
    ]
    metadata = node.raw_payload.get("metadata")
    if _is_json_object(metadata):
        contracts.extend(
            metadata[key] for key in OUTPUT_CONTRACT_KEYS if key in metadata
        )
    return tuple(contracts)


def _output_field_names(
    value: object, *, prefix: str
) -> tuple[set[str], set[str]]:
    if isinstance(value, list):
        return _list_output_field_names(
            cast("list[object]", value), prefix=prefix
        )
    if not _is_json_object(value):
        return set(), set()
    explicit_name = _explicit_field_name(value)
    if explicit_name:
        return _named_output_field_names(
            value, field_name=_join_path(prefix, explicit_name)
        )
    return _anonymous_output_field_names(value, prefix=prefix)


def _list_output_field_names(
    value: list[object], *, prefix: str
) -> tuple[set[str], set[str]]:
    fields: set[str] = set()
    dynamic_parents: set[str] = set()
    for item in value:
        item_fields, item_dynamic_parents = _output_field_names(
            item, prefix=prefix
        )
        fields.update(item_fields)
        dynamic_parents.update(item_dynamic_parents)
    return fields, dynamic_parents


def _named_output_field_names(
    value: JsonObject,
    *,
    field_name: str,
) -> tuple[set[str], set[str]]:
    fields = {field_name}
    dynamic_parents: set[str] = set()
    for child_key in FIELD_CHILD_KEYS:
        child_fields, child_dynamic = _output_field_names(
            value.get(child_key), prefix=field_name
        )
        fields.update(child_fields)
        dynamic_parents.update(child_dynamic)
    if _schema_allows_dynamic_children(value) and not _has_declared_child(
        field_name, fields
    ):
        dynamic_parents.add(field_name)
    return fields, dynamic_parents


def _anonymous_output_field_names(
    value: JsonObject, *, prefix: str
) -> tuple[set[str], set[str]]:
    child_fields: set[str] = set()
    child_dynamic: set[str] = set()
    for child_key in FIELD_CHILD_KEYS:
        fields, dynamic_parents = _output_field_names(
            value.get(child_key), prefix=prefix
        )
        child_fields.update(fields)
        child_dynamic.update(dynamic_parents)
    if child_fields:
        return child_fields, child_dynamic
    return _mapping_output_field_names(value, prefix=prefix)


def _mapping_output_field_names(
    value: JsonObject, *, prefix: str
) -> tuple[set[str], set[str]]:
    fields: set[str] = set()
    dynamic_parents: set[str] = set()
    for raw_key, child in value.items():
        if raw_key in FIELD_METADATA_KEYS:
            continue
        field_name = _join_path(prefix, raw_key)
        fields.add(field_name)
        child_fields, child_dynamic = _output_field_names(
            child, prefix=field_name
        )
        fields.update(child_fields)
        dynamic_parents.update(child_dynamic)
        if _value_allows_dynamic_children(child) and not _has_declared_child(
            field_name,
            child_fields,
        ):
            dynamic_parents.add(field_name)
    return fields, dynamic_parents


def _module_output_alias_fields(
    *,
    node: MakeAstNode,
    fields: set[str],
    dynamic_parents: set[str],
) -> tuple[set[str], set[str]]:
    aliases = MODULE_OUTPUT_WRAPPER_ALIASES.get(
        module_token_semantic_key(node.module_token), ()
    )
    alias_fields: set[str] = set()
    alias_dynamic_parents: set[str] = set()
    for alias in aliases:
        alias_fields.update(f"{alias}.{field}" for field in fields)
        alias_dynamic_parents.update(
            f"{alias}.{parent}" for parent in dynamic_parents
        )
    return alias_fields, alias_dynamic_parents


def _contract_allows_field(field_path: str, contract: OutputContract) -> bool:
    normalized_fields = {
        _normalized_field_path_segments(field) for field in contract.fields
    }
    normalized_path = _normalized_field_path_segments(field_path)
    if normalized_path in normalized_fields:
        return True
    index_free_path = _normalized_field_path_segments(
        _field_path_without_numeric_indexes(field_path)
    )
    if index_free_path in normalized_fields:
        return True
    return any(
        _field_path_is_child_of(field_path, parent)
        for parent in contract.dynamic_parents
    )


def _unknown_output_finding(
    *,
    reference: OutputReference,
    contract: OutputContract,
) -> BlueprintValidationFinding:
    allowed = ", ".join(sorted(contract.fields))
    return BlueprintValidationFinding(
        finding_id=(
            "error:semantic.output_field_unknown:"
            f"{_reference_finding_key(reference)}"
        ),
        severity="error",
        code="semantic.output_field_unknown",
        node_id=reference.consumer_node.node_id,
        client_message=(
            "A mapping expression references an undeclared output field."
        ),
        internal_message=(
            f"Node {reference.consumer_node.node_id} references field "
            f"{reference.field_path!r} from node {reference.source_node_id!r}; "
            f"declared fields: {allowed}."
        ),
        catalog_module_id=None,
        source_path=reference.source_path,
    )


def _unknown_node_reference_finding(
    reference: OutputReference,
) -> BlueprintValidationFinding:
    """Return one finding for a reference to a missing source node."""
    return BlueprintValidationFinding(
        finding_id=(
            "error:semantic.reference_unknown_node:"
            f"{_reference_finding_key(reference)}"
        ),
        severity="error",
        code="semantic.reference_unknown_node",
        node_id=reference.consumer_node.node_id,
        client_message="A mapping expression references an unknown module.",
        internal_message=(
            f"Node {reference.consumer_node.node_id} references missing node "
            f"{reference.source_node_id!r}."
        ),
        catalog_module_id=None,
        source_path=reference.source_path,
    )


def _duplicate_node_reference_finding(
    *,
    reference: OutputReference,
    source_nodes: tuple[MakeAstNode, ...],
) -> BlueprintValidationFinding:
    """Return one finding for a reference to an ambiguous duplicated source.

    node.
    """
    source_paths = ", ".join(
        str(node.source_trace.path) for node in source_nodes
    )
    return BlueprintValidationFinding(
        finding_id=(
            "error:output.reference_duplicate_node_id:"
            f"{_reference_finding_key(reference)}"
        ),
        severity="error",
        code="output.reference_duplicate_node_id",
        node_id=reference.consumer_node.node_id,
        client_message=(
            "A mapping expression references a module ID that appears more than"
            "once."
        ),
        internal_message=(
            f"Node {reference.consumer_node.node_id} references duplicated "
            f"source node "
            f"{reference.source_node_id!r}; duplicate source paths: "
            f"{source_paths}."
        ),
        catalog_module_id=None,
        source_path=reference.source_path,
    )


def _explicit_field_name(value: JsonObject) -> str:
    for key in FIELD_NAME_KEYS:
        field_name = value.get(key)
        if isinstance(field_name, str) and field_name.strip():
            return field_name.strip()
    return ""


def _field_path_is_child_of(field_path: str, parent_path: str) -> bool:
    field_segments = _normalized_field_path_segments(field_path)
    parent_segments = _normalized_field_path_segments(parent_path)
    return (
        len(field_segments) > len(parent_segments)
        and field_segments[: len(parent_segments)] == parent_segments
    )


def _field_path_without_numeric_indexes(field_path: str) -> str:
    return ".".join(
        segment for segment in field_path.split(".") if not segment.isdigit()
    )


def _normalized_field_path_segments(field_path: str) -> tuple[str, ...]:
    return tuple(
        _normalize_field_name(segment)
        for segment in field_path.split(".")
        if segment.strip()
    )


def _reference_finding_key(reference: OutputReference) -> str:
    path_key = ".".join(str(part) for part in reference.source_path)
    field_key = _normalize_field_name(reference.field_path) or "field"
    return (
        f"{reference.consumer_node.node_id}:{reference.source_node_id}:"
        f"{field_key}:{path_key}"
    )


def _normalize_field_name(value: str) -> str:
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )


def _join_path(prefix: str, field_name: str) -> str:
    return f"{prefix}.{field_name}" if prefix else field_name


def _has_declared_child(field_name: str, fields: set[str]) -> bool:
    return any(item.startswith(f"{field_name}.") for item in fields)


def _value_allows_dynamic_children(value: object) -> bool:
    return _is_json_object(value) and _schema_allows_dynamic_children(value)


def _schema_allows_dynamic_children(value: JsonObject) -> bool:
    raw_type = value.get("type")
    if not isinstance(raw_type, str):
        return False
    return raw_type.strip().casefold() in {
        "any",
        "array",
        "collection",
        "dict",
        "dictionary",
        "map",
        "object",
    }


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in mapping)
