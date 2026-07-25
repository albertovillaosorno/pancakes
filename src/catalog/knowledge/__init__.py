# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001064#repo.make-knowledge.structural-ssot
# - 001064#repo.make-knowledge.live-probe-evidence
# - 001066#repo.make-linter.documented-designer-message-signal
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make knowledge-store public package surface.

Boundary contract:
- Owns: stable imports for Make knowledge-store commands and query projections.
- Must not: implement SQLite IO, raw-spec parsing, or validation behavior.
- Allows: re-exporting focused sibling module APIs.
- Split when: command surfaces become independent executable packages.
- Merge when: another package surface duplicates these exact exports.
"""

from __future__ import annotations

from catalog.knowledge.catalog_graph_future_gate import (
    CatalogNeuralGraphFutureGateReport,
    catalog_neural_graph_future_gate_status,
)
from catalog.knowledge.catalog_graph_projection import (
    CatalogGraphProjectionReport,
    catalog_graph_projection_status,
    rebuild_catalog_graph_projection,
)
from catalog.knowledge.catalog_plan_ssot import (
    CatalogPlanMigrationReport,
    CatalogPlanPlaceholderCleanupReport,
    cleanup_placeholder_semantic_answers,
    connect_catalog_plan_ssot,
    migrate_legacy_catalog_plan_artifacts,
    migrate_legacy_catalog_plan_artifacts_with_retry,
)
from catalog.knowledge.catalog_quality_reset import (
    CATALOG_UNIT_NOTE_SURFACES,
    CatalogQualityProgressReport,
    CatalogQualityResetRunReport,
    CatalogResetUnitInput,
    catalog_quality_progress,
    catalog_reset_units_from_raw_specs,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.linter_probe import (
    MAKE_AST_ERROR_PREFIX,
    MAKE_AST_WARNING_PREFIX,
    MAKE_DESIGNER_MESSAGE_RAW_DIR,
    MAKE_DESIGNER_MESSAGE_SOURCE_KIND,
    MAKE_DESIGNER_WARNING_PREFIX,
    MAKE_LINTER_REPORT_PATH,
    MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT,
    MAKE_SECONDARY_LINTER_SOURCE,
    MakeDesignerMessageBatchReport,
    MakeDesignerMessageBatchRequest,
    MakeDesignerMessageRawRecord,
    MakeLinterBlueprintTransport,
    MakeLinterFinding,
    MakeLinterProbeAuthorization,
    MakeSecondaryLinterReport,
    build_linter_probe_status,
    collect_designer_message_batch,
    designer_message_findings_to_sql,
    normalize_linter_findings,
    probe_linter_findings,
    secondary_linter_result_from_findings,
    secondary_linter_result_from_validation_findings,
    secondary_linter_result_from_warning_payloads,
    secondary_linter_unavailable,
)
from catalog.knowledge.live_probe import (
    DEFAULT_LIVE_PROBE_EVIDENCE_PATH,
    LIVE_PROBE_SOURCE_CONFIDENCE,
    LIVE_PROBE_SOURCE_KIND,
    LiveProbeAuthorization,
    MakeLiveRoundtripTransport,
    build_live_probe_plan,
    diff_json_payloads,
    list_needs_review_conflicts,
    live_probe_authorization_from_json,
    run_live_roundtrip_probe,
    stage_live_probe_result,
)
from catalog.knowledge.models import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_GENERATED_FACTS_PATH,
    DEFAULT_KNOWLEDGE_DB_PATH,
    KNOWLEDGE_SCHEMA_VERSION,
    KnowledgeClaimConflict,
    KnowledgeConstraintFact,
    KnowledgeDesignerMessageEvidence,
    KnowledgeFieldFact,
    KnowledgeModuleAlias,
    KnowledgeModuleFact,
    KnowledgeModuleSearchReport,
    KnowledgeNativeExpectation,
    KnowledgeOptimizerHint,
    KnowledgeRuleFact,
    KnowledgeStoreBuildReport,
    KnowledgeStoreDumpReport,
    KnowledgeStoreQuery,
    KnowledgeStoreStatusReport,
    KnowledgeTransactionProfile,
    NativeModuleGap,
)
from catalog.knowledge.storage import (
    build_knowledge_store,
    dump_knowledge_store,
    knowledge_report_to_json,
    knowledge_store_status,
    load_knowledge_store_query,
    load_knowledge_store_query_for_module_ids,
    search_knowledge_module_ids,
)

__all__ = (
    "CATALOG_UNIT_NOTE_SURFACES",
    "DEFAULT_DB_SNAPSHOT_DIR",
    "DEFAULT_GENERATED_FACTS_PATH",
    "DEFAULT_KNOWLEDGE_DB_PATH",
    "DEFAULT_LIVE_PROBE_EVIDENCE_PATH",
    "KNOWLEDGE_SCHEMA_VERSION",
    "LIVE_PROBE_SOURCE_CONFIDENCE",
    "LIVE_PROBE_SOURCE_KIND",
    "MAKE_AST_ERROR_PREFIX",
    "MAKE_AST_WARNING_PREFIX",
    "MAKE_DESIGNER_MESSAGE_RAW_DIR",
    "MAKE_DESIGNER_MESSAGE_SOURCE_KIND",
    "MAKE_DESIGNER_WARNING_PREFIX",
    "MAKE_LINTER_REPORT_PATH",
    "MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT",
    "MAKE_SECONDARY_LINTER_SOURCE",
    "CatalogGraphProjectionReport",
    "CatalogNeuralGraphFutureGateReport",
    "CatalogPlanMigrationReport",
    "CatalogPlanPlaceholderCleanupReport",
    "CatalogQualityProgressReport",
    "CatalogQualityResetRunReport",
    "CatalogResetUnitInput",
    "KnowledgeClaimConflict",
    "KnowledgeConstraintFact",
    "KnowledgeDesignerMessageEvidence",
    "KnowledgeFieldFact",
    "KnowledgeModuleAlias",
    "KnowledgeModuleFact",
    "KnowledgeModuleSearchReport",
    "KnowledgeNativeExpectation",
    "KnowledgeOptimizerHint",
    "KnowledgeRuleFact",
    "KnowledgeStoreBuildReport",
    "KnowledgeStoreDumpReport",
    "KnowledgeStoreQuery",
    "KnowledgeStoreStatusReport",
    "KnowledgeTransactionProfile",
    "LiveProbeAuthorization",
    "MakeDesignerMessageBatchReport",
    "MakeDesignerMessageBatchRequest",
    "MakeDesignerMessageRawRecord",
    "MakeLinterBlueprintTransport",
    "MakeLinterFinding",
    "MakeLinterProbeAuthorization",
    "MakeLiveRoundtripTransport",
    "MakeSecondaryLinterReport",
    "NativeModuleGap",
    "build_knowledge_store",
    "build_linter_probe_status",
    "build_live_probe_plan",
    "catalog_graph_projection_status",
    "catalog_neural_graph_future_gate_status",
    "catalog_quality_progress",
    "catalog_reset_units_from_raw_specs",
    "cleanup_placeholder_semantic_answers",
    "collect_designer_message_batch",
    "connect_catalog_plan_ssot",
    "designer_message_findings_to_sql",
    "diff_json_payloads",
    "dump_knowledge_store",
    "knowledge_report_to_json",
    "knowledge_store_status",
    "list_needs_review_conflicts",
    "live_probe_authorization_from_json",
    "load_knowledge_store_query",
    "load_knowledge_store_query_for_module_ids",
    "migrate_legacy_catalog_plan_artifacts",
    "migrate_legacy_catalog_plan_artifacts_with_retry",
    "normalize_linter_findings",
    "probe_linter_findings",
    "rebuild_catalog_graph_projection",
    "run_live_roundtrip_probe",
    "search_knowledge_module_ids",
    "secondary_linter_result_from_findings",
    "secondary_linter_result_from_validation_findings",
    "secondary_linter_result_from_warning_payloads",
    "secondary_linter_unavailable",
    "stage_live_probe_result",
    "start_catalog_quality_reset_run",
)
