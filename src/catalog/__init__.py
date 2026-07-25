# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make module and action catalog slice boundary.

Boundary contract:
- Owns: the catalog package export surface.
- Must not: implement catalog compilation, validation, drift, or JSON behavior.
- Allows: re-exporting catalog public APIs from focused sibling modules.
- Split when: exports need runtime branching or adapter-specific behavior.
- Merge when: another package surface duplicates these exact catalog exports.
"""

from __future__ import annotations

from catalog.compiler import (
    catalog_snapshot_json,
    compile_catalog_from_manifest,
    extract_rpc_dependencies,
)
from catalog.drift import (
    detect_catalog_drift,
    drift_report_to_json,
    revalidate_catalog_targets,
    revalidation_report_to_json,
)
from catalog.fallback import (
    CatalogModuleCandidate,
    CatalogOnlyPlanningHints,
    CatalogOnlyRetrievalReport,
    CatalogOnlyValidationReport,
    CatalogRetrievalTruncatedError,
    ModulePlannerHints,
    SemanticRequirementPlan,
    build_catalog_planning_hints,
    build_semantic_requirement_plan,
    require_complete_catalog_retrieval,
    retrieve_catalog_modules,
    validate_catalog_module_selection,
)
from catalog.generation_audit import (
    CatalogGenerationAuditBlocker,
    CatalogGenerationAuditEntry,
    CatalogGenerationAuditReport,
    build_catalog_generation_audit,
)
from catalog.identity import SLICE_NAME
from catalog.intelligence import (
    CatalogModuleIntelligence,
    build_catalog_intelligence_profile,
    infer_module_intelligence,
)
from catalog.json_payloads import (
    catalog_snapshot_from_json,
    catalog_snapshot_to_json,
)
from catalog.knowledge import (
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
    build_knowledge_store,
    dump_knowledge_store,
    knowledge_report_to_json,
    knowledge_store_status,
    load_knowledge_store_query,
    load_knowledge_store_query_for_module_ids,
    search_knowledge_module_ids,
)
from catalog.lineage import (
    CatalogLineageReport,
    CatalogModuleLineage,
    build_catalog_lineage_report,
)
from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    CatalogApp,
    CatalogAppVersion,
    CatalogConstraint,
    CatalogDriftReport,
    CatalogEntityChange,
    CatalogField,
    CatalogModule,
    CatalogModuleQueryReport,
    CatalogRawSpecDiagnostic,
    CatalogRevalidationIssue,
    CatalogRevalidationReport,
    CatalogRevalidationTarget,
    CatalogSnapshot,
)
from catalog.refresh import CatalogRefreshReport, refresh_catalog_from_source
from catalog.storage import (
    DEFAULT_CATALOG_SNAPSHOT_PATH,
    CatalogSnapshotWriteReport,
    write_catalog_snapshot,
)
from catalog.validation import (
    require_catalog_module,
    validate_catalog_snapshot,
)

__all__ = (
    "CATALOG_SCHEMA_VERSION",
    "DEFAULT_CATALOG_SNAPSHOT_PATH",
    "DEFAULT_DB_SNAPSHOT_DIR",
    "DEFAULT_GENERATED_FACTS_PATH",
    "DEFAULT_KNOWLEDGE_DB_PATH",
    "KNOWLEDGE_SCHEMA_VERSION",
    "SLICE_NAME",
    "CatalogApp",
    "CatalogAppVersion",
    "CatalogConstraint",
    "CatalogDriftReport",
    "CatalogEntityChange",
    "CatalogField",
    "CatalogGenerationAuditBlocker",
    "CatalogGenerationAuditEntry",
    "CatalogGenerationAuditReport",
    "CatalogLineageReport",
    "CatalogModule",
    "CatalogModuleCandidate",
    "CatalogModuleIntelligence",
    "CatalogModuleLineage",
    "CatalogModuleQueryReport",
    "CatalogOnlyPlanningHints",
    "CatalogOnlyRetrievalReport",
    "CatalogOnlyValidationReport",
    "CatalogRawSpecDiagnostic",
    "CatalogRefreshReport",
    "CatalogRetrievalTruncatedError",
    "CatalogRevalidationIssue",
    "CatalogRevalidationReport",
    "CatalogRevalidationTarget",
    "CatalogSnapshot",
    "CatalogSnapshotWriteReport",
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
    "ModulePlannerHints",
    "NativeModuleGap",
    "SemanticRequirementPlan",
    "build_catalog_generation_audit",
    "build_catalog_intelligence_profile",
    "build_catalog_lineage_report",
    "build_catalog_planning_hints",
    "build_knowledge_store",
    "build_semantic_requirement_plan",
    "catalog_snapshot_from_json",
    "catalog_snapshot_json",
    "catalog_snapshot_to_json",
    "compile_catalog_from_manifest",
    "detect_catalog_drift",
    "drift_report_to_json",
    "dump_knowledge_store",
    "extract_rpc_dependencies",
    "infer_module_intelligence",
    "knowledge_report_to_json",
    "knowledge_store_status",
    "load_knowledge_store_query",
    "load_knowledge_store_query_for_module_ids",
    "refresh_catalog_from_source",
    "require_catalog_module",
    "require_complete_catalog_retrieval",
    "retrieve_catalog_modules",
    "revalidate_catalog_targets",
    "revalidation_report_to_json",
    "search_knowledge_module_ids",
    "validate_catalog_module_selection",
    "validate_catalog_snapshot",
    "write_catalog_snapshot",
)
