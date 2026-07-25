# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for the non-gating Make linter rule-family taxonomy.

Boundary contract:
- Owns: taxonomy shape, exact supported-code lookup, and severity posture tests.
- Must not: emit validation findings, contact Make.com, or test rule behavior.
- Allows: metadata checks for rule-family promotion readiness.
- Split when: rule promotion workflow becomes executable.
- Merge when: another validation test owns this exact taxonomy contract.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest
from blueprints.validation import FINDING_SEVERITIES
from blueprints.validation.linter_taxonomy import (
    MakeLinterRuleFamily,
    make_linter_rule_families,
    make_linter_rule_family_by_id,
    make_linter_rule_family_for_code,
    make_linter_supported_codes,
)

from tests.support.paths import repo_root

DECISIONS_LEDGER_PATH = (
    repo_root()
    / "src"
    / "blueprints"
    / "validation"
    / "data"
    / "linter"
    / "decisions"
    / "linter-candidate-decisions.json"
)
QUARANTINE_MANIFEST_PATH = (
    repo_root()
    / "src"
    / "blueprints"
    / "validation"
    / "data"
    / "linter"
    / "quarantine"
    / "manifest.json"
)
FUTURE_FAMILY_SOURCE_FILE = "09_quarantine_and_future_families.md"
EXPECTED_FUTURE_FAMILY_CANDIDATE_IDS = frozenset(
    (
        "Q-ARH-002",
        "Q-CBR-002",
        "Q-CBR-007",
        "Q-CON-007",
        "Q-EMAIL-010",
        "Q-LLM-010",
        "Q-MEM-007",
        "Q-NOT-001-004",
        "Q-OPS-014",
        "Q-PRIV-008",
        "Q-SCH-007",
        "Q-TME-001",
        "Q-TME-010",
        "Q-TYP-009",
    )
)
EXPECTED_FUTURE_FAMILY_QUARANTINE_IDS = frozenset(
    (
        "Q-CBR-002",
        "Q-EMAIL-010",
        "Q-LLM-010",
        "Q-PRIV-008",
        "Q-SCH-007",
        "Q-TME-001",
        "Q-TME-010",
        "Q-TYP-009",
    )
)

REQUIRED_RULE_FAMILIES = {
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
    "graphql_security ",
    "http_url_security ",
    "mapping_reference_contracts ",
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
}


def test_make_linter_taxonomy_declares_required_family_metadata() -> None:
    """Every linter family declares owner, evidence, severity, and proof test.

    metadata.
    """
    families = make_linter_rule_families()
    family_ids = {family.family_id for family in families}

    missing_families = REQUIRED_RULE_FAMILIES.difference(family_ids)
    assert not (missing_families), (
        f"Required linter families are missing: {sorted(missing_families)}"
    )
    for family in families:
        _assert_family_metadata(family)


def test_make_linter_taxonomy_uses_exact_codes_without_duplicates() -> None:
    """Supported rule codes are exact, unique, and classified by one family.

    only.
    """
    codes = make_linter_supported_codes()
    duplicate_codes = tuple(
        code for code, count in Counter(codes).items() if count > 1
    )

    assert not (duplicate_codes), (
        f"Duplicate linter taxonomy codes: {duplicate_codes}"
    )
    assert not ("http.parse_response_missing" not in codes), (
        "Promoted HTTP parse-response warning is missing from taxonomy."
    )
    for code in (
        "http.url_unencrypted_transport ",
        "http.accept_header_missing ",
        "http.api_version_pinning_missing ",
        "http.authorization_redirect_leak ",
        "http.basic_auth_url_credentials ",
        "http.blind_error_catchall ",
        "http.conflict_resume_missing ",
        "http.cookie_passthrough_header ",
        "http.delete_body_guard_missing ",
        "http.dynamic_header_mapping ",
        "http.sensitive_query_parameter ",
        "http.header_crlf_injection ",
        "http.conflict_branch_missing ",
        "http.dynamic_url_host ",
        "http.empty_body_parse_guard_missing ",
        "http.get_body_not_allowed ",
        "http.head_response_body_expected ",
        "http.header_secret_masking_missing ",
        "http.json_body_syntax_invalid ",
        "http.local_untrusted_timeout_retry_missing ",
        "http.not_found_classification_missing ",
        "http.options_usage_guard_missing ",
        "http.path_segment_encoding_missing ",
        "http.patch_semantics_missing ",
        "http.proxy_header_trust_missing ",
        "http.static_secret_literal ",
        "http.tls_verification_disabled ",
        "http.timeout_policy_missing ",
        "http.permanent_error_retry_policy ",
        "http.put_replacement_guard_missing ",
        "http.query_parameter_encoding_missing ",
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
        "crypto.weak_security_hash ",
        "data_exposure.internal_url_literal ",
        "data_exposure.pagination_token_output ",
        "data_exposure.raw_payload_sink ",
        "data_exposure.raw_error_output ",
        "data_exposure.secret_output_sink ",
        "data_exposure.sensitive_http_response_sink ",
        "data_exposure.static_personal_literal ",
        "graphql.depth_budget_exceeded ",
        "graphql.dynamic_query_without_variables ",
        "graphql.error_array_guard_missing ",
        "graphql.field_count_budget_exceeded ",
        "graphql.mutation_idempotency_missing ",
        "graphql.operation_name_missing ",
        "graphql.partial_data_guard_missing ",
        "graphql.production_introspection_query ",
        "graphql.schema_version_missing ",
        "graphql.variable_type_declaration_missing ",
        "ai_agent.conversation_memory_policy_missing ",
        "ai_agent.apply_300_second_default ",
        "ai_agent.configure_appropriate_step_timeout ",
        "ai_agent.exceed_600_seconds ",
        "ai_agent.response_format_missing ",
        "ai_agent.sensitive_action_approval_missing ",
        "ai_agent.tool_name_duplicate ",
        "ai_agent.tool_name_missing ",
        "ai_agent.tool_text_sensitive_literal ",
        "notes.static_personal_literal ",
        "notes.insecure_link_literal ",
        "content.html_dynamic_mapping ",
        "content.markdown_dynamic_mapping ",
        "aggregator.bundle_limit_missing ",
        "graphql.query_minification_suggested ",
        "http.error_status_evaluation_disabled ",
        "http.external_api_allowlist_missing ",
        "http.external_sensitive_mapping ",
        "http.method_url_missing ",
        "iterator.item_limit_missing ",
        "parse_json.schema_missing ",
        "data_store.secret_storage ",
        "data_store.ttl_missing ",
        "scenario.change_reason_missing ",
        "scenario.incident_note_missing ",
        "scenario.owner_missing ",
        "scenario.production_debug_marker ",
        "scenario.rollback_plan_missing ",
        "schedule.sub_minute_interval ",
        "redirect.dynamic_destination_url ",
        "redirect.response_contract_missing ",
        "route.id_duplicate ",
        "sql.dynamic_raw_query_mapping ",
        "webhook.response_content_type_missing",
    ):
        assert not (code not in codes), (
            f"Promoted linter rule is missing: {code}"
        )
    assert "make-http-sre-error" not in codes, (
        "Example-only Make HTTP wording must not become a standalone taxonomy "
        "code."
    )
    for code in codes:
        family = make_linter_rule_family_for_code(code)
        assert not (code not in family.supported_codes), (
            f"Code {code!r} classified outside its owning family: {family}"
        )


def test_unknown_make_linter_rule_codes_are_rejected() -> None:
    """Unknown or prefix-shaped codes cannot silently pass as valid rules."""
    family = make_linter_rule_family_for_code("http.parse_response_missing")

    assert family.family_id == "webhook_http_security", (
        f"Known HTTP rule classified into wrong family: {family}"
    )
    with pytest.raises(ValueError, match="Unsupported Make linter rule code"):
        _ = make_linter_rule_family_for_code(
            "http.parse_response_missing.extra"
        )
    with pytest.raises(ValueError, match="Unsupported Make linter rule code"):
        _ = make_linter_rule_family_for_code("make-http-sre-error")


def test_make_linter_taxonomy_separates_blocking_from_advisory_posture() -> (
    None
):
    """Errors, warnings, optimizations, and secondary linter output stay.

    distinct.
    """
    catalog_family = make_linter_rule_family_for_code("module.unresolved")
    designer_family = make_linter_rule_family_for_code("make_designer.warning")
    error_handler_family = make_linter_rule_family_for_code(
        "error_route.missing"
    )
    optimization_family = make_linter_rule_family_for_code(
        "optimization.pagination_required"
    )
    http_security_family = make_linter_rule_family_for_code(
        "http.url_unencrypted_transport"
    )

    assert catalog_family.gate_behavior == "blocking_errors_possible", (
        f"Unresolved modules must remain blocking-capable: {catalog_family}"
    )
    assert not ("error" not in catalog_family.allowed_severities), (
        f"Unresolved modules must allow error severity: {catalog_family}"
    )
    assert designer_family.allowed_severities == ("warning",), (
        f"Designer linter evidence must stay warning-only: {designer_family}"
    )
    assert designer_family.gate_behavior == "advisory_only", (
        f"Designer linter evidence must stay advisory: {designer_family}"
    )
    if "optimization" not in error_handler_family.allowed_severities:
        message = (
            f"Missing error handlers should keep advisory promotion path:"
            f"{error_handler_family}"
        )
        assert not (
            "optimization" not in error_handler_family.allowed_severities
        ), message
    assert optimization_family.gate_behavior == "advisory_only", (
        f"Optimization hints must not become fatal gates: {optimization_family}"
    )
    if http_security_family.gate_behavior != "blocking_errors_possible":
        message = (
            f"Deterministic HTTP URL security must stay blocking-capable:"
            f"{http_security_family}"
        )
        assert (
            http_security_family.gate_behavior == "blocking_errors_possible"
        ), message
    if "error" not in http_security_family.allowed_severities:
        message = (
            f"Deterministic HTTP URL security must allow error severity:"
            f"{http_security_family}"
        )
        assert not ("error" not in http_security_family.allowed_severities), (
            message
        )


def test_candidate_rule_discovery_is_non_gating_and_evidence_backed() -> None:
    """First-principles candidate discovery is a proof workflow, not runtime.

    output.
    """
    family = make_linter_rule_family_by_id("candidate_rule_discovery")

    assert not (family.output_affecting), (
        f"Candidate discovery must not affect output: {family}"
    )
    assert family.gate_behavior == "candidate_non_gating", (
        f"Candidate discovery must stay non-gating: {family}"
    )
    required_sources = {
        "ast_structure ",
        "catalog_truth ",
        "local_failure ",
        "promoted_golden_evidence",
    }
    assert required_sources.issubset(family.evidence_sources), (
        f"Candidate discovery lacks first-principles evidence sources: {family}"
    )
    assert not (family.supported_codes), (
        f"Candidate discovery must not pre-approve output codes: {family}"
    )
    assert not (
        "manual rule-intake gate" not in family.promotion_requirement
    ), f"Candidate discovery must route through intake policy: {family}"
    with pytest.raises(ValueError, match="Unsupported Make linter rule family"):
        _ = make_linter_rule_family_by_id("temporary_shortcut")


def test_future_family_intake_records_closed_non_runtime_decisions() -> None:
    """Future-family candidates remain reviewed records, not empty active.

    families.
    """
    records = _decision_records_for_source(FUTURE_FAMILY_SOURCE_FILE)
    records_by_id = {
        str(record.get("candidate_id")): record for record in records
    }

    assert set(records_by_id) == EXPECTED_FUTURE_FAMILY_CANDIDATE_IDS, (
        f"Future-family decision coverage drifted: {sorted(records_by_id)}"
    )

    supported_codes = set(make_linter_supported_codes())
    for candidate_id, record in records_by_id.items():
        decision = record.get("decision")
        canonical_rule_code = record.get("canonical_rule_code")
        alias_of_candidate_id = record.get("alias_of_candidate_id")
        quarantine_reason = record.get("quarantine_reason")

        if decision == "downgrade":
            assert isinstance(canonical_rule_code, str), (
                f"Downgraded future-family candidate lacks a canonical "
                f"rule: {record}"
            )
            assert canonical_rule_code in supported_codes, (
                f"Downgraded future-family candidate uses an unknown rule: "
                f"{record}"
            )
            continue
        if decision == "alias_to_canonical":
            assert isinstance(alias_of_candidate_id, str), (
                f"Aliased future-family candidate lacks a canonical target: "
                f"{record}"
            )
            assert alias_of_candidate_id.strip(), (
                f"Aliased future-family candidate has an empty canonical "
                f"target: {record}"
            )
            continue
        if decision == "quarantine":
            assert candidate_id in EXPECTED_FUTURE_FAMILY_QUARANTINE_IDS, (
                f"Unexpected future-family quarantine candidate: {record}"
            )
            assert canonical_rule_code is None, (
                f"Quarantined candidates must not predeclare runtime codes: "
                f"{record}"
            )
            assert isinstance(quarantine_reason, str), (
                f"Quarantined candidate lacks a reason: {record}"
            )
            assert quarantine_reason.strip(), (
                f"Quarantined candidate reason is empty: {record}"
            )
            continue
        assert decision == "reject", (
            f"Unexpected future-family decision state: {record}"
        )
        assert canonical_rule_code is None, (
            f"Rejected candidates must not predeclare runtime codes: {record}"
        )


def test_future_family_quarantine_manifest_preserves_non_promoted_records() -> (
    None
):
    """Quarantined future-family ideas keep durable records and reasons."""
    records = _quarantine_records_for_source(FUTURE_FAMILY_SOURCE_FILE)
    records_by_id = {
        str(record.get("candidate_id")): record for record in records
    }

    assert set(records_by_id) == EXPECTED_FUTURE_FAMILY_QUARANTINE_IDS, (
        f"Future-family quarantine manifest drifted: {sorted(records_by_id)}"
    )

    for record in records_by_id.values():
        candidate_id = str(record.get("candidate_id"))
        reason = str(record.get("quarantine_reason"))
        record_path = str(record.get("record_path"))
        assert record.get("final_state") == "kept_quarantined", (
            f"Future-family quarantine record changed final state: {record}"
        )
        assert record_path.startswith(
            "src/blueprints/validation/data/linter/quarantine/quarantine-and-future-families/"
        ), (
            f"Future-family quarantine record escaped its family directory: "
            f"{record}"
        )

        full_record_path = repo_root() / Path(record_path)
        record_text = full_record_path.read_text(encoding="utf-8")
        assert candidate_id in record_text, (
            f"Quarantine record lost its candidate ID: {full_record_path}"
        )
        assert reason in record_text, (
            f"Quarantine record lost its reason: {full_record_path}"
        )


def _assert_family_metadata(family: MakeLinterRuleFamily) -> None:
    _assert_family_text_metadata(family)
    _assert_family_severity_metadata(family)
    _assert_family_code_metadata(family)


def _assert_family_text_metadata(family: MakeLinterRuleFamily) -> None:
    assert family.title.strip(), f"Rule family title is empty: {family}"
    assert family.owner_path.startswith("src/"), (
        f"Rule family owner must be a source path: {family}"
    )
    assert family.invariant.strip(), f"Rule family invariant is empty: {family}"
    assert family.evidence_sources, (
        f"Rule family evidence sources are empty: {family}"
    )
    assert family.focused_test_path.startswith("tests/"), (
        f"Rule family focused test must be under tests/: {family}"
    )
    assert family.promotion_requirement.strip(), (
        f"Rule family promotion requirement is empty: {family}"
    )


def _assert_family_severity_metadata(family: MakeLinterRuleFamily) -> None:
    unknown_severities = set(family.allowed_severities).difference(
        FINDING_SEVERITIES
    )
    assert not (unknown_severities), (
        f"Rule family declares unsupported severities: {family}"
    )


def _assert_family_code_metadata(family: MakeLinterRuleFamily) -> None:
    if family.gate_behavior == "candidate_non_gating":
        assert not (family.output_affecting), (
            f"Candidate-only families must not affect output: {family}"
        )
    else:
        assert family.supported_codes, (
            f"Runtime families must declare exact supported codes: {family}"
        )


def _decision_records_for_source(
    source_file: str,
) -> tuple[dict[str, object], ...]:
    payload = _load_json_object(DECISIONS_LEDGER_PATH)
    sources_value = payload.get("sources")
    assert isinstance(sources_value, list), (
        f"Decision ledger must expose sources: {payload}"
    )
    sources = cast("list[object]", sources_value)
    for source_value in sources:
        source_payload = _json_record(source_value)
        if source_payload.get("source_file") != source_file:
            continue
        records_value = source_payload.get("records")
        assert isinstance(records_value, list), (
            f"Decision source records must be a list: {source_payload}"
        )
        records = cast("list[object]", records_value)
        return tuple(_json_record(record_value) for record_value in records)
    pytest.fail(f"Decision source is missing: {source_file}")


def _quarantine_records_for_source(
    source_file: str,
) -> tuple[dict[str, object], ...]:
    payload = _load_json_object(QUARANTINE_MANIFEST_PATH)
    records_value = payload.get("records")
    assert isinstance(records_value, list), (
        f"Quarantine manifest must expose records: {payload}"
    )
    records = cast("list[object]", records_value)
    return tuple(
        record
        for record in (
            _json_record(candidate_value) for candidate_value in records
        )
        if record.get("source_file") == source_file
    )


def _json_record(value: object) -> dict[str, object]:
    assert isinstance(value, dict), f"JSON record must be an object: {value}"
    return cast("dict[str, object]", value)


def _load_json_object(path: Path) -> dict[str, object]:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return cast("dict[str, object]", payload)
