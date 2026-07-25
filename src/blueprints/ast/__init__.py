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

"""Typed Pancakes blueprint AST slice boundary.

Boundary contract:
- Owns: the public import surface for blueprint AST capabilities.
- Must not: implement parsing, rendering, resolution, or layout behavior.
- Allows: re-exporting stable blueprint AST models and owned functions.
- Split when: exports require compatibility adapters or optional integrations.
- Merge when another package marker duplicates this blueprint API surface.
Current public names retain `MakeAst*` compatibility where existing Make
behavior depends on them. General graph semantics belong in `ir`.
"""

from __future__ import annotations

from blueprints.ast.artifacts import (
    BLUEPRINT_BUNDLE_ROOT,
    MakeBlueprintBundlePayloads,
    make_blueprint_bundle_root,
    persist_make_blueprint_bundle,
    slugify_blueprint_name,
    validate_make_blueprint_bundle_collection,
)
from blueprints.ast.assembler import (
    BlueprintAssemblySpec,
    BlueprintNodeAssemblySpec,
    assemble_blueprint_from_catalog,
)
from blueprints.ast.compilation import (
    BlueprintCompileRequest,
    CompiledBlueprint,
    compile_blueprint_from_module_ids,
)
from blueprints.ast.delta import (
    LAYOUT_DELTA_CATEGORIES,
    BlueprintAstDelta,
    BlueprintComparisonReport,
    BlueprintDeltaFinding,
    compare_blueprints,
    compute_ast_delta,
)
from blueprints.ast.errors import MakeAstParseError
from blueprints.ast.evidence import MakeAstEvidenceReport, ast_evidence_report
from blueprints.ast.execution_paths import iter_ast_execution_paths
from blueprints.ast.identity import SLICE_NAME
from blueprints.ast.layout_analysis import (
    BlueprintLayoutMovement,
    BlueprintLayoutTransitionReport,
    analyze_blueprint_layout_transition,
)
from blueprints.ast.layout_models import (
    BlueprintLayoutPlan,
    BlueprintNodeLayout,
    BlueprintNoteLayout,
)
from blueprints.ast.layout_payloads import apply_blueprint_layout
from blueprints.ast.layout_planner import (
    DEFAULT_COLUMN_SPACING,
    DEFAULT_ROW_SPACING,
    plan_blueprint_layout,
)
from blueprints.ast.models import (
    AST_NODE_KINDS,
    AST_SCHEMA_VERSION,
    AstNodeKind,
    AstPathPart,
    JsonObject,
    MakeAstFilter,
    MakeAstNode,
    MakeAstRawSpecBinding,
    MakeAstRoot,
    MakeAstRoute,
    MakeAstScenario,
    MakeAstScenarioEndpoint,
    MakeAstScheduleConfig,
    MakeAstSourceTrace,
    PancakesAstFilter,
    PancakesAstNode,
    PancakesAstRawSpecBinding,
    PancakesAstRoot,
    PancakesAstRoute,
    PancakesAstScenario,
    PancakesAstScenarioEndpoint,
    PancakesAstScheduleConfig,
    PancakesAstSourceTrace,
)
from blueprints.ast.module_roles import (
    infer_module_role,
    module_looks_like_trigger,
    module_looks_like_webhook_response,
)
from blueprints.ast.orphans import (
    DesignerOrphanGroup,
    DesignerOrphanNode,
    extract_designer_orphan_groups,
)
from blueprints.ast.parser import parse_make_ast, parse_make_ast_json_text
from blueprints.ast.references import (
    MakeReferenceUsage,
    collect_reference_targets,
    collect_reference_usages,
    cross_node_reference_errors,
    iter_top_level_nodes,
    note_binding_errors,
    rewrite_cross_node_references,
)
from blueprints.ast.resolution import (
    MakeAstModuleResolution,
    MakeAstResolutionReport,
    require_module_resolution,
    resolve_ast_modules,
)
from blueprints.ast.runtime_drift import (
    BlueprintRuntimeDrift,
    DesignerMessageEvidence,
    collect_designer_message_evidence,
    designer_message_signature,
    evaluate_runtime_drift,
)
from blueprints.ast.runtime_metadata import (
    BlueprintErrorDirective,
    BlueprintLatencyObservation,
    BlueprintRuntimeFilterCondition,
    BlueprintRuntimeMetadata,
    BlueprintRuntimeNote,
    BlueprintRuntimeSampleObservation,
    extract_error_directives,
    extract_forman_mapping_events,
    extract_latency_observations,
    extract_runtime_filter_conditions,
    extract_runtime_notes,
    extract_runtime_sample_observations,
    inspect_blueprint_runtime_metadata,
)
from blueprints.ast.snapshots import ast_root_snapshot
from blueprints.ast.traversal import (
    collect_ast_node_ids,
    iter_ast_nodes,
    require_ast_node,
)

__all__ = (
    "AST_NODE_KINDS",
    "AST_SCHEMA_VERSION",
    "BLUEPRINT_BUNDLE_ROOT",
    "DEFAULT_COLUMN_SPACING",
    "DEFAULT_ROW_SPACING",
    "LAYOUT_DELTA_CATEGORIES",
    "SLICE_NAME",
    "AstNodeKind",
    "AstPathPart",
    "BlueprintAssemblySpec",
    "BlueprintAstDelta",
    "BlueprintComparisonReport",
    "BlueprintCompileRequest",
    "BlueprintDeltaFinding",
    "BlueprintErrorDirective",
    "BlueprintLatencyObservation",
    "BlueprintLayoutMovement",
    "BlueprintLayoutPlan",
    "BlueprintLayoutTransitionReport",
    "BlueprintNodeAssemblySpec",
    "BlueprintNodeLayout",
    "BlueprintNoteLayout",
    "BlueprintRuntimeDrift",
    "BlueprintRuntimeFilterCondition",
    "BlueprintRuntimeMetadata",
    "BlueprintRuntimeNote",
    "BlueprintRuntimeSampleObservation",
    "CompiledBlueprint",
    "DesignerMessageEvidence",
    "DesignerOrphanGroup",
    "DesignerOrphanNode",
    "JsonObject",
    "MakeAstEvidenceReport",
    "MakeAstFilter",
    "MakeAstModuleResolution",
    "MakeAstNode",
    "MakeAstParseError",
    "MakeAstRawSpecBinding",
    "MakeAstResolutionReport",
    "MakeAstRoot",
    "MakeAstRoute",
    "MakeAstScenario",
    "MakeAstScenarioEndpoint",
    "MakeAstScheduleConfig",
    "MakeAstSourceTrace",
    "MakeBlueprintBundlePayloads",
    "MakeReferenceUsage",
    "PancakesAstFilter",
    "PancakesAstNode",
    "PancakesAstRawSpecBinding",
    "PancakesAstRoot",
    "PancakesAstRoute",
    "PancakesAstScenario",
    "PancakesAstScenarioEndpoint",
    "PancakesAstScheduleConfig",
    "PancakesAstSourceTrace",
    "analyze_blueprint_layout_transition",
    "apply_blueprint_layout",
    "assemble_blueprint_from_catalog",
    "ast_evidence_report",
    "ast_root_snapshot",
    "collect_ast_node_ids",
    "collect_designer_message_evidence",
    "collect_reference_targets",
    "collect_reference_usages",
    "compare_blueprints",
    "compile_blueprint_from_module_ids",
    "compute_ast_delta",
    "cross_node_reference_errors",
    "designer_message_signature",
    "evaluate_runtime_drift",
    "extract_designer_orphan_groups",
    "extract_error_directives",
    "extract_forman_mapping_events",
    "extract_latency_observations",
    "extract_runtime_filter_conditions",
    "extract_runtime_notes",
    "extract_runtime_sample_observations",
    "infer_module_role",
    "inspect_blueprint_runtime_metadata",
    "iter_ast_execution_paths",
    "iter_ast_nodes",
    "iter_top_level_nodes",
    "make_blueprint_bundle_root",
    "module_looks_like_trigger",
    "module_looks_like_webhook_response",
    "note_binding_errors",
    "parse_make_ast",
    "parse_make_ast_json_text",
    "persist_make_blueprint_bundle",
    "plan_blueprint_layout",
    "require_ast_node",
    "require_module_resolution",
    "resolve_ast_modules",
    "rewrite_cross_node_references",
    "slugify_blueprint_name",
    "validate_make_blueprint_bundle_collection",
)
