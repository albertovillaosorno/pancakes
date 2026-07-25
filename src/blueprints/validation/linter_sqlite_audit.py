# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite audit matrix for Make linter code and data coverage.

Boundary contract:
- Owns: linter rule surface classification and linter data-source inventory
  projection into the Make knowledge SQLite SSOT.
- Must not: emit validation findings, promote linter candidates, author catalog
  semantic answers, call live services, or treat JSON/Markdown linter files as
  runtime authority.
- Allows: deterministic SQLite rows derived from taxonomy code and tracked
  product-safe linter evidence files.
- Split when: linter promotion decisions gain their own SQLite decision store.
- Merge when: the linter taxonomy owns this exact SQLite audit matrix.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from catalog.knowledge import (
    KNOWLEDGE_SCHEMA_VERSION,
    build_knowledge_store,
    connect_catalog_plan_ssot,
    knowledge_store_status,
)

from blueprints.validation.linter_taxonomy import (
    MakeLinterRuleFamily,
    make_linter_rule_families,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable, Mapping

    from catalog.knowledge import KnowledgeStoreStatusReport

type JsonObject = dict[str, object]
type LinterRuleSurface = Literal["code_only", "sqlite_only", "cross_surface"]

LINTER_DATA_ROOT: Final = Path("src/blueprints/validation/data/linter")
LINTER_AUDIT_SOURCE_OF_TRUTH: Final = "sqlite:linter_rule_surface_matrix"
LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH: Final = (
    "sqlite:linter_data_source_inventory"
)
LINTER_AUDIT_OBSERVED_AT_UTC: Final = "2026-05-18T00:00:00Z"
CODE_PREDICATE_SOURCES: Final[frozenset[str]] = frozenset(
    (
        "ast_structure ",
        "local_failure ",
        "promoted_golden_evidence ",
        "validation_fixture",
    )
)
SQLITE_PREDICATE_SOURCES: Final[frozenset[str]] = frozenset(
    (
        "catalog_truth ",
        "designer_message_api ",
        "knowledge_store",
    )
)
SQLITE_TABLES_BY_EVIDENCE_SOURCE: Final[dict[str, tuple[str, ...]]] = {
    "catalog_truth": (
        "apps ",
        "app_versions ",
        "modules ",
        "fields ",
        "constraints ",
        "module_aliases ",
        "catalog_search_documents",
    ),
    "designer_message_api": ("designer_message_evidence",),
    "knowledge_store": (
        "rule_facts ",
        "optimizer_hints ",
        "module_transaction_profiles ",
        "course_claims ",
        "claim_evidence ",
        "claim_conflicts ",
        "native_module_expectations ",
        "linter_quarantine_records",
    ),
}
REBUILDABLE_AUDIT_STATUSES: Final[frozenset[str]] = frozenset(
    ("empty_database", "missing_database", "stale_schema")
)
EXACT_LINTER_SOURCE_KINDS_BY_SUFFIX: Final[tuple[tuple[str, str], ...]] = (
    ("/quarantine/manifest.json", "sqlite_derived_quarantine_manifest"),
    ("/quarantine/review-coverage.json", "sqlite_derived_review_coverage"),
    (
        "/decisions/linter-candidate-decisions.json ",
        "legacy_candidate_decision_ledger",
    ),
)
MARKER_LINTER_SOURCE_KINDS: Final[tuple[tuple[str, str], ...]] = (
    ("/quarantine/mcp-review-decisions/", "sqlite_derived_review_event"),
    ("/completed-intake/", "completed_intake_evidence"),
    ("/designer-messages/", "reviewed_designer_evidence"),
    ("/probes/", "reviewed_designer_evidence"),
    ("/compliance/", "standards_research_evidence"),
    ("/corpus/", "linter_corpus_projection"),
)


class LinterRuleSurfaceMatrixRow(NamedTuple):
    """One linter rule-family runtime surface classification."""

    family_id: str
    rule_surface: LinterRuleSurface
    owner_path: str
    code_predicate_sources: tuple[str, ...]
    sqlite_predicate_sources: tuple[str, ...]
    source_tables: tuple[str, ...]
    source_files: tuple[str, ...]
    promoted_code_count: int
    output_affecting: bool
    fingerprint: str


class LinterDataSourceInventoryRow(NamedTuple):
    """One tracked linter data source represented in SQLite."""

    inventory_id: str
    source_path: str
    source_kind: str
    authority_state: str
    sqlite_table: str
    consumed_policy: str
    size_bytes: int
    fingerprint: str


class LinterSQLiteAuditReport(NamedTuple):
    """Summary for one linter audit SQLite synchronization."""

    database_path: str
    schema_version: int
    rule_matrix_count: int
    data_source_count: int
    code_only_count: int
    sqlite_only_count: int
    cross_surface_count: int
    source_of_truth: str


def linter_rule_surface_matrix() -> tuple[LinterRuleSurfaceMatrixRow, ...]:
    """Return the computed result for the caller."""
    return tuple(
        _matrix_row_for_family(family) for family in make_linter_rule_families()
    )


def linter_data_source_inventory(
    repo_root: Path,
) -> tuple[LinterDataSourceInventoryRow, ...]:
    """Return tracked linter data files as SQLite inventory rows."""
    data_root = (repo_root / LINTER_DATA_ROOT).resolve()
    if not data_root.is_dir():
        return ()
    rows: list[LinterDataSourceInventoryRow] = []
    for path in sorted(data_root.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in {".json", ".md"}:
            continue
        relative_path = _repo_relative_path(repo_root=repo_root, path=path)
        source_kind = _source_kind_for_linter_path(relative_path)
        authority_state = _authority_state_for_source_kind(source_kind)
        sqlite_table = _sqlite_table_for_source_kind(source_kind)
        consumed_policy = _consumed_policy_for_source_kind(source_kind)
        fingerprint = _file_fingerprint(path)
        rows.append(
            LinterDataSourceInventoryRow(
                inventory_id=_stable_id("linter-data-source", relative_path),
                source_path=relative_path,
                source_kind=source_kind,
                authority_state=authority_state,
                sqlite_table=sqlite_table,
                consumed_policy=consumed_policy,
                size_bytes=path.stat().st_size,
                fingerprint=fingerprint,
            )
        )
    return tuple(rows)


def sync_linter_sqlite_audit(repo_root: Path) -> LinterSQLiteAuditReport:
    """Project the linter rule matrix and data-source inventory into SQLite.

    Returns:
        Synchronization counts and SQLite source-of-truth evidence.
    """
    status = _ensure_linter_audit_database(repo_root)
    matrix_rows = linter_rule_surface_matrix()
    inventory_rows = linter_data_source_inventory(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            _ensure_linter_audit_tables_sql(connection)
            _replace_linter_rule_surface_matrix(connection, matrix_rows)
            _replace_linter_data_source_inventory(connection, inventory_rows)
            _ = connection.execute(
                "INSERT OR REPLACE INTO snapshot_metadata (key, value) VALUES "
                "(?, ?)",
                ("schema_version", str(KNOWLEDGE_SCHEMA_VERSION)),
            )
    finally:
        connection.close()
    counts = _surface_counts(matrix_rows)
    return LinterSQLiteAuditReport(
        database_path=status.database_path,
        schema_version=KNOWLEDGE_SCHEMA_VERSION,
        rule_matrix_count=len(matrix_rows),
        data_source_count=len(inventory_rows),
        code_only_count=counts["code_only"],
        sqlite_only_count=counts["sqlite_only"],
        cross_surface_count=counts["cross_surface"],
        source_of_truth=LINTER_AUDIT_SOURCE_OF_TRUTH,
    )


def _matrix_row_for_family(
    family: MakeLinterRuleFamily,
) -> LinterRuleSurfaceMatrixRow:
    evidence_sources = tuple(str(source) for source in family.evidence_sources)
    code_sources = tuple(
        source
        for source in evidence_sources
        if source in CODE_PREDICATE_SOURCES
    )
    sqlite_sources = tuple(
        source
        for source in evidence_sources
        if source in SQLITE_PREDICATE_SOURCES
    )
    source_tables = tuple(
        sorted(
            {
                table_name
                for source in sqlite_sources
                for table_name in SQLITE_TABLES_BY_EVIDENCE_SOURCE[source]
            }
        )
    )
    source_files = tuple(
        item
        for item in (family.owner_path, family.focused_test_path)
        if item and item.startswith(("src/", "tests/"))
    )
    payload: JsonObject = {
        "family_id": family.family_id,
        "rule_surface": _rule_surface(
            code_sources=code_sources, sqlite_sources=sqlite_sources
        ),
        "owner_path": family.owner_path,
        "code_predicate_sources": list(code_sources),
        "sqlite_predicate_sources": list(sqlite_sources),
        "source_tables": list(source_tables),
        "source_files": list(source_files),
        "promoted_code_count": len(family.supported_codes),
        "output_affecting": family.output_affecting,
    }
    return LinterRuleSurfaceMatrixRow(
        family_id=family.family_id,
        rule_surface=cast(
            "LinterRuleSurface",
            payload["rule_surface"],
        ),
        owner_path=family.owner_path,
        code_predicate_sources=code_sources,
        sqlite_predicate_sources=sqlite_sources,
        source_tables=source_tables,
        source_files=source_files,
        promoted_code_count=len(family.supported_codes),
        output_affecting=family.output_affecting,
        fingerprint=_fingerprint(payload),
    )


def _rule_surface(
    *,
    code_sources: tuple[str, ...],
    sqlite_sources: tuple[str, ...],
) -> LinterRuleSurface:
    if code_sources and sqlite_sources:
        return "cross_surface"
    if sqlite_sources:
        return "sqlite_only"
    return "code_only"


def _ensure_linter_audit_database(
    repo_root: Path,
) -> KnowledgeStoreStatusReport:
    status = knowledge_store_status(repo_root=repo_root)
    if status.status in REBUILDABLE_AUDIT_STATUSES:
        _ = build_knowledge_store(repo_root=repo_root)
        status = knowledge_store_status(repo_root=repo_root)
    if not status.database_available:
        message = (
            f"Make knowledge SQLite is unavailable for linter audit:"
            f"{status.status}"
        )
        raise ValueError(message)
    return status


def _ensure_linter_audit_tables_sql(connection: sqlite3.Connection) -> None:
    _ = connection.executescript(
        """
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

        CREATE INDEX IF NOT EXISTS idx_linter_rule_surface_matrix_surface
          ON linter_rule_surface_matrix (rule_surface, owner_path);

        CREATE INDEX IF NOT EXISTS idx_linter_data_source_inventory_authority
          ON linter_data_source_inventory (authority_state, sqlite_table);
        """
    )


def _replace_linter_rule_surface_matrix(
    connection: sqlite3.Connection,
    rows: Iterable[LinterRuleSurfaceMatrixRow],
) -> None:
    _ = connection.execute("DELETE FROM linter_rule_surface_matrix")
    for row in rows:
        _ = connection.execute(
            """
            INSERT INTO linter_rule_surface_matrix (
              family_id,
              rule_surface,
              owner_path,
              code_predicate_sources_json,
              sqlite_predicate_sources_json,
              source_tables_json,
              source_files_json,
              promoted_code_count,
              output_affecting,
              fingerprint,
              source_kind,
              source_ref,
              valid_from,
              valid_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                row.family_id,
                row.rule_surface,
                row.owner_path,
                _canonical_json_text(list(row.code_predicate_sources)),
                _canonical_json_text(list(row.sqlite_predicate_sources)),
                _canonical_json_text(list(row.source_tables)),
                _canonical_json_text(list(row.source_files)),
                row.promoted_code_count,
                int(row.output_affecting),
                row.fingerprint,
                "linter_taxonomy ",
                "src/blueprints/validation/linter_taxonomy.py",
                LINTER_AUDIT_OBSERVED_AT_UTC,
            ),
        )


def _replace_linter_data_source_inventory(
    connection: sqlite3.Connection,
    rows: Iterable[LinterDataSourceInventoryRow],
) -> None:
    _ = connection.execute("DELETE FROM linter_data_source_inventory")
    for row in rows:
        _ = connection.execute(
            """
            INSERT INTO linter_data_source_inventory (
              inventory_id,
              source_path,
              source_kind,
              authority_state,
              sqlite_table,
              consumed_policy,
              source_of_truth,
              size_bytes,
              fingerprint,
              valid_from,
              valid_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                row.inventory_id,
                row.source_path,
                row.source_kind,
                row.authority_state,
                row.sqlite_table,
                row.consumed_policy,
                LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
                row.size_bytes,
                row.fingerprint,
                LINTER_AUDIT_OBSERVED_AT_UTC,
            ),
        )


def _source_kind_for_linter_path(relative_path: str) -> str:
    path = relative_path.replace("\\", "/")
    if path.endswith("/README.md"):
        return "readme_sentinel"
    for suffix, source_kind in EXACT_LINTER_SOURCE_KINDS_BY_SUFFIX:
        if path.endswith(suffix):
            return source_kind
    for marker, source_kind in MARKER_LINTER_SOURCE_KINDS:
        if marker in path:
            return source_kind
    if "/quarantine/" in path and path.endswith(".md"):
        return "legacy_quarantine_record"
    return "tracked_linter_evidence"


def _authority_state_for_source_kind(source_kind: str) -> str:
    if source_kind.startswith("sqlite_derived_"):
        return "sqlite_derived_snapshot"
    if source_kind.startswith("legacy_"):
        return "legacy_evidence_pending_sqlite_migration"
    if source_kind == "readme_sentinel":
        return "documentation_sentinel"
    return "deterministic_fixture_or_source"


def _sqlite_table_for_source_kind(source_kind: str) -> str:
    if source_kind in {
        "sqlite_derived_quarantine_manifest ",
        "sqlite_derived_review_coverage ",
        "legacy_candidate_decision_ledger ",
        "legacy_quarantine_record ",
        "completed_intake_evidence",
    }:
        return "linter_quarantine_records"
    if source_kind == "sqlite_derived_review_event":
        return "linter_quarantine_review_events"
    if source_kind == "reviewed_designer_evidence":
        return "designer_message_evidence"
    if source_kind == "standards_research_evidence":
        return "claim_evidence"
    if source_kind == "linter_corpus_projection":
        return "rule_facts"
    return ""


def _consumed_policy_for_source_kind(source_kind: str) -> str:
    if source_kind.startswith("sqlite_derived_"):
        return "Regenerate from SQLite; do not edit as authority."
    if source_kind == "legacy_quarantine_record":
        return (
            "Keep as legacy review evidence until candidate promotion, "
            "rejection, or aliasing "
            "preserves the source ID in SQLite."
        )
    if source_kind == "legacy_candidate_decision_ledger":
        return (
            "Use only as migration input; reviewed quarantine state belongs in "
            "SQLite after "
            "the import path consumes it."
        )
    if source_kind == "readme_sentinel":
        return "Documentation only; persistent linter state belongs in SQLite."
    return (
        "Represent the file fingerprint and derived facts in SQLite before "
        "runtime use."
    )


def _surface_counts(
    rows: tuple[LinterRuleSurfaceMatrixRow, ...],
) -> dict[str, int]:
    counts = {"code_only": 0, "sqlite_only": 0, "cross_surface": 0}
    for row in rows:
        counts[row.rule_surface] += 1
    return counts


def _repo_relative_path(*, repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _fingerprint(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json_text(payload).encode("utf-8")
    ).hexdigest()


def _canonical_json_text(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
