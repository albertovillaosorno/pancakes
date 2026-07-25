# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001032#repo.quality.no-silly-linter-bypasses
# - 001046#repo.blueprint-validation.findings-model
# - 001064#repo.make-knowledge.course-promoted-rules
# - 001066#repo.make-linter.offline-validator-remains-default
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Non-gating Make linter rule-family taxonomy.

Boundary contract:
- Owns: rule-family metadata, evidence posture, and supported finding-code
lookup.
- Must not: emit validation findings, call Make.com, or change gate severity.
- Allows: typed taxonomy records and exact-code classification helpers.
- Split when: rule promotion workflow needs persistence, scoring, or remediation
state.
- Merge when: another module owns the same Make linter taxonomy contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple

if TYPE_CHECKING:
    from blueprints.validation.models import BlueprintFindingSeverity

type MakeLinterEvidenceSource = Literal[
    "adr_policy ",
    "ast_structure ",
    "catalog_truth ",
    "designer_message_api ",
    "knowledge_store ",
    "local_failure ",
    "promoted_golden_evidence ",
    "validation_fixture",
]
type MakeLinterGateBehavior = Literal[
    "blocking_errors_possible ",
    "advisory_only ",
    "candidate_non_gating",
]
type MakeLinterRuleFamilyId = Literal[
    "ai_agent_contracts ",
    "ast_import_shape ",
    "catalog_resolution ",
    "candidate_rule_discovery ",
    "content_injection_security ",
    "crypto_security ",
    "data_exposure_security ",
    "designer_layout_handoff ",
    "designer_message_evidence ",
    "error_handling_reliability ",
    "generation_gate ",
    "graphql_security ",
    "mapping_reference_contracts ",
    "http_url_security ",
    "note_content_security ",
    "operation_volume_optimization ",
    "redirect_security ",
    "route_branch_topology ",
    "scenario_release_governance ",
    "semantic_runtime_contracts ",
    "setup_readiness ",
    "sql_security ",
    "transaction_safety ",
    "webhook_http_security",
]


class MakeLinterRuleFamily(NamedTuple):
    """One deterministic Make linter rule family."""

    family_id: MakeLinterRuleFamilyId
    title: str
    owner_path: str
    invariant: str
    evidence_sources: tuple[MakeLinterEvidenceSource, ...]
    allowed_severities: tuple[BlueprintFindingSeverity, ...]
    gate_behavior: MakeLinterGateBehavior
    output_affecting: bool
    focused_test_path: str
    supported_codes: tuple[str, ...]
    promotion_requirement: str


MAKE_LINTER_RULE_FAMILIES: Final[tuple[MakeLinterRuleFamily, ...]] = (
    MakeLinterRuleFamily(
        family_id="ast_import_shape",
        title="AST import-shape safety",
        owner_path="src/blueprints/validation/importability.py",
        invariant=(
            "Raw Blueprint AST shapes must remain importable without "
            "coercing invalid Make "
            "metadata, node identity, notes, placeholder, or error-handler "
            "payloads."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/test_importability_fixtures.py",
        supported_codes=(
            "ast.designer_coordinates_invalid ",
            "ast.designer_invalid ",
            "ast.designer_messages_invalid ",
            "ast.metadata_invalid ",
            "ast.module_token_invalid ",
            "ast.node_id_boolean ",
            "ast.node_id_duplicate ",
            "ast.node_id_invalid ",
            "ast.node_version_invalid ",
            "ast.note_content_invalid ",
            "ast.note_invalid ",
            "ast.note_metadata_invalid ",
            "ast.note_module_id_invalid ",
            "ast.note_module_id_unknown ",
            "ast.note_module_ids_invalid ",
            "ast.notes_invalid ",
            "importability.metadata_invalid ",
            "importability.placeholder_registry_conflict ",
            "importability.placeholder_registry_incomplete ",
            "importability.placeholder_registry_target_mismatch ",
            "importability.placeholder_registry_unused ",
            "importability.placeholder_unregistered ",
            "importability.placeholder_unresolved ",
            "importability.reference_unavailable",
        ),
        promotion_requirement=(
            "Add exact fixture coverage for every new import-shape code "
            "before it can be "
            "classified here."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="catalog_resolution",
        title="Catalog resolution and required fields",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "Every executable Make module and required field must be backed "
            "by catalog or "
            "approved raw-spec evidence before render or handoff claims."
        ),
        evidence_sources=(
            "catalog_truth ",
            "ast_structure ",
            "adr_policy ",
            "validation_fixture",
        ),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "deprecated_module ",
            "importability.module.operator_approved_stub ",
            "importability.module.unknown ",
            "mapping.mapper_not_object ",
            "mapping.parameters_not_object ",
            "mapping.required_parameter_missing ",
            "module.catalog_record_missing ",
            "module.unresolved ",
            "raw_spec.binding_hash_missing ",
            "raw_spec.binding_version_drift",
        ),
        promotion_requirement=(
            "Catalog-backed codes must cite resolver, raw-spec, or "
            "required-field evidence and "
            "prove unknown modules cannot render."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="route_branch_topology",
        title="Route and branch topology",
        owner_path="src/blueprints/validation/route_validation.py",
        invariant=(
            "Routers, routes, branches, tools, and filters must expose "
            "deterministic local "
            "topology, executable branch conditions, and fallback behavior "
            "for reviewed "
            "event-type routing."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/test_router_topology_importability.py",
        supported_codes=(
            "filter.empty_conditions ",
            "filter.expression_unsupported ",
            "filter.label_missing ",
            "filter.label_overlong ",
            "filter.operator_unsupported ",
            "filter.reference_not_upstream ",
            "filter.reference_unknown_field ",
            "importability.router_topology ",
            "route.event_type_fallback_missing ",
            "route.empty_flow ",
            "route.id_duplicate ",
            "route.routes_on_non_router ",
            "router.routes_missing",
        ),
        promotion_requirement=(
            "New route rules must prove the branch or filter condition from "
            "AST structure, not "
            "from visual-editor layout."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="mapping_reference_contracts",
        title="Mapping and reference contracts",
        owner_path="src/blueprints/validation/expression_intelligence.py",
        invariant=(
            "Make expressions and downstream references must use supported "
            "syntax, promoted "
            "function contracts, and locally declared output fields."
        ),
        evidence_sources=(
            "ast_structure ",
            "knowledge_store ",
            "validation_fixture",
        ),
        allowed_severities=("error", "warning", "optimization"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path=(
            "tests/blueprints/validation/mapping_expression_intelligence_contract.py"
        ),
        supported_codes=(
            "mapping.aggregator_target_missing ",
            "mapping.expression_empty ",
            "mapping.expression_unbalanced ",
            "mapping.function_argument_count ",
            "mapping.function_unknown ",
            "mapping.iterator_source_missing ",
            "mapping.pagination_without_limit ",
            "output.reference_duplicate_node_id ",
            "semantic.output_field_unknown ",
            "semantic.reference_unknown_node",
        ),
        promotion_requirement=(
            "Reference and expression rules must include a focused "
            "expression fixture plus a "
            "client-safe repair diagnostic."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="error_handling_reliability",
        title="Error-handling reliability",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "Mutating or reliability-sensitive modules must declare "
            "deterministic error-route "
            "evidence before a rule is promoted beyond advisory posture."
        ),
        evidence_sources=(
            "ast_structure ",
            "knowledge_store ",
            "adr_policy ",
            "validation_fixture",
        ),
        allowed_severities=("error", "optimization"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/test_error_handler_importability.py",
        supported_codes=(
            "ast.error_handler_child_invalid ",
            "ast.error_handler_empty ",
            "error_route.missing ",
            "importability.error_handler.nested_unsupported",
        ),
        promotion_requirement=(
            "Missing-handler candidates start as optimization findings "
            "unless an ADR and "
            "tests justify blocking severity."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="semantic_runtime_contracts",
        title="Runtime semantic contracts",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "Scenario runtime semantics must reject locally provable misuse "
            "such as invalid "
            "triggers, invalid schedule cadence, cycles, authentication "
            "blockers, webhook guard "
            "gaps, and unsupported module substitutes."
        ),
        evidence_sources=(
            "ast_structure ",
            "knowledge_store ",
            "designer_message_api",
        ),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "basic_trigger.interface_missing ",
            "custom_app.schema_contract_missing ",
            "mcp_tool.contract_missing ",
            "semantic.authentication_required ",
            "semantic.download_file_post ",
            "semantic.multiple_root_triggers ",
            "semantic.nested_trigger ",
            "semantic.scenario_self_invocation_cycle ",
            "semantic.trigger_position_invalid ",
            "schedule.sub_minute_interval ",
            "webhook.backpressure_missing ",
            "webhook.method_guard_missing ",
            "webhook.payload_contract_missing ",
            "webhook.response_body_size_limit_exceeded ",
            "webhook.response_content_type_missing ",
            "webhook.response_missing ",
            "webhook.sequential_response_conflict",
        ),
        promotion_requirement=(
            "Semantic rules must be deterministic from local AST, reviewed "
            "knowledge rows, or "
            "reviewed designer-message evidence."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="scenario_release_governance",
        title="Scenario release governance",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "Production or governance-profiled scenarios must expose only "
            "locally visible "
            "owner, change, rollback, incident, and debug-marker evidence "
            "before release "
            "governance diagnostics can run."
        ),
        evidence_sources=(
            "ast_structure ",
            "knowledge_store ",
            "adr_policy ",
            "validation_fixture",
        ),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path=(
            "tests/blueprints/validation/"
            "make_linter_observability_release_governance_rules_contract.py"
        ),
        supported_codes=(
            "scenario.change_reason_missing ",
            "scenario.incident_note_missing ",
            "scenario.owner_missing ",
            "scenario.production_debug_marker ",
            "scenario.rollback_plan_missing",
        ),
        promotion_requirement=(
            "Release-governance rules require explicit scenario governance "
            "profile evidence "
            "plus failing and passing fixtures; ordinary blueprints must "
            "not be treated as "
            "production by silence."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="ai_agent_contracts",
        title="AI-agent and tool contracts",
        owner_path="src/blueprints/validation/ai_agent_contracts.py",
        invariant=(
            "AI-agent nodes and agent-callable tools must expose model, "
            "prompt, fallback, "
            "security, and input/output contracts that can be tested locally."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning", "optimization"),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "ai_agent.context_structure_missing ",
            "ai_agent.conversation_history_limit_high ",
            "ai_agent.conversation_memory_policy_missing ",
            "ai_agent.deterministic_temperature_high ",
            "ai_agent.fallback_missing ",
            "ai_agent.file_processing_capability_missing ",
            "ai_agent.instructions_inputs_mixed ",
            "ai_agent.knowledge_attachment_review ",
            "ai_agent.knowledge_retrieval_scope_missing ",
            "ai_agent.knowledge_retrieval_test_missing ",
            "ai_agent.knowledge_source_missing ",
            "ai_agent.multi_tool_plan_missing ",
            "ai_agent.mutating_tool_guard_missing ",
            "ai_agent.objective_missing ",
            "ai_agent.optional_parameter_default_missing ",
            "ai_agent.provider_missing ",
            "ai_agent.production_metrics_missing ",
            "ai_agent.response_field_description_missing ",
            "ai_agent.response_format_missing ",
            "ai_agent.scope_too_broad ",
            "ai_agent.security_guardrails_missing ",
            "ai_agent.session_isolation_missing ",
            "ai_agent.sensitive_action_approval_missing ",
            "ai_agent.test_cases_missing ",
            "ai_agent.apply_300_second_default ",
            "ai_agent.configure_appropriate_step_timeout ",
            "ai_agent.exceed_600_seconds ",
            "ai_agent.tool_contract_missing ",
            "ai_agent.tool_description_unclear ",
            "ai_agent.tool_name_duplicate ",
            "ai_agent.tool_name_missing ",
            "ai_agent.tool_not_on_demand ",
            "ai_agent.tool_output_missing ",
            "ai_agent.tool_output_filter_missing ",
            "ai_agent.tool_text_sensitive_literal ",
            "ai_agent.tools_missing",
        ),
        promotion_requirement=(
            "AI-agent rules stay advisory unless a future ADR changes handoff "
            "severity."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="http_url_security",
        title="HTTP URL security",
        owner_path="src/blueprints/validation/http_security.py",
        invariant=(
            "HTTP request modules must not use external plain HTTP "
            "transport, embed "
            "credentials in URL authority fields, carry dynamic scheme or "
            "host mappings, "
            "target private or metadata networks without allowlist "
            "evidence, carry static "
            "secret literals, or map sensitive source fields into static "
            "external targets; "
            "Slack or Discord webhook destination fields should not map "
            "arbitrary runtime "
            "sources; dynamic header mappings should expose sanitization "
            "evidence; and "
            "proxy identity headers should expose trusted-proxy "
            "normalization evidence "
            "before forwarding inbound-looking values; and secret-scoped "
            "header mappings "
            "should expose log masking evidence; outbound Cookie headers "
            "should not map "
            "inbound cookie-like source fields."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "http.basic_auth_url_credentials ",
            "http.api_version_pinning_missing ",
            "http.cookie_passthrough_header ",
            "http.dynamic_chat_webhook_destination ",
            "http.dynamic_header_mapping ",
            "http.header_secret_masking_missing ",
            "http.header_crlf_injection ",
            "http.dynamic_url_host ",
            "http.external_api_allowlist_missing ",
            "http.external_sensitive_mapping ",
            "http.local_untrusted_timeout_retry_missing ",
            "http.path_segment_encoding_missing ",
            "http.private_network_url ",
            "http.proxy_header_trust_missing ",
            "http.query_parameter_encoding_missing ",
            "http.sensitive_query_parameter ",
            "http.static_secret_literal ",
            "http.tls_verification_disabled ",
            "http.timeout_policy_missing ",
            "http.url_unencrypted_transport",
        ),
        promotion_requirement=(
            "HTTP URL security rules require manual intake review plus "
            "deterministic AST "
            "URL-shape fixtures with redacted diagnostics."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="data_exposure_security",
        title="Data exposure security",
        owner_path="src/blueprints/validation/data_exposure.py",
        invariant=(
            "Unsafe sink modules should not carry static personal "
            "identifier literals in "
            "message, body, prompt, or response fields, whole payload "
            "mappings in "
            "content and record fields, secret-like mappings in visible "
            "output or "
            "variable fields, static internal URL literals in visible "
            "output fields, "
            "sensitive-looking HTTP response mappings in unsafe sink "
            "fields, or raw "
            "error-like and pagination token-like mappings in webhook "
            "response fields."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "data_exposure.raw_payload_sink ",
            "data_exposure.raw_error_output ",
            "data_exposure.pagination_token_output ",
            "data_exposure.internal_url_literal ",
            "data_exposure.secret_output_sink ",
            "data_exposure.sensitive_http_response_sink ",
            "data_exposure.static_personal_literal",
        ),
        promotion_requirement=(
            "Data exposure rules require manual intake review, sink-field "
            "scoping, "
            "redacted diagnostics, and passing fixtures for ordinary "
            "specific-field "
            "mappings or redacted values."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="note_content_security",
        title="Metadata note content security",
        owner_path="src/blueprints/validation/note_security.py",
        invariant=(
            "Root and module metadata notes should not carry static "
            "email-like or "
            "phone-like personal identifier literals, static secret-like "
            "examples, "
            "or internal linter rule IDs and predicate mechanics."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/test_note_shape_policy.py",
        supported_codes=(
            "notes.internal_linter_marker ",
            "notes.insecure_link_literal ",
            "notes.static_personal_literal ",
            "notes.static_secret_literal",
        ),
        promotion_requirement=(
            "Note-content security rules require manual intake review, "
            "structured note "
            "content paths, redacted diagnostics, and passing fixtures for "
            "ordinary "
            "general or redacted note text."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="sql_security",
        title="SQL query security",
        owner_path="src/blueprints/validation/sql_security.py",
        invariant=(
            "SQL-like modules should keep mapped values out of raw query "
            "text and place "
            "dynamic inputs in provider-supported parameter binding fields "
            "instead."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=("sql.dynamic_raw_query_mapping",),
        promotion_requirement=(
            "SQL query rules require manual intake review, SQL-module "
            "scoping, redacted "
            "diagnostics, and passing fixtures for mappings kept outside "
            "raw query text."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="redirect_security",
        title="Redirect destination security",
        owner_path="src/blueprints/validation/redirect_security.py",
        invariant=(
            "Redirect response destinations should keep scheme and host "
            "static or rely "
            "on an explicitly promoted allowlist profile."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "redirect.dynamic_destination_url ",
            "redirect.response_contract_missing",
        ),
        promotion_requirement=(
            "Redirect security rules require manual intake review, "
            "redirect-response "
            "scoping, redacted diagnostics, and passing fixtures for "
            "static-host redirects."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="graphql_security",
        title="GraphQL request security and optimization",
        owner_path="src/blueprints/validation/graphql_security.py",
        invariant=(
            "GraphQL request rules must stay local to visible query strings "
            "and avoid "
            "claiming provider schema, cost, or runtime response semantics "
            "without "
            "dedicated evidence."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "graphql.depth_budget_exceeded ",
            "graphql.dynamic_query_without_variables ",
            "graphql.error_array_guard_missing ",
            "graphql.field_count_budget_exceeded ",
            "graphql.mutation_idempotency_missing ",
            "graphql.operation_name_missing ",
            "graphql.partial_data_guard_missing ",
            "graphql.production_introspection_query ",
            "graphql.query_minification_suggested ",
            "graphql.schema_version_missing ",
            "graphql.variable_type_declaration_missing",
        ),
        promotion_requirement=(
            "GraphQL rules require manual intake review, query-field "
            "scoping, redacted "
            "diagnostics, and passing fixtures for ordinary minified query "
            "strings."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="content_injection_security",
        title="Rendered content injection security",
        owner_path="src/blueprints/validation/content_injection.py",
        invariant=(
            "HTML-capable and Markdown-capable response or message fields "
            "should escape "
            "or sanitize mapped values before rendering them as rich content."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "content.html_dynamic_mapping ",
            "content.markdown_dynamic_mapping",
        ),
        promotion_requirement=(
            "Rendered content injection rules require manual intake review, "
            "rendered-field "
            "scoping, redacted diagnostics, and passing fixtures for "
            "visibly escaped values."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="crypto_security",
        title="Cryptographic algorithm security",
        owner_path="src/blueprints/validation/crypto_security.py",
        invariant=(
            "Security-scoped signature, digest, authentication, token, and "
            "integrity "
            "configuration should not declare MD5 or SHA-1 hash algorithms, "
            "and JWT "
            "validation configuration must not allow alg none."
        ),
        evidence_sources=("ast_structure", "adr_policy", "validation_fixture"),
        allowed_severities=("error", "warning"),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "crypto.jwt_none_algorithm ",
            "crypto.weak_security_hash",
        ),
        promotion_requirement=(
            "Cryptographic algorithm rules require manual intake review, "
            "security-context "
            "scoping, current standards bibliography, and redacted diagnostics."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="webhook_http_security",
        title="Webhook and HTTP safety",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "HTTP, webhook, and parser modules must expose reviewed local "
            "evidence for "
            "structured responses, file upload semantics, protected payload "
            "handling, "
            "custom webhook ingress budgets, mailhook sender allowlists, "
            "and signed-webhook "
            "timestamp windows."
        ),
        evidence_sources=(
            "knowledge_store ",
            "ast_structure ",
            "validation_fixture",
        ),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "http.accept_header_missing ",
            "http.authorization_redirect_leak ",
            "http.blind_error_catchall ",
            "http.conflict_branch_missing ",
            "http.conflict_resume_missing ",
            "http.delete_body_guard_missing ",
            "http.empty_body_parse_guard_missing ",
            "http.error_status_evaluation_disabled ",
            "http.file_upload_body_type_invalid ",
            "http.get_body_not_allowed ",
            "http.head_response_body_expected ",
            "http.json_body_syntax_invalid ",
            "http.json_content_type_missing ",
            "http.method_url_missing ",
            "http.not_found_classification_missing ",
            "http.options_usage_guard_missing ",
            "http.parse_response_missing ",
            "http.patch_semantics_missing ",
            "http.permanent_error_retry_policy ",
            "http.put_replacement_guard_missing ",
            "http.rate_limit_branch_missing ",
            "http.raw_json_body_validation_missing ",
            "http.redirect_policy_missing ",
            "http.request_body_size_budget_missing ",
            "http.response_content_type_guard_missing ",
            "http.response_schema_guard_missing ",
            "http.response_size_budget_missing ",
            "http.restore_label_dependency ",
            "http.retryable_mutation_idempotency_missing ",
            "http.server_error_backoff_missing ",
            "http.success_status_contract_missing ",
            "http.upstream_status_mapping_missing ",
            "http.user_agent_context_missing ",
            "parse_json.schema_missing ",
            "text_parser.input_missing ",
            "text_parser.pattern_missing ",
            "webhook.ingress_budget_missing ",
            "webhook.mailhook_sender_allowlist_missing ",
            "webhook.signature_timestamp_missing ",
            "webhook.security_ip_allowlist_missing ",
            "webhook.security_sensitive_cleartext ",
            "webhook.security_signature_missing",
        ),
        promotion_requirement=(
            "Security and HTTP warnings require promoted knowledge facts "
            "and must not claim "
            "live protection without source evidence."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="transaction_safety",
        title="Transaction and state-mutation safety",
        owner_path="src/blueprints/validation/validator.py",
        invariant=(
            "State-changing operations must disclose key, recovery, audit, "
            "idempotency, or "
            "compensation posture before local handoff can treat the risk "
            "as reviewed."
        ),
        evidence_sources=(
            "knowledge_store ",
            "adr_policy ",
            "validation_fixture",
        ),
        allowed_severities=("warning", "optimization"),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "data_store.delete_recovery_missing ",
            "data_store.secret_storage ",
            "data_store.ttl_missing ",
            "data_store.write_key_missing ",
            "transaction.rollback_posture_missing",
        ),
        promotion_requirement=(
            "Transaction rules must cite promoted transaction profiles and "
            "cannot infer ACID "
            "guarantees from handler presence alone."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="operation_volume_optimization",
        title="Operation volume and optimization advice",
        owner_path="src/blueprints/optimization/advisory.py",
        invariant=(
            "Operation, pagination, webhook response, AI cost, and "
            "function-compaction advice "
            "must stay deterministic and non-mutating."
        ),
        evidence_sources=(
            "knowledge_store ",
            "ast_structure ",
            "validation_fixture",
        ),
        allowed_severities=("optimization",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/optimization/blueprint_optimization_advisory_contract.py",
        supported_codes=(
            "aggregator.bundle_limit_missing ",
            "aggregator.source_missing ",
            "aggregator.strategy_missing ",
            "iterator.array_input_missing ",
            "iterator.item_limit_missing ",
            "optimization.ai_model_size_review ",
            "optimization.ai_output_human_review ",
            "optimization.function_nesting_compaction ",
            "optimization.operation_volume_review ",
            "optimization.pagination_required ",
            "optimization.pagination_stop_condition ",
            "optimization.webhook_queue_review ",
            "optimization.webhook_response_timeout_risk ",
            "semantic.operation_volume_review",
        ),
        promotion_requirement=(
            "Optimization rules must remain non-mutating and driven by "
            "promoted knowledge-store "
            "hints or local AST volume evidence."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="designer_message_evidence",
        title="Reviewed designer-message evidence",
        owner_path="src/catalog/knowledge/linter_probe.py",
        invariant=(
            "Make designer-message evidence may appear only as reviewed, "
            "warning-only, "
            "secondary linter signal and never replace offline validation."
        ),
        evidence_sources=(
            "designer_message_api ",
            "knowledge_store ",
            "adr_policy",
        ),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/make_linter_secondary_gate_contract.py",
        supported_codes=("make_designer.warning",),
        promotion_requirement=(
            "Designer-message rules require reviewed normalized evidence "
            "and must keep the "
            "MAKE-DESIGNER-WARN prefix distinct from local AST errors."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="setup_readiness",
        title="Setup readiness blockers",
        owner_path="src/blueprints/validation/setup_readiness.py",
        invariant=(
            "Client-ready coverage cannot be marked complete while local "
            "designer or "
            "validation evidence says a module requires setup."
        ),
        evidence_sources=(
            "designer_message_api ",
            "validation_fixture ",
            "adr_policy",
        ),
        allowed_severities=("error",),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/test_setup_readiness.py",
        supported_codes=(
            "designer.setup ",
            "designer.setupreq ",
            "designer.epochreq ",
            "setup_readiness.setup_required",
        ),
        promotion_requirement=(
            "Setup rules must preserve uncertainty fields when evidence is "
            "inferred from "
            "message text."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="designer_layout_handoff",
        title="Designer layout and handoff notes",
        owner_path="src/blueprints/ast/layout_analysis.py",
        invariant=(
            "Designer labels, branch spacing, coordinates, and module notes "
            "are local "
            "handoff-quality diagnostics, not runtime truth."
        ),
        evidence_sources=("ast_structure", "validation_fixture"),
        allowed_severities=("warning",),
        gate_behavior="advisory_only",
        output_affecting=True,
        focused_test_path="tests/blueprints/ast/blueprint_layout_analysis_contract.py",
        supported_codes=(
            "designer.branch_crowded ",
            "designer.coordinates_overlap ",
            "designer.label_missing ",
            "designer.module_note_missing",
        ),
        promotion_requirement=(
            "Missing-note or layout rules stay advisory unless a separate "
            "handoff ADR makes "
            "them completion blockers."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="generation_gate",
        title="Generation and render gate blockers",
        owner_path="src/blueprints/validation/generation_gate.py",
        invariant=(
            "Generated or assembled blueprints must not render when local "
            "validation returns "
            "blocking errors."
        ),
        evidence_sources=(
            "ast_structure ",
            "catalog_truth ",
            "validation_fixture ",
            "adr_policy",
        ),
        allowed_severities=("error",),
        gate_behavior="blocking_errors_possible",
        output_affecting=True,
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        supported_codes=(
            "generation.unsupported_module ",
            "generation.validation_failed",
        ),
        promotion_requirement=(
            "New gate blocker classes require ADR-backed severity and blocker "
            "tests."
        ),
    ),
    MakeLinterRuleFamily(
        family_id="candidate_rule_discovery",
        title="First-principles candidate rule discovery",
        owner_path="src/blueprints/validation/linter_taxonomy.py",
        invariant=(
            "Candidate rules must declare the Make-domain invariant, local "
            "evidence source, "
            "owner path, and focused proof test before becoming "
            "output-affecting behavior."
        ),
        evidence_sources=(
            "ast_structure ",
            "catalog_truth ",
            "local_failure ",
            "promoted_golden_evidence ",
            "adr_policy",
        ),
        allowed_severities=("warning", "optimization", "explanation"),
        gate_behavior="candidate_non_gating",
        output_affecting=False,
        focused_test_path="tests/blueprints/validation/make_linter_taxonomy_contract.py",
        supported_codes=(),
        promotion_requirement=(
            "Promote only after the manual rule-intake gate records a "
            "decision, evidence "
            "surface, deterministic predicate, severity posture, owner, "
            "fixtures, ADR impact, "
            "and bibliography impact."
        ),
    ),
)

MAKE_LINTER_RULE_FAMILY_IDS: Final[frozenset[str]] = frozenset(
    family.family_id for family in MAKE_LINTER_RULE_FAMILIES
)
_MAKE_LINTER_RULE_FAMILY_BY_ID: Final[dict[str, MakeLinterRuleFamily]] = {
    family.family_id: family for family in MAKE_LINTER_RULE_FAMILIES
}


def _make_linter_rule_family_by_code() -> dict[str, MakeLinterRuleFamily]:
    families_by_code: dict[str, MakeLinterRuleFamily] = {}
    for family in MAKE_LINTER_RULE_FAMILIES:
        for code in family.supported_codes:
            if code in families_by_code:
                message = f"Duplicate Make linter taxonomy code: {code}"
                raise ValueError(message)
            families_by_code[code] = family
    return families_by_code


_MAKE_LINTER_RULE_FAMILY_BY_CODE: Final[dict[str, MakeLinterRuleFamily]] = (
    _make_linter_rule_family_by_code()
)


def make_linter_rule_families() -> tuple[MakeLinterRuleFamily, ...]:
    """Return all Make linter rule families in deterministic review order."""
    return MAKE_LINTER_RULE_FAMILIES


def make_linter_supported_codes() -> tuple[str, ...]:
    """Return all exact Make linter codes recognized by the taxonomy."""
    return tuple(sorted(_MAKE_LINTER_RULE_FAMILY_BY_CODE))


def make_linter_rule_family_by_id(family_id: str) -> MakeLinterRuleFamily:
    """Return one Make linter rule family by ID.

    Raises:
        ValueError: If the family ID is not part of the taxonomy.
    """
    family = _MAKE_LINTER_RULE_FAMILY_BY_ID.get(family_id)
    if family is None:
        message = f"Unsupported Make linter rule family: {family_id!r}"
        raise ValueError(message)
    return family


def make_linter_rule_family_for_code(code: str) -> MakeLinterRuleFamily:
    """Return the taxonomy family for one exact finding or advisory code.

    Raises:
        ValueError: If the code has not been promoted into the taxonomy.
    """
    family = _MAKE_LINTER_RULE_FAMILY_BY_CODE.get(code)
    if family is None:
        message = f"Unsupported Make linter rule code: {code!r}"
        raise ValueError(message)
    return family
