# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.validator-policy
# - 001060#repo.architecture.srp.extreme-one-responsibility
# - 001063#repo.architecture.file-boundary.contract-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Route, branch, tool, and filter validation for Make AST nodes.

Boundary contract:
- Owns: route-like wrapper validation for routers, branches, tools, and filters.
- Must not: resolve catalog modules, validate schedules, or inspect mappings.
- Allows: AST route inputs and deterministic validation findings.
- Split when: router, filter, branch, or tool-flow rules diverge materially.
- Merge when: another module owns the same route-like validation rules.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

from blueprints.ast.references import collect_expression_reference_usages
from blueprints.validation.expression_templates import (
    MakeExpressionTemplate,
    MakeExpressionTemplateParseError,
    iter_make_expression_templates,
)
from blueprints.validation.findings import (
    INVALID_FILTER_EXPRESSION_CODE,
    MISSING_ROUTER_FANOUT_CODE,
    ROUTES_ON_NON_ROUTER_CODE,
    build_validation_finding,
)

if TYPE_CHECKING:
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstFilter,
        MakeAstNode,
        MakeAstRoute,
    )
    from blueprints.validation.models import BlueprintValidationFinding

FILTER_EXPRESSION_UNSUPPORTED_CODE: Final = "filter.expression_unsupported"
FILTER_LABEL_MISSING_CODE: Final = "filter.label_missing"
FILTER_LABEL_OVERLONG_CODE: Final = "filter.label_overlong"
FILTER_OPERATOR_UNSUPPORTED_CODE: Final = "filter.operator_unsupported"
FILTER_REFERENCE_NOT_UPSTREAM_CODE: Final = "filter.reference_not_upstream"
FILTER_REFERENCE_UNKNOWN_FIELD_CODE: Final = "filter.reference_unknown_field"
EVENT_TYPE_FALLBACK_MISSING_CODE: Final = "route.event_type_fallback_missing"
ROUTE_ID_DUPLICATE_CODE: Final = "route.id_duplicate"
FILTER_LABEL_MAX_LENGTH: Final = 120
FILTER_LABEL_KEYS: Final = ("name", "label")
FILTER_EXPRESSION_KEYS: Final = (
    "conditions ",
    "condition ",
    "rules ",
    "expression",
)
FILTER_NATIVE_CONDITION_KEYS: Final = (
    "conditions ",
    "condition ",
    "rules ",
    "expression",
)
FILTER_NATIVE_LEFT_KEYS: Final = ("a", "left", "lhs", "field", "expression")
FILTER_NATIVE_OPERATOR_KEYS: Final = (
    "o ",
    "operator ",
    "op ",
    "comparison ",
    "type",
)
FILTER_NATIVE_RIGHT_KEYS: Final = ("b", "right", "rhs", "operand2", "value")
OUTPUT_CONTRACT_KEYS: Final = ("interface", "outputs", "output_schema")
FIELD_NAME_KEYS: Final = ("name", "key", "id")
FIELD_CHILD_KEYS: Final = (
    "fields ",
    "items ",
    "children ",
    "properties ",
    "schema ",
    "spec",
)
FIELD_METADATA_KEYS: Final = frozenset(
    {
        "default ",
        "description ",
        "help ",
        "id ",
        "key ",
        "label ",
        "name ",
        "options ",
        "required ",
        "semantic ",
        "type",
    }
)
RUNTIME_PLACEHOLDER_KEYS: Final = (
    "runtime_placeholders ",
    "runtime_fields ",
    "placeholder_fields",
)
LOGICAL_OPERATOR_PATTERN: Final = re.compile(
    r"\s+(?:and|or)\s+", flags=re.IGNORECASE
)
FILTER_LITERAL_VALUE_PATTERN: Final = (
    r"(?:\"[^\"]*\"|'[^']*'|-?\d+(?:\.\d+)?|true|false|null)"
)
COMPARISON_CLAUSE_PATTERN: Final = re.compile(
    rf"^ref\s*(?:=|==|!=|>=|<=|>|<)\s*{FILTER_LITERAL_VALUE_PATTERN}$",
    flags=re.IGNORECASE,
)
CONTAINS_CLAUSE_PATTERN: Final = re.compile(
    rf"^contains\(ref,\s*{FILTER_LITERAL_VALUE_PATTERN}\)$",
    flags=re.IGNORECASE,
)
FILTER_COMBINATOR_TEXTS: Final = frozenset({"all", "and", "any", "or"})
SUPPORTED_NATIVE_FILTER_OPERATORS: Final = frozenset(
    {
        "contains ",
        "contains (case insensitive)",
        "does not exist ",
        "equal ",
        "equal to ",
        "equal to (case insensitive)",
        "exist ",
        "exists ",
        "gt ",
        "gte ",
        "less than ",
        "lt ",
        "lte ",
        "not equal ",
        "not equal to ",
        "not equal to (case insensitive)",
        "notexist ",
        "number:equal ",
        "number:greater ",
        "number:greaterorequal ",
        "number:less ",
        "number:lessorequal ",
        "text:contains ",
        "text:contains:ci ",
        "text:equal ",
        "text:equal:ci ",
        "text:notequal ",
        "text:notequal:ci",
    }
)
EVENT_TYPE_FILTER_TOKENS: Final = (
    "event type ",
    "event.type ",
    "event_type ",
    "eventname ",
    "eventtype",
)
FALLBACK_ROUTE_TOKENS: Final = (
    "default ",
    "else ",
    "fallback ",
    "otherwise ",
    "unknown event ",
    "unknown type",
)


class _NativeFilterCondition(NamedTuple):
    """One native Make filter condition object."""

    source_path: tuple[AstPathPart, ...]
    left_operand: str
    operator: str
    right_operand: str


def validate_routes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate route, branch, tool, and filter basics.

    Returns:
        The validated value.
    """
    findings: list[BlueprintValidationFinding] = []
    nodes_by_id = {node.node_id: node for node in nodes}
    for node in nodes:
        if node.kind == "router" and not node.routes:
            findings.append(_router_without_routes_finding(node))
        if node.kind != "router" and node.routes:
            findings.append(_routes_on_non_router_finding(node))
        if _webhook_event_type_router_missing_fallback(node, nodes=nodes):
            findings.append(_event_type_fallback_missing_finding(node))
        findings.extend(_validate_duplicate_route_ids(node))
        for route in (*node.routes, *node.branches, *node.tools):
            findings.extend(
                _validate_route(
                    route, owner=node, nodes=nodes, nodes_by_id=nodes_by_id
                )
            )
    return tuple(findings)


def _validate_duplicate_route_ids(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate route-like wrapper IDs are unique inside each owner container.

    Returns:
        The duplicate route-like wrapper ID validation findings.
    """
    findings: list[BlueprintValidationFinding] = []
    for routes in (node.routes, node.branches, node.tools):
        seen: set[str] = set()
        reported: set[str] = set()
        for route in routes:
            raw_route_id = _route_raw_id(route)
            if raw_route_id is None:
                continue
            if raw_route_id not in seen:
                seen.add(raw_route_id)
                continue
            if raw_route_id in reported:
                continue
            reported.add(raw_route_id)
            findings.append(
                build_validation_finding(
                    code=ROUTE_ID_DUPLICATE_CODE,
                    severity="error",
                    node=(
                        route.source_trace.parent_node_id,
                        (*route.source_trace.path, "id"),
                    ),
                    catalog_module_id=None,
                    messages=(
                        (
                            "A route ID appears more than once inside the same "
                            "route container."
                        ),
                        (
                            f"Node {node.node_id} has duplicated route-like "
                            f"wrapper ID "
                            f"{raw_route_id!r} in {route.container_kind}."
                        ),
                    ),
                )
            )
    return tuple(findings)


def _route_raw_id(route: MakeAstRoute) -> str | None:
    """Return a comparable raw route-like wrapper ID when explicitly present.

    Returns:
        The route-like wrapper ID, or None when no comparable raw ID is present.
    """
    value = route.raw_payload.get("id")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _validate_route(
    route: MakeAstRoute,
    *,
    owner: MakeAstNode,
    nodes: tuple[MakeAstNode, ...],
    nodes_by_id: dict[str, MakeAstNode],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate one route-like wrapper.

    Returns:
        The validated value.
    """
    findings: list[BlueprintValidationFinding] = []
    if not route.flow:
        findings.append(
            build_validation_finding(
                code="route.empty_flow",
                severity="warning",
                node=(
                    route.source_trace.parent_node_id,
                    route.source_trace.path,
                ),
                catalog_module_id=None,
                messages=(
                    "A route has no modules to run.",
                    f"Route {route.route_id} has an empty flow.",
                ),
            )
        )
    if route.filter is not None and not _has_condition_payload(
        route.filter.conditions
    ):
        findings.append(
            build_validation_finding(
                code=INVALID_FILTER_EXPRESSION_CODE,
                severity="warning",
                node=(
                    route.source_trace.parent_node_id,
                    (*route.source_trace.path, "filter"),
                ),
                catalog_module_id=None,
                messages=(
                    "A route filter has no conditions.",
                    f"Route {route.route_id} filter has no conditions.",
                ),
            )
        )
    if route.filter is not None:
        findings.extend(_validate_filter_label(route=route))
    findings.extend(
        _validate_filter_expressions(
            route=route,
            owner=owner,
            nodes=nodes,
            nodes_by_id=nodes_by_id,
        )
    )
    return tuple(findings)


def _validate_filter_expressions(
    *,
    route: MakeAstRoute,
    owner: MakeAstNode,
    nodes: tuple[MakeAstNode, ...],
    nodes_by_id: dict[str, MakeAstNode],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return expression and reference findings for one route filter."""
    if route.filter is None:
        return ()
    findings: list[BlueprintValidationFinding] = []
    upstream_ids = _route_upstream_node_ids(owner=owner, nodes=nodes)
    for raw_condition in _native_filter_conditions(route.filter):
        condition = raw_condition._replace(
            source_path=(*route.source_trace.path, *raw_condition.source_path)
        )
        findings.extend(
            _validate_native_filter_condition(
                condition=condition,
                owner=owner,
                nodes_by_id=nodes_by_id,
                upstream_ids=upstream_ids,
            )
        )
    for relative_path, expression in _filter_expression_strings(route.filter):
        if _filter_condition_combinator(expression):
            continue
        source_path = (*route.source_trace.path, *relative_path)
        try:
            templates = iter_make_expression_templates(expression)
        except MakeExpressionTemplateParseError:
            findings.append(
                _unsupported_filter_expression_finding(
                    owner=owner,
                    source_path=source_path,
                    expression=expression,
                )
            )
            continue
        if not _supports_filter_expression(expression, templates):
            findings.append(
                _unsupported_filter_expression_finding(
                    owner=owner,
                    source_path=source_path,
                    expression=expression,
                )
            )
            continue
        for source_node_id, field_path in collect_expression_reference_usages(
            expression
        ):
            if source_node_id not in upstream_ids:
                findings.append(
                    _filter_reference_not_upstream_finding(
                        owner=owner,
                        source_path=source_path,
                        source_node_id=source_node_id,
                    )
                )
                continue
            source_node = nodes_by_id.get(source_node_id)
            if source_node is not None and not _source_field_known(
                source_node, field_path
            ):
                findings.append(
                    _filter_reference_unknown_field_finding(
                        owner=owner,
                        source_path=source_path,
                        source_node=source_node,
                        field_path=field_path,
                    )
                )
    return tuple(findings)


def _validate_filter_label(
    route: MakeAstRoute,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate Make UI filter label constraints.

    Returns:
        Filter label validation findings.
    """
    if route.filter is None:
        return ()
    label_key, label = _filter_label(route.filter)
    if label is None:
        return (_filter_label_missing_finding(route),)
    if len(label) > FILTER_LABEL_MAX_LENGTH:
        return (
            _filter_label_overlong_finding(
                route=route,
                label_key=label_key,
                label_length=len(label),
            ),
        )
    return ()


def _filter_label(filter_value: MakeAstFilter) -> tuple[str, str | None]:
    for key in FILTER_LABEL_KEYS:
        value = filter_value.raw_payload.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return "name", None


def _validate_native_filter_condition(
    *,
    condition: _NativeFilterCondition,
    owner: MakeAstNode,
    nodes_by_id: dict[str, MakeAstNode],
    upstream_ids: frozenset[str],
) -> tuple[BlueprintValidationFinding, ...]:
    findings: list[BlueprintValidationFinding] = []
    if condition.operator and _normalize_filter_operator(
        condition.operator
    ) not in (SUPPORTED_NATIVE_FILTER_OPERATORS):
        findings.append(
            _unsupported_filter_operator_finding(
                owner=owner,
                source_path=condition.source_path,
                operator=condition.operator,
            )
        )
    for operand in (condition.left_operand, condition.right_operand):
        if "{{" not in operand:
            continue
        findings.extend(
            _validate_filter_operand_references(
                owner=owner,
                source_path=condition.source_path,
                expression=operand,
                nodes_by_id=nodes_by_id,
                upstream_ids=upstream_ids,
            )
        )
    return tuple(findings)


def _validate_filter_operand_references(
    *,
    owner: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    expression: str,
    nodes_by_id: dict[str, MakeAstNode],
    upstream_ids: frozenset[str],
) -> tuple[BlueprintValidationFinding, ...]:
    try:
        templates = iter_make_expression_templates(expression)
    except MakeExpressionTemplateParseError:
        return (
            _unsupported_filter_expression_finding(
                owner=owner,
                source_path=source_path,
                expression=expression,
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    for template in templates:
        for source_node_id, field_path in collect_expression_reference_usages(
            template.raw_text
        ):
            if source_node_id not in upstream_ids:
                findings.append(
                    _filter_reference_not_upstream_finding(
                        owner=owner,
                        source_path=source_path,
                        source_node_id=source_node_id,
                    )
                )
                continue
            source_node = nodes_by_id.get(source_node_id)
            if source_node is not None and not _source_field_known(
                source_node, field_path
            ):
                findings.append(
                    _filter_reference_unknown_field_finding(
                        owner=owner,
                        source_path=source_path,
                        source_node=source_node,
                        field_path=field_path,
                    )
                )
    return tuple(findings)


def _filter_expression_strings(
    filter_payload: MakeAstFilter,
) -> tuple[tuple[tuple[AstPathPart, ...], str], ...]:
    """Return string expressions from supported filter condition containers."""
    expressions: list[tuple[tuple[AstPathPart, ...], str]] = []
    for key in FILTER_EXPRESSION_KEYS:
        if key not in filter_payload.raw_payload:
            continue
        expressions.extend(
            _expression_alias_items(
                filter_payload.raw_payload[key], path=("filter", key)
            )
        )
    return tuple(expressions)


def _expression_alias_items(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[tuple[AstPathPart, ...], str], ...]:
    if isinstance(value, str):
        return ((path, value),)
    if _is_json_object(value):
        if _is_native_filter_condition_object(value):
            return ()
        return tuple(
            result
            for key in ("expression", "condition")
            if key in value
            for result in _expression_alias_items(value[key], path=(*path, key))
        )
    if isinstance(value, list):
        return tuple(
            result
            for index, child in enumerate(cast("list[object]", value))
            for result in _expression_alias_items(child, path=(*path, index))
        )
    return ()


def _native_filter_conditions(
    filter_payload: MakeAstFilter,
) -> tuple[_NativeFilterCondition, ...]:
    conditions: list[_NativeFilterCondition] = []
    for key in FILTER_NATIVE_CONDITION_KEYS:
        if key in filter_payload.raw_payload:
            conditions.extend(
                _native_filter_conditions_from_value(
                    filter_payload.raw_payload[key],
                    path=("filter", key),
                )
            )
    return tuple(conditions)


def _native_filter_conditions_from_value(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[_NativeFilterCondition, ...]:
    if _is_json_object(value):
        if _is_native_filter_condition_object(value):
            return (_native_filter_condition_from_object(value, path=path),)
        return tuple(
            condition
            for key, child in value.items()
            for condition in _native_filter_conditions_from_value(
                child, path=(*path, key)
            )
        )
    if isinstance(value, list):
        return tuple(
            condition
            for index, child in enumerate(cast("list[object]", value))
            for condition in _native_filter_conditions_from_value(
                child, path=(*path, index)
            )
        )
    return ()


def _is_native_filter_condition_object(value: JsonObject) -> bool:
    return any(key in value for key in FILTER_NATIVE_OPERATOR_KEYS) and any(
        key in value for key in FILTER_NATIVE_LEFT_KEYS
    )


def _native_filter_condition_from_object(
    value: JsonObject,
    *,
    path: tuple[AstPathPart, ...],
) -> _NativeFilterCondition:
    return _NativeFilterCondition(
        source_path=path,
        left_operand=_first_text(value, FILTER_NATIVE_LEFT_KEYS),
        operator=_first_text(value, FILTER_NATIVE_OPERATOR_KEYS),
        right_operand=_first_text(value, FILTER_NATIVE_RIGHT_KEYS),
    )


def _first_text(value: JsonObject, keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, int | float) and not isinstance(item, bool):
            return str(item)
    return ""


def _normalize_filter_operator(operator: str) -> str:
    return " ".join(operator.casefold().replace("_", " ").split())


def _filter_condition_combinator(value: str) -> bool:
    return value.strip().casefold() in FILTER_COMBINATOR_TEXTS


def _supports_filter_expression(
    expression: str,
    templates: tuple[MakeExpressionTemplate, ...],
) -> bool:
    """Return if a filter expression is inside the first supported subset."""
    if not templates:
        return False
    normalized = _normalize_filter_expression(expression, templates)
    clauses = tuple(
        clause.strip()
        for clause in LOGICAL_OPERATOR_PATTERN.split(normalized)
        if clause.strip()
    )
    return bool(clauses) and all(
        _supported_filter_clause(clause) for clause in clauses
    )


def _normalize_filter_expression(
    expression: str,
    templates: tuple[MakeExpressionTemplate, ...],
) -> str:
    normalized = expression.strip()
    for template in templates:
        normalized = normalized.replace(template.raw_text, "REF")
    return normalized


def _supported_filter_clause(clause: str) -> bool:
    normalized = " ".join(clause.casefold().split())
    if normalized in {"empty(ref)", "not empty(ref)"}:
        return True
    if CONTAINS_CLAUSE_PATTERN.fullmatch(normalized) is not None:
        return True
    return COMPARISON_CLAUSE_PATTERN.fullmatch(normalized) is not None


def _route_upstream_node_ids(
    *,
    owner: MakeAstNode,
    nodes: tuple[MakeAstNode, ...],
) -> frozenset[str]:
    return frozenset(
        node.node_id
        for node in nodes
        if _node_is_upstream_sibling(node=node, owner=owner)
    )


def _node_is_upstream_sibling(*, node: MakeAstNode, owner: MakeAstNode) -> bool:
    if node.source_trace.parent_node_id != owner.source_trace.parent_node_id:
        return False
    if node.source_trace.container_kind != owner.source_trace.container_kind:
        return False
    node_path = node.source_trace.path
    owner_path = owner.source_trace.path
    if len(node_path) != len(owner_path) or node_path[:-1] != owner_path[:-1]:
        return False
    node_index = node_path[-1]
    owner_index = owner_path[-1]
    return (
        isinstance(node_index, int)
        and isinstance(owner_index, int)
        and node_index < owner_index
    )


def _webhook_event_type_router_missing_fallback(
    owner: MakeAstNode,
    *,
    nodes: tuple[MakeAstNode, ...],
) -> bool:
    """Return if a webhook-fed event-type router lacks fallback evidence."""
    if owner.kind != "router" or not owner.routes:
        return False
    upstream_ids = _route_upstream_node_ids(owner=owner, nodes=nodes)
    if not any(
        node.node_id in upstream_ids and node.kind == "webhook"
        for node in nodes
    ):
        return False
    if not any(
        _route_filter_mentions_event_type(route) for route in owner.routes
    ):
        return False
    return not any(_route_declares_fallback(route) for route in owner.routes)


def _route_filter_mentions_event_type(route: MakeAstRoute) -> bool:
    """Return whether one route filter appears to branch on event type."""
    if route.filter is None:
        return False
    text_blob = _json_text_blob(route.filter.raw_payload)
    return any(token in text_blob for token in EVENT_TYPE_FILTER_TOKENS)


def _route_declares_fallback(route: MakeAstRoute) -> bool:
    """Return whether one route handles otherwise unmatched event types."""
    if route.filter is None:
        return True
    text_blob = _json_text_blob(route.raw_payload)
    return any(token in text_blob for token in FALLBACK_ROUTE_TOKENS)


def _json_text_blob(value: object) -> str:
    """Return the computed result for the caller."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, (int, float)):
        return str(value).casefold()
    if _is_json_object(value):
        return " ".join(
            f"{key} {_json_text_blob(child)}" for key, child in value.items()
        ).casefold()
    if isinstance(value, list):
        return " ".join(
            _json_text_blob(item) for item in cast("list[object]", value)
        )
    return ""


def _source_field_known(source_node: MakeAstNode, field_path: str) -> bool:
    if not field_path:
        return True
    fields = _declared_output_fields(source_node)
    if not fields:
        return True
    normalized = _normalize_field_path(field_path)
    if normalized in fields:
        return True
    if _field_is_child_of_dynamic_parent(
        normalized,
        _declared_dynamic_output_parents(source_node),
    ):
        return True
    if _runtime_placeholder_field(source_node, field_path):
        return True
    index_free = _normalize_field_path(
        ".".join(
            segment
            for segment in field_path.split(".")
            if not segment.isdigit()
        )
    )
    return index_free in fields


def _declared_output_fields(node: MakeAstNode) -> frozenset[str]:
    raw_contracts = [
        node.raw_payload[key]
        for key in OUTPUT_CONTRACT_KEYS
        if key in node.raw_payload
    ]
    metadata = node.raw_payload.get("metadata")
    if _is_json_object(metadata):
        raw_contracts.extend(
            metadata[key] for key in OUTPUT_CONTRACT_KEYS if key in metadata
        )
    return frozenset(
        _normalize_field_path(field)
        for contract in raw_contracts
        for field in _field_names(contract, prefix="")
        if field
    )


def _declared_dynamic_output_parents(node: MakeAstNode) -> frozenset[str]:
    raw_contracts = [
        node.raw_payload[key]
        for key in OUTPUT_CONTRACT_KEYS
        if key in node.raw_payload
    ]
    metadata = node.raw_payload.get("metadata")
    if _is_json_object(metadata):
        raw_contracts.extend(
            metadata[key] for key in OUTPUT_CONTRACT_KEYS if key in metadata
        )
    return frozenset(
        _normalize_field_path(parent)
        for contract in raw_contracts
        for parent in _dynamic_parent_field_names(contract, prefix="")
        if parent
    )


def _field_names(value: object, *, prefix: str) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(
            field
            for item in cast("list[object]", value)
            for field in _field_names(item, prefix=prefix)
        )
    if not _is_json_object(value):
        return ()
    explicit_name = _explicit_field_name(value)
    if explicit_name:
        field_name = _join_path(prefix, explicit_name)
        return (field_name, *_child_field_names(value, prefix=field_name))
    child_fields = _child_field_names(value, prefix=prefix)
    if child_fields:
        return child_fields
    return tuple(
        _join_path(prefix, key)
        for key in value
        if key not in FIELD_METADATA_KEYS
    )


def _child_field_names(value: JsonObject, *, prefix: str) -> tuple[str, ...]:
    return tuple(
        field
        for key in FIELD_CHILD_KEYS
        for field in _field_names(value.get(key), prefix=prefix)
    )


def _dynamic_parent_field_names(
    value: object, *, prefix: str
) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(
            parent
            for item in cast("list[object]", value)
            for parent in _dynamic_parent_field_names(item, prefix=prefix)
        )
    if not _is_json_object(value):
        return ()
    explicit_name = _explicit_field_name(value)
    if explicit_name:
        field_name = _join_path(prefix, explicit_name)
        child_fields = _child_field_names(value, prefix=field_name)
        dynamic_children = _child_dynamic_parent_field_names(
            value, prefix=field_name
        )
        if _schema_allows_dynamic_children(value) and not _has_declared_child(
            field_name,
            child_fields,
        ):
            return (field_name, *dynamic_children)
        return dynamic_children
    child_fields = _child_field_names(value, prefix=prefix)
    child_dynamic = _child_dynamic_parent_field_names(value, prefix=prefix)
    if child_fields:
        return child_dynamic
    return (
        *child_dynamic,
        *_mapping_dynamic_parent_field_names(value, prefix=prefix),
    )


def _child_dynamic_parent_field_names(
    value: JsonObject, *, prefix: str
) -> tuple[str, ...]:
    return tuple(
        field
        for key in FIELD_CHILD_KEYS
        for field in _dynamic_parent_field_names(value.get(key), prefix=prefix)
    )


def _mapping_dynamic_parent_field_names(
    value: JsonObject, *, prefix: str
) -> tuple[str, ...]:
    parents: list[str] = []
    for raw_key, child in value.items():
        if raw_key in FIELD_METADATA_KEYS:
            continue
        field_name = _join_path(prefix, raw_key)
        child_fields = _field_names(child, prefix=field_name)
        parents.extend(_dynamic_parent_field_names(child, prefix=field_name))
        if _value_allows_dynamic_children(child) and not _has_declared_child(
            field_name,
            child_fields,
        ):
            parents.append(field_name)
    return tuple(parents)


def _explicit_field_name(value: JsonObject) -> str:
    for key in FIELD_NAME_KEYS:
        raw_value = value.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return ""


def _runtime_placeholder_field(node: MakeAstNode, field_path: str) -> bool:
    normalized = _normalize_field_path(field_path)
    for container in (node.raw_payload, node.raw_payload.get("metadata")):
        if not _is_json_object(container):
            continue
        for key in RUNTIME_PLACEHOLDER_KEYS:
            if normalized in _placeholder_field_names(container.get(key)):
                return True
    return False


def _placeholder_field_names(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset({_normalize_field_path(value)})
    if isinstance(value, list):
        return frozenset(
            _normalize_field_path(item)
            for item in cast("list[object]", value)
            if isinstance(item, str)
        )
    if _is_json_object(value):
        return frozenset(_normalize_field_path(key) for key in value)
    return frozenset()


def _field_is_child_of_dynamic_parent(
    field_path: str, parents: frozenset[str]
) -> bool:
    return any(field_path.startswith(f"{parent}.") for parent in parents)


def _schema_allows_dynamic_children(value: JsonObject) -> bool:
    raw_type = value.get("type")
    if not isinstance(raw_type, str):
        return False
    return raw_type.strip().casefold() in {
        "any ",
        "array ",
        "collection ",
        "dict ",
        "dictionary ",
        "map ",
        "object",
    }


def _value_allows_dynamic_children(value: object) -> bool:
    return _is_json_object(value) and _schema_allows_dynamic_children(value)


def _has_declared_child(field_name: str, fields: tuple[str, ...]) -> bool:
    return any(item.startswith(f"{field_name}.") for item in fields)


def _normalize_field_path(value: str) -> str:
    return ".".join(
        "".join(
            character for character in segment.casefold() if character.isalnum()
        )
        for segment in value.split(".")
        if segment.strip()
    )


def _join_path(prefix: str, field_name: str) -> str:
    return f"{prefix}.{field_name}" if prefix else field_name


def _filter_label_missing_finding(
    route: MakeAstRoute,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_LABEL_MISSING_CODE,
        severity="warning",
        node=(
            route.source_trace.parent_node_id,
            (*route.source_trace.path, "filter"),
        ),
        catalog_module_id=None,
        messages=(
            "A route filter is missing a Make UI label.",
            f"Route {route.route_id} filter needs a label before handoff.",
        ),
    )


def _filter_label_overlong_finding(
    *,
    route: MakeAstRoute,
    label_key: str,
    label_length: int,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_LABEL_OVERLONG_CODE,
        severity="warning",
        node=(
            route.source_trace.parent_node_id,
            (*route.source_trace.path, "filter", label_key),
        ),
        catalog_module_id=None,
        messages=(
            "A route filter label is longer than Make's UI limit.",
            (
                f"Route {route.route_id} filter label is {label_length} "
                f"characters; "
                f"Make's filter dialog caps labels at "
                f"{FILTER_LABEL_MAX_LENGTH}."
            ),
        ),
    )


def _unsupported_filter_expression_finding(
    *,
    owner: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    expression: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_EXPRESSION_UNSUPPORTED_CODE,
        severity="error",
        node=(owner.node_id, source_path),
        catalog_module_id=None,
        messages=(
            "A route filter uses unsupported Make expression syntax.",
            (
                f"Route filter on node {owner.node_id} is outside the "
                f"supported subset; "
                f"raw expression is redacted and has {len(expression)} "
                f"characters."
            ),
        ),
    )


def _unsupported_filter_operator_finding(
    *,
    owner: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    operator: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_OPERATOR_UNSUPPORTED_CODE,
        severity="error",
        node=(owner.node_id, source_path),
        catalog_module_id=None,
        messages=(
            "A route filter uses an unsupported Make operator.",
            (
                f"Route filter on node {owner.node_id} uses operator "
                f"{operator!r}, "
                "which is outside the documented basic, text, or numeric "
                "families."
            ),
        ),
    )


def _filter_reference_not_upstream_finding(
    *,
    owner: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    source_node_id: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_REFERENCE_NOT_UPSTREAM_CODE,
        severity="error",
        node=(owner.node_id, source_path),
        catalog_module_id=None,
        messages=(
            "A route filter references a module that is not upstream.",
            (
                f"Route filter on node {owner.node_id} references node "
                f"{source_node_id!r}, "
                "which is not upstream of the filter owner."
            ),
        ),
    )


def _filter_reference_unknown_field_finding(
    *,
    owner: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    source_node: MakeAstNode,
    field_path: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=FILTER_REFERENCE_UNKNOWN_FIELD_CODE,
        severity="error",
        node=(owner.node_id, source_path),
        catalog_module_id=None,
        messages=(
            (
                "A route filter references a field that is not declared by the "
                "upstream module."
            ),
            (
                f"Route filter on node {owner.node_id} references field "
                f"{field_path!r} "
                f"from node {source_node.node_id!r} without local output "
                f"evidence."
            ),
        ),
    )


def _has_condition_payload(value: object) -> bool:
    """Return if a normalized filter condition carries executable content."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(
            _has_condition_payload(item)
            for item in cast("dict[object, object]", value).values()
        )
    if isinstance(value, list):
        return any(
            _has_condition_payload(item) for item in cast("list[object]", value)
        )
    return False


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _router_without_routes_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return a blocking router structure finding."""
    return build_validation_finding(
        code=MISSING_ROUTER_FANOUT_CODE,
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A router node must contain at least one route.",
            f"Router node {node.node_id} has no route flows.",
        ),
    )


def _event_type_fallback_missing_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return the computed result for the caller."""
    return build_validation_finding(
        code=EVENT_TYPE_FALLBACK_MISSING_CODE,
        severity="warning",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A webhook event-type router should declare fallback handling.",
            (
                f"Router node {node.node_id} has event-type filters without "
                f"fallback evidence."
            ),
        ),
    )


def _routes_on_non_router_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return a blocking finding for route containers outside routers."""
    return build_validation_finding(
        code=ROUTES_ON_NON_ROUTER_CODE,
        severity="error",
        node=(node.node_id, (*node.source_trace.path, "routes")),
        catalog_module_id=None,
        messages=(
            "A non-router module contains route branches.",
            f"Node {node.node_id} is {node.kind!r} but owns route containers.",
        ),
    )
