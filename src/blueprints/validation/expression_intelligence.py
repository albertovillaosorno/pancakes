# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Conservative Make expression and mapping-risk analysis.

Boundary contract:
- Owns: static mapping-expression and mapping-pattern risk analysis.
- Must not: validate catalog modules, render blueprints, or repair expressions.
- Allows: promoted expression rules, typed risks, and client-safe repair hints.
- Split when: a mapping-risk family needs independent rule ownership.
- Merge when: another analyzer reports the same mapping risks identically.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

from languages.make.expression_palette import (
    PALETTE_OBSERVED_ARITY_STATUS,
    PALETTE_OBSERVED_SOURCE,
    make_expression_function_facts,
    make_expression_function_family_ids,
)

from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.expression_paths import (
    path_allows_mapping_expression,
)
from blueprints.validation.expression_templates import (
    EXPRESSION_END,
    EXPRESSION_START,
    MakeExpressionTemplateParseError,
    iter_make_expression_templates,
)

if TYPE_CHECKING:
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import BlueprintFindingSeverity

PROMOTED_RULE_SOURCE: Final = "promoted:adr-tests-runtime"
FUNCTION_CALL_PATTERN: Final = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)
CHILD_FLOW_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools")
)
DIRECT_ERROR_CHILD_KEYS: Final[frozenset[str]] = frozenset(
    ("onerror", "on_error")
)


class MakeExpressionFunctionRule(NamedTuple):
    """Promoted Make expression function rule."""

    name: str
    category: str
    min_args: int
    max_args: int | None
    promoted_source: str


class MakeExpressionFunctionPosture(NamedTuple):
    """Known posture for one Make expression function."""

    name: str
    family_ids: tuple[str, ...]
    arity_status: str
    evidence_source: str
    min_args: int | None = None
    max_args: int | None = None


class MappingRepairSuggestion(NamedTuple):
    """Client-safe repair suggestion for a mapping risk."""

    suggestion_id: str
    client_message: str
    internal_detail: str


class MappingRisk(NamedTuple):
    """One typed mapping risk attached to an AST node."""

    risk_id: str
    severity: BlueprintFindingSeverity
    code: str
    node_id: str
    source_path: tuple[AstPathPart, ...]
    expression: str
    client_message: str
    internal_message: str
    repair_suggestion: MappingRepairSuggestion
    evidence_source: str


FUNCTION_RULES: Final[tuple[MakeExpressionFunctionRule, ...]] = (
    MakeExpressionFunctionRule("trim", "text", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("get", "collection", 2, 2, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule(
        "map", "collection", 2, None, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule("match", "text", 2, 2, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("regex", "text", 2, 3, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("replace", "text", 3, 3, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("split", "text", 2, 2, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("join", "array", 2, 2, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("lower", "text", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("upper", "text", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("length", "array", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule(
        "toNumber", "numeric", 1, 1, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule(
        "parseNumber", "numeric", 1, 1, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule("round", "numeric", 1, 2, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("ceil", "numeric", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("floor", "numeric", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule("sum", "numeric", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule(
        "average", "numeric", 1, 1, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule(
        "formatDate", "datetime", 2, 3, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule(
        "parseDate", "datetime", 2, 3, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule(
        "addDays", "datetime", 2, 2, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule(
        "parseJSON", "parsing", 1, 1, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule("if", "control", 3, 3, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule(
        "ifempty", "control", 2, 2, PROMOTED_RULE_SOURCE
    ),
    MakeExpressionFunctionRule("empty", "control", 1, 1, PROMOTED_RULE_SOURCE),
    MakeExpressionFunctionRule(
        "contains", "control", 2, 2, PROMOTED_RULE_SOURCE
    ),
)
FUNCTION_RULES_BY_NAME: Final[dict[str, MakeExpressionFunctionRule]] = {
    rule.name.casefold(): rule for rule in FUNCTION_RULES
}


def make_expression_function_posture(
    function_name: str,
) -> MakeExpressionFunctionPosture:
    """Return the known Make expression function posture without inferring.

    hidden.

    arity.
    """
    normalized = function_name.casefold()
    rule = FUNCTION_RULES_BY_NAME.get(normalized)
    if rule is not None:
        return MakeExpressionFunctionPosture(
            name=rule.name,
            family_ids=(rule.category,),
            arity_status="promoted_arity",
            evidence_source=rule.promoted_source,
            min_args=rule.min_args,
            max_args=rule.max_args,
        )
    family_ids = make_expression_function_family_ids(function_name)
    if family_ids:
        return MakeExpressionFunctionPosture(
            name=function_name,
            family_ids=family_ids,
            arity_status=PALETTE_OBSERVED_ARITY_STATUS,
            evidence_source=PALETTE_OBSERVED_SOURCE,
        )
    return MakeExpressionFunctionPosture(
        name=function_name,
        family_ids=(),
        arity_status="unknown",
        evidence_source="none",
    )


def analyze_mapping_risks(root: MakeAstRoot) -> tuple[MappingRisk, ...]:
    """Return typed mapping risks for expressions attached to AST nodes."""
    risks: list[MappingRisk] = []
    for node in iter_ast_nodes(root):
        risks.extend(_node_expression_risks(node))
        risks.extend(_node_pattern_risks(node))
    return tuple(risks)


def _node_expression_risks(node: MakeAstNode) -> tuple[MappingRisk, ...]:
    """Return expression risks for one AST node raw payload."""
    risks: list[MappingRisk] = []
    for path, text in _iter_json_strings(node.raw_payload):
        if not path_allows_mapping_expression(path):
            continue
        if EXPRESSION_START not in text and EXPRESSION_END not in text:
            continue
        risks.extend(_analyze_expression_text(node=node, path=path, text=text))
    return tuple(risks)


def _analyze_expression_text(
    *,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    text: str,
) -> tuple[MappingRisk, ...]:
    """Return risks for one string containing Make expression delimiters."""
    try:
        templates = iter_make_expression_templates(text)
    except MakeExpressionTemplateParseError:
        return _unbalanced_expression_risk(node=node, path=path, text=text)
    risks: list[MappingRisk] = []
    for template in templates:
        body = template.body.strip()
        if not body:
            risks.append(
                _risk(
                    location=(node, path),
                    expression=template.raw_text,
                    code="mapping.expression_empty",
                    severity="error",
                    messages=(
                        "A mapping expression is empty.",
                        "Map a source field or remove the empty expression.",
                    ),
                )
            )
            continue
        risks.extend(
            _function_call_risks(node=node, path=path, expression=body)
        )
        risks.extend(_pagination_risks(node=node, path=path, expression=body))
    return tuple(risks)


def _unbalanced_expression_risk(
    *,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    text: str,
) -> tuple[MappingRisk, ...]:
    """Return one risk for expression text with unmatched delimiters."""
    return (
        _risk(
            location=(node, path),
            expression=text,
            code="mapping.expression_unbalanced",
            severity="error",
            messages=(
                "A mapping expression has unbalanced delimiters.",
                "Close every Make expression with matching braces.",
            ),
        ),
    )


def _function_call_risks(
    *,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    expression: str,
) -> tuple[MappingRisk, ...]:
    """Return function-call risks for one expression body."""
    risks: list[MappingRisk] = []
    masked_expression = _mask_quoted_text(expression)
    for match in FUNCTION_CALL_PATTERN.finditer(masked_expression):
        function_name = match.group("name")
        rule = FUNCTION_RULES_BY_NAME.get(function_name.casefold())
        call_arguments = _call_arguments(expression, match.end() - 1)
        if rule is None:
            if make_expression_function_facts(function_name):
                continue
            risks.append(
                _unknown_function_risk(node, path, expression, function_name)
            )
            continue
        arg_count = _argument_count(call_arguments)
        if arg_count < rule.min_args:
            risks.append(
                _argument_count_risk(node, path, expression, rule, arg_count)
            )
        if rule.max_args is not None and arg_count > rule.max_args:
            risks.append(
                _argument_count_risk(node, path, expression, rule, arg_count)
            )
    return tuple(risks)


def _pagination_risks(
    *,
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    expression: str,
) -> tuple[MappingRisk, ...]:
    """Return conservative pagination-expression risks."""
    lowered = _mask_quoted_text(expression).casefold()
    if "page" not in lowered or "limit" in lowered or "total" in lowered:
        return ()
    return (
        _risk(
            location=(node, path),
            expression=expression,
            code="mapping.pagination_without_limit",
            severity="optimization",
            messages=(
                "A pagination mapping may need a limit or stop condition.",
                (
                    "Add a limit, total count, or stop condition to pagination "
                    "mappings."
                ),
            ),
        ),
    )


def _node_pattern_risks(node: MakeAstNode) -> tuple[MappingRisk, ...]:
    """Return iterator and aggregator mapping-pattern risks."""
    if node.kind == "iterator" and not _contains_field_name(
        node.raw_payload, "array"
    ):
        return (
            _risk(
                location=(node, node.source_trace.path),
                expression=node.module_token,
                code="mapping.iterator_source_missing",
                severity="warning",
                messages=(
                    "An iterator should declare the array it iterates over.",
                    (
                        "Map the iterator array source before rendering an "
                        "importable flow."
                    ),
                ),
            ),
        )
    if node.kind == "aggregator" and not _contains_any_field_name(
        node.raw_payload,
        ("target", "array"),
    ):
        return (
            _risk(
                location=(node, node.source_trace.path),
                expression=node.module_token,
                code="mapping.aggregator_target_missing",
                severity="warning",
                messages=(
                    "An aggregator should declare the collection it builds.",
                    (
                        "Map the aggregator target collection before "
                        "relying on its "
                        "output."
                    ),
                ),
            ),
        )
    return ()


def _unknown_function_risk(
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    expression: str,
    function_name: str,
) -> MappingRisk:
    """Return a risk for an unpromoted or unknown function."""
    return _risk(
        location=(node, path),
        expression=expression,
        code="mapping.function_unknown",
        severity="warning",
        messages=(
            "A mapping expression uses an unknown or unpromoted function.",
            f"Verify `{function_name}` against Make docs before using it.",
        ),
    )


def _argument_count_risk(
    node: MakeAstNode,
    path: tuple[AstPathPart, ...],
    expression: str,
    rule: MakeExpressionFunctionRule,
    arg_count: int,
) -> MappingRisk:
    """Return a risk for a function call with invalid arity."""
    expected = (
        f"{rule.min_args}+"
        if rule.max_args is None
        else f"{rule.min_args}-{rule.max_args}"
    )
    return _risk(
        location=(node, path),
        expression=expression,
        code="mapping.function_argument_count",
        severity="error",
        messages=(
            "A mapping function has the wrong number of arguments.",
            (
                f"Use {expected} argument(s) for `{rule.name}`; detected "
                f"{arg_count}."
            ),
        ),
    )


def _risk(
    *,
    location: tuple[MakeAstNode, tuple[AstPathPart, ...]],
    expression: str,
    code: str,
    severity: BlueprintFindingSeverity,
    messages: tuple[str, str],
) -> MappingRisk:
    """Build a typed mapping risk.

    Returns:
        The constructed value.
    """
    node, path = location
    client_message, repair_message = messages
    source_key = ".".join(str(part) for part in path) or "node"
    internal_detail = (
        f"Node {node.node_id} path {source_key} has {code} evidence."
    )
    suggestion = MappingRepairSuggestion(
        suggestion_id=f"repair:{node.node_id}:{code}:{source_key}",
        client_message=repair_message,
        internal_detail=internal_detail,
    )
    return MappingRisk(
        risk_id=f"risk:{node.node_id}:{code}:{source_key}",
        severity=severity,
        code=code,
        node_id=node.node_id,
        source_path=path,
        expression=expression,
        client_message=client_message,
        internal_message=internal_detail,
        repair_suggestion=suggestion,
        evidence_source=PROMOTED_RULE_SOURCE,
    )


def _call_arguments(expression: str, open_paren_index: int) -> str:
    """Return the argument source inside one function call."""
    depth = 0
    start_index = open_paren_index + 1
    quote: str | None = None
    escaped = False
    for index in range(open_paren_index, len(expression)):
        character = expression[index]
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character == "(":
            depth += 1
            continue
        if character != ")":
            continue
        depth -= 1
        if depth == 0:
            return expression[start_index:index]
    return expression[start_index:]


def _mask_quoted_text(expression: str) -> str:
    """Replace quoted literal content with spaces while preserving indexes.

    Returns:
        The result produced by replace quoted literal content with spaces while
        preserving indexes.
    """
    characters = list(expression)
    quote: str | None = None
    escaped = False
    for index, character in enumerate(characters):
        if escaped:
            if quote is not None:
                characters[index] = " "
            escaped = False
            continue
        if character == "\\":
            if quote is not None:
                characters[index] = " "
            escaped = True
            continue
        if quote is None and character in {"'", '"'}:
            quote = character
            characters[index] = " "
            continue
        if quote is not None:
            characters[index] = " "
            if character == quote:
                quote = None
    return "".join(characters)


def _argument_count(argument_text: str) -> int:
    """Return a conservative top-level function argument count."""
    stripped = argument_text.strip()
    if not stripped:
        return 0
    masked = _mask_quoted_text(stripped)
    depth = 0
    count = 1
    for character in masked:
        if character in {"(", "[", "{"}:
            depth += 1
        elif character in {")", "]", "}"}:
            depth = max(depth - 1, 0)
        elif character in {",", ";"} and depth == 0:
            count += 1
    return count


def _iter_json_strings(
    value: object,
    path: tuple[AstPathPart, ...] = (),
) -> tuple[tuple[tuple[AstPathPart, ...], str], ...]:
    """Return all string leaves in a JSON-like value."""
    if isinstance(value, str):
        return ((path, value),)
    if _is_json_object(value):
        return tuple(
            result
            for key, child in value.items()
            for result in _iter_json_strings(child, (*path, str(key)))
        )
    if _is_json_array(value):
        return tuple(
            result
            for index, child in enumerate(value)
            for result in _iter_json_strings(child, (*path, index))
        )
    return ()


def _contains_field_name(value: object, field_name: str) -> bool:
    """Return whether a JSON-like value contains one field name."""
    return _contains_field_name_at_path(value, field_name, path=())


def _contains_field_name_at_path(
    value: object,
    field_name: str,
    *,
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return if JSON-like data contains one field name outside child nodes."""
    if _descends_into_child_node(path):
        return False
    if _is_json_object(value):
        return any(
            (
                str(key).casefold() == field_name.casefold()
                and _has_mapping_evidence_value(child)
            )
            or _contains_field_name_at_path(
                child, field_name, path=(*path, str(key))
            )
            for key, child in value.items()
        )
    if _is_json_array(value):
        return any(
            _contains_field_name_at_path(item, field_name, path=(*path, index))
            for index, item in enumerate(value)
        )
    return False


def _contains_any_field_name(
    value: object, field_names: tuple[str, ...]
) -> bool:
    """Return whether a JSON-like value contains any field name."""
    return any(
        _contains_field_name(value, field_name) for field_name in field_names
    )


def _has_mapping_evidence_value(value: object) -> bool:
    """Return whether a mapping-pattern field carries usable evidence."""
    if isinstance(value, str):
        return bool(value.strip())
    if _is_json_object(value):
        return any(
            _has_mapping_evidence_value(child) for child in value.values()
        )
    if _is_json_array(value):
        return any(_has_mapping_evidence_value(item) for item in value)
    if isinstance(value, bool):
        return False
    return bool(value)


def _descends_into_child_node(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether a node-local scan path enters a nested child node."""
    string_parts = tuple(part for part in path if isinstance(part, str))
    if any(part in DIRECT_ERROR_CHILD_KEYS for part in string_parts):
        return True
    return any(
        _has_flow_after_child_container(string_parts, child_key)
        for child_key in CHILD_FLOW_CONTAINER_KEYS
    )


def _has_flow_after_child_container(
    path: tuple[str, ...], child_key: str
) -> bool:
    """Return whether a route-like container path enters a child flow node."""
    if child_key not in path:
        return False
    child_index = path.index(child_key)
    return "flow" in path[child_index + 1 :]


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _is_json_array(value: object) -> TypeGuard[list[object]]:
    """Return whether a value is a JSON-like array."""
    return isinstance(value, list)
