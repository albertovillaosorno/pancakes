# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for blueprint repair diagnostics.

Boundary contract:
- Owns: tests for repair diagnostics, staging preparation, and migration
assessment.
- Must not: test tool governance, Git hooks, or generic repository policy.
- Allows: deterministic blueprint/catalog fixtures and repair-domain assertions.
- Split when: repair, staging, and migration behavior need separate test
modules.
- Merge when: another repair diagnostics test duplicates this behavior coverage.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.ast.resolution import MakeAstModuleResolution
from blueprints.repair import (
    assess_module_migration,
    prepare_blueprint_for_staging_import,
    propose_repair_candidates,
    repair_blueprint_offline,
)
from blueprints.validation import validate_blueprint
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from catalog.knowledge import KnowledgeRuleFact, KnowledgeStoreQuery

from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.repair import RepairCandidate, RepairDiagnosticsReport
    from catalog import CatalogSnapshot

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
CLIENT_PATH_TOKENS = ("\\", "/", "src/", "tests/", "Refactor", "node ")
EXPECTED_STAGING_NODE_COUNT = 5
EXPECTED_RESPONSE_STATUS = 200


def test_repair_diagnostics_are_deterministic_for_validation_fixture() -> None:
    """Repair diagnostics convert validator findings into stable candidates."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(repair_fixture())),
        catalog=load_catalog_fixture(),
    )
    diagnostics = propose_repair_candidates(report)

    candidate_ids = tuple(
        candidate.candidate_id for candidate in diagnostics.candidates
    )
    assert candidate_ids == tuple(sorted(candidate_ids)), (
        f"Repair candidates must be deterministic: {candidate_ids}"
    )
    expected_categories = {
        "unsupported_module_discovery",
        "data_validation_risk",
        "webhook_response_risk",
        "operation_limit_risk",
        "incomplete_execution_risk",
        "ai_tool_contract_risk",
        "missing_error_strategy",
    }
    missing_categories = expected_categories.difference(
        diagnostics.categories()
    )
    assert not (missing_categories), (
        f"Repair diagnostics missed categories: {missing_categories}"
    )


def test_repair_diagnostics_include_brittle_api_dependency() -> None:
    """Deprecated resolved modules produce brittle dependency guidance."""
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )

    assert not ("brittle_api_dependency" not in diagnostics.categories()), (
        f"Deprecated module guidance is missing: {diagnostics.categories()}"
    )


def test_repair_diagnostics_include_missing_error_strategy() -> None:
    """Mutating catalog modules without handlers produce error strategy.

    guidance.
    """
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )

    assert not ("missing_error_strategy" not in diagnostics.categories()), (
        f"Missing error strategy guidance is absent: {diagnostics.categories()}"
    )


def test_repair_diagnostics_include_nested_error_path_candidate() -> None:
    """Nested direct error-handler paths produce non-mutating repair.

    guidance.
    """
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(
                json.dumps(nested_error_path_fixture())
            ),
            catalog=load_catalog_fixture(),
        )
    )

    candidate = require_candidate(
        diagnostics,
        source_finding_code="importability.error_handler.nested_unsupported",
    )

    assert candidate.category == "incomplete_execution_risk", (
        f"Nested error path category drifted: {candidate}"
    )
    assert not (candidate.applies_automatically), (
        f"Nested error path repair must not auto-apply: {candidate}"
    )
    assert candidate.source_path == ("flow", 0, "onerror", 0, "onerror"), (
        f"Nested error path source trace drifted: {candidate}"
    )
    assert not (
        "unknown fields" not in " ".join(candidate.preconditions).casefold()
    ), f"Nested error path repair must preserve unknown fields: {candidate}"


def test_repair_diagnostics_include_malformed_error_path_candidate() -> None:
    """Malformed direct error-handler children preserve the original alias.

    path.
    """
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(
                json.dumps(malformed_error_path_fixture())
            ),
            catalog=load_catalog_fixture(),
        )
    )

    candidate = require_candidate(
        diagnostics,
        source_finding_code="ast.error_handler_child_invalid",
    )

    assert candidate.category == "incomplete_execution_risk", (
        f"Malformed error path category drifted: {candidate}"
    )
    assert candidate.source_path == ("flow", 0, "on_error", 0), (
        f"Malformed error path source trace drifted: {candidate}"
    )
    assert candidate.rollback_notes == (
        "No blueprint mutation is performed by diagnostics.",
        "Discard the candidate by leaving the source blueprint unchanged.",
    ), f"Malformed error path rollback posture drifted: {candidate}"


def test_repair_diagnostics_include_invalid_mapping_risk() -> None:
    """Invalid required mappings produce data validation guidance."""
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )

    assert not ("data_validation_risk" not in diagnostics.categories()), (
        f"Invalid mapping guidance is absent: {diagnostics.categories()}"
    )


def test_offline_repair_uses_knowledge_backed_validation() -> None:
    """Offline repair status must preserve knowledge-store validation errors."""
    baseline = repair_blueprint_offline(
        root=parse_make_ast_json_text(json.dumps(knowledge_webhook_fixture())),
        catalog=load_catalog_fixture(),
    )
    assert (
        "webhook.sequential_response_conflict"
        not in baseline.validation_report.codes()
    ), f"Baseline unexpectedly used knowledge rules: {baseline}"

    outcome = repair_blueprint_offline(
        root=parse_make_ast_json_text(json.dumps(knowledge_webhook_fixture())),
        catalog=load_catalog_fixture(),
        knowledge=repair_webhook_knowledge_query(),
    )

    assert outcome.status == "rejected_with_reasons", (
        f"Knowledge-backed repair status drifted: {outcome}"
    )
    assert not (
        "webhook.sequential_response_conflict"
        not in outcome.validation_report.codes()
    ), f"Offline repair dropped promoted knowledge errors: {outcome}"


def test_repair_diagnostics_include_repeated_error_risk() -> None:
    """Repeated blocking validation codes produce grouped repair guidance."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(repeated_error_fixture())),
        catalog=load_catalog_fixture(),
    )
    diagnostics = propose_repair_candidates(report)

    assert not ("repeated_error_risk" not in diagnostics.categories()), (
        f"Repeated error guidance is absent: {diagnostics.categories()}"
    )


def test_repair_diagnostics_candidate_limit_is_deterministic() -> None:
    """Candidate limits keep the deterministic candidate order."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(repair_fixture())),
        catalog=load_catalog_fixture(),
    )
    full = propose_repair_candidates(report)
    limited = propose_repair_candidates(report, max_candidates=2)

    assert limited.candidates == full.candidates[:2], (
        f"Limited candidates are not deterministic: {limited}"
    )


def test_repair_diagnostics_separate_severities_and_avoid_auto_fix_claims() -> (
    None
):
    """Repair candidates preserve severity and never claim automatic.

    mutation.
    """
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )

    assert diagnostics.candidates_for_severity("hard_failure"), (
        "Expected hard-failure repair candidates."
    )
    assert diagnostics.candidates_for_severity("warning"), (
        "Expected warning repair candidates."
    )
    assert diagnostics.candidates_for_severity("optimization"), (
        "Expected optimization repair candidates."
    )
    for candidate in diagnostics.candidates:
        assert not (candidate.applies_automatically), (
            f"Repair diagnostics must not auto-apply candidates: {candidate}"
        )
        assert (
            "fix unsupported external platform behavior"
            not in candidate.client_explanation
        ), f"Candidate overstates external behavior: {candidate}"


def test_repair_diagnostics_require_catalog_evidence_f23d56cc() -> None:
    """Unsupported-module repair guidance cannot fabricate replacements."""
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )
    unsupported_candidates = tuple(
        candidate
        for candidate in diagnostics.candidates
        if candidate.category == "unsupported_module_discovery"
    )

    assert unsupported_candidates, (
        "Expected unsupported-module repair diagnostics."
    )
    for candidate in unsupported_candidates:
        assert not (candidate.applies_automatically), (
            f"Unsupported modules must not be auto-repaired: {candidate}"
        )
        assert not (
            "Validated Make catalog record is available."
            not in candidate.preconditions
        ), f"Unsupported module repair lacks catalog evidence: {candidate}"


def test_repair_diagnostics_client_text_is_path_safe() -> None:
    """Client-facing repair explanations avoid internal names and paths."""
    diagnostics = propose_repair_candidates(
        validate_blueprint(
            root=parse_make_ast_json_text(json.dumps(repair_fixture())),
            catalog=load_catalog_fixture(),
        )
    )

    for candidate in diagnostics.candidates:
        leaked_tokens = [
            token
            for token in CLIENT_PATH_TOKENS
            if token in candidate.client_explanation
        ]
        assert not (leaked_tokens), (
            f"Client repair text leaked {leaked_tokens}: {candidate}"
        )


def test_prepare_blueprint_for_staging_import_9eb38b9c() -> None:
    """Staging import preparation replaces placeholders without mutating source.

    JSON.
    """
    source = staging_fixture()
    prepared = prepare_blueprint_for_staging_import(source)

    source_first_node = object_at(list_member(source, "flow"), 0)
    source_first_branch = object_at(
        list_member(source_first_node, "branches"), 0
    )
    assert "type" not in source_first_branch, (
        f"Staging preparation mutated the source payload: {source}"
    )

    nodes = tuple(flatten_flow_nodes(prepared))
    assert len(nodes) == EXPECTED_STAGING_NODE_COUNT, (
        f"Unexpected staging node traversal: {nodes}"
    )

    first_node = nodes[0]
    branch_types = tuple(
        object_at(list_member(first_node, "branches"), index).get("type")
        for index in range(2)
    )
    assert branch_types == ("condition", "else"), (
        f"BasicIfElse branches were not normalized: {first_node}"
    )

    webhook_parameters = object_member(nodes[1], "parameters")
    assert not (webhook_parameters.get("hook") is not None), (
        f"Custom webhook preparation drifted: {webhook_parameters}"
    )
    assert webhook_parameters.get("maxResults") == 1, (
        f"Custom webhook preparation drifted: {webhook_parameters}"
    )
    http_mapper = object_member(nodes[2], "mapper")
    assert http_mapper.get("url") == "https://example.com/make-canary", (
        f"HTTP request URL placeholder was not replaced: {http_mapper}"
    )
    assert not (http_mapper.get("stopOnHttpError") is not True), (
        f"Missing HTTP safety defaults were not populated: {http_mapper}"
    )
    response_mapper = object_member(nodes[3], "mapper")
    assert response_mapper.get("status") == EXPECTED_RESPONSE_STATUS, (
        f"Webhook response staging payload drifted: {response_mapper}"
    )
    assert response_mapper.get("body") == '{"ok":true}', (
        f"Webhook response staging payload drifted: {response_mapper}"
    )
    ai_mapper = object_member(nodes[4], "mapper")
    assert "makeConnectionId" not in ai_mapper, (
        f"AI staging payload must remove live connection ids: {ai_mapper}"
    )
    assert ai_mapper.get("files") == [], (
        f"AI staging payload should be import-safe: {ai_mapper}"
    )
    assert ai_mapper.get("outputType") == "text", (
        f"AI staging payload should be import-safe: {ai_mapper}"
    )


def test_prepare_blueprint_for_staging_import_7a9cad04() -> None:
    """HTTP staging preparation fills required mapper defaults when keys are.

    absent.
    """
    source: JsonObject = {
        "name": "missing-http-mapper",
        "flow": [{"id": 1, "module": "http:MakeRequest"}],
    }

    prepared = prepare_blueprint_for_staging_import(source)
    http_mapper = object_member(
        object_at(list_member(prepared, "flow"), 0), "mapper"
    )

    expected_values = {
        "authenticationType": "noAuth",
        "url": "https://example.com/make-canary",
        "method": "post",
        "parseResponse": True,
        "stopOnHttpError": True,
    }
    for key, expected_value in expected_values.items():
        assert http_mapper.get(key) == expected_value, (
            f"Missing HTTP mapper default {key!r} was not set: {http_mapper}"
        )


def test_assess_module_migration_requires_resolved_superset_targets() -> None:
    """Module migration assessment rejects unsafe catalog-backed.

    replacements.
    """
    current = module_resolution(
        module_name="http:MakeRequest",
        parameter_ids=("method", "url"),
        interface_field_ids=("status",),
        rpc_dependencies=("rpc://http/listConnections",),
    )
    safe_target = module_resolution(
        module_name="http:MakeRequestV2",
        parameter_ids=("method", "url", "timeout"),
        interface_field_ids=("status", "headers"),
        rpc_dependencies=(
            "rpc://http/listConnections",
            "rpc://http/listRegions",
        ),
    )
    unsafe_target = module_resolution(
        module_name="slack:CreateMessage",
        app_signature=("slack", "search"),
        parameter_ids=("channel",),
        interface_field_ids=(),
        rpc_dependencies=(),
    )

    safe = assess_module_migration(current=current, target=safe_target)
    unsafe = assess_module_migration(current=current, target=unsafe_target)

    assert safe.safe, f"Superset migration should be safe: {safe}"
    assert not (safe.reasons), f"Superset migration should be safe: {safe}"
    expected_reasons = (
        "app slug changes",
        "module kind changes",
        "target loses RPC dependencies",
        "target loses output fields",
        "target loses parameter fields",
    )
    assert not (unsafe.safe), f"Unsafe migration reasons drifted: {unsafe}"
    assert unsafe.reasons == expected_reasons, (
        f"Unsafe migration reasons drifted: {unsafe}"
    )


def test_assess_module_migration_blocks_interface_only_loss() -> None:
    """Module migration assessment reports output interface loss on its own."""
    current = module_resolution(
        module_name="http:MakeRequest",
        parameter_ids=("method", "url"),
        interface_field_ids=("headers", "status"),
        rpc_dependencies=("rpc://http/listConnections",),
    )
    target = module_resolution(
        module_name="http:MakeRequestV2",
        parameter_ids=("method", "timeout", "url"),
        interface_field_ids=("status",),
        rpc_dependencies=("rpc://http/listConnections",),
    )

    assessment = assess_module_migration(current=current, target=target)

    assert not (assessment.safe), (
        f"Interface-only migration loss was not isolated: {assessment}"
    )
    assert assessment.reasons == ("target loses output fields",), (
        f"Interface-only migration loss was not isolated: {assessment}"
    )


def repair_fixture() -> JsonObject:
    """Return a blueprint with representative repair risks."""
    return {
        "name": "repair-diagnostics",
        "flow": [
            {"id": 1, "module": "unknown-service:MissingAction"},
            {
                "id": 2,
                "module": "gateway:CustomWebHook",
                "parameters": {},
            },
            {
                "id": 3,
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
            },
            {"id": 4, "module": "builtin:BasicRouter", "routes": []},
            {"id": 5, "module": "ai-local-agent:RunLocalAIAgent"},
            {
                "id": 6,
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
            },
        ],
    }


def repeated_error_fixture() -> JsonObject:
    """Return a blueprint with repeated unsupported module errors."""
    return {
        "name": "repeated-errors",
        "flow": [
            {"id": 1, "module": "unknown-service:MissingAction"},
            {"id": 2, "module": "other-unknown:MissingAction"},
        ],
    }


def knowledge_webhook_fixture() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "name": "knowledge-webhook-repair",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "response": {"status": EXPECTED_RESPONSE_STATUS},
                "parameters": {"processing": "sequential"},
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def nested_error_path_fixture() -> JsonObject:
    """Return a blueprint with unsupported nested error-handler paths."""
    return {
        "name": "nested-error-path-repair",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "onerror": [
                    {
                        "id": 2,
                        "module": "builtin:Ignore",
                        "metadata": {"custom": {"keep": True}},
                        "onerror": [{"id": 3, "module": "builtin:Break"}],
                    }
                ],
                "parameters": {
                    "method": "POST",
                    "url": "https://example.invalid/items",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
    }


def malformed_error_path_fixture() -> JsonObject:
    """Return a blueprint with a malformed on_error child."""
    return {
        "name": "malformed-error-path-repair",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "on_error": [{"notFlow": []}],
                "parameters": {
                    "method": "POST",
                    "url": "https://example.invalid/items",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
    }


def repair_webhook_knowledge_query() -> KnowledgeStoreQuery:
    """Return the promoted webhook rule needed by offline repair tests."""
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
                    "Sequential webhook processing conflicts with webhook"
                    "responses."
                ),
                adr_anchor="001064#repo.make-knowledge.course-promoted-rules",
            ),
        ),
        optimizer_hints=(),
    )


def staging_fixture() -> JsonObject:
    """Return a blueprint with Make placeholders for staging import tests."""
    return {
        "name": "staging",
        "flow": [
            {
                "id": 1,
                "module": "builtin:BasicIfElse",
                "branches": [
                    {
                        "flow": [
                            {
                                "id": 2,
                                "module": "gateway:CustomWebHook",
                                "parameters": {"hook": "{{PLACEHOLDER_HOOK}}"},
                            },
                            {
                                "id": 3,
                                "module": "http:MakeRequest",
                                "mapper": {
                                    "authenticationType": (
                                        "{{PLACEHOLDER_AUTHENTICATIONTYPE}}"
                                    ),
                                    "url": "{{PLACEHOLDER_URL}}",
                                    "method": "{{PLACEHOLDER_METHOD}}",
                                    "parseResponse": (
                                        "{{PLACEHOLDER_PARSERESPONSE}}"
                                    ),
                                },
                            },
                        ]
                    },
                    {"flow": []},
                ],
            },
            {
                "id": 4,
                "module": "gateway:WebhookRespond",
                "mapper": {"status": "{{PLACEHOLDER_STATUS}}"},
            },
            {
                "id": 5,
                "module": "ai-local-agent:RunLocalAIAgent",
                "mapper": {
                    "makeConnectionId": "live-connection",
                    "defaultModel": "{{PLACEHOLDER_DEFAULTMODEL}}",
                    "message": "{{PLACEHOLDER_MESSAGE}}",
                    "files": "{{PLACEHOLDER_UNKNOWN}}",
                },
            },
        ],
    }


def flatten_flow_nodes(payload: JsonObject) -> list[JsonObject]:
    """Return active node payloads from the staging fixture."""
    nodes: list[JsonObject] = []
    for item in list_member(payload, "flow"):
        assert isinstance(item, dict), f"Expected flow node: {item}"
        node = cast("JsonObject", item)
        nodes.append(node)
        for branch in cast("list[object]", node.get("branches", [])):
            assert isinstance(branch, dict), f"Expected branch object: {branch}"
            for child in list_member(cast("JsonObject", branch), "flow"):
                assert isinstance(child, dict), (
                    f"Expected branch child node: {child}"
                )
                nodes.append(cast("JsonObject", child))
    return nodes


def module_resolution(
    *,
    module_name: str,
    parameter_ids: tuple[str, ...],
    interface_field_ids: tuple[str, ...],
    rpc_dependencies: tuple[str, ...],
    app_signature: tuple[str, str] = ("http", "action"),
) -> MakeAstModuleResolution:
    """Return one resolved module binding for migration assessment tests."""
    app_slug, module_kind = app_signature
    return MakeAstModuleResolution(
        node_id="1",
        module_token=module_name,
        status="resolved",
        catalog_module_id=f"module:{module_name}",
        app_slug=app_slug,
        app_version="1.0",
        module_kind=module_kind,
        internal_name=module_name.partition(":")[2],
        module_family=module_name.partition(":")[2].casefold(),
        parameter_ids=parameter_ids,
        expect_field_ids=(),
        interface_field_ids=interface_field_ids,
        rpc_dependencies=rpc_dependencies,
        deprecated=False,
        issues=(),
        raw_spec_references=(),
    )


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return an object member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return cast("JsonObject", value)


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return a list member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_at(items: list[object], index: int) -> JsonObject:
    """Return one object item from a JSON list."""
    item = items[index]
    assert isinstance(item, dict), (
        f"Expected object list item at {index}: {items}"
    )
    return cast("JsonObject", item)


def require_candidate(
    diagnostics: RepairDiagnosticsReport,
    *,
    source_finding_code: str,
) -> RepairCandidate:
    """Return one repair candidate by source finding code."""
    for candidate in diagnostics.candidates:
        if candidate.source_finding_code == source_finding_code:
            return candidate
    failure_message = (
        f"Expected repair candidate for {source_finding_code!r}: {diagnostics}"
    )
    assert_unexpected_success(failure_message)
    return None


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
