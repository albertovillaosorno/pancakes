# ruff: noqa: S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for the generated Make knowledge SQLite store.

Boundary contract:
- Owns: tests for SQL snapshots, SQLite rebuilds, status, dumps, and queries.
- Must not: contact live Make services, validate blueprints, or install
services.
- Allows: temporary raw-spec manifests, deterministic SQL snapshots, and SQLite
IO.
- Split when: query, dump, and raw-spec normalization tests need separate
modules.
- Merge when: another catalog test duplicates this knowledge-store coverage.
"""

from __future__ import annotations

import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

import pytest
from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_KNOWLEDGE_DB_PATH,
    KnowledgeStoreBuildReport,
    KnowledgeStoreDumpReport,
    KnowledgeStoreQuery,
    KnowledgeStoreStatusReport,
    build_knowledge_store,
    dump_knowledge_store,
    knowledge_store_status,
    load_knowledge_store_query,
)
from catalog.knowledge.__main__ import main as knowledge_cli_main
from catalog.knowledge.projection import knowledge_query_to_catalog_snapshot
from catalog.knowledge.schema import RUNTIME_EXTENSION_TABLES
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    sync_raw_specs,
)

from tests.support.json_payloads import json_object_from_text
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from _pytest.capture import CaptureFixture
    from languages.make.raw_specs.models import JsonObject

REPO_ROOT = repo_root()
FIXED_GENERATED_AT = "2026-04-30T00:00:00+00:00"
NEXT_GENERATED_AT = "2026-05-01T00:00:00+00:00"
EXPECTED_MODULE_HISTORY_ROWS = 2
EXPECTED_CLAIM_EVIDENCE_COUNT = 4
EXPECTED_CLAIM_CONFLICT_COUNT = 2
HTTP_MODULE_ID = "module:http:1.0:action:makeRequest"
HTTP_URL_FIELD_ID = "field:module:http:1.0:action:makeRequest:parameter:url"
HTTP_MODULE_SELECTOR = "http"
TEMPORAL_HISTORY_SNAPSHOT = (
    DEFAULT_DB_SNAPSHOT_DIR / "make_temporal_history.sql"
)


class InMemoryRawSpecSource:
    """Deterministic raw-spec source for knowledge-store tests."""

    def __init__(self, specs: Mapping[MakeRawSpecTarget, JsonObject]) -> None:
        """Validate the catalog knowledge-store contract."""
        self._specs = dict(specs)

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return the helper result.

        Returns:
            Helper result.
        """
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return the helper result.

        Returns:
            Helper result.
        """
        return self._specs[target]


def test_knowledge_store_builds_from_tracked_sql_and_raw_specs(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)

    report = build_knowledge_store(repo_root=tmp_path)
    status = knowledge_store_status(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    _assert_build_report_and_status(report=report, status=status)
    _assert_promoted_query_facts(query)
    _assert_structural_query_facts(query)
    _assert_knowledge_query_helpers(query)


def test_knowledge_store_bootstrap_uses_editable_schema_authority(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    schema_projection = tmp_path / DEFAULT_DB_SNAPSHOT_DIR / "schema.sql"
    _ = schema_projection.write_text(
        "SELECT invalid_restore_projection_should_not_bootstrap_schema;\n",
        encoding="utf-8",
    )
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)

    report = build_knowledge_store(repo_root=tmp_path)
    status = knowledge_store_status(repo_root=tmp_path)

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        table_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall(),
        )
    finally:
        connection.close()

    tables = {row[0] for row in table_rows}
    assert report.schema_version == 13
    assert status.schema_version == 13
    assert "modules" in tables
    assert "make_raw_spec_payloads" in tables
    assert not (tables & set(RUNTIME_EXTENSION_TABLES))


def test_knowledge_store_rebuild_preserves_local_semantic_and_runtime_state(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    seed_preserved_local_state(database_path)

    _ = build_knowledge_store(repo_root=tmp_path)

    connection = sqlite3.connect(database_path)
    try:
        row_counts = {
            table: current_table_count(connection, table)
            for table in (
                "ingest_runs",
                "source_documents",
                "entity_nodes",
                "make_raw_spec_update_reviews",
                "catalog_plan_semantic_answers",
                "catalog_search_documents",
                "catalog_units",
                "catalog_unit_outputs",
                "mcp_backlog_entries",
            )
        }
        old_raw_ingest_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM ingest_runs WHERE run_id = "
                "'old-raw-ingest'"
            ).fetchone(),
        )[0]
        raw_backlog_index_rows = cast(
            "Sequence[Sequence[object]]",
            connection.execute(
                "PRAGMA index_list('mcp_backlog_entries')"
            ).fetchall(),
        )
        backlog_indexes = {str(row[1]) for row in raw_backlog_index_rows}
    finally:
        connection.close()

    assert row_counts == {
        "ingest_runs": 1,
        "source_documents": 1,
        "entity_nodes": 1,
        "make_raw_spec_update_reviews": 1,
        "catalog_plan_semantic_answers": 1,
        "catalog_search_documents": 1,
        "catalog_units": 1,
        "catalog_unit_outputs": 1,
        "mcp_backlog_entries": 1,
    }
    assert old_raw_ingest_count == 0
    assert "idx_mcp_backlog_entries_status" in backlog_indexes


def _assert_build_report_and_status(
    *,
    report: KnowledgeStoreBuildReport,
    status: KnowledgeStoreStatusReport,
) -> None:
    assert report.database_path == "src/data/pancakes.sqlite", (
        f"Unexpected database path: {report.database_path}"
    )
    assert report.raw_spec_record_count == 1, (
        f"Raw-spec facts were not normalized: {report}"
    )
    assert report.module_count == 1, (
        f"Raw-spec facts were not normalized: {report}"
    )
    assert status.status == "degraded", (
        f"Native module gaps should degrade incomplete fixture status: {status}"
    )
    assert any(
        gap.app_slug == "ai-provider" for gap in status.native_module_gaps
    ), (
        f"Native platform gaps must include ai-provider: "
        f"{status.native_module_gaps}"
    )
    ai_provider_gap = next(
        gap
        for gap in status.native_module_gaps
        if gap.app_slug == "ai-provider"
    )
    assert ai_provider_gap.critical, (
        f"Native platform gap details are incomplete: {ai_provider_gap}"
    )
    assert ai_provider_gap.missing_kinds == ("action", "agent"), (
        f"Native platform gap details are incomplete: {ai_provider_gap}"
    )


def _assert_promoted_query_facts(query: KnowledgeStoreQuery) -> None:
    assert any(alias.alias_text == "trigger" for alias in query.aliases), (
        f"Promoted aliases were not loaded: {query.aliases}"
    )
    has_webhook_rule = any(
        rule.rule_code == "webhook.sequential_response_conflict"
        for rule in query.rule_facts
    )
    assert has_webhook_rule, (
        f"Promoted course rules were not loaded: {query.rule_facts}"
    )
    assert (
        query.canonical_token_for_alias("Scenario Trigger") == "trigger_imt"
    ), f"Alias lookup did not normalize promoted aliases: {query.aliases}"
    assert (
        query.rule_by_code("webhook.sequential_response_conflict") is not None
    ), f"Rule lookup did not return promoted webhook rule: {query.rule_facts}"
    assert (
        query.optimizer_hint_by_code("optimization.pagination_required")
        is not None
    ), (
        f"Hint lookup did not return promoted pagination hint: "
        f"{query.optimizer_hints}"
    )


def _assert_structural_query_facts(query: KnowledgeStoreQuery) -> None:
    assert any(
        module.module_id == HTTP_MODULE_ID for module in query.modules
    ), f"Normalized module facts were not loaded: {query.modules}"
    required_field_paths = {
        field.path
        for field in query.fields
        if field.module_id == HTTP_MODULE_ID and field.required
    }
    assert required_field_paths == {("method",), ("url",)}, (
        f"Normalized field facts were not loaded: {required_field_paths}"
    )
    assert any(
        constraint.constraint_key == "required"
        and constraint.field_id == HTTP_URL_FIELD_ID
        for constraint in query.constraints
    ), f"Normalized constraint facts were not loaded: {query.constraints}"
    assert any(
        expectation.app_slug == "http"
        for expectation in query.native_expectations
    ), (
        f"Native module expectations were not loaded: "
        f"{query.native_expectations}"
    )


def _assert_knowledge_query_helpers(query: KnowledgeStoreQuery) -> None:
    module = query.module_by_id(HTTP_MODULE_ID)
    assert module is not None, (
        f"Module lookup did not return the normalized HTTP action: {module}"
    )
    assert module.module_kind == "action", (
        f"Module lookup did not return the normalized HTTP action: {module}"
    )
    parameter_fields = query.fields_for_module(
        HTTP_MODULE_ID,
        direction="parameter",
    )
    assert {field.path for field in parameter_fields} == {
        ("method",),
        ("url",),
    }, f"Module field lookup returned unexpected fields: {parameter_fields}"
    url_constraints = query.constraints_for_field(HTTP_URL_FIELD_ID)
    assert any(
        constraint.constraint_key == "type" for constraint in url_constraints
    ), (
        f"Field constraint lookup returned unexpected constraints: "
        f"{url_constraints}"
    )
    assert any(
        profile.profile_id == "transaction-profile-http-write"
        for profile in query.transaction_profiles
    ), (
        f"Transaction safety profiles were not loaded: "
        f"{query.transaction_profiles}"
    )
    http_profiles = query.transaction_profiles_matching(
        module_token_key=HTTP_MODULE_SELECTOR
    )
    assert any(
        profile.operation_kind == "external_write" for profile in http_profiles
    ), f"Transaction profile lookup failed for HTTP writes: {http_profiles}"
    expectation = query.native_expectation_for_slug("http")
    assert expectation is not None, (
        f"Native expectation lookup returned unexpected value: {expectation}"
    )
    assert not ("action" not in expectation.expected_kinds), (
        f"Native expectation lookup returned unexpected value: {expectation}"
    )


def test_knowledge_store_query_keeps_structural_facts_opt_in(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)

    query = load_knowledge_store_query(repo_root=tmp_path)

    assert query.rule_facts, (
        f"Lightweight query must still load promoted behavior facts: {query}"
    )
    assert query.optimizer_hints, (
        f"Lightweight query must still load promoted behavior facts: {query}"
    )
    assert query.transaction_profiles, (
        f"Lightweight query must still load promoted behavior facts: {query}"
    )
    assert not (query.modules), (
        f"Structural facts should require opt-in loading: {query}"
    )
    assert not (query.fields), (
        f"Structural facts should require opt-in loading: {query}"
    )
    assert not (query.constraints), (
        f"Structural facts should require opt-in loading: {query}"
    )
    assert not (query.native_expectations), (
        f"Structural facts should require opt-in loading: {query}"
    )


def test_knowledge_store_query_rejects_stale_generated_sqlite(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=NEXT_GENERATED_AT,
        action_label="Make HTTP request",
    )

    with pytest.raises(FileNotFoundError, match="stale_manifest"):
        _ = load_knowledge_store_query(
            repo_root=tmp_path, include_structural_facts=True
        )


def test_promoted_course_facts_have_claim_ledger_rows(tmp_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)

    facts = promoted_course_fact_rows(tmp_path)
    claims = promoted_course_claims_by_id(tmp_path)
    missing_claims = [
        fact_id
        for fact_id, _source_ref in facts
        if _expected_claim_id(fact_id) not in claims
    ]
    assert not (missing_claims), (
        f"Promoted course facts are missing claim rows: {missing_claims}"
    )

    incomplete_claims = [
        claim_id
        for claim_id, claim in claims.items()
        if not all(
            claim[field]
            for field in ("adr_anchor", "code_target", "test_target")
        )
    ]
    assert not (incomplete_claims), (
        f"Promoted claims must be ADR, code, and test backed: "
        f"{incomplete_claims}"
    )


def test_claim_evidence_conflicts_are_arbitrated_by_confidence_and_recency(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    write_claim_evidence_snapshot(tmp_path)

    report = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(repo_root=tmp_path)

    assert report.claim_evidence_count == EXPECTED_CLAIM_EVIDENCE_COUNT, (
        f"Claim conflict counts were not materialized: {report}"
    )
    assert report.claim_conflict_count == EXPECTED_CLAIM_CONFLICT_COUNT, (
        f"Claim conflict counts were not materialized: {report}"
    )

    credit_conflicts = query.claim_conflicts_for_key("ai_agent.credit_limit")
    assert len(credit_conflicts) == 1, (
        f"Expected one credit-limit conflict: {credit_conflicts}"
    )
    credit_conflict = credit_conflicts[0]
    assert (
        credit_conflict.winning_evidence_id
        == "raw-spec-ai-agent-credit-limit-v2"
    ), (
        f"Source confidence should select the raw-spec evidence: "
        f"{credit_conflict}"
    )
    assert credit_conflict.resolution_status == "resolved", (
        f"Higher-confidence evidence should be resolved: {credit_conflict}"
    )
    assert (
        query.winning_claim_value_for_key("ai_agent.credit_limit")
        == '{"credits":5}'
    ), f"Winning claim value lookup failed: {credit_conflict}"

    timeout_conflicts = query.claim_conflicts_for_key(
        "webhook.response.timeout_seconds"
    )
    assert len(timeout_conflicts) == 1, (
        f"Expected one webhook-timeout conflict: {timeout_conflicts}"
    )
    timeout_conflict = timeout_conflicts[0]
    assert (
        timeout_conflict.winning_evidence_id == "course-webhook-timeout-180"
    ), (
        f"Evidence recency should select the newer course evidence: "
        f"{timeout_conflict}"
    )
    assert (
        timeout_conflict.arbitration_reason == "newer evidence observed_at"
    ), f"Conflict reason should expose recency arbitration: {timeout_conflict}"


def test_reviewed_designer_message_evidence_loads_for_validator_queries(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    write_designer_message_evidence_snapshot(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)

    query = load_knowledge_store_query(repo_root=tmp_path)

    messages = query.reviewed_designer_messages_for_node("2", "json:ParseJSON")
    assert len(messages) == 1, (
        f"Expected one reviewed designer message for node 2: {query}"
    )
    case_variant_messages = query.reviewed_designer_messages_for_node(
        "2", "JSON:ParseJSON"
    )
    assert case_variant_messages == messages, (
        f"Designer message module matching must be case-insensitive: {query}"
    )
    missing_module_messages = query.reviewed_designer_messages_for_node(
        "2", None
    )
    assert not (missing_module_messages), "".join(
        (
            (
                "Module-specific designer evidence must not match unknown "
                "module tokens: "
            ),
            f"{missing_module_messages}",
        )
    )
    wrong_module_messages = query.reviewed_designer_messages_for_node(
        "2", "http:makeRequest"
    )
    assert not (wrong_module_messages), "".join(
        (
            (
                "Module-specific designer evidence must not match different "
                "module tokens: "
            ),
            f"{wrong_module_messages}",
        )
    )
    message = messages[0]
    assert message.severity == "warning", (
        f"Designer evidence must stay warning-only and source-tagged: {message}"
    )
    assert message.source_kind == "designer_message", (
        f"Designer evidence must stay warning-only and source-tagged: {message}"
    )
    assert message.review_status == "reviewed", (
        f"Designer evidence lost review metadata: {message}"
    )
    assert message.field_path == "parameters.url", (
        f"Designer evidence lost review metadata: {message}"
    )
    root_messages = query.reviewed_root_designer_messages()
    assert len(root_messages) == 1, (
        f"Expected one reviewed root designer message: {root_messages}"
    )
    root_message = root_messages[0]
    assert not (root_message.node_id is not None), (
        f"Root designer evidence must not invent node identity: {root_message}"
    )
    assert not (root_message.module_slug is not None), (
        f"Root designer evidence must not invent node identity: {root_message}"
    )
    assert root_message.finding_id == "designer-message-reviewed-root", (
        f"Malformed root designer rows must not apply globally: {root_messages}"
    )


def test_ui_only_designer_diagnostics_remain_reviewed_warning_evidence(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    write_designer_message_evidence_snapshot(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)

    query = load_knowledge_store_query(repo_root=tmp_path)

    loaded_finding_ids = {
        message.finding_id for message in query.designer_messages
    }
    assert loaded_finding_ids == {
        "designer-message-malformed-root-module",
        "designer-message-reviewed-root",
        "designer-message-test-url",
    }, (
        f"UI-only diagnostics should load only reviewed warnings: "
        f"{query.designer_messages}"
    )
    assert all(
        message.source_kind == "designer_message"
        for message in query.designer_messages
    ), f"UI-only diagnostics must stay source-tagged: {query.designer_messages}"
    assert all(
        message.review_status == "reviewed"
        for message in query.designer_messages
    ), f"UI-only diagnostics must stay review-gated: {query.designer_messages}"
    assert all(
        message.severity == "warning" for message in query.designer_messages
    ), (
        f"UI-only diagnostics must not promote Make UI errors: "
        f"{query.designer_messages}"
    )
    root_messages = query.reviewed_root_designer_messages()
    assert tuple(message.finding_id for message in root_messages) == (
        "designer-message-reviewed-root",
    ), f"Malformed UI diagnostics must not apply globally: {root_messages}"


def test_knowledge_store_dump_preserves_temporal_history(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(
        tmp_path, generated_at=FIXED_GENERATED_AT, action_label="Make a request"
    )
    _ = build_knowledge_store(repo_root=tmp_path)
    dump_report = dump_temporal_history_snapshot(tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=NEXT_GENERATED_AT,
        action_label="Make HTTP request",
    )

    rebuild_report = build_knowledge_store(repo_root=tmp_path)

    assert not (dump_report.row_count <= 0), (
        f"Expected dumped SQL rows: {dump_report}"
    )
    assert rebuild_report.module_count == 1, (
        f"Only one current module row should remain: {rebuild_report}"
    )
    rows = module_history_rows(tmp_path)
    assert len(rows) == EXPECTED_MODULE_HISTORY_ROWS, (
        f"Expected previous and current module history rows: {rows}"
    )
    assert rows[0][1] == NEXT_GENERATED_AT, (
        f"Temporal valid_to history was not maintained: {rows}"
    )
    assert not (rows[1][1] is not None), (
        f"Temporal valid_to history was not maintained: {rows}"
    )


def test_knowledge_store_closes_removed_raw_spec_fields(tmp_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=FIXED_GENERATED_AT,
        include_method_parameter=True,
    )
    _ = build_knowledge_store(repo_root=tmp_path)
    _ = dump_temporal_history_snapshot(tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=NEXT_GENERATED_AT,
        include_method_parameter=False,
    )

    _ = build_knowledge_store(repo_root=tmp_path)

    rows = field_history_rows(
        tmp_path,
        "field:module:http:1.0:action:makeRequest:parameter:method",
    )
    assert rows == [(FIXED_GENERATED_AT, NEXT_GENERATED_AT)], (
        f"Removed raw-spec field should be closed, not current: {rows}"
    )


def test_knowledge_store_partial_refresh_keeps_unrefreshed_apps_current(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_and_slack_raw_specs(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    _ = dump_temporal_history_snapshot(tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=NEXT_GENERATED_AT,
        include_method_parameter=False,
    )

    _ = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    assert (
        query.module_by_id("module:slack:1.0:action:createMessage") is not None
    ), f"Partial HTTP refresh must not retire Slack facts: {query.modules}"


def dump_temporal_history_snapshot(
    repo_root_path: Path,
) -> KnowledgeStoreDumpReport:
    """Return the helper result.

    Returns:
        Helper result.
    """
    return dump_knowledge_store(
        repo_root=repo_root_path,
        output_path=TEMPORAL_HISTORY_SNAPSHOT,
    )


def test_knowledge_store_rejects_malformed_raw_spec_booleans(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    payload = http_raw_spec(action_label="Make a request")
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    parameters = cast("list[JsonObject]", actions[0]["parameters"])
    parameters[0]["required"] = "true"
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    with pytest.raises(TypeError, match="required"):
        _ = build_knowledge_store(repo_root=tmp_path)


def test_knowledge_store_quarantines_malformed_raw_spec_field_collections(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    payload = http_raw_spec(action_label="Make a request")
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    actions[0]["parameters"] = {"name": "url", "type": "url", "required": True}
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    report = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    assert (
        query.module_by_id("module:http:1.0:action:makeRequest") is not None
    ), f"Malformed field metadata must not drop the module: {query.modules}"
    module_id = "module:http:1.0:action:makeRequest"
    field_paths = {
        field.path for field in query.fields if field.module_id == module_id
    }
    assert field_paths == {("statusCode",)}, (
        f"Only valid sibling fields should be ingested: {field_paths}"
    )
    diagnostic_codes = {
        diagnostic.code for diagnostic in report.raw_spec_diagnostics
    }
    assert diagnostic_codes == {"raw_spec.field_collection_shape_invalid"}, (
        f"Expected field collection diagnostic: {report.raw_spec_diagnostics}"
    )
    diagnostic = report.raw_spec_diagnostics[0]
    assert diagnostic.module_id == "module:http:1.0:action:makeRequest", (
        f"Diagnostic must identify the containing module: {diagnostic}"
    )
    assert diagnostic.collection_path == ("parameters",), (
        f"Diagnostic must identify the bad collection: {diagnostic}"
    )


def test_knowledge_store_quarantines_duplicate_raw_spec_fields_with_source_path(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    payload = http_raw_spec(action_label="Make a request")
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    parameters = cast("list[JsonObject]", actions[0]["parameters"])
    parameters.append({"name": "url", "type": "text", "required": False})
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    report = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    url_fields = [
        field
        for field in query.fields
        if field.module_id == HTTP_MODULE_ID and field.path == ("url",)
    ]
    assert len(url_fields) == 1, (
        f"Duplicate raw fields must not create duplicate facts: {url_fields}"
    )
    assert url_fields[0].field_type == "url", (
        f"The first duplicate field occurrence should be retained: {url_fields}"
    )
    duplicate_diagnostics = [
        diagnostic
        for diagnostic in report.raw_spec_diagnostics
        if diagnostic.code == "raw_spec.field_duplicate"
    ]
    assert len(duplicate_diagnostics) == 1, (
        f"Expected one duplicate-field diagnostic: "
        f"{report.raw_spec_diagnostics}"
    )
    diagnostic = duplicate_diagnostics[0]
    assert diagnostic.field_path == ("url",), (
        f"Duplicate diagnostics must identify the normalized field path: "
        f"{diagnostic}"
    )
    assert diagnostic.collection_path == ("parameters", 2), (
        f"Duplicate diagnostics must identify the raw source field: "
        f"{diagnostic}"
    )


def test_knowledge_store_projects_dynamic_selector_rpc_dependencies(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    payload = http_raw_spec(action_label="Make a request")
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    parameters = cast("list[JsonObject]", actions[0]["parameters"])
    parameters[1]["options"] = "rpc://http/listMethods"
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    _ = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )
    snapshot = knowledge_query_to_catalog_snapshot(query=query)
    projected_module = next(
        module
        for app_snapshot in snapshot.apps
        for version in app_snapshot.versions
        for module in version.modules
        if module.module_id == HTTP_MODULE_ID
    )

    assert projected_module.rpc_dependencies == ("rpc://http/listMethods",), (
        f"Dynamic selector RPC dependencies were not projected: "
        f"{projected_module}"
    )


def test_knowledge_store_ingests_make_native_default_collections(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(
        app_slug="builtin-defaults", app_version="current"
    )
    payload: JsonObject = {
        "app": {
            "name": "builtin-defaults",
            "version": "current",
            "label": "Built-in defaults",
            "latest": True,
            "manifest": {"version": 2},
            "feeders": [{"name": "FeedBundle", "label": "Feed bundle"}],
            "agents": [{"name": "RunAgent", "label": "Run AI agent"}],
            "returners": [{"name": "ReturnData", "label": "Return data"}],
        }
    }
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    _ = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    module_facts = {
        (module.module_kind, module.internal_name)
        for module in query.modules
        if module.app_slug == "builtin-defaults"
    }
    assert module_facts == {
        ("action", "ReturnData"),
        ("agent", "RunAgent"),
        ("transformer", "FeedBundle"),
    }, (
        f"Make-native collections were not generalized into knowledge "
        f"facts: {module_facts}"
    )


def test_knowledge_store_quarantines_malformed_nested_raw_spec_fields(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    payload = http_raw_spec(action_label="Make a request")
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    parameters = cast("list[JsonObject]", actions[0]["parameters"])
    parameters[0]["schema"] = [{"name": "headers"}, "not-a-field"]
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: payload}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    report = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )

    module_id = "module:http:1.0:action:makeRequest"
    field_paths = {
        field.path for field in query.fields if field.module_id == module_id
    }
    assert field_paths == {
        ("url",),
        ("url", "headers"),
        ("method",),
        ("statusCode",),
    }, f"Valid sibling and nested fields should be ingested: {field_paths}"
    diagnostic_codes = {
        diagnostic.code for diagnostic in report.raw_spec_diagnostics
    }
    assert diagnostic_codes == {"raw_spec.nested_field_item_shape_invalid"}, (
        f"Expected nested field item diagnostic: {report.raw_spec_diagnostics}"
    )
    diagnostic = report.raw_spec_diagnostics[0]
    assert diagnostic.field_path == ("url",), (
        f"Diagnostic must identify the parent field path: {diagnostic}"
    )
    assert diagnostic.collection_path == ("parameters", 0, "schema", 1), (
        f"Diagnostic must identify the nested bad item: {diagnostic}"
    )


def test_knowledge_store_failed_build_preserves_existing_database(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    database_path = tmp_path / "src/data/pancakes.sqlite"
    before_size = database_path.stat().st_size
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            """
            UPDATE make_raw_spec_payloads
            SET payload_json = ?
            WHERE valid_to IS NULL
            """,
            ("{}\n",),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="SQLite raw spec hash mismatch"):
        _ = build_knowledge_store(repo_root=tmp_path)

    assert database_path.stat().st_size == before_size, (
        "Failed build should preserve the existing SQLite file."
    )
    connection = sqlite3.connect(database_path)
    try:
        module_row = cast(
            "tuple[object, ...] | None",
            connection.execute(
                "SELECT module_id FROM modules WHERE module_id = ?",
                ("module:http:1.0:action:makeRequest",),
            ).fetchone(),
        )
    finally:
        connection.close()
    assert module_row is not None, (
        "Failed build lost the last-good module facts."
    )
    assert not (
        database_path.with_name("pancakes.sqlite.build.tmp").exists()
    ), "Failed build should remove its temporary SQLite file."


def test_knowledge_store_rebuild_refuses_semantic_state_schema_loss(
    tmp_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    seed_incompatible_catalog_search_document_schema(database_path)

    with pytest.raises(RuntimeError, match="catalog_search_documents"):
        _ = build_knowledge_store(repo_root=tmp_path)

    assert not (
        database_path.with_name("pancakes.sqlite.build.tmp").exists()
    ), "Rejected rebuild should remove its temporary SQLite file."
    connection = sqlite3.connect(database_path)
    try:
        assert current_table_count(connection, "catalog_search_documents") == 1
    finally:
        connection.close()


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def seed_preserved_local_state(database_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.executescript(
            """
            INSERT INTO ingest_runs (
            run_id, source_kind, source_ref, generated_at_utc, fingerprint,
            record_count
            ) VALUES (
              'preserved-ingest',
              'semantic_projection',
              'tests:preserved-ingest',
              '2026-05-18T00:00:00+00:00',
              'fingerprint-preserved-ingest',
              1
            );

            INSERT INTO ingest_runs (
            run_id, source_kind, source_ref, generated_at_utc, fingerprint,
            record_count
            ) VALUES (
              'old-raw-ingest',
              'raw_spec_manifest',
              'tests:old-raw-ingest',
              '2026-05-17T00:00:00+00:00',
              'fingerprint-old-raw-ingest',
              1
            );

            INSERT INTO source_documents (
            document_id, domain, source_path, media_type, source_text,
            source_kind,
              source_ref, valid_from, valid_to, fingerprint, ingest_run_id
            ) VALUES (
              'source-document-preserved',
              'catalog',
              'tests/catalog.md',
              'text/markdown',
              'Synthetic preserved source text.',
              'test',
              'tests:source-document-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL,
              'fingerprint-source-document-preserved',
              'preserved-ingest'
            );

            INSERT INTO entity_nodes (
            node_id, domain, entity_kind, canonical_label, payload_json,
            source_kind,
              source_ref, valid_from, valid_to, fingerprint, ingest_run_id
            ) VALUES (
              'node-preserved',
              'catalog',
              'module',
              'Preserved node',
              '{}',
              'test',
              'tests:node-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL,
              'fingerprint-node-preserved',
              'preserved-ingest'
            );

            INSERT INTO make_raw_spec_update_reviews (
            review_id, app_slug, app_version, app_label, update_kind,
            review_status,
            review_surfaces_json, source_sha256, previous_sha256,
            previous_valid_from,
            source_kind, source_ref, valid_from, valid_to, fingerprint,
            ingest_run_id
            ) VALUES (
              'raw-review-preserved',
              'slack',
              '1.0',
              'Slack',
              'changed',
              'reviewed',
              '[]',
              'source-sha-preserved',
              'previous-sha-preserved',
              '2026-05-17T00:00:00+00:00',
              'test',
              'tests:raw-review-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL,
              'fingerprint-raw-review-preserved',
              'preserved-ingest'
            );

            INSERT INTO catalog_plan_ranges (
            range_id, range_label, range_start, range_end, surface, status,
            source_kind,
              source_ref, fingerprint, valid_from, valid_to
            ) VALUES (
              7,
              '000007-000007',
              7,
              7,
              'synthetic preserved catalog plan',
              'complete',
              'test',
              'tests:catalog-plan-range-preserved',
              'fingerprint-catalog-plan-range-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL
            );

            INSERT INTO catalog_plan_units (
            unit_number, range_id, status, surface, evidence_path, commit_hash,
            semantic_answer_sha256, updated_at_utc, source_kind, source_ref,
            fingerprint,
              valid_from, valid_to
            ) VALUES (
              7,
              7,
              'semantic_answered',
              'synthetic preserved catalog plan',
              '',
              '',
              'semantic-answer-sha-preserved',
              '2026-05-18T00:00:00+00:00',
              'test',
              'tests:catalog-plan-unit-preserved',
              'fingerprint-catalog-plan-unit-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL
            );

            INSERT INTO catalog_plan_semantic_answers (
              unit_number, unit_id, answer_json, answer_sha256, answer_status,
            evidence_status, source_kind, source_ref, created_at_utc,
            saved_by_tool,
              valid_to
            ) VALUES (
              7,
              '000007',
              '{"summary":"Synthetic preserved answer."}',
              'semantic-answer-sha-preserved',
              'accepted',
              'reviewed',
              'test',
              'tests:catalog-plan-answer-preserved',
              '2026-05-18T00:00:00+00:00',
              'catalog.work.save',
              NULL
            );

            INSERT INTO catalog_runs (
              run_id, run_status, reset_strategy, priority_policy_json,
              old_semantic_status, incomplete_coverage_policy, created_at_utc,
              source_kind, source_ref, fingerprint
            ) VALUES (
              'run-preserved',
              'complete',
              'hard_reset',
              '{}',
              'complete',
              'allow_incomplete',
              '2026-05-18T00:00:00+00:00',
              'test',
              'tests:catalog-run-preserved',
              'fingerprint-catalog-run-preserved'
            );

            INSERT INTO catalog_units (
            run_id, unit_id, unit_type, priority_band, priority_order,
            source_ref,
            source_hash, source_size_bytes, complexity_score, status, locked_by,
              locked_at_utc, lease_expires_at_utc, lease_token, attempt_count,
            completed_at_utc, validation_status, coverage_status,
            created_at_utc,
              updated_at_utc
            ) VALUES (
              'run-preserved',
              'unit-preserved',
              'module',
              'p0',
              1,
              'tests:unit-preserved',
              'unit-source-hash-preserved',
              42,
              3,
              'completed',
              NULL,
              NULL,
              NULL,
              'lease-preserved',
              1,
              '2026-05-18T00:00:00+00:00',
              'valid',
              'covered',
              '2026-05-18T00:00:00+00:00',
              '2026-05-18T00:00:00+00:00'
            );

            INSERT INTO catalog_unit_outputs (
            run_id, unit_id, lease_token, worker_id, output_json, output_sha256,
            validation_status, saved_by_tool, created_at_utc, source_kind,
            source_ref,
              fingerprint
            ) VALUES (
              'run-preserved',
              'unit-preserved',
              'lease-preserved',
              'test-worker',
              '{}',
              'output-sha-preserved',
              'valid',
              'catalog.work.save',
              '2026-05-18T00:00:00+00:00',
              'test',
              'tests:catalog-unit-output-preserved',
              'fingerprint-catalog-unit-output-preserved'
            );

            INSERT INTO catalog_search_documents (
            document_id, surface, title, body, record_kind, tags_json,
            search_text,
              source_kind, source_ref, fingerprint, valid_from, valid_to
            ) VALUES (
              'catalog-search-preserved',
              'catalog',
              'Preserved semantic candidate',
              'Synthetic preserved candidate body.',
              'semantic_candidate',
              '[]',
              'preserved semantic candidate',
              'test',
              'tests:catalog-search-preserved',
              'fingerprint-catalog-search-preserved',
              '2026-05-18T00:00:00+00:00',
              NULL
            );

            CREATE TABLE mcp_backlog_entries (
              entry_id TEXT PRIMARY KEY,
              domain TEXT NOT NULL,
              title TEXT NOT NULL,
              status TEXT NOT NULL,
              priority INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              source_kind TEXT NOT NULL,
              source_ref TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              updated_at_utc TEXT NOT NULL
            );

            CREATE INDEX idx_mcp_backlog_entries_status
              ON mcp_backlog_entries (status, priority, domain);

            INSERT INTO mcp_backlog_entries (
            entry_id, domain, title, status, priority, payload_json,
            source_kind,
              source_ref, created_at_utc, updated_at_utc
            ) VALUES (
              'backlog-preserved',
              'catalog',
              'Preserved backlog entry',
              'open',
              1,
              '{}',
              'test',
              'tests:backlog-preserved',
              '2026-05-18T00:00:00+00:00',
              '2026-05-18T00:00:00+00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def seed_incompatible_catalog_search_document_schema(
    database_path: Path,
) -> None:
    """Validate the catalog knowledge-store contract."""
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.executescript(
            """
            PRAGMA foreign_keys = OFF;

            ALTER TABLE catalog_search_documents
              RENAME TO catalog_search_documents_full;

            CREATE TABLE catalog_search_documents (
              document_id TEXT PRIMARY KEY,
              title TEXT NOT NULL
            );

            INSERT INTO catalog_search_documents (document_id, title)
            VALUES ('semantic-document-must-not-disappear', 'Must not
            disappear');

            DROP TABLE catalog_search_documents_full;

            PRAGMA foreign_keys = ON;
            """
        )
        connection.commit()
    finally:
        connection.close()


def current_table_count(connection: sqlite3.Connection, table: str) -> int:
    """Return the helper result.

    Returns:
        Helper result.
    """
    row = cast(
        "tuple[int] | None",
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone(),
    )
    assert row is not None, f"Expected a row-count result for {table}."
    return row[0]


def sync_http_raw_spec(
    tmp_path: Path,
    *,
    generated_at: str,
    action_label: str = "Make a request",
    include_method_parameter: bool = True,
) -> None:
    """Validate the catalog knowledge-store contract."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource(
            {
                target: http_raw_spec(
                    action_label=action_label,
                    include_method_parameter=include_method_parameter,
                )
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=generated_at,
    )


def sync_http_and_slack_raw_specs(tmp_path: Path, *, generated_at: str) -> None:
    """Validate the catalog knowledge-store contract."""
    http_target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    slack_target = MakeRawSpecTarget(app_slug="slack", app_version="1.0")
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource(
            {
                http_target: http_raw_spec(action_label="Make a request"),
                slack_target: slack_raw_spec(),
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=generated_at,
    )


def write_claim_evidence_snapshot(tmp_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    snapshot_path = (
        tmp_path / DEFAULT_DB_SNAPSHOT_DIR / "claim_evidence_test.sql"
    )
    _ = snapshot_path.write_text(
        """
INSERT OR REPLACE INTO claim_evidence (
  evidence_id,
  claim_key,
  domain,
  value_json,
  claim_text,
  source_confidence,
  evidence_observed_at,
  source_kind,
  source_ref,
  claim_ref,
  valid_from,
  valid_to,
  fingerprint,
  adr_anchor
) VALUES
  (
    'course-ai-agent-credit-limit-10',
    'ai_agent.credit_limit',
    'ai_agents',
    '{"credits":10}',
    'A course claim says ai-agent has a 10-credit limit.',
    60,
    '2026-04-29T00:00:00+00:00',
    'course',
        'docs/fixtures/sample-source.md#test-credit-limit',
    'claim-ai-agent-tool-description',
    '2026-04-29T00:00:00+00:00',
    NULL,
    'claim-evidence-course-ai-agent-credit-limit-10',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  ),
  (
    'raw-spec-ai-agent-credit-limit-v2',
    'ai_agent.credit_limit',
    'ai_agents',
    '{"credits":5}',
    'A raw spec claim says ai-agent has a 5-credit limit.',
    90,
    '2026-04-30T00:00:00+00:00',
    'raw_spec',
    'temp/raw-specs-json/ai-agent/current.json#test-credit-limit',
    NULL,
    '2026-04-30T00:00:00+00:00',
    NULL,
    'claim-evidence-raw-spec-ai-agent-credit-limit-v2',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  ),
  (
    'course-webhook-timeout-120',
    'webhook.response.timeout_seconds',
    'webhooks',
    '{"seconds":120}',
    'Older course evidence says webhook responses have a 120-second timeout.',
    80,
    '2026-04-28T00:00:00+00:00',
    'course',
    'docs/fixtures/sample-source.md#test-timeout-old',
    'claim-webhook-response-timeout',
    '2026-04-28T00:00:00+00:00',
    NULL,
    'claim-evidence-course-webhook-timeout-120',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  ),
  (
    'course-webhook-timeout-180',
    'webhook.response.timeout_seconds',
    'webhooks',
    '{"seconds":180}',
    'Newer course evidence says webhook responses have a 180-second timeout.',
    80,
    '2026-04-30T00:00:00+00:00',
    'course',
    'docs/fixtures/sample-source.md#test-timeout-new',
    'claim-webhook-response-timeout',
    '2026-04-30T00:00:00+00:00',
    NULL,
    'claim-evidence-course-webhook-timeout-180',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  );
""".lstrip(),
        encoding="utf-8",
    )


def write_designer_message_evidence_snapshot(tmp_path: Path) -> None:
    """Validate the catalog knowledge-store contract."""
    snapshot_path = (
        tmp_path
        / DEFAULT_DB_SNAPSHOT_DIR
        / "designer_message_evidence_test.sql"
    )
    _ = snapshot_path.write_text(
        """
INSERT OR REPLACE INTO designer_message_evidence (
  finding_id,
  node_id,
  module_slug,
  severity,
  message,
  category,
  field_path,
  review_status,
  source_kind,
  source_ref,
  valid_from,
  valid_to,
  fingerprint,
  adr_anchor
) VALUES (
  'designer-message-test-url',
  '2',
  'json:ParseJSON',
  'warning',
  'URL mapping is incomplete.',
  'mapping',
  'parameters.url',
  'reviewed',
  'designer_message',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-test-url',
  '001066#repo.make-linter.documented-designer-message-signal'
),
(
  'designer-message-needs-review-url',
  '2',
  'json:ParseJSON',
  'warning',
  'Needs-review URL mapping is incomplete.',
  'mapping',
  'parameters.url',
  'needs_review',
  'designer_message',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-needs-review-url',
  '001066#repo.make-linter.documented-designer-message-signal'
),
(
  'designer-message-reviewed-error-url',
  '2',
  'json:ParseJSON',
  'error',
  'Error-channel designer evidence should not load.',
  'mapping',
  'parameters.url',
  'reviewed',
  'designer_message',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-reviewed-error-url',
  '001066#repo.make-linter.documented-designer-message-signal'
),
(
  'designer-message-reviewed-source-url',
  '2',
  'json:ParseJSON',
  'warning',
  'Wrong-source designer evidence should not load.',
  'mapping',
  'parameters.url',
  'reviewed',
  'live_probe',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-reviewed-source-url',
  '001066#repo.make-linter.documented-designer-message-signal'
),
(
  'designer-message-reviewed-root',
  NULL,
  NULL,
  'warning',
  'Scenario warning is still active.',
  'scenario',
  NULL,
  'reviewed',
  'designer_message',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-reviewed-root',
  '001066#repo.make-linter.documented-designer-message-signal'
),
(
  'designer-message-malformed-root-module',
  NULL,
  'json:ParseJSON',
  'warning',
  'Node-scoped module evidence without a node should not apply globally.',
  'scenario',
  NULL,
  'reviewed',
  'designer_message',
  'make-api:/api/v2/scenarios/112/blueprint?draft=true',
  '2026-04-30T00:00:00+00:00',
  NULL,
  'designer-message-evidence-malformed-root-module',
  '001066#repo.make-linter.documented-designer-message-signal'
);
""".lstrip(),
        encoding="utf-8",
    )


def http_raw_spec(
    *,
    action_label: str,
    include_method_parameter: bool = True,
) -> JsonObject:
    """Return the helper result.

    Returns:
        Helper result.
    """
    parameters: list[JsonObject] = [
        {"name": "url", "type": "url", "required": True}
    ]
    if include_method_parameter:
        parameters.append(
            {"name": "method", "type": "select", "required": True}
        )
    return {
        "app": {
            "name": "http",
            "version": "1.0",
            "label": "HTTP",
            "latest": True,
            "manifest": {"version": 2},
            "actions": [
                {
                    "name": "makeRequest",
                    "label": action_label,
                    "parameters": parameters,
                    "interface": [{"name": "statusCode", "type": "number"}],
                }
            ],
        }
    }


def slack_raw_spec() -> JsonObject:
    """Return the helper result.

    Returns:
        Helper result.
    """
    return {
        "app": {
            "name": "slack",
            "version": "1.0",
            "label": "Slack",
            "latest": True,
            "manifest": {"version": 2},
            "actions": [
                {
                    "name": "createMessage",
                    "label": "Create a message",
                    "parameters": [
                        {"name": "channel", "type": "text", "required": True},
                        {"name": "text", "type": "text", "required": True},
                    ],
                    "interface": [{"name": "messageId", "type": "text"}],
                }
            ],
        }
    }


def module_history_rows(tmp_path: Path) -> list[tuple[str, str | None]]:
    """Return the helper result.

    Returns:
        Helper result.
    """
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    connection = sqlite3.connect(database_path)
    try:
        raw_rows = cast(
            "Sequence[Sequence[object]]",
            connection.execute(
                """
                SELECT valid_from, valid_to
                FROM modules
                WHERE module_id = 'module:http:1.0:action:makeRequest'
                ORDER BY valid_from
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    rows = tuple(tuple(row) for row in raw_rows)
    return [
        (str(row[0]), None if row[1] is None else str(row[1])) for row in rows
    ]


def field_history_rows(
    tmp_path: Path, field_id: str
) -> list[tuple[str, str | None]]:
    """Return the helper result.

    Returns:
        Helper result.
    """
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    connection = sqlite3.connect(database_path)
    try:
        raw_rows = cast(
            "Sequence[Sequence[object]]",
            connection.execute(
                """
                SELECT valid_from, valid_to
                FROM fields
                WHERE field_id = ?
                ORDER BY valid_from
                """,
                (field_id,),
            ).fetchall(),
        )
    finally:
        connection.close()
    rows = tuple(tuple(row) for row in raw_rows)
    return [
        (str(row[0]), None if row[1] is None else str(row[1])) for row in rows
    ]


def promoted_course_fact_rows(tmp_path: Path) -> list[tuple[str, str]]:
    """Return the helper result.

    Returns:
        Helper result.
    """
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    connection = sqlite3.connect(database_path)
    try:
        raw_rows = cast(
            "Sequence[Sequence[object]]",
            connection.execute(
                """
                SELECT rule_id, source_ref
                FROM rule_facts
                WHERE source_kind = 'course' AND valid_to IS NULL
                UNION ALL
                SELECT hint_id, source_ref
                FROM optimizer_hints
                WHERE source_kind = 'course' AND valid_to IS NULL
                ORDER BY 1
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    return [(str(row[0]), str(row[1])) for row in raw_rows]


def promoted_course_claims_by_id(tmp_path: Path) -> dict[str, dict[str, str]]:
    """Return the helper result.

    Returns:
        Helper result.
    """
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    connection = sqlite3.connect(database_path)
    try:
        raw_rows = cast(
            "Sequence[Sequence[object]]",
            connection.execute(
                """
                SELECT claim_id, adr_anchor, code_target, test_target
                FROM course_claims
                WHERE status = 'promoted' AND valid_to IS NULL
                ORDER BY claim_id
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    return {
        str(row[0]): {
            "adr_anchor": str(row[1]),
            "code_target": str(row[2]),
            "test_target": str(row[3]),
        }
        for row in raw_rows
    }


def _expected_claim_id(fact_id: str) -> str:
    """Return the helper result.

    Returns:
        Helper result.
    """
    return "claim-" + fact_id.removeprefix("course-rule-").removeprefix(
        "course-hint-"
    )


def test_knowledge_store_cli_build_outputs_json(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """Validate the catalog knowledge-store contract."""
    prepare_snapshot_dir(tmp_path)

    exit_code = knowledge_cli_main(["--repo-root", str(tmp_path), "build"])
    captured = capsys.readouterr()
    payload = json_object_from_text(captured.out, "knowledge build output")

    assert exit_code == 0, f"Unexpected CLI payload: {exit_code}, {payload}"
    assert payload["database_path"] == "src/data/pancakes.sqlite", (
        f"Unexpected CLI payload: {exit_code}, {payload}"
    )
