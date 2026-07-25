# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.optimizer-hints
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Build deterministic optimization advice from Make AST and knowledge hints.

Boundary contract:
- Owns: non-mutating blueprint optimization advice derived from promoted hints.
- Must not: validate catalog truth, rewrite ASTs, render blueprints, or read
courses.
- Allows: scanning AST nodes and knowledge-store optimizer hints for local
advice.
- Split when: advice becomes a mutating optimizer or planner with state.
- Merge when: another module emits the same advice records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast.module_roles import (
    module_looks_like_webhook_response,
    module_token_semantic_key,
)
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.optimization.execution_paths import iter_optimization_paths

if TYPE_CHECKING:
    from catalog.knowledge import KnowledgeOptimizerHint, KnowledgeStoreQuery

    from blueprints.ast.models import MakeAstNode, MakeAstRoot

WEBHOOK_RESPONSE_LATENCY_THRESHOLD: Final[int] = 2
NESTED_FUNCTION_CALL_THRESHOLD: Final[int] = 2
HIGH_LATENCY_MODULE_TOKENS: Final[tuple[str, ...]] = (
    "agent ",
    "api ",
    "ai-provider ",
    "delay ",
    "graphql ",
    "http ",
    "llm ",
    "makerequest ",
    "openai ",
    "repeater ",
    "sleep",
)
NODE_CHILD_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    (
        "routes ",
        "branches ",
        "tools ",
        "onerror ",
        "on_error",
    )
)


class BlueprintOptimizationAdvice(NamedTuple):
    """One deterministic optimization advisory item for a Make AST node."""

    advice_id: str
    hint_code: str
    severity: str
    node_id: str
    client_message: str
    internal_message: str
    adr_anchor: str


def build_blueprint_optimization_advice(
    *,
    root: MakeAstRoot,
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Build deterministic optimization advice from promoted knowledge hints.

    Returns:
        The optimization advice for the supplied AST.
    """
    nodes = iter_ast_nodes(root)
    advice: list[BlueprintOptimizationAdvice] = []
    for hint in knowledge.optimizer_hints:
        if hint.hint_code == "optimization.operation_volume_review":
            advice.extend(_operation_volume_advice(nodes=nodes, hint=hint))
        elif hint.hint_code == "optimization.pagination_required":
            advice.extend(_pagination_advice(nodes=nodes, hint=hint))
        elif hint.hint_code == "optimization.webhook_queue_review":
            advice.extend(_webhook_queue_advice(nodes=nodes, hint=hint))
        elif hint.hint_code == "optimization.webhook_response_timeout_risk":
            advice.extend(
                _webhook_response_timeout_advice(root=root, hint=hint)
            )
        elif hint.hint_code == "optimization.ai_model_size_review":
            advice.extend(_ai_model_size_advice(nodes=nodes, hint=hint))
        elif hint.hint_code == "optimization.ai_output_human_review":
            advice.extend(
                _ai_output_human_review_advice(nodes=nodes, hint=hint)
            )
        elif hint.hint_code == "optimization.function_nesting_compaction":
            advice.extend(_function_nesting_advice(nodes=nodes, hint=hint))
        elif hint.hint_code == "optimization.pagination_stop_condition":
            advice.extend(
                _pagination_stop_condition_advice(nodes=nodes, hint=hint)
            )
    return tuple(advice)


def _operation_volume_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return operation-volume advice for iterator-like nodes."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Review this module for operation and bundle volume."
            ),
        )
        for node in nodes
        if node.kind in {"iterator", "aggregator"}
        or _token_has_any(node, ("search", "list", "watch"))
    )


def _pagination_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return pagination advice for list-style API retrieval."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Declare pagination behavior when retrieving all records."
            ),
        )
        for node in nodes
        if _token_has_any(node, ("list", "search", "request"))
        and _node_payload_requests_all_without_pagination(node)
    )


def _webhook_queue_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return webhook queue advice for webhook nodes with queue-related.

    payloads.
    """
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Review webhook queue, retry, and response behavior."
            ),
        )
        for node in nodes
        if _node_looks_like_webhook(node) and _node_mentions_queue(node)
    )


def _webhook_response_timeout_advice(
    *,
    root: MakeAstRoot,
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return advice when slow work sits before a custom webhook response."""
    advice: list[BlueprintOptimizationAdvice] = []
    seen_response_ids: set[str] = set()
    for path in iter_optimization_paths(root):
        for trigger_index, trigger_node in enumerate(path):
            if not _node_looks_like_webhook_trigger(trigger_node):
                continue
            response_index = _first_webhook_response_index(
                path, start=trigger_index + 1
            )
            if response_index is None:
                continue
            response_node = path[response_index]
            if response_node.node_id in seen_response_ids:
                continue
            latency_risks = tuple(
                node
                for node in path[trigger_index + 1 : response_index]
                if _node_has_latency_risk(node)
            )
            if len(latency_risks) < WEBHOOK_RESPONSE_LATENCY_THRESHOLD:
                continue
            seen_response_ids.add(response_node.node_id)
            advice.append(
                _advice(
                    hint=hint,
                    node=response_node,
                    client_message=(
                        "Keep custom webhook response paths under 180 seconds "
                        "or move slow "
                        "work after the response."
                    ),
                )
            )
    return tuple(advice)


def _ai_model_size_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return credit advice for large or unspecified AI model usage."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Review AI model size against credit cost and output quality."
            ),
        )
        for node in nodes
        if _node_looks_like_ai(node)
        and _node_uses_large_model_without_cost_posture(node)
    )


def _ai_output_human_review_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return review advice for AI extraction or classification outputs."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Review AI extraction or classification outputs before "
                "critical "
                "use."
            ),
        )
        for node in nodes
        if _node_looks_like_ai(node)
        and _node_mentions_ai_extraction(node)
        and not _node_mentions_review(node)
    )


def _function_nesting_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return the computed result for the caller."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Review nested functions as a way to reduce helper modules."
            ),
        )
        for node in nodes
        if _node_has_nested_function_chain(node)
    )


def _pagination_stop_condition_advice(
    *,
    nodes: tuple[MakeAstNode, ...],
    hint: KnowledgeOptimizerHint,
) -> tuple[BlueprintOptimizationAdvice, ...]:
    """Return the computed result for the caller."""
    return tuple(
        _advice(
            hint=hint,
            node=node,
            client_message=(
                "Declare a pagination stop condition, limit, or total count."
            ),
        )
        for node in nodes
        if _node_has_pagination_without_stop_condition(node)
    )


def _advice(
    *,
    hint: KnowledgeOptimizerHint,
    node: MakeAstNode,
    client_message: str,
) -> BlueprintOptimizationAdvice:
    """Return one advisory item."""
    return BlueprintOptimizationAdvice(
        advice_id=f"{hint.hint_code}:{node.node_id}",
        hint_code=hint.hint_code,
        severity=hint.severity,
        node_id=node.node_id,
        client_message=client_message,
        internal_message=f"Node {node.node_id} matched {hint.hint_id}.",
        adr_anchor=hint.adr_anchor,
    )


def _token_has_any(node: MakeAstNode, tokens: tuple[str, ...]) -> bool:
    """Return whether a node module token has any normalized token."""
    token_key = module_token_semantic_key(node.module_token)
    return any(
        module_token_semantic_key(token) in token_key for token in tokens
    )


def _node_looks_like_webhook(node: MakeAstNode) -> bool:
    """Return whether one node is a webhook-style trigger or action."""
    return node.kind == "webhook" or _token_has_any(node, ("webhook",))


def _node_looks_like_webhook_trigger(node: MakeAstNode) -> bool:
    """Return whether one node is a webhook entry point."""
    return _node_looks_like_webhook(
        node
    ) and not module_looks_like_webhook_response(node.module_token)


def _first_webhook_response_index(
    nodes: tuple[MakeAstNode, ...],
    *,
    start: int,
) -> int | None:
    """Return the first webhook response node index after a trigger."""
    for index, node in enumerate(nodes[start:], start=start):
        if module_looks_like_webhook_response(node.module_token):
            return index
    return None


def _node_has_latency_risk(node: MakeAstNode) -> bool:
    """Return whether one node is likely to consume material response time."""
    return _token_has_any(node, HIGH_LATENCY_MODULE_TOKENS)


def _node_looks_like_ai(node: MakeAstNode) -> bool:
    """Return whether one node is an AI or LLM module."""
    return node.kind == "ai_agent" or _token_has_any(
        node,
        ("ai", "agent", "llm", "openai"),
    )


def _node_uses_large_model_without_cost_posture(node: MakeAstNode) -> bool:
    """Return whether a node uses a large model without cost/credit posture."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    has_large_model = any(
        token in payload_text for token in ("large", "premium", "max")
    )
    has_cost_posture = any(
        token in payload_text for token in ("cost", "credit", "small")
    )
    return has_large_model and not has_cost_posture


def _node_mentions_ai_extraction(node: MakeAstNode) -> bool:
    """Return whether a node uses AI for extraction or classification."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    return any(
        token in payload_text
        for token in (
            "classify ",
            "decide ",
            "enrich ",
            "extract ",
            "receipt ",
            "rewrite ",
            "route ",
            "score ",
            "summarize ",
            "transform",
        )
    )


def _node_mentions_review(node: MakeAstNode) -> bool:
    """Return whether a node declares human review or validation posture."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    return any(
        token in payload_text
        for token in (
            "check ",
            "confidence threshold ",
            "fallback ",
            "human review ",
            "sample case ",
            "schema check ",
            "validate ",
            "verify",
        )
    )


def _node_has_nested_function_chain(node: MakeAstNode) -> bool:
    """Return whether node payload contains nested function syntax."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    return payload_text.count("(") >= NESTED_FUNCTION_CALL_THRESHOLD and any(
        token in payload_text
        for token in ("first(", "get(", "map(", "merge(", "sort(", "sum(")
    )


def _node_mentions_queue(node: MakeAstNode) -> bool:
    """Return whether one node declares queue-related behavior."""
    return _json_has_key_token(
        node.raw_payload,
        tokens=("queue", "queued"),
        node_local=True,
    ) or ("queue" in _json_text_blob(node.raw_payload, node_local=True))


def _node_payload_requests_all_without_pagination(node: MakeAstNode) -> bool:
    """Return if one node locally asks for all records without pagination."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    return "pagination" not in payload_text and "all" in payload_text


def _node_has_pagination_without_stop_condition(node: MakeAstNode) -> bool:
    """Return whether one node declares pagination without a stop condition."""
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    if "pagination" not in payload_text and "page" not in payload_text:
        return False
    return not any(
        token in payload_text for token in ("limit", "stop", "total", "until")
    )


def _json_has_key_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool = False,
) -> bool:
    """Return whether JSON-like data contains a key matching any token."""
    if isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            if node_local and _is_node_child_payload_key(key):
                continue
            normalized_key = module_token_semantic_key(str(key))
            if any(token in normalized_key for token in tokens):
                return True
            if _json_has_key_token(item, tokens=tokens, node_local=False):
                return True
    if isinstance(value, list):
        return any(
            _json_has_key_token(item, tokens=tokens, node_local=False)
            for item in cast("list[object]", value)
        )
    return False


def _json_text_blob(value: object, *, node_local: bool = False) -> str:
    """Return lower-case text recursively from JSON-like values."""
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, dict):
        return " ".join(
            _json_text_blob(item, node_local=False)
            for key, item in cast("dict[object, object]", value).items()
            if not node_local or not _is_node_child_payload_key(key)
        )
    if isinstance(value, list):
        return " ".join(
            _json_text_blob(item, node_local=False)
            for item in cast("list[object]", value)
        )
    if value is None:
        return ""
    return str(value).casefold()


def _is_node_child_payload_key(key: object) -> bool:
    """Return whether one root node payload key owns parsed child nodes."""
    return str(key) in NODE_CHILD_PAYLOAD_KEYS
