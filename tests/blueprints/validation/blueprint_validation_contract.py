# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make blueprint validation.

Boundary contract:
- Owns: tests for Make blueprint validation gates and delivery-mode findings.
- Must not: test renderer output, catalog compilation, or repository tools.
- Allows: catalog-backed blueprint fixtures and validation report assertions.
- Split when: validation subdomains become too large for one focused module.
- Merge when: another blueprint validation test duplicates these behaviors.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import (
    AiReviewError,
    BlueprintDeliveryCoverage,
    BlueprintValidationFinding,
    BlueprintValidationReport,
    achieved_blueprint_delivery_mode,
    bounded_review_text,
    build_blueprint_delivery_coverage,
    build_handoff_placeholder_manifest,
    build_minimal_content_review,
    choose_catalog_field_seed_value,
    classify_catalog_field_binding,
    coverage_regressed,
    decode_text_content,
    extract_json_object,
    guard_blueprint_for_render,
    is_unresolved_handoff_value,
    normalize_legacy_policy,
    normalize_quality_profile,
    reject_server_side_ai,
    validate_blueprint,
    validate_content_review,
)
from catalog import (
    CatalogApp,
    CatalogAppVersion,
    CatalogField,
    CatalogModule,
    CatalogSnapshot,
    catalog_snapshot_from_json,
)
from catalog.json_payloads import normalize_json_object
from catalog.knowledge import (
    KnowledgeDesignerMessageEvidence,
    KnowledgeRuleFact,
    KnowledgeStoreQuery,
    KnowledgeTransactionProfile,
)

from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.validation import BlueprintFindingSeverity

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
CLIENT_PATH_TOKENS = ("\\", "/", "src/", "tests/", "Refactor", "C:")
BOUNDED_REVIEW_LIMIT = 5
MALFORMED_NODE_ID_CASES = 6
MALFORMED_NODE_VERSION_CASES = 2
REPEATED_ERROR_HANDLER_FAILURES = 2
REPEATED_OUTPUT_REFERENCE_FAILURES = 2
REQUIRED_PARAMETER_MISSING_COUNT = 2
AI_TOOL_CONTRACT_FINDING_COUNT = 2
EMPTY_FILTER_ALIAS_FAILURES = 3
MALFORMED_NOTE_MODULE_ID_FAILURES = 5


def test_blueprint_validator_accepts_resolved_catalog_0babc5fa() -> None:
    """A catalog-backed module with required mappings has no blocking errors."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "valid-http",
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
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (report.has_errors), (
        f"Resolved blueprint should not have blocking findings: {report}"
    )
    assert not ("deprecated_module" not in report.codes()), (
        f"Deprecated catalog module should warn: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_empty_ast_without_blocking_errors() -> (
    None
):
    """Blueprint validation keeps empty AST behavior stable."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-ast",
                    "flow": [],
                    "metadata": {"schedule": {"id": "schedule:manual"}},
                },
                sort_keys=True,
            )
        ),
        catalog=load_catalog_fixture(),
    )
    assert not (report.has_errors), (
        f"Empty AST should not get blocking findings: {report}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_fake_modules() -> None:
    """A nonexistent module cannot validate as a usable Make module."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "fake-module",
                    "flow": [
                        {"id": 1, "module": "unknown-service:MissingAction"}
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert report.has_errors, (
        "Fake module should create a blocking validation error."
    )
    assert not ("module.unresolved" not in report.codes()), (
        f"Fake module did not produce unresolved finding: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_generation_gate_blocks_nonexistent_module_requests() -> None:
    """Unknown module requests return typed discovery blockers instead of.

    blueprints.
    """
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "fake-module-request",
                    "flow": [
                        {"id": 1, "module": "unknown-service:MissingAction"}
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (result.can_render), (
        "Nonexistent module request should not be ready to render."
    )
    assert result.blockers, (
        f"Unknown module did not return typed blocker: {result.blockers}"
    )
    assert result.blockers[0].code == "generation.unsupported_module", (
        f"Unknown module did not return typed blocker: {result.blockers}"
    )
    assert (
        result.blockers[0].requested_module == "unknown-service:MissingAction"
    ), f"Requested module was not preserved: {result.blockers[0]}"
    assert not (
        "Make app raw spec" not in result.blockers[0].needed_evidence
    ), f"Discovery requirements are incomplete: {result.blockers[0]}"
    assert not (
        "validated catalog" not in result.blockers[0].client_explanation
    ), f"Client explanation is not proposal friendly: {result.blockers[0]}"


def test_generation_gate_keeps_repeated_validation_blocker_ids_distinct() -> (
    None
):
    """Repeated validation failures on one node keep distinct blocker IDs."""
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "repeated-error-handler-failures",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [{"notFlow": []}, {"notFlow": []}],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    error_handler_blockers = tuple(
        blocker
        for blocker in result.blockers
        if "onerror" in blocker.internal_detail
        and blocker.code == "generation.validation_failed"
    )
    blocker_ids = tuple(
        blocker.blocker_id for blocker in error_handler_blockers
    )
    assert len(blocker_ids) == REPEATED_ERROR_HANDLER_FAILURES, (
        f"Expected two error-handler blockers: {result.blockers}"
    )
    assert len(set(blocker_ids)) == len(blocker_ids), (
        f"Repeated validation blockers reused IDs: {blocker_ids}"
    )


def test_generation_gate_allows_warning_only_blueprints() -> None:
    """Warnings and optimizations do not block rendering when validation has no.

    errors.
    """
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "warning-only",
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
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert result.can_render, (
        f"Warning-only blueprint should pass the generation gate: {result}"
    )
    assert not (result.blockers), (
        f"Warning-only blueprint should pass the generation gate: {result}"
    )


def test_generation_gate_applies_knowledge_promoted_errors() -> None:
    """Knowledge-backed validation errors must block pre-render generation."""
    result = guard_blueprint_for_render(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sequential-webhook-response-gate",
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
        ),
        catalog=load_catalog_fixture(),
        knowledge=webhook_knowledge_query(),
    )

    assert not (result.can_render), (
        f"Knowledge-backed validation errors must block rendering: {result}"
    )
    assert not (
        "webhook.sequential_response_conflict"
        not in result.validation_report.codes()
    ), f"Promoted webhook rule did not reach the gate: {result}"
    assert any(
        blocker.code == "generation.validation_failed"
        and "webhook.sequential_response_conflict" in blocker.blocker_id
        for blocker in result.blockers
    ), f"Knowledge-backed error did not become a blocker: {result.blockers}"


def test_blueprint_validator_rejects_missing_required_mappings() -> None:
    """Required catalog parameters must be present in parameters or mapper.

    data.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "missing-method",
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
                            "module": "http:MakeRequest",
                            "parameters": {"url": "https://example.invalid"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("mapping.required_parameter_missing" not in report.codes()), (
        f"Missing required mapping was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_blank_required_mapping_strings() -> None:
    """Whitespace-only strings do not satisfy required catalog mappings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "blank-required-mappings",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {"method": "   ", "url": "\t"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    missing_count = report.codes().count("mapping.required_parameter_missing")
    assert missing_count == REQUIRED_PARAMETER_MISSING_COUNT, (
        f"Blank required mappings were treated as mapped: {report.findings}"
    )
    missing_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "mapping.required_parameter_missing"
    )
    missing_finding_ids = tuple(
        finding.finding_id for finding in missing_findings
    )
    assert len(set(missing_finding_ids)) == len(missing_finding_ids), (
        f"Repeated required-field findings reused IDs: {missing_finding_ids}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_required_mapping_containers() -> (
    None
):
    """Empty JSON containers do not satisfy required catalog mappings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-container-required-mappings",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {"method": [], "url": {}},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    missing_count = report.codes().count("mapping.required_parameter_missing")
    assert missing_count == REQUIRED_PARAMETER_MISSING_COUNT, (
        f"Empty containers were treated as mapped: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_treats_json_falsy_required_values_as_mapped() -> (
    None
):
    """Required fields with meaningful JSON false or zero values count as.

    mapped.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "falsy-required-values",
                    "flow": [
                        {
                            "id": 1,
                            "metadata": {
                                "raw_spec": {
                                    "catalog_module_id": "module:test",
                                    "issues": [],
                                    "raw_spec_sha256": "1" * 64,
                                    "status": "resolved",
                                }
                            },
                            "module": "test:FalsyRequired",
                            "parameters": {"count": 0, "enabled": False},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=catalog_with_falsy_required_fields(),
    )

    assert "mapping.required_parameter_missing" not in report.codes(), (
        f"Falsy mapped values were treated as missing: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_checks_routes_schedule_and_ai_tool_contracts() -> (
    None
):
    """Route structure, schedule basics, and AI tool contracts produce typed.

    findings.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "structure-checks",
                    "flow": [
                        {"id": 1, "module": "builtin:BasicRouter"},
                        {
                            "id": 2,
                            "module": "ai-local-agent:RunLocalAIAgent",
                        },
                        {
                            "id": 3,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {"filter": {"name": "empty"}, "flow": []}
                            ],
                        },
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    expected_codes = {
        "router.routes_missing ",
        "route.empty_flow ",
        "filter.empty_conditions ",
        "schedule.missing ",
        "ai_agent.tools_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Expected structure findings missing: {missing_codes}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_schedule_id() -> None:
    """Schedule IDs must be explicit strings, not coerced JSON scalars."""
    unsafe_schedule_secret = "sk-" + ("S" * 24)
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "malformed-schedule-id",
                    "flow": [],
                    "metadata": {
                        "schedule": {
                            "id": True,
                            "private_token": unsafe_schedule_secret,
                        }
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("schedule.id_invalid" not in report.codes()), (
        f"Malformed schedule ID was not rejected: {report.codes()}"
    )
    schedule_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "schedule.id_invalid"
    )
    leaked_messages = [
        message
        for finding in schedule_findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_schedule_secret in message or "private_token" in message
    ]
    assert not leaked_messages, (
        f"Schedule payload leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_sub_minute_schedule_interval() -> None:
    """Explicit sub-minute schedule metadata is a local operation-cadence.

    risk.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sub-minute-schedule",
                    "flow": [],
                    "metadata": {
                        "schedule": {
                            "id": "schedule:fast-watch",
                            "every": 30,
                            "unit": "seconds",
                        }
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "schedule.sub_minute_interval"
    )

    assert findings, (
        f"Sub-minute schedule cadence was not detected: {report.codes()}"
    )
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Sub-minute schedule findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_minute_schedule_interval() -> None:
    """Minute-or-slower schedule metadata stays quiet for the sub-minute.

    rule.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "minute-schedule",
                    "flow": [],
                    "metadata": {
                        "schedule": {
                            "id": "schedule:minute-watch",
                            "every": 1,
                            "unit": "minute",
                        }
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "schedule.sub_minute_interval" not in report.codes(), (
        f"Minute schedule cadence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_ai_agent_contract_risks() -> None:
    """AI-agent validation should flag missing agent and tool contracts."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "risky-agent",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "instructions": (
                                    "Do anything needed and use all data from "
                                    "the private knowledge dataset."
                                )
                            },
                            "tools": [
                                {
                                    "name": "Scenario tool ",
                                    "description": "Do stuff",
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    expected_codes = {
        "ai_agent.provider_missing ",
        "ai_agent.instructions_inputs_mixed ",
        "ai_agent.scope_too_broad ",
        "ai_agent.objective_missing ",
        "ai_agent.context_structure_missing ",
        "ai_agent.security_guardrails_missing ",
        "ai_agent.fallback_missing ",
        "ai_agent.response_format_missing ",
        "ai_agent.test_cases_missing ",
        "ai_agent.knowledge_attachment_review ",
        "ai_agent.tool_description_unclear ",
        "ai_agent.tool_contract_missing ",
        "ai_agent.tool_not_on_demand ",
        "ai_agent.tool_output_filter_missing ",
        "ai_agent.tool_output_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"AI-agent contract findings missing: {missing_codes}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_sensitive_customer_619cfede() -> None:
    """Sensitive customer data in knowledge files needs attachment review.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sensitive-customer-data-knowledge-file",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Role: support assistant. Summarize the "
                                    "current ticket "
                                    "using the knowledge file with sensitive "
                                    "customer data,"
                                    "validate current user permission, and "
                                    "follow fallback "
                                    "instructions if retrieval fails."
                                ),
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["retrieve one customer policy"],
                            },
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_attachment_review" in report.codes(), (
        "Sensitive customer data in knowledge files did not require attachment "
        "review:"
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_injection_risk_knowledge_files() -> None:
    """Knowledge files with injection or unauthorized-access risk need.

    review.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "injection-risk-knowledge-file",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Role: support assistant. Summarize one "
                                    "policy from the "
                                    "knowledge file after validating current "
                                    "user permission;"
                                    "review unauthorized access and harmful "
                                    "instructions as "
                                    "fallback conditions."
                                ),
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["retrieve one scoped policy"],
                            },
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_attachment_review" in report.codes(), (
        "Knowledge files with injection or unauthorized-access risk did not "
        "require review:"
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_ai_agent_contract_evidence() -> None:
    """AI-agent keys must carry meaningful values, not just empty shapes."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-agent-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "",
                                "instructions": " ",
                                "input": [],
                                "test_cases": [{}],
                            },
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    expected_codes = {
        "ai_agent.provider_missing ",
        "ai_agent.instructions_inputs_mixed ",
        "ai_agent.test_cases_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Empty AI-agent evidence was accepted: {missing_codes} "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_ai_agent_timeout_policy() -> None:
    """AI-agent timeout rules use only local exported configuration evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-timeout-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Research many records in a long-running "
                                    "multi-step task "
                                    "and use fallback instructions if tools "
                                    "are "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                        },
                        {
                            "id": 2,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                                "stepTimeout": "",
                            },
                        },
                        {
                            "id": 3,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                                "stepTimeout": "11 minutes",
                            },
                        },
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    expected_codes = {
        "ai_agent.configure_appropriate_step_timeout ",
        "ai_agent.apply_300_second_default ",
        "ai_agent.exceed_600_seconds",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"AI-agent timeout findings missing: {missing_codes}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_agent_response_format_missing() -> (
    None
):
    """AI-agent contracts should declare response format evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-response-format-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.response_format_missing" in report.codes(), (
        f"Missing AI-agent response format was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_response_format_evidence() -> (
    None
):
    """Explicit response-format metadata satisfies AI-agent output-structure.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-response-format-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "score", "type": "number"}
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.response_format_missing" not in report.codes(), (
        f"Response-format evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_response_650abfa3() -> None:
    """Response-format fields should describe what belongs in each field."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-response-format-field-description-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "score", "type": "number"}
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.response_field_description_missing" in report.codes(), (
        f"Missing response-field description was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_described_response_format_fields() -> None:
    """Response-format field descriptions satisfy field-level response.

    guidance.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-response-format-field-description-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "score ",
                                            "type": "number ",
                                            "description": "Lead quality score "
                                            "from 0 to 100.",
                                        }
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert (
        "ai_agent.response_field_description_missing" not in report.codes()
    ), f"Described response-field still produced a warning: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_multi_tool_agent_without_plan() -> None:
    """Multi-tool agents should declare order, dependencies, or expected.

    outputs.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-multi-tool-plan-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if a "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "score ",
                                            "type": "number ",
                                            "description": "Lead quality score "
                                            "from 0 to 100.",
                                        }
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead enrichment scenario",
                                    "description": (
                                        "Looks up one lead and returns "
                                        "enrichment evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "industry", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                },
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one enriched lead and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 4,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 5,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.multi_tool_plan_missing" in report.codes(), (
        f"Missing multi-tool plan was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_multi_tool_agent_plan() -> None:
    """Prompted order/dependency evidence satisfies multi-tool agent.

    planning.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-multi-tool-plan-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead. First call lead "
                                    "enrichment, then call "
                                    "lead scoring with the output from "
                                    "enrichment. Use fallback "
                                    "instructions if a tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "score ",
                                            "type": "number ",
                                            "description": "Lead quality score "
                                            "from 0 to 100.",
                                        }
                                    ],
                                },
                                "testCases": ["valid enriched lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead enrichment scenario",
                                    "description": (
                                        "Looks up one lead and returns "
                                        "enrichment evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "industry", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                },
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one enriched lead and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 4,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 5,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.multi_tool_plan_missing" not in report.codes(), (
        f"Multi-tool plan evidence still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_high_c2346043() -> None:
    """High temperature should be lowered for deterministic AI-agent tasks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-deterministic-temperature-high",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "temperature": 0.95,
                                "systemPrompt": (
                                    "Classify one support request into a "
                                    "structured JSON "
                                    "category and use fallback instructions if "
                                    "the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "category ",
                                            "type": "text ",
                                            "description": "Support request "
                                            "category.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one support request and "
                                        "returns category "
                                        "evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "category", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.deterministic_temperature_high" in report.codes(), (
        f"High deterministic temperature was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_low_temperature_f3451606() -> None:
    """Low temperature satisfies deterministic AI-agent tasks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-deterministic-temperature-low",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "temperature": 0.2,
                                "systemPrompt": (
                                    "Classify one support request into a "
                                    "structured JSON "
                                    "category and use fallback instructions if "
                                    "the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "category ",
                                            "type": "text ",
                                            "description": "Support request "
                                            "category.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one support request and "
                                        "returns category "
                                        "evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "category", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.deterministic_temperature_high" not in report.codes(), (
        f"Low deterministic temperature still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_production_ai_agent_without_metrics() -> (
    None
):
    """Production AI agents should expose metric evidence before launch."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-production-metrics-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support request before "
                                    "production launch "
                                    "and use fallback instructions if the tool "
                                    "is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "category ",
                                            "type": "text ",
                                            "description": "Support request "
                                            "category.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one support request and "
                                        "returns category "
                                        "evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "category", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.production_metrics_missing" in report.codes(), (
        f"Missing production metrics were not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_production_ai_agent_metrics() -> None:
    """Metric evidence satisfies production-readiness AI-agent checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-production-metrics-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "evaluationMetrics": {
                                    "accuracy": "95% fixture pass rate ",
                                    "cost": "estimated per run ",
                                    "latency": "p95 under 4 seconds ",
                                    "failures": "fallback tracked",
                                },
                                "systemPrompt": (
                                    "Classify one support request before "
                                    "production launch "
                                    "and use fallback instructions if the tool "
                                    "is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "category ",
                                            "type": "text ",
                                            "description": "Support request "
                                            "category.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one support request and "
                                        "returns category "
                                        "evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "category", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.production_metrics_missing" not in report.codes(), (
        f"Production metrics still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_98e5d54f() -> None:
    """Conversation-memory agent prompts should declare ID and bounded.

    history.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-conversation-memory-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support thread, remember "
                                    "context across "
                                    "multiple questions in the same "
                                    "conversation, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid support thread"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support thread and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "thread_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.conversation_memory_policy_missing" in report.codes(), (
        f"Missing conversation memory policy was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_conversation_memory_policy() -> (
    None
):
    """Conversation ID plus history limit satisfies conversation-memory.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-conversation-memory-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support thread, remember "
                                    "context across "
                                    "multiple questions in the same "
                                    "conversation, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "conversationId": "{{1.customer_id}}",
                                "maxConversationHistory": 10,
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid support thread"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support thread and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "thread_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert (
        "ai_agent.conversation_memory_policy_missing" not in report.codes()
    ), (
        f"Conversation memory policy evidence produced a warning: "
        f"{report.findings}"
    )
    assert "ai_agent.conversation_history_limit_high" not in report.codes(), (
        f"Bounded conversation history produced a high-limit warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_96288641() -> None:
    """High or unlimited conversation-history limits should be reduced."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-conversation-history-high",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support thread, remember "
                                    "context across "
                                    "multiple questions in the same "
                                    "conversation, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "conversationId": "{{1.customer_id}}",
                                "maxConversationHistory": 50,
                                "replyLimit": "unlimited",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid support thread"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support thread and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "thread_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.conversation_history_limit_high" in report.codes(), (
        f"High conversation-history limit was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_agent_session_isolation_missing() -> (
    None
):
    """Agents that must avoid carryover should declare context isolation."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-session-isolation-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support thread, avoid "
                                    "carryover between "
                                    "sessions for a different customer, and "
                                    "use "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid support thread"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support thread and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "thread_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.session_isolation_missing" in report.codes(), (
        f"Missing session isolation was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_session_isolation() -> None:
    """Conversation ID evidence satisfies session-isolation checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-session-isolation-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one support thread, avoid "
                                    "carryover between "
                                    "sessions for a different customer, and "
                                    "use "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "conversationId": "{{1.customer_id}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid support thread"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support thread and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "thread_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.session_isolation_missing" not in report.codes(), (
        f"Session isolation evidence still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_8ccffa7d() -> None:
    """Sensitive AI-agent actions should declare approval evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-sensitive-action-missing-approval",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Update customer billing records for one "
                                    "ticket, validate "
                                    "the current user, and use fallback "
                                    "instructions if the "
                                    "tool is unavailable."
                                ),
                                "userPrompt": "{{1.ticket_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "status", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid billing ticket"],
                            },
                            "tools": [
                                {
                                    "name": "Billing update scenario",
                                    "description": (
                                        "Updates one billing record and "
                                        "returns "
                                        "status evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "ticket_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "status", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.sensitive_action_approval_missing" in report.codes(), (
        f"Missing sensitive-action approval was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_0cfff233() -> None:
    """Personal information in AI context should require explicit guardrails."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-personal-information-guardrails-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Answer one support question using "
                                    "knowledge base personal "
                                    "information about other users and use "
                                    "fallback instructions "
                                    "if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.ticket_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "answer ",
                                            "type": "text ",
                                            "description": "Support answer for "
                                            "the requester.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support question"],
                            },
                            "tools": [
                                {
                                    "name": "Support lookup scenario",
                                    "description": (
                                        "Looks up one support record and "
                                        "returns answer evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "ticket_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "answer", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.security_guardrails_missing" in report.codes(), (
        f"Missing personal-information guardrails were not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_sensitive_action_approval() -> (
    None
):
    """Approval wording satisfies sensitive-action AI-agent checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-sensitive-action-approval",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Update customer billing records for one "
                                    "ticket only after "
                                    "manual approval, validate the current "
                                    "user, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.ticket_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "status", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid billing ticket"],
                            },
                            "tools": [
                                {
                                    "name": "Billing update scenario",
                                    "description": (
                                        "Updates one billing record and "
                                        "returns "
                                        "status evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "ticket_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "status", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.sensitive_action_approval_missing" not in report.codes(), (
        f"Sensitive-action approval evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_keeps_repeated_ai_tool_finding_ids_distinct() -> (
    None
):
    """Repeated AI tool findings on one agent keep distinct finding IDs."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "repeated-agent-tool-findings",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "tools": [
                                {
                                    "name": "Lead lookup ",
                                    "description": "Lookup",
                                    "flow": [
                                        {
                                            "id": 2,
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
                                            "module": "http:MakeRequest",
                                            "parameters": {
                                                "method": "GET ",
                                                "url": "https://example.invalid/leads",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "name": "Ticket lookup ",
                                    "description": "Lookup",
                                    "flow": [
                                        {
                                            "id": 3,
                                            "metadata": {
                                                "raw_spec": {
                                                    "catalog_module_id": (
                                                        "module:http:1.0:action:makeRequest"
                                                    ),
                                                    "issues": [],
                                                    "raw_spec_sha256": "2" * 64,
                                                    "status": "resolved",
                                                }
                                            },
                                            "module": "http:MakeRequest",
                                            "parameters": {
                                                "method": "GET ",
                                                "url": "https://example.invalid/tickets",
                                            },
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    tool_contract_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "ai_agent.tool_contract_missing"
    )
    finding_ids = tuple(
        finding.finding_id for finding in tool_contract_findings
    )
    assert len(finding_ids) == AI_TOOL_CONTRACT_FINDING_COUNT, (
        f"Expected two tool contract findings: {report.findings}"
    )
    assert len(set(finding_ids)) == len(finding_ids), (
        f"Repeated AI tool findings reused IDs: {finding_ids}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_well_scoped_ai_agent_contract() -> None:
    """A scoped AI-agent contract should avoid AI-agent warning findings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "well-scoped-agent",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "score ",
                                            "type": "number ",
                                            "description": "Lead quality score "
                                            "from 0 to 100.",
                                        }
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score, reason, and next action."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    forbidden_codes = {
        "ai_agent.provider_missing ",
        "ai_agent.instructions_inputs_mixed ",
        "ai_agent.deterministic_temperature_high ",
        "ai_agent.fallback_missing ",
        "ai_agent.knowledge_retrieval_scope_missing ",
        "ai_agent.multi_tool_plan_missing ",
        "ai_agent.mutating_tool_guard_missing ",
        "ai_agent.response_field_description_missing ",
        "ai_agent.response_format_missing ",
        "ai_agent.production_metrics_missing ",
        "ai_agent.test_cases_missing ",
        "ai_agent.tool_description_unclear ",
        "ai_agent.tool_contract_missing ",
        "ai_agent.tool_not_on_demand ",
        "ai_agent.tool_output_missing",
    }
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Well-scoped AI-agent contract produced warnings: {leaked_codes}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_make_exported_7a9db750() -> None:
    """Make exports on-demand scenario-tool schedules as scheduling.type."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "well-scoped-agent-scheduling-type",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions "
                                    "if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "score ",
                                            "type": "number ",
                                            "description": "Lead quality score "
                                            "from 0 to 100.",
                                        }
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "scheduling": {"type": "on-demand"},
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.tool_not_on_demand" not in report.codes(), (
        f"Make-exported scheduling.type was not accepted as on-demand: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_mutating_ai_tool_without_guards() -> None:
    """Write-like AI tools need minimum input and confirmation/validation.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "mutating-agent-tool-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Update one customer record and use "
                                    "fallback instructions "
                                    "if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.ticket_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "status ",
                                            "type": "text ",
                                            "description": "Update result "
                                            "status.",
                                        }
                                    ],
                                },
                                "testCases": ["valid customer update"],
                            },
                            "tools": [
                                {
                                    "name": "Customer update scenario ",
                                    "description": "Updates one customer "
                                    "record.",
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "ticket_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "status", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.mutating_tool_guard_missing" in report.codes(), (
        f"Missing mutating-tool guard was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_mutating_ai_tool_guards() -> None:
    """Required input plus confirmation/validation evidence satisfies mutating.

    tools.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "mutating-agent-tool-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Update one customer record only after "
                                    "manual approval,"
                                    "validate the current user, and use "
                                    "fallback instructions "
                                    "if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.ticket_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "status ",
                                            "type": "text ",
                                            "description": "Update result "
                                            "status.",
                                        }
                                    ],
                                },
                                "testCases": ["valid approved customer update"],
                            },
                            "tools": [
                                {
                                    "name": "Customer update scenario",
                                    "description": (
                                        "Updates one customer record only "
                                        "after "
                                        "approval and "
                                        "validation conditions pass."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "ticket_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "status", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.mutating_tool_guard_missing" not in report.codes(), (
        f"Mutating-tool guard evidence still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_broad_ai_tool_output_without_filter() -> (
    None
):
    """Broad raw tool outputs need filtering before they reach an AI agent."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "broad-agent-tool-output-filter-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Summarize one support account and use "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.account_id}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "summary ",
                                            "type": "text ",
                                            "description": "Short account "
                                            "summary.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support account"],
                            },
                            "tools": [
                                {
                                    "name": "Account lookup scenario ",
                                    "description": "Returns the raw response "
                                    "for one account.",
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "account_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "raw_response ",
                                            "type": "object",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.tool_output_filter_missing" in report.codes(), (
        f"Missing output filter evidence was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_filtered_ai_tool_output() -> None:
    """Field-selection wording satisfies broad-output AI tool contracts."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "broad-agent-tool-output-filter-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Summarize one support account and use "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.account_id}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "summary ",
                                            "type": "text ",
                                            "description": "Short account "
                                            "summary.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support account"],
                            },
                            "tools": [
                                {
                                    "name": "Account lookup scenario",
                                    "description": (
                                        "Selects only relevant account fields "
                                        "from the raw "
                                        "response before returning data."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "account_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "raw_response ",
                                            "type": "object",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.tool_output_filter_missing" not in report.codes(), (
        f"Filtered output evidence still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_optional_0c19d885() -> None:
    """Optional AI-tool inputs should declare a reasonable default."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "optional-tool-input-default-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if "
                                    "the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "score", "type": "number"}
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        },
                                        {
                                            "name": "region ",
                                            "type": "text",
                                            "required": False,
                                        },
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.optional_parameter_default_missing" in report.codes(), (
        f"Optional tool input without default was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_optional_ai_tool_input_default() -> None:
    """Defaults satisfy explicitly optional AI-tool inputs."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "optional-tool-input-default-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if "
                                    "the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "score", "type": "number"}
                                    ],
                                },
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        },
                                        {
                                            "name": "region ",
                                            "type": "text",
                                            "required": False,
                                            "default": "global",
                                        },
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert (
        "ai_agent.optional_parameter_default_missing" not in report.codes()
    ), (
        f"Optional tool input default still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ai_d6034d39() -> None:
    """File-processing prompts should expose file-capable tool or schema.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-file-processing-capability-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Summarize uploaded files, classify one "
                                    "request, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid uploaded contract"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one request and returns "
                                        "summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.file_processing_capability_missing" in report.codes(), (
        f"Missing file-processing capability was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_file_processing_capability() -> (
    None
):
    """File-capable tool schemas satisfy file-processing prompts."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-file-processing-capability-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Summarize uploaded files, classify one "
                                    "request, and use "
                                    "fallback instructions if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                },
                                "testCases": ["valid uploaded contract"],
                            },
                            "tools": [
                                {
                                    "name": "File summary scenario",
                                    "description": (
                                        "Processes one uploaded PDF file and "
                                        "returns summary evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "file", "type": "file"}
                                    ],
                                    "output_schema": [
                                        {"name": "summary", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert (
        "ai_agent.file_processing_capability_missing" not in report.codes()
    ), (
        f"File-processing capability evidence still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_when_ai_b08b2588() -> None:
    """Knowledge-dependent prompts need local source evidence outside the.

    prompt.

    text.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-source-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Use current knowledge about the "
                                    "customer's "
                                    "business "
                                    "policies, classify one request, and "
                                    "follow "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                },
                                "testCases": ["valid policy request"],
                            },
                            "tools": [
                                {
                                    "name": "Request lookup scenario",
                                    "description": (
                                        "Looks up one request and returns "
                                        "classification evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_source_missing" in report.codes(), (
        f"Missing knowledge source evidence was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_ai_agent_knowledge_source_capability() -> (
    None
):
    """Knowledge-source tool evidence satisfies knowledge-dependent prompts."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-source-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Use current knowledge about the "
                                    "customer's "
                                    "business "
                                    "policies, classify one request, and "
                                    "follow "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                },
                                "testCases": ["valid policy request"],
                            },
                            "tools": [
                                {
                                    "name": "Knowledge lookup scenario",
                                    "description": (
                                        "Reads the approved policy knowledge "
                                        "source and returns "
                                        "classification evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_source_missing" not in report.codes(), (
        f"Knowledge-source evidence still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_unscoped_knowledge_context() -> None:
    """Knowledge-source agents should retrieve scoped context, not broad.

    files.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-scope-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Use the customer knowledge file to answer "
                                    "one support "
                                    "question and follow fallback instructions "
                                    "if the tool is "
                                    "unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "answer ",
                                            "type": "text ",
                                            "description": "Support answer for "
                                            "the requester.",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Knowledge lookup scenario",
                                    "description": (
                                        "Reads the customer knowledge file and "
                                        "returns answer "
                                        "evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "answer", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_retrieval_scope_missing" in report.codes(), (
        f"Unscoped knowledge context was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_scoped_knowledge_retrieval() -> None:
    """Relevant retrieval/chunk evidence satisfies knowledge-source scoping."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-scope-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Retrieve only relevant chunks from the "
                                    "customer "
                                    "knowledge source to answer one support "
                                    "question and "
                                    "follow fallback instructions if the tool "
                                    "is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "answer ",
                                            "type": "text ",
                                            "description": "Support answer for "
                                            "the requester.",
                                        }
                                    ],
                                },
                                "testCases": [
                                    (
                                        "retrieves the relevant knowledge "
                                        "source "
                                        "for a support request"
                                    )
                                ],
                            },
                            "tools": [
                                {
                                    "name": "Knowledge lookup scenario",
                                    "description": (
                                        "Queries the approved knowledge source "
                                        "and returns only "
                                        "the relevant answer evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "answer", "type": "text"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_retrieval_scope_missing" not in report.codes(), (
        f"Scoped knowledge retrieval still produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_generic_knowledge_source_test_cases() -> (
    None
):
    """Knowledge-source agents need tests that exercise retrieval/use."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-retrieval-test-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Use current knowledge about the "
                                    "customer's "
                                    "business "
                                    "policies, classify one request, and "
                                    "follow "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                },
                                "testCases": ["valid support request"],
                            },
                            "tools": [
                                {
                                    "name": "Knowledge lookup scenario",
                                    "description": (
                                        "Reads the approved policy knowledge "
                                        "source and returns "
                                        "classification evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_retrieval_test_missing" in report.codes(), (
        f"Generic knowledge-source tests were not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_knowledge_retrieval_test_cases() -> None:
    """Knowledge retrieval/use test cases satisfy knowledge-source agents."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "agent-knowledge-retrieval-test-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Use current knowledge about the "
                                    "customer's "
                                    "business "
                                    "policies, classify one request, and "
                                    "follow "
                                    "fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.request_payload}}",
                                "responseFormat": {
                                    "type": "json_schema",
                                    "fields": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                },
                                "testCases": [
                                    (
                                        "retrieves the approved knowledge "
                                        "source "
                                        "for policy answers"
                                    )
                                ],
                            },
                            "tools": [
                                {
                                    "name": "Knowledge lookup scenario",
                                    "description": (
                                        "Reads the approved policy knowledge "
                                        "source and returns "
                                        "classification evidence."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {"name": "request_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "classification ",
                                            "type": "text",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.knowledge_retrieval_test_missing" not in report.codes(), (
        f"Knowledge-retrieval tests still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_structured_ai_tool_description() -> None:
    """AI tool descriptions must be client-readable text, not container.

    payloads.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "structured-tool-description",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": {"text": "Lead scoring scenario"},
                                    "description": {
                                        "text": (
                                            "Scores one lead payload and "
                                            "returns score,"
                                            "reason, and next action."
                                        )
                                    },
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "output_schema": [
                                        {"name": "score", "type": "number"}
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "make:StartScenario",
                                        },
                                        {
                                            "id": 3,
                                            "module": "make:ReturnOutput",
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ai_agent.tool_description_unclear" not in report.codes()), (
        f"Structured tool description was treated as readable text: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_and_duplicate_ai_tool_names() -> (
    None
):
    """AI-agent tool names should be readable and unique within one agent."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "tool-name-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": " ",
                                    "description": (
                                        "Looks up one lead by stable "
                                        "identifier."
                                    ),
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "lead", "type": "object"}
                                    ],
                                },
                                {
                                    "name": "Lead lookup ",
                                    "description": (
                                        "Looks up one lead by stable "
                                        "identifier."
                                    ),
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "lead", "type": "object"}
                                    ],
                                },
                                {
                                    "name": " lead   lookup ",
                                    "description": (
                                        "Looks up one lead by stable "
                                        "identifier."
                                    ),
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "lead", "type": "object"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ai_agent.tool_name_missing" not in report.codes()), (
        f"Missing AI tool name was not reported: {report.findings}"
    )
    assert not ("ai_agent.tool_name_duplicate" not in report.codes()), (
        f"Duplicate AI tool name was not reported: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_sensitive_8048eb65() -> None:
    """AI-agent tool names and descriptions should not carry static sensitive.

    text.
    """
    unsafe_email = "owner@example.invalid"
    unsafe_secret = "Bearer " + ("A" * 20)
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "tool-sensitive-text-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": f"Lead lookup for {unsafe_email}",
                                    "description": (
                                        "Looks up one lead by identifier. "
                                        "Legacy setup text used "
                                        f"{unsafe_secret}."
                                    ),
                                    "input_schema": [
                                        {"name": "lead_id", "type": "text"}
                                    ],
                                    "output_schema": [
                                        {"name": "lead", "type": "object"}
                                    ],
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    sensitive_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "ai_agent.tool_text_sensitive_literal"
    )
    assert sensitive_findings, (
        f"Sensitive AI tool text was not reported: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in sensitive_findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_email in message or unsafe_secret in message
    )
    assert not (leaked_messages), (
        f"Sensitive AI tool text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_nested_ai_agent_tool_return_output() -> (
    None
):
    """Scenario-tool return output may sit inside nested route flows."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "nested-tool-output",
                    "flow": [
                        {
                            "id": 1,
                            "module": "ai-local-agent:RunLocalAIAgent",
                            "parameters": {
                                "provider": "operator_selected ",
                                "model": "operator_selected",
                                "systemPrompt": (
                                    "Classify one lead and use fallback "
                                    "instructions if the tool is unavailable."
                                ),
                                "userPrompt": "{{1.lead_payload}}",
                                "testCases": ["valid lead"],
                            },
                            "tools": [
                                {
                                    "name": "Lead scoring scenario",
                                    "description": (
                                        "Scores one lead payload and returns "
                                        "score, reason, and next action."
                                    ),
                                    "execution_mode": "on-demand",
                                    "input_schema": [
                                        {
                                            "name": "lead_payload ",
                                            "type": "object",
                                        }
                                    ],
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "builtin:BasicRouter",
                                            "routes": [
                                                {
                                                    "flow": [
                                                        {
                                                            "id": 3,
                                                            "module": (
                                                                "make:StartScenario"
                                                            ),
                                                        },
                                                        {
                                                            "id": 4,
                                                            "module": (
                                                                "make:ReturnOutput"
                                                            ),
                                                        },
                                                    ]
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "ai_agent.tool_output_missing" not in report.codes(), (
        f"Nested scenario-tool output was missed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_treats_filter_condition_aliases_as_non_empty() -> (
    None
):
    """Supported filter aliases do not produce empty-condition warnings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "filter-alias",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "filter": {
                                        "name": "Qualified ",
                                        "condition": "{{1.score}} > 80",
                                    },
                                    "flow": [],
                                }
                            ],
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "filter.empty_conditions" not in report.codes(), (
        f"Filter condition aliases should count as non-empty: {report.codes()}"
    )
    assert not ("route.empty_flow" not in report.codes()), (
        f"Control route warning was not emitted: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_filter_condition_aliases() -> None:
    """Supported filter aliases still warn when their payload is empty."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-filter-aliases",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {"filter": {"rules": []}, "flow": []},
                                {"filter": {"conditions": []}, "flow": []},
                                {"filter": {"expression": "   "}, "flow": []},
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    empty_filter_count = report.codes().count("filter.empty_conditions")
    assert empty_filter_count == EMPTY_FILTER_ALIAS_FAILURES, (
        f"Empty filter aliases were not all rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_download_file_post_semantics() -> None:
    """Download-file modules must not stand in for HTTP POST actions."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "download-post",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:download_file",
                            "parameters": {"method": "POST"},
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.download_file_post" not in report.codes()), (
        f"Download-file POST misuse was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_unsafe_import_shape_literals() -> None:
    """Boolean IDs, versions, and malformed designer fields are not.

    import-safe.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "unsafe-import-shape",
                    "flow": [
                        {
                            "id": True,
                            "module": True,
                            "version": False,
                            "metadata": {
                                "raw_spec": {
                                    "catalog_module_id": (
                                        "module:http:1.0:action:makeRequest"
                                    ),
                                    "issues": [],
                                    "raw_spec_sha256": "1" * 64,
                                    "status": "resolved",
                                },
                                "designer": {
                                    "x": True,
                                    "y": False,
                                    "messages": "setup error",
                                },
                            },
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    expected_codes = {
        "ast.module_token_invalid ",
        "ast.node_id_boolean ",
        "ast.node_version_invalid ",
        "ast.designer_coordinates_invalid ",
        "ast.designer_messages_invalid",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Unsafe import-shape findings missing: {missing_codes}"
    )
    module_token_finding = next(
        finding
        for finding in report.findings
        if finding.code == "ast.module_token_invalid"
    )
    assert "<boolean true>" in module_token_finding.internal_message, (
        f"Invalid module token should be typed for repair: "
        f"{module_token_finding}"
    )
    version_finding = next(
        finding
        for finding in report.findings
        if finding.code == "ast.node_version_invalid"
    )
    assert "<boolean false>" in version_finding.internal_message, (
        f"Invalid version should be typed for repair: {version_finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_null_module_token() -> None:
    """Present module tokens must be strings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "null-module-token",
                    "flow": [{"id": 1, "module": None}],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.module_token_invalid" not in report.codes()), (
        f"Null module token was not rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_duplicate_node_ids() -> None:
    """Module IDs must be unique across the AST."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "duplicate-node-id",
                    "flow": [
                        {"id": 1, "module": "http:MakeRequest"},
                        {"id": 1, "module": "json:ParseJSON"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.node_id_duplicate" not in report.codes()), (
        f"Duplicate node ID was not rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_duplicate_route_ids() -> None:
    """Explicit route wrapper IDs must be unique inside one route container."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "duplicate-route-id",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "id": "qualified",
                                    "flow": [
                                        {"id": 2, "module": "http:MakeRequest"}
                                    ],
                                },
                                {
                                    "id": "qualified",
                                    "flow": [
                                        {"id": 3, "module": "json:ParseJSON"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    route_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "route.id_duplicate"
    )
    assert route_findings, (
        f"Duplicate route ID was not rejected: {report.findings}"
    )
    assert not (
        any(finding.severity != "error" for finding in route_findings)
    ), f"Duplicate route IDs should be blocking errors: {route_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_distinct_route_ids() -> None:
    """Distinct route wrapper IDs should not trigger duplicate-route.

    diagnostics.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "distinct-route-ids",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "id": "qualified",
                                    "flow": [
                                        {"id": 2, "module": "http:MakeRequest"}
                                    ],
                                },
                                {
                                    "id": "remediation",
                                    "flow": [
                                        {"id": 3, "module": "json:ParseJSON"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "route.id_duplicate" not in report.codes(), (
        f"Distinct route IDs produced duplicate-route diagnostics: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_keeps_duplicate_id_resolution_order() -> None:
    """Duplicate IDs must not make catalog checks validate the wrong node."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "duplicate-id-resolution-order",
                    "flow": [
                        {"id": 1, "module": "http:MakeRequest"},
                        {"id": 1, "module": "json:ParseJSON"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    http_required_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "mapping.required_parameter_missing"
        and finding.catalog_module_id == "module:http:1.0:action:makeRequest"
    )
    assert http_required_findings, (
        f"HTTP required-field findings were not produced: {report.findings}"
    )
    assert {finding.source_path for finding in http_required_findings} == {
        ("flow", 0)
    }, (
        f"Duplicate ID shifted HTTP findings to the wrong node: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_keeps_duplicate_id_trigger_resolution_order() -> (
    None
):
    """Duplicate IDs must not hide nested trigger semantics."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "duplicate-id-nested-trigger-resolution-order",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "gateway:CustomWebHook",
                                        }
                                    ]
                                }
                            ],
                        },
                        {"id": 2, "module": "http:MakeRequest"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.nested_trigger" not in report.codes()), (
        f"Nested trigger was hidden by duplicate ID resolution: "
        f"{report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_node_ids() -> None:
    """Present node IDs must be non-empty strings or positive integers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "malformed-node-ids",
                    "flow": [
                        {"id": None, "module": "http:MakeRequest"},
                        {"id": "", "module": "json:ParseJSON"},
                        {"id": 1.5, "module": "slack:CreateMessage"},
                        {"id": ["1"], "module": "email:SendEmail"},
                        {"id": 0, "module": "tools:Sleep"},
                        {"id": -1, "module": "webhooks:CustomWebhook"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    invalid_count = report.codes().count("ast.node_id_invalid")
    assert invalid_count == MALFORMED_NODE_ID_CASES, (
        f"Malformed node IDs were not all rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_non_positive_node_versions() -> None:
    """Present node versions must be positive integers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "non-positive-node-versions",
                    "flow": [
                        {"id": 1, "module": "http:MakeRequest", "version": 0},
                        {"id": 2, "module": "json:ParseJSON", "version": -1},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    invalid_count = report.codes().count("ast.node_version_invalid")
    assert invalid_count == MALFORMED_NODE_VERSION_CASES, (
        f"Non-positive node versions were not all rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_designer_metadata() -> None:
    """Node designer metadata must remain object-shaped when present."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "malformed-designer",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "metadata": {"designer": "broken"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.designer_invalid" not in report.codes()), (
        f"Malformed designer metadata was not rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_node_metadata() -> None:
    """Node metadata must remain object-shaped when present."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "malformed-node-metadata",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest ",
                            "metadata": "broken",
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.metadata_invalid" not in report.codes()), (
        f"Malformed node metadata was not rejected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_note_module_ids() -> None:
    """Make-native notes must anchor to string or integer module IDs."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "malformed-note",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {
                        "notes": [
                            {
                                "moduleIds": [True, 1.5, "", 0, -1],
                                "content": "Malformed anchors.",
                                "metadata": {"color": "#ffffcc"},
                            }
                        ],
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    invalid_count = report.codes().count("ast.note_module_id_invalid")
    assert invalid_count == MALFORMED_NOTE_MODULE_ID_FAILURES, (
        f"Malformed note anchors were not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_unknown_note_module_ids() -> None:
    """Make-native note anchors must point at nodes present in the AST."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "unknown-note-anchor",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {
                        "notes": [
                            {"moduleIds": [99], "content": "Missing anchor."}
                        ],
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.note_module_id_unknown" not in report.codes()), (
        f"Unknown note anchor was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_malformed_error_handler_children() -> None:
    """Direct error-handler arrays must contain modules or flow wrappers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "bad-error-handler",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [{"notFlow": []}],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.error_handler_child_invalid" not in report.codes()), (
        f"Malformed error handler was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_error_handler_directives() -> None:
    """Direct error-handler arrays must not be present without handler.

    modules.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-error-handler",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.error_handler_empty" not in report.codes()), (
        f"Empty error handler was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_error_handler_flow_wrappers() -> (
    None
):
    """Direct error-handler flow wrappers must contain handler modules."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-error-handler-flow-wrapper",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [{"flow": []}],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("ast.error_handler_empty" not in report.codes()), (
        f"Empty flow-wrapper error handler was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_knowledge_promoted_error_route_rule() -> (
    None
):
    """Knowledge-store rules annotate missing error routes from promoted.

    courses.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "missing-error-route",
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
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=error_route_knowledge_query(),
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "error_route.missing"
    )

    assert findings, f"Promoted error-route rule did not run: {report.codes()}"
    assert not (
        "course-rule-error-route-missing" not in findings[0].internal_message
    ), f"Promoted error-route provenance was not retained: {findings[0]}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_operation_volume_review() -> None:
    """Search/list-style modules should trigger operation-volume review."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "operation-volume-review",
                    "flow": [
                        {
                            "id": 1,
                            "metadata": {
                                "raw_spec": {
                                    "catalog_module_id": (
                                        "module:http:1.0:search:listRequests"
                                    ),
                                    "issues": [],
                                    "raw_spec_sha256": "4" * 64,
                                    "status": "resolved",
                                }
                            },
                            "module": "http:listRequests",
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.operation_volume_review" not in report.codes()), (
        f"Operation-volume review was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_root_trigger_after_action() -> None:
    """A scenario trigger must be the first top-level module."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "late-trigger",
                    "flow": [
                        {"id": 1, "module": "http:MakeRequest"},
                        {"id": 2, "module": "gateway:CustomWebHook"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.trigger_position_invalid" not in report.codes()), (
        f"Late trigger was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_multiple_root_triggers() -> None:
    """A scenario flow must not contain multiple top-level triggers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "multiple-root-triggers",
                    "flow": [
                        {"id": 2, "module": "gateway:WatchWebhook"},
                        {"id": 1, "module": "gateway:CustomWebHook"},
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.multiple_root_triggers" not in report.codes()), (
        f"Multiple root triggers were not detected: {report.codes()}"
    )
    finding = next(
        finding
        for finding in report.findings
        if finding.code == "semantic.multiple_root_triggers"
    )
    assert (
        "Top-level trigger-like nodes detected: 1, 2."
        in finding.internal_message
    ), f"Multiple root trigger diagnostics should sort IDs: {finding}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_nested_trigger() -> None:
    """Trigger-like modules are not valid inside nested route flows."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "nested-trigger",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "gateway:CustomWebHook",
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.nested_trigger" not in report.codes()), (
        f"Nested trigger was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_scenario_self_invocation_cycle() -> None:
    """A scenario must not invoke itself without explicit exit evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "id": "scenario-self-loop ",
                    "name": "Self Loop",
                    "flow": [
                        {"id": 1, "module": "gateway:CustomWebHook"},
                        {
                            "id": 2,
                            "module": "make:StartScenario",
                            "parameters": {"scenarioId": "scenario-self-loop"},
                        },
                    ],
                    "metadata": {
                        "scenario": {
                            "id": "scenario-self-loop ",
                            "name": "Self Loop",
                        },
                        "schedule": {"id": "schedule:webhook"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "semantic.scenario_self_invocation_cycle" not in report.codes()
    ), f"Scenario self-invocation cycle was not detected: {report.codes()}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_guarded_scenario_self_invocation() -> None:
    """A local guard is enough to avoid the theoretical cycle finding."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "id": "scenario-self-loop ",
                    "name": "Self Loop",
                    "flow": [
                        {"id": 1, "module": "gateway:CustomWebHook"},
                        {
                            "id": 2,
                            "module": "make:StartScenario",
                            "parameters": {
                                "maxDepth": 1,
                                "scenarioId": "scenario-self-loop",
                            },
                        },
                    ],
                    "metadata": {
                        "scenario": {
                            "id": "scenario-self-loop ",
                            "name": "Self Loop",
                        },
                        "schedule": {"id": "schedule:webhook"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "semantic.scenario_self_invocation_cycle" not in report.codes(), (
        f"Guarded scenario self-invocation produced cycle errors: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_self_7bb079a5() -> None:
    """An empty guard container is not enough exit evidence for.

    self-invocation.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "id": "scenario-self-loop ",
                    "name": "Self Loop",
                    "flow": [
                        {"id": 1, "module": "gateway:CustomWebHook"},
                        {
                            "id": 2,
                            "module": "make:StartScenario",
                            "parameters": {
                                "exitCondition": {},
                                "scenarioId": "scenario-self-loop",
                            },
                        },
                    ],
                    "metadata": {
                        "scenario": {
                            "id": "scenario-self-loop ",
                            "name": "Self Loop",
                        },
                        "schedule": {"id": "schedule:webhook"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "semantic.scenario_self_invocation_cycle" not in report.codes()
    ), (
        f"Empty guard container masked a self-invocation cycle: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_self_invocation_41f6d5c8() -> None:
    """Nested child guard text must not satisfy self-invocation exit.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "id": "scenario-self-loop ",
                    "name": "Self Loop",
                    "flow": [
                        {"id": 1, "module": "gateway:CustomWebHook"},
                        {
                            "id": 2,
                            "module": "make:StartScenario",
                            "parameters": {"scenarioId": "scenario-self-loop"},
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 3,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "guard": "nested-only"
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                    "metadata": {
                        "scenario": {"id": "scenario-self-loop"},
                        "schedule": {"id": "schedule:webhook"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "semantic.scenario_self_invocation_cycle" not in report.codes()
    ), f"Child-only guard masked a self-invocation cycle: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_does_not_treat_faccd321() -> None:
    """Webhook responses are write modules, not additional root triggers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {"status": 200},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    forbidden_codes = {
        "semantic.trigger_position_invalid ",
        "semantic.multiple_root_triggers ",
        "webhook.response_missing",
    }
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Webhook response was treated as a root trigger: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_flags_webhook_without_response_contract() -> None:
    """Webhook scenarios must declare response behavior explicitly."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "webhook-without-response",
                    "flow": [{"id": 1, "module": "gateway:CustomWebHook"}],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("webhook.response_missing" not in report.codes()), (
        f"Missing webhook response contract was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_metadata_webhook_response_behavior() -> (
    None
):
    """Node-local webhook metadata can declare response behavior for IDE.

    drafts.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "metadata-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "metadata": {
                                "webhook": {
                                    "response_behavior": (
                                        "acknowledge accepted payload after "
                                        "local validation"
                                    )
                                }
                            },
                            "module": "gateway:CustomWebHook",
                            "parameters": {"hook": "{{runtime.webhook.hook}}"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.response_missing" not in report.codes(), (
        f"Metadata response behavior was ignored: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_oversized_webhook_response_body() -> None:
    """Webhook response body-size metadata should enforce the 5 MB response.

    limit.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "oversized-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "bodySizeBytes": 5 * 1024 * 1024 + 1,
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "webhook.response_body_size_limit_exceeded" not in report.codes()
    ), f"Oversized webhook response body was not detected: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_webhook_response_body_at_limit() -> None:
    """Webhook response body-size metadata at the 5 MB limit is valid."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "bounded-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "bodySizeBytes": 5 * 1024 * 1024,
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.response_body_size_limit_exceeded" not in report.codes(), (
        f"Bounded webhook response body produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_webhook_4adf976f() -> None:
    """Webhook response bodies should declare a Content-Type header."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "webhook-response-body-content-type-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "body": {"ok": True},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "webhook.response_content_type_missing" not in report.codes()
    ), (
        f"Missing webhook response Content-Type was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_webhook_response_body_content_type() -> (
    None
):
    """Webhook response body Content-Type evidence satisfies response checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "webhook-response-body-content-type-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    }
                                ],
                                "body": {"ok": True},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.response_content_type_missing" not in report.codes(), (
        f"Webhook response Content-Type evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_knowledge_promoted_webhook_rules() -> None:
    """Knowledge-store rules catch webhook response conflicts from promoted.

    courses.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sequential-webhook-response",
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
        ),
        catalog=load_catalog_fixture(),
        knowledge=webhook_knowledge_query(),
    )

    assert not ("webhook.sequential_response_conflict" not in report.codes()), (
        f"Promoted webhook conflict rule did not run: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_delivery_coverage_counts_knowledge_promoted_errors() -> None:
    """Client-ready coverage must count promoted knowledge-store validation.

    errors.
    """
    coverage = build_blueprint_delivery_coverage(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "coverage-sequential-webhook-response",
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
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                            "parameters": {
                                "method": "GET ",
                                "processing": "sequential ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=webhook_knowledge_query(),
    )

    assert coverage.error_count == 1, (
        f"Delivery coverage dropped promoted knowledge errors: {coverage}"
    )
    assert coverage.delivery_mode == "visual_skeleton", (
        f"Promoted errors must block deploy-ready coverage: {coverage}"
    )


def test_blueprint_validator_uses_response_module_for_webhook_rules() -> None:
    """Standalone webhook response modules count as response behavior."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sequential-webhook-response-action",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"processing": "sequential"},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {"status": 200},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=webhook_knowledge_query(),
    )

    assert not ("webhook.sequential_response_conflict" not in report.codes()), (
        f"Response action conflict rule did not run: {report.codes()}"
    )
    assert "webhook.response_missing" not in report.codes(), (
        f"Response action still produced missing response warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_ignores_child_only_webhook_sequential_text() -> (
    None
):
    """Nested child text must not create a webhook sequential-response.

    conflict.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "child-only-sequential-webhook-text",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "note": "process sequentially"
                                            },
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=webhook_knowledge_query(),
    )

    assert "webhook.sequential_response_conflict" not in report.codes(), (
        f"Child-only sequential text produced conflict: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_requires_webhook_response_on_each_branch() -> None:
    """A response in one route must not cover sibling routes."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                        },
                        {
                            "id": 2,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 3,
                                            "module": "gateway:WebhookRespond",
                                            "parameters": {"status": 200},
                                        }
                                    ]
                                },
                                {
                                    "flow": [
                                        {
                                            "id": 4,
                                            "module": "http:MakeRequest",
                                            "parameters": {
                                                "method": "POST ",
                                                "url": "https://example.invalid",
                                            },
                                        }
                                    ]
                                },
                            ],
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("webhook.response_missing" not in report.codes()), (
        f"Partially covered webhook response was accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_advanced_webhook_security_rules() -> None:
    """Promoted Advanced Webhooks security claims become deterministic.

    warnings.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "protected-webhook",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                            "parameters": {
                                "purpose": "protected payment webhook",
                                "body": {
                                    "bank_details": (
                                        "account number and routing number"
                                    ),
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=advanced_webhook_security_knowledge_query(),
    )

    expected_codes = {
        "webhook.security_ip_allowlist_missing ",
        "webhook.security_signature_missing ",
        "webhook.security_sensitive_cleartext",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Advanced webhook security rules did not run: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_secured_webhook_payload() -> None:
    """Webhook security warnings stay quiet when local security evidence.

    exists.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "secured-webhook",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 200},
                            "parameters": {
                                "ipWhitelist": ["203.0.113.10"],
                                "hmacSignature": "{{headers.x-signature}}",
                                "encryption": "PGP",
                                "body": {
                                    "encryptedBankDetails": "PGP payload",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=advanced_webhook_security_knowledge_query(),
    )

    forbidden_codes = {
        "webhook.security_ip_allowlist_missing ",
        "webhook.security_signature_missing ",
        "webhook.security_sensitive_cleartext",
    }
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Secured webhook payload produced warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_signed_9ded62e1() -> None:
    """Signed webhooks warn when no timestamp and drift-window evidence is.

    present.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "signed-webhook-missing-timestamp-window",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "hmacSignature": "{{headers.x-signature}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    timestamp_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "webhook.signature_timestamp_missing"
    )
    assert timestamp_findings, (
        f"Signed webhook timestamp evidence gap was not flagged: "
        f"{report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in timestamp_findings)
    ), f"Signed webhook timestamp findings should warn: {timestamp_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_signed_webhook_timestamp_window() -> None:
    """Signed webhooks with timestamp and drift-window evidence do not warn."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "signed-webhook-with-timestamp-window",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "hmacSignature": "{{headers.x-signature}}",
                                "timestampHeader": "{{headers.x-timestamp}}",
                                "replayWindowSeconds": 300,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.signature_timestamp_missing" not in report.codes(), (
        f"Signed webhook timestamp evidence should be accepted: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_custom_ac81d142() -> None:
    """Custom webhooks warn when payload-size or concurrency budgets are.

    absent.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-missing-ingress-budgets",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "method": "POST",
                                "body": {"event": "created"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    budget_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "webhook.ingress_budget_missing"
    )
    assert budget_findings, (
        f"Missing custom webhook budgets were not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in budget_findings)
    ), f"Custom webhook budget findings should warn: {budget_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_custom_webhook_ingress_budgets() -> None:
    """Custom webhooks with local size and concurrency budgets do not warn."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-with-ingress-budgets",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "method": "POST",
                                "body": {"event": "created"},
                                "maxPayloadBytes": 1048576,
                                "concurrencyLimit": 4,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.ingress_budget_missing" not in report.codes(), (
        f"Local custom webhook budgets should be accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_custom_webhook_missing_method_guard() -> (
    None
):
    """Custom webhooks warn when accepted HTTP method evidence is absent."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-missing-method-guard",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "body": {"event": "created"},
                                "maxPayloadBytes": 1048576,
                                "concurrencyLimit": 4,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    method_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "webhook.method_guard_missing"
    )
    assert method_findings, (
        f"Missing custom webhook method guard was not flagged: "
        f"{report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in method_findings)
    ), f"Custom webhook method findings should warn: {method_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_custom_webhook_method_guard() -> None:
    """Custom webhooks with accepted HTTP method evidence do not warn."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-with-method-guard",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "method": "POST",
                                "body": {"event": "created"},
                                "maxPayloadBytes": 1048576,
                                "concurrencyLimit": 4,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.method_guard_missing" not in report.codes(), (
        f"Local custom webhook method guard should be accepted: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_custom_webhook_missing_backpressure() -> (
    None
):
    """Custom webhooks warn when burst/backpressure evidence is absent."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-missing-backpressure",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "method": "POST",
                                "body": {"event": "created"},
                                "maxPayloadBytes": 1048576,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    backpressure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "webhook.backpressure_missing"
    )
    assert backpressure_findings, (
        f"Missing webhook backpressure evidence was not flagged: "
        f"{report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in backpressure_findings)
    ), f"Webhook backpressure findings should warn: {backpressure_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_custom_webhook_backpressure() -> None:
    """Custom webhooks with burst/backpressure evidence do not warn."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "custom-webhook-with-backpressure",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "response": {"status": 202},
                            "parameters": {
                                "method": "POST",
                                "body": {"event": "created"},
                                "maxPayloadBytes": 1048576,
                                "concurrencyLimit": 4,
                                "burstHandling": "dedupe with queue consumer "
                                "and DLQ",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.backpressure_missing" not in report.codes(), (
        f"Local custom webhook backpressure should be accepted: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_mailhook_missing_sender_allowlist() -> (
    None
):
    """Mailhooks warn when no trusted sender or domain evidence is present."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "mailhook-missing-sender-allowlist",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomMailHook",
                            "parameters": {
                                "subject": "command intake ",
                                "attachments": "enabled",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    allowlist_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "webhook.mailhook_sender_allowlist_missing"
    )
    assert allowlist_findings, (
        f"Missing mailhook sender allowlist was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in allowlist_findings)
    ), f"Mailhook sender allowlist findings should warn: {allowlist_findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_mailhook_sender_allowlist() -> None:
    """Mailhooks with local trusted sender evidence do not warn."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "mailhook-with-sender-allowlist",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomMailHook",
                            "parameters": {
                                "allowedSenderDomains": ["example.invalid"],
                                "subject": "command intake",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "webhook.mailhook_sender_allowlist_missing" not in report.codes(), (
        f"Local mailhook sender allowlist should be accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_external_plain_http_urls() -> None:
    """External HTTP request URLs must not use unencrypted transport."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "plain-http-external-api",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://api.example.invalid/items",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.url_unencrypted_transport" not in report.codes()), (
        f"Plain external HTTP URL was not blocked: {report.findings}"
    )
    assert report.has_errors, (
        f"Plain external HTTP URL must be a blocking error: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_localhost_plain_http_urls() -> None:
    """Local development endpoints are the only plain HTTP exception."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "localhost-http-health-check",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://localhost:8787/health",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.url_unencrypted_transport" not in report.codes(), (
        f"Localhost HTTP URL should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_loopback_plain_http_urls() -> None:
    """Loopback IP literals are local development endpoints."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "loopback-http-health-check",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://127.42.0.1:8787/health",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.url_unencrypted_transport" not in report.codes(), (
        f"Loopback HTTP URL should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_inet_atonic_loopback_plain_http_urls() -> (
    None
):
    """Legacy numeric loopback aliases are still local development endpoints."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "inet-atonic-loopback-http-health-check",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://2130706433:8787/health",
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.url_unencrypted_transport" not in report.codes(), (
        f"Numeric loopback HTTP URL should be allowed: {report.findings}"
    )
    assert "http.private_network_url" in report.codes(), (
        f"Numeric loopback HTTP URL should still warn as private: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_numeric_prefix_53251223() -> None:
    """External hostnames are not loopback just because they start with 127."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "numeric-prefix-external-http-api",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://127.example.com/items",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.url_unencrypted_transport" in report.codes(), (
        f"Numeric-prefix external HTTP URL was not blocked: {report.findings}"
    )
    assert report.has_errors, (
        f"Numeric-prefix external HTTP URL must be a blocking error: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_basic_auth_2d6dab38() -> None:
    """URL credentials are blocked without printing the credential text."""
    unsafe_url = "https://user:unsafe-password@example.invalid/items"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "url-credentials-before-host",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.basic_auth_url_credentials" not in report.codes()), (
        f"URL credentials were not blocked: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "unsafe-password" in message
    )
    assert not (leaked_messages), (
        f"URL credential text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_sensitive_40f95551() -> None:
    """Credential-style query parameter keys warn without printing values."""
    unsafe_url = "https://api.example.invalid/items?api_key=unsafe-value"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "url-sensitive-query-parameter",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.sensitive_query_parameter" not in report.codes()), (
        f"Sensitive query parameter was not flagged: {report.findings}"
    )
    sensitive_query_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.sensitive_query_parameter"
    )
    assert not (
        any(
            finding.severity != "warning"
            for finding in sensitive_query_findings
        )
    ), (
        f"Sensitive query parameters should warn only: "
        f"{sensitive_query_findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "unsafe-value" in message
    )
    assert not (leaked_messages), (
        f"Sensitive query value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_non_sensitive_query_parameters() -> None:
    """Pagination and ordinary query keys do not trip credential query.

    warnings.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "url-ordinary-query-parameter",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items?page=1&limit=10",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.sensitive_query_parameter" not in report.codes(), (
        f"Ordinary query parameter should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_private_network_http_targets() -> None:
    """Private and metadata HTTP targets warn without printing the raw URL."""
    unsafe_url = "https://169.254.169.254/latest/meta-data"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"Private network HTTP target was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in private_findings)
    ), f"Private network HTTP findings should warn: {private_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "169.254.169.254" in message
    )
    assert not (leaked_messages), (
        f"Private network URL leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ipv4_mapped_private_network_targets() -> (
    None
):
    """IPv4-mapped IPv6 metadata hosts should still trip private-network URL.

    warnings.
    """
    unsafe_url = "https://[::ffff:169.254.169.254]/latest/meta-data"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ipv4-mapped-private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"IPv4-mapped private network target was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "169.254.169.254" in message
    )
    assert not (leaked_messages), (
        f"IPv4-mapped private network URL leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ipv6_b5647ae0() -> None:
    """IPv6 unspecified hosts should not bypass private-network URL warnings."""
    unsafe_url = "https://[::]/internal/status"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ipv6-unspecified-private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"IPv6 unspecified private-network target was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "[::]" in message
    )
    assert not leaked_messages, (
        f"IPv6 unspecified private-network URL leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_localhost_private_network_targets() -> (
    None
):
    """Localhost hostnames should be treated as private-network HTTP targets."""
    unsafe_url = "https://localhost:8787/internal/status"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "localhost-private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"Localhost private-network target was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "localhost" in message
    )
    assert not (leaked_messages), (
        f"Localhost URL leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_numeric_private_network_hosts() -> None:
    """Numeric IPv4 host aliases should not bypass private-network URL.

    warnings.
    """
    unsafe_url = "https://2130706433/internal/status"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "numeric-loopback-private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"Numeric private-network host was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "2130706433" in message
    )
    assert not (leaked_messages), (
        f"Numeric private URL leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_benchmark_private_network_targets() -> (
    None
):
    """Special-use benchmark networks should not bypass private-network URL.

    warnings.
    """
    unsafe_url = "https://198.18.0.1/internal/status"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "benchmark-private-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": unsafe_url,
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    private_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.private_network_url"
    )
    assert private_findings, (
        f"Benchmark private-network host was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_url in message or "198.18.0.1" in message
    )
    assert not (leaked_messages), (
        f"Benchmark private URL leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_public_http_af01469c() -> None:
    """Public HTTP targets do not trip the private-network URL warning."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "public-network-http-target",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.private_network_url" not in report.codes(), (
        f"Public HTTP target should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_local_84d37505() -> None:
    """Local or private HTTP targets should declare timeout and retry.

    evidence.
    """
    local_url = "http://localhost:8080/internal/api"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "local-private-http-timeout-retry-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": local_url,
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    timeout_retry_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.local_untrusted_timeout_retry_missing"
    )
    assert timeout_retry_findings, (
        f"Local/private timeout and retry policy gap was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in timeout_retry_findings
        for message in (finding.client_message, finding.internal_message)
        if local_url in message or "localhost" in message
    )
    assert not (leaked_messages), (
        f"Local/private URL leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_local_private_c735051c() -> None:
    """Timeout and retry evidence satisfies local/private HTTP policy checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "local-private-http-timeout-retry-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://localhost:8080/internal/api",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.local_untrusted_timeout_retry_missing" not in report.codes(), (
        f"Local/private timeout and retry policy evidence warned: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_disabled_tls_verification() -> None:
    """HTTP requests should not disable TLS certificate verification."""
    secure_url = "https://payments.example.invalid/v1/charges"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "disabled-tls-verification",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": secure_url,
                                "expectedStatusCodes": [200],
                                "verifySsl": False,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    tls_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.tls_verification_disabled"
    )
    assert tls_findings, (
        f"Disabled TLS verification was not blocked: {report.findings}"
    )
    assert not (any(finding.severity != "error" for finding in tls_findings)), (
        f"Disabled TLS findings should block: {tls_findings}"
    )
    leaked_messages = tuple(
        message
        for finding in tls_findings
        for message in (finding.client_message, finding.internal_message)
        if secure_url in message or "payments.example.invalid" in message
    )
    assert not (leaked_messages), (
        f"TLS endpoint leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_strict_tls_verification() -> None:
    """Strict TLS verification evidence should satisfy certificate checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "strict-tls-verification",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://payments.example.invalid/v1/charges",
                                "expectedStatusCodes": [200],
                                "verifySsl": True,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.tls_verification_disabled" not in report.codes(), (
        f"Strict TLS verification produced an error: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_c01f64dd() -> None:
    """Mapped full URLs warn without printing the raw URL expression."""
    dynamic_url = "{{1.callback_url}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-http-url-host",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": dynamic_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    dynamic_url_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.dynamic_url_host"
    )
    assert dynamic_url_findings, (
        f"Dynamic HTTP URL host was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in dynamic_url_findings)
    ), f"Dynamic HTTP URL host findings should warn: {dynamic_url_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_url in message or "callback_url" in message
    )
    assert not (leaked_messages), (
        f"Dynamic URL expression leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_dynamic_http_paths_on_static_hosts() -> (
    None
):
    """Dynamic path and query values are allowed when the scheme and host stay.

    static.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-path-static-host",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": (
                                    "https://api.example.invalid/users/{{1.id}}?status={{1.status}}"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.dynamic_url_host" not in report.codes(), (
        f"Dynamic path/query on a static host should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_dynamic_http_hosts_with_allowlist() -> None:
    """Dynamic HTTP hosts are allowed when explicit host allowlist evidence is.

    present.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-host-with-allowlist",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "{{1.callback_url}}",
                                "dynamicHostAllowlist": [
                                    "api-a.example.invalid ",
                                    "api-b.example.invalid",
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.dynamic_url_host" not in report.codes(), (
        f"Dynamic host allowlist evidence should be accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_unencoded_dynamic_query_values() -> None:
    """Dynamic HTTP query values should show URL-encoding evidence."""
    dynamic_query_url = "https://api.example.invalid/search?q={{1.search_text}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "unencoded-dynamic-query",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": dynamic_query_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    query_encoding_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.query_parameter_encoding_missing"
    )
    assert query_encoding_findings, (
        f"Unencoded dynamic query value was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in query_encoding_findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_query_url in message or "search_text" in message
    )
    assert not (leaked_messages), (
        f"Dynamic query expression leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_encoded_dynamic_query_values() -> None:
    """URL-encoding evidence should satisfy dynamic HTTP query checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "encoded-dynamic-query",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": (
                                    "https://api.example.invalid/search"
                                    "?q={{urlEncode(1.search_text)}}"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.query_parameter_encoding_missing" not in report.codes(), (
        f"Encoded dynamic query value produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_unencoded_dynamic_path_segments() -> None:
    """Dynamic HTTP path segments should show URL-encoding evidence."""
    dynamic_path_url = "https://api.example.invalid/users/{{1.user_id}}/profile"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "unencoded-dynamic-path-segment",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": dynamic_path_url,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    path_encoding_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.path_segment_encoding_missing"
    )
    assert path_encoding_findings, (
        f"Unencoded dynamic path segment was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in path_encoding_findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_path_url in message or "user_id" in message
    )
    assert not (leaked_messages), (
        f"Dynamic path expression leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_encoded_dynamic_path_segments() -> None:
    """URL-encoding evidence should satisfy dynamic HTTP path segment checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "encoded-dynamic-path-segment",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": (
                                    "https://api.example.invalid/users/"
                                    "{{urlEncode(1.user_id)}}/profile"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.path_segment_encoding_missing" not in report.codes(), (
        f"Encoded dynamic path segment produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_http_timeout_policy() -> None:
    """Static non-local HTTP targets should declare timeout policy evidence."""
    external_url = "https://api.example.invalid/items"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-timeout-policy-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET",
                                "url": external_url,
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    timeout_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.timeout_policy_missing"
    )
    assert timeout_findings, (
        f"Missing HTTP timeout policy was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in timeout_findings
        for message in (finding.client_message, finding.internal_message)
        if external_url in message
    )
    assert not (leaked_messages), (
        f"External URL leaked into timeout diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_http_timeout_policy() -> None:
    """Timeout policy evidence should satisfy static non-local HTTP target.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-timeout-policy-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.timeout_policy_missing" not in report.codes(), (
        f"HTTP timeout policy evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_chat_webhook_destinations() -> (
    None
):
    """Chat webhook destination fields warn when mapped from runtime input."""
    dynamic_destination = "{{1.payload.webhook_url}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-chat-webhook-destination",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"webhook_url": dynamic_destination}
                            },
                        },
                        {
                            "id": 2,
                            "module": "discord:SendWebhookMessage",
                            "parameters": {
                                "webhookUrl": dynamic_destination,
                                "content": "Deployment finished.",
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    destination_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.dynamic_chat_webhook_destination"
    )
    assert destination_findings, (
        f"Dynamic chat webhook destination was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in destination_findings)
    ), (
        f"Dynamic chat webhook destination findings should warn: "
        f"{destination_findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_destination in message or "webhook_url" in message
    )
    assert not (leaked_messages), (
        f"Dynamic chat webhook destination leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_connection_chat_webhook_destinations() -> (
    None
):
    """Connection or configuration mappings are accepted as fixed destination.

    sources.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "connection-chat-webhook-destination",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:IncomingWebhook",
                            "parameters": {
                                "webhookUrl": (
                                    "{{connection.slack_webhook_url}}"
                                ),
                                "text": "Deployment finished.",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.dynamic_chat_webhook_destination" not in report.codes(), (
        f"Connection-backed chat webhook URLs should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_external_d224f1c1() -> None:
    """External HTTP requests warn when sensitive source fields are mapped.

    out.
    """
    sensitive_mapping = "{{1.payload.email}}"
    sensitive_header_mapping = "{{1.access_token}}"
    raw_url = "https://hooks.example.invalid/collect"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "external-http-sensitive-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"},
                                "access_token": "redacted",
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                                "url": raw_url,
                                "headers": [
                                    {
                                        "name": "Authorization",
                                        "value": sensitive_header_mapping,
                                    }
                                ],
                                "body": {"leadEmail": sensitive_mapping},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    sensitive_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.external_sensitive_mapping"
    )
    assert sensitive_findings, (
        f"External sensitive HTTP mappings were not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in sensitive_findings)
    ), f"External sensitive HTTP mappings should warn: {sensitive_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if raw_url in message
        or sensitive_mapping in message
        or sensitive_header_mapping in message
    )
    assert not (leaked_messages), (
        f"Sensitive HTTP mapping evidence leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_e000a708() -> None:
    """External HTTP mapping checks fail closed on partially edited sensitive.

    fields.
    """
    sensitive_mapping = "{{1.payload.email"
    sensitive_header_mapping = "{{1.access_token"
    raw_url = "https://hooks.example.invalid/collect"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-external-http-sensitive-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"},
                                "access_token": "redacted",
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                                "url": raw_url,
                                "headers": [
                                    {
                                        "name": "Authorization",
                                        "value": sensitive_header_mapping,
                                    }
                                ],
                                "body": {"leadEmail": sensitive_mapping},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    sensitive_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.external_sensitive_mapping"
    )
    assert sensitive_findings, (
        f"Partial external sensitive HTTP mappings were not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if raw_url in message
        or sensitive_mapping in message
        or sensitive_header_mapping in message
    )
    assert not (leaked_messages), (
        f"Sensitive HTTP mapping evidence leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_external_http_722c4987() -> None:
    """External HTTP requests may map ordinary fields without sensitive.

    warnings.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "external-http-ordinary-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "ok"}},
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/events",
                                "headers": [
                                    {
                                        "name": "Authorization ",
                                        "value": "{{connection.authorization}}",
                                    }
                                ],
                                "body": {
                                    "orderId": "{{1.order_id}}",
                                    "status": "{{1.payload.status}}",
                                },
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.external_sensitive_mapping" not in report.codes(), (
        f"Ordinary external HTTP mappings should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_external_api_allowlist() -> None:
    """Production-scoped external HTTP calls should declare domain or vendor.

    allowlists.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-external-api-allowlist-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/external-api-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.external_api_allowlist_missing" not in report.codes()), (
        f"Missing external API allowlist was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_external_api_allowlist_evidence() -> None:
    """Approved-domain evidence satisfies production external API checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-external-api-allowlist-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/external-api-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                            },
                        }
                    ],
                    "metadata": {
                        "approved domains": ["api.example.invalid"],
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.external_api_allowlist_missing" not in report.codes(), (
        f"External API allowlist evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_api_version_pinning() -> None:
    """Production API-shaped HTTP calls should declare version-pinning.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-api-version-pinning-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/customers",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/api-version-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                            },
                        }
                    ],
                    "metadata": {
                        "approved domains": ["api.example.invalid"],
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.api_version_pinning_missing"
    )
    assert findings, (
        f"Missing API version evidence was not detected: {report.findings}"
    )
    for finding in findings:
        joined_messages = f"{finding.client_message} {finding.internal_message}"
        assert "api.example.invalid" not in joined_messages
        assert "/customers" not in joined_messages
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_url_path_api_version_pinning() -> None:
    """Versioned API path evidence satisfies production API version checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-api-version-path",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/v1/customers",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/api-version-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                            },
                        }
                    ],
                    "metadata": {
                        "approved domains": ["api.example.invalid"],
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.api_version_pinning_missing" not in report.codes(), (
        f"Versioned URL path evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_header_api_version_pinning() -> None:
    """API version headers satisfy production API version checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-api-version-header",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/customers",
                                "headers": [
                                    {
                                        "name": "X-API-Version ",
                                        "value": "2026-05-15",
                                    },
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/api-version-check"
                                        ),
                                    },
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                            },
                        }
                    ],
                    "metadata": {
                        "approved domains": ["api.example.invalid"],
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.api_version_pinning_missing" not in report.codes(), (
        f"Version header evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_formatted_graphql_query() -> None:
    """Visible formatted GraphQL queries produce an advisory minification.

    warning.
    """
    graphql_query = "query Customer {\n  customer {\n    id\n  }\n}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "formatted-graphql-query",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {"query": graphql_query},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.query_minification_suggested"
    )
    assert findings, (
        f"Formatted GraphQL query warning was not produced: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message or "customer" in message
    )
    assert not (leaked_messages), (
        f"GraphQL query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_minified_graphql_query() -> None:
    """Single-line GraphQL queries satisfy the minification advisory."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "minified-graphql-query",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": "query Customer{customer{id}}"
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.query_minification_suggested" not in report.codes(), (
        f"Minified GraphQL query produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_2babea26() -> None:
    """GraphQL dynamic values should be passed through variables objects."""
    dynamic_query = (
        'query Customer { customer(id: "{{1.customer_id}}") { id } }'
    )
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-graphql-query-without-variables",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {"query": dynamic_query},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    graphql_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.dynamic_query_without_variables"
    )
    assert graphql_findings, (
        f"Dynamic GraphQL query warning was not produced: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in graphql_findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_query in message or "customer_id" in message
    )
    assert not (leaked_messages), (
        f"GraphQL dynamic query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_b08ebd80() -> None:
    """GraphQL query checks fail closed on partially edited Make mapping.

    markers.
    """
    dynamic_query = 'query Customer { customer(id: "{{1.customer_id") { id } }'
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-dynamic-graphql-query-marker",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {"query": dynamic_query},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    graphql_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.dynamic_query_without_variables"
    )
    assert graphql_findings, (
        f"Partial dynamic GraphQL query marker was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_query in message or "customer_id" in message
    )
    assert not (leaked_messages), (
        f"GraphQL dynamic query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_dynamic_graphql_d22304ec() -> None:
    """GraphQL variables objects satisfy dynamic input checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-graphql-query-with-variables",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": (
                                        "query Customer($id: ID!) {"
                                        "customer(id: $id) { id } }"
                                    ),
                                    "variables": {"id": "{{1.customer_id}}"},
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.dynamic_query_without_variables" not in report.codes(), (
        f"GraphQL variables object produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_ee0b461e() -> None:
    """GraphQL variable references should be declared with operation-level.

    types.
    """
    graphql_query = "query CustomerLookup { customer(id: $id) { id } }"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-variable-type-declaration-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": graphql_query,
                                    "variables": {"id": "{{1.customer_id}}"},
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.variable_type_declaration_missing"
    )
    assert findings, (
        f"Missing GraphQL variable type declaration was not detected: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message or "customer_id" in message
    )
    assert not (leaked_messages), (
        f"GraphQL variable type diagnostics leaked query text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_variable_type_declaration() -> None:
    """Operation variable type declarations satisfy GraphQL variable checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-variable-type-declaration-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": (
                                        "query CustomerLookup($id: ID!) "
                                        "{ customer(id: $id) { id } }"
                                    ),
                                    "variables": {"id": "{{1.customer_id}}"},
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.variable_type_declaration_missing" not in report.codes(), (
        f"GraphQL variable type declaration produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_anonymous_graphql_operation() -> None:
    """GraphQL operations should declare operation names."""
    anonymous_query = "query ($id: ID!) { customer(id: $id) { id } }"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "anonymous-graphql-operation",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": anonymous_query,
                                    "variables": {"id": "{{1.customer_id}}"},
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    operation_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.operation_name_missing"
    )
    assert operation_findings, (
        f"Anonymous GraphQL operation warning was not produced: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in operation_findings
        for message in (finding.client_message, finding.internal_message)
        if anonymous_query in message or "customer" in message
    )
    assert not (leaked_messages), (
        f"Anonymous GraphQL query text leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_named_graphql_operation() -> None:
    """Named GraphQL operations satisfy observability checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "named-graphql-operation",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": (
                                        "query CustomerLookup($id: ID!) "
                                        "{ customer(id: $id) { id } }"
                                    ),
                                    "variables": {"id": "{{1.customer_id}}"},
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.operation_name_missing" not in report.codes(), (
        f"Named GraphQL operation produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_graphql_depth_budget_exceeded() -> None:
    """GraphQL query depth should stay within declared local budgets."""
    deep_query = (
        "query DeepCustomer { customer { orders { edges { node { id } } } } }"
    )
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-depth-budget-exceeded",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlDepthBudget": 3,
                                "body": {"query": deep_query},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    depth_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.depth_budget_exceeded"
    )
    assert depth_findings, (
        f"GraphQL depth budget warning was not produced: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in depth_findings
        for message in (finding.client_message, finding.internal_message)
        if deep_query in message or "orders" in message
    )
    assert not (leaked_messages), (
        f"GraphQL deep query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_depth_budget() -> None:
    """GraphQL query depth at or under the local budget should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-depth-budget-allowed",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlDepthBudget": 6,
                                "body": {
                                    "query": (
                                        "query DeepCustomer "
                                        "{ customer { orders { edges { node {"
                                        "id } } } } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.depth_budget_exceeded" not in report.codes(), (
        f"GraphQL depth budget produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_graphql_field_count_budget_exceeded() -> (
    None
):
    """GraphQL selected field count should stay within declared local.

    budgets.
    """
    wide_query = (
        "query WideCustomer { customer { id name email phone status createdAt }"
        "}"
    )
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-field-count-budget-exceeded",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlFieldCountBudget": 4,
                                "body": {"query": wide_query},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    field_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.field_count_budget_exceeded"
    )
    assert field_findings, (
        f"GraphQL field-count warning was not produced: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in field_findings
        for message in (finding.client_message, finding.internal_message)
        if wide_query in message or "createdAt" in message
    )
    assert not (leaked_messages), (
        f"GraphQL wide query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_field_count_budget() -> None:
    """GraphQL selected field count at or under the local budget should stay.

    quiet.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "graphql-field-count-budget-allowed",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlFieldCountBudget": 8,
                                "body": {
                                    "query": (
                                        "query WideCustomer "
                                        "{ customer { id name email phone "
                                        "status createdAt } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.field_count_budget_exceeded" not in report.codes(), (
        f"GraphQL field-count budget produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_production_graphql_introspection() -> (
    None
):
    """Production GraphQL requests should not execute introspection queries."""
    introspection_query = (
        "query IntrospectionQuery { __schema { queryType { name } } }"
    )
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-introspection",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {"query": introspection_query},
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    introspection_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.production_introspection_query"
    )
    assert introspection_findings, (
        f"Production GraphQL introspection warning was not produced: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in introspection_findings
        for message in (finding.client_message, finding.internal_message)
        if introspection_query in message or "__schema" in message
    )
    assert not (leaked_messages), (
        f"GraphQL introspection query text leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_non_production_graphql_introspection() -> (
    None
):
    """Non-production GraphQL introspection remains outside this profile-gated.

    warning.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "development-graphql-introspection",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {
                                    "query": (
                                        "query IntrospectionQuery "
                                        "{ __schema { queryType { name } } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "development",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.production_introspection_query" not in report.codes(), (
        f"Non-production GraphQL introspection produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_graphql_error_array_guard() -> (
    None
):
    """Production GraphQL requests should show response errors-array handling.

    evidence.
    """
    graphql_query = "query CustomerLookup { customer { id status } }"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-error-array-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "body": {"query": graphql_query},
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.error_array_guard_missing"
    )
    assert findings, (
        f"Missing GraphQL errors guard was not detected: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message or "CustomerLookup" in message
    )
    assert not (leaked_messages), (
        f"GraphQL error-array guard diagnostics leaked query text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_error_array_guard_evidence() -> (
    None
):
    """Local response.errors guard evidence satisfies GraphQL production.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-error-array-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "body": {
                                    "query": (
                                        "query CustomerLookup { customer { id "
                                        "status } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.error_array_guard_missing" not in report.codes(), (
        f"GraphQL error-array evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_graphql_partial_data_guard() -> (
    None
):
    """Production GraphQL requests should show partial-data handling.

    evidence.
    """
    graphql_query = "query CustomerLookup { customer { id status } }"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-partial-data-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "body": {"query": graphql_query},
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.partial_data_guard_missing"
    )
    assert findings, (
        f"Missing GraphQL partial-data guard was not detected: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message or "CustomerLookup" in message
    )
    assert not (leaked_messages), (
        f"GraphQL partial-data guard diagnostics leaked query text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_partial_data_guard_evidence() -> (
    None
):
    """Local partial-data guard evidence satisfies GraphQL production checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-partial-data-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "graphqlPartialDataHandling": {
                                    "requiredGraphqlData": ["customer.id"],
                                    "policy": "route null required data to "
                                    "remediation",
                                },
                                "body": {
                                    "query": (
                                        "query CustomerLookup { customer { id "
                                        "status } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.partial_data_guard_missing" not in report.codes(), (
        f"GraphQL partial-data evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_351e9c7d() -> None:
    """Production GraphQL requests should declare visible schema-version.

    evidence.
    """
    graphql_query = "query CustomerLookup { customer { id status } }"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-schema-version-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "graphqlPartialDataHandling": {
                                    "requiredGraphqlData": ["customer.id"],
                                    "policy": "route null required data to "
                                    "remediation",
                                },
                                "body": {"query": graphql_query},
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.schema_version_missing"
    )
    assert findings, (
        f"Missing GraphQL schema-version evidence was not detected: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message or "CustomerLookup" in message
    )
    assert not (leaked_messages), (
        f"GraphQL schema-version diagnostics leaked query text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_schema_version_evidence() -> None:
    """Local schema-version evidence satisfies GraphQL production checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-schema-version-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlSchemaVersion": "2026-05-15",
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "graphqlPartialDataHandling": {
                                    "requiredGraphqlData": ["customer.id"],
                                    "policy": "route null required data to "
                                    "remediation",
                                },
                                "body": {
                                    "query": (
                                        "query CustomerLookup { customer { id "
                                        "status } }"
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.schema_version_missing" not in report.codes(), (
        f"GraphQL schema-version evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_a333498c() -> None:
    """Production GraphQL mutations should show local idempotency evidence."""
    graphql_query = (
        "mutation CreateInvoice($amount: Int!) "
        "{ createInvoice(input: {amount: $amount}) { id } }"
    )
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-mutation-idempotency-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlSchemaVersion": "2026-05-15",
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "graphqlPartialDataHandling": {
                                    "requiredGraphqlData": ["createInvoice.id"],
                                    "policy": "route null required data to "
                                    "remediation",
                                },
                                "body": {
                                    "query": graphql_query,
                                    "variables": {"amount": 100},
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "graphql.mutation_idempotency_missing"
    )
    assert findings, (
        f"Missing GraphQL mutation idempotency was not detected: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in findings
        for message in (finding.client_message, finding.internal_message)
        if graphql_query in message
        or "CreateInvoice" in message
        or "$amount" in message
    )
    assert not (leaked_messages), (
        f"GraphQL mutation idempotency diagnostics leaked query text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_graphql_mutation_idempotency_evidence() -> (
    None
):
    """Local idempotency evidence satisfies production GraphQL mutation.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "production-graphql-mutation-idempotency-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/graphql",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": "make-scenario/graphql-check",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "timeoutPolicy": {"seconds": 10},
                                "graphqlSchemaVersion": "2026-05-15 ",
                                "graphqlIdempotencyKey": "{{1.request_id}}",
                                "graphqlErrorHandling": {
                                    "errorsPath": "response.errors ",
                                    "policy": "route to local error handler",
                                },
                                "graphqlPartialDataHandling": {
                                    "requiredGraphqlData": ["createInvoice.id"],
                                    "policy": "route null required data to "
                                    "remediation",
                                },
                                "body": {
                                    "query": (
                                        "mutation CreateInvoice($amount: Int!) "
                                        "{ createInvoice(input: {amount:"
                                        "$amount}) { id } }"
                                    ),
                                    "variables": {"amount": 100},
                                },
                            },
                        }
                    ],
                    "metadata": {
                        "environment": "production",
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "graphql.mutation_idempotency_missing" not in report.codes(), (
        f"GraphQL idempotency evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_header_crlf_3e4e8251() -> None:
    """HTTP header line-break injection is blocked without printing raw header.

    values.
    """
    unsafe_header_value = "safe\r\nX-Injected: yes"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-header-crlf-injection",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Trace",
                                        "value": unsafe_header_value,
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.header_crlf_injection" not in report.codes()), (
        f"CRLF header injection was not blocked: {report.findings}"
    )
    assert report.has_errors, (
        f"CRLF header injection must be a blocking error: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_header_value in message or "X-Injected" in message
    )
    assert not (leaked_messages), (
        f"Header injection value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_safe_http_headers() -> None:
    """Ordinary HTTP headers do not trip CRLF injection findings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-safe-headers",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Trace ",
                                        "value": "handoff-check",
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.header_crlf_injection" not in report.codes(), (
        f"Safe headers produced CRLF findings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_78223968() -> None:
    """Dynamic HTTP header values warn without printing the raw mapping."""
    dynamic_header_value = "{{1.payload.x_forwarded_for}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-dynamic-header-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"x_forwarded_for": "203.0.113.9"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Forwarded-For",
                                        "value": dynamic_header_value,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    header_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.dynamic_header_mapping"
    )
    assert header_findings, (
        f"Dynamic header mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in header_findings)
    ), f"Dynamic header mapping findings should warn: {header_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_header_value in message or "x_forwarded_for" in message
    )
    assert not (leaked_messages), (
        f"Dynamic header mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_sanitized_dynamic_header_mappings() -> None:
    """Visible header sanitizer helpers suppress dynamic-header warnings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-sanitized-dynamic-header-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"x_forwarded_for": "203.0.113.9"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Forwarded-For ",
                                        "value": (
                                            "{{sanitizeHeader(1.payload.x_forwarded_for)}}"
                                        ),
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.dynamic_header_mapping" not in report.codes(), (
        f"Sanitized dynamic header mappings should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_proxy_b5ebe9d9() -> None:
    """Proxy identity headers need trust-policy evidence even when header text.

    is sanitized.
    """
    dynamic_header_value = "{{sanitizeHeader(1.payload.x_forwarded_for)}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-proxy-header-trust-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"x_forwarded_for": "203.0.113.9"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Forwarded-For",
                                        "value": dynamic_header_value,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    proxy_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.proxy_header_trust_missing"
    )
    assert proxy_findings, (
        f"Proxy header trust gap was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in proxy_findings)
    ), f"Proxy header trust findings should warn: {proxy_findings}"
    assert "http.dynamic_header_mapping" not in report.codes(), (
        f"Sanitized proxy header text should not trigger generic header "
        f"warning: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in proxy_findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_header_value in message or "x_forwarded_for" in message
    )
    assert not (leaked_messages), (
        f"Proxy header trust diagnostics leaked raw mapping text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_proxy_header_d8d645c6() -> None:
    """Local trusted-proxy normalization evidence suppresses proxy-header trust.

    warnings.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-proxy-header-trust-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"x_forwarded_for": "203.0.113.9"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Forwarded-For ",
                                        "value": (
                                            "{{sanitizeHeader(1.payload.x_forwarded_for)}}"
                                        ),
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {
                        "trusted_proxy_header_policy": {
                            "normalization": (
                                "Ingress proxy allowlist validates "
                                "source chain."
                            )
                        }
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.proxy_header_trust_missing" not in report.codes(), (
        f"Trusted proxy evidence should suppress proxy-header warnings: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_a3959f4e() -> None:
    """Proxy header checks fail closed on partially edited inbound header.

    mappings.
    """
    dynamic_header_value = "{{1.payload.x_forwarded_for"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-http-proxy-header-trust-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"x_forwarded_for": "203.0.113.9"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "X-Forwarded-For",
                                        "value": dynamic_header_value,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    proxy_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.proxy_header_trust_missing"
    )
    assert proxy_findings, (
        f"Partial proxy header mapping was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in proxy_findings
        for message in (finding.client_message, finding.internal_message)
        if dynamic_header_value in message or "x_forwarded_for" in message
    )
    assert not (leaked_messages), (
        f"Proxy header trust diagnostics leaked raw mapping text: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_static_http_ce48380f() -> None:
    """Static secret-looking HTTP values are blocked without printing raw.

    values.
    """
    unsafe_header_value = "Bearer " + ("A" * 16)
    unsafe_body_secret = "sk-" + ("B" * 24)
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-static-secret-literals",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Authorization",
                                        "value": unsafe_header_value,
                                    }
                                ],
                                "body": {"api_key": unsafe_body_secret},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    secret_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.static_secret_literal"
    )
    assert secret_findings, (
        f"Static HTTP secrets were not blocked: {report.findings}"
    )
    assert not (
        any(finding.severity != "error" for finding in secret_findings)
    ), f"Static HTTP secret literals must be blocking: {secret_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_header_value in message or unsafe_body_secret in message
    )
    assert not (leaked_messages), (
        f"Static HTTP secret value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_mapped_http_secret_placeholders() -> None:
    """Make mappings and redacted placeholders do not count as static secret.

    literals.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-secret-placeholders",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Authorization ",
                                        "value": "{{connection.authorization}}",
                                    }
                                ],
                                "body": {"api_key": "redacted"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.static_secret_literal" not in report.codes(), (
        f"Mapped or redacted HTTP secrets should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_secret_header_without_masking() -> None:
    """Mapped secret-scoped headers should declare log masking evidence."""
    header_mapping = "{{connection.authorization}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-secret-header-without-masking",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Authorization",
                                        "value": header_mapping,
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    masking_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.header_secret_masking_missing"
    )
    assert masking_findings, (
        f"Secret header masking warning was not produced: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in masking_findings
        for message in (finding.client_message, finding.internal_message)
        if header_mapping in message or "authorization" in message.casefold()
    )
    assert not (leaked_messages), (
        f"Secret header mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_secret_header_masking_evidence() -> None:
    """Header masking declarations satisfy mapped secret-scoped header.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-secret-header-with-masking",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headerMasking": {"Authorization": "redact"},
                                "headers": [
                                    {
                                        "name": "Authorization ",
                                        "value": "{{connection.authorization}}",
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.header_secret_masking_missing" not in report.codes(), (
        f"Header masking evidence should be accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_cookie_passthrough_header() -> None:
    """Outbound Cookie headers warn when mapped from inbound cookie-like.

    fields.
    """
    cookie_mapping = "{{1.headers.cookie}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-cookie-passthrough-header",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "headers": {"cookie": "session=redacted"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Cookie",
                                        "value": cookie_mapping,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    cookie_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.cookie_passthrough_header"
    )
    assert cookie_findings, (
        f"Cookie pass-through warning was not produced: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in cookie_findings)
    ), f"Cookie pass-through findings should warn: {cookie_findings}"
    leaked_messages = tuple(
        message
        for finding in cookie_findings
        for message in (finding.client_message, finding.internal_message)
        if cookie_mapping in message or "session=redacted" in message
    )
    assert not (leaked_messages), (
        f"Cookie pass-through diagnostics leaked raw header values: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_cookie_passthrough_header() -> (
    None
):
    """Cookie pass-through checks fail closed on partially edited cookie.

    mappings.
    """
    cookie_mapping = "{{1.headers.cookie"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-http-cookie-passthrough-header",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "headers": {"cookie": "session=redacted"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {"name": "Cookie", "value": cookie_mapping}
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    cookie_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.cookie_passthrough_header"
    )
    assert cookie_findings, (
        f"Partial cookie pass-through was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in cookie_findings
        for message in (finding.client_message, finding.internal_message)
        if cookie_mapping in message or "session=redacted" in message
    )
    assert not (leaked_messages), (
        f"Cookie pass-through diagnostics leaked raw header values: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_connection_cookie_header() -> None:
    """Connection-scoped Cookie header mappings are not treated as inbound.

    pass-through.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-connection-cookie-header",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Cookie ",
                                        "value": (
                                            "{{connection.session_cookie}}"
                                        ),
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.cookie_passthrough_header" not in report.codes(), (
        f"Connection-scoped cookie headers should be accepted: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_raw_5a2e4972() -> None:
    """SQL-like modules warn on raw query interpolation without printing the.

    query.
    """
    unsafe_query = "SELECT * FROM customers WHERE email = '{{1.email}}'"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-raw-sql-query-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "postgresql:ExecuteQuery",
                            "parameters": {"query": unsafe_query},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    sql_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "sql.dynamic_raw_query_mapping"
    )
    assert sql_findings, (
        f"Dynamic raw SQL query mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in sql_findings)
    ), f"Dynamic raw SQL query mappings should warn: {sql_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_query in message or "{{1.email}}" in message
    )
    assert not (leaked_messages), (
        f"Raw SQL query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_raw_sql_mapping_marker() -> None:
    """SQL raw-query checks fail closed on partially edited Make mapping.

    markers.
    """
    unsafe_query = "SELECT * FROM customers WHERE email = '{{1.email'"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-dynamic-raw-sql-query-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "postgresql:ExecuteQuery",
                            "parameters": {"query": unsafe_query},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    sql_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "sql.dynamic_raw_query_mapping"
    )
    assert sql_findings, (
        f"Partial raw SQL query marker was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_query in message or "{{1.email" in message
    )
    assert not (leaked_messages), (
        f"Raw SQL query text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_parameterized_sql_query_mappings() -> None:
    """SQL-like modules may map values through explicit parameter bindings."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "parameterized-sql-query-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "postgresql:ExecuteQuery",
                            "parameters": {
                                "query": "SELECT * FROM customers WHERE email ="
                                "$1",
                                "values": ["{{1.email}}"],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "sql.dynamic_raw_query_mapping" not in report.codes(), (
        f"Parameterized SQL query mappings should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_redirect_7060dfce() -> None:
    """Redirect responses with 3xx status must declare Location evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "redirect-status-without-location",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"account": "demo"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 302,
                                "body": "Redirecting",
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    redirect_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "redirect.response_contract_missing"
    )
    assert redirect_findings, (
        f"Redirect status without Location was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in redirect_findings)
    ), f"Redirect response contract findings should warn: {redirect_findings}"
    assert not (any(finding.node_id != "2" for finding in redirect_findings)), (
        f"Redirect response findings should attach to the response action: "
        f"{redirect_findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_location_8bfa4a99() -> None:
    """Redirect responses with Location evidence must declare a 3xx status."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "location-without-redirect-status",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"account": "demo"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "headers": [
                                    {
                                        "name": "Location ",
                                        "value": "https://app.example.invalid/next",
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("redirect.response_contract_missing" not in report.codes()), (
        f"Location without redirect status was not flagged: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_complete_redirect_response_contract() -> (
    None
):
    """Redirect responses with 3xx status and Location evidence are complete."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "complete-redirect-response-contract",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"account": "demo"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 302,
                                "headers": [
                                    {
                                        "name": "Location ",
                                        "value": "https://app.example.invalid/next",
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "redirect.response_contract_missing" not in report.codes(), (
        f"Complete redirect response contract produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_ignores_non_target_redirect_flags() -> None:
    """Boolean redirect switches are not Location or redirect-target.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "non-target-redirect-flag",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"account": "demo"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {"status": 200, "redirect": False},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "redirect.response_contract_missing" not in report.codes(), (
        f"Boolean redirect flag produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_159127a5() -> None:
    """Redirect responses warn on dynamic destination hosts without printing.

    raw.

    URLs.
    """
    unsafe_redirect_url = "{{1.redirect_url}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-redirect-destination",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"redirect_url": unsafe_redirect_url}
                            },
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 302,
                                "headers": [
                                    {
                                        "name": "Location",
                                        "value": unsafe_redirect_url,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    redirect_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "redirect.dynamic_destination_url"
    )
    assert redirect_findings, (
        f"Dynamic redirect destination was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in redirect_findings)
    ), f"Dynamic redirect destinations should warn: {redirect_findings}"
    assert not (any(finding.node_id != "2" for finding in redirect_findings)), (
        f"Redirect findings should attach to the response action: "
        f"{redirect_findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_redirect_url in message or "redirect_url" in message
    )
    assert not (leaked_messages), (
        f"Redirect destination leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_12d91d4b() -> None:
    """Redirect host checks fail closed on partially edited Make mapping.

    markers.
    """
    unsafe_redirect_url = "https://{{1.redirect_host.example.invalid/callback"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-dynamic-redirect-host",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {"redirect_host": "example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 302,
                                "headers": [
                                    {
                                        "name": "Location",
                                        "value": unsafe_redirect_url,
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    redirect_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "redirect.dynamic_destination_url"
    )
    assert redirect_findings, (
        f"Partial dynamic redirect host marker was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_redirect_url in message or "redirect_host" in message
    )
    assert not (leaked_messages), (
        f"Redirect destination leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_static_host_dynamic_redirect_paths() -> (
    None
):
    """Redirect responses may map path/query values under a static host."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "static-host-dynamic-redirect-path",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"account": "demo"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 302,
                                "headers": [
                                    {
                                        "name": "Location",
                                        "value": (
                                            "https://app.example.invalid/accounts/"
                                            "{{1.payload.account}}"
                                        ),
                                    }
                                ],
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "redirect.dynamic_destination_url" not in report.codes(), (
        f"Static-host dynamic redirect path should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_2875f92a() -> None:
    """HTML-capable content warns on unescaped mappings without printing raw.

    content.
    """
    unsafe_html = "<p>{{1.payload.comment}}</p>"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-html-content-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"comment": "hello"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "text/html",
                                    }
                                ],
                                "body": unsafe_html,
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    html_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "content.html_dynamic_mapping"
    )
    assert html_findings, (
        f"Dynamic HTML content mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in html_findings)
    ), f"Dynamic HTML content mappings should warn: {html_findings}"
    assert not (any(finding.node_id != "2" for finding in html_findings)), (
        f"HTML content findings should attach to the response action: "
        f"{html_findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_html in message or "payload.comment" in message
    )
    assert not (leaked_messages), (
        f"HTML content value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_dynamic_html_content_marker() -> (
    None
):
    """HTML content checks fail closed on partially edited Make mapping.

    markers.
    """
    unsafe_html = "<p>{{1.payload.comment</p>"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-dynamic-html-content-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"comment": "hello"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "text/html",
                                    }
                                ],
                                "body": unsafe_html,
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    html_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "content.html_dynamic_mapping"
    )
    assert html_findings, (
        f"Partial dynamic HTML marker was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_html in message or "payload.comment" in message
    )
    assert not (leaked_messages), (
        f"HTML content value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_escaped_dynamic_html_content() -> None:
    """HTML-capable content may map values through visible HTML escaping."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "escaped-dynamic-html-content",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"comment": "hello"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookRespond",
                            "parameters": {
                                "status": 200,
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "text/html",
                                    }
                                ],
                                "body": (
                                    "<p>{{escapeHTML(1.payload.comment)}}</p>"
                                ),
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "content.html_dynamic_mapping" not in report.codes(), (
        f"Escaped dynamic HTML content should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_dynamic_b19c6792() -> None:
    """Markdown-capable content warns on unescaped mappings without printing.

    raw.

    content.
    """
    unsafe_markdown = "[{{1.payload.label}}]({{1.payload.url}})"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "dynamic-markdown-content-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "payload": {
                                    "label": "link ",
                                    "url": "https://example.invalid",
                                }
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:PostMessage",
                            "parameters": {
                                "blocks": [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": unsafe_markdown,
                                        },
                                    }
                                ]
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    markdown_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "content.markdown_dynamic_mapping"
    )
    assert markdown_findings, (
        f"Dynamic Markdown content mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in markdown_findings)
    ), f"Dynamic Markdown content mappings should warn: {markdown_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_markdown in message
        or "payload.label" in message
        or "payload.url" in message
    )
    assert not (leaked_messages), (
        f"Markdown content value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_fc9d2891() -> None:
    """Markdown content checks fail closed on partially edited Make mapping.

    markers.
    """
    unsafe_markdown = "[{{1.payload.label](https://example.invalid)"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-dynamic-markdown-content-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"label": "link"}},
                        },
                        {
                            "id": 2,
                            "module": "slack:PostMessage",
                            "parameters": {
                                "blocks": [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": unsafe_markdown,
                                        },
                                    }
                                ]
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    markdown_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "content.markdown_dynamic_mapping"
    )
    assert markdown_findings, (
        f"Partial dynamic Markdown marker was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_markdown in message or "payload.label" in message
    )
    assert not (leaked_messages), (
        f"Markdown content value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_escaped_dynamic_markdown_content() -> None:
    """Markdown-capable content may map values through visible Markdown.

    escaping.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "escaped-dynamic-markdown-content",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {"payload": {"label": "link"}},
                        },
                        {
                            "id": 2,
                            "module": "slack:PostMessage",
                            "parameters": {
                                "blocks": [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn ",
                                            "text": (
                                                "{{escapeMarkdown(1.payload.label)}}"
                                            ),
                                        },
                                    }
                                ]
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "content.markdown_dynamic_mapping" not in report.codes(), (
        f"Escaped dynamic Markdown content should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_static_f5e1c190() -> None:
    """Unsafe sink message fields warn on static personal identifiers without.

    echoing them.
    """
    unsafe_email = "owner@example.invalid"
    unsafe_phone = "+1 (415) 555-0199"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "static-personal-data-in-http-body",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/notify",
                                "body": {
                                    "message": (
                                        f"Contact {unsafe_email} or "
                                        f"{unsafe_phone} "
                                        "when processing fails."
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.static_personal_literal"
    )
    assert exposure_findings, (
        f"Static personal identifiers were not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Static personal identifier findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_email in message or unsafe_phone in message
    )
    assert not (leaked_messages), (
        f"Static personal identifier text leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_mapped_or_b9d9ae0b() -> None:
    """Mapped and redacted sink content does not count as a static personal.

    literal.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "mapped-personal-data-in-http-body",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/notify",
                                "body": {
                                    "message": (
                                        "Contact {{1.email}} or [redacted "
                                        "phone]"
                                        "when processing fails."
                                    )
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.static_personal_literal" not in report.codes(), (
        f"Mapped or redacted personal values should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_raw_ca57c49c() -> None:
    """Unsafe sink content fields warn on whole-payload mappings without.

    printing them.
    """
    raw_payload_mapping = "Diagnostic dump: {{1.payload}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "raw-payload-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": raw_payload_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.raw_payload_sink"
    )
    assert exposure_findings, (
        f"Whole payload sink mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Whole payload sink findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if raw_payload_mapping in message
    )
    assert not (leaked_messages), (
        f"Whole payload mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_raw_payload_sink_mapping() -> (
    None
):
    """Raw-payload sink checks fail closed on partially edited Make mappings."""
    raw_payload_mapping = "Diagnostic dump: {{1.payload"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-raw-payload-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": raw_payload_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.raw_payload_sink"
    )
    assert exposure_findings, (
        f"Partial raw payload sink was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if raw_payload_mapping in message
    )
    assert not (leaked_messages), (
        f"Whole payload mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_specific_payload_548ee7a3() -> None:
    """Specific payload fields are not treated as whole raw payload dumps."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "specific-payload-field-sink",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"email": "owner@example.invalid"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {
                                "text": "Lead email: {{1.payload.email}}"
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.raw_payload_sink" not in report.codes(), (
        f"Specific payload field mappings should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_secret_061599c5() -> None:
    """Unsafe sink output fields warn on secret-like mappings without printing.

    them.
    """
    output_mapping = "Token: {{1.payload.access_token}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "secret-output-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"access_token": "redacted"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": output_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.secret_output_sink"
    )
    assert exposure_findings, (
        f"Secret output sink mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Secret output sink findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if output_mapping in message or "access_token" in message
    )
    assert not (leaked_messages), (
        f"Secret output mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_secret_output_sink_mapping() -> (
    None
):
    """Secret-output sink checks fail closed on partially edited Make.

    mappings.
    """
    output_mapping = "Token: {{1.payload.access_token"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-secret-output-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"access_token": "redacted"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": output_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.secret_output_sink"
    )
    assert exposure_findings, (
        f"Partial secret output sink was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if output_mapping in message or "access_token" in message
    )
    assert not (leaked_messages), (
        f"Secret output mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_ordinary_output_sink_mappings() -> None:
    """Ordinary specific-field mappings are not treated as secret output.

    exposure.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ordinary-output-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "open"}},
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {
                                "text": "Status: {{1.payload.status}}"
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.secret_output_sink" not in report.codes(), (
        f"Ordinary output mappings should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_sensitive_14dd456a() -> None:
    """Unsafe sinks should redact sensitive-looking HTTP response fields."""
    response_mapping = "Customer: {{1.body.email}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sensitive-http-response-sink",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/customer",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/data-exposure-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": response_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.sensitive_http_response_sink"
    )
    assert exposure_findings, (
        f"Sensitive HTTP response sink mapping was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in exposure_findings
        for message in (finding.client_message, finding.internal_message)
        if response_mapping in message or "body.email" in message
    )
    assert not (leaked_messages), (
        f"Sensitive HTTP response mapping leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_partial_22dd9bb3() -> None:
    """HTTP-response sink checks fail closed on partially edited sensitive.

    fields.
    """
    response_mapping = "Customer: {{1.body.email"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "partial-sensitive-http-response-sink",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/customer",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/data-exposure-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": response_mapping},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.sensitive_http_response_sink"
    )
    assert exposure_findings, (
        f"Partial sensitive HTTP response sink was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in exposure_findings
        for message in (finding.client_message, finding.internal_message)
        if response_mapping in message or "body.email" in message
    )
    assert not (leaked_messages), (
        f"Sensitive HTTP response mapping leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_redacted_http_response_sink_mapping() -> (
    None
):
    """Visible redaction evidence satisfies sensitive HTTP response sink.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "redacted-http-response-sink",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/customer",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/data-exposure-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                            },
                        },
                        {
                            "id": 2,
                            "module": "slack:CreateMessage",
                            "parameters": {
                                "text": "Customer: {{redact(1.body.email)}}"
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.sensitive_http_response_sink" not in report.codes(), (
        f"Redacted HTTP response mapping should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_secret_variable_sink_mappings() -> None:
    """Variable modules warn on token-like mappings without printing them."""
    mapped_value = "{{1.payload.access_token}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "secret-variable-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {
                                "payload": {"access_token": "redacted"}
                            },
                        },
                        {
                            "id": 2,
                            "module": "util:SetVariable",
                            "parameters": {
                                "name": "latest_access_token",
                                "value": mapped_value,
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.secret_output_sink"
    )
    assert exposure_findings, (
        f"Secret variable sink mapping was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in exposure_findings
        for message in (finding.client_message, finding.internal_message)
        if mapped_value in message or "access_token" in message
    )
    assert not (leaked_messages), (
        f"Secret variable mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_ordinary_variable_sink_mappings() -> None:
    """Ordinary variable mappings are not treated as secret output exposure."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ordinary-variable-sink-mapping",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "open"}},
                        },
                        {
                            "id": 2,
                            "module": "util:SetVariable",
                            "parameters": {
                                "name": "last_status ",
                                "value": "{{1.payload.status}}",
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.secret_output_sink" not in report.codes(), (
        f"Ordinary variable mappings should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_raw_error_webhook_responses() -> None:
    """Webhook response fields warn on raw error mappings without printing.

    them.
    """
    raw_error_mapping = "{{1.error.message}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "raw-error-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "failed"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 500,
                                "body": {"message": raw_error_mapping},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.raw_error_output"
    )
    assert exposure_findings, (
        f"Raw error webhook response mapping was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Raw error output findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if raw_error_mapping in message or "error.message" in message
    )
    assert not (leaked_messages), (
        f"Raw error mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_sanitized_error_013c0e1a() -> None:
    """Webhook response error codes and trace IDs are not raw error output."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "sanitized-error-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "failed"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 500,
                                "body": {
                                    "error_code": "{{1.error.code}}",
                                    "trace_id": "{{1.trace_id}}",
                                },
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.raw_error_output" not in report.codes(), (
        f"Sanitized error response fields should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_pagination_token_webhook_responses() -> (
    None
):
    """Webhook response fields warn on raw pagination token mappings."""
    pagination_mapping = "{{1.next_page_token}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "pagination-token-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "next"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 200,
                                "body": {"next_page_token": pagination_mapping},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.pagination_token_output"
    )
    assert exposure_findings, (
        f"Pagination token webhook response was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Pagination token findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in exposure_findings
        for message in (finding.client_message, finding.internal_message)
        if pagination_mapping in message or "next_page_token" in message
    )
    assert not (leaked_messages), (
        f"Pagination token mapping leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_public_pagination_af0ab0af() -> None:
    """Webhook response page numbers and counts are not token-like output."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "safe-pagination-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"status": "next"}},
                        },
                        {
                            "id": 2,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 200,
                                "body": {
                                    "page": "{{1.page}}",
                                    "total_pages": "{{1.total_pages}}",
                                },
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.pagination_token_output" not in report.codes(), (
        f"Public pagination counts should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_internal_2b4ba05a() -> None:
    """Unsafe sink output fields warn on static internal URLs without printing.

    them.
    """
    internal_url_message = "Internal admin URL: http://10.0.0.5/admin"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "internal-url-output-literal",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": internal_url_message},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.internal_url_literal"
    )
    assert exposure_findings, (
        f"Internal URL output literal was not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in exposure_findings)
    ), f"Internal URL literal findings should warn: {exposure_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if "10.0.0.5" in message or internal_url_message in message
    )
    assert not (leaked_messages), (
        f"Internal URL literal leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ipv4_mapped_internal_url_literals() -> (
    None
):
    """Unsafe output sinks should treat IPv4-mapped IPv6 URLs as internal.

    evidence.
    """
    internal_url_message = "Internal admin URL: http://[::ffff:10.0.0.5]/admin"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ipv4-mapped-internal-url-output-literal",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": internal_url_message},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.internal_url_literal"
    )
    assert exposure_findings, (
        f"IPv4-mapped internal URL literal was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if "10.0.0.5" in message or internal_url_message in message
    )
    assert not (leaked_messages), (
        f"IPv4-mapped internal URL literal leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_ipv6_174f4f7b() -> None:
    """Unsafe output sinks should treat IPv6 unspecified URLs as internal.

    evidence.
    """
    internal_url_message = "Internal admin URL: http://[::]/admin"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "ipv6-unspecified-internal-url-output-literal",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": internal_url_message},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.internal_url_literal"
    )
    assert exposure_findings, (
        f"IPv6 unspecified internal URL literal was not flagged: "
        f"{report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if "[::]" in message or internal_url_message in message
    )
    assert not leaked_messages, (
        f"IPv6 unspecified internal URL literal leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_numeric_internal_url_literals() -> None:
    """Unsafe sink text should treat numeric IPv4 aliases as internal URL.

    evidence.
    """
    internal_url_message = "Internal admin URL: http://2130706433/admin"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "numeric-internal-url-output-literal",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:CreateMessage",
                            "parameters": {"text": internal_url_message},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    exposure_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_exposure.internal_url_literal"
    )
    assert exposure_findings, (
        f"Numeric internal URL literal was not flagged: {report.findings}"
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if "2130706433" in message or internal_url_message in message
    )
    assert not (leaked_messages), (
        f"Numeric internal URL literal leaked into diagnostics: "
        f"{leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_public_url_literals_in_output_sinks() -> (
    None
):
    """Public URL literals are not treated as internal infrastructure.

    exposure.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "public-url-output-literal",
                    "flow": [
                        {
                            "id": 1,
                            "module": "slack:CreateMessage",
                            "parameters": {
                                "text": "Public status: "
                                "https://status.example.invalid/help"
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "data_exposure.internal_url_literal" not in report.codes(), (
        f"Public URL literals should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_weak_c442aeb7() -> None:
    """Security-scoped MD5 and SHA-1 hash settings warn without printing raw.

    values.
    """
    weak_signature_algorithm = "HMAC-SHA1"
    weak_digest_algorithm = "md5"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "weak-security-hash",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:VerifySignature",
                            "parameters": {
                                "signatureAlgorithm": weak_signature_algorithm,
                                "digest": weak_digest_algorithm,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    crypto_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "crypto.weak_security_hash"
    )
    assert crypto_findings, (
        f"Weak security hash settings were not flagged: {report.findings}"
    )
    assert not (
        any(finding.severity != "warning" for finding in crypto_findings)
    ), f"Weak security hash findings should warn: {crypto_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if weak_signature_algorithm in message
        or weak_digest_algorithm in message
    )
    assert not (leaked_messages), (
        f"Weak hash value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_stronger_security_8a3615ae() -> None:
    """SHA-256 security settings pass, and unscoped MD5 text is not a hash.

    policy claim.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "strong-security-hash",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:VerifySignature",
                            "parameters": {
                                "signatureAlgorithm": "HMAC-SHA256 ",
                                "digest": "sha256 ",
                                "description": "Legacy note mentions md5 "
                                "migration.",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "crypto.weak_security_hash" not in report.codes(), (
        f"Strong or unscoped hash text should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_blocks_jwt_none_654475f0() -> None:
    """JWT validation configuration must not statically allow the none.

    algorithm.
    """
    unsafe_algorithm = "alg: none"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "jwt-none-algorithm",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:VerifyJwt",
                            "parameters": {
                                "jwt": "{{1.request.jwt}}",
                                "allowedAlgorithms": [unsafe_algorithm],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    crypto_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "crypto.jwt_none_algorithm"
    )
    assert crypto_findings, (
        f"JWT none algorithm setting was not blocked: {report.findings}"
    )
    assert not (
        any(finding.severity != "error" for finding in crypto_findings)
    ), f"JWT none algorithm findings should block: {crypto_findings}"
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_algorithm in message
    )
    assert not (leaked_messages), (
        f"JWT algorithm value leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_expected_jwt_algorithms() -> None:
    """JWT validation configuration can declare concrete non-none algorithms."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "jwt-expected-algorithms",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:VerifyJwt",
                            "parameters": {
                                "jwt": "{{1.request.jwt}}",
                                "allowedAlgorithms": ["RS256"],
                                "header": {"alg": "HS256"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "crypto.jwt_none_algorithm" not in report.codes(), (
        f"Concrete JWT algorithms should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_promoted_http_ed5efedf() -> None:
    """Promoted HTTP, iterator, and data-store course rules run from knowledge.

    facts.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "course-promoted-structural-rules",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items ",
                                "purpose": "Retrieve JSON records.",
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "bodyType": "raw ",
                                "body": "{{1.file_upload}}",
                            },
                        },
                        {
                            "id": 3,
                            "module": "util:Iterator",
                            "parameters": {},
                        },
                        {
                            "id": 4,
                            "module": "datastore:DeleteRecord",
                            "parameters": {"key": "{{3.key}}"},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=http_iterator_datastore_knowledge_query(),
    )

    expected_codes = {
        "http.method_url_missing ",
        "http.parse_response_missing ",
        "http.file_upload_body_type_invalid ",
        "iterator.array_input_missing ",
        "data_store.delete_recovery_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Promoted structural rules did not run: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_when_http_432ecf28() -> None:
    """Promoted HTTP method and URL evidence must live on each request node."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-method-url-contract",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "url": "https://api.example.invalid/items",
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                            },
                        },
                        {
                            "id": 3,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/status",
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=http_iterator_datastore_knowledge_query(),
    )

    method_url_findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "http.method_url_missing"
    )
    assert tuple(finding.node_id for finding in method_url_findings) == (
        "1 ",
        "2",
    ), (
        f"HTTP method and URL warnings should target only incomplete nodes: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_promoted_http_9863a0b1() -> None:
    """Promoted structural rules stay quiet when local configuration evidence.

    exists.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "course-promoted-structural-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items ",
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": True,
                            },
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/uploads ",
                                "bodyType": "multipart/form-data ",
                                "body": "{{1.file_upload}}",
                            },
                        },
                        {
                            "id": 3,
                            "module": "util:Iterator",
                            "parameters": {"array": "{{1.data.items}}"},
                        },
                        {
                            "id": 4,
                            "module": "datastore:DeleteRecord",
                            "parameters": {"key": "{{3.key}}"},
                            "metadata": {
                                "notes": "Backup snapshot is retained for "
                                "recovery."
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=http_iterator_datastore_knowledge_query(),
    )

    forbidden_codes = {
        "http.method_url_missing ",
        "http.parse_response_missing ",
        "http.file_upload_body_type_invalid ",
        "iterator.array_input_missing ",
        "data_store.delete_recovery_missing",
    }
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Complete local evidence produced promoted warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_parse_response_evidence() -> None:
    """Empty parse-response containers do not satisfy promoted HTTP evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-parse-response-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items ",
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": {},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=http_iterator_datastore_knowledge_query(),
    )

    assert not ("http.parse_response_missing" not in report.codes()), (
        f"Empty parseResponse object was treated as enabled: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_get_missing_success_status_contract() -> (
    None
):
    """HTTP GET modules should declare accepted success status evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "get-missing-success-status",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.success_status_contract_missing" not in report.codes()), (
        f"Missing HTTP success status contract was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_get_success_status_contract() -> None:
    """HTTP GET modules with local success status evidence should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "get-success-status-contract",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 204],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.success_status_contract_missing" not in report.codes(), (
        f"HTTP success status evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_disabled_52e69bd9() -> None:
    """Make HTTP modules should keep non-2xx/3xx error evaluation enabled."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "disabled-http-error-status-evaluation",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "handleErrors": False,
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.error_status_evaluation_disabled" not in report.codes()
    ), (
        f"Disabled HTTP error status evaluation was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_enabled_http_error_status_evaluation() -> (
    None
):
    """Make HTTP modules with handleErrors enabled satisfy error-state.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "enabled-http-error-status-evaluation",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "handleErrors": True,
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.error_status_evaluation_disabled" not in report.codes(), (
        f"Enabled HTTP error status evaluation produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_post_955dab18() -> None:
    """HTTP write modules should also declare accepted success status.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "post-missing-success-status",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items ",
                                "bodyType": "raw",
                                "body": '{"name":"Ada"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.success_status_contract_missing" not in report.codes()), (
        f"Missing HTTP success status contract was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_post_success_status_contract() -> None:
    """HTTP write modules with local success status evidence should stay.

    quiet.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "post-success-status-contract",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items ",
                                "bodyType": "raw",
                                "body": '{"name":"Ada"}',
                                "successStatus": "2xx",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.success_status_contract_missing" not in report.codes(), (
        f"HTTP success status evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_redirects_without_policy() -> None:
    """HTTP modules following redirects should declare redirect policy.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "redirect-policy-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "followRedirects": True,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.redirect_policy_missing" not in report.codes()), (
        f"Missing HTTP redirect policy was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_redirect_policy() -> None:
    """HTTP redirect policy evidence should satisfy redirect checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "redirect-policy-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "followRedirects": True,
                                "redirectLimit": 3,
                                "allowedRedirectHosts": ["api.example.invalid"],
                                "credentialForwardingPolicy": (
                                    "strip authorization on cross-host redirect"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.redirect_policy_missing" not in report.codes(), (
        f"HTTP redirect policy evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_authorization_redirect_leak() -> None:
    """Authorization headers need redirect host and credential-forwarding.

    posture.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "authorization-redirect-leak",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "followRedirects": True,
                                "redirectLimit": 3,
                                "headers": [
                                    {
                                        "name": "Authorization ",
                                        "value": "{{connection.authorization}}",
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.authorization_redirect_leak" not in report.codes()), (
        f"Authorization redirect leak warning was not produced: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_authorization_redirect_policy() -> None:
    """Allowed redirect hosts plus credential policy satisfy Authorization.

    redirects.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "authorization-redirect-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "followRedirects": True,
                                "redirectLimit": 3,
                                "allowedRedirectHosts": ["api.example.invalid"],
                                "redirectCredentialPolicy": (
                                    "strip authorization on cross-host redirect"
                                ),
                                "headers": [
                                    {
                                        "name": "Authorization ",
                                        "value": "{{connection.authorization}}",
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.authorization_redirect_leak" not in report.codes(), (
        f"Authorization redirect policy produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_empty_body_parse_guard_missing() -> None:
    """HTTP response parsing with 204 success evidence should declare an.

    empty-body guard.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-body-parse-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 204],
                                "parseResponse": True,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.empty_body_parse_guard_missing" not in report.codes()), (
        f"Missing HTTP empty-body parse guard was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_empty_body_parse_guard() -> None:
    """Empty-body parse guard evidence should satisfy 204 parsing checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-body-parse-guard-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 204],
                                "parseResponse": True,
                                "emptyBodyParseGuard": (
                                    "skip JSON parse for 204 or empty body "
                                ),
                                "responseContentTypeGuard": "validate response "
                                "Content-Type first",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.empty_body_parse_guard_missing" not in report.codes(), (
        f"HTTP empty-body parse guard evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_json_ea0ca091() -> None:
    """HTTP JSON response parsing should declare response Content-Type.

    validation.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "json-parse-content-type-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": True,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.response_content_type_guard_missing" not in report.codes()
    ), (
        f"Missing HTTP response Content-Type guard was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_json_parse_content_type_guard() -> None:
    """Response Content-Type guard evidence should satisfy JSON parsing.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "json-parse-content-type-guard-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": True,
                                "responseContentTypeGuard": (
                                    "validate response Content-Type before "
                                    "JSON "
                                    "parse"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.response_content_type_guard_missing" not in report.codes(), (
        f"HTTP response Content-Type guard produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_permanent_error_retry_policy() -> None:
    """HTTP retry policies should not include permanent errors."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "permanent-error-retry-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "retryPolicy": {"retryStatusCodes": [400, 500]},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.permanent_error_retry_policy" not in report.codes()), (
        f"Permanent HTTP retry policy was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_transient_error_retry_policy() -> None:
    """HTTP retry policies limited to transient errors should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "transient-error-retry-policy",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "retryPolicy": {
                                    "retryStatusCodes": [500, 502, 503],
                                    "backoff": "exponential",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.permanent_error_retry_policy" not in report.codes(), (
        f"Transient HTTP retry policy produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_retryable_f66bf9c7() -> None:
    """Retryable HTTP mutations should declare idempotency or transaction.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "retryable-mutation-idempotency-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/orders",
                                "expectedStatusCodes": [201],
                                "timeoutSeconds": 30,
                                "retryPolicy": {
                                    "retryStatusCodes": [500, 502, 503],
                                    "backoff": "exponential",
                                },
                                "body": '{"status":"created"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.retryable_mutation_idempotency_missing" not in report.codes()
    ), f"Retryable mutation idempotency gap was not detected: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_retryable_mutation_idempotency() -> None:
    """Idempotency evidence should satisfy retryable HTTP mutation checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "retryable-mutation-idempotency-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/orders",
                                "expectedStatusCodes": [201],
                                "timeoutSeconds": 30,
                                "headers": [
                                    {
                                        "name": "Idempotency-Key ",
                                        "value": "{{1.request_id}}",
                                    }
                                ],
                                "retryPolicy": {
                                    "retryStatusCodes": [500, 502, 503],
                                    "backoff": "exponential",
                                },
                                "body": '{"status":"created"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert (
        "http.retryable_mutation_idempotency_missing" not in report.codes()
    ), f"Retryable mutation idempotency evidence warned: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_patch_without_semantics() -> None:
    """PATCH requests should declare merge, JSON Patch, or provider-specific.

    semantics.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "patch-semantics-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "PATCH ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "body": '{"status":"active"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.patch_semantics_missing" not in report.codes()), (
        f"Missing PATCH semantics were not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_patch_semantics() -> None:
    """PATCH semantics evidence should satisfy partial-update request checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "patch-semantics-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "PATCH ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "patchSemantics": "JSON Merge Patch partial "
                                "update",
                                "body": '{"status":"active"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.patch_semantics_missing" not in report.codes(), (
        f"PATCH semantics evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_put_without_replacement_guard() -> None:
    """PUT requests should acknowledge full replacement or partial-update.

    conversion.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "put-replacement-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "PUT ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "body": '{"status":"active"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.put_replacement_guard_missing" not in report.codes()), (
        f"Missing PUT replacement guard was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_put_replacement_guard() -> None:
    """PUT replacement evidence should satisfy full-replacement request.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "put-replacement-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "PUT ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "putSemantics": "full replacement acknowledged",
                                "body": '{"status":"active"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.put_replacement_guard_missing" not in report.codes(), (
        f"PUT replacement guard evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_delete_body_without_guard() -> None:
    """DELETE request bodies should declare explicit provider support.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "delete-body-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "DELETE ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [202],
                                "timeoutSeconds": 30,
                                "body": '{"reason":"duplicate"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.delete_body_guard_missing" not in report.codes()), (
        f"DELETE body without guard was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_delete_body_guard() -> None:
    """Provider-support evidence should satisfy DELETE request body checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "delete-body-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "DELETE ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [202],
                                "timeoutSeconds": 30,
                                "deleteBodyGuard": "provider supports DELETE "
                                "body semantics",
                                "body": '{"reason":"duplicate"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.delete_body_guard_missing" not in report.codes(), (
        f"DELETE body guard evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_head_response_body_expectation() -> None:
    """HEAD requests should not expect response-body parsing or schemas."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "head-response-body-expected",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "HEAD ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "parseResponse": True,
                                "responseBodySchema": {"id": "string"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.head_response_body_expected" not in report.codes()), (
        f"HEAD response-body expectation was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_head_no_body_expectation() -> None:
    """HEAD requests without response-body expectations should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "head-response-body-not-expected",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "HEAD ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.head_response_body_expected" not in report.codes(), (
        f"HEAD without response-body expectation produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_options_without_usage_guard() -> None:
    """OPTIONS requests should declare CORS or capability-discovery usage."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "options-usage-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "OPTIONS ",
                                "url": "https://api.example.invalid/users",
                                "expectedStatusCodes": [204],
                                "timeoutSeconds": 30,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.options_usage_guard_missing" not in report.codes()), (
        f"OPTIONS usage guard gap was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_options_usage_guard() -> None:
    """CORS or capability evidence should satisfy OPTIONS request checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "options-usage-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "OPTIONS ",
                                "url": "https://api.example.invalid/users",
                                "expectedStatusCodes": [204],
                                "timeoutSeconds": 30,
                                "purpose": (
                                    "CORS preflight capability discovery"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.options_usage_guard_missing" not in report.codes(), (
        f"OPTIONS usage guard evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_response_schema_guard_missing() -> None:
    """Parsed HTTP responses should declare schema or fallback evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "response-schema-guard-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "parseResponse": True,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.response_schema_guard_missing" not in report.codes()), (
        f"Missing HTTP response schema guard was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_response_schema_guard() -> None:
    """Schema or fallback evidence should satisfy parsed HTTP response.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "response-schema-guard-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/users/123",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "parseResponse": True,
                                "responseSchema": {
                                    "id": "string ",
                                    "status": "string",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.response_schema_guard_missing" not in report.codes(), (
        f"HTTP response schema guard evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_request_body_size_budget_missing() -> (
    None
):
    """Mapped HTTP bodies from payload-like sources should declare size.

    budgets.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "request-body-size-budget-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/uploads",
                                "expectedStatusCodes": [202],
                                "timeoutSeconds": 30,
                                "body": "{{1.payload}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.request_body_size_budget_missing" not in report.codes()
    ), f"Missing request body size budget was not detected: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_request_body_size_budget() -> None:
    """Request body size-budget evidence should satisfy mapped body checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "request-body-size-budget-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/uploads",
                                "expectedStatusCodes": [202],
                                "timeoutSeconds": 30,
                                "requestBodyBudget": "max body 128 KB ",
                                "body": "{{1.payload}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.request_body_size_budget_missing" not in report.codes(), (
        f"Request body size-budget evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_response_size_budget_missing() -> None:
    """Parsed HTTP responses should declare response size budgets."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "response-size-budget-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/users",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "parseResponse": True,
                                "responseSchema": {"items": "array"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.response_size_budget_missing" not in report.codes()), (
        f"Missing HTTP response size budget was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_response_size_budget() -> None:
    """Response size-budget evidence should satisfy parsed response checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "response-size-budget-present",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/users",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 30,
                                "parseResponse": True,
                                "responseSchema": {"items": "array"},
                                "responseSizeBudget": "max response 256 KB",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.response_size_budget_missing" not in report.codes(), (
        f"HTTP response size-budget evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_404_without_semantic_classification() -> (
    None
):
    """HTTP 404 handling should declare not-found semantics."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "not-found-classification-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items/{{1.id}}",
                                "expectedStatusCodes": [200, 404],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.not_found_classification_missing" not in report.codes()
    ), f"Missing HTTP 404 classification was not detected: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_404_semantic_classification() -> None:
    """HTTP 404 semantic classification evidence should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "not-found-classification-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items/{{1.id}}",
                                "expectedStatusCodes": [200, 404],
                                "notFoundClassification": "expected missing "
                                "resource",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.not_found_classification_missing" not in report.codes(), (
        f"HTTP 404 classification evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_409_without_conflict_branch() -> None:
    """Mutating HTTP 409 handling should declare conflict branch evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "conflict-branch-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 409],
                                "bodyType": "raw ",
                                "body": "name=Ada",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.conflict_branch_missing" not in report.codes()), (
        f"Missing HTTP 409 conflict branch was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_409_conflict_branch() -> None:
    """Mutating HTTP 409 conflict branch evidence should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "conflict-branch-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 409],
                                "bodyType": "raw ",
                                "body": "name=Ada ",
                                "conflictBranch": "route 409 conflict to "
                                "conflict resolution",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.conflict_branch_missing" not in report.codes(), (
        f"HTTP 409 conflict branch evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_409_without_resume_or_dedupe() -> None:
    """409 conflict branches should declare resume or dedupe semantics."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "conflict-resume-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 409],
                                "bodyType": "raw ",
                                "body": "name=Ada ",
                                "conflictBranch": "route 409 conflict to a "
                                "handler",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.conflict_resume_missing" not in report.codes()), (
        f"Missing HTTP 409 resume evidence was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_409_resume_or_dedupe() -> None:
    """409 conflict handling may retrieve existing resources or deduplicate."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "conflict-resume-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 409],
                                "bodyType": "raw ",
                                "body": "name=Ada ",
                                "conflictBranch": "route 409 conflict to a "
                                "handler",
                                "conflictResume": (
                                    "retrieve existing resource and use "
                                    "idempotent resume "
                                    "with dedupe key"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.conflict_resume_missing" not in report.codes(), (
        f"HTTP 409 resume evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_429_without_rate_limit_branch() -> None:
    """HTTP 429 handling should declare rate-limit branch evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "rate-limit-branch-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 429],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.rate_limit_branch_missing" not in report.codes()), (
        f"Missing HTTP 429 rate-limit branch was not detected: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_429_rate_limit_branch() -> None:
    """HTTP 429 rate-limit branch evidence should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "rate-limit-branch-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 429],
                                "rateLimitBranch": "route 429 to Retry-After "
                                "backoff",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.rate_limit_branch_missing" not in report.codes(), (
        f"HTTP 429 rate-limit branch evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_5xx_without_backoff() -> None:
    """HTTP 5xx handling should declare bounded backoff, queueing, or DLQ.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "server-error-backoff-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 500],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.server_error_backoff_missing" not in report.codes()), (
        f"Missing HTTP 5xx backoff handling was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_5xx_backoff() -> None:
    """HTTP 5xx backoff or queueing evidence should stay quiet."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "server-error-backoff-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 500],
                                "serverErrorBackoff": "bounded exponential "
                                "backoff with DLQ",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.server_error_backoff_missing" not in report.codes(), (
        f"HTTP 5xx backoff evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_blind_error_catchall() -> None:
    """Mixed HTTP error status classes should not share one generic.

    catch-all.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "blind-error-catchall",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 401, 429, 500],
                                "genericErrorRoute": "single catch-all for "
                                "every error",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.blind_error_catchall" not in report.codes()), (
        f"Blind HTTP error catch-all was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_distinct_error_status_class_handling() -> (
    None
):
    """Class-specific handling evidence satisfies mixed HTTP error status.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "distinct-error-status-class-handling",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200, 401, 429, 500],
                                "genericErrorRoute": "fallback after specific "
                                "routes ",
                                "authErrorBranch": "route 401 to credential "
                                "refresh ",
                                "rateLimitBranch": "route 429 to Retry-After "
                                "backoff ",
                                "serverErrorBackoff": "bounded exponential "
                                "backoff with DLQ",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.blind_error_catchall" not in report.codes(), (
        f"Distinct status-class handling should be accepted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_upstream_status_mapping() -> None:
    """Webhook responses should not collapse upstream HTTP failures to static.

    500.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "upstream-status-mapping-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"id": "123"}},
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items/{{1.payload.id}}",
                                "expectedStatusCodes": [200, 404, 429, 500],
                            },
                        },
                        {
                            "id": 3,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 500,
                                "body": {"message": "Upstream request failed"},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.upstream_status_mapping_missing" not in report.codes()), (
        f"Missing upstream status mapping was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_upstream_status_mapping() -> None:
    """Status mapping evidence satisfies HTTP-backed webhook response checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "upstream-status-mapping-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhook:CustomWebhook",
                            "parameters": {"payload": {"id": "123"}},
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items/{{1.payload.id}}",
                                "expectedStatusCodes": [200, 404, 429, 500],
                            },
                        },
                        {
                            "id": 3,
                            "module": "gateway:WebhookResponse",
                            "parameters": {
                                "status": 500,
                                "upstreamStatusMapping": (
                                    "map upstream 404 to 404, 429 to 429, and "
                                    "5xx to 503"
                                ),
                                "body": {"message": "Mapped upstream failure"},
                            },
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.upstream_status_mapping_missing" not in report.codes(), (
        f"Upstream status mapping evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_http_user_agent_context() -> None:
    """Static external HTTP requests should declare User-Agent or context.

    headers.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-user-agent-context-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.user_agent_context_missing" not in report.codes()), (
        f"Missing User-Agent context warning was not produced: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_http_user_agent_context() -> None:
    """User-Agent evidence satisfies static external HTTP context checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "http-user-agent-context-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/portfolio-check"
                                        ),
                                    }
                                ],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.user_agent_context_missing" not in report.codes(), (
        f"User-Agent context evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_local_numeric_dae0eb64() -> None:
    """Numeric loopback aliases should not be treated as external HTTP.

    endpoints.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "numeric-loopback-http-user-agent-context",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "http://2130706433:8787/health",
                                "expectedStatusCodes": [200],
                                "timeoutSeconds": 5,
                                "retryPolicy": {
                                    "maxAttempts": 2,
                                    "backoff": "exponential jitter",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.user_agent_context_missing" not in report.codes(), (
        f"Numeric loopback HTTP URL should not require User-Agent context: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_restore_6c61d471() -> None:
    """Restore labels must not be the only visible HTTP runtime.

    configuration.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "restore-label-http-config",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "metadata": {
                                "restore": {
                                    "label": (
                                        "POST https://api.example."
                                        "invalid/items "
                                        "with Bearer auth"
                                    )
                                }
                            },
                            "parameters": {"expectedStatusCodes": [200]},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.restore_label_dependency" not in report.codes()), (
        f"Restore label dependency warning was not produced: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_runtime_config_with_restore_label() -> None:
    """Runtime fields satisfy restore-label dependency checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "restore-label-http-config-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "metadata": {
                                "restore": {
                                    "label": (
                                        "POST https://api.example."
                                        "invalid/items "
                                        "with Bearer auth"
                                    )
                                }
                            },
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items ",
                                "connection": "managed-http-connection",
                                "headers": [
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/restore-label-check"
                                        ),
                                    }
                                ],
                                "expectedStatusCodes": [200],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.restore_label_dependency" not in report.codes(), (
        f"Runtime HTTP config still produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_missing_json_accept_header() -> None:
    """HTTP requests expecting JSON should declare Accept: application/json."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "json-accept-header-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "expectedStatusCodes": [200],
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": True,
                                "responseContentTypeGuard": (
                                    "validate response Content-Type before "
                                    "JSON "
                                    "parse"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.accept_header_missing" not in report.codes()), (
        f"Missing HTTP JSON Accept header was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_json_accept_header() -> None:
    """Accept: application/json evidence should satisfy JSON response.

    expectations.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "json-accept-header-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Accept ",
                                        "value": "application/json",
                                    }
                                ],
                                "expectedStatusCodes": [200],
                                "purpose": "Retrieve JSON records.",
                                "parseResponse": True,
                                "responseContentTypeGuard": (
                                    "validate response Content-Type before "
                                    "JSON "
                                    "parse"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.accept_header_missing" not in report.codes(), (
        f"HTTP JSON Accept header evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_raw_json_body_without_validation() -> (
    None
):
    """Raw string bodies sent as JSON should declare JSON validation.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "raw-json-body-validation-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    }
                                ],
                                "bodyType": "raw ",
                                "body": "name={{1.name}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (
        "http.raw_json_body_validation_missing" not in report.codes()
    ), f"Raw JSON body validation warning was not produced: {report.findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_raw_json_body_validation() -> None:
    """JSON body validation evidence satisfies raw string JSON content-type.

    checks.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "raw-json-body-validation-complete",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    }
                                ],
                                "bodyType": "raw ",
                                "body": "name={{1.name}}",
                                "jsonBodyValidation": "validate JSON body "
                                "before send",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.raw_json_body_validation_missing" not in report.codes(), (
        f"Raw JSON body validation evidence produced a warning: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_invalid_json_body_syntax() -> None:
    """JSON-looking request bodies should be locally parseable JSON."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "invalid-json-body-syntax",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    },
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/json-body-check"
                                        ),
                                    },
                                ],
                                "expectedStatusCodes": [200],
                                "body": '{"name": "{{1.name}}",}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.json_body_syntax_invalid" not in report.codes()), (
        f"Invalid JSON body syntax warning was not produced: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_valid_json_body_syntax() -> None:
    """Parseable JSON request body syntax satisfies JSON shape checks."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "valid-json-body-syntax",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    },
                                    {
                                        "name": "User-Agent ",
                                        "value": (
                                            "make-scenario/json-body-check"
                                        ),
                                    },
                                ],
                                "expectedStatusCodes": [200],
                                "body": '{"name": "{{1.name}}"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.json_body_syntax_invalid" not in report.codes(), (
        f"Valid JSON body syntax produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_warns_on_get_body_without_allowlist() -> None:
    """HTTP GET request bodies should declare explicit nonstandard API.

    evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "get-body-without-allowlist",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/search",
                                "expectedStatusCodes": [200],
                                "bodyType": "raw",
                                "body": '{"filter":"active"}',
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("http.get_body_not_allowed" not in report.codes()), (
        f"GET body without allowlist was not detected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_get_body_with_allowlist() -> None:
    """Allowlist evidence should satisfy nonstandard HTTP GET request body.

    usage.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "get-body-with-allowlist",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/search",
                                "expectedStatusCodes": [200],
                                "bodyType": "raw",
                                "body": '{"filter":"active"}',
                                "getBodyAllowlist": (
                                    "known nonstandard API requires a body on"
                                    "GET"
                                ),
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "http.get_body_not_allowed" not in report.codes(), (
        f"GET body allowlist evidence produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_requires_promoted_structural_37f5() -> None:
    """Child route evidence must not satisfy parent structural rules."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "child-only-structural-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "GET ",
                                "url": "https://api.example.invalid/items ",
                                "purpose": "Retrieve JSON records.",
                            },
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 11,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "parseResponse": True
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                        {
                            "id": 2,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "bodyType": "raw ",
                                "body": "{{1.file_upload}}",
                            },
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 12,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "bodyType": (
                                                    "multipart/form-data"
                                                )
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                        {
                            "id": 3,
                            "module": "util:Iterator",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 13,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "array": "{{1.data}}"
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                        {
                            "id": 4,
                            "module": "datastore:DeleteRecord",
                            "parameters": {"key": "{{3.key}}"},
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 14,
                                            "module": "util:SetVariable",
                                            "metadata": {
                                                "notes": (
                                                    "Backup snapshot is "
                                                    "retained for recovery."
                                                )
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=http_iterator_datastore_knowledge_query(),
    )

    expected_codes = {
        "http.parse_response_missing ",
        "http.file_upload_body_type_invalid ",
        "iterator.array_input_missing ",
        "data_store.delete_recovery_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Child-only evidence suppressed structural warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_course_completion_rules() -> None:
    """Promoted remaining course claims run through deterministic validators."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "course-completion-rules",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "method": "POST ",
                                "body": "customer payload",
                            },
                        },
                        {
                            "id": 2,
                            "module": "tools:TextAggregator",
                            "parameters": {},
                        },
                        {
                            "id": 3,
                            "module": "text-parser:MatchPattern",
                            "parameters": {},
                        },
                        {
                            "id": 4,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "bodyType": "raw",
                                "body": '{"name":"Ada"}',
                            },
                        },
                        {
                            "id": 5,
                            "module": "datastore:UpdateRecord",
                            "parameters": {"value": "Ada"},
                        },
                        {
                            "id": 6,
                            "module": "tools:BasicTrigger",
                            "parameters": {},
                        },
                        {
                            "id": 7,
                            "module": "mcp:RunTool",
                            "parameters": {},
                        },
                        {
                            "id": 8,
                            "module": "custom-app:CreateThing",
                            "parameters": {},
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=course_completion_knowledge_query(),
    )

    expected_codes = {
        "webhook.payload_contract_missing ",
        "aggregator.source_missing ",
        "aggregator.strategy_missing ",
        "text_parser.pattern_missing ",
        "text_parser.input_missing ",
        "http.json_content_type_missing ",
        "data_store.write_key_missing ",
        "basic_trigger.interface_missing ",
        "mcp_tool.contract_missing ",
        "custom_app.schema_contract_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Course completion rules did not run: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_empty_course_completion_evidence() -> None:
    """Course-rule evidence keys must carry meaningful payload values."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "empty-course-completion-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:TextAggregator",
                            "parameters": {
                                "sourceModule": "",
                                "rowSeparator": [],
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=course_completion_knowledge_query(),
    )

    expected_codes = {
        "aggregator.source_missing ",
        "aggregator.strategy_missing",
    }
    missing_codes = expected_codes.difference(report.codes())
    assert not (missing_codes), (
        f"Empty course-rule evidence was accepted: {missing_codes} "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_course_completion_evidence() -> None:
    """Remaining promoted course rules stay quiet when local evidence exists."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "course-completion-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "interface": [{"name": "customer", "type": "text"}],
                            "parameters": {
                                "method": "POST ",
                                "body": "customer payload",
                            },
                        },
                        {
                            "id": 2,
                            "module": "tools:TextAggregator",
                            "parameters": {
                                "sourceModule": "1 ",
                                "rowSeparator": "\\n",
                            },
                        },
                        {
                            "id": 3,
                            "module": "text-parser:MatchPattern",
                            "parameters": {
                                "pattern": "[A-Z]+",
                                "text": "{{1.customer}}",
                            },
                        },
                        {
                            "id": 4,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                                "headers": [
                                    {
                                        "name": "Content-Type ",
                                        "value": "application/json",
                                    }
                                ],
                                "body": '{"name":"Ada"}',
                            },
                        },
                        {
                            "id": 5,
                            "module": "datastore:UpdateRecord",
                            "parameters": {
                                "key": "{{1.customer}}",
                                "value": "Ada",
                            },
                        },
                        {
                            "id": 6,
                            "module": "tools:BasicTrigger",
                            "interface": [{"name": "customer", "type": "text"}],
                        },
                        {
                            "id": 7,
                            "module": "mcp:RunTool",
                            "parameters": {
                                "input_schema": [
                                    {"name": "query", "type": "text"}
                                ],
                                "output_schema": [
                                    {"name": "answer", "type": "text"}
                                ],
                            },
                        },
                        {
                            "id": 8,
                            "module": "custom-app:CreateThing",
                            "interface": [{"name": "thing_id", "type": "text"}],
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=course_completion_knowledge_query(),
    )

    forbidden_codes = {
        "webhook.payload_contract_missing ",
        "aggregator.source_missing ",
        "aggregator.strategy_missing ",
        "text_parser.pattern_missing ",
        "text_parser.input_missing ",
        "http.json_content_type_missing ",
        "data_store.write_key_missing ",
        "basic_trigger.interface_missing ",
        "mcp_tool.contract_missing ",
        "custom_app.schema_contract_missing",
    }
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Complete local evidence produced course warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_applies_transaction_safety_profiles() -> None:
    """Promoted transaction profiles warn on rollback-unsafe HTTP writes."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "transaction-safety-missing",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "body": {"name": "Created outside Make"},
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=transaction_safety_knowledge_query(),
    )

    assert not ("transaction.rollback_posture_missing" not in report.codes()), (
        f"Transaction profile rule did not run: {report.codes()}"
    )
    finding = next(
        finding
        for finding in report.findings
        if finding.code == "transaction.rollback_posture_missing"
    )
    assert not (
        "course-rule-transaction-rollback-posture-missing"
        not in finding.internal_message
    ), f"Transaction rule provenance was not retained: {finding}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_accepts_transaction_safety_posture_evidence() -> (
    None
):
    """Transaction profile warnings stay quiet when compensation evidence.

    exists.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "transaction-safety-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "body": {"name": "Created outside Make"},
                                "idempotencyKey": "{{1.request_id}}",
                            },
                            "metadata": {
                                "notes": "Compensation flow can undo the "
                                "external write."
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=transaction_safety_knowledge_query(),
    )

    assert "transaction.rollback_posture_missing" not in report.codes(), (
        f"Transaction evidence still produced warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_keeps_transaction_posture_node_local() -> None:
    """Nested child text must not satisfy a parent transaction-safety.

    posture.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "transaction-child-only-evidence",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "https://api.example.invalid/items",
                                "body": {"name": "Created outside Make"},
                            },
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "util:SetVariable",
                                            "parameters": {
                                                "note": (
                                                    "Child rollback note is "
                                                    "not parent posture."
                                                )
                                            },
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=transaction_safety_knowledge_query(),
    )

    assert not ("transaction.rollback_posture_missing" not in report.codes()), (
        f"Child transaction text suppressed parent warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_does_not_treat_495d0ca9() -> None:
    """Webhook responses inside routes remain response actions."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "nested-webhook-response",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "gateway:WebhookResponse",
                                            "parameters": {"status": 200},
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    forbidden_codes = {"semantic.nested_trigger", "webhook.response_missing"}
    leaked_codes = forbidden_codes.intersection(report.codes())
    assert not (leaked_codes), (
        f"Nested webhook response was treated as a webhook trigger: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_authentication_designer_message() -> None:
    """Authentication designer messages are blocking runtime evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "auth-message",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "metadata": {
                                "raw_spec": {
                                    "catalog_module_id": (
                                        "module:http:1.0:action:makeRequest"
                                    ),
                                    "issues": [],
                                    "raw_spec_sha256": "1" * 64,
                                    "status": "resolved",
                                },
                                "designer": {
                                    "x": 0,
                                    "y": 0,
                                    "messages": [
                                        {
                                            "message": "Connection requires "
                                            "re-authentication."
                                        }
                                    ],
                                },
                            },
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.authentication_required" not in report.codes()), (
        f"Authentication designer message was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_authentication_designer_text_message() -> (
    None
):
    """Authentication designer text fields are blocking runtime evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "auth-text-message",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "metadata": {
                                "raw_spec": {
                                    "catalog_module_id": (
                                        "module:http:1.0:action:makeRequest"
                                    ),
                                    "issues": [],
                                    "raw_spec_sha256": "1" * 64,
                                    "status": "resolved",
                                },
                                "designer": {
                                    "x": 0,
                                    "y": 0,
                                    "messages": [
                                        {
                                            "text": "Connection requires "
                                            "re-authentication."
                                        }
                                    ],
                                },
                            },
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.authentication_required" not in report.codes()), (
        f"Authentication designer text was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_surfaces_reviewed_designer_message_warnings() -> (
    None
):
    """Reviewed Make designer evidence remains a warning diagnostic stream."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "reviewed-designer-warning",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
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
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=designer_message_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "make_designer.warning"
    )
    assert len(findings) == 1, (
        f"Expected one reviewed designer warning: {report.findings}"
    )
    finding = findings[0]
    assert finding.severity == "warning", (
        f"Designer evidence must stay warning-only and node-scoped: {finding}"
    )
    assert finding.node_id == "1", (
        f"Designer evidence must stay warning-only and node-scoped: {finding}"
    )
    assert finding.client_message.startswith("MAKE-DESIGNER-WARN:"), (
        f"Designer warning prefix was not preserved: {finding}"
    )
    assert "MAKE-AST-ERROR" not in finding.client_message, (
        f"Designer warnings must not use local error prefixes: {finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_surfaces_root_designer_message_warnings() -> None:
    """Reviewed scenario-level designer evidence remains a distinct warning."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "reviewed-root-designer-warning",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
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
                            "parameters": {
                                "method": "POST ",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=root_designer_message_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "make_designer.warning"
    )
    assert len(findings) == 1, (
        f"Expected one reviewed root designer warning: {report.findings}"
    )
    finding = findings[0]
    assert finding.severity == "warning", (
        f"Root designer evidence must stay warning-only and root-scoped: "
        f"{finding}"
    )
    assert not (finding.node_id is not None), (
        f"Root designer evidence must stay warning-only and root-scoped: "
        f"{finding}"
    )
    assert finding.client_message.startswith("MAKE-DESIGNER-WARN:"), (
        f"Designer warning prefix was not preserved: {finding}"
    )
    assert "MAKE-AST-ERROR" not in finding.client_message, (
        f"Designer warnings must not use local error prefixes: {finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_unknown_declared_output_reference() -> (
    None
):
    """Declared source outputs reject misspelled downstream field references."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{1.emailTypo}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.output_field_unknown" not in report.codes()), (
        f"Unknown output reference was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_unknown_expression_source_node() -> None:
    """Make expressions must not reference nodes absent from the AST."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{99.email}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.reference_unknown_node" not in report.codes()), (
        f"Unknown expression source node was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_bracket_quoted_unknown_source_node() -> (
    None
):
    """Bracket-quoted Make references still require an existing source node."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference='{{99["email"]}}',
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.reference_unknown_node" not in report.codes()), (
        f"Unknown bracket reference source was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_bare_unknown_expression_source_node() -> (
    None
):
    """Bare Make node references still require an existing source node."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{99}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.reference_unknown_node" not in report.codes()), (
        f"Unknown bare source reference was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_declared_output_reference() -> None:
    """Declared source output fields are valid mapping references."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{1.email}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "semantic.output_field_unknown" not in report.codes(), (
        f"Declared output reference was rejected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_bracket_quoted_a4c29a4b() -> None:
    """Bracket-quoted references can target declared output fields."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference='{{1["email"]}}',
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "semantic.output_field_unknown" not in report.codes(), (
        f"Declared bracket output reference was rejected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_ignores_quoted_output_reference_literals() -> None:
    """Output-contract checks only validate executable expression references."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference='{{if(true; "1.emailTypo"; 1.email)}}',
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    blocked_codes = {
        "semantic.output_field_unknown ",
        "semantic.reference_unknown_node",
    }
    assert not (blocked_codes.intersection(report.codes())), (
        f"Quoted output-reference literal was validated: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_ignores_quoted_unknown_node_literals() -> None:
    """Quoted module-looking text is documentation data inside expressions."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference='{{if(true; "99.email"; 1.email)}}',
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "semantic.reference_unknown_node" not in report.codes(), (
        f"Quoted unknown-node literal was validated: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_bracket_quoted_c426b265() -> None:
    """Bracket-quoted source fields still enforce declared output contracts."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference='{{1["emailTypo"]}}',
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.output_field_unknown" not in report.codes()), (
        f"Unknown bracket output reference was not detected: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_rejects_collapsed_nested_output_reference() -> (
    None
):
    """Declared nested output paths must not match collapsed field names."""
    collapsed_reference = "{{1.payload" + "email}}"
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[
                        {
                            "name": "payload",
                            "fields": [{"name": "email", "type": "text"}],
                            "type": "collection",
                        }
                    ],
                    reference=collapsed_reference,
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not ("semantic.output_field_unknown" not in report.codes()), (
        f"Collapsed nested output path was accepted: {report.codes()}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_keeps_output_reference_finding_ids_distinct() -> (
    None
):
    """Multiple output-reference failures in one field keep distinct finding.

    IDs.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{1.emailTypo}}/{{1.nameTypo}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "semantic.output_field_unknown"
    )
    finding_ids = tuple(finding.finding_id for finding in findings)

    assert len(finding_ids) == REPEATED_OUTPUT_REFERENCE_FAILURES, (
        f"Expected two output-reference findings: {report.findings}"
    )
    assert len(set(finding_ids)) == len(finding_ids), (
        f"Output-reference findings reused IDs: {finding_ids}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_reports_same_unknown_2a519585() -> None:
    """The same bad output reference in different fields keeps both source.

    paths.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{1.emailTypo}}",
                    body_reference="{{1.emailTypo}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "semantic.output_field_unknown"
    )
    finding_ids = tuple(finding.finding_id for finding in findings)

    assert len(finding_ids) == REPEATED_OUTPUT_REFERENCE_FAILURES, (
        f"Expected two path-specific output-reference findings: "
        f"{report.findings}"
    )
    assert len({finding.source_path for finding in findings}) == len(
        findings
    ), f"Output-reference findings lost source-path specificity: {findings}"
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_attaches_nested_output_730a4a3a() -> None:
    """Nested child expressions must not be attributed to their parent.

    router.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "nested-output-reference",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "interface": [{"name": "email", "type": "text"}],
                            "response": {"status": 200},
                        },
                        {
                            "id": 2,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 3,
                                            "module": "http:MakeRequest",
                                            "parameters": {
                                                "method": "POST ",
                                                "url": "{{1.emailTypo}}",
                                            },
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "semantic.output_field_unknown"
    )

    assert tuple(finding.node_id for finding in findings) == ("3",), (
        f"Nested output reference was attributed to the wrong node: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_ignores_documentation_output_e81b() -> None:
    """Documentation examples must not become output-reference blockers."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[{"name": "email", "type": "text"}],
                    reference="{{1.email}}",
                    consumer_metadata_message="Example only: {{1.emailTypo}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    blocked_codes = {
        "semantic.output_field_unknown ",
        "semantic.reference_unknown_node",
    }
    assert not (blocked_codes.intersection(report.codes())), (
        f"Documentation examples were treated as executable: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_blueprint_validator_allows_dynamic_output_children() -> None:
    """Dynamic object output contracts allow child fields below that root."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                output_reference_blueprint(
                    source_interface=[
                        {"name": "payload", "type": "collection"}
                    ],
                    reference="{{1.payload.email}}",
                )
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert "semantic.output_field_unknown" not in report.codes(), (
        f"Dynamic output child reference was rejected: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_handoff_policy_classifies_bindings_and_seed_values() -> None:
    """Handoff policy detects Make bindings and conservative seed values."""
    connection = catalog_field(
        path=("connection",),
        field_type="account:openai-gpt-3",
        raw_schema={"type": "account:openai-gpt-3"},
        required=True,
    )
    hook = catalog_field(
        path=("hook",),
        field_type="webhook",
        raw_schema={"type": "webhook"},
        required=False,
    )
    selector = catalog_field(
        path=("channel",),
        field_type="select",
        raw_schema={
            "options": [
                {"value": "primary", "default": True},
                {"value": "fallback"},
            ]
        },
        rpc_dependencies=("rpc://slack/listChannels",),
        required=False,
    )
    empty_default_selector = catalog_field(
        path=("channel",),
        field_type="select",
        raw_schema={
            "options": [
                {"value": "", "default": True},
                {"value": "primary"},
            ]
        },
        rpc_dependencies=("rpc://slack/listChannels",),
        required=False,
    )
    prompt = catalog_field(
        path=("message",),
        field_type="text",
        raw_schema={},
        required=True,
    )
    number = catalog_field(
        path=("score",),
        field_type="number",
        raw_schema={"type": "number"},
        required=True,
    )

    assert normalize_quality_profile("unknown") == "client_ready", (
        "Unknown quality profiles must fall back to client_ready."
    )
    assert (
        normalize_legacy_policy(None, existing_ast=True) == "preserve_existing"
    ), "Existing AST migration must preserve legacy modules by default."
    assert tuple(
        classify_catalog_field_binding(field)
        for field in (connection, hook, selector, prompt)
    ) == ("connection", "hook", "dynamic_selector", "inline_required"), (
        "Field binding classification drifted."
    )
    assert choose_catalog_field_seed_value(selector) == "primary", (
        "Default options should seed dynamic selector placeholders."
    )
    assert (
        choose_catalog_field_seed_value(empty_default_selector) == "primary"
    ), "Empty default options must not seed dynamic selector placeholders."
    assert (
        choose_catalog_field_seed_value(prompt)
        == "Replace this value with the client-specific instruction."
    ), "Prompt-like fields should receive human-readable seed text."
    assert (
        choose_catalog_field_seed_value(number, export_value=float("nan")) == 1
    ), "Non-finite export values must not become handoff seed values."
    assert is_unresolved_handoff_value("{{PLACEHOLDER_URL}}"), (
        "Placeholder strings must remain unresolved handoff values."
    )
    assert not (is_unresolved_handoff_value("https://example.invalid")), (
        "Concrete scalar exports must not be treated as unresolved."
    )


def test_handoff_policy_treats_empty_json_containers_as_unresolved() -> None:
    """Empty JSON containers remain unresolved until operator data is.

    supplied.
    """
    assert is_unresolved_handoff_value([]), (
        "Empty JSON containers must remain unresolved handoff values."
    )
    assert is_unresolved_handoff_value({}), (
        "Empty JSON containers must remain unresolved handoff values."
    )


def test_handoff_manifest_merges_catalog_backed_replacements() -> None:
    """Handoff manifests expose only client-owned replacements for a.

    blueprint.
    """
    manifest = build_handoff_placeholder_manifest(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "handoff-demo",
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
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST ",
                                "url": "{{PLACEHOLDER_URL}}",
                            },
                        }
                    ],
                }
            )
        ),
        catalog=load_catalog_fixture(),
    )
    by_key = {placeholder.key: placeholder for placeholder in manifest}

    assert tuple(sorted(by_key)) == ("http_connection", "http_url"), (
        f"Unexpected handoff placeholders: {manifest}"
    )
    connection = by_key["http_connection"]
    assert connection.bind_in_make, (
        f"Connection placeholders must be Make bindings: {connection}"
    )
    assert connection.client_supplies_value, (
        f"Connection placeholders must be Make bindings: {connection}"
    )
    assert (
        connection.replacement_paths[0].json_pointer
        == "/flow/0/parameters/connection"
    ), f"Connection replacement path drifted: {connection}"
    url = by_key["http_url"]
    assert url.expected_type == "url", (
        f"URL placeholder should expose safe seed guidance: {url}"
    )
    assert url.seed_value == "https://example.invalid/resource", (
        f"URL placeholder should expose safe seed guidance: {url}"
    )


def test_ai_review_contracts_are_client_supplied_and_exact() -> None:
    """AI review helpers require explicit client coverage for exact content."""
    content = "Client supplied review payload."
    review = build_minimal_content_review(content=content)
    assert validate_content_review(content=content, review=review) == review, (
        "Minimal client review should validate for exact content."
    )

    with pytest.raises(AiReviewError, match="content hash does not match"):
        require_content_review_mismatch_failure(content=content, review=review)
    with pytest.raises(
        AiReviewError, match="Direct server-side AI execution is prohibited"
    ):
        reject_server_side_ai(purpose="handoff review")

    bounded = bounded_review_text("abcdefghij", max_chars=BOUNDED_REVIEW_LIMIT)
    assert not ("[TRUNCATED_FOR_AI_REVIEW:5_CHARS]" not in bounded), (
        f"Bounded review text did not preserve overflow evidence: {bounded}"
    )
    decoded = decode_text_content(
        [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]
    )
    assert decoded == "first\nsecond", f"Text-part decoding drifted: {decoded}"
    extracted = extract_json_object('```json\n{"decision":"accept"}\n```')
    assert extracted == {"decision": "accept"}, (
        f"Fenced JSON extraction drifted: {extracted}"
    )
    with pytest.raises(AiReviewError, match="non-standard JSON constant NaN"):
        _ = extract_json_object('{"decision":"accept","confidence":NaN}')


def test_delivery_mode_and_coverage_regression_are_ordered() -> None:
    """Delivery mode classification separates import, semantic, and handoff.

    blockers.
    """
    reports = (
        validation_report(("module.unresolved", "error")),
        validation_report(("semantic.operation_volume_review", "error")),
        validation_report(("handoff.connection_missing", "error")),
        validation_report(("explain.note", "explanation")),
        validation_report(),
    )
    assert tuple(
        achieved_blueprint_delivery_mode(report) for report in reports
    ) == (
        "invalid ",
        "visual_skeleton ",
        "import_safe_functional ",
        "import_safe_functional ",
        "deploy_ready",
    ), f"Delivery mode classification drifted: {reports}"

    baseline = delivery_coverage(score=0.95)
    current = delivery_coverage(score=0.75)
    assert coverage_regressed(baseline=baseline, current=current), (
        "Coverage regression should be detected when the score drops."
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


def output_reference_blueprint(
    *,
    source_interface: object,
    reference: str,
    body_reference: str = "",
    consumer_metadata_message: str = "",
) -> JsonObject:
    """Return a minimal blueprint with one declared source output reference."""
    consumer_messages: list[object] = []
    if consumer_metadata_message:
        consumer_messages.append({"message": consumer_metadata_message})
    parameters: JsonObject = {
        "method": "POST ",
        "url": f"https://example.invalid/{reference}",
    }
    if body_reference:
        parameters["body"] = body_reference
    return {
        "name": "declared-reference",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "version": 1,
                "interface": source_interface,
                "metadata": {"designer": {"x": 0, "y": 0, "messages": []}},
            },
            {
                "id": 2,
                "module": "http:MakeRequest",
                "version": 1,
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:http:1.0:action:makeRequest"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "1" * 64,
                        "status": "resolved",
                    },
                    "designer": {
                        "x": 300,
                        "y": 0,
                        "messages": consumer_messages,
                    },
                },
                "parameters": parameters,
            },
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def catalog_field(
    *,
    path: tuple[str, ...],
    field_type: str | None,
    raw_schema: JsonObject,
    required: bool,
    rpc_dependencies: tuple[str, ...] = (),
) -> CatalogField:
    """Return a catalog field for handoff policy tests."""
    field_path = ".".join(path)
    return CatalogField(
        field_id=f"field:test:{field_path}",
        module_id="module:test",
        direction="parameter",
        path=path,
        label=path[-1],
        required=required,
        field_type=field_type,
        advanced=None,
        external_id=f"external:{field_path}",
        rpc_dependencies=rpc_dependencies,
        raw_schema=raw_schema,
        constraints=(),
        fingerprint="0" * 64,
    )


def catalog_with_falsy_required_fields() -> CatalogSnapshot:
    """Return a small catalog with required boolean and integer parameters."""
    enabled = catalog_field(
        path=("enabled",),
        field_type="boolean",
        raw_schema={"type": "boolean"},
        required=True,
    )
    count = catalog_field(
        path=("count",),
        field_type="integer",
        raw_schema={"type": "integer"},
        required=True,
    )
    module = CatalogModule(
        module_id="module:test",
        app_version_id="app:test:1.0",
        app_slug="test",
        app_version="1.0",
        module_kind="action",
        internal_name="FalsyRequired",
        display_name="Falsy Required",
        external_id="external:module:test",
        deprecated=False,
        parameters=(enabled, count),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256="0" * 64,
        fingerprint="0" * 64,
    )
    version = CatalogAppVersion(
        app_version_id="app:test:1.0",
        app_id="app:test",
        app_slug="test",
        version="1.0",
        latest=True,
        manifest_version=1,
        modules=(module,),
        raw_spec_sha256="0" * 64,
        fingerprint="0" * 64,
    )
    app = CatalogApp(
        app_id="app:test",
        app_slug="test",
        label="Test",
        external_id="external:app:test",
        deprecated=False,
        versions=(version,),
        fingerprint="0" * 64,
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-04-29T00:00:00Z",
        raw_spec_manifest_sha256="0" * 64,
        apps=(app,),
        fingerprint="0" * 64,
    )


def validation_report(
    finding: tuple[str, str] | None = None,
) -> BlueprintValidationReport:
    """Return a validation report with zero or one finding."""
    findings: tuple[BlueprintValidationFinding, ...] = ()
    if finding is not None:
        code, severity = finding
        findings = (
            BlueprintValidationFinding(
                finding_id=f"finding:{code}",
                severity=cast("BlueprintFindingSeverity", severity),
                code=code,
                node_id="1",
                client_message="Client-safe validation message.",
                internal_message="Internal validation detail.",
            ),
        )
    return BlueprintValidationReport(
        catalog_fingerprint="catalog:test", findings=findings
    )


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


def advanced_webhook_security_knowledge_query() -> KnowledgeStoreQuery:
    """Return a knowledge projection with promoted Advanced Webhooks rules."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-webhook-ip-allowlist-missing",
                domain="webhooks",
                rule_code="webhook.security_ip_allowlist_missing",
                severity="warning",
                description=(
                    "Protected webhooks should declare caller IP allowlists."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-webhook-signature-missing",
                domain="webhooks",
                rule_code="webhook.security_signature_missing",
                severity="warning",
                description=(
                    "Protected webhooks should verify signatures or hashes."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-webhook-sensitive-cleartext",
                domain="webhooks",
                rule_code="webhook.security_sensitive_cleartext",
                severity="warning",
                description=(
                    "Sensitive webhook payloads should declare encryption."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def http_iterator_datastore_knowledge_query() -> KnowledgeStoreQuery:
    """Return the computed result for the caller."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-http-method-url-contract",
                domain="http",
                rule_code="http.method_url_missing",
                severity="warning",
                description=(
                    "HTTP request modules should declare method and URL before "
                    "API use."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-http-parse-response-missing",
                domain="http",
                rule_code="http.parse_response_missing",
                severity="warning",
                description="Structured HTTP API responses should be parsed.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-http-file-upload-body-type",
                domain="http",
                rule_code="http.file_upload_body_type_invalid",
                severity="warning",
                description="File uploads should use multipart/form-data.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-iterator-array-input-missing",
                domain="aggregators",
                rule_code="iterator.array_input_missing",
                severity="warning",
                description="Iterators should map the array they split.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-data-store-delete-recovery-missing",
                domain="data_stores",
                rule_code="data_store.delete_recovery_missing",
                severity="optimization",
                description=(
                    "Data store deletes should declare recovery posture."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def course_completion_knowledge_query() -> KnowledgeStoreQuery:
    """Return knowledge facts for the remaining course promotion batch."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-webhook-payload-contract-missing",
                domain="webhooks",
                rule_code="webhook.payload_contract_missing",
                severity="warning",
                description=(
                    "Payload-receiving webhooks should declare a schema."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-aggregator-source-missing",
                domain="aggregators",
                rule_code="aggregator.source_missing",
                severity="warning",
                description=(
                    "Aggregators should declare the source they consume."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-aggregator-strategy-missing",
                domain="aggregators",
                rule_code="aggregator.strategy_missing",
                severity="warning",
                description=(
                    "Aggregators should declare strategy or output format."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-text-parser-pattern-missing",
                domain="functions",
                rule_code="text_parser.pattern_missing",
                severity="warning",
                description="Regex text parsers should declare a pattern.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-text-parser-input-missing",
                domain="functions",
                rule_code="text_parser.input_missing",
                severity="warning",
                description="Regex text parsers should declare input text.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-http-json-content-type-missing",
                domain="http",
                rule_code="http.json_content_type_missing",
                severity="warning",
                description=(
                    "JSON HTTP bodies should declare JSON content type."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-data-store-write-key-missing",
                domain="data_stores",
                rule_code="data_store.write_key_missing",
                severity="warning",
                description="Data store writes should declare a stable key.",
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-basic-trigger-interface-missing",
                domain="scenario_design",
                rule_code="basic_trigger.interface_missing",
                severity="warning",
                description=(
                    "Basic triggers should declare output bundle fields."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-mcp-tool-contract-missing",
                domain="mcp",
                rule_code="mcp_tool.contract_missing",
                severity="warning",
                description=(
                    "MCP tools should declare input and output contracts."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
            KnowledgeRuleFact(
                rule_id="course-rule-custom-app-schema-contract",
                domain="custom_apps",
                rule_code="custom_app.schema_contract_missing",
                severity="warning",
                description=(
                    "Custom apps should expose schema contract evidence."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def designer_message_knowledge_query() -> KnowledgeStoreQuery:
    """Return a knowledge projection with reviewed designer-message evidence."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        designer_messages=(
            KnowledgeDesignerMessageEvidence(
                finding_id="designer-message-http-url",
                node_id="1",
                module_slug="http:MakeRequest",
                severity="warning",
                message="URL mapping is incomplete.",
                category="mapping",
                field_path="parameters.url",
                review_status="reviewed",
                source_kind="designer_message",
                source_ref=(
                    "make-api:/api/v2/scenarios/112/blueprint?draft=true"
                ),
                fingerprint="designer-message-evidence-http-url",
                adr_anchor=(
                    "001066#repo.make-linter.documented-designer-message-signal"
                ),
            ),
            KnowledgeDesignerMessageEvidence(
                finding_id="designer-message-wrong-module",
                node_id="1",
                module_slug="json:ParseJSON",
                severity="warning",
                message="Wrong module warning must not match.",
                category="mapping",
                field_path="parameters.url",
                review_status="reviewed",
                source_kind="designer_message",
                source_ref=(
                    "make-api:/api/v2/scenarios/112/blueprint?draft=true"
                ),
                fingerprint="designer-message-evidence-wrong-module",
                adr_anchor=(
                    "001066#repo.make-linter.documented-designer-message-signal"
                ),
            ),
        ),
    )


def root_designer_message_knowledge_query() -> KnowledgeStoreQuery:
    """Return a knowledge projection with reviewed root designer-message.

    evidence.
    """
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        designer_messages=(
            KnowledgeDesignerMessageEvidence(
                finding_id="designer-message-root-scenario",
                node_id=None,
                module_slug=None,
                severity="warning",
                message="Scenario-level warning remains active.",
                category="scenario",
                field_path=None,
                review_status="reviewed",
                source_kind="designer_message",
                source_ref=(
                    "make-api:/api/v2/scenarios/112/blueprint?draft=true"
                ),
                fingerprint="designer-message-evidence-root-scenario",
                adr_anchor=(
                    "001066#repo.make-linter.documented-designer-message-signal"
                ),
            ),
        ),
    )


def error_route_knowledge_query() -> KnowledgeStoreQuery:
    """Return the computed result for the caller."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-error-route-missing",
                domain="error_handling",
                rule_code="error_route.missing",
                severity="optimization",
                description=(
                    "Mutating modules should declare deterministic error "
                    "handling paths."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def transaction_safety_knowledge_query() -> KnowledgeStoreQuery:
    """Return a knowledge projection with promoted transaction-safety facts."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:test",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="course-rule-transaction-rollback-posture-missing",
                domain="transactions",
                rule_code="transaction.rollback_posture_missing",
                severity="optimization",
                description=(
                    "Rollback-unsafe mutations should declare recovery, "
                    "idempotency, audit, or compensation posture."
                ),
                adr_anchor=(
                    "001064#repo.make-knowledge.transaction-safety-profiles"
                ),
            ),
        ),
        optimizer_hints=(),
        transaction_profiles=(
            KnowledgeTransactionProfile(
                profile_id="transaction-profile-http-write",
                module_selector_kind="module_token_contains",
                module_selector="http",
                operation_kind="external_write",
                mutates_state=True,
                rollback_capability="external_system",
                acid_compatibility="not_acid",
                safety_level="requires_compensation_posture",
                description="HTTP writes commit outside Make.",
                adr_anchor=(
                    "001064#repo.make-knowledge.transaction-safety-profiles"
                ),
            ),
        ),
    )


def delivery_coverage(*, score: float) -> BlueprintDeliveryCoverage:
    """Return compact delivery coverage for regression tests."""
    return BlueprintDeliveryCoverage(
        catalog_fingerprint="catalog:test",
        delivery_mode="import_safe_functional",
        error_count=0,
        warning_count=0,
        optimization_count=0,
        explanation_count=0,
        handoff_placeholder_count=0,
        client_ready_score=score,
    )


def require_content_review_mismatch_failure(
    *, content: str, review: JsonObject
) -> None:
    """Fail unless content-review validation rejects changed content."""
    invalid_review = validate_content_review(
        content=f"{content} changed", review=review
    )
    failure_message = (
        f"Mismatched review content should be rejected: {invalid_review}"
    )
    assert_unexpected_success(failure_message)


def assert_client_messages_are_path_safe(
    report: BlueprintValidationReport,
) -> None:
    """Fail if any public validation message leaks repository path details."""
    for finding in report.findings:
        leaked_tokens = [
            token
            for token in CLIENT_PATH_TOKENS
            if token in finding.client_message
        ]
        assert not (leaked_tokens), (
            f"Client message leaked path tokens {leaked_tokens}: {finding}"
        )
