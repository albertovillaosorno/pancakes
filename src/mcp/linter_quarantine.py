# ruff: noqa: E501, PLR0913, PLR0914
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite-backed MCP linter quarantine candidate and review evidence tools.

Boundary contract:
- Owns: candidate-only intake, compact quarantine listing, review coverage,
  and promotion state against the Make knowledge SQLite SSOT.
- Must not: activate validation rules, accept linter candidates, modify
taxonomy,
  write decision ledgers, create Markdown side records, call live services, or
  treat JSON/Markdown snapshots as authority.
- Allows: deterministic SQLite writes and derived JSON snapshots for manual
  linter intake evidence.
- Split when: linter decision-ledger writes gain a separate typed command
surface.
- Merge when: another MCP module owns the same quarantine write contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.validation.linter_taxonomy import (
    make_linter_rule_families,
    make_linter_rule_family_by_id,
    make_linter_rule_family_for_code,
    make_linter_supported_codes,
)
from catalog.knowledge import (
    DEFAULT_KNOWLEDGE_DB_PATH,
    KNOWLEDGE_SCHEMA_VERSION,
    build_knowledge_store,
    connect_catalog_plan_ssot,
    knowledge_store_status,
)
from languages.make.raw_specs.paths import resolve_repo_relative_path

if TYPE_CHECKING:
    import sqlite3

    from catalog.knowledge import KnowledgeStoreStatusReport

    from mcp.models import JsonObject

QUARANTINE_ROOT: Final = Path(
    "src/blueprints/validation/data/linter/quarantine"
)
QUARANTINE_MANIFEST_NAME: Final = "manifest.json"
REVIEW_COVERAGE_LEDGER_NAME: Final = "review-coverage.json"
MCP_REVIEW_DIR_NAME: Final = "mcp-review-decisions"
MCP_OWNER_REFERENCE: Final = "mcp:linter.quarantine.write"
QUARANTINE_RECORD_TABLE_NAME: Final = "linter_quarantine_records"
QUARANTINE_REVIEW_TABLE_NAME: Final = "linter_quarantine_review_events"
SQLITE_SOURCE_OF_TRUTH: Final = "sqlite:linter_quarantine_records"
ATOMIC_REPLACE_RETRY_COUNT: Final = 5
ATOMIC_REPLACE_RETRY_DELAY_SECONDS: Final = 0.05
REVIEW_COVERAGE_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "candidate_id",
    "source_file",
    "record_path",
    "review_status",
    "implementation_status",
    "implementation_level",
    "severity_mapping",
    "blocked_reason",
    "reviewed_at",
    "commit_hash",
)
ROUND_ORDER_POLICY: Final[tuple[str, ...]] = (
    "easiest_blockers_first",
    "locally_verifiable_before_external_evidence",
    "low_false_positive_risk_before_high_false_positive_risk",
)
REBUILDABLE_KNOWLEDGE_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "empty_database",
        "missing_database",
    )
)
IMPLEMENTATION_PRESERVE_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "implemented",
        "blocked",
    )
)
INTEGRATION_REVIEW_SOURCE_REF: Final = (
    "operator:2026-05-27-make-quarantine-backlog-review"
)
INTEGRATION_REVIEW_SCHEMA_VERSION: Final = 1
INTEGRATION_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    (
        "not_implemented",
        "implemented",
        "canonical_equivalent",
        "duplicate",
        "invalid",
        "blocked",
    )
)
MIN_DUPLICATE_CANDIDATE_GROUP_SIZE: Final = 2
LEGACY_NON_PREDICATE_QUARANTINE_REASONS: Final[frozenset[str]] = frozenset(
    ("high_false_positive_risk", "impossible_to_verify_locally")
)
GENERIC_REVIEW_SURFACE_PREDICATE_PATTERN: Final = re.compile(
    r"^(?:Compare|Inspect|Parse|Query|Review|Round-trip|Scan)\b",
    re.IGNORECASE,
)
UNMAPPED_DETECTOR_PREDICATE_PATTERN: Final = re.compile(
    r"^Detect\b", re.IGNORECASE
)
CANONICAL_CANDIDATE_EQUIVALENT_PREDICATE_PATTERNS: Final[
    tuple[tuple[re.Pattern[str], str], ...]
] = (
    (
        re.compile(
            r"^Detect cases where A connection is defined\b",
            re.IGNORECASE,
        ),
        "semantic.authentication_required",
    ),
    (
        re.compile(
            r"^Detect cases where A custom app (?:is built|uses an "
            r"external API)\b",
            re.IGNORECASE,
        ),
        "custom_app.schema_contract_missing",
    ),
    (
        re.compile(
            r"^Detect cases where A scenario uses an external app\b",
            re.IGNORECASE,
        ),
        "semantic.authentication_required",
    ),
    (
        re.compile(
            r"^Detect cases where An API response can fail\b",
            re.IGNORECASE,
        ),
        "http.upstream_status_mapping_missing",
    ),
    (
        re.compile(
            r"^Detect cases where The scenario requires retries or recovery\b",
            re.IGNORECASE,
        ),
        "error_route.missing",
    ),
    (
        re.compile(
            r"^(?:Analyze schedule frequency|Estimate operations and "
            r"credits)\b",
            re.IGNORECASE,
        ),
        "optimization.operation_volume_review",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose authentication mode\b",
            re.IGNORECASE,
        ),
        "semantic.authentication_required",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose body type or content type\b",
            re.IGNORECASE,
        ),
        "http.json_content_type_missing",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose downstream mappings "
            r"rely on response fields\b",
            re.IGNORECASE,
        ),
        "http.response_schema_guard_missing",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose endpoint URL\b",
            re.IGNORECASE,
        ),
        "http.method_url_missing",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose method\b",
            re.IGNORECASE,
        ),
        "http.method_url_missing",
    ),
    (
        re.compile(
            r"^Detect HTTP request modules whose required query parameters\b",
            re.IGNORECASE,
        ),
        "http.query_parameter_encoding_missing",
    ),
    (
        re.compile(
            r"^Detect production scenarios without an error handler or "
            r"policy\b",
            re.IGNORECASE,
        ),
        "error_route.missing",
    ),
    (
        re.compile(
            r"^Detect webhook flows without an explicit error-handler\b",
            re.IGNORECASE,
        ),
        "error_route.missing",
    ),
)
INVALID_CANDIDATE_REASON_PATTERNS: Final[
    tuple[tuple[re.Pattern[str], str], ...]
] = (
    (
        re.compile(r"^Assessment validation for ", re.IGNORECASE),
        (
            "assessment validation is a course answer-key check, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^Correct answer:\s+", re.IGNORECASE),
        (
            "correct-answer text is course answer-key content, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^\d+(?:\.\d+)+\s+"),
        (
            "numbered course-section content is training material, not a "
            "Make blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^(?:This was covered|As covered)\b", re.IGNORECASE),
        (
            "course cross-reference content is training material, not a "
            "Make blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^The assessment\b", re.IGNORECASE),
        (
            "assessment description content is course material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(
            r"^Ambiguous extracted candidate requires manual review\.$",
            re.IGNORECASE,
        ),
        (
            "manual-extraction triage text is quarantine workflow metadata, "
            "not a Make "
            "blueprint linter predicate"
        ),
    ),
    (
        re.compile(
            r"^\N{PURPLE HEART} Advantage of using Make\b", re.IGNORECASE
        ),
        (
            "course advantage copy is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(r"^Congrats!$", re.IGNORECASE),
        (
            "standalone course fragment is training material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^The agent\.$", re.IGNORECASE),
        (
            "standalone course fragment is training material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^Your agent asks\.$", re.IGNORECASE),
        (
            "standalone course fragment is training material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^You cannot go on properly\.$", re.IGNORECASE),
        (
            "standalone course fragment is training material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^The data is rejected\.$", re.IGNORECASE),
        (
            "standalone course fragment is training material, not a Make "
            "blueprint "
            "linter predicate"
        ),
    ),
    (
        re.compile(r"^An API \(", re.IGNORECASE),
        (
            "API definition prose is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(
            r"^API (?:endpoints|is like|is a|related errors|response "
            r"contains)\b",
            re.IGNORECASE,
        ),
        (
            "API definition prose is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(r"^Then API is\b", re.IGNORECASE),
        (
            "API definition prose is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(r"^The Make API is\b", re.IGNORECASE),
        (
            "API definition prose is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(r"^The API response contains\b", re.IGNORECASE),
        (
            "API definition prose is training material, not a Make "
            "blueprint linter "
            "predicate"
        ),
    ),
    (
        re.compile(
            r"^(?:Click|Select|Open|Go to|Search "
            r"for|Enter|Save|Drag|Download)\b",
            re.IGNORECASE,
        ),
        (
            "tutorial UI action instruction is training material, not a "
            "Make blueprint "
            "linter predicate"
        ),
    ),
)
LEGACY_SOURCE_FILE_FAMILY_HINTS: Final[dict[str, str]] = {
    "02_security_ingress_http.md": "webhook_http_security",
    "03_reliability_state_concurrency.md": "error_handling_reliability",
    "04_performance_memory_cost.md": "operation_volume_optimization",
    "05_types_schema_data_apps.md": "catalog_resolution",
    "06_topology_blueprint_architecture.md": "route_branch_topology",
    "07_observability_release_governance.md": "scenario_release_governance",
    "08_documentation_surface_linter_rules.md": "designer_layout_handoff",
    "09_quarantine_and_future_families.md": "candidate_rule_discovery",
}
CANONICAL_CANDIDATE_EQUIVALENTS: Final[dict[str, str]] = {
    "BPI-018": "route.id_duplicate",
    "DST-004": "data_store.secret_storage",
    "GQL-006": "graphql.error_array_guard_missing",
    "GQL-007": "graphql.partial_data_guard_missing",
    "GQL-010": "graphql.mutation_idempotency_missing",
    "GQL-011": "graphql.variable_type_declaration_missing",
    "GQL-015": "graphql.schema_version_missing",
    "HTTP-018": "http.api_version_pinning_missing",
    "NET-209": "http.proxy_header_trust_missing",
    "SEC-023": "http.cookie_passthrough_header",
    "TME-006": "schedule.sub_minute_interval",
    "ai_agent.ai_generated_transformations_evidence": (
        "optimization.ai_output_human_review"
    ),
    "ai_agent.agent_process_files_task": (
        "ai_agent.file_processing_capability_missing"
    ),
    "ai_agent.balance_speed_cost_reliability_task_complexity": (
        "optimization.ai_model_size_review"
    ),
    (
        "candidate.ai_agent.goal_least_powerful_model_still_completes_"
        "tasks_accurately"
    ): ("optimization.ai_model_size_review"),
    "candidate.ai_agent.llm_model_follow_best_practice_previous_units_start": (
        "optimization.ai_model_size_review"
    ),
    "ai_agent.clear_so_agent_chooses_correct_tool": (
        "ai_agent.tool_description_unclear"
    ),
    "ai_agent.configure_response_format_output_structure": (
        "ai_agent.response_format_missing"
    ),
    "ai_agent.conversation_id_limit_history": (
        "ai_agent.conversation_memory_policy_missing"
    ),
    "ai_agent.treat_10_replies_course_documented_default": (
        "ai_agent.conversation_history_limit_high"
    ),
    "ai_agent.define_agent_role_behavior": "ai_agent.context_structure_missing",
    "ai_agent.define_boundaries_safety_prohibited_actions": (
        "ai_agent.security_guardrails_missing"
    ),
    "ai_agent.define_clear_objective_role_tools_necessary_knowledge": (
        "ai_agent.objective_missing"
    ),
    "ai_agent.define_user_specific_goal_task": "ai_agent.objective_missing",
    "ai_agent.describe_fields_return_easy_parse_format": (
        "ai_agent.tool_output_missing"
    ),
    "ai_agent.filter_limit_fields_results_passing_agent": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.ai_agents_receive_data_don_need": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.ai_agent_process_fields_don_help_complete_task": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.ai_agent_receives_only_30_relevant_customer_records": (
        "ai_agent.tool_output_filter_missing"
    ),
    (
        "candidate.ai_agent.control_verbosity_need_implement_data_"
        "filtering_strategies_so"
    ): ("ai_agent.tool_output_filter_missing"),
    (
        "candidate.ai_agent.control_what_enters_ai_agent_context_"
        "configuring_tool"
    ): ("ai_agent.tool_output_filter_missing"),
    "candidate.ai_agent.configure_tool_return_only_fields_ai_agent_task": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.data_filtering_strategies_ai_agents_receive_too_many": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.limit_fields_per_result_filter_which_data_fields": (
        "ai_agent.tool_output_filter_missing"
    ),
    "candidate.ai_agent.only_need_provide_fields_relevant_case": (
        "ai_agent.tool_output_filter_missing"
    ),
    (
        "candidate.ai_agent.wastes_context_space_irrelevant_data_forces_"
        "ai_agents"
    ): ("ai_agent.tool_output_filter_missing"),
    "note_content.exclude_fields_agent_need": (
        "ai_agent.tool_output_filter_missing"
    ),
    "ai_agent.give_tools_llm_alone_execute_external_actions": (
        "ai_agent.tools_missing"
    ),
    "ai_agent.limit_control_tokens_costs_relevance": (
        "ai_agent.conversation_history_limit_high"
    ),
    (
        "ai_agent.lower_creativity_deterministic_tasks_raise_only_"
        "variation_needed"
    ): ("ai_agent.deterministic_temperature_high"),
    "ai_agent.measure_accuracy_cost_latency_failures_launch": (
        "ai_agent.production_metrics_missing"
    ),
    "candidate.ai_agent.now_ve_built_agent_tested_component_works_time": (
        "ai_agent.production_metrics_missing"
    ),
    "ai_agent.organize_information_so_only_what_needed_retrieved": (
        "ai_agent.knowledge_retrieval_scope_missing"
    ),
    (
        "candidate.ai_agent.agent_query_knowledge_base_retrieve_relevant_"
        "data_response"
    ): ("ai_agent.knowledge_retrieval_scope_missing"),
    "candidate.ai_agent.upload_team_knowledge_base_task_agent_uses_rag": (
        "ai_agent.knowledge_retrieval_scope_missing"
    ),
    "candidate.ai_agent.knowledge_files_vs_tools_work_files_knowledge_files": (
        "ai_agent.knowledge_retrieval_scope_missing"
    ),
    (
        "candidate.ai_agent.agent_only_retrieves_contracts_inquiry_"
        "automatically_selects_correct"
    ): ("ai_agent.knowledge_retrieval_scope_missing"),
    "ai_agent.connect_relevant_current_knowledge_files_sources": (
        "ai_agent.knowledge_source_missing"
    ),
    "ai_agent.optional_provide_reasonable_default": (
        "ai_agent.optional_parameter_default_missing"
    ),
    "ai_agent.separate_conversation_ids_clear_context": (
        "ai_agent.session_isolation_missing"
    ),
    "ai_agent.mark_clearly_explain_purpose": "ai_agent.tool_contract_missing",
    "ai_agent.return_specific_error_cause_recovery_guidance": (
        "ai_agent.fallback_missing"
    ),
    "ai_agent.testing_tools_logs_varied_test_cases": (
        "ai_agent.test_cases_missing"
    ),
    "candidate.ai_agent.default_timeout_300_seconds_minutes": (
        "ai_agent.apply_300_second_default"
    ),
    "candidate.ai_agent.maximum_timeout_give_agent_600_seconds_10_minutes": (
        "ai_agent.exceed_600_seconds"
    ),
    "candidate.ai_agent.need_set_tool_demand_so_ai_agent_trigger": (
        "ai_agent.tool_not_on_demand"
    ),
    "candidate.ai_agent.prompts_define_fallback_behavior_tool_failure": (
        "ai_agent.fallback_missing"
    ),
    (
        "candidate.ai_agent.prompts_define_fallback_behavior_ambiguous_"
        "instructions"
    ): ("ai_agent.fallback_missing"),
    "candidate.ai_agent.prompts_define_fallback_behavior_missing_data": (
        "ai_agent.fallback_missing"
    ),
    "candidate.ai_agent.prompts_define_fallback_behavior_out_scope_requests": (
        "ai_agent.fallback_missing"
    ),
    "candidate.ai_agent.prompts_define_fallback_behavior_unsafe_requests": (
        "ai_agent.fallback_missing"
    ),
    "candidate.ai_agent.sets_scheduler_demand_which_subscenario_tool": (
        "ai_agent.tool_not_on_demand"
    ),
    (
        "candidate.ai_agent.select_model_first_element_need_define_"
        "building_agent"
    ): ("ai_agent.provider_missing"),
    "candidate.ai_agent.sure_tool_ends_return_output": (
        "ai_agent.tool_output_missing"
    ),
    (
        "candidate.ai_agent.tools_agent_only_write_suggestions_human_"
        "execute_manually"
    ): ("ai_agent.tools_missing"),
    "candidate.ai_agent.test_agent_sure_ready_deployed": (
        "ai_agent.test_cases_missing"
    ),
    "candidate.ai_agent.test_test_real_identify_ai_agent_fails_behaves": (
        "ai_agent.test_cases_missing"
    ),
    (
        "candidate.discovery.check_agent_performs_well_real_world_"
        "conditions_need"
    ): ("ai_agent.test_cases_missing"),
    (
        "candidate.ai_agent.clear_output_definitions_ai_agent_understand_"
        "what_tools"
    ): ("ai_agent.tool_output_missing"),
    "candidate.ai_agent.define_agent_objective_next_thing_need_take_account": (
        "ai_agent.objective_missing"
    ),
    "candidate.ai_agent.define_ai_agent_role_tone_instructions_constraints": (
        "ai_agent.context_structure_missing"
    ),
    "candidate.ai_agent.system_prompt_defines_ai_agent_role": (
        "ai_agent.context_structure_missing"
    ),
    (
        "candidate.ai_agent.instructions_specify_how_want_agent_behave_"
        "managing_tickets"
    ): ("ai_agent.context_structure_missing"),
    (
        "candidate.ai_agent.prompt_engineering_involves_structuring_"
        "clearly_defining_ai_agent"
    ): ("ai_agent.context_structure_missing"),
    (
        "candidate.ai_agent.information_previous_analysis_write_down_"
        "agent_objective_clearly"
    ): ("ai_agent.objective_missing"),
    (
        "candidate.ai_agent.need_give_ai_agent_objective_agent_determine_"
        "necessary"
    ): ("ai_agent.objective_missing"),
    "candidate.ai_agent.llms_come_ai_providers_so_first_need_create": (
        "ai_agent.provider_missing"
    ),
    "candidate.ai_agent.need_create_connection": "ai_agent.provider_missing",
    "candidate.ai_agent.need_connect_ai_provider_get_access_large_language": (
        "ai_agent.provider_missing"
    ),
    "candidate.ai_agent.choosing_ai_provider_need_give_access_llm_so": (
        "ai_agent.provider_missing"
    ),
    "candidate.ai_agent.ai_toolkit_need_connection_ai_provider": (
        "ai_agent.provider_missing"
    ),
    (
        "candidate.ai_agent.added_instructions_define_safe_boundaries_"
        "agent_behavior"
    ): ("ai_agent.security_guardrails_missing"),
    (
        "candidate.ai_agent.never_disclose_personal_information_about_"
        "other_users_even"
    ): ("ai_agent.security_guardrails_missing"),
    (
        "candidate.ai_agent.tools_access_data_perform_actions_beyond_what_"
        "explicitly"
    ): ("ai_agent.security_guardrails_missing"),
    "candidate.ai_agent.specify_what_ai_agent_topics_avoid_actions_take": (
        "ai_agent.security_guardrails_missing"
    ),
    "candidate.ai_agent.actions_tracked_manual_approvals_sensitive_steps": (
        "ai_agent.sensitive_action_approval_missing"
    ),
    (
        "candidate.ai_agent.add_knowledge_file_need_test_agent_retrieve_"
        "information"
    ): ("ai_agent.knowledge_retrieval_test_missing"),
    (
        "candidate.ai_agent.instead_storing_sensitive_customer_data_"
        "knowledge_files_fetch"
    ): ("ai_agent.knowledge_attachment_review"),
    (
        "candidate.ai_agent.risks_linked_knowledge_files_due_information_"
        "stored_unauthorized"
    ): ("ai_agent.knowledge_attachment_review"),
    (
        "candidate.ai_agent.including_descriptions_item_response_format_"
        "helps_ai_agent"
    ): ("ai_agent.response_field_description_missing"),
    "ai_agent.plan_order_dependencies_expected_outputs": (
        "ai_agent.multi_tool_plan_missing"
    ),
    "candidate.ai_agent.plan_include_step_user_review_approve_agent_decision": (
        "ai_agent.mutating_tool_guard_missing"
    ),
    "candidate.ai_agent.process_refunds_confirming_policy_eligibility_first": (
        "ai_agent.mutating_tool_guard_missing"
    ),
    "candidate.ai_agent.process_refunds_500_escalate_manager": (
        "ai_agent.mutating_tool_guard_missing"
    ),
    (
        "candidate.ai_agent.example_invoice_data_management_agent_"
        "processes_invoice_asks"
    ): ("ai_agent.mutating_tool_guard_missing"),
    "ai_agent.request_minimum_inputs_confirm_critical_conditions": (
        "ai_agent.mutating_tool_guard_missing"
    ),
    (
        "candidate.ai_agent.needs_remember_context_across_multiple_"
        "questions_conversation_so"
    ): ("ai_agent.conversation_memory_policy_missing"),
    (
        "candidate.ai_agent.agent_knows_needs_return_output_specific_"
        "format_determined"
    ): ("ai_agent.response_format_missing"),
    "candidate.ai_agent.agent_return_data_matching_specified_structure": (
        "ai_agent.response_format_missing"
    ),
    "candidate.ai_agent.ai_agent_needs_know_what_format_expect_produce": (
        "ai_agent.response_format_missing"
    ),
    "candidate.ai_agent.agent_tools_only_generate_text_cannot_take_actions": (
        "ai_agent.tools_missing"
    ),
    (
        "candidate.ai_agent.include_fallback_instructions_guide_ai_agent_"
        "what_information"
    ): ("ai_agent.fallback_missing"),
    (
        "candidate.ai_agent.add_approval_steps_logs_re_doing_sensitive_"
        "operations"
    ): ("ai_agent.sensitive_action_approval_missing"),
    (
        "candidate.ai_agent.implement_logging_approval_data_filtering_"
        "track_actions_authorization"
    ): ("ai_agent.sensitive_action_approval_missing"),
    (
        "candidate.ai_agent.protects_organization_letting_control_exactly_"
        "what_ai_access"
    ): ("ai_agent.sensitive_action_approval_missing"),
    (
        "transaction_safety.approval_gates_irreversible_externally_"
        "visible_ai_actions"
    ): ("ai_agent.sensitive_action_approval_missing"),
    "candidate.ai_agent.response_format_defines_structure_agent_response": (
        "ai_agent.response_format_missing"
    ),
    (
        "candidate.http.parse_response_really_important_data_retrieve_"
        "converted_presentable"
    ): ("http.parse_response_missing"),
    "candidate.http.http_request_multipart_form_data_want_submit_data": (
        "http.file_upload_body_type_invalid"
    ),
    "http.declare_correct_content_type_send_valid_json": (
        "http.json_content_type_missing"
    ),
    "candidate.transaction_safety.data_store_writes_define_key_strategy": (
        "data_store.write_key_missing"
    ),
    (
        "candidate.transaction_safety.data_store_writes_define_retention_"
        "expectations"
    ): ("data_store.ttl_missing"),
    (
        "candidate.transaction_safety.no_automated_process_restore_"
        "deleted_records"
    ): ("data_store.delete_recovery_missing"),
    "candidate.transaction_safety.unfortunately_no_automated_process_restore_deleted_information_data": (
        "data_store.delete_recovery_missing"
    ),
    (
        "candidate.webhook.reason_sequential_processing_cannot_webhook_"
        "response_present"
    ): ("webhook.sequential_response_conflict"),
    (
        "candidate.webhook.prevent_unauthorized_requests_specify_which_ip_"
        "addresses_allowed"
    ): ("webhook.security_ip_allowlist_missing"),
    "candidate.webhook.note_webhook_request_limit_mb_content_re_returning": (
        "webhook.response_body_size_limit_exceeded"
    ),
    "MEM-012": "webhook.ingress_budget_missing",
    "http.avoid_infinite_loops_clear_stop_condition": (
        "optimization.pagination_stop_condition"
    ),
    "http.encode_key_value_pairs_separate_correctly": (
        "http.query_parameter_encoding_missing"
    ),
    "http.implement_pagination_until_data_retrieved": (
        "optimization.pagination_required"
    ),
    "http.limit_frequency_paginate_handle_429_retries": (
        "http.rate_limit_branch_missing"
    ),
    "http.repeat_until_response_no_next_page_no_data": (
        "optimization.pagination_stop_condition"
    ),
    "http.replace_modify_only_part_existing_object_send_only": (
        "http.patch_semantics_missing"
    ),
    "http.replace_update_complete_object_send_resource_represe": (
        "http.put_replacement_guard_missing"
    ),
    "http.stop_handle_empty_result_valid_condition": (
        "optimization.pagination_stop_condition"
    ),
    "http.treat_server_provider_failure_apply_retry_control_logic": (
        "http.server_error_backoff_missing"
    ),
    "http.treat_request_received_processed_successfully_according_exact_st": (
        "http.success_status_contract_missing"
    ),
    (
        "candidate.http.rule_200_status_code_means_server_received_"
        "processed_request"
    ): ("http.success_status_contract_missing"),
    "http.treat_request_authorization_resource_problem_correct_request": (
        "http.permanent_error_retry_policy"
    ),
    "mapping.close_parentheses_correct_order": "mapping.expression_unbalanced",
    "mapping.verify_field_exists_expected_input_bundle": (
        "semantic.output_field_unknown"
    ),
    "mapping.separate_semicolons_according_syntax_applicable": (
        "mapping.function_argument_count"
    ),
    "setup.declare_inputs_types_optional_status": (
        "custom_app.schema_contract_missing"
    ),
    "setup.fill_field_execution": "mapping.required_parameter_missing",
    "note_content.map_output_schema_so_expose_fields": (
        "http.response_schema_guard_missing"
    ),
    "operation_volume.provide_sample_json_defined_structure": (
        "parse_json.schema_missing"
    ),
    "operation_volume.array_text_numeric_aggregator_according_output": (
        "aggregator.strategy_missing"
    ),
    "operation_volume.map_text_plus_separators_template_readable_output": (
        "aggregator.strategy_missing"
    ),
    "operation_volume.select_correct": "aggregator.source_missing",
    "operation_volume.produce_one_bundle_containing_array": (
        "aggregator.strategy_missing"
    ),
    "candidate.redirect.check_yes_selected_evaluate_states_errors_except_2xx": (
        "http.error_status_evaluation_disabled"
    ),
    "candidate.redirect.redirect_consumer_need_specific_http_status_code_put": (
        "redirect.response_contract_missing"
    ),
    "redirect.redirect_status_code_location_header": (
        "redirect.response_contract_missing"
    ),
    "webhook.expect_send_default_200_accepted_automatically": (
        "optimization.webhook_response_timeout_risk"
    ),
    "webhook.keep_response_body_mb_limit": (
        "webhook.response_body_size_limit_exceeded"
    ),
    "webhook.configure_content_type_headers": (
        "webhook.response_content_type_missing"
    ),
    "candidate.webhook.just_need_add_content_body_response_specify_format": (
        "webhook.response_content_type_missing"
    ),
    "webhook.determine_data_structure_representative_sample": (
        "webhook.payload_contract_missing"
    ),
    (
        "candidate.webhook.needs_determine_data_structure_payload_"
        "received_together_request"
    ): ("webhook.payload_contract_missing"),
    "webhook.webhook_queue_behavior_production": (
        "optimization.webhook_queue_review"
    ),
    "webhook.webhook_payload_shape_production": (
        "webhook.payload_contract_missing"
    ),
    "webhook.webhook_response_timing_production": (
        "optimization.webhook_response_timeout_risk"
    ),
    "webhook.sequential_processing": "webhook.sequential_response_conflict",
    "candidate.operation_volume.aggregators_define": (
        "aggregator.source_missing"
    ),
    "candidate.operation_volume.aggregators_define_output_shape": (
        "aggregator.strategy_missing"
    ),
    "candidate.operation_volume.aggregators_define_grouping_behavior": (
        "aggregator.strategy_missing"
    ),
    (
        "candidate.operation_volume.iterator_data_another_plus_following_"
        "pass_processed_data"
    ): ("iterator.array_input_missing"),
    "candidate.operation_volume.iterators_expected_item_bounds": (
        "iterator.item_limit_missing"
    ),
    "candidate.operation_volume.pagination_loops_explicit_stop_conditions": (
        "optimization.pagination_stop_condition"
    ),
    (
        "error_handling.production_define_rollback_compensation_behavior_"
        "failed_side_effects"
    ): ("scenario.rollback_plan_missing"),
    "error_handling.rollback_compensation_applicable": (
        "transaction.rollback_posture_missing"
    ),
    "APP-SHOPIFY-001": "webhook.security_signature_missing",
    "APP-STRIPE-003": "http.api_version_pinning_missing",
    "APP-STRIPE-004": "webhook.security_signature_missing",
    "APP-TWILIO-002": "webhook.security_signature_missing",
    "REL-007": "scenario.production_debug_marker",
    "SEC-027": "crypto.weak_security_hash",
}
CANONICAL_RULE_EVIDENCE_OVERRIDES: Final[dict[str, tuple[str, str]]] = {
    "aggregator.source_missing": (
        "src/blueprints/validation/validator.py",
        "tests/blueprints/validation/blueprint_validation_contract.py",
    ),
    "aggregator.strategy_missing": (
        "src/blueprints/validation/validator.py",
        "tests/blueprints/validation/blueprint_validation_contract.py",
    ),
    "iterator.array_input_missing": (
        "src/blueprints/validation/validator.py",
        "tests/blueprints/validation/blueprint_validation_contract.py",
    ),
    "iterator.item_limit_missing": (
        "src/blueprints/validation/validator.py",
        "tests/blueprints/validation/blueprint_validation_contract.py",
    ),
    "semantic.output_field_unknown": (
        "src/blueprints/validation/output_contracts.py",
        "tests/blueprints/validation/blueprint_validation_contract.py",
    ),
}
SAFE_CANDIDATE_ID_PATTERN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
)
SECRET_LIKE_TEXT_PATTERN: Final = re.compile(
    r"""
    authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{8,}
    |
    bearer\s+[A-Za-z0-9._~+/=-]{8,}
    |
    (?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password
    )
    ["']?\s*[:=]\s*\S+
    |
    sk-[A-Za-z0-9]{16,}
    """,
    re.IGNORECASE | re.VERBOSE,
)
ACTIVE_RULE_FINAL_STATES: Final[frozenset[str]] = frozenset(
    ("accept", "rewrite", "downgrade", "alias_to_canonical")
)
ALLOWED_FINAL_STATES: Final[frozenset[str]] = frozenset(
    ("quarantine", "needs_evidence", "needs_review")
)
ALLOWED_REVIEW_STATES: Final[frozenset[str]] = frozenset(
    (
        "accepted",
        "implemented",
        "rejected",
        "postponed",
        "blocked",
        "not_implemented",
        "converted_to_todo",
    )
)
EXIT_REVIEW_STATES: Final[frozenset[str]] = frozenset(
    ("implemented", "rejected", "postponed", "converted_to_todo")
)
MANIFEST_PENDING_STATES: Final[frozenset[str]] = frozenset(
    ("quarantine", "needs_evidence", "needs_review")
)
SEVERITY_RANK: Final[dict[str, int]] = {
    "critical": 5,
    "error": 4,
    "warning": 3,
    "advisory_info": 2,
    "info": 1,
}
SEVERITY_ALIASES: Final[dict[str, str]] = {
    "blocker": "error",
    "warn": "warning",
    "advisory": "advisory_info",
    "notice": "info",
}
MIN_DOWNGRADE_JUSTIFICATION_WORDS: Final = 50
WORD_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")


class _QuarantineReviewRecord(NamedTuple):
    """One deterministic quarantine review record render input."""

    candidate_id: str
    review_state: str
    rationale: str
    reviewer: str
    reviewed_at_utc: str
    candidate_path: str
    state_evidence: dict[str, str]


def snapshot_linter_quarantine_review_coverage(
    repo_root: Path,
    *,
    reset_unimplemented: bool = True,
) -> JsonObject:
    """Snapshot every SQLite quarantine record into derived JSON coverage.

    Existing implemented and blocked outcomes are preserved. Unimplemented
    records
    are reset to unreviewed by default so a new `humbe` review round can start
    from a deterministic queue without losing blocker history.

    Returns:
        Snapshot status, counts, and repository-relative path evidence.
    """
    status = _ensure_linter_quarantine_database(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            imported = _import_legacy_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
            )
            if reset_unimplemented:
                _reset_unimplemented_review_state(connection)
            export = _export_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
                reset_unimplemented=reset_unimplemented,
            )
    finally:
        connection.close()
    return {
        "status": "snapshotted",
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": status.database_path,
        "manifest_path": export["manifest_path"],
        "coverage_path": export["coverage_path"],
        "record_count": export["record_count"],
        "manifest_record_count": export["manifest_record_count"],
        "reset_unimplemented": reset_unimplemented,
        "legacy_snapshot_imported_count": imported,
        "required_fields": list(REVIEW_COVERAGE_REQUIRED_FIELDS),
        "live_services_called": False,
    }


def review_linter_quarantine_backlog(
    repo_root: Path,
    *,
    reviewer: str = "codex",
    reviewed_at_utc: str | None = None,
) -> JsonObject:
    """Review every quarantine row into a non-runtime integration disposition.

    This sweep is intentionally conservative: it does not activate rules, does
    not
    claim implementation without existing review evidence, and preserves prior
    blocked reviews as history before reopening actionable records.

    Returns:
        Review counts, duplicate handling, and regenerated snapshot evidence.
    """
    status = _ensure_linter_quarantine_database(repo_root)
    reviewed_at = reviewed_at_utc or _utc_now()
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            imported = _import_legacy_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
            )
            rows = _sqlite_quarantine_rows(connection)
            duplicate_targets = _duplicate_candidate_targets(rows)
            changed_count = 0
            disposition_counts: Counter[str] = Counter()
            for row in rows:
                changed = _apply_integration_review(
                    connection=connection,
                    row=row,
                    duplicate_targets=duplicate_targets,
                    reviewer=reviewer,
                    reviewed_at_utc=reviewed_at,
                )
                if changed:
                    changed_count += 1
                evidence = _evidence_from_row(
                    _sqlite_record_for_candidate(
                        connection=connection,
                        candidate_id=str(
                            _evidence_from_row(row).get("candidate_id")
                            or row[2]
                        ),
                    )
                    or row
                )
                review = _json_mapping(evidence.get("integration_review"))
                disposition_counts[
                    str(review.get("disposition", "missing"))
                ] += 1
            export = _export_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
                reset_unimplemented=False,
            )
            rows_after = _sqlite_quarantine_rows(connection)
    finally:
        connection.close()
    return {
        "status": "reviewed",
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": status.database_path,
        "record_count": len(rows_after),
        "changed_count": changed_count,
        "legacy_snapshot_imported_count": imported,
        "duplicate_count": len(duplicate_targets),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "sqlite_status_counts": dict(
            sorted(Counter(str(row[4]) for row in rows_after).items())
        ),
        "manifest_path": export["manifest_path"],
        "coverage_path": export["coverage_path"],
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_services_called": False,
    }


def list_linter_quarantine_records(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Return compact linter quarantine categories from SQLite.

    Returns:
        Collapsed category and candidate summaries from the SQLite SSOT.
    """
    expand = _optional_bool(arguments, "expand", default=False)
    category_limit = _optional_int(
        arguments, "category_limit", default=20, minimum=1, maximum=100
    )
    record_limit = _optional_int(
        arguments, "record_limit", default=5, minimum=1, maximum=50
    )
    status = _ensure_linter_quarantine_database(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            imported = _import_legacy_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
            )
        records = [
            _manifest_record_from_row(row)
            for row in _sqlite_quarantine_rows(connection)
        ]
    finally:
        connection.close()
    categories = _quarantine_categories(records)
    shown_categories = categories[:category_limit]
    manifest_path = _manifest_path(repo_root=repo_root)
    return {
        "status": "listed" if records else "empty",
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": status.database_path,
        "manifest_path": _repo_relative_path(
            repo_root=repo_root, path=manifest_path
        ),
        "coverage_path": _repo_relative_path(
            repo_root=repo_root,
            path=_coverage_ledger_path(repo_root=repo_root),
        ),
        "legacy_snapshot_imported_count": imported,
        "record_count": len(records),
        "category_count": len(categories),
        "shown_category_count": len(shown_categories),
        "hidden_category_count": max(
            len(categories) - len(shown_categories), 0
        ),
        "expand": expand,
        "record_limit": record_limit,
        "categories": [
            _category_payload(
                category, index=index, expand=expand, record_limit=record_limit
            )
            for index, category in enumerate(shown_categories, start=1)
        ],
        "expansion_options": {
            "expand": "Set expand=true to include numbered candidate records.",
            "category_limit": (
                "Increase category_limit to show more categories."
            ),
            "record_limit": (
                "Increase record_limit to show more records per category."
            ),
        },
        "agent_guidance": (
            "The linter is evidence, not an oracle. This internal "
            "controlled list is for "
            "humbe review rounds; public MCP clients should use "
            "linter.quarantine.write only "
            "for candidate intake. Do not lower severity just to move faster."
        ),
    }


def write_linter_quarantine_record(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Record one candidate-only linter quarantine row in SQLite.

    Returns:
        Candidate-only write status and repository-relative path evidence.
    """
    candidate_id = _required_text(arguments, "candidate_id")
    _ = _candidate_file_name(candidate_id)
    source_file = _safe_source_reference(
        _required_text(arguments, "source_file")
    )
    candidate_title = _required_text(arguments, "candidate_title")
    quarantine_reason = _required_text(arguments, "quarantine_reason")
    missing_evidence = _required_text(arguments, "missing_evidence")
    proposed_predicate_text = _required_text(
        arguments, "proposed_predicate_text"
    )
    final_state = _safe_final_state(_required_text(arguments, "final_state"))
    severity = _severity_fields(arguments)
    severity_mapping = _severity_mapping(severity)
    status = _ensure_linter_quarantine_database(repo_root)
    record_locator = _manifest_record_locator(
        repo_root=repo_root, candidate_id=candidate_id
    )
    evidence: JsonObject = {
        "candidate_id": candidate_id,
        "source_file": source_file,
        "original_heading": candidate_title,
        "quarantine_reason": quarantine_reason,
        "missing_evidence": missing_evidence,
        "proposed_predicate_text": proposed_predicate_text,
        "final_state": _manifest_final_state(final_state),
        "record_path": record_locator,
        "owner_todo": MCP_OWNER_REFERENCE,
        "decision_ledger_anchor": "",
        "origin": "mcp_agent_quarantine_intake",
        "severity_mapping": severity_mapping,
        "technical_justification": severity["technical_justification"],
        "agent_agency": (
            "The linter is evidence, not an oracle. Do not lower rigor "
            "merely to "
            "make a scenario pass faster."
        ),
        "current_review": {},
        "promotion_state": "candidate_quarantined",
    }
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            _ = _import_legacy_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
            )
            _insert_quarantine_record(
                connection=connection,
                repo_root=repo_root,
                candidate_id=candidate_id,
                source_file=source_file,
                severity_mapping=severity_mapping,
                evidence=evidence,
                source_kind="mcp_agent_quarantine_intake",
                source_ref="linter.quarantine.write",
            )
    finally:
        connection.close()
    return {
        "status": "created",
        "candidate_id": candidate_id,
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": status.database_path,
        "record_locator": record_locator,
        "manifest_path": "",
        "coverage_path": "",
        "final_state": final_state,
        "sqlite_record_written": True,
        "manifest_entry_appended": False,
        "coverage_entry_appended": False,
        "manifest_snapshot_written": False,
        "coverage_snapshot_written": False,
        "append_only": False,
        "allowed_write_surfaces": [
            DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        ],
        "candidate_markdown_written": False,
        "severity_mapping": severity_mapping,
        "technical_justification_word_count": _word_count(
            severity["technical_justification"]
        ),
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_services_called": False,
    }


def review_linter_quarantine_record(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Record one deterministic review decision for an existing SQLite record.

    Returns:
        Review status, transition evidence, and repository-relative path proof.

    Raises:
        FileNotFoundError: If the quarantine candidate does not exist.
    """
    candidate_id = _required_text(arguments, "candidate_id")
    review_state = _safe_review_state(_required_text(arguments, "review_state"))
    rationale = _required_text(arguments, "rationale")
    reviewer = _required_text(arguments, "reviewer")
    reviewed_at_utc = _required_text(arguments, "reviewed_at_utc")
    status = _ensure_linter_quarantine_database(repo_root)
    state_evidence = _review_state_evidence(
        arguments, review_state=review_state
    )
    review_path = _review_path(repo_root=repo_root, candidate_id=candidate_id)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            _ = _import_legacy_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
            )
            candidate_row = _sqlite_record_for_candidate(
                connection=connection,
                candidate_id=candidate_id,
            )
            if candidate_row is None:
                message = (
                    f"Quarantine candidate does not exist in SQLite:"
                    f"{candidate_id}"
                )
                raise FileNotFoundError(message)
            candidate_record = _manifest_record_from_row(candidate_row)
            candidate_locator = str(
                candidate_record.get("record_path", "")
            ) or _manifest_record_locator(
                repo_root=repo_root,
                candidate_id=candidate_id,
            )
            payload = _review_payload(
                _QuarantineReviewRecord(
                    candidate_id=candidate_id,
                    review_state=review_state,
                    rationale=rationale,
                    reviewer=reviewer,
                    reviewed_at_utc=reviewed_at_utc,
                    candidate_path=candidate_locator,
                    state_evidence=state_evidence,
                )
            )
            review_event_id = _insert_review_event(
                connection=connection,
                candidate_id=candidate_id,
                review_state=review_state,
                payload=payload,
                source_ref=_repo_relative_path(
                    repo_root=repo_root, path=review_path
                ),
                implementation_level=_optional_text(
                    arguments, "implementation_level"
                )
                or None,
                commit_hash=_optional_text(arguments, "commit_hash"),
            )
            _update_quarantine_review_state(
                connection=connection,
                candidate_id=candidate_id,
                review_state=review_state,
                payload=payload,
                review_path=_repo_relative_path(
                    repo_root=repo_root, path=review_path
                ),
                implementation_level=_optional_text(
                    arguments, "implementation_level"
                )
                or None,
                commit_hash=_optional_text(arguments, "commit_hash"),
            )
            payload["source_of_truth"] = SQLITE_SOURCE_OF_TRUTH
            payload["sqlite_review_event_id"] = review_event_id
            payload["sqlite_quarantine_id"] = _quarantine_id(candidate_id)
            _write_json_atomically(review_path, payload)
            export = _export_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
                reset_unimplemented=False,
            )
    finally:
        connection.close()
    return {
        "status": "reviewed",
        "candidate_id": candidate_id,
        "review_state": review_state,
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": status.database_path,
        "sqlite_review_event_id": review_event_id,
        "candidate_path": payload["candidate_path"],
        "review_path": _repo_relative_path(
            repo_root=repo_root, path=review_path
        ),
        "coverage_path": export["coverage_path"],
        "coverage_entry_appended": False,
        "coverage_snapshot_written": True,
        "leaves_quarantine": payload["leaves_quarantine"],
        "allowed_exit_reason": payload["allowed_exit_reason"],
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_services_called": False,
    }


def _ensure_linter_quarantine_database(
    repo_root: Path,
) -> KnowledgeStoreStatusReport:
    """Ensure the Make knowledge SQLite database can own quarantine state.

    Returns:
        Current knowledge-store status after any safe schema setup.

    Raises:
        ValueError: If the database is unavailable or cannot be migrated safely.
    """
    status = knowledge_store_status(repo_root=repo_root)
    if status.status in REBUILDABLE_KNOWLEDGE_STATUSES:
        _ = build_knowledge_store(repo_root=repo_root)
        status = knowledge_store_status(repo_root=repo_root)
    if status.status == "stale_schema":
        _migrate_linter_quarantine_schema(repo_root)
        status = knowledge_store_status(repo_root=repo_root)
    if status.status == "stale_schema":
        commands = ", ".join(status.recommended_commands)
        message = (
            "Make knowledge SQLite schema is stale; refusing linter "
            "quarantine writes until "
            f"schema is rebuilt. Recommended command: {commands}"
        )
        raise ValueError(message)
    if not status.database_available:
        message = f"Make knowledge SQLite is unavailable: {status.status}"
        raise ValueError(message)
    if _linter_quarantine_tables_missing(repo_root):
        _migrate_linter_quarantine_schema(repo_root)
    _require_linter_quarantine_tables(repo_root)
    return status


def _migrate_linter_quarantine_schema(repo_root: Path) -> None:
    """Apply the non-destructive linter quarantine schema extension in place."""
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            _ensure_linter_quarantine_tables_sql(connection)
            _ = connection.execute(
                """
                INSERT OR REPLACE INTO snapshot_metadata (key, value)
                VALUES ('schema_version', ?)
                """,
                (str(KNOWLEDGE_SCHEMA_VERSION),),
            )
    finally:
        connection.close()


def _require_linter_quarantine_tables(repo_root: Path) -> None:
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    missing = _linter_quarantine_tables_missing(repo_root)
    if missing:
        message = (
            f"Linter quarantine tables missing from SQLite SSOT"
            f"{database_path}: {missing}"
        )
        raise ValueError(message)


def _linter_quarantine_tables_missing(repo_root: Path) -> list[str]:
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        return [
            table_name
            for table_name in (
                QUARANTINE_RECORD_TABLE_NAME,
                QUARANTINE_REVIEW_TABLE_NAME,
            )
            if connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table_name,),
            ).fetchone()
            is None
        ]
    finally:
        connection.close()


def _ensure_linter_quarantine_tables_sql(
    connection: sqlite3.Connection,
) -> None:
    """Create the linter quarantine tables and indexes without touching other.

    facts.
    """
    _ = connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS linter_quarantine_records (
          quarantine_id TEXT PRIMARY KEY,
          subject_kind TEXT NOT NULL,
          subject_ref TEXT NOT NULL,
          finding_code TEXT NOT NULL,
          severity TEXT NOT NULL,
          status TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL,
          resolved_at_utc TEXT
        );

        CREATE TABLE IF NOT EXISTS linter_quarantine_review_events (
          review_event_id TEXT PRIMARY KEY,
          quarantine_id TEXT NOT NULL,
          review_state TEXT NOT NULL,
          implementation_status TEXT NOT NULL,
          implementation_level TEXT,
          blocked_reason TEXT NOT NULL,
          review_payload_json TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          reviewed_at_utc TEXT NOT NULL,
          commit_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS linter_rule_surface_matrix (
          family_id TEXT PRIMARY KEY,
          rule_surface TEXT NOT NULL,
          owner_path TEXT NOT NULL,
          code_predicate_sources_json TEXT NOT NULL,
          sqlite_predicate_sources_json TEXT NOT NULL,
          source_tables_json TEXT NOT NULL,
          source_files_json TEXT NOT NULL,
          promoted_code_count INTEGER NOT NULL,
          output_affecting INTEGER NOT NULL,
          fingerprint TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT
        );

        CREATE TABLE IF NOT EXISTS linter_data_source_inventory (
          inventory_id TEXT PRIMARY KEY,
          source_path TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          authority_state TEXT NOT NULL,
          sqlite_table TEXT NOT NULL,
          consumed_policy TEXT NOT NULL,
          source_of_truth TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          fingerprint TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_linter_quarantine_records_status
          ON linter_quarantine_records (status, severity, finding_code);

        CREATE INDEX IF NOT EXISTS idx_linter_quarantine_review_events_record
          ON linter_quarantine_review_events (quarantine_id, reviewed_at_utc);

        CREATE INDEX IF NOT EXISTS idx_linter_rule_surface_matrix_surface
          ON linter_rule_surface_matrix (rule_surface, owner_path);

        CREATE INDEX IF NOT EXISTS idx_linter_data_source_inventory_authority
          ON linter_data_source_inventory (authority_state, sqlite_table);
        """
    )


def _import_legacy_quarantine_snapshots(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
) -> int:
    """Import legacy manifest and coverage snapshots into SQLite when needed.

    Returns:
        Count of manifest records inserted into SQLite.
    """
    manifest_path = _manifest_path(repo_root=repo_root)
    if not manifest_path.is_file():
        return 0
    manifest_payload = _load_json_object(
        manifest_path, default=_empty_manifest_payload()
    )
    manifest_records = _records_from_payload(manifest_payload)
    imported = 0
    for record in manifest_records:
        candidate_id = str(record.get("candidate_id", "")).strip()
        if not candidate_id or _sqlite_record_for_candidate(
            connection=connection,
            candidate_id=candidate_id,
        ):
            continue
        severity_mapping = _coverage_severity_mapping(record)
        evidence = _legacy_manifest_evidence(record)
        _insert_quarantine_record(
            connection=connection,
            repo_root=repo_root,
            candidate_id=candidate_id,
            source_file=str(record.get("source_file", ""))
            or "legacy/quarantine",
            severity_mapping=severity_mapping,
            evidence=evidence,
            source_kind="legacy_quarantine_snapshot",
            source_ref=_repo_relative_path(
                repo_root=repo_root, path=manifest_path
            ),
        )
        imported += 1
    _import_legacy_coverage_snapshot(connection=connection, repo_root=repo_root)
    return imported


def _import_legacy_coverage_snapshot(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
) -> None:
    coverage_path = _coverage_ledger_path(repo_root=repo_root)
    if not coverage_path.is_file():
        return
    payload = _load_json_object(
        coverage_path, default=_empty_coverage_payload()
    )
    for coverage_record in _records_from_payload(payload):
        candidate_id = str(coverage_record.get("candidate_id", "")).strip()
        if not candidate_id:
            continue
        row = _sqlite_record_for_candidate(
            connection=connection, candidate_id=candidate_id
        )
        if row is None:
            continue
        evidence = _evidence_from_row(row)
        review_state = _coverage_review_status(coverage_record)
        implementation_status = _coverage_implementation_status(coverage_record)
        if review_state:
            evidence["current_review"] = {
                "review_state": review_state,
                "implementation_status": implementation_status,
                "implementation_level": _coverage_implementation_level(
                    coverage_record
                ),
                "blocked_reason": _coverage_text(
                    coverage_record, "blocked_reason"
                ),
                "reviewed_at": _coverage_text(coverage_record, "reviewed_at"),
                "commit_hash": _coverage_text(coverage_record, "commit_hash"),
                "review_path": _coverage_text(coverage_record, "review_path"),
                "coverage_event": _coverage_text(
                    coverage_record, "coverage_event"
                )
                or "legacy_coverage_import",
            }
        evidence["review_coverage"] = coverage_record
        _update_sqlite_evidence(
            connection=connection,
            candidate_id=candidate_id,
            evidence=evidence,
            status=_record_status_from_evidence(evidence),
            resolved_at_utc=_resolved_at_for_evidence(evidence),
        )


def _legacy_manifest_evidence(record: Mapping[str, object]) -> JsonObject:
    return {
        "candidate_id": str(record.get("candidate_id", "")),
        "source_file": str(record.get("source_file", "")),
        "original_heading": str(record.get("original_heading", "")),
        "quarantine_reason": str(record.get("quarantine_reason", "")),
        "missing_evidence": str(record.get("missing_evidence", "")),
        "proposed_predicate_text": str(
            record.get("proposed_predicate_text", "")
        ),
        "final_state": str(record.get("final_state", "")) or "kept_quarantined",
        "record_path": str(record.get("record_path", "")),
        "owner_todo": str(record.get("owner_todo", "")),
        "decision_ledger_anchor": str(record.get("decision_ledger_anchor", "")),
        "origin": str(record.get("origin", "")) or "legacy_quarantine_snapshot",
        "severity_mapping": _coverage_severity_mapping(record),
        "technical_justification": str(
            record.get("technical_justification", "")
        ),
        "agent_agency": str(record.get("agent_agency", "")),
        "current_review": {},
        "promotion_state": "candidate_quarantined",
    }


def _insert_quarantine_record(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
    candidate_id: str,
    source_file: str,
    severity_mapping: Mapping[str, object],
    evidence: JsonObject,
    source_kind: str,
    source_ref: str,
) -> None:
    if (
        _sqlite_record_for_candidate(
            connection=connection, candidate_id=candidate_id
        )
        is not None
    ):
        message = (
            "linter.quarantine.write is SQLite-owned and cannot duplicate"
            "candidate_id."
        )
        raise ValueError(message)
    observed_at_utc = _utc_now()
    quarantine_id = _quarantine_id(candidate_id)
    severity = _record_severity(severity_mapping)
    evidence = dict(evidence)
    evidence["sqlite_quarantine_id"] = quarantine_id
    evidence["source_of_truth"] = SQLITE_SOURCE_OF_TRUTH
    evidence["database_path"] = _repo_relative_path(
        repo_root=repo_root,
        path=resolve_repo_relative_path(repo_root, DEFAULT_KNOWLEDGE_DB_PATH),
    )
    _ = connection.execute(
        """
        INSERT INTO linter_quarantine_records (
        quarantine_id, subject_kind, subject_ref, finding_code, severity,
        status,
        evidence_json, source_kind, source_ref, created_at_utc, updated_at_utc,
        resolved_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quarantine_id,
            "make_scenario_linter_candidate",
            source_file,
            candidate_id,
            severity,
            _record_status_from_evidence(evidence),
            _canonical_json_text(evidence),
            source_kind,
            source_ref,
            observed_at_utc,
            observed_at_utc,
            _resolved_at_for_evidence(evidence),
        ),
    )


def _insert_review_event(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    review_state: str,
    payload: JsonObject,
    source_ref: str,
    implementation_level: str | None,
    commit_hash: str,
) -> str:
    review_event_id = _stable_id(
        "linter-quarantine-review",
        candidate_id,
        review_state,
        str(payload.get("reviewed_at_utc", "")),
        str(payload.get("reviewer", "")),
        str(payload.get("rationale", "")),
    )
    implementation_status = _implementation_status_for_review(review_state)
    state_evidence = _json_mapping(payload.get("state_evidence"))
    blocked_reason = ""
    if state_evidence:
        blocked_reason = str(state_evidence.get("blocker_summary", ""))
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO linter_quarantine_review_events (
          review_event_id, quarantine_id, review_state, implementation_status,
        implementation_level, blocked_reason, review_payload_json, source_kind,
          source_ref, reviewed_at_utc, commit_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_event_id,
            _quarantine_id(candidate_id),
            review_state,
            implementation_status,
            implementation_level,
            blocked_reason,
            _canonical_json_text(payload),
            "mcp_linter_quarantine_review",
            source_ref,
            str(payload.get("reviewed_at_utc", "")),
            commit_hash,
        ),
    )
    return review_event_id


def _update_quarantine_review_state(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    review_state: str,
    payload: JsonObject,
    review_path: str,
    implementation_level: str | None,
    commit_hash: str,
) -> None:
    row = _sqlite_record_for_candidate(
        connection=connection, candidate_id=candidate_id
    )
    if row is None:
        message = f"Unknown quarantine candidate: {candidate_id}"
        raise ValueError(message)
    evidence = _evidence_from_row(row)
    state_evidence = _json_mapping(payload.get("state_evidence"))
    blocked_reason = ""
    if state_evidence:
        blocked_reason = str(state_evidence.get("blocker_summary", ""))
    evidence["current_review"] = {
        "review_state": review_state,
        "implementation_status": _implementation_status_for_review(
            review_state
        ),
        "implementation_level": implementation_level,
        "blocked_reason": blocked_reason,
        "reviewed_at": str(payload.get("reviewed_at_utc", "")),
        "commit_hash": commit_hash,
        "review_path": review_path,
        "coverage_event": "review_recorded",
    }
    evidence["promotion_state"] = _promotion_state_for_review(review_state)
    _update_sqlite_evidence(
        connection=connection,
        candidate_id=candidate_id,
        evidence=evidence,
        status=_record_status_from_evidence(evidence),
        resolved_at_utc=_resolved_at_for_evidence(evidence),
    )


def _reset_unimplemented_review_state(connection: sqlite3.Connection) -> None:
    for row in _sqlite_quarantine_rows(connection):
        evidence = _evidence_from_row(row)
        current_review = _json_mapping(evidence.get("current_review"))
        if not current_review:
            continue
        implementation_status = str(
            current_review.get("implementation_status", "")
        )
        if implementation_status in IMPLEMENTATION_PRESERVE_STATUSES:
            continue
        evidence["current_review"] = {}
        evidence["promotion_state"] = "candidate_quarantined"
        _update_sqlite_evidence(
            connection=connection,
            candidate_id=str(evidence.get("candidate_id", "")),
            evidence=evidence,
            status="quarantined",
            resolved_at_utc=None,
        )


def _apply_integration_review(
    *,
    connection: sqlite3.Connection,
    row: tuple[object, ...],
    duplicate_targets: Mapping[str, str],
    reviewer: str,
    reviewed_at_utc: str,
) -> bool:
    evidence = _evidence_from_row(row)
    candidate_id = str(evidence.get("candidate_id") or row[2])
    previous_text = _canonical_json_text(evidence)
    current_review = _json_mapping(evidence.get("current_review"))
    integration_review = _integration_review_for_row(
        row=row,
        duplicate_targets=duplicate_targets,
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
    )
    disposition = str(integration_review["disposition"])
    evidence["integration_review"] = integration_review
    if _is_active_blocked_review(current_review) and disposition != "blocked":
        _append_review_history(
            evidence=evidence,
            current_review=current_review,
            reviewed_at_utc=reviewed_at_utc,
            transition_reason=f"reclassified_as_{disposition}",
        )
    if disposition == "not_implemented":
        evidence["current_review"] = {}
        evidence["promotion_state"] = "candidate_quarantined"
        status = "quarantined"
    elif disposition == "duplicate":
        evidence["current_review"] = _synthetic_exit_review(
            review_state="rejected",
            reviewed_at_utc=reviewed_at_utc,
            coverage_event="duplicate_integration_review",
        )
        evidence["promotion_state"] = "candidate_rejected_duplicate"
        status = "rejected"
    elif disposition == "invalid":
        evidence["current_review"] = _synthetic_exit_review(
            review_state="rejected",
            reviewed_at_utc=reviewed_at_utc,
            coverage_event="invalid_integration_review",
        )
        evidence["promotion_state"] = "candidate_rejected_invalid"
        status = "rejected"
    elif disposition == "canonical_equivalent":
        evidence["current_review"] = _synthetic_exit_review(
            review_state="implemented",
            reviewed_at_utc=reviewed_at_utc,
            coverage_event="canonical_equivalent_integration_review",
            implementation_level="exact",
        )
        evidence["promotion_state"] = (
            "candidate_implemented_by_canonical_equivalent"
        )
        status = "implemented"
    else:
        status = _record_status_from_evidence(evidence)
    changed = (
        previous_text != _canonical_json_text(evidence) or str(row[4]) != status
    )
    if changed:
        _update_sqlite_evidence(
            connection=connection,
            candidate_id=candidate_id,
            evidence=evidence,
            status=status,
            resolved_at_utc=_resolved_at_for_evidence(evidence),
        )
    return changed


def _integration_review_for_row(
    *,
    row: tuple[object, ...],
    duplicate_targets: Mapping[str, str],
    reviewer: str,
    reviewed_at_utc: str,
) -> JsonObject:
    evidence = _evidence_from_row(row)
    candidate_id = str(evidence.get("candidate_id") or row[2])
    finding_code = str(row[2])
    current_review = _json_mapping(evidence.get("current_review"))
    previous_blocked_reason = str(current_review.get("blocked_reason", ""))
    source_file = str(evidence.get("source_file") or row[1])
    duplicate_target = duplicate_targets.get(candidate_id)
    if duplicate_target:
        return _integration_review_payload(
            candidate_id=candidate_id,
            disposition="duplicate",
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            explanation=(
                f"{candidate_id} is a duplicate quarantine statement of "
                f"{duplicate_target}; "
                "the duplicate is closed without writing a runtime rule."
            ),
            previous_blocked_reason=previous_blocked_reason,
            canonical_candidate_id=duplicate_target,
            family_id=_family_id_for_record(evidence=evidence),
        )
    canonical_equivalent_code = _canonical_equivalent_code_for_record(
        finding_code=finding_code,
        evidence=evidence,
    )
    if canonical_equivalent_code:
        return _canonical_equivalent_integration_review(
            candidate_id=candidate_id,
            canonical_rule_code=canonical_equivalent_code,
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            previous_blocked_reason=previous_blocked_reason,
        )
    if finding_code in set(make_linter_supported_codes()):
        return _canonical_equivalent_integration_review(
            candidate_id=candidate_id,
            canonical_rule_code=finding_code,
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            previous_blocked_reason=previous_blocked_reason,
        )
    if str(current_review.get("implementation_status", "")) == "implemented":
        return _integration_review_payload(
            candidate_id=candidate_id,
            disposition="implemented",
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            explanation=(
                f"{candidate_id} already has implemented review evidence; "
                f"this sweep "
                "preserves that implementation state and does not write a "
                "new rule."
            ),
            previous_blocked_reason=previous_blocked_reason,
            family_id=_family_id_for_record(evidence=evidence),
            implementation_reference=str(current_review.get("commit_hash", "")),
        )
    invalid_reason = _invalid_candidate_reason(evidence)
    if invalid_reason:
        return _integration_review_payload(
            candidate_id=candidate_id,
            disposition="invalid",
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            explanation=(
                f"{candidate_id} is rejected as invalid for the Make linter "
                f"quarantine: "
                f"{invalid_reason}."
            ),
            previous_blocked_reason=previous_blocked_reason,
            family_id=_family_id_for_record(evidence=evidence),
            source_evidence=[SQLITE_SOURCE_OF_TRUTH, source_file],
        )
    family_id = _family_id_for_record(evidence=evidence)
    family = _safe_family_payload(family_id)
    if family:
        explanation = (
            f"{candidate_id} remains valid/actionable but not implemented: "
            f"it is scoped to "
            f"Make linter family {family_id}, has SQLite quarantine "
            f"evidence, and still "
            "needs an exact local predicate plus fixture evidence before "
            "runtime activation."
        )
        source_evidence = [
            SQLITE_SOURCE_OF_TRUTH,
            str(family["owner_path"]),
            str(family["focused_test_path"]),
        ]
    else:
        explanation = (
            f"{candidate_id} remains valid/actionable but not implemented: "
            f"source "
            f"{source_file} is preserved as quarantine evidence, while no "
            f"exact local "
            "predicate or fixture has been written."
        )
        source_evidence = [SQLITE_SOURCE_OF_TRUTH, source_file]
    return _integration_review_payload(
        candidate_id=candidate_id,
        disposition="not_implemented",
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        explanation=explanation,
        previous_blocked_reason=previous_blocked_reason,
        family_id=family_id,
        source_evidence=source_evidence,
    )


def _canonical_equivalent_integration_review(
    *,
    candidate_id: str,
    canonical_rule_code: str,
    reviewer: str,
    reviewed_at_utc: str,
    previous_blocked_reason: str,
) -> JsonObject:
    family = make_linter_rule_family_for_code(canonical_rule_code)
    implementation_reference, validation_reference = (
        CANONICAL_RULE_EVIDENCE_OVERRIDES.get(
            canonical_rule_code,
            (family.owner_path, family.focused_test_path),
        )
    )
    return _integration_review_payload(
        candidate_id=candidate_id,
        disposition="canonical_equivalent",
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        explanation=(
            f"{candidate_id} is covered by canonical Make linter code "
            f"{canonical_rule_code} "
            f"in family {family.family_id}; no duplicate runtime rule is "
            f"written."
        ),
        previous_blocked_reason=previous_blocked_reason,
        family_id=family.family_id,
        canonical_rule_code=canonical_rule_code,
        implementation_reference=implementation_reference,
        validation_reference=validation_reference,
    )


def _canonical_equivalent_code_for_record(
    *,
    finding_code: str,
    evidence: Mapping[str, object],
) -> str:
    """Return the supported rule code that already covers a candidate."""
    canonical_equivalent_code = CANONICAL_CANDIDATE_EQUIVALENTS.get(
        finding_code, ""
    )
    if canonical_equivalent_code:
        return canonical_equivalent_code
    proposed_predicate = str(
        evidence.get("proposed_predicate_text", "")
    ).strip()
    for (
        pattern,
        canonical_code,
    ) in CANONICAL_CANDIDATE_EQUIVALENT_PREDICATE_PATTERNS:
        if pattern.search(proposed_predicate):
            return canonical_code
    return ""


def _integration_review_payload(
    *,
    candidate_id: str,
    disposition: str,
    reviewer: str,
    reviewed_at_utc: str,
    explanation: str,
    previous_blocked_reason: str,
    family_id: str,
    canonical_rule_code: str = "",
    canonical_candidate_id: str = "",
    implementation_reference: str = "",
    validation_reference: str = "",
    source_evidence: list[str] | None = None,
) -> JsonObject:
    if disposition not in INTEGRATION_DISPOSITIONS:
        message = f"Unsupported integration review disposition: {disposition!r}"
        raise ValueError(message)
    payload: JsonObject = {
        "schema_version": INTEGRATION_REVIEW_SCHEMA_VERSION,
        "review_source": INTEGRATION_REVIEW_SOURCE_REF,
        "candidate_id": candidate_id,
        "disposition": disposition,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at_utc,
        "explanation": explanation,
        "family_id": family_id,
        "previous_blocked_reason": previous_blocked_reason,
        "runtime_activation": "none",
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_services_called": False,
    }
    if canonical_rule_code:
        payload["canonical_rule_code"] = canonical_rule_code
    if canonical_candidate_id:
        payload["canonical_candidate_id"] = canonical_candidate_id
    if implementation_reference:
        payload["implementation_reference"] = implementation_reference
    if validation_reference:
        payload["validation_reference"] = validation_reference
    if source_evidence:
        payload["source_evidence"] = source_evidence
    return payload


def _duplicate_candidate_targets(
    rows: list[tuple[object, ...]],
) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for row in rows:
        evidence = _evidence_from_row(row)
        candidate_id = str(evidence.get("candidate_id") or row[2])
        key = _normalized_candidate_rule_text(evidence)
        if not key:
            continue
        groups.setdefault(key, []).append(candidate_id)
    targets: dict[str, str] = {}
    for candidate_ids in groups.values():
        if len(candidate_ids) < MIN_DUPLICATE_CANDIDATE_GROUP_SIZE:
            continue
        canonical_id = min(candidate_ids, key=_duplicate_candidate_sort_key)
        for candidate_id in candidate_ids:
            if candidate_id != canonical_id:
                targets[candidate_id] = canonical_id
    return targets


def _duplicate_candidate_sort_key(candidate_id: str) -> tuple[int, str]:
    if candidate_id.startswith(("GOV-", "SEC-", "HTTP-", "WHK-")):
        return (0, candidate_id)
    return (1, candidate_id)


def _normalized_candidate_rule_text(evidence: Mapping[str, object]) -> str:
    text = _candidate_rule_text(evidence).casefold().replace("\u2014", "-")
    text = re.sub(r"^[a-z0-9._-]+\s*-\s*", "", text)
    text = re.sub(
        r"^(error|warning|info|optimization|quarantine)\s*-\s*", "", text
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _candidate_rule_text(evidence: Mapping[str, object]) -> str:
    for key in (
        "candidate_rule",
        "original_heading",
        "proposed_predicate_text",
    ):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _invalid_candidate_reason(evidence: Mapping[str, object]) -> str:
    """Return why a candidate is outside the Make linter rule domain."""
    text = _candidate_rule_text(evidence)
    if not text:
        return ""
    proposed_predicate = str(
        evidence.get("proposed_predicate_text", "")
    ).strip()
    reason = ""
    if (
        str(evidence.get("origin", "")) == "legacy_quarantine_snapshot"
        and not proposed_predicate
        and str(evidence.get("quarantine_reason", ""))
        in LEGACY_NON_PREDICATE_QUARANTINE_REASONS
    ):
        reason = (
            "legacy quarantine evidence records no deterministic predicate "
            "and classifies "
            "the row as locally unsafe to promote, so it cannot be promoted "
            "as a Make "
            "blueprint linter rule without a new source-backed predicate"
        )
    elif proposed_predicate.rstrip(".").casefold() == "manual_review_required":
        reason = (
            "manual-review extraction has no executable predicate and the "
            "source text is "
            "not backed by an exact Make blueprint linter invariant"
        )
    elif GENERIC_REVIEW_SURFACE_PREDICATE_PATTERN.search(proposed_predicate):
        reason = (
            "the proposed predicate names only a review surface or "
            "validation strategy, "
            "not an exact failing condition that can run as a Make "
            "blueprint linter rule"
        )
    elif UNMAPPED_DETECTOR_PREDICATE_PATTERN.search(proposed_predicate):
        reason = (
            "the proposed detector is not mapped to a supported Pancakes "
            "rule code and "
            "does not provide enough exact local predicate evidence for "
            "runtime activation"
        )
    else:
        for pattern, pattern_reason in INVALID_CANDIDATE_REASON_PATTERNS:
            if pattern.search(text):
                reason = pattern_reason
                break
    return reason


def _is_active_blocked_review(current_review: Mapping[str, object]) -> bool:
    return (
        str(current_review.get("review_state", "")) == "blocked"
        or str(current_review.get("implementation_status", "")) == "blocked"
    )


def _append_review_history(
    *,
    evidence: JsonObject,
    current_review: Mapping[str, object],
    reviewed_at_utc: str,
    transition_reason: str,
) -> None:
    if not current_review:
        return
    raw_history = evidence.get("review_history")
    history: list[JsonObject] = []
    if isinstance(raw_history, list):
        raw_history_items = cast("list[object]", raw_history)
        history = [
            _mapping_to_json_object(cast("Mapping[object, object]", item))
            for item in raw_history_items
            if isinstance(item, Mapping)
        ]
    entry: JsonObject = {
        "archived_at_utc": reviewed_at_utc,
        "transition_reason": transition_reason,
        "review": dict(current_review),
    }
    if history and history[-1] == entry:
        return
    history.append(entry)
    evidence["review_history"] = history


def _synthetic_exit_review(
    *,
    review_state: str,
    reviewed_at_utc: str,
    coverage_event: str,
    implementation_level: str | None = None,
) -> JsonObject:
    return {
        "review_state": review_state,
        "implementation_status": _implementation_status_for_review(
            review_state
        ),
        "implementation_level": implementation_level,
        "blocked_reason": "",
        "reviewed_at": reviewed_at_utc,
        "commit_hash": "",
        "review_path": "",
        "coverage_event": coverage_event,
    }


def _family_id_for_record(*, evidence: Mapping[str, object]) -> str:
    source_file = str(evidence.get("source_file", ""))
    known_family_ids = {
        family.family_id for family in make_linter_rule_families()
    }
    if source_file in known_family_ids:
        return source_file
    return LEGACY_SOURCE_FILE_FAMILY_HINTS.get(
        source_file, "candidate_rule_discovery"
    )


def _safe_family_payload(family_id: str) -> JsonObject:
    try:
        family = make_linter_rule_family_by_id(family_id)
    except ValueError:
        return {}
    return {
        "owner_path": family.owner_path,
        "focused_test_path": family.focused_test_path,
        "evidence_sources": list(family.evidence_sources),
    }


def _update_sqlite_evidence(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    evidence: JsonObject,
    status: str,
    resolved_at_utc: str | None,
) -> None:
    _ = connection.execute(
        """
        UPDATE linter_quarantine_records
        SET evidence_json = ?, status = ?, updated_at_utc = ?, resolved_at_utc =
        ?
        WHERE quarantine_id = ?
        """,
        (
            _canonical_json_text(evidence),
            status,
            _utc_now(),
            resolved_at_utc,
            _quarantine_id(candidate_id),
        ),
    )


def _export_quarantine_snapshots(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
    reset_unimplemented: bool,
) -> JsonObject:
    rows = _sqlite_quarantine_rows(connection)
    manifest_records = [_manifest_record_from_row(row) for row in rows]
    sorted_records = _sorted_manifest_records_for_review(manifest_records)
    coverage_records = [
        _coverage_snapshot_record_from_sqlite(
            manifest_record=record,
            round_order=index,
            reset_unimplemented=reset_unimplemented,
        )
        for index, record in enumerate(sorted_records, start=1)
    ]
    manifest_path = _manifest_path(repo_root=repo_root)
    coverage_path = _coverage_ledger_path(repo_root=repo_root)
    manifest_payload: JsonObject = {
        "schema_version": 1,
        "ledger_version": "derived-mcp-agent-intake",
        "generated_from": SQLITE_SOURCE_OF_TRUTH,
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "database_path": _repo_relative_path(
            repo_root=repo_root,
            path=resolve_repo_relative_path(
                repo_root, DEFAULT_KNOWLEDGE_DB_PATH
            ),
        ),
        "record_root": QUARANTINE_ROOT.as_posix(),
        "runtime_activation": "none; records are review evidence only",
        "total_quarantined": len(manifest_records),
        "final_state_counts": dict(
            sorted(
                Counter(
                    str(record.get("final_state", ""))
                    for record in manifest_records
                ).items()
            )
        ),
        "records": manifest_records,
    }
    coverage_payload: JsonObject = {
        "schema_version": 1,
        "ledger_version": "derived-mcp-agent-review-coverage",
        "generated_from": SQLITE_SOURCE_OF_TRUTH,
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_ssot": True,
        "source_manifest": _repo_relative_path(
            repo_root=repo_root, path=manifest_path
        ),
        "round_order_policy": list(ROUND_ORDER_POLICY),
        "required_fields": list(REVIEW_COVERAGE_REQUIRED_FIELDS),
        "reset_unimplemented": reset_unimplemented,
        "record_count": len(coverage_records),
        "manifest_record_count": len(manifest_records),
        "implementation_status_counts": dict(
            sorted(
                Counter(
                    str(record.get("implementation_status", "unknown"))
                    for record in coverage_records
                ).items()
            )
        ),
        "review_status_counts": dict(
            sorted(
                Counter(
                    str(
                        record.get("review_status", "unreviewed")
                        or "unreviewed"
                    )
                    for record in coverage_records
                ).items()
            )
        ),
        "integration_status_counts": dict(
            sorted(
                Counter(
                    str(
                        record.get("integration_status", "missing") or "missing"
                    )
                    for record in coverage_records
                ).items()
            )
        ),
        "records": coverage_records,
    }
    _write_json_atomically(manifest_path, manifest_payload)
    _write_json_atomically(coverage_path, coverage_payload)
    return {
        "manifest_path": _repo_relative_path(
            repo_root=repo_root, path=manifest_path
        ),
        "coverage_path": _repo_relative_path(
            repo_root=repo_root, path=coverage_path
        ),
        "record_count": len(coverage_records),
        "manifest_record_count": len(manifest_records),
    }


def _sqlite_quarantine_rows(
    connection: sqlite3.Connection,
) -> list[tuple[object, ...]]:
    return cast(
        "list[tuple[object, ...]]",
        connection.execute(
            """
            SELECT quarantine_id, subject_ref, finding_code, severity, status,
            evidence_json,
            source_kind, source_ref, created_at_utc, updated_at_utc,
            resolved_at_utc
            FROM linter_quarantine_records
            ORDER BY subject_ref, finding_code, quarantine_id
            """
        ).fetchall(),
    )


def _sqlite_record_for_candidate(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
) -> tuple[object, ...] | None:
    return cast(
        "tuple[object, ...] | None",
        connection.execute(
            """
            SELECT quarantine_id, subject_ref, finding_code, severity, status,
            evidence_json,
            source_kind, source_ref, created_at_utc, updated_at_utc,
            resolved_at_utc
            FROM linter_quarantine_records
            WHERE quarantine_id = ?
            """,
            (_quarantine_id(candidate_id),),
        ).fetchone(),
    )


def _manifest_record_from_row(row: tuple[object, ...]) -> JsonObject:
    evidence = _evidence_from_row(row)
    return {
        "candidate_id": str(evidence.get("candidate_id") or row[2]),
        "source_file": str(evidence.get("source_file") or row[1]),
        "original_heading": str(evidence.get("original_heading", "")),
        "quarantine_reason": str(evidence.get("quarantine_reason", "")),
        "missing_evidence": str(evidence.get("missing_evidence", "")),
        "proposed_predicate_text": str(
            evidence.get("proposed_predicate_text", "")
        ),
        "final_state": str(evidence.get("final_state", ""))
        or "kept_quarantined",
        "record_path": str(evidence.get("record_path", "")),
        "owner_todo": str(evidence.get("owner_todo", "")),
        "decision_ledger_anchor": str(
            evidence.get("decision_ledger_anchor", "")
        ),
        "origin": str(evidence.get("origin", "")),
        "severity_mapping": _coverage_severity_mapping(evidence),
        "technical_justification": str(
            evidence.get("technical_justification", "")
        ),
        "agent_agency": str(evidence.get("agent_agency", "")),
        "current_review": _json_mapping(evidence.get("current_review")),
        "integration_review": _json_mapping(evidence.get("integration_review")),
        "promotion_state": str(evidence.get("promotion_state", "")),
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_quarantine_id": str(row[0]),
        "sqlite_status": str(row[4]),
    }


def _coverage_snapshot_record_from_sqlite(
    *,
    manifest_record: JsonObject,
    round_order: int,
    reset_unimplemented: bool,
) -> JsonObject:
    current_review = _json_mapping(manifest_record.get("current_review"))
    integration_review = _json_mapping(
        manifest_record.get("integration_review")
    )
    implementation_status = str(
        current_review.get("implementation_status", "not_attempted")
        or "not_attempted"
    )
    preserve_review = (
        implementation_status in IMPLEMENTATION_PRESERVE_STATUSES
        or not reset_unimplemented
    )
    review_status = (
        str(current_review.get("review_state", "")).strip()
        if preserve_review
        else ""
    )
    record: JsonObject = {
        "candidate_id": str(manifest_record.get("candidate_id", "")),
        "source_file": str(manifest_record.get("source_file", "")),
        "record_path": str(manifest_record.get("record_path", "")),
        "review_status": review_status or None,
        "implementation_status": implementation_status,
        "implementation_level": current_review.get("implementation_level")
        if implementation_status == "implemented"
        else None,
        "severity_mapping": _coverage_severity_mapping(manifest_record),
        "blocked_reason": str(current_review.get("blocked_reason", ""))
        if implementation_status == "blocked"
        else "",
        "reviewed_at": str(current_review.get("reviewed_at", ""))
        if preserve_review
        else "",
        "commit_hash": str(current_review.get("commit_hash", ""))
        if implementation_status == "implemented"
        else "",
        "coverage_event": str(current_review.get("coverage_event", ""))
        if preserve_review
        else "manifest_snapshot",
        "round_order": round_order,
        "round_priority": _quarantine_round_priority(manifest_record),
        "original_heading": str(manifest_record.get("original_heading", "")),
        "quarantine_reason": str(manifest_record.get("quarantine_reason", "")),
        "final_state": str(manifest_record.get("final_state", "")),
        "owner_todo": str(manifest_record.get("owner_todo", "")),
        "decision_ledger_anchor": str(
            manifest_record.get("decision_ledger_anchor", "")
        ),
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "sqlite_quarantine_id": str(
            manifest_record.get("sqlite_quarantine_id", "")
        ),
        "integration_status": str(
            integration_review.get("disposition", "missing") or "missing"
        ),
        "integration_explanation": str(
            integration_review.get("explanation", "")
        ),
        "integration_reviewed_at": str(
            integration_review.get("reviewed_at_utc", "")
        ),
        "active_rule_written": bool(
            integration_review.get("active_rule_written", False)
        ),
        "accepted_rule_code_written": bool(
            integration_review.get("accepted_rule_code_written", False)
        ),
    }
    for key in (
        "canonical_rule_code",
        "canonical_candidate_id",
        "implementation_reference",
        "validation_reference",
        "previous_blocked_reason",
        "family_id",
    ):
        value = integration_review.get(key)
        if isinstance(value, str) and value:
            record[key] = value
    source_evidence = integration_review.get("source_evidence")
    if isinstance(source_evidence, list):
        raw_source_evidence = cast("list[object]", source_evidence)
        record["integration_source_evidence"] = [
            item for item in raw_source_evidence if isinstance(item, str)
        ]
    review_path = (
        str(current_review.get("review_path", "")) if preserve_review else ""
    )
    if review_path:
        record["review_path"] = review_path
    return record


def _evidence_from_row(row: tuple[object, ...]) -> JsonObject:
    value = row[5]
    if not isinstance(value, str):
        message = "linter_quarantine_records.evidence_json must be text."
        raise TypeError(message)
    payload = cast("object", json.loads(value))
    if not isinstance(payload, Mapping):
        message = (
            "linter_quarantine_records.evidence_json must decode to an object."
        )
        raise TypeError(message)
    return _mapping_to_json_object(cast("Mapping[object, object]", payload))


def _json_mapping(value: object) -> JsonObject:
    if isinstance(value, Mapping):
        return _mapping_to_json_object(cast("Mapping[object, object]", value))
    return {}


def _record_severity(severity_mapping: Mapping[str, object]) -> str:
    proposed = str(severity_mapping.get("proposed_severity", "") or "")
    observed = str(severity_mapping.get("observed_linter_severity", "") or "")
    return proposed or observed or "info"


def _record_status_from_evidence(evidence: Mapping[str, object]) -> str:
    current_review = _json_mapping(evidence.get("current_review"))
    if not current_review:
        return "quarantined"
    review_state = str(current_review.get("review_state", ""))
    if not review_state:
        return "quarantined"
    if review_state == "accepted":
        return "accepted_pending_implementation"
    return review_state


def _resolved_at_for_evidence(evidence: Mapping[str, object]) -> str | None:
    current_review = _json_mapping(evidence.get("current_review"))
    if not current_review:
        return None
    implementation_status = str(current_review.get("implementation_status", ""))
    review_state = str(current_review.get("review_state", ""))
    if (
        implementation_status not in IMPLEMENTATION_PRESERVE_STATUSES
        and review_state not in EXIT_REVIEW_STATES
    ):
        return None
    reviewed_at = str(current_review.get("reviewed_at", ""))
    return reviewed_at or None


def _promotion_state_for_review(review_state: str) -> str:
    if review_state == "accepted":
        return "candidate_accepted_for_manual_implementation"
    if review_state == "implemented":
        return "candidate_promoted_or_implemented"
    if review_state == "blocked":
        return "candidate_blocked"
    if review_state == "not_implemented":
        return "candidate_valid_actionable_not_implemented"
    if review_state == "converted_to_todo":
        return "candidate_converted_to_todo"
    return f"candidate_{review_state}"


def _quarantine_id(candidate_id: str) -> str:
    _ = _candidate_file_name(candidate_id)
    return f"linter-quarantine:{candidate_id.casefold()}"


def _stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}:{_sha256_json(parts)[:16]}"


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, default=str
        ).encode("utf-8")
    ).hexdigest()


def _canonical_json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        message = f"{key} must be a string."
        raise TypeError(message)
    text = value.strip()
    if not text:
        message = f"{key} must not be blank."
        raise ValueError(message)
    _reject_secret_like_text(key, text)
    return text


def _optional_text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        message = f"{key} must be a string."
        raise TypeError(message)
    text = value.strip()
    if text:
        _reject_secret_like_text(key, text)
    return text


def _optional_bool(
    arguments: Mapping[str, object], key: str, *, default: bool
) -> bool:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        message = f"{key} must be a boolean."
        raise TypeError(message)
    return value


def _optional_int(
    arguments: Mapping[str, object],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, int) or value < minimum or value > maximum:
        message = f"{key} must be an integer from {minimum} to {maximum}."
        raise ValueError(message)
    return value


def _safe_source_reference(value: str) -> str:
    normalized = value.replace("\\", "/")
    if ":" in normalized.split("/", maxsplit=1)[0]:
        message = "source_file must be a repository-relative reference."
        raise ValueError(message)
    parts = tuple(part for part in normalized.split("/") if part)
    if (
        normalized.startswith("/")
        or not parts
        or any(part == ".." for part in parts)
    ):
        message = (
            "source_file must not be absolute or contain parent-directory"
            "escapes."
        )
        raise ValueError(message)
    return "/".join(parts)


def _safe_final_state(value: str) -> str:
    final_state = value.casefold().strip()
    if final_state in ACTIVE_RULE_FINAL_STATES:
        message = (
            "linter.quarantine.write cannot write accepted or active rule"
            "states."
        )
        raise ValueError(message)
    if final_state not in ALLOWED_FINAL_STATES:
        allowed = ", ".join(sorted(ALLOWED_FINAL_STATES))
        message = f"final_state must be one of: {allowed}."
        raise ValueError(message)
    return final_state


def _manifest_final_state(final_state: str) -> str:
    if final_state in MANIFEST_PENDING_STATES:
        return "kept_quarantined"
    return final_state


def _safe_review_state(value: str) -> str:
    review_state = value.casefold().strip()
    if review_state not in ALLOWED_REVIEW_STATES:
        allowed = ", ".join(sorted(ALLOWED_REVIEW_STATES))
        message = f"review_state must be one of: {allowed}."
        raise ValueError(message)
    return review_state


def _review_path(*, repo_root: Path, candidate_id: str) -> Path:
    review_file_name = _candidate_file_name(candidate_id).replace(
        ".md", ".json"
    )
    quarantine_root = (repo_root / QUARANTINE_ROOT).resolve()
    review_path = (
        quarantine_root / MCP_REVIEW_DIR_NAME / review_file_name
    ).resolve()
    if not review_path.is_relative_to(quarantine_root):
        message = "review path escaped linter quarantine root."
        raise ValueError(message)
    return review_path


def _candidate_file_name(candidate_id: str) -> str:
    if (
        not SAFE_CANDIDATE_ID_PATTERN.fullmatch(candidate_id)
        or ".." in candidate_id
        or "/" in candidate_id
        or "\\" in candidate_id
    ):
        message = "candidate_id must be a safe linter candidate identifier."
        raise ValueError(message)
    return f"{candidate_id.casefold()}.md"


def _review_state_evidence(
    arguments: Mapping[str, object],
    *,
    review_state: str,
) -> dict[str, str]:
    if review_state == "accepted":
        evidence = {
            "linter_intake_reference": _required_source_reference(
                arguments,
                "linter_intake_reference",
            ),
            "implementation_reference": _required_source_reference(
                arguments,
                "implementation_reference",
            ),
        }
    elif review_state == "implemented":
        evidence = {
            "implementation_reference": _required_source_reference(
                arguments,
                "implementation_reference",
            ),
            "validation_reference": _required_source_reference(
                arguments, "validation_reference"
            ),
        }
    elif review_state == "rejected":
        evidence = {
            "rejection_reason": _required_text(arguments, "rejection_reason")
        }
    elif review_state == "postponed":
        evidence = {
            "postponement_reason": _required_text(
                arguments, "postponement_reason"
            ),
            "review_after_utc": _required_text(arguments, "review_after_utc"),
        }
    elif review_state == "blocked":
        evidence = {
            "blocker_summary": _required_text(arguments, "blocker_summary"),
            "promotion_requirement": _required_text(
                arguments, "promotion_requirement"
            ),
        }
    elif review_state == "not_implemented":
        evidence = {
            "previous_review_state": _optional_text(
                arguments, "previous_review_state"
            )
            or "blocked",
            "actionability_summary": _required_text(
                arguments, "actionability_summary"
            ),
            "promotion_requirement": _required_text(
                arguments, "promotion_requirement"
            ),
            "source_evidence": _required_text(arguments, "source_evidence"),
        }
    else:
        evidence = {
            "todo_reference": _required_source_reference(
                arguments, "todo_reference"
            )
        }
    return evidence


def _severity_fields(arguments: Mapping[str, object]) -> dict[str, object]:
    observed = _optional_severity(arguments, "observed_linter_severity")
    proposed = _optional_severity(arguments, "proposed_severity")
    if bool(observed) != bool(proposed):
        message = (
            "observed_linter_severity and proposed_severity must be supplied"
            "together."
        )
        raise ValueError(message)
    technical_justification = _optional_text(
        arguments, "technical_justification"
    )
    severity_downgrade = bool(
        observed
        and proposed
        and SEVERITY_RANK[proposed] < SEVERITY_RANK[observed]
    )
    if severity_downgrade:
        technical_justification = _required_text(
            arguments, "technical_justification"
        )
        word_count = _word_count(technical_justification)
        if word_count < MIN_DOWNGRADE_JUSTIFICATION_WORDS:
            message = (
                "technical_justification must contain at least "
                f"{MIN_DOWNGRADE_JUSTIFICATION_WORDS} words when the "
                f"proposed severity lowers "
                "the linter severity."
            )
            raise ValueError(message)
    return {
        "observed_linter_severity": observed,
        "proposed_severity": proposed,
        "technical_justification": technical_justification,
        "severity_downgrade": severity_downgrade,
    }


def _optional_severity(arguments: Mapping[str, object], key: str) -> str:
    raw_value = _optional_text(arguments, key)
    if not raw_value:
        return ""
    value = SEVERITY_ALIASES.get(raw_value.casefold(), raw_value.casefold())
    if value not in SEVERITY_RANK:
        allowed = ", ".join(sorted(SEVERITY_RANK))
        message = f"{key} must be one of: {allowed}."
        raise ValueError(message)
    return value


def _severity_mapping(severity: Mapping[str, object]) -> JsonObject:
    return {
        "observed_linter_severity": str(severity["observed_linter_severity"]),
        "proposed_severity": str(severity["proposed_severity"]),
        "severity_downgrade": bool(severity["severity_downgrade"]),
    }


def _word_count(text: object) -> int:
    return len(WORD_PATTERN.findall(text)) if isinstance(text, str) else 0


def _manifest_path(*, repo_root: Path) -> Path:
    return repo_root / QUARANTINE_ROOT / QUARANTINE_MANIFEST_NAME


def _coverage_ledger_path(*, repo_root: Path) -> Path:
    return repo_root / QUARANTINE_ROOT / REVIEW_COVERAGE_LEDGER_NAME


def _manifest_record_locator(*, repo_root: Path, candidate_id: str) -> str:
    manifest_path = _repo_relative_path(
        repo_root=repo_root,
        path=_manifest_path(repo_root=repo_root),
    )
    return f"{manifest_path}#candidate_id={candidate_id}"


def _load_json_object(path: Path, *, default: JsonObject) -> JsonObject:
    if not path.is_file():
        return dict(default)
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, Mapping):
        message = f"{path.name} must contain a JSON object."
        raise TypeError(message)
    return _mapping_to_json_object(cast("Mapping[object, object]", payload))


def _empty_manifest_payload() -> JsonObject:
    return {
        "schema_version": 1,
        "ledger_version": "mcp-agent-intake",
        "generated_from": "linter.quarantine.write",
        "record_root": QUARANTINE_ROOT.as_posix(),
        "runtime_activation": "none; records are review evidence only",
        "total_quarantined": 0,
        "final_state_counts": {},
        "records": [],
    }


def _empty_coverage_payload() -> JsonObject:
    return {
        "schema_version": 1,
        "ledger_version": "mcp-agent-review-coverage",
        "source_manifest": (
            QUARANTINE_ROOT / QUARANTINE_MANIFEST_NAME
        ).as_posix(),
        "record_count": 0,
        "records": [],
    }


def _sorted_manifest_records_for_review(
    records: list[JsonObject],
) -> list[JsonObject]:
    return sorted(
        records,
        key=lambda record: (
            _quarantine_round_priority(record),
            str(record.get("source_file", "")),
            str(record.get("candidate_id", "")),
        ),
    )


def _quarantine_round_priority(record: Mapping[str, object]) -> int:
    reason = str(record.get("quarantine_reason", "")).casefold()
    if "high_false_positive" in reason:
        return 30
    if "impossible_to_verify_locally" in reason:
        return 20
    return 10


def _coverage_severity_mapping(record: Mapping[str, object]) -> JsonObject:
    severity_mapping = record.get("severity_mapping", {})
    if isinstance(severity_mapping, Mapping):
        return _mapping_to_json_object(
            cast("Mapping[object, object]", severity_mapping)
        )
    return {}


def _coverage_implementation_status(record: Mapping[str, object]) -> str:
    status = str(record.get("implementation_status", "")).strip()
    if status in {"implemented", "blocked"}:
        return status
    return "not_attempted"


def _coverage_review_status(record: Mapping[str, object]) -> str | None:
    status = record.get("review_status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return None


def _coverage_implementation_level(record: Mapping[str, object]) -> str | None:
    level = record.get("implementation_level")
    if level in {"exact", "modified"}:
        return str(level)
    return None


def _coverage_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def _records_from_payload(payload: Mapping[str, object]) -> list[JsonObject]:
    records = payload.get("records")
    if not isinstance(records, list):
        message = "quarantine JSON payload must contain a records array."
        raise TypeError(message)
    raw_records = cast("list[object]", records)
    return [
        _mapping_to_json_object(cast("Mapping[object, object]", record))
        for record in raw_records
        if isinstance(record, Mapping)
    ]


def _implementation_status_for_review(review_state: str) -> str:
    if review_state == "implemented":
        return "implemented"
    if review_state == "blocked":
        return "blocked"
    return "not_attempted"


def _quarantine_categories(
    records: list[JsonObject],
) -> list[dict[str, object]]:
    categories: dict[str, list[JsonObject]] = {}
    for record in records:
        source_file = str(record.get("source_file", "unknown"))
        categories.setdefault(source_file, []).append(record)
    return [
        {"source_file": source_file, "records": categories[source_file]}
        for source_file in sorted(categories)
    ]


def _category_payload(
    category: Mapping[str, object],
    *,
    index: int,
    expand: bool,
    record_limit: int,
) -> JsonObject:
    raw_records = category.get("records")
    if not isinstance(raw_records, list):
        message = "quarantine category must contain a records array."
        raise TypeError(message)
    records = [
        _mapping_to_json_object(cast("Mapping[object, object]", record))
        for record in cast("list[object]", raw_records)
        if isinstance(record, Mapping)
    ]
    shown_records = records[:record_limit]
    payload: JsonObject = {
        "number": index,
        "category": str(category.get("source_file", "unknown")),
        "record_count": len(records),
        "candidate_id_sample": [
            str(record["candidate_id"])
            for record in shown_records
            if record.get("candidate_id")
        ],
        "hidden_record_count": max(len(records) - len(shown_records), 0),
    }
    if expand:
        payload["records"] = [
            {
                "number": record_number,
                "candidate_id": record.get("candidate_id", ""),
                "title": record.get("original_heading", ""),
                "final_state": record.get("final_state", ""),
                "record_path": record.get("record_path", ""),
                "severity_mapping": record.get("severity_mapping", {}),
            }
            for record_number, record in enumerate(shown_records, start=1)
        ]
    return payload


def _mapping_to_json_object(value: Mapping[object, object]) -> JsonObject:
    return {str(key): item for key, item in value.items()}


def _required_source_reference(
    arguments: Mapping[str, object], key: str
) -> str:
    return _safe_source_reference(_required_text(arguments, key))


def _review_payload(record: _QuarantineReviewRecord) -> JsonObject:
    leaves_quarantine = record.review_state in EXIT_REVIEW_STATES
    return {
        "schema_version": 1,
        "candidate_id": record.candidate_id,
        "candidate_path": record.candidate_path,
        "review_state": record.review_state,
        "rationale": record.rationale,
        "reviewer": record.reviewer,
        "reviewed_at_utc": record.reviewed_at_utc,
        "state_evidence": record.state_evidence,
        "leaves_quarantine": leaves_quarantine,
        "allowed_exit_reason": record.review_state if leaves_quarantine else "",
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_services_called": False,
    }


def _write_json_atomically(path: Path, payload: JsonObject) -> None:
    _write_text_atomically(
        path, f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
    )


def _write_text_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            _ = temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        _replace_path_with_retry(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _replace_path_with_retry(source: Path, destination: Path) -> None:
    """Replace a path while tolerating short Windows file-indexing races.

    Raises:
        PermissionError: If the destination remains unavailable after retries.
    """
    for attempt in range(ATOMIC_REPLACE_RETRY_COUNT):
        try:
            _ = source.replace(destination)
        except PermissionError:
            if attempt == ATOMIC_REPLACE_RETRY_COUNT - 1:
                raise
            time.sleep(ATOMIC_REPLACE_RETRY_DELAY_SECONDS)
        else:
            return


def _repo_relative_path(*, repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def ensure_linter_quarantine_database(
    repo_root: Path,
) -> KnowledgeStoreStatusReport:
    """Ensure the quarantine SQLite schema is available.

    Returns:
        Current knowledge-store status.
    """
    return _ensure_linter_quarantine_database(repo_root)


def linter_quarantine_family_id_for_record(
    *, evidence: Mapping[str, object]
) -> str:
    """Resolve the quarantine linter family id for evidence.

    Returns:
        Canonical family id.
    """
    return _family_id_for_record(evidence=evidence)


def update_linter_quarantine_evidence(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    evidence: JsonObject,
    status: str,
    resolved_at_utc: str | None,
) -> None:
    """Update one quarantine evidence row through the public adapter."""
    _update_sqlite_evidence(
        connection=connection,
        candidate_id=candidate_id,
        evidence=evidence,
        status=status,
        resolved_at_utc=resolved_at_utc,
    )


def export_linter_quarantine_snapshots(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
    reset_unimplemented: bool,
) -> JsonObject:
    """Export derived quarantine snapshots.

    Returns:
        Manifest and coverage snapshot paths.
    """
    return _export_quarantine_snapshots(
        connection=connection,
        repo_root=repo_root,
        reset_unimplemented=reset_unimplemented,
    )


def sqlite_linter_quarantine_rows(
    connection: sqlite3.Connection,
) -> list[tuple[object, ...]]:
    """Read all quarantine rows from SQLite.

    Returns:
        Raw SQLite row tuples.
    """
    return _sqlite_quarantine_rows(connection)


def sqlite_linter_quarantine_record_for_candidate(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
) -> tuple[object, ...] | None:
    """Read one quarantine row by candidate id.

    Returns:
        Raw SQLite row tuple when present.
    """
    return _sqlite_record_for_candidate(
        connection=connection, candidate_id=candidate_id
    )


def linter_quarantine_evidence_from_row(row: tuple[object, ...]) -> JsonObject:
    """Decode quarantine evidence JSON from a row.

    Returns:
        Evidence payload.
    """
    return _evidence_from_row(row)


def linter_quarantine_json_mapping(value: object) -> JsonObject:
    """Coerce a mapping-like value into a JSON object.

    Returns:
        JSON object or an empty object for non-mappings.
    """
    return _json_mapping(value)


def linter_quarantine_canonical_json_text(payload: Mapping[str, object]) -> str:
    """Serialize quarantine JSON deterministically.

    Returns:
        Canonical JSON text.
    """
    return _canonical_json_text(payload)


def safe_linter_quarantine_source_reference(value: str) -> str:
    """Normalize a quarantine source reference.

    Returns:
        Repository-relative source reference.
    """
    return _safe_source_reference(value)


def linter_quarantine_manifest_path(*, repo_root: Path) -> Path:
    """Build the derived quarantine manifest path.

    Returns:
        Absolute manifest path.
    """
    return _manifest_path(repo_root=repo_root)


def linter_quarantine_coverage_ledger_path(*, repo_root: Path) -> Path:
    """Build the derived quarantine coverage path.

    Returns:
        Absolute coverage ledger path.
    """
    return _coverage_ledger_path(repo_root=repo_root)


def linter_quarantine_repo_relative_path(*, repo_root: Path, path: Path) -> str:
    """Render a path relative to the repository root.

    Returns:
        POSIX-style repository-relative path.
    """
    return _repo_relative_path(repo_root=repo_root, path=path)


def _reject_secret_like_text(key: str, text: str) -> None:
    if SECRET_LIKE_TEXT_PATTERN.search(text):
        message = (
            f"{key} contains secret-like text and cannot be written to linter"
            f"quarantine."
        )
        raise ValueError(message)
