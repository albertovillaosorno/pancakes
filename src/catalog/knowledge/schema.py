# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001064#repo.make-knowledge.temporal-facts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Editable schema authority for the Pancakes engine SQLite database.

Boundary contract:
- Owns: engine schema table groups and the authoritative bootstrap SQL.
- Must not: create workflow ledgers, contact providers, or ingest live Make.
- Allows: deterministic source truth, graph projections, and semantic tables.
- Split when: generated projection snapshots gain their own schema exporter.
- Merge when: another module defines the same engine schema table contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

ENGINE_SCHEMA_SQL_PATH: Final[Path] = Path(__file__).with_name("schema.sql")

CORE_METADATA_TABLES: Final[tuple[str, ...]] = (
    "snapshot_metadata",
    "ingest_runs",
)
SOURCE_LEDGER_TABLES: Final[tuple[str, ...]] = (
    "source_documents",
    "make_raw_spec_payloads",
    "make_raw_spec_manifest_records",
    "make_raw_spec_update_reviews",
    "linter_source_artifacts",
    "assisted_delivery_artifacts",
)
GRAPH_PROJECTION_TABLES: Final[tuple[str, ...]] = (
    "entity_nodes",
    "entity_edges",
)
TEMPORAL_TABLES: Final[tuple[str, ...]] = (
    "apps",
    "app_versions",
    "modules",
    "fields",
    "constraints",
    "module_aliases",
    "rule_facts",
    "optimizer_hints",
    "module_transaction_profiles",
    "course_claims",
    "claim_evidence",
    "claim_conflicts",
    "designer_message_evidence",
    "native_module_expectations",
)
CATALOG_PLAN_SSOT_TABLES: Final[tuple[str, ...]] = (
    "catalog_plan_metadata",
    "catalog_plan_ranges",
    "catalog_plan_units",
    "catalog_plan_progress_events",
    "catalog_plan_semantic_answers",
    "catalog_plan_quarantine_records",
    "catalog_search_documents",
    "make_datastore_structure_evidence",
    "make_webhook_structure_evidence",
    "make_scraped_datastore_evidence",
    "make_scraped_webhook_evidence",
    "make_scraped_structure_evidence",
    "make_scraped_connection_evidence",
    "make_scraped_scope_evidence",
    "make_scraped_import_export_evidence",
)
CATALOG_RESET_TABLES: Final[tuple[str, ...]] = (
    "catalog_runs",
    "catalog_units",
    "catalog_unit_notes",
    "catalog_unit_outputs",
    "catalog_module_intelligence_metadata",
    "catalog_modification_events",
    "catalog_edge_proposals",
    "catalog_review_records",
    "catalog_legacy_semantic_archives",
)
LINTER_TECHNICAL_TABLES: Final[tuple[str, ...]] = (
    "linter_rule_surface_matrix",
    "linter_data_source_inventory",
)
RUNTIME_EXTENSION_TABLES: Final[tuple[str, ...]] = (
    "mcp_backlog_entries",
    "local_project_metadata",
    "linter_quarantine_records",
    "linter_quarantine_review_events",
)
PURE_SEMANTIC_TABLES: Final[tuple[str, ...]] = (
    "catalog_runs",
    "catalog_units",
    "catalog_unit_notes",
    "catalog_unit_outputs",
    "catalog_plan_semantic_answers",
    "catalog_search_documents",
)
ENGINE_SCHEMA_TABLES: Final[tuple[str, ...]] = (
    *CORE_METADATA_TABLES,
    "source_documents",
    *GRAPH_PROJECTION_TABLES,
    "make_raw_spec_payloads",
    "make_raw_spec_manifest_records",
    "make_raw_spec_update_reviews",
    "linter_source_artifacts",
    "assisted_delivery_artifacts",
    *TEMPORAL_TABLES,
    *CATALOG_PLAN_SSOT_TABLES,
    *CATALOG_RESET_TABLES,
    *LINTER_TECHNICAL_TABLES,
)
DUMP_TABLES: Final[tuple[str, ...]] = ENGINE_SCHEMA_TABLES
REQUIRED_SCHEMA_TABLES: Final[frozenset[str]] = frozenset(ENGINE_SCHEMA_TABLES)


def read_engine_schema_sql() -> str:
    """Return the authoritative engine schema SQL."""
    return ENGINE_SCHEMA_SQL_PATH.read_text(encoding="utf-8")
