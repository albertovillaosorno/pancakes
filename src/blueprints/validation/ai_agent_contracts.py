# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate AI-agent and agent tool contracts in typed Make AST nodes.

Boundary contract:
- Owns: AI-agent node and tool-wrapper contract validation findings.
- Must not: execute AI calls, inspect live tools, or own generic validation
rules.
- Allows: deterministic AST payload checks and client-safe agent guidance.
- Split when: agent-node and tool-wrapper policies need separate ownership.
- Merge when: another agent validator reports the same findings identically.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from collections.abc import Callable

    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoute
    from blueprints.validation.models import (
        BlueprintFindingSeverity,
        BlueprintValidationFinding,
    )

MINIMUM_TOOL_DESCRIPTION_LENGTH = 24
MIN_MULTI_TOOL_PLAN_TOOL_COUNT: Final = 2
AI_AGENT_DETERMINISTIC_TEMPERATURE_MAX: Final = 0.7
AI_AGENT_TIMEOUT_DEFAULT_SECONDS: Final = 300
AI_AGENT_TIMEOUT_MAX_SECONDS: Final = 600
AI_AGENT_TOOL_NAME_MISSING_CODE: Final = "ai_agent.tool_name_missing"
AI_AGENT_TOOL_NAME_DUPLICATE_CODE: Final = "ai_agent.tool_name_duplicate"
AI_AGENT_TOOL_TEXT_SENSITIVE_LITERAL_CODE: Final = (
    "ai_agent.tool_text_sensitive_literal"
)
AI_AGENT_TOOL_OUTPUT_FILTER_MISSING_CODE: Final = (
    "ai_agent.tool_output_filter_missing"
)
AI_AGENT_OPTIONAL_PARAMETER_DEFAULT_MISSING_CODE: Final = (
    "ai_agent.optional_parameter_default_missing"
)
AI_AGENT_FILE_PROCESSING_CAPABILITY_MISSING_CODE: Final = (
    "ai_agent.file_processing_capability_missing"
)
AI_AGENT_KNOWLEDGE_SOURCE_MISSING_CODE: Final = (
    "ai_agent.knowledge_source_missing"
)
AI_AGENT_KNOWLEDGE_RETRIEVAL_TEST_MISSING_CODE: Final = (
    "ai_agent.knowledge_retrieval_test_missing"
)
AI_AGENT_KNOWLEDGE_RETRIEVAL_SCOPE_MISSING_CODE: Final = (
    "ai_agent.knowledge_retrieval_scope_missing"
)
AI_AGENT_MULTI_TOOL_PLAN_MISSING_CODE: Final = (
    "ai_agent.multi_tool_plan_missing"
)
AI_AGENT_MUTATING_TOOL_GUARD_MISSING_CODE: Final = (
    "ai_agent.mutating_tool_guard_missing"
)
AI_AGENT_TIMEOUT_DEFAULT_CODE: Final = "ai_agent.apply_300_second_default"
AI_AGENT_TIMEOUT_MISSING_CODE: Final = (
    "ai_agent.configure_appropriate_step_timeout"
)
AI_AGENT_TIMEOUT_MAX_EXCEEDED_CODE: Final = "ai_agent.exceed_600_seconds"
AI_AGENT_CONVERSATION_MEMORY_POLICY_MISSING_CODE: Final = (
    "ai_agent.conversation_memory_policy_missing"
)
AI_AGENT_CONVERSATION_HISTORY_LIMIT_HIGH_CODE: Final = (
    "ai_agent.conversation_history_limit_high"
)
AI_AGENT_SESSION_ISOLATION_MISSING_CODE: Final = (
    "ai_agent.session_isolation_missing"
)
AI_AGENT_RESPONSE_FORMAT_MISSING_CODE: Final = (
    "ai_agent.response_format_missing"
)
AI_AGENT_RESPONSE_FIELD_DESCRIPTION_MISSING_CODE: Final = (
    "ai_agent.response_field_description_missing"
)
AI_AGENT_DETERMINISTIC_TEMPERATURE_HIGH_CODE: Final = (
    "ai_agent.deterministic_temperature_high"
)
AI_AGENT_PRODUCTION_METRICS_MISSING_CODE: Final = (
    "ai_agent.production_metrics_missing"
)
AI_AGENT_SENSITIVE_ACTION_APPROVAL_MISSING_CODE: Final = (
    "ai_agent.sensitive_action_approval_missing"
)
AI_OBJECTIVE_TOKENS = (
    "classify ",
    "decide ",
    "extract ",
    "goal ",
    "objective ",
    "prioritize ",
    "research ",
    "score ",
    "summarize ",
    "task",
)
AI_CONTEXT_STRUCTURE_TOKENS = (
    "constraint ",
    "limitation ",
    "role ",
    "rule ",
    "style ",
    "tone",
)
AI_SECURITY_RISK_TOKENS = (
    "bank ",
    "credential ",
    "customer ",
    "personal information ",
    "pii ",
    "private ",
    "secret ",
    "sensitive ",
    "token ",
    "user data",
)
AI_SECURITY_GUARDRAIL_TOKENS = (
    "authenticated ",
    "authorization ",
    "current user ",
    "decline ",
    "least privilege ",
    "permission ",
    "validate",
)
AI_RESPONSE_FORMAT_TEXT_TOKENS = (
    "json object ",
    "output format ",
    "response format ",
    "return json ",
    "return a json ",
    "return fields ",
    "schema ",
    "structured output",
)
AI_DETERMINISTIC_TASK_TOKENS = (
    "classify ",
    "extract ",
    "json ",
    "parse ",
    "route ",
    "score ",
    "structured ",
    "validate",
)
AI_CREATIVE_TASK_TOKENS = (
    "brainstorm ",
    "creative ",
    "draft ",
    "variation ",
    "write content",
)
AI_PRODUCTION_READINESS_TEXT_TOKENS = (
    "deploy ",
    "launch ",
    "production ",
    "production readiness ",
    "ready to go live",
)
AI_PRODUCTION_METRIC_EVIDENCE_TOKENS = (
    "accuracy ",
    "benchmark ",
    "cost ",
    "eval ",
    "evaluation ",
    "failure ",
    "latency ",
    "metric ",
    "test result",
)
AI_CONVERSATION_MEMORY_TEXT_TOKENS = (
    "conversation history ",
    "memory across ",
    "multi-step conversation ",
    "multistep conversation ",
    "past interaction ",
    "previous exchange ",
    "previous interaction ",
    "remember context ",
    "remember past ",
    "remember previous ",
    "same conversation ",
    "stored conversation",
)
AI_SESSION_ISOLATION_TEXT_TOKENS = (
    "avoid carryover ",
    "carryover between sessions ",
    "clear context ",
    "different customer ",
    "new customer ",
    "separate conversation ",
    "separate session",
)
AI_FILE_PROCESSING_TEXT_TOKENS = (
    "analyze file ",
    "analyze files ",
    "process file ",
    "process files ",
    "read document ",
    "read documents ",
    "summarize file ",
    "summarize files ",
    "uploaded file ",
    "uploaded files",
)
AI_FILE_CAPABILITY_TOKENS = (
    "attachment ",
    "document ",
    "file ",
    "knowledge ",
    "pdf",
)
AI_KNOWLEDGE_ATTACHMENT_TOKENS = ("dataset", "file", "knowledge", "vector")
AI_KNOWLEDGE_ATTACHMENT_RISK_TOKENS = (
    "all data ",
    "confidential ",
    "customer data ",
    "full access ",
    "harmful instruction ",
    "harmful instructions ",
    "personal information ",
    "pii ",
    "prompt injection ",
    "private ",
    "sensitive ",
    "unauthorized",
)
AI_KNOWLEDGE_REQUIREMENT_TEXT_TOKENS = (
    "business knowledge ",
    "current knowledge ",
    "domain knowledge ",
    "domain-specific ",
    "knowledge file ",
    "knowledge source ",
    "latest information ",
    "specialized knowledge",
)
AI_KNOWLEDGE_CAPABILITY_TOKENS = (
    "document ",
    "file ",
    "knowledge ",
    "rag ",
    "source ",
    "vector",
)
AI_KNOWLEDGE_TEST_OBJECT_TOKENS = (
    "document ",
    "file ",
    "knowledge ",
    "policy ",
    "rag ",
    "reference ",
    "source",
)
AI_KNOWLEDGE_TEST_ACTION_TOKENS = (
    "look up ",
    "lookup ",
    "query ",
    "queries ",
    "retrieval ",
    "retrieve ",
    "retrieves ",
    "use ",
    "uses",
)
AI_KNOWLEDGE_SCOPE_NEED_TOKENS = (
    "context ",
    "document ",
    "knowledge base ",
    "knowledge file ",
    "knowledge source",
)
AI_KNOWLEDGE_SCOPE_EVIDENCE_TOKENS = (
    "chunk ",
    "filter ",
    "only ",
    "query ",
    "rag ",
    "relevant ",
    "retrieve ",
    "retrieves ",
    "specific",
)
AI_MULTI_TOOL_PLAN_TOKENS = (
    "after ",
    "before ",
    "depends ",
    "dependency ",
    "expected output ",
    "first ",
    "next ",
    "order ",
    "output from ",
    "sequence ",
    "then call",
)
AI_MUTATING_TOOL_TOKENS = (
    "cancel ",
    "change ",
    "create ",
    "delete ",
    "modify ",
    "payment ",
    "send ",
    "update ",
    "write",
)
AI_MUTATING_TOOL_GUARD_TOKENS = (
    "approval ",
    "approved ",
    "condition ",
    "confirm ",
    "confirmed ",
    "only after ",
    "validate ",
    "validated ",
    "validation",
)
AI_BROAD_OUTPUT_FIELD_NAMES = (
    "body ",
    "data ",
    "items ",
    "payload ",
    "raw ",
    "rawresponse ",
    "response ",
    "responsebody ",
    "results",
)
AI_BROAD_OUTPUT_TYPES = ("array", "collection", "json", "object")
AI_OUTPUT_FILTER_EVIDENCE_TOKENS = (
    "field ",
    "filter ",
    "limit ",
    "only ",
    "relevant ",
    "select ",
    "top",
)
AI_SENSITIVE_ACTION_TOKENS = (
    "approve payment ",
    "billing ",
    "cancel account ",
    "change customer ",
    "customer record ",
    "delete ",
    "financial ",
    "modify data ",
    "payment ",
    "sensitive action ",
    "sensitive operation ",
    "sensitive step ",
    "update customer ",
    "write access",
)
AI_APPROVAL_EVIDENCE_TOKENS = (
    "approval ",
    "approved by ",
    "authorization ",
    "authorize ",
    "human review ",
    "manual approval ",
    "review and approve ",
    "user approval",
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PHONE_LIKE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w])(?:\+?\d[\d .()/-]{8,}\d)(?![\w])"
)
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
MIN_PHONE_DIGITS: Final = 10
AI_AGENT_MAX_CONVERSATION_HISTORY_REPLIES: Final = 10


def validate_ai_agent_contracts(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic AI-agent contract findings."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if node.kind != "ai_agent":
            continue
        findings.extend(_agent_node_findings(node))
        findings.extend(_tool_wrapper_findings(node))
    return tuple(findings)


def _agent_node_findings(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for one AI-agent node."""
    parameters = _object_or_empty(node.raw_payload.get("parameters"))
    mapper = _object_or_empty(node.raw_payload.get("mapper"))
    text_blob = _json_text_blob({"parameters": parameters, "mapper": mapper})
    findings: list[BlueprintValidationFinding] = []
    if not node.tools:
        findings.append(
            _finding(
                code="ai_agent.tools_missing",
                severity="warning",
                node=node,
                messages=(
                    "An AI agent node has no tool contract.",
                    f"AI agent node {node.node_id} has no tools flow.",
                ),
            )
        )
    if not _has_any_key(parameters, mapper, keys=("provider", "model", "llm")):
        findings.append(
            _finding(
                code="ai_agent.provider_missing",
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI agent should declare its model or provider "
                        "assumption."
                    ),
                    (
                        f"AI agent node {node.node_id} does not expose "
                        f"provider/model metadata."
                    ),
                ),
            )
        )
    if not _has_instruction_and_input(parameters, mapper):
        findings.append(
            _finding(
                code="ai_agent.instructions_inputs_mixed",
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI agent should separate stable instructions from "
                        "runtime input."
                    ),
                    (
                        f"AI agent node {node.node_id} lacks distinct "
                        f"instruction and input keys."
                    ),
                ),
            )
        )
    if _text_looks_too_broad(text_blob):
        findings.append(
            _finding(
                code="ai_agent.scope_too_broad",
                severity="optimization",
                node=node,
                messages=(
                    (
                        "An AI agent task should be narrow enough to test and "
                        "maintain."
                    ),
                    (
                        f"AI agent node {node.node_id} uses task wording that "
                        f"is too broad."
                    ),
                ),
            )
        )
    findings.extend(
        _agent_multi_tool_plan_findings(node=node, text_blob=text_blob)
    )
    findings.extend(
        _agent_course_context_findings(node=node, text_blob=text_blob)
    )
    findings.extend(
        _agent_timeout_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            text_blob=text_blob,
        )
    )
    if "fallback" not in text_blob and "if unable" not in text_blob:
        findings.append(
            _finding(
                code="ai_agent.fallback_missing",
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI agent should define fallback behavior for tool "
                        "failures."
                    ),
                    (
                        f"AI agent node {node.node_id} has no fallback "
                        f"instruction text."
                    ),
                ),
            )
        )
    findings.extend(
        _agent_response_format_findings(
            node=node, parameters=parameters, mapper=mapper
        )
    )
    findings.extend(
        _agent_temperature_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            text_blob=text_blob,
        )
    )
    findings.extend(
        _agent_production_metrics_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            text_blob=text_blob,
        )
    )
    findings.extend(
        _agent_conversation_memory_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            text_blob=text_blob,
        )
    )
    findings.extend(
        _agent_conversation_history_limit_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
        )
    )
    findings.extend(
        _agent_session_isolation_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            text_blob=text_blob,
        )
    )
    findings.extend(
        _agent_file_processing_findings(node=node, text_blob=text_blob)
    )
    findings.extend(
        _agent_knowledge_source_findings(node=node, text_blob=text_blob)
    )
    findings.extend(
        _agent_knowledge_retrieval_scope_findings(
            node=node, text_blob=text_blob
        )
    )
    findings.extend(
        _agent_knowledge_retrieval_test_findings(
            node=node,
            parameters=parameters,
            mapper=mapper,
            metadata=_object_or_empty(node.raw_payload.get("metadata")),
        )
    )
    findings.extend(
        _agent_sensitive_action_findings(node=node, text_blob=text_blob)
    )
    if not _has_test_cases(
        parameters, mapper, _object_or_empty(node.raw_payload.get("metadata"))
    ):
        findings.append(
            _finding(
                code="ai_agent.test_cases_missing",
                severity="optimization",
                node=node,
                messages=(
                    (
                        "An AI agent should include representative behavior "
                        "test cases."
                    ),
                    f"AI agent node {node.node_id} has no declared test cases.",
                ),
            )
        )
    if _has_knowledge_attachment_risk(node):
        findings.append(
            _finding(
                code="ai_agent.knowledge_attachment_review",
                severity="warning",
                node=node,
                messages=(
                    (
                        "AI knowledge attachments should follow "
                        "least-privilege "
                        ""
                        "access."
                    ),
                    (
                        f"AI agent node {node.node_id} references broad "
                        f"private "
                        f"knowledge."
                    ),
                ),
            )
        )
    return tuple(findings)


def _agent_timeout_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic AI-agent timeout findings."""
    timeout_values = tuple(_timeout_values(parameters)) + tuple(
        _timeout_values(mapper)
    )
    findings: list[BlueprintValidationFinding] = []
    if not timeout_values:
        if _agent_text_mentions_long_running_work(text_blob):
            findings.append(
                _finding(
                    code=AI_AGENT_TIMEOUT_MISSING_CODE,
                    severity="optimization",
                    node=node,
                    messages=(
                        (
                            "Long-running AI-agent work should declare a step "
                            "timeout."
                        ),
                        (
                            f"AI agent node {node.node_id} mentions "
                            f"long-running work "
                            "without a timeout."
                        ),
                    ),
                )
            )
        return tuple(findings)
    if any(_is_empty_timeout(value) for value in timeout_values):
        findings.append(
            _finding(
                code=AI_AGENT_TIMEOUT_DEFAULT_CODE,
                severity="optimization",
                node=node,
                messages=(
                    (
                        "An empty AI-agent timeout uses the documented default "
                        "timeout."
                    ),
                    (
                        f"AI agent node {node.node_id} has an empty "
                        f"timeout; treat it as "
                        f"{AI_AGENT_TIMEOUT_DEFAULT_SECONDS} seconds."
                    ),
                ),
            )
        )
    if any(_timeout_exceeds_maximum(value) for value in timeout_values):
        findings.append(
            _finding(
                code=AI_AGENT_TIMEOUT_MAX_EXCEEDED_CODE,
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI-agent timeout must not exceed the documented "
                        "maximum."
                    ),
                    (
                        f"AI agent node {node.node_id} declares a timeout "
                        f"above "
                        f"{AI_AGENT_TIMEOUT_MAX_SECONDS} seconds."
                    ),
                ),
            )
        )
    return tuple(findings)


def _agent_response_format_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return response-format findings for one AI-agent node."""
    if not _has_response_format_contract(
        node=node, parameters=parameters, mapper=mapper
    ):
        return (
            _finding(
                code=AI_AGENT_RESPONSE_FORMAT_MISSING_CODE,
                severity="warning",
                node=node,
                messages=(
                    "An AI agent should declare its response format.",
                    (
                        f"AI agent node {node.node_id} has no response-format "
                        f"evidence."
                    ),
                ),
            ),
        )
    return _response_format_field_description_findings(
        node=node,
        parameters=parameters,
        mapper=mapper,
    )


def _response_format_field_description_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for response-format fields without descriptions."""
    findings: list[BlueprintValidationFinding] = []
    for field in (
        *_direct_response_format_fields(node.raw_payload),
        *_response_format_fields(parameters, mapper),
    ):
        if _schema_field_has_description(field):
            continue
        field_name = _optional_text(field.get("name")) or _optional_text(
            field.get("label")
        )
        field_label = field_name or "one response field"
        findings.append(
            _finding(
                code=AI_AGENT_RESPONSE_FIELD_DESCRIPTION_MISSING_CODE,
                severity="optimization",
                node=node,
                messages=(
                    "AI response-format fields should include descriptions.",
                    (
                        f"AI agent node {node.node_id} response field "
                        f"{field_label!r} has no description."
                    ),
                ),
            )
        )
    return tuple(findings)


def _agent_conversation_memory_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return conversation-memory policy findings for one AI-agent node."""
    if not _needs_conversation_memory_policy(
        text_blob
    ) or _has_conversation_memory_policy(
        parameters=parameters,
        mapper=mapper,
    ):
        return ()
    return (
        _finding(
            code=AI_AGENT_CONVERSATION_MEMORY_POLICY_MISSING_CODE,
            severity="warning",
            node=node,
            messages=(
                (
                    "An AI agent using conversation memory should declare "
                    "Conversation ID "
                    "and history-limit evidence."
                ),
                (
                    f"AI agent node {node.node_id} mentions memory without "
                    f"memory-policy evidence."
                ),
            ),
        ),
    )


def _agent_temperature_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for high creativity on deterministic AI-agent tasks."""
    temperature_values = tuple(_temperature_values(parameters)) + tuple(
        _temperature_values(mapper)
    )
    if not temperature_values:
        return ()
    if not _is_deterministic_ai_task(text_blob):
        return ()
    if not any(_temperature_is_high(value) for value in temperature_values):
        return ()
    return (
        _finding(
            code=AI_AGENT_DETERMINISTIC_TEMPERATURE_HIGH_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "Deterministic AI-agent tasks should use lower creativity "
                    "settings."
                ),
                (
                    f"AI agent node {node.node_id} has high temperature for "
                    f"deterministic work."
                ),
            ),
        ),
    )


def _agent_production_metrics_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when production AI agents lack metrics evidence."""
    if not _needs_production_metrics(text_blob):
        return ()
    if _has_production_metrics_evidence(
        node=node, parameters=parameters, mapper=mapper
    ):
        return ()
    return (
        _finding(
            code=AI_AGENT_PRODUCTION_METRICS_MISSING_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "Production AI agents should record accuracy, cost, "
                    "latency, and failures."
                ),
                (
                    f"AI agent node {node.node_id} mentions launch without "
                    f"metrics evidence."
                ),
            ),
        ),
    )


def _agent_conversation_history_limit_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for high or unbounded conversation-history limits."""
    limit_values = tuple(_history_limit_values(parameters)) + tuple(
        _history_limit_values(mapper)
    )
    if not any(_history_limit_is_high(value) for value in limit_values):
        return ()
    return (
        _finding(
            code=AI_AGENT_CONVERSATION_HISTORY_LIMIT_HIGH_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "High AI-agent conversation history should be limited for "
                    "cost and relevance."
                ),
                (
                    f"AI agent node {node.node_id} declares high "
                    f"conversation-history retention."
                ),
            ),
        ),
    )


def _agent_session_isolation_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when session carryover avoidance lacks local evidence."""
    if not _needs_session_isolation(text_blob) or _has_session_isolation(
        parameters=parameters,
        mapper=mapper,
        text_blob=text_blob,
    ):
        return ()
    return (
        _finding(
            code=AI_AGENT_SESSION_ISOLATION_MISSING_CODE,
            severity="warning",
            node=node,
            messages=(
                (
                    "AI agents that must avoid session carryover should "
                    "isolate "
                    ""
                    "context."
                ),
                (
                    f"AI agent node {node.node_id} mentions session carryover "
                    f"without isolation."
                ),
            ),
        ),
    )


def _agent_file_processing_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return when file-processing prompts lack file-capability evidence."""
    if not _needs_file_processing(text_blob) or _has_file_processing_capability(
        node
    ):
        return ()
    return (
        _finding(
            code=AI_AGENT_FILE_PROCESSING_CAPABILITY_MISSING_CODE,
            severity="warning",
            node=node,
            messages=(
                (
                    "AI agents that process files should expose "
                    "file-capability "
                    ""
                    "evidence."
                ),
                (
                    f"AI agent node {node.node_id} mentions file processing "
                    f"without evidence."
                ),
            ),
        ),
    )


def _agent_knowledge_source_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when knowledge-dependent prompts lack source evidence."""
    if not _needs_knowledge_source(
        text_blob
    ) or _has_knowledge_source_capability(node):
        return ()
    return (
        _finding(
            code=AI_AGENT_KNOWLEDGE_SOURCE_MISSING_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "AI agents that need business knowledge should declare "
                    "knowledge sources."
                ),
                (
                    f"AI agent node {node.node_id} mentions knowledge needs "
                    f"without source evidence."
                ),
            ),
        ),
    )


def _agent_knowledge_retrieval_test_findings(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
    metadata: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when knowledge-source agents have only generic tests."""
    if not _has_knowledge_source_capability(node):
        return ()
    if not _has_test_cases(parameters, mapper, metadata):
        return ()
    if _has_knowledge_retrieval_test_case(parameters, mapper, metadata):
        return ()
    return (
        _finding(
            code=AI_AGENT_KNOWLEDGE_RETRIEVAL_TEST_MISSING_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "AI agents with knowledge sources should test knowledge "
                    "retrieval."
                ),
                (
                    f"AI agent node {node.node_id} has knowledge evidence but "
                    f"generic tests."
                ),
            ),
        ),
    )


def _agent_knowledge_retrieval_scope_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when knowledge-source context lacks retrieval scope.

    evidence.
    """
    if not _has_knowledge_scope_need(node=node, text_blob=text_blob):
        return ()
    if _has_knowledge_retrieval_scope_evidence(node=node, text_blob=text_blob):
        return ()
    return (
        _finding(
            code=AI_AGENT_KNOWLEDGE_RETRIEVAL_SCOPE_MISSING_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "AI knowledge sources should retrieve only relevant "
                    "information."
                ),
                (
                    f"AI agent node {node.node_id} has knowledge context "
                    f"without scope evidence."
                ),
            ),
        ),
    )


def _agent_multi_tool_plan_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings when a multi-tool agent lacks orchestration planning."""
    if len(node.tools) < MIN_MULTI_TOOL_PLAN_TOOL_COUNT or _has_multi_tool_plan(
        text_blob
    ):
        return ()
    return (
        _finding(
            code=AI_AGENT_MULTI_TOOL_PLAN_MISSING_CODE,
            severity="optimization",
            node=node,
            messages=(
                (
                    "AI agents with multiple tools should declare tool order "
                    "and outputs."
                ),
                (
                    f"AI agent node {node.node_id} has multiple tools without "
                    f"plan evidence."
                ),
            ),
        ),
    )


def _agent_sensitive_action_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return approval findings for one sensitive AI-agent action."""
    if not _needs_sensitive_action_approval(
        text_blob
    ) or _has_sensitive_action_approval(text_blob):
        return ()
    return (
        _finding(
            code=AI_AGENT_SENSITIVE_ACTION_APPROVAL_MISSING_CODE,
            severity="warning",
            node=node,
            messages=(
                (
                    "An AI agent performing sensitive actions should declare "
                    "approval evidence."
                ),
                (
                    f"AI agent node {node.node_id} mentions sensitive actions "
                    f"without approval."
                ),
            ),
        ),
    )


def _agent_course_context_findings(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return course-promoted AI-agent objective, context, and security.

    findings.
    """
    findings: list[BlueprintValidationFinding] = []
    if not _has_agent_objective(text_blob):
        findings.append(
            _finding(
                code="ai_agent.objective_missing",
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI agent should declare the goal it is expected to "
                        "reach."
                    ),
                    (
                        f"AI agent node {node.node_id} does not expose an "
                        f"objective."
                    ),
                ),
            )
        )
    if _needs_context_structure(text_blob) and not _has_context_structure(
        text_blob
    ):
        findings.append(
            _finding(
                code="ai_agent.context_structure_missing",
                severity="optimization",
                node=node,
                messages=(
                    (
                        "An AI agent should include role, rule, or constraint "
                        "context."
                    ),
                    (
                        f"AI agent node {node.node_id} has unstructured prompt "
                        f"context."
                    ),
                ),
            )
        )
    if _has_security_risk(text_blob) and not _has_security_guardrails(
        text_blob
    ):
        findings.append(
            _finding(
                code="ai_agent.security_guardrails_missing",
                severity="warning",
                node=node,
                messages=(
                    (
                        "An AI agent handling sensitive context should declare "
                        "guardrails."
                    ),
                    (
                        f"AI agent node {node.node_id} lacks sensitive-data "
                        f"guardrails."
                    ),
                ),
            )
        )
    return tuple(findings)


def _tool_wrapper_findings(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return findings for tool wrappers under one agent."""
    findings: list[BlueprintValidationFinding] = []
    seen_names: dict[str, MakeAstRoute] = {}
    for index, tool in enumerate(node.tools, start=1):
        label = _tool_label(tool, index=index)
        name = _optional_text(tool.raw_payload.get("name"))
        description = _optional_text(tool.raw_payload.get("description")) or ""
        findings.extend(
            _tool_name_findings(
                node=node,
                tool=tool,
                label=label,
                name=name,
                seen_names=seen_names,
            )
        )
        findings.extend(
            _tool_description_findings(
                node=node,
                tool=tool,
                label=label,
                description=description,
            )
        )
        findings.extend(
            _tool_contract_findings(node=node, tool=tool, label=label)
        )
        findings.extend(
            _tool_scenario_findings(node=node, tool=tool, label=label)
        )
    return tuple(findings)


def _tool_name_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
    name: str | None,
    seen_names: dict[str, MakeAstRoute],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return name findings for one AI-agent tool wrapper."""
    if name is None:
        return (
            _tool_field_finding(
                code=AI_AGENT_TOOL_NAME_MISSING_CODE,
                node=node,
                tool=tool,
                field="name",
                message=f"{label} needs a client-readable tool name.",
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    normalized_name = _normalized_tool_name(name)
    if normalized_name in seen_names:
        findings.append(
            _tool_field_finding(
                code=AI_AGENT_TOOL_NAME_DUPLICATE_CODE,
                node=node,
                tool=tool,
                field="name",
                message=(
                    f"{label} duplicates another tool name on the same agent."
                ),
            )
        )
    else:
        seen_names[normalized_name] = tool
    if _static_sensitive_literal(name):
        findings.append(
            _tool_field_finding(
                code=AI_AGENT_TOOL_TEXT_SENSITIVE_LITERAL_CODE,
                node=node,
                tool=tool,
                field="name",
                message="An AI tool name contains sensitive literal text.",
            )
        )
    return tuple(findings)


def _tool_description_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
    description: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return description findings for one AI-agent tool wrapper."""
    findings: list[BlueprintValidationFinding] = []
    if description and _static_sensitive_literal(description):
        findings.append(
            _tool_field_finding(
                code=AI_AGENT_TOOL_TEXT_SENSITIVE_LITERAL_CODE,
                node=node,
                tool=tool,
                field="description",
                message=(
                    "An AI tool description contains sensitive literal text."
                ),
            )
        )
    if (
        len(description) < MINIMUM_TOOL_DESCRIPTION_LENGTH
        or description == "Auto-derived tool flow."
    ):
        findings.append(
            _tool_finding(
                code="ai_agent.tool_description_unclear",
                node=node,
                tool=tool,
                message=(
                    f"{label} needs a clear client-readable tool description."
                ),
            )
        )
    return tuple(findings)


def _tool_contract_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return input/output contract findings for one AI-agent tool wrapper."""
    findings: list[BlueprintValidationFinding] = []
    if not _tool_has_input_output_contract(tool):
        findings.append(
            _tool_finding(
                code="ai_agent.tool_contract_missing",
                node=node,
                tool=tool,
                message=(
                    f"{label} needs explicit input and output contractmetadata."
                ),
            )
        )
    if _tool_has_optional_input_without_default(tool):
        findings.append(
            _tool_finding(
                code=AI_AGENT_OPTIONAL_PARAMETER_DEFAULT_MISSING_CODE,
                severity="optimization",
                node=node,
                tool=tool,
                message=(
                    f"{label} has an optional input without a default value."
                ),
            )
        )
    findings.extend(
        _tool_mutating_guard_findings(node=node, tool=tool, label=label)
    )
    findings.extend(
        _tool_output_filter_findings(node=node, tool=tool, label=label)
    )
    return tuple(findings)


def _tool_mutating_guard_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return write-like tools without input and confirmation guards."""
    if not _tool_looks_mutating(tool):
        return ()
    if _tool_has_required_input_field(
        tool
    ) and _tool_has_mutating_guard_evidence(tool):
        return ()
    return (
        _tool_finding(
            code=AI_AGENT_MUTATING_TOOL_GUARD_MISSING_CODE,
            severity="warning",
            node=node,
            tool=tool,
            message=(
                f"{label} modifies data without minimum input and confirmation "
                f"evidence."
            ),
        ),
    )


def _tool_output_filter_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return broad tool outputs passed without filtering evidence."""
    if not _tool_has_broad_output_field(
        tool
    ) or _tool_has_output_filter_evidence(tool):
        return ()
    return (
        _tool_finding(
            code=AI_AGENT_TOOL_OUTPUT_FILTER_MISSING_CODE,
            severity="optimization",
            node=node,
            tool=tool,
            message=(
                f"{label} exposes broad output without filter or field-limit "
                f"evidence."
            ),
        ),
    )


def _tool_scenario_findings(
    *,
    node: MakeAstNode,
    tool: MakeAstRoute,
    label: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return scenario-tool configuration findings for one AI-agent tool.

    wrapper.
    """
    if not _tool_looks_like_scenario_tool(tool):
        return ()
    findings: list[BlueprintValidationFinding] = []
    if not _tool_is_on_demand(tool):
        findings.append(
            _tool_finding(
                code="ai_agent.tool_not_on_demand",
                node=node,
                tool=tool,
                message=f"{label} should be marked on-demand before agent use.",
            )
        )
    if not _tool_has_return_output(tool):
        findings.append(
            _tool_finding(
                code="ai_agent.tool_output_missing",
                node=node,
                tool=tool,
                message=f"{label} lacks a detectable return-output path.",
            )
        )
    return tuple(findings)


def _tool_finding(
    *,
    code: str,
    severity: BlueprintFindingSeverity = "warning",
    node: MakeAstNode,
    tool: MakeAstRoute,
    message: str,
) -> BlueprintValidationFinding:
    """Return a tool-wrapper validation finding."""
    return build_validation_finding(
        code=code,
        severity=severity,
        node=(node.node_id, tool.source_trace.path),
        catalog_module_id=None,
        messages=(
            message,
            f"AI agent node {node.node_id} tool {tool.route_id}: {message}",
        ),
    )


def _tool_field_finding(
    *,
    code: str,
    node: MakeAstNode,
    tool: MakeAstRoute,
    field: str,
    message: str,
) -> BlueprintValidationFinding:
    """Return a tool-wrapper field validation finding."""
    return build_validation_finding(
        code=code,
        severity="warning",
        node=(node.node_id, (*tool.source_trace.path, field)),
        catalog_module_id=None,
        messages=(
            message,
            f"AI agent node {node.node_id} tool {tool.route_id}: {message}",
        ),
    )


def _finding(
    *,
    code: str,
    severity: BlueprintFindingSeverity,
    node: MakeAstNode,
    messages: tuple[str, str],
) -> BlueprintValidationFinding:
    """Return a node-level validation finding."""
    client_message, internal_message = messages
    return build_validation_finding(
        code=code,
        severity=severity,
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(client_message, internal_message),
    )


def _tool_label(tool: MakeAstRoute, *, index: int) -> str:
    """Return a compact label for one tool wrapper."""
    name = _optional_text(tool.raw_payload.get("name")) or ""
    return name or f"Tool {index}"


def _normalized_tool_name(value: str) -> str:
    """Return a case- and spacing-insensitive tool name key."""
    return " ".join(value.casefold().split())


def _tool_has_input_output_contract(tool: MakeAstRoute) -> bool:
    """Return whether a tool wrapper declares inputs and outputs."""
    return (
        _has_schema_payload(tool.raw_payload.get("inputs"))
        or _has_schema_payload(tool.raw_payload.get("input_schema"))
    ) and (
        _has_schema_payload(tool.raw_payload.get("outputs"))
        or _has_schema_payload(tool.raw_payload.get("output_schema"))
    )


def _tool_has_optional_input_without_default(tool: MakeAstRoute) -> bool:
    """Return whether a tool input explicitly optional but has no default."""
    return any(
        _schema_field_is_optional(field)
        and not _schema_field_has_default(field)
        for field in _tool_input_schema_fields(tool)
    )


def _tool_has_required_input_field(tool: MakeAstRoute) -> bool:
    """Return whether one tool has at least one required input field."""
    return any(
        not _schema_field_is_optional(field)
        for field in _tool_input_schema_fields(tool)
    )


def _tool_has_broad_output_field(tool: MakeAstRoute) -> bool:
    """Return if one tool output schema exposes broad result payload fields."""
    return any(
        _schema_field_is_broad_output(field)
        for field in _tool_output_schema_fields(tool)
    )


def _tool_output_schema_fields(tool: MakeAstRoute) -> tuple[JsonObject, ...]:
    """Return JSON-object fields from tool output schemas."""
    return tuple(
        field
        for key in ("outputs", "output_schema")
        for field in _schema_fields(tool.raw_payload.get(key))
    )


def _tool_input_schema_fields(tool: MakeAstRoute) -> tuple[JsonObject, ...]:
    """Return JSON-object fields from tool input schemas."""
    return tuple(
        field
        for key in ("inputs", "input_schema")
        for field in _schema_fields(tool.raw_payload.get(key))
    )


def _schema_fields(value: object) -> tuple[JsonObject, ...]:
    """Return schema field objects from common Make schema shapes."""
    if _is_json_object(value):
        fields = value.get("fields")
        if _is_object_list(fields):
            return tuple(item for item in fields if _is_json_object(item))
        return (value,)
    if _is_object_list(value):
        return tuple(item for item in value if _is_json_object(item))
    return ()


def _schema_field_is_optional(field: JsonObject) -> bool:
    """Return whether one schema field explicitly declares optionality."""
    required = field.get("required")
    if required is False:
        return True
    if isinstance(required, str) and _normalized_mode(required) in {
        "false ",
        "no ",
        "optional",
    }:
        return True
    optional = field.get("optional")
    return optional is True or (
        isinstance(optional, str)
        and _normalized_mode(optional) in {"true", "yes", "optional"}
    )


def _schema_field_is_broad_output(field: JsonObject) -> bool:
    """Return whether a schema field describes broad raw output data."""
    name = (
        _optional_text(field.get("name"))
        or _optional_text(field.get("key"))
        or ""
    )
    field_type = (
        _optional_text(field.get("type"))
        or _optional_text(field.get("datatype"))
        or ""
    )
    name_token = _compact_key_token(name)
    type_token = _compact_key_token(field_type)
    if any(token in name_token for token in AI_BROAD_OUTPUT_FIELD_NAMES):
        return not type_token or any(
            token in type_token for token in AI_BROAD_OUTPUT_TYPES
        )
    return False


def _schema_field_has_default(field: JsonObject) -> bool:
    """Return whether one schema field declares a meaningful default value."""
    for key in ("default", "defaultValue", "default_value"):
        if key in field and _has_meaningful_contract_value(field[key]):
            return True
    return False


def _tool_looks_like_scenario_tool(tool: MakeAstRoute) -> bool:
    """Return whether one tool wrapper appears to invoke a scenario."""
    text_blob = _json_text_blob(
        {
            "name": tool.raw_payload.get("name"),
            "description": tool.raw_payload.get("description"),
            "type": tool.raw_payload.get("type"),
            "kind": tool.raw_payload.get("kind"),
            "tool_type": tool.raw_payload.get("tool_type"),
            "module": tool.raw_payload.get("module"),
        }
    )
    return any(
        token in text_blob for token in ("scenario", "start a scenario")
    ) or (
        _flow_has_module_token(
            tool.flow, predicate=lambda token: "scenario" in token.casefold()
        )
    )


def _tool_looks_mutating(tool: MakeAstRoute) -> bool:
    """Return whether one tool wrapper appears to modify data."""
    text_blob = _json_text_blob(
        {
            "name": tool.raw_payload.get("name"),
            "description": tool.raw_payload.get("description"),
            "type": tool.raw_payload.get("type"),
            "kind": tool.raw_payload.get("kind"),
            "tool_type": tool.raw_payload.get("tool_type"),
            "module": tool.raw_payload.get("module"),
        }
    )
    return _json_text_has_any(text_blob, AI_MUTATING_TOOL_TOKENS)


def _tool_has_mutating_guard_evidence(tool: MakeAstRoute) -> bool:
    """Return whether one mutating tool declares confirmation or validation.

    evidence.
    """
    text_blob = _json_text_blob(
        {
            "description": tool.raw_payload.get("description"),
            "guardrails": tool.raw_payload.get("guardrails"),
            "metadata": tool.raw_payload.get("metadata"),
            "validation": tool.raw_payload.get("validation"),
        }
    )
    return _json_text_has_any(text_blob, AI_MUTATING_TOOL_GUARD_TOKENS)


def _tool_has_output_filter_evidence(tool: MakeAstRoute) -> bool:
    """Return if one broad-output tool declares filtering or field selection."""
    text_blob = _json_text_blob(
        {
            "description": tool.raw_payload.get("description"),
            "metadata": tool.raw_payload.get("metadata"),
            "outputs": tool.raw_payload.get("outputs"),
            "output_schema": tool.raw_payload.get("output_schema"),
        }
    )
    return _json_text_has_any(text_blob, AI_OUTPUT_FILTER_EVIDENCE_TOKENS)


def _tool_is_on_demand(tool: MakeAstRoute) -> bool:
    """Return whether one scenario tool is marked on-demand."""
    metadata = _object_or_empty(tool.raw_payload.get("metadata"))
    values = (
        tool.raw_payload.get("execution_mode"),
        tool.raw_payload.get("mode"),
        tool.raw_payload.get("schedule"),
        _object_or_empty(tool.raw_payload.get("schedule")).get("mode"),
        _object_or_empty(tool.raw_payload.get("schedule")).get("type"),
        tool.raw_payload.get("scheduling"),
        _object_or_empty(tool.raw_payload.get("scheduling")).get("mode"),
        _object_or_empty(tool.raw_payload.get("scheduling")).get("type"),
        metadata.get("execution_mode"),
        metadata.get("mode"),
        _object_or_empty(metadata.get("schedule")).get("mode"),
        _object_or_empty(metadata.get("schedule")).get("type"),
        _object_or_empty(metadata.get("scheduling")).get("mode"),
        _object_or_empty(metadata.get("scheduling")).get("type"),
    )
    return any(
        _normalized_mode(value) in {"on_demand", "on" + "demand"}
        for value in values
    )


def _tool_has_return_output(tool: MakeAstRoute) -> bool:
    """Return whether one scenario tool has a detectable return-output path."""
    if _has_schema_payload(tool.raw_payload.get("outputs")):
        return True
    if _has_schema_payload(tool.raw_payload.get("output_schema")):
        return True
    return _flow_has_module_token(
        tool.flow,
        predicate=lambda token: (
            "return" in token.casefold() and "output" in token.casefold()
        ),
    )


def _flow_has_module_token(
    flow: tuple[MakeAstNode, ...],
    *,
    predicate: Callable[[str], bool],
) -> bool:
    """Return whether any node in a route-like flow matches a module-token.

    predicate.
    """
    for child in flow:
        if predicate(child.module_token):
            return True
        for route in (*child.routes, *child.branches, *child.tools):
            if _flow_has_module_token(route.flow, predicate=predicate):
                return True
    return False


def _has_instruction_and_input(
    parameters: JsonObject, mapper: JsonObject
) -> bool:
    """Return if instructions and runtime inputs are represented separately."""
    has_instruction = _has_any_key(
        parameters,
        mapper,
        keys=("instruction", "system_prompt", "developer_prompt"),
    )
    has_input = _has_any_key(
        parameters, mapper, keys=("input", "user_prompt", "prompt")
    )
    return has_instruction and has_input


def _has_test_cases(
    parameters: JsonObject,
    mapper: JsonObject,
    metadata: JsonObject,
) -> bool:
    """Return whether representative AI-agent test cases are declared."""
    return any(
        _json_has_nonempty_key(
            source, normalized_keys=("test_cases", "testcases")
        )
        for source in (parameters, mapper, metadata)
    )


def _has_response_format_contract(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
) -> bool:
    """Return whether an agent declares output-structure evidence."""
    response_format_keys = (
        "json_schema ",
        "output_schema ",
        "output_format ",
        "response_format ",
        "response_schema ",
        "structured_output",
    )
    if any(
        _json_has_key_token(source, normalized_keys=response_format_keys)
        for source in (parameters, mapper)
    ) or _json_has_direct_key_token(
        node.raw_payload, normalized_keys=response_format_keys
    ):
        return True
    text_blob = _json_text_blob({"parameters": parameters, "mapper": mapper})
    return any(token in text_blob for token in AI_RESPONSE_FORMAT_TEXT_TOKENS)


def _response_format_fields(*sources: object) -> tuple[JsonObject, ...]:
    """Return the computed result for the caller."""
    fields: list[JsonObject] = []
    for source in sources:
        fields.extend(_response_format_fields_from_value(source))
    return tuple(fields)


def _direct_response_format_fields(value: object) -> tuple[JsonObject, ...]:
    """Return response-format fields declared directly on an AI-agent node."""
    if not _is_json_object(value):
        return ()
    fields: list[JsonObject] = []
    for key, item in value.items():
        if _compact_key_token(key) in {
            "jsonschema ",
            "outputformat ",
            "outputschema ",
            "responseformat ",
            "responseschema ",
            "structuredoutput",
        }:
            fields.extend(_fields_from_response_format_payload(item))
    return tuple(fields)


def _response_format_fields_from_value(value: object) -> tuple[JsonObject, ...]:
    """Return response-format field objects from one JSON-like value."""
    if _is_json_object(value):
        fields: list[JsonObject] = []
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if key_token in {
                "jsonschema ",
                "outputformat ",
                "outputschema ",
                "responseformat ",
                "responseschema ",
                "structuredoutput",
            }:
                fields.extend(_fields_from_response_format_payload(item))
            else:
                fields.extend(_response_format_fields_from_value(item))
        return tuple(fields)
    if _is_object_list(value):
        return tuple(
            field
            for item in value
            for field in _response_format_fields_from_value(item)
        )
    return ()


def _fields_from_response_format_payload(
    value: object,
) -> tuple[JsonObject, ...]:
    """Return field objects from a response-format payload."""
    if _is_json_object(value):
        fields = value.get("fields")
        if _is_object_list(fields):
            return tuple(item for item in fields if _is_json_object(item))
        properties = value.get("properties")
        if _is_json_object(properties):
            return tuple(
                {"name": key, **item}
                if _is_json_object(item)
                else {"name": key, "type": item}
                for key, item in properties.items()
            )
    if _is_object_list(value):
        return tuple(item for item in value if _is_json_object(item))
    return ()


def _schema_field_has_description(field: JsonObject) -> bool:
    """Return whether a schema field declares a human-facing description."""
    for key, value in field.items():
        key_token = _compact_key_token(key)
        if key_token in {
            "description ",
            "desc ",
            "helptext",
        } and _has_meaningful_contract_value(value):
            return True
    return False


def _needs_conversation_memory_policy(text_blob: str) -> bool:
    """Return whether prompt text asks the agent to use conversation memory."""
    return any(
        token in text_blob for token in AI_CONVERSATION_MEMORY_TEXT_TOKENS
    )


def _has_conversation_memory_policy(
    *,
    parameters: JsonObject,
    mapper: JsonObject,
) -> bool:
    """Return if conversation ID and bounded-history evidence are present."""
    has_conversation_id = _has_any_key(
        parameters,
        mapper,
        keys=("conversation_id", "conversationid", "session_id", "thread_id"),
    )
    has_history_limit = _has_any_key(
        parameters,
        mapper,
        keys=(
            "conversation_history_limit ",
            "history_limit ",
            "max_conversation_history ",
            "maximum_conversation_history ",
            "max_history ",
            "reply_limit",
        ),
    )
    return has_conversation_id and has_history_limit


def _history_limit_values(value: object) -> tuple[object, ...]:
    """Return conversation-history limit values from JSON-like payloads."""
    if _is_json_object(value):
        values: list[object] = []
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if key_token in {
                "conversationhistorylimit ",
                "historylimit ",
                "maxconversationhistory ",
                "maximumconversationhistory ",
                "maxhistory ",
                "replylimit",
            }:
                values.append(item)
            values.extend(_history_limit_values(item))
        return tuple(values)
    if _is_object_list(value):
        return tuple(
            item for nested in value for item in _history_limit_values(nested)
        )
    return ()


def _history_limit_is_high(value: object) -> bool:
    """Return the computed result for the caller."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value > AI_AGENT_MAX_CONVERSATION_HISTORY_REPLIES
    text = _optional_text(value)
    if text is None:
        return False
    normalized = " ".join(text.casefold().split())
    if normalized in {
        "all ",
        "full ",
        "no limit ",
        "none ",
        "unbounded ",
        "unlimited",
    }:
        return True
    try:
        return float(normalized) > AI_AGENT_MAX_CONVERSATION_HISTORY_REPLIES
    except ValueError:
        return False


def _temperature_values(value: object) -> tuple[object, ...]:
    """Return temperature-like values from JSON-like payloads."""
    if _is_json_object(value):
        values: list[object] = []
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if key_token in {"creativity", "temperature"}:
                values.append(item)
            values.extend(_temperature_values(item))
        return tuple(values)
    if _is_object_list(value):
        return tuple(
            item for nested in value for item in _temperature_values(nested)
        )
    return ()


def _temperature_is_high(value: object) -> bool:
    """Return whether a temperature/creativity value is high for deterministic.

    tasks.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return float(value) > AI_AGENT_DETERMINISTIC_TEMPERATURE_MAX
    text = _optional_text(value)
    if text is None:
        return False
    normalized = " ".join(text.casefold().split())
    if normalized in {"creative", "high", "high creativity", "maximum"}:
        return True
    try:
        return float(normalized) > AI_AGENT_DETERMINISTIC_TEMPERATURE_MAX
    except ValueError:
        return False


def _is_deterministic_ai_task(text_blob: str) -> bool:
    """Return whether prompt text describes deterministic AI work."""
    if _json_text_has_any(text_blob, AI_CREATIVE_TASK_TOKENS):
        return False
    return _json_text_has_any(text_blob, AI_DETERMINISTIC_TASK_TOKENS)


def _needs_production_metrics(text_blob: str) -> bool:
    """Return whether prompt text describes production or launch readiness."""
    return _json_text_has_any(text_blob, AI_PRODUCTION_READINESS_TEXT_TOKENS)


def _has_production_metrics_evidence(
    *,
    node: MakeAstNode,
    parameters: JsonObject,
    mapper: JsonObject,
) -> bool:
    """Return whether non-prompt payload declares production metric evidence."""
    payload = {
        "parameters": _without_prompt_text(parameters),
        "mapper": _without_prompt_text(mapper),
        "metadata": _object_or_empty(node.raw_payload.get("metadata")),
    }
    return _json_text_has_any(
        _json_text_blob(payload),
        AI_PRODUCTION_METRIC_EVIDENCE_TOKENS,
    ) or any(
        _json_has_key_token(
            source, normalized_keys=AI_PRODUCTION_METRIC_EVIDENCE_TOKENS
        )
        for source in payload.values()
    )


def _needs_session_isolation(text_blob: str) -> bool:
    """Return whether prompt text asks to avoid cross-session carryover."""
    return any(token in text_blob for token in AI_SESSION_ISOLATION_TEXT_TOKENS)


def _has_session_isolation(
    *,
    parameters: JsonObject,
    mapper: JsonObject,
    text_blob: str,
) -> bool:
    """Return whether an agent declares session-isolation evidence."""
    return (
        _has_any_key(
            parameters,
            mapper,
            keys=(
                "clear_context ",
                "clearcontext ",
                "conversation_id ",
                "session_id ",
                "thread_id",
            ),
        )
        or "clear context" in text_blob
    )


def _needs_file_processing(text_blob: str) -> bool:
    """Return if prompt text asks the agent to process files or documents."""
    return any(token in text_blob for token in AI_FILE_PROCESSING_TEXT_TOKENS)


def _has_file_processing_capability(node: MakeAstNode) -> bool:
    """Return whether an agent exposes local file/document handling evidence."""
    return _agent_payload_has_file_capability(node) or any(
        _json_text_has_any(
            _json_text_blob(tool.raw_payload),
            AI_FILE_CAPABILITY_TOKENS,
        )
        for tool in node.tools
    )


def _agent_payload_has_file_capability(node: MakeAstNode) -> bool:
    """Return whether non-prompt agent payload keys expose file capability."""
    payload = {
        "parameters": _without_prompt_text(
            _object_or_empty(node.raw_payload.get("parameters"))
        ),
        "mapper": _without_prompt_text(
            _object_or_empty(node.raw_payload.get("mapper"))
        ),
        "metadata": _object_or_empty(node.raw_payload.get("metadata")),
    }
    return _json_text_has_any(
        _json_text_blob(payload), AI_FILE_CAPABILITY_TOKENS
    )


def _without_prompt_text(payload: JsonObject) -> JsonObject:
    """Return payload data excluding prompt text that only describes the.

    requirement.
    """
    prompt_key_tokens = ("prompt", "instruction", "message")
    return {
        key: value
        for key, value in payload.items()
        if not any(
            token in _compact_key_token(key) for token in prompt_key_tokens
        )
    }


def _json_text_has_any(text_blob: str, tokens: tuple[str, ...]) -> bool:
    """Return whether a lower-case JSON text blob contains any token."""
    return any(token in text_blob for token in tokens)


def _needs_knowledge_source(text_blob: str) -> bool:
    """Return whether prompt text asks for external or business knowledge."""
    return _json_text_has_any(text_blob, AI_KNOWLEDGE_REQUIREMENT_TEXT_TOKENS)


def _has_knowledge_source_capability(node: MakeAstNode) -> bool:
    """Return whether an agent exposes knowledge-source evidence outside prompt.

    text.
    """
    payload = {
        "parameters": _without_prompt_text(
            _object_or_empty(node.raw_payload.get("parameters"))
        ),
        "mapper": _without_prompt_text(
            _object_or_empty(node.raw_payload.get("mapper"))
        ),
        "metadata": _object_or_empty(node.raw_payload.get("metadata")),
    }
    return _json_text_has_any(
        _json_text_blob(payload),
        AI_KNOWLEDGE_CAPABILITY_TOKENS,
    ) or any(
        _json_text_has_any(
            _json_text_blob(tool.raw_payload), AI_KNOWLEDGE_CAPABILITY_TOKENS
        )
        for tool in node.tools
    )


def _has_knowledge_retrieval_test_case(
    parameters: JsonObject,
    mapper: JsonObject,
    metadata: JsonObject,
) -> bool:
    """Return whether declared tests exercise knowledge-source retrieval."""
    text_blob = _json_text_blob(
        (
            _test_case_values(parameters),
            _test_case_values(mapper),
            _test_case_values(metadata),
        )
    )
    return _json_text_has_any(
        text_blob,
        AI_KNOWLEDGE_TEST_OBJECT_TOKENS,
    ) and _json_text_has_any(text_blob, AI_KNOWLEDGE_TEST_ACTION_TOKENS)


def _has_knowledge_scope_need(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> bool:
    """Return the computed result for the caller."""
    if not _has_knowledge_source_capability(node):
        return False
    payload_blob = _json_text_blob(
        {
            "metadata": _object_or_empty(node.raw_payload.get("metadata")),
            "tools": [tool.raw_payload for tool in node.tools],
        }
    )
    return _json_text_has_any(
        f"{text_blob} {payload_blob}",
        AI_KNOWLEDGE_SCOPE_NEED_TOKENS,
    )


def _has_knowledge_retrieval_scope_evidence(
    *,
    node: MakeAstNode,
    text_blob: str,
) -> bool:
    """Return whether knowledge-source evidence describes scoped retrieval."""
    payload_blob = _json_text_blob(
        {
            "metadata": _object_or_empty(node.raw_payload.get("metadata")),
            "tools": [tool.raw_payload for tool in node.tools],
        }
    )
    return _json_text_has_any(
        f"{text_blob} {payload_blob}",
        AI_KNOWLEDGE_SCOPE_EVIDENCE_TOKENS,
    )


def _test_case_values(value: object) -> tuple[object, ...]:
    """Return values under test-case-like keys from a JSON-like payload."""
    if _is_json_object(value):
        values: list[object] = []
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if "testcase" in key_token:
                values.append(item)
            values.extend(_test_case_values(item))
        return tuple(values)
    if _is_object_list(value):
        return tuple(
            item for nested in value for item in _test_case_values(nested)
        )
    return ()


def _has_multi_tool_plan(text_blob: str) -> bool:
    """Return whether prompt text describes multi-tool order or dependencies."""
    return _json_text_has_any(text_blob, AI_MULTI_TOOL_PLAN_TOKENS)


def _needs_sensitive_action_approval(text_blob: str) -> bool:
    """Return whether prompt text describes sensitive or mutating actions."""
    return any(token in text_blob for token in AI_SENSITIVE_ACTION_TOKENS)


def _has_sensitive_action_approval(text_blob: str) -> bool:
    """Return whether prompt text includes human approval or authorization.

    evidence.
    """
    return any(token in text_blob for token in AI_APPROVAL_EVIDENCE_TOKENS)


def _has_knowledge_attachment_risk(node: MakeAstNode) -> bool:
    """Return whether node knowledge/context attachments require review."""
    text_blob = _json_text_blob(
        {
            "parameters": _object_or_empty(node.raw_payload.get("parameters")),
            "mapper": _object_or_empty(node.raw_payload.get("mapper")),
        }
    )
    has_attachment = any(
        token in text_blob for token in AI_KNOWLEDGE_ATTACHMENT_TOKENS
    )
    has_risk_text = any(
        token in text_blob for token in AI_KNOWLEDGE_ATTACHMENT_RISK_TOKENS
    )
    return has_attachment and has_risk_text


def _has_agent_objective(text_blob: str) -> bool:
    """Return whether prompt text exposes a concrete agent objective."""
    if _text_looks_too_broad(text_blob):
        return False
    return any(token in text_blob for token in AI_OBJECTIVE_TOKENS)


def _needs_context_structure(text_blob: str) -> bool:
    """Return whether prompt text is broad enough to need explicit structure."""
    return _text_looks_too_broad(text_blob) or _has_security_risk(text_blob)


def _has_context_structure(text_blob: str) -> bool:
    """Return whether prompt text includes role, rule, or limitation context."""
    return any(token in text_blob for token in AI_CONTEXT_STRUCTURE_TOKENS)


def _has_security_risk(text_blob: str) -> bool:
    """Return whether prompt text references sensitive agent context."""
    return any(token in text_blob for token in AI_SECURITY_RISK_TOKENS)


def _has_security_guardrails(text_blob: str) -> bool:
    """Return whether prompt text includes sensitive-data guardrails."""
    return any(token in text_blob for token in AI_SECURITY_GUARDRAIL_TOKENS)


def _agent_text_mentions_long_running_work(text_blob: str) -> bool:
    """Return whether prompt text describes a long-running agent task."""
    return any(
        phrase in text_blob
        for phrase in (
            "long reasoning ",
            "long-running ",
            "long running ",
            "multi-step ",
            "multistep ",
            "large research ",
            "research many",
        )
    )


def _timeout_values(value: object) -> tuple[object, ...]:
    """Return timeout-like values from JSON object keys."""
    if _is_json_object(value):
        values: list[object] = []
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if _is_timeout_key(key_token):
                values.append(item)
            values.extend(_timeout_values(item))
        return tuple(values)
    if _is_object_list(value):
        return tuple(
            item for nested in value for item in _timeout_values(nested)
        )
    return ()


def _is_timeout_key(key_token: str) -> bool:
    """Return if one compact JSON key declares timeout-like configuration."""
    return (
        "timeout" in key_token
        or "maxtime" in key_token
        or "maxruntime" in key_token
        or ("execution" in key_token and "time" in key_token)
    )


def _is_empty_timeout(value: object) -> bool:
    """Return whether a timeout value is explicitly present but empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if _is_json_object(value) or _is_object_list(value):
        return not value
    return False


def _timeout_exceeds_maximum(value: object) -> bool:
    """Return whether a timeout value exceeds the documented maximum seconds."""
    seconds = _timeout_seconds(value)
    return seconds is not None and seconds > AI_AGENT_TIMEOUT_MAX_SECONDS


def _timeout_seconds(value: object) -> float | None:
    """Return a timeout value normalized to seconds when locally parseable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.casefold().strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]*)", text)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    multipliers = {
        "": 1,
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "ms": 0.001,
        "millisecond": 0.001,
        "milliseconds": 0.001,
    }
    multiplier = multipliers.get(unit)
    return amount * multiplier if multiplier is not None else None


def _text_looks_too_broad(text_blob: str) -> bool:
    """Return if an instruction blob looks too broad for reliable tooling."""
    return any(
        phrase in text_blob
        for phrase in (
            "do anything ",
            "handle everything ",
            "all tasks ",
            "whatever is needed",
        )
    )


def _static_sensitive_literal(value: str) -> bool:
    """Return whether tool-facing text contains static sensitive literals."""
    stripped = value.strip()
    if not stripped:
        return False
    return (
        EMAIL_PATTERN.search(stripped) is not None
        or _contains_phone_like_value(stripped)
        or any(
            pattern.search(stripped) is not None
            for pattern in SECRET_VALUE_PATTERNS
        )
    )


def _contains_phone_like_value(value: str) -> bool:
    """Return whether text contains a phone-like contact value."""
    for match in PHONE_LIKE_PATTERN.finditer(value):
        digits = "".join(
            character for character in match.group(0) if character.isdigit()
        )
        if len(digits) >= MIN_PHONE_DIGITS:
            return True
    return False


def _has_any_key(
    parameters: JsonObject,
    mapper: JsonObject,
    *,
    keys: tuple[str, ...],
) -> bool:
    """Return whether either mapping has one of the requested keys."""
    normalized_keys = tuple(key.casefold() for key in keys)
    return any(
        _json_has_key_token(source, normalized_keys=normalized_keys)
        for source in (parameters, mapper)
    )


def _json_text_blob(value: object) -> str:
    """Return lower-case text recursively from JSON-like values."""
    if isinstance(value, str):
        return value.casefold()
    if _is_json_object(value):
        return " ".join(_json_text_blob(item) for item in value.values())
    if _is_object_list(value):
        return " ".join(_json_text_blob(item) for item in value)
    if value is None:
        return ""
    return str(value).casefold()


def _json_has_key_token(
    value: object,
    *,
    normalized_keys: tuple[str, ...],
) -> bool:
    """Return the computed result for the caller."""
    if _is_json_object(value):
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if any(
                token in key.casefold()
                or _compact_key_token(token) in key_token
                for token in normalized_keys
            ) and _has_meaningful_contract_value(item):
                return True
            if _json_has_key_token(item, normalized_keys=normalized_keys):
                return True
    if _is_object_list(value):
        return any(
            _json_has_key_token(item, normalized_keys=normalized_keys)
            for item in value
        )
    return False


def _json_has_direct_key_token(
    value: object,
    *,
    normalized_keys: tuple[str, ...],
) -> bool:
    """Return if the current JSON object has one requested key with evidence."""
    if not _is_json_object(value):
        return False
    for key, item in value.items():
        key_token = _compact_key_token(key)
        if any(
            token in key.casefold() or _compact_key_token(token) in key_token
            for token in normalized_keys
        ) and _has_meaningful_contract_value(item):
            return True
    return False


def _json_has_nonempty_key(
    value: object,
    *,
    normalized_keys: tuple[str, ...],
) -> bool:
    """Return if any nested JSON key contains a non-empty requested value."""
    if _is_json_object(value):
        for key, item in value.items():
            key_token = _compact_key_token(key)
            if any(
                token in key.casefold()
                or _compact_key_token(token) in key_token
                for token in normalized_keys
            ) and _has_meaningful_contract_value(item):
                return True
            if _json_has_nonempty_key(item, normalized_keys=normalized_keys):
                return True
    if _is_object_list(value):
        return any(
            _json_has_nonempty_key(item, normalized_keys=normalized_keys)
            for item in value
        )
    return False


def _has_schema_payload(value: object) -> bool:
    """Return whether schema-like tool data has a non-empty JSON payload."""
    if _is_json_object(value):
        return bool(value)
    if _is_object_list(value):
        return any(_schema_list_item_has_payload(item) for item in value)
    return False


def _schema_list_item_has_payload(value: object) -> bool:
    """Return whether one list item contains meaningful schema data."""
    if _is_json_object(value):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _has_meaningful_contract_value(value: object) -> bool:
    """Return whether a JSON value carries non-empty contract evidence."""
    if isinstance(value, str):
        return bool(value.strip())
    if _is_json_object(value):
        return any(
            _has_meaningful_contract_value(item) for item in value.values()
        )
    if _is_object_list(value):
        return any(_has_meaningful_contract_value(item) for item in value)
    return bool(value)


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object or an empty object."""
    return value if _is_json_object(value) else {}


def _optional_text(value: object) -> str | None:
    """Return stripped text only when the value is already text."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalized_mode(value: object) -> str:
    """Return a mode token normalized across Make export spelling variants."""
    return str(value).casefold().replace("-", "_").replace(" ", "_").strip()


def _compact_key_token(value: str) -> str:
    """Return a separator-insensitive token for exported JSON keys."""
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    """Return whether a value is list-shaped."""
    return isinstance(value, list)
