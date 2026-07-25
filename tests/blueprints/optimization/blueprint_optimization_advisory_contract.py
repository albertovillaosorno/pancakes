# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for blueprint optimization advice from promoted knowledge.

Boundary contract:
- Owns: deterministic optimization advisory behavior tests.
- Must not: validate catalog truth, repair blueprints, or read course evidence.
- Allows: compact AST fixtures and fake knowledge-store optimizer hints.
- Split when: advisory domains need separate focused contract files.
- Merge when: another test file owns the same optimization advice behavior.
"""

from __future__ import annotations

import json

from blueprints.ast import parse_make_ast_json_text
from blueprints.optimization import build_blueprint_optimization_advice
from catalog.knowledge import KnowledgeOptimizerHint, KnowledgeStoreQuery


def test_optimization_advice_uses_promoted_operation_and_pagination_hints() -> (
    None
):
    """Optimization advice is driven by knowledge-store hints, not course.

    files.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "optimization-advice",
                "flow": [
                    {"id": 1, "module": "util:Iterator"},
                    {
                        "id": 2,
                        "module": "http:MakeRequest",
                        "parameters": {"mode": "all records"},
                    },
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    codes = tuple(item.hint_code for item in advice)

    assert not ("optimization.operation_volume_review" not in codes), (
        f"Operation-volume advice did not run: {advice}"
    )
    assert not ("optimization.pagination_required" not in codes), (
        f"Pagination advice did not run: {advice}"
    )


def test_optimization_advice_uses_promoted_webhook_queue_hint() -> None:
    """Webhook queue advice is driven by the promoted knowledge-store hint."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "webhook-queue-advice",
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "parameters": {"queue": "enabled"},
                    }
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    codes = tuple(item.hint_code for item in advice)

    assert not ("optimization.webhook_queue_review" not in codes), (
        f"Webhook queue advice did not run: {advice}"
    )


def test_optimization_advice_flags_slow_work_before_webhook_response() -> None:
    """Webhook response timeout advice uses the promoted Advanced Webhooks.

    hint.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "webhook-response-timeout-risk",
                "flow": [
                    {"id": 1, "module": "gateway:CustomWebHook"},
                    {"id": 2, "module": "http:MakeRequest"},
                    {"id": 3, "module": "ai-local-agent:RunLocalAIAgent"},
                    {"id": 4, "module": "gateway:WebhookRespond"},
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    codes = tuple(item.hint_code for item in advice)

    assert not ("optimization.webhook_response_timeout_risk" not in codes), (
        f"Webhook response timeout advice did not run: {advice}"
    )


def test_optimization_advice_flags_slow_route_759c605f() -> None:
    """Webhook response timeout advice follows router route paths."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "webhook-response-route-timeout-risk",
                "flow": [
                    {"id": 1, "module": "gateway:CustomWebHook"},
                    {
                        "id": 2,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "flow": [
                                    {"id": 3, "module": "http:MakeRequest"},
                                    {
                                        "id": 4,
                                        "module": (
                                            "ai-provider:CreateCompletion"
                                        ),
                                    },
                                    {
                                        "id": 5,
                                        "module": "gateway:WebhookRespond",
                                    },
                                ]
                            }
                        ],
                    },
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    response_advice = tuple(
        item
        for item in advice
        if item.hint_code == "optimization.webhook_response_timeout_risk"
    )

    assert tuple(item.node_id for item in response_advice) == ("5",), (
        f"Route webhook response timeout advice drifted: {advice}"
    )


def test_optimization_advice_ignores_child_only_webhook_queue_payload() -> None:
    """Webhook queue advice does not inherit child route payload evidence."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "child-only-webhook-queue",
                "flow": [
                    {
                        "id": 1,
                        "module": "gateway:CustomWebHook",
                        "routes": [
                            {
                                "flow": [
                                    {
                                        "id": 2,
                                        "module": "util:SetVariable",
                                        "parameters": {"queue": "child-only"},
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    queue_advice = tuple(
        item
        for item in advice
        if item.hint_code == "optimization.webhook_queue_review"
    )

    assert not (queue_advice), (
        f"Webhook queue advice inherited child payload evidence: {advice}"
    )


def test_optimization_advice_ignores_child_only_pagination_payload() -> None:
    """Pagination advice does not inherit child route payload evidence."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "child-only-pagination",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "parameters": {"endpoint": "/contacts"},
                        "routes": [
                            {
                                "flow": [
                                    {
                                        "id": 2,
                                        "module": "util:SetVariable",
                                        "parameters": {"mode": "all records"},
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    pagination_advice = tuple(
        item
        for item in advice
        if item.hint_code == "optimization.pagination_required"
    )

    assert not (pagination_advice), (
        f"Pagination advice inherited child payload evidence: {advice}"
    )


def test_optimization_advice_uses_promoted_ai_and_function_hints() -> None:
    """Remaining promoted course hints drive AI, function, and pagination.

    advice.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "course-completion-advice",
                "flow": [
                    {
                        "id": 1,
                        "module": "ai-provider:CreateCompletion",
                        "parameters": {
                            "model": "large ",
                            "prompt": (
                                "Extract receipt fields and score confidence."
                            ),
                        },
                    },
                    {
                        "id": 2,
                        "module": "util:SetVariable",
                        "parameters": {
                            "value": "{{get(map(1.items; name); 1)}}",
                        },
                    },
                    {
                        "id": 3,
                        "module": "http:MakeRequest",
                        "parameters": {"pagination": "page by page"},
                    },
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )
    codes = tuple(item.hint_code for item in advice)

    expected_codes = {
        "optimization.ai_model_size_review ",
        "optimization.ai_output_human_review ",
        "optimization.function_nesting_compaction ",
        "optimization.pagination_stop_condition",
    }
    missing_codes = expected_codes.difference(codes)
    assert not (missing_codes), (
        f"Promoted AI/function advice did not run: {advice}"
    )


def test_optimization_advice_flags_ai_generated_106b90c5() -> None:
    """AI-generated transformations used downstream should declare validation.

    evidence.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "ai-generated-transformation-evidence",
                "flow": [
                    {
                        "id": 1,
                        "module": "ai-provider:CreateCompletion",
                        "parameters": {
                            "model": "small",
                            "prompt": (
                                "Rewrite, enrich, decide, route, and transform "
                                "one customer "
                                "message for downstream automation."
                            ),
                        },
                    },
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )

    assert "optimization.ai_output_human_review" in tuple(
        item.hint_code for item in advice
    ), f"AI-generated transformation evidence advice did not run: {advice}"


def test_optimization_advice_accepts_ai_generated_transformation_evidence() -> (
    None
):
    """Schema checks, sample cases, thresholds, or fallback evidence satisfy.

    the.

    advisory.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "ai-generated-transformation-evidence-present",
                "flow": [
                    {
                        "id": 1,
                        "module": "ai-provider:CreateCompletion",
                        "parameters": {
                            "model": "small",
                            "prompt": (
                                "Rewrite and route one customer message with "
                                "schema checks, "
                                "sample cases, confidence threshold, and "
                                "fallback handling."
                            ),
                        },
                    },
                ],
            }
        )
    )

    advice = build_blueprint_optimization_advice(
        root=root,
        knowledge=optimization_knowledge_query(),
    )

    assert "optimization.ai_output_human_review" not in tuple(
        item.hint_code for item in advice
    ), f"AI-generated transformation evidence still produced advice: {advice}"


def optimization_knowledge_query() -> KnowledgeStoreQuery:
    """Return a minimal knowledge projection with optimizer hints."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(),
        optimizer_hints=(
            KnowledgeOptimizerHint(
                hint_id="course-hint-operation-volume",
                domain="operations",
                hint_code="optimization.operation_volume_review",
                severity="optimization",
                description=(
                    "Iterator-like modules can multiply operation volume."
                ),
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-pagination",
                domain="http",
                hint_code="optimization.pagination_required",
                severity="optimization",
                description="List-style retrieval needs pagination.",
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-webhook-queue",
                domain="webhooks",
                hint_code="optimization.webhook_queue_review",
                severity="optimization",
                description="Webhook queues require retry and response review.",
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-webhook-response-timeout",
                domain="webhooks",
                hint_code="optimization.webhook_response_timeout_risk",
                severity="optimization",
                description=(
                    "Webhook custom responses have a 180-second responsewindow."
                ),
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-ai-model-size-review",
                domain="ai_agents",
                hint_code="optimization.ai_model_size_review",
                severity="optimization",
                description=(
                    "Large AI models should be reviewed against credit cost."
                ),
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-ai-output-human-review",
                domain="ai_agents",
                hint_code="optimization.ai_output_human_review",
                severity="optimization",
                description=(
                    "Critical AI extraction outputs should be reviewed."
                ),
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-function-nesting-compaction",
                domain="functions",
                hint_code="optimization.function_nesting_compaction",
                severity="optimization",
                description="Nested functions can reduce helper modules.",
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
            KnowledgeOptimizerHint(
                hint_id="course-hint-pagination-stop-condition",
                domain="http",
                hint_code="optimization.pagination_stop_condition",
                severity="optimization",
                description="Pagination should declare stop criteria.",
                adr_anchor="001064#repo.make-knowledge.optimizer-hints",
            ),
        ),
    )
