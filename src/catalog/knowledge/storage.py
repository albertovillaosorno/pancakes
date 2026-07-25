# ruff: noqa: E501, PLR0913, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-specs.persistent-data-output
# - 001064#repo.make-knowledge.structural-ssot
# - 001064#repo.make-knowledge.temporal-facts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false, reportUnusedCallResult=false,

"""Build, dump, status, and query behavior for the Make knowledge SQLite store.

Boundary contract:
- Owns: repository-confined SQLite materialization from tracked SQL and raw
specs.
- Must not: contact live Make services, validate blueprints, or own service
loops.
- Allows: deterministic SQL snapshot loading, raw-spec normalization, and
queries.
- Split when: live refresh orchestration or blueprint validation logic appears
here.
- Merge when: another module rebuilds the same knowledge-store artifact.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.manifest import (
    canonical_json_bytes,
    load_raw_spec_manifest,
)
from languages.make.raw_specs.parser import parse_make_raw_spec
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_MANIFEST,
    relative_to_repo,
    resolve_repo_relative_path,
)
from languages.make.raw_specs.sqlite_store import (
    RawSpecSqliteBundle,
    is_sqlite_raw_spec_ref,
    load_sqlite_raw_spec_bundle,
    load_sqlite_raw_spec_payload,
    persist_sqlite_raw_spec_bundle,
)

from catalog.compiler import MODULE_COLLECTIONS
from catalog.field_collections import FIELD_COLLECTIONS
from catalog.identifiers import constraint_id, field_id, module_id
from catalog.json_payloads import normalize_json_object, payload_fingerprint
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
from catalog.knowledge.schema import (
    CATALOG_PLAN_SSOT_TABLES,
    CATALOG_RESET_TABLES,
    DUMP_TABLES,
    GRAPH_PROJECTION_TABLES,
    LINTER_TECHNICAL_TABLES,
    REQUIRED_SCHEMA_TABLES,
    RUNTIME_EXTENSION_TABLES,
    SOURCE_LEDGER_TABLES,
    read_engine_schema_sql,
)
from catalog.models import (
    CatalogFieldDirection,
    CatalogModuleKind,
    CatalogRawSpecDiagnostic,
    CatalogRawSpecDiagnosticCode,
)
from catalog.value_index import canonicalize_catalog_field_type

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from languages.make.raw_specs.models import RawSpecManifest, RawSpecRecord

    from catalog.models import JsonObject

FIELD_CONSTRAINT_KEYS: Final[frozenset[str]] = frozenset(
    (
        "advanced",
        "default",
        "editable",
        "enum",
        "forceReload",
        "grouped",
        "help",
        "labels",
        "mappable",
        "max",
        "maxItems",
        "maxLength",
        "min",
        "minItems",
        "minLength",
        "multiple",
        "options",
        "pattern",
        "placeholder",
        "required",
        "scope",
        "semantic",
        "type",
    )
)
NESTED_FIELD_KEYS: Final[frozenset[str]] = frozenset(
    ("fields", "schema", "spec")
)
GENERATED_SQL_SNAPSHOT_NAMES: Final[frozenset[str]] = frozenset(("make.sql",))
PROJECTION_SQL_SNAPSHOT_NAMES: Final[frozenset[str]] = frozenset(
    ("schema.sql",)
)
GENERATED_SQL_SNAPSHOT_SUFFIXES: Final[tuple[str, ...]] = (
    ".dump.sql",
    ".full.sql",
    ".backup.sql",
    ".generated.sql",
)
LIGHTWEIGHT_QUERY_FINGERPRINT_TABLES: Final[tuple[str, ...]] = (
    "snapshot_metadata",
    "module_aliases",
    "rule_facts",
    "optimizer_hints",
    "module_transaction_profiles",
    "course_claims",
    "claim_evidence",
    "claim_conflicts",
    "designer_message_evidence",
)
SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = 2_147_483_647
SQLITE_BUSY_TIMEOUT_SECONDS: Final = SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
MIN_DISTINCT_CLAIM_VALUES_FOR_CONFLICT: Final = 2
KNOWLEDGE_STATUS_DB_ENSURE_COMMAND: Final = (
    "python -B -m catalog.knowledge ensure"
)
KNOWLEDGE_STATUS_RECOMMENDED_COMMANDS: Final[tuple[str, ...]] = (
    KNOWLEDGE_STATUS_DB_ENSURE_COMMAND,
)
KNOWLEDGE_REBUILD_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "empty_database",
        "missing_database",
        "stale_schema",
        "stale_manifest",
    )
)
KNOWLEDGE_MODULE_SEARCH_MIN_TERM_LENGTH: Final = 2
KNOWLEDGE_MODULE_SEARCH_TRUNCATION_REASON: Final = (
    "knowledge_module_search_limit_applied"
)
MIN_PROVIDER_TERM_SCORE_FOR_SEARCH_NARROWING: Final = 2
SQL_PARAMETER_CHUNK_SIZE: Final = 500
RAW_SPEC_REBUILT_SOURCE_TABLES: Final[frozenset[str]] = frozenset(
    (
        "make_raw_spec_manifest_records",
        "make_raw_spec_payloads",
    )
)
RAW_SPEC_INGEST_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    (
        "raw_spec_manifest",
        "raw_spec_sqlite_manifest",
    )
)
PRESERVED_CORE_METADATA_TABLES: Final[tuple[str, ...]] = ("ingest_runs",)
PRESERVED_SOURCE_LEDGER_TABLES: Final[tuple[str, ...]] = tuple(
    table
    for table in SOURCE_LEDGER_TABLES
    if table not in RAW_SPEC_REBUILT_SOURCE_TABLES
)
PRESERVED_LOCAL_STATE_TABLES: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *PRESERVED_CORE_METADATA_TABLES,
            *PRESERVED_SOURCE_LEDGER_TABLES,
            *GRAPH_PROJECTION_TABLES,
            *CATALOG_PLAN_SSOT_TABLES,
            *CATALOG_RESET_TABLES,
            *LINTER_TECHNICAL_TABLES,
            *RUNTIME_EXTENSION_TABLES,
        )
    )
)
LOSS_PROTECTED_LOCAL_STATE_TABLES: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *GRAPH_PROJECTION_TABLES,
            *CATALOG_PLAN_SSOT_TABLES,
            *CATALOG_RESET_TABLES,
            *RUNTIME_EXTENSION_TABLES,
        )
    )
)
KNOWLEDGE_DATABASE_VALIDATION_CACHE_LOCK = Lock()
KNOWLEDGE_DATABASE_VALIDATION_CACHE: dict[tuple[object, ...], Path] = {}


class ClaimEvidenceRow(NamedTuple):
    """One current claim-evidence row used for deterministic arbitration."""

    evidence_id: str
    claim_key: str
    domain: str
    value_json: str
    source_confidence: int
    evidence_observed_at: str
    source_kind: str
    source_ref: str
    valid_from: str
    adr_anchor: str


class RawFieldDiagnosticContext(NamedTuple):
    """Shared context for quarantined knowledge-store field metadata."""

    diagnostics: list[CatalogRawSpecDiagnostic]
    durable_module_id: str
    record: RawSpecRecord
    module_kind: CatalogModuleKind
    internal_name: str


class RawFieldIssue(NamedTuple):
    """One malformed raw field metadata issue found during DB ingestion."""

    code: CatalogRawSpecDiagnosticCode
    field_path: tuple[str, ...]
    collection_path: tuple[str | int, ...]
    message: str


class RawFieldPayload(NamedTuple):
    """One normalized raw field payload and its source location."""

    direction: CatalogFieldDirection
    payload: JsonObject
    path: tuple[str, ...]
    collection_path: tuple[str | int, ...]


RawSpecSeenKeys = dict[str, set[tuple[object, ...]]]
RawSpecTargetKeys = set[tuple[str, str]]


class StaleRawSpecChildRowsRequest(NamedTuple):
    """Inputs for closing stale raw-spec child rows in one table."""

    connection: sqlite3.Connection
    table: str
    key_column: str
    seen_keys: set[tuple[object, ...]]
    target_keys: RawSpecTargetKeys
    valid_to: str


def build_knowledge_store(
    *,
    repo_root: Path,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
    snapshot_dir: Path = DEFAULT_DB_SNAPSHOT_DIR,
    raw_spec_manifest_path: Path = DEFAULT_RAW_SPEC_MANIFEST,
) -> KnowledgeStoreBuildReport:
    """Rebuild the generated Make knowledge SQLite database.

    Returns:
        The build report for the rebuilt local database.
    """
    resolved_database = resolve_repo_relative_path(repo_root, database_path)
    resolved_snapshot_dir = resolve_repo_relative_path(repo_root, snapshot_dir)
    resolved_manifest_path = resolve_repo_relative_path(
        repo_root, raw_spec_manifest_path
    )
    resolved_database.parent.mkdir(parents=True, exist_ok=True)
    build_database = _build_database_path(resolved_database)
    if build_database.exists():
        build_database.unlink()

    connection = _connect_database(build_database)
    build_succeeded = False
    report: KnowledgeStoreBuildReport | None = None
    diagnostics: list[CatalogRawSpecDiagnostic] = []
    try:
        sql_snapshot_count = _execute_sql_snapshots(
            connection, resolved_snapshot_dir
        )
        raw_spec_bundle = _load_raw_spec_bundle_if_available(
            repo_root=repo_root,
            database_path=resolved_database,
            manifest_path=resolved_manifest_path,
        )
        manifest = None if raw_spec_bundle is None else raw_spec_bundle.manifest
        if raw_spec_bundle is not None:
            persist_sqlite_raw_spec_bundle(
                connection=connection, bundle=raw_spec_bundle
            )
            _ingest_raw_spec_manifest(
                connection=connection,
                repo_root=repo_root,
                manifest=raw_spec_bundle.manifest,
                payloads_by_ref=raw_spec_bundle.payloads_by_ref,
                diagnostics=diagnostics,
            )
        _materialize_claim_conflicts(connection)
        _preserve_local_state_tables(
            connection=connection,
            source_database=resolved_database,
        )
        connection.commit()
        status = _status_from_connection(
            connection=connection,
            repo_root=repo_root,
            database_path=resolved_database,
            raw_spec_manifest_path=resolved_manifest_path,
            manifest=manifest,
        )
        report = KnowledgeStoreBuildReport(
            database_path=relative_to_repo(repo_root, resolved_database),
            snapshot_dir=relative_to_repo(repo_root, resolved_snapshot_dir),
            schema_version=KNOWLEDGE_SCHEMA_VERSION,
            sql_snapshot_count=sql_snapshot_count,
            raw_spec_manifest_path=relative_to_repo(
                repo_root, resolved_manifest_path
            ),
            raw_spec_manifest_available=manifest is not None,
            raw_spec_manifest_sha256=None
            if manifest is None
            else manifest.manifest_sha256,
            raw_spec_record_count=0
            if manifest is None
            else len(manifest.records),
            app_count=status.app_count,
            app_version_count=status.app_version_count,
            module_count=status.module_count,
            field_count=_current_count(connection, "fields"),
            constraint_count=_current_count(connection, "constraints"),
            alias_count=_current_count(connection, "module_aliases"),
            rule_count=_current_count(connection, "rule_facts"),
            optimizer_hint_count=_current_count(connection, "optimizer_hints"),
            transaction_profile_count=_current_count(
                connection,
                "module_transaction_profiles",
            ),
            course_claim_count=_current_count(connection, "course_claims"),
            claim_evidence_count=_current_count(connection, "claim_evidence"),
            claim_conflict_count=_current_count(connection, "claim_conflicts"),
            native_expectation_count=_current_count(
                connection, "native_module_expectations"
            ),
            native_gap_count=len(status.native_module_gaps),
            raw_spec_diagnostics=tuple(
                sorted(diagnostics, key=_diagnostic_sort_key)
            ),
            fingerprint=status.fingerprint or _database_fingerprint(connection),
        )
        build_succeeded = True
    finally:
        connection.close()
        if build_succeeded:
            build_database.replace(resolved_database)
        elif build_database.exists():
            build_database.unlink()
    return report


def dump_knowledge_store(
    *,
    repo_root: Path,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
    output_path: Path = DEFAULT_GENERATED_FACTS_PATH,
) -> KnowledgeStoreDumpReport:
    """Dump current SQLite facts into a deterministic service-regenerable SQL.

    file.

    Returns:
        The deterministic dump report.

    Raises:
        FileNotFoundError: If the generated SQLite database is missing.
    """
    resolved_database = resolve_repo_relative_path(repo_root, database_path)
    resolved_output = resolve_repo_relative_path(repo_root, output_path)
    if not resolved_database.is_file():
        message = f"Knowledge database is missing: {resolved_database}"
        raise FileNotFoundError(message)

    connection = _connect_database(resolved_database)
    try:
        lines: list[str] = [
            "-- Generated Make knowledge facts. Review before committing.",
            "BEGIN TRANSACTION;",
        ]
        row_count = 0
        for table in DUMP_TABLES:
            columns = _table_columns(connection, table)
            rows = _dump_rows(connection, table, columns)
            for row in rows:
                row_count += 1
                lines.append(_insert_sql(table=table, columns=columns, row=row))
        lines.extend(("COMMIT;", ""))
        payload = "\n".join(lines)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload, encoding="utf-8")
        return KnowledgeStoreDumpReport(
            database_path=relative_to_repo(repo_root, resolved_database),
            output_path=relative_to_repo(repo_root, resolved_output),
            table_count=len(DUMP_TABLES),
            row_count=row_count,
            fingerprint=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )
    finally:
        connection.close()


def knowledge_store_status(
    *,
    repo_root: Path,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
    raw_spec_manifest_path: Path = DEFAULT_RAW_SPEC_MANIFEST,
) -> KnowledgeStoreStatusReport:
    """Return current Make knowledge database status without mutating files.

    Returns:
        The current status report.
    """
    resolved_database = resolve_repo_relative_path(repo_root, database_path)
    resolved_manifest_path = resolve_repo_relative_path(
        repo_root, raw_spec_manifest_path
    )
    try:
        raw_spec_bundle = _load_raw_spec_bundle_if_available(
            repo_root=repo_root,
            database_path=resolved_database,
            manifest_path=resolved_manifest_path,
        )
        manifest = None if raw_spec_bundle is None else raw_spec_bundle.manifest
    except (OSError, TypeError, ValueError):
        return _invalid_manifest_status(
            repo_root=repo_root,
            database_path=resolved_database,
            raw_spec_manifest_path=resolved_manifest_path,
        )
    if not resolved_database.is_file():
        status_label = "missing_database"
        return KnowledgeStoreStatusReport(
            status=status_label,
            database_path=relative_to_repo(repo_root, resolved_database),
            database_available=False,
            schema_version=None,
            raw_spec_manifest_path=relative_to_repo(
                repo_root, resolved_manifest_path
            ),
            missing_paths=_knowledge_status_missing_paths(
                repo_root=repo_root,
                database_path=resolved_database,
                raw_spec_manifest_path=resolved_manifest_path,
            ),
            recommended_commands=_knowledge_status_recommended_commands(
                status_label
            ),
            raw_spec_manifest_available=manifest is not None,
            raw_spec_manifest_generated_at_utc=(
                None if manifest is None else manifest.generated_at_utc
            ),
            raw_spec_manifest_sha256=None
            if manifest is None
            else manifest.manifest_sha256,
            database_raw_spec_manifest_generated_at_utc=None,
            database_raw_spec_manifest_sha256=None,
            raw_spec_manifest_matches_database=None,
            raw_spec_record_count=0
            if manifest is None
            else len(manifest.records),
            app_count=0,
            app_version_count=0,
            module_count=0,
            alias_count=0,
            rule_count=0,
            optimizer_hint_count=0,
            transaction_profile_count=0,
            course_claim_count=0,
            claim_evidence_count=0,
            claim_conflict_count=0,
            native_expectation_count=0,
            native_module_gaps=(),
            fingerprint=None,
        )

    connection = _connect_database(resolved_database)
    try:
        if not _knowledge_schema_exists(connection):
            return _empty_database_status(
                repo_root=repo_root,
                database_path=resolved_database,
                raw_spec_manifest_path=resolved_manifest_path,
                manifest=manifest,
            )
        missing_schema_tables = _missing_required_knowledge_tables(connection)
        if missing_schema_tables:
            return _stale_schema_status(
                repo_root=repo_root,
                database_path=resolved_database,
                raw_spec_manifest_path=resolved_manifest_path,
                manifest=manifest,
                schema_version=_schema_version(connection),
            )
        return _status_from_connection(
            connection=connection,
            repo_root=repo_root,
            database_path=resolved_database,
            raw_spec_manifest_path=resolved_manifest_path,
            manifest=manifest,
        )
    finally:
        connection.close()


def _invalid_manifest_status(
    *,
    repo_root: Path,
    database_path: Path,
    raw_spec_manifest_path: Path,
) -> KnowledgeStoreStatusReport:
    """Return a status report for a present but unreadable raw-spec manifest."""
    if not database_path.is_file():
        status_label = "invalid_manifest"
        return KnowledgeStoreStatusReport(
            status=status_label,
            database_path=relative_to_repo(repo_root, database_path),
            database_available=False,
            schema_version=None,
            raw_spec_manifest_path=relative_to_repo(
                repo_root, raw_spec_manifest_path
            ),
            missing_paths=_knowledge_status_missing_paths(
                repo_root=repo_root,
                database_path=database_path,
                raw_spec_manifest_path=raw_spec_manifest_path,
            ),
            recommended_commands=_knowledge_status_recommended_commands(
                status_label
            ),
            raw_spec_manifest_available=True,
            raw_spec_manifest_generated_at_utc=None,
            raw_spec_manifest_sha256=None,
            database_raw_spec_manifest_generated_at_utc=None,
            database_raw_spec_manifest_sha256=None,
            raw_spec_manifest_matches_database=None,
            raw_spec_record_count=0,
            app_count=0,
            app_version_count=0,
            module_count=0,
            alias_count=0,
            rule_count=0,
            optimizer_hint_count=0,
            transaction_profile_count=0,
            course_claim_count=0,
            claim_evidence_count=0,
            claim_conflict_count=0,
            native_expectation_count=0,
            native_module_gaps=(),
            fingerprint=None,
        )

    connection = _connect_database(database_path)
    try:
        if not _knowledge_schema_exists(connection):
            return _empty_database_status(
                repo_root=repo_root,
                database_path=database_path,
                raw_spec_manifest_path=raw_spec_manifest_path,
                manifest=None,
            )._replace(
                status="invalid_manifest",
                raw_spec_manifest_available=True,
            )
        missing_schema_tables = _missing_required_knowledge_tables(connection)
        if missing_schema_tables:
            return _stale_schema_status(
                repo_root=repo_root,
                database_path=database_path,
                raw_spec_manifest_path=raw_spec_manifest_path,
                manifest=None,
                schema_version=_schema_version(connection),
            )._replace(
                status="invalid_manifest",
                raw_spec_manifest_available=True,
            )
        status = _status_from_connection(
            connection=connection,
            repo_root=repo_root,
            database_path=database_path,
            raw_spec_manifest_path=raw_spec_manifest_path,
            manifest=None,
        )
    finally:
        connection.close()
    return status._replace(
        status="invalid_manifest",
        raw_spec_manifest_available=True,
        recommended_commands=_knowledge_status_recommended_commands(
            "invalid_manifest"
        ),
    )


def _empty_database_status(
    *,
    repo_root: Path,
    database_path: Path,
    raw_spec_manifest_path: Path,
    manifest: RawSpecManifest | None,
) -> KnowledgeStoreStatusReport:
    """Return status for a SQLite file that has no knowledge-store schema."""
    status_label = "empty_database"
    return KnowledgeStoreStatusReport(
        status=status_label,
        database_path=relative_to_repo(repo_root, database_path),
        database_available=True,
        schema_version=None,
        raw_spec_manifest_path=relative_to_repo(
            repo_root, raw_spec_manifest_path
        ),
        missing_paths=_knowledge_status_missing_paths(
            repo_root=repo_root,
            database_path=database_path,
            raw_spec_manifest_path=raw_spec_manifest_path,
        ),
        recommended_commands=_knowledge_status_recommended_commands(
            status_label
        ),
        raw_spec_manifest_available=manifest is not None,
        raw_spec_manifest_generated_at_utc=None
        if manifest is None
        else manifest.generated_at_utc,
        raw_spec_manifest_sha256=None
        if manifest is None
        else manifest.manifest_sha256,
        database_raw_spec_manifest_generated_at_utc=None,
        database_raw_spec_manifest_sha256=None,
        raw_spec_manifest_matches_database=None,
        raw_spec_record_count=0 if manifest is None else len(manifest.records),
        app_count=0,
        app_version_count=0,
        module_count=0,
        alias_count=0,
        rule_count=0,
        optimizer_hint_count=0,
        transaction_profile_count=0,
        course_claim_count=0,
        claim_evidence_count=0,
        claim_conflict_count=0,
        native_expectation_count=0,
        native_module_gaps=(),
        fingerprint=None,
    )


def _stale_schema_status(
    *,
    repo_root: Path,
    database_path: Path,
    raw_spec_manifest_path: Path,
    manifest: RawSpecManifest | None,
    schema_version: int | None,
) -> KnowledgeStoreStatusReport:
    """Return status for a SQLite file that predates the current schema."""
    status_label = "stale_schema"
    return KnowledgeStoreStatusReport(
        status=status_label,
        database_path=relative_to_repo(repo_root, database_path),
        database_available=True,
        schema_version=schema_version,
        raw_spec_manifest_path=relative_to_repo(
            repo_root, raw_spec_manifest_path
        ),
        missing_paths=_knowledge_status_missing_paths(
            repo_root=repo_root,
            database_path=database_path,
            raw_spec_manifest_path=raw_spec_manifest_path,
        ),
        recommended_commands=_knowledge_status_recommended_commands(
            status_label
        ),
        raw_spec_manifest_available=manifest is not None,
        raw_spec_manifest_generated_at_utc=None
        if manifest is None
        else manifest.generated_at_utc,
        raw_spec_manifest_sha256=None
        if manifest is None
        else manifest.manifest_sha256,
        database_raw_spec_manifest_generated_at_utc=None,
        database_raw_spec_manifest_sha256=None,
        raw_spec_manifest_matches_database=None,
        raw_spec_record_count=0 if manifest is None else len(manifest.records),
        app_count=0,
        app_version_count=0,
        module_count=0,
        alias_count=0,
        rule_count=0,
        optimizer_hint_count=0,
        transaction_profile_count=0,
        course_claim_count=0,
        claim_evidence_count=0,
        claim_conflict_count=0,
        native_expectation_count=0,
        native_module_gaps=(),
        fingerprint=None,
    )


def _knowledge_status_missing_paths(
    *,
    repo_root: Path,
    database_path: Path,
    raw_spec_manifest_path: Path,
) -> tuple[str, ...]:
    """Return missing local asset paths needed for a useful status payload."""
    paths: list[str] = []
    if not database_path.is_file():
        paths.append(relative_to_repo(repo_root, database_path))
    if not raw_spec_manifest_path.is_file():
        try:
            sqlite_bundle_available = (
                database_path.is_file()
                and load_sqlite_raw_spec_bundle(database_path=database_path)
                is not None
            )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            sqlite_bundle_available = False
        if not sqlite_bundle_available:
            paths.append(relative_to_repo(repo_root, raw_spec_manifest_path))
    return tuple(paths)


def _missing_required_knowledge_tables(
    connection: sqlite3.Connection,
) -> tuple[str, ...]:
    """Return required schema tables missing from an existing SQLite file."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tables = frozenset(str(row[0]) for row in rows)
    return tuple(sorted(REQUIRED_SCHEMA_TABLES - tables))


def _knowledge_status_recommended_commands(status: str) -> tuple[str, ...]:
    """Return deterministic local recovery commands for states that need.

    rebuilds.
    """
    if status in KNOWLEDGE_REBUILD_STATUSES or status == "invalid_manifest":
        return KNOWLEDGE_STATUS_RECOMMENDED_COMMANDS
    return ()


def load_knowledge_store_query(
    *,
    repo_root: Path,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
    include_structural_facts: bool = False,
) -> KnowledgeStoreQuery:
    """Load current facts needed by validators and optimization advisors.

    Returns:
        The query projection for current knowledge-store rows.
    """
    resolved_database = _validated_knowledge_database_path(
        repo_root=repo_root,
        database_path=database_path,
    )
    connection = _connect_database(resolved_database)
    try:
        return KnowledgeStoreQuery(
            fingerprint=_query_fingerprint(
                connection=connection,
                include_structural_facts=include_structural_facts,
            ),
            aliases=_load_aliases(connection),
            rule_facts=_load_rule_facts(connection),
            optimizer_hints=_load_optimizer_hints(connection),
            transaction_profiles=_load_transaction_profiles(connection),
            claim_conflicts=_load_claim_conflicts(connection),
            designer_messages=_load_designer_message_evidence(connection),
            modules=_load_modules(connection)
            if include_structural_facts
            else (),
            fields=_load_fields(connection) if include_structural_facts else (),
            constraints=_load_constraints(connection)
            if include_structural_facts
            else (),
            native_expectations=(
                _load_native_expectations(connection)
                if include_structural_facts
                else ()
            ),
        )
    finally:
        connection.close()


def search_knowledge_module_ids(
    *,
    repo_root: Path,
    terms: Sequence[str],
    limit: int,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
) -> KnowledgeModuleSearchReport:
    """Return bounded current module IDs matching module or field search terms.

    Returns:
        The matching module IDs and bounded truncation metadata.

    Raises:
        ValueError: If the requested search limit is not positive.
    """
    if limit < 1:
        message = "Knowledge module search limit must be positive."
        raise ValueError(message)
    search_terms = _knowledge_module_search_terms(terms)
    if not search_terms:
        return KnowledgeModuleSearchReport(
            module_ids=(),
            returned_count=0,
            total_candidate_count=0,
            effective_limit=limit,
            truncated=False,
            truncation_reason=None,
        )

    resolved_database = _validated_knowledge_database_path(
        repo_root=repo_root,
        database_path=database_path,
    )
    connection = _connect_database(resolved_database)
    try:
        module_hits = _search_current_modules_by_terms(
            connection=connection,
            terms=search_terms,
            limit=limit,
        )
        if len(module_hits) > limit:
            module_ids = _sorted_current_module_ids(
                connection, module_hits[:limit]
            )
            return KnowledgeModuleSearchReport(
                module_ids=module_ids,
                returned_count=len(module_ids),
                total_candidate_count=len(module_hits),
                effective_limit=limit,
                truncated=True,
                truncation_reason=KNOWLEDGE_MODULE_SEARCH_TRUNCATION_REASON,
            )
        field_hits = (
            ()
            if module_hits
            else _search_current_field_modules_by_terms(
                connection=connection,
                terms=search_terms,
                limit=limit,
            )
        )
        combined_hits = _dedupe_values((*module_hits, *field_hits))
        truncated = len(combined_hits) > limit
        bounded_hits = combined_hits[:limit]
        module_ids = _sorted_current_module_ids(connection, bounded_hits)
        return KnowledgeModuleSearchReport(
            module_ids=module_ids,
            returned_count=len(module_ids),
            total_candidate_count=len(combined_hits),
            effective_limit=limit,
            truncated=truncated,
            truncation_reason=KNOWLEDGE_MODULE_SEARCH_TRUNCATION_REASON
            if truncated
            else None,
        )
    finally:
        connection.close()


def load_knowledge_store_query_for_module_ids(
    *,
    repo_root: Path,
    module_ids: Sequence[str],
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
) -> KnowledgeStoreQuery:
    """Load current facts for a bounded module slice without hydrating all.

    structure.

    Returns:
    A knowledge-store query projection containing selected modules and child
    facts.
    """
    requested_module_ids = _dedupe_values(tuple(module_ids))
    resolved_database = _validated_knowledge_database_path(
        repo_root=repo_root,
        database_path=database_path,
    )
    connection = _connect_database(resolved_database)
    try:
        modules = _load_modules_for_ids(connection, requested_module_ids)
        selected_module_ids = tuple(module.module_id for module in modules)
        fields = _load_fields_for_module_ids(connection, selected_module_ids)
        constraints = _load_constraints_for_field_ids(
            connection,
            tuple(field.field_id for field in fields),
        )
        return KnowledgeStoreQuery(
            fingerprint=_selected_structural_fingerprint(
                modules=modules,
                fields=fields,
                constraints=constraints,
            ),
            aliases=_load_aliases(connection),
            rule_facts=_load_rule_facts(connection),
            optimizer_hints=_load_optimizer_hints(connection),
            transaction_profiles=_load_transaction_profiles(connection),
            claim_conflicts=_load_claim_conflicts(connection),
            designer_messages=_load_designer_message_evidence(connection),
            modules=modules,
            fields=fields,
            constraints=constraints,
            native_expectations=(),
        )
    finally:
        connection.close()


def _validated_knowledge_database_path(
    *,
    repo_root: Path,
    database_path: Path,
) -> Path:
    """Return a loadable knowledge database path after freshness checks.

    Returns:
        The resolved repository-confined database path.

    Raises:
        FileNotFoundError: If the generated SQLite database is missing or stale.
        ValueError: If the raw-spec manifest cannot prove SQLite freshness.
    """
    resolved_database = resolve_repo_relative_path(repo_root, database_path)
    if not resolved_database.is_file():
        message = f"Knowledge database is missing: {resolved_database}"
        raise FileNotFoundError(message)
    cache_key = _knowledge_database_validation_cache_key(
        repo_root=repo_root,
        database_path=resolved_database,
    )
    with KNOWLEDGE_DATABASE_VALIDATION_CACHE_LOCK:
        cached = KNOWLEDGE_DATABASE_VALIDATION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    status = knowledge_store_status(
        repo_root=repo_root, database_path=database_path
    )
    if status.status in KNOWLEDGE_REBUILD_STATUSES:
        command = next(
            iter(status.recommended_commands),
            KNOWLEDGE_STATUS_DB_ENSURE_COMMAND,
        )
        message = (
            f"Knowledge database is {status.status}; run {command} before"
            f"loading facts."
        )
        raise FileNotFoundError(message)
    if status.status == "invalid_manifest":
        message = (
            "Knowledge database cannot prove raw-spec freshness because"
            "manifest is invalid."
        )
        raise ValueError(message)
    with KNOWLEDGE_DATABASE_VALIDATION_CACHE_LOCK:
        KNOWLEDGE_DATABASE_VALIDATION_CACHE.clear()
        KNOWLEDGE_DATABASE_VALIDATION_CACHE[cache_key] = resolved_database
    return resolved_database


def _knowledge_database_validation_cache_key(
    *,
    repo_root: Path,
    database_path: Path,
) -> tuple[object, ...]:
    """Return the cache key for one validated knowledge database state."""
    database_stat = database_path.stat()
    manifest_path = resolve_repo_relative_path(
        repo_root, DEFAULT_RAW_SPEC_MANIFEST
    )
    if manifest_path.is_file():
        manifest_stat = manifest_path.stat()
        manifest_mtime = manifest_stat.st_mtime_ns
        manifest_size = manifest_stat.st_size
    else:
        manifest_mtime = 0
        manifest_size = 0
    return (
        str(repo_root.resolve()),
        str(database_path.resolve()),
        database_stat.st_mtime_ns,
        database_stat.st_size,
        str(manifest_path.resolve()),
        manifest_mtime,
        manifest_size,
    )


def knowledge_report_to_json(
    report: KnowledgeStoreBuildReport
    | KnowledgeStoreDumpReport
    | KnowledgeStoreStatusReport,
) -> JsonObject:
    """Return a JSON object for one knowledge-store command report."""
    return normalize_json_object(dict(report._asdict()))


def _connect_database(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with an effectively unbounded busy timeout.

    Returns:
        The opened SQLite connection.
    """
    connection = sqlite3.connect(
        database_path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS
    )
    connection.execute(
        f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
    )
    return connection


def _build_database_path(database_path: Path) -> Path:
    """Return the temporary SQLite build path for atomic materialization."""
    return database_path.with_name(f"{database_path.name}.build.tmp")


def _execute_sql_snapshots(
    connection: sqlite3.Connection, snapshot_dir: Path
) -> int:
    """Execute the engine schema authority and tracked data snapshots.

    Returns:
        The number of executed schema or data SQL files.

    Raises:
        FileNotFoundError: If the data snapshot directory is missing.
    """
    if not snapshot_dir.is_dir():
        message = (
            f"Knowledge data snapshot directory is missing: {snapshot_dir}"
        )
        raise FileNotFoundError(message)

    seed_scripts = tuple(
        sorted(
            path
            for path in snapshot_dir.glob("*.sql")
            if _is_restore_sql_snapshot(path)
        )
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(read_engine_schema_sql())
    for script in seed_scripts:
        connection.executescript(script.read_text(encoding="utf-8"))
    return 1 + len(seed_scripts)


def _is_restore_sql_snapshot(path: Path) -> bool:
    """Return if a SQL file is a tracked or review-created restore snapshot."""
    if (
        path.name in GENERATED_SQL_SNAPSHOT_NAMES
        or path.name in PROJECTION_SQL_SNAPSHOT_NAMES
    ):
        return False
    return not path.name.endswith(GENERATED_SQL_SNAPSHOT_SUFFIXES)


def _preserve_local_state_tables(
    *,
    connection: sqlite3.Connection,
    source_database: Path,
) -> None:
    """Copy non-rebuilt local state from the previous SQLite database."""
    if not source_database.is_file():
        return
    connection.execute(
        "ATTACH DATABASE ? AS old_state", (str(source_database),)
    )
    try:
        for table in PRESERVED_LOCAL_STATE_TABLES:
            _preserve_local_state_table(connection=connection, table=table)
        _assert_loss_protected_local_state_preserved(connection=connection)
    finally:
        connection.commit()
        connection.execute("DETACH DATABASE old_state")


def _preserve_local_state_table(
    *, connection: sqlite3.Connection, table: str
) -> None:
    """Copy one preserved table from attached old_state when schemas are.

    compatible.
    """
    _safe_sqlite_identifier(table)
    if not _table_exists_in_schema(
        connection=connection, schema="old_state", table=table
    ):
        return
    if not _table_exists_in_schema(
        connection=connection, schema="main", table=table
    ):
        if table not in RUNTIME_EXTENSION_TABLES:
            return
        _copy_runtime_extension_table_schema(connection=connection, table=table)
    if not _table_exists_in_schema(
        connection=connection, schema="main", table=table
    ):
        return

    old_columns = _table_columns_in_schema(
        connection=connection, schema="old_state", table=table
    )
    new_columns = _table_columns_in_schema(
        connection=connection, schema="main", table=table
    )
    if not old_columns or old_columns != new_columns:
        return

    column_sql = _sqlite_identifier_list(old_columns)
    if table == "ingest_runs":
        source_kind_placeholders = ", ".join(
            "?" for _ in RAW_SPEC_INGEST_SOURCE_KINDS
        )
        connection.execute(
            f"INSERT OR IGNORE INTO main.{table} ({column_sql}) "
            f"SELECT {column_sql} FROM old_state.{table} "
            f"WHERE source_kind NOT IN ({source_kind_placeholders})",
            tuple(sorted(RAW_SPEC_INGEST_SOURCE_KINDS)),
        )
        return
    connection.execute(
        f"INSERT OR REPLACE INTO main.{table} ({column_sql}) "
        f"SELECT {column_sql} FROM old_state.{table}"
    )


def _assert_loss_protected_local_state_preserved(
    *, connection: sqlite3.Connection
) -> None:
    """Fail before replacement when semantic, graph, or runtime state would be.

    lost.

    Raises:
    RuntimeError: If any loss-protected table with source rows is not preserved.
    """
    for table in LOSS_PROTECTED_LOCAL_STATE_TABLES:
        _safe_sqlite_identifier(table)
        if not _table_exists_in_schema(
            connection=connection, schema="old_state", table=table
        ):
            continue
        old_row_count = _table_row_count_in_schema(
            connection=connection,
            schema="old_state",
            table=table,
        )
        if old_row_count == 0:
            continue
        if not _table_exists_in_schema(
            connection=connection, schema="main", table=table
        ):
            message = _local_state_loss_message(
                table=table,
                old_row_count=old_row_count,
                new_row_count=0,
                reason="destination table is missing",
            )
            raise RuntimeError(message)

        old_columns = _table_columns_in_schema(
            connection=connection,
            schema="old_state",
            table=table,
        )
        new_columns = _table_columns_in_schema(
            connection=connection,
            schema="main",
            table=table,
        )
        if not old_columns or old_columns != new_columns:
            message = _local_state_loss_message(
                table=table,
                old_row_count=old_row_count,
                new_row_count=_table_row_count_in_schema(
                    connection=connection,
                    schema="main",
                    table=table,
                ),
                reason="source and destination schemas are incompatible",
            )
            raise RuntimeError(message)

        new_row_count = _table_row_count_in_schema(
            connection=connection,
            schema="main",
            table=table,
        )
        if new_row_count < old_row_count:
            message = _local_state_loss_message(
                table=table,
                old_row_count=old_row_count,
                new_row_count=new_row_count,
                reason="fewer rows were preserved",
            )
            raise RuntimeError(message)


def _local_state_loss_message(
    *,
    table: str,
    old_row_count: int,
    new_row_count: int,
    reason: str,
) -> str:
    return (
        "Refusing to replace the knowledge SQLite database because "
        "loss-protected "
        f"local state table {table!r} was not preserved: {reason}; "
        f"old_row_count={old_row_count}; new_row_count={new_row_count}."
    )


def _copy_runtime_extension_table_schema(
    *,
    connection: sqlite3.Connection,
    table: str,
) -> None:
    """Copy a runtime extension table and indexes from the previous database."""
    _safe_sqlite_identifier(table)
    row = connection.execute(
        """
        SELECT sql
        FROM old_state.sqlite_master
        WHERE type = 'table'
          AND name = ?
          AND sql IS NOT NULL
        """,
        (table,),
    ).fetchone()
    if row is None:
        return
    create_table_sql = str(row[0]).strip()
    if not _is_safe_create_table_sql(create_table_sql, table):
        return
    connection.execute(create_table_sql)
    index_rows = connection.execute(
        """
        SELECT sql
        FROM old_state.sqlite_master
        WHERE type = 'index'
          AND tbl_name = ?
          AND sql IS NOT NULL
        ORDER BY name
        """,
        (table,),
    ).fetchall()
    for index_row in index_rows:
        create_index_sql = str(index_row[0]).strip()
        if _is_safe_create_index_sql(create_index_sql, table):
            connection.execute(create_index_sql)


def _table_exists_in_schema(
    *,
    connection: sqlite3.Connection,
    schema: str,
    table: str,
) -> bool:
    """Return whether a table exists in one attached SQLite schema."""
    _safe_sqlite_identifier(schema)
    _safe_sqlite_identifier(table)
    row = connection.execute(
        f"SELECT name FROM {schema}.sqlite_master "
        "WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns_in_schema(
    *,
    connection: sqlite3.Connection,
    schema: str,
    table: str,
) -> tuple[str, ...]:
    """Return one table's columns from a specific attached SQLite schema."""
    _safe_sqlite_identifier(schema)
    _safe_sqlite_identifier(table)
    rows = connection.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    columns = tuple(str(row[1]) for row in rows)
    if not all(_is_safe_sqlite_identifier(column) for column in columns):
        return ()
    return columns


def _table_row_count_in_schema(
    *,
    connection: sqlite3.Connection,
    schema: str,
    table: str,
) -> int:
    """Return the full row count for one attached SQLite table."""
    _safe_sqlite_identifier(schema)
    _safe_sqlite_identifier(table)
    row = connection.execute(
        f"SELECT COUNT(*) FROM {schema}.{table}"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _is_safe_create_table_sql(sql: str, table: str) -> bool:
    """Return whether runtime extension DDL is a bounded table definition."""
    normalized = " ".join(sql.lower().split())
    return normalized.startswith(
        (
            f"create table {table.lower()} ",
            f"create table if not exists {table.lower()} ",
        )
    )


def _is_safe_create_index_sql(sql: str, table: str) -> bool:
    """Return whether runtime extension index DDL targets the copied table."""
    normalized = " ".join(sql.lower().split())
    return (
        normalized.startswith("create index ")
        and f" on {table.lower()} " in normalized
    )


def _sqlite_identifier_list(identifiers: tuple[str, ...]) -> str:
    """Return comma-separated SQLite identifiers after validation."""
    for identifier in identifiers:
        _safe_sqlite_identifier(identifier)
    return ", ".join(identifiers)


def _safe_sqlite_identifier(identifier: str) -> str:
    """Return a validated ASCII SQLite identifier.

    Raises:
        ValueError: If the identifier is unsafe for dynamic SQLite SQL.
    """
    if _is_safe_sqlite_identifier(identifier):
        return identifier
    message = f"Unsafe SQLite identifier: {identifier!r}"
    raise ValueError(message)


def _is_safe_sqlite_identifier(identifier: str) -> bool:
    """Return whether text is a simple ASCII SQLite identifier."""
    if not identifier or not identifier.isascii():
        return False
    first = identifier[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(
        character.isalnum() or character == "_" for character in identifier
    )


def _load_manifest_if_available(manifest_path: Path) -> RawSpecManifest | None:
    """Return a raw-spec manifest if it exists."""
    if not manifest_path.is_file():
        return None
    return load_raw_spec_manifest(manifest_path)


def _load_raw_spec_bundle_if_available(
    *,
    repo_root: Path,
    database_path: Path,
    manifest_path: Path,
) -> RawSpecSqliteBundle | None:
    """Return the raw-spec bundle from SQLite, falling back to legacy files."""
    sqlite_bundle = load_sqlite_raw_spec_bundle(database_path=database_path)
    if sqlite_bundle is not None:
        return sqlite_bundle
    manifest = _load_manifest_if_available(manifest_path)
    if manifest is None:
        return None
    return RawSpecSqliteBundle(
        manifest=manifest,
        payloads_by_ref={
            record.relative_path: _load_raw_spec_payload(
                connection=None,
                repo_root=repo_root,
                record=record,
                payloads_by_ref=None,
            )
            for record in manifest.records
        },
    )


def _ingest_raw_spec_manifest(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
    manifest: RawSpecManifest,
    payloads_by_ref: Mapping[str, JsonObject] | None,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> None:
    """Normalize one raw-spec manifest into current SQLite facts."""
    direct_raw_insert = not any(
        _current_count(connection, table)
        for table in ("apps", "app_versions", "modules")
    )
    seen_keys = _new_raw_spec_seen_keys()
    target_keys: RawSpecTargetKeys = set()
    run_id = payload_fingerprint(
        {
            "manifest_sha256": manifest.manifest_sha256,
            "generated_at_utc": manifest.generated_at_utc,
        }
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO ingest_runs (
        run_id, source_kind, source_ref, generated_at_utc, fingerprint,
        record_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "raw_spec_manifest",
            manifest.raw_spec_dir,
            manifest.generated_at_utc,
            manifest.manifest_sha256,
            len(manifest.records),
        ),
    )
    for record in manifest.records:
        target_keys.add((record.app_slug, record.app_version))
        payload = _load_raw_spec_payload(
            connection=connection,
            repo_root=repo_root,
            record=record,
            payloads_by_ref=payloads_by_ref,
        )
        _ingest_raw_spec_record(
            connection=connection,
            record=record,
            payload=payload,
            valid_from=manifest.generated_at_utc,
            direct_insert=direct_raw_insert,
            seen_keys=seen_keys,
            diagnostics=diagnostics,
        )
    _close_stale_raw_spec_rows(
        connection=connection,
        seen_keys=seen_keys,
        target_keys=target_keys,
        valid_to=manifest.generated_at_utc,
    )


def _load_raw_spec_payload(
    *,
    connection: sqlite3.Connection | None,
    repo_root: Path,
    record: RawSpecRecord,
    payloads_by_ref: Mapping[str, JsonObject] | None,
) -> JsonObject:
    """Load and verify one raw-spec payload referenced by a manifest record.

    Returns:
        The verified raw-spec JSON object.

    Raises:
        TypeError: If the raw-spec payload is not a JSON object.
        ValueError: If the raw-spec hash does not match the manifest.
    """
    if payloads_by_ref is not None and record.relative_path in payloads_by_ref:
        return payloads_by_ref[record.relative_path]
    if is_sqlite_raw_spec_ref(record.relative_path):
        if connection is None:
            message = (
                f"SQLite raw spec payload requires an open connection:"
                f"{record.relative_path}"
            )
            raise ValueError(message)
        return load_sqlite_raw_spec_payload(
            connection=connection, record=record
        )
    raw_spec_path = resolve_repo_relative_path(
        repo_root, Path(record.relative_path)
    )
    payload_bytes = raw_spec_path.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    if digest != record.sha256:
        message = f"Raw spec hash mismatch for {record.relative_path}."
        raise ValueError(message)
    payload = cast("object", json.loads(payload_bytes.decode("utf-8")))
    if not isinstance(payload, dict):
        message = f"Raw spec {record.relative_path} must contain a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _ingest_raw_spec_record(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
    payload: JsonObject,
    valid_from: str,
    direct_insert: bool,
    seen_keys: RawSpecSeenKeys,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> None:
    """Normalize one raw-spec app/version payload into temporal fact tables."""
    parsed = parse_make_raw_spec(payload)
    app_payload = _object_member(payload, "app")
    _insert_temporal_row(
        connection=connection,
        table="apps",
        key_columns=("app_slug",),
        key_values=(record.app_slug,),
        columns=(
            "app_slug",
            "label",
            "external_id",
            "source_kind",
            "source_ref",
            "valid_from",
            "valid_to",
            "fingerprint",
            "adr_anchor",
        ),
        values=(
            record.app_slug,
            record.app_label,
            record.app_slug,
            "raw_spec",
            record.relative_path,
            valid_from,
            None,
            payload_fingerprint(
                {"app_slug": record.app_slug, "label": record.app_label}
            ),
            "001064#repo.make-knowledge.raw-spec-normalization",
        ),
        valid_from=valid_from,
        direct_insert=direct_insert,
    )
    _remember_raw_spec_key(seen_keys, "apps", (record.app_slug,))
    _insert_temporal_row(
        connection=connection,
        table="app_versions",
        key_columns=("app_slug", "app_version"),
        key_values=(record.app_slug, record.app_version),
        columns=(
            "app_slug",
            "app_version",
            "latest",
            "manifest_version",
            "raw_spec_sha256",
            "source_kind",
            "source_ref",
            "valid_from",
            "valid_to",
            "fingerprint",
            "adr_anchor",
        ),
        values=(
            record.app_slug,
            record.app_version,
            int(parsed.latest),
            record.manifest_version,
            record.sha256,
            "raw_spec",
            record.relative_path,
            valid_from,
            None,
            payload_fingerprint(_record_payload(record)),
            "001064#repo.make-knowledge.raw-spec-normalization",
        ),
        valid_from=valid_from,
        direct_insert=direct_insert,
    )
    _remember_raw_spec_key(
        seen_keys, "app_versions", (record.app_slug, record.app_version)
    )
    for module_kind, module_payload in _iter_module_payloads(app_payload):
        _ingest_module(
            connection=connection,
            record=record,
            module_kind=module_kind,
            module_payload=module_payload,
            valid_from=valid_from,
            direct_insert=direct_insert,
            seen_keys=seen_keys,
            diagnostics=diagnostics,
        )


def _ingest_module(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
    module_kind: CatalogModuleKind,
    module_payload: JsonObject,
    valid_from: str,
    direct_insert: bool,
    seen_keys: RawSpecSeenKeys,
    diagnostics: list[CatalogRawSpecDiagnostic],
) -> None:
    """Normalize one raw module payload into module, field, and constraint.

    rows.
    """
    internal_name = _optional_text(module_payload, "name")
    if internal_name is None:
        return
    display_name = _optional_text(module_payload, "label") or internal_name
    durable_module_id = module_id(
        app_slug=record.app_slug,
        app_version=record.app_version,
        module_kind=module_kind,
        internal_name=internal_name,
    )
    module_fingerprint = payload_fingerprint(
        {
            "module_id": durable_module_id,
            "display_name": display_name,
            "payload": module_payload,
            "raw_spec_sha256": record.sha256,
        }
    )
    _insert_temporal_row(
        connection=connection,
        table="modules",
        key_columns=("module_id",),
        key_values=(durable_module_id,),
        columns=(
            "module_id",
            "app_slug",
            "app_version",
            "module_kind",
            "internal_name",
            "display_name",
            "external_id",
            "deprecated",
            "raw_spec_sha256",
            "source_kind",
            "source_ref",
            "valid_from",
            "valid_to",
            "fingerprint",
            "adr_anchor",
        ),
        values=(
            durable_module_id,
            record.app_slug,
            record.app_version,
            module_kind,
            internal_name,
            display_name,
            (
                f"{record.app_slug}:{record.app_version}:{module_kind}:{internal_name}"
            ),
            int(_optional_bool(module_payload, "deprecated")),
            record.sha256,
            "raw_spec",
            record.relative_path,
            valid_from,
            None,
            module_fingerprint,
            "001064#repo.make-knowledge.raw-spec-normalization",
        ),
        valid_from=valid_from,
        direct_insert=direct_insert,
    )
    _remember_raw_spec_key(seen_keys, "modules", (durable_module_id,))
    diagnostic_context = RawFieldDiagnosticContext(
        diagnostics=diagnostics,
        durable_module_id=durable_module_id,
        record=record,
        module_kind=module_kind,
        internal_name=internal_name,
    )
    for field in _iter_field_payloads(
        module_payload,
        diagnostic_context=diagnostic_context,
    ):
        durable_field_id = field_id(
            parent_module_id=durable_module_id,
            direction=field.direction,
            path=field.path,
        )
        if (durable_field_id,) in seen_keys["fields"]:
            _append_field_diagnostic(
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.field_duplicate",
                    field_path=field.path,
                    collection_path=field.collection_path,
                    message=(
                        "Raw field metadata repeats the normalized field path "
                        f"{'.'.join(field.path)!r}; the first occurrence "
                        f"was kept."
                    ),
                ),
            )
            continue
        _ingest_field(
            connection=connection,
            record=record,
            durable_module_id=durable_module_id,
            direction=field.direction,
            field_payload=field.payload,
            field_path=field.path,
            valid_from=valid_from,
            direct_insert=direct_insert,
            seen_keys=seen_keys,
        )


def _ingest_field(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
    durable_module_id: str,
    direction: str,
    field_payload: JsonObject,
    field_path: tuple[str, ...],
    valid_from: str,
    direct_insert: bool,
    seen_keys: RawSpecSeenKeys,
) -> None:
    """Normalize one raw field payload into field and constraint rows."""
    durable_field_id = field_id(
        parent_module_id=durable_module_id,
        direction=direction,
        path=field_path,
    )
    field_type = canonicalize_catalog_field_type(
        _optional_text(field_payload, "type")
    )
    field_fingerprint = payload_fingerprint(
        {
            "field_id": durable_field_id,
            "payload": field_payload,
        }
    )
    _insert_temporal_row(
        connection=connection,
        table="fields",
        key_columns=("field_id",),
        key_values=(durable_field_id,),
        columns=(
            "field_id",
            "module_id",
            "direction",
            "path",
            "label",
            "required",
            "field_type",
            "raw_schema_json",
            "source_kind",
            "source_ref",
            "valid_from",
            "valid_to",
            "fingerprint",
            "adr_anchor",
        ),
        values=(
            durable_field_id,
            durable_module_id,
            direction,
            ".".join(field_path),
            _optional_text(field_payload, "label") or field_path[-1],
            int(_optional_bool(field_payload, "required")),
            field_type,
            _canonical_json_text(field_payload),
            "raw_spec",
            record.relative_path,
            valid_from,
            None,
            field_fingerprint,
            "001064#repo.make-knowledge.raw-spec-normalization",
        ),
        valid_from=valid_from,
        direct_insert=direct_insert,
    )
    _remember_raw_spec_key(seen_keys, "fields", (durable_field_id,))
    for key, value in _constraint_payloads(field_payload):
        durable_constraint_id = constraint_id(
            parent_field_id=durable_field_id, key=key
        )
        _insert_temporal_row(
            connection=connection,
            table="constraints",
            key_columns=("constraint_id",),
            key_values=(durable_constraint_id,),
            columns=(
                "constraint_id",
                "field_id",
                "constraint_key",
                "value_json",
                "source_kind",
                "source_ref",
                "valid_from",
                "valid_to",
                "fingerprint",
                "adr_anchor",
            ),
            values=(
                durable_constraint_id,
                durable_field_id,
                key,
                _canonical_json_text(value),
                "raw_spec",
                record.relative_path,
                valid_from,
                None,
                payload_fingerprint(
                    {
                        "constraint_id": durable_constraint_id,
                        "key": key,
                        "value": value,
                    }
                ),
                "001064#repo.make-knowledge.raw-spec-normalization",
            ),
            valid_from=valid_from,
            direct_insert=direct_insert,
        )
        _remember_raw_spec_key(
            seen_keys, "constraints", (durable_constraint_id,)
        )


def _insert_temporal_row(
    *,
    connection: sqlite3.Connection,
    table: str,
    key_columns: tuple[str, ...],
    key_values: tuple[object, ...],
    columns: tuple[str, ...],
    values: tuple[object, ...],
    valid_from: str,
    direct_insert: bool,
) -> None:
    """Insert a temporal row after closing a changed current fact."""
    fingerprint = str(values[columns.index("fingerprint")])
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    if direct_insert:
        connection.execute(
            f"INSERT OR REPLACE INTO {table} ({column_sql}) VALUES ({placeholders})",
            values,
        )
        return
    current_fingerprint = _current_fingerprint(
        connection, table, key_columns, key_values
    )
    if current_fingerprint == fingerprint:
        return
    _close_current_row(
        connection=connection,
        table=table,
        key_columns=key_columns,
        key_values=key_values,
        fingerprint=fingerprint,
        valid_to=valid_from,
    )
    connection.execute(
        f"INSERT OR REPLACE INTO {table} ({column_sql}) VALUES ({placeholders})",
        values,
    )


def _current_fingerprint(
    connection: sqlite3.Connection,
    table: str,
    key_columns: tuple[str, ...],
    key_values: tuple[object, ...],
) -> str | None:
    """Return the current fingerprint for one temporal fact key."""
    where_sql = " AND ".join(f"{column} = ?" for column in key_columns)
    row = connection.execute(
        f"SELECT fingerprint FROM {table} WHERE {where_sql} AND valid_to IS NULL "
        "ORDER BY valid_from DESC LIMIT 1",
        key_values,
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _close_current_row(
    *,
    connection: sqlite3.Connection,
    table: str,
    key_columns: tuple[str, ...],
    key_values: tuple[object, ...],
    fingerprint: str,
    valid_to: str,
) -> None:
    """Close any changed current row for a temporal fact key."""
    where_sql = " AND ".join(f"{column} = ?" for column in key_columns)
    connection.execute(
        f"UPDATE {table} SET valid_to = ? WHERE {where_sql} "
        "AND valid_to IS NULL AND fingerprint <> ?",
        (valid_to, *key_values, fingerprint),
    )


def _new_raw_spec_seen_keys() -> RawSpecSeenKeys:
    return {
        "apps": set(),
        "app_versions": set(),
        "modules": set(),
        "fields": set(),
        "constraints": set(),
    }


def _remember_raw_spec_key(
    seen_keys: RawSpecSeenKeys,
    table: str,
    key_values: tuple[object, ...],
) -> None:
    seen_keys[table].add(tuple(str(value) for value in key_values))


def _close_stale_raw_spec_rows(
    *,
    connection: sqlite3.Connection,
    seen_keys: RawSpecSeenKeys,
    target_keys: RawSpecTargetKeys,
    valid_to: str,
) -> None:
    if not target_keys:
        return
    _close_stale_raw_spec_child_rows(
        StaleRawSpecChildRowsRequest(
            connection=connection,
            table="constraints",
            key_column="constraint_id",
            seen_keys=seen_keys["constraints"],
            target_keys=target_keys,
            valid_to=valid_to,
        )
    )
    _close_stale_raw_spec_child_rows(
        StaleRawSpecChildRowsRequest(
            connection=connection,
            table="fields",
            key_column="field_id",
            seen_keys=seen_keys["fields"],
            target_keys=target_keys,
            valid_to=valid_to,
        )
    )
    _close_stale_raw_spec_module_rows(
        connection=connection,
        seen_keys=seen_keys["modules"],
        target_keys=target_keys,
        valid_to=valid_to,
    )


def _close_stale_raw_spec_child_rows(
    request: StaleRawSpecChildRowsRequest,
) -> None:
    join_sql = (
        "JOIN fields AS f ON f.field_id = t.field_id AND f.valid_to IS NULL "
        "JOIN modules AS m ON m.module_id = f.module_id AND m.valid_to IS NULL"
        if request.table == "constraints"
        else (
            "JOIN modules AS m ON m.module_id = t.module_id AND m.valid_to IS"
            "NULL"
        )
    )
    rows = request.connection.execute(
        f"SELECT t.{request.key_column}, m.app_slug, m.app_version "
        f"FROM {request.table} AS t {join_sql} "
        "WHERE t.valid_to IS NULL AND t.source_kind = 'raw_spec'"
    ).fetchall()
    for row in rows:
        key = (str(row[0]),)
        target_key = (str(row[1]), str(row[2]))
        if target_key not in request.target_keys or key in request.seen_keys:
            continue
        request.connection.execute(
            f"UPDATE {request.table} SET valid_to = ? WHERE {request.key_column} = ? "
            "AND valid_to IS NULL AND source_kind = 'raw_spec'",
            (request.valid_to, key[0]),
        )


def _close_stale_raw_spec_module_rows(
    *,
    connection: sqlite3.Connection,
    seen_keys: set[tuple[object, ...]],
    target_keys: RawSpecTargetKeys,
    valid_to: str,
) -> None:
    rows = connection.execute(
        """
        SELECT module_id, app_slug, app_version
        FROM modules
        WHERE valid_to IS NULL AND source_kind = 'raw_spec'
        """
    ).fetchall()
    for row in rows:
        key = (str(row[0]),)
        target_key = (str(row[1]), str(row[2]))
        if target_key not in target_keys or key in seen_keys:
            continue
        connection.execute(
            """
            UPDATE modules
            SET valid_to = ?
            WHERE module_id = ?
              AND valid_to IS NULL
              AND source_kind = 'raw_spec'
            """,
            (valid_to, key[0]),
        )


def _materialize_claim_conflicts(connection: sqlite3.Connection) -> None:
    """Materialize current claim conflicts from claim-evidence rows."""
    evidence_by_key = _claim_evidence_by_key(connection)
    latest_valid_from = _latest_claim_evidence_valid_from(connection)
    emitted_conflict_ids: set[str] = set()
    for claim_key, evidence_rows in evidence_by_key.items():
        distinct_values = {row.value_json for row in evidence_rows}
        if len(distinct_values) < MIN_DISTINCT_CLAIM_VALUES_FOR_CONFLICT:
            continue
        winner = _winning_claim_evidence(evidence_rows)
        for loser in evidence_rows:
            if (
                loser.evidence_id == winner.evidence_id
                or loser.value_json == winner.value_json
            ):
                continue
            conflict_id = _claim_conflict_id(
                claim_key=claim_key,
                winning_evidence_id=winner.evidence_id,
                losing_evidence_id=loser.evidence_id,
            )
            resolution_status, arbitration_reason = _claim_arbitration_outcome(
                winner=winner,
                loser=loser,
            )
            fingerprint = payload_fingerprint(
                {
                    "claim_key": claim_key,
                    "domain": winner.domain,
                    "winning_evidence_id": winner.evidence_id,
                    "losing_evidence_id": loser.evidence_id,
                    "winning_value_json": winner.value_json,
                    "losing_value_json": loser.value_json,
                    "resolution_status": resolution_status,
                    "arbitration_reason": arbitration_reason,
                }
            )
            valid_from = max(winner.valid_from, loser.valid_from)
            _insert_temporal_row(
                connection=connection,
                table="claim_conflicts",
                key_columns=("conflict_id",),
                key_values=(conflict_id,),
                columns=(
                    "conflict_id",
                    "claim_key",
                    "domain",
                    "winning_evidence_id",
                    "losing_evidence_id",
                    "winning_value_json",
                    "losing_value_json",
                    "winning_source_kind",
                    "winning_source_ref",
                    "losing_source_kind",
                    "losing_source_ref",
                    "winning_source_confidence",
                    "losing_source_confidence",
                    "winning_evidence_observed_at",
                    "losing_evidence_observed_at",
                    "resolution_status",
                    "arbitration_reason",
                    "source_kind",
                    "source_ref",
                    "valid_from",
                    "valid_to",
                    "fingerprint",
                    "adr_anchor",
                ),
                values=(
                    conflict_id,
                    claim_key,
                    winner.domain,
                    winner.evidence_id,
                    loser.evidence_id,
                    winner.value_json,
                    loser.value_json,
                    winner.source_kind,
                    winner.source_ref,
                    loser.source_kind,
                    loser.source_ref,
                    winner.source_confidence,
                    loser.source_confidence,
                    winner.evidence_observed_at,
                    loser.evidence_observed_at,
                    resolution_status,
                    arbitration_reason,
                    "materialized",
                    f"claim_evidence:{winner.evidence_id}>{loser.evidence_id}",
                    valid_from,
                    None,
                    fingerprint,
                    "001064#repo.make-knowledge.claim-conflict-arbitration",
                ),
                valid_from=valid_from,
                direct_insert=False,
            )
            emitted_conflict_ids.add(conflict_id)
    if latest_valid_from is not None:
        _close_omitted_claim_conflicts(
            connection=connection,
            emitted_conflict_ids=emitted_conflict_ids,
            valid_to=latest_valid_from,
        )


def _claim_evidence_by_key(
    connection: sqlite3.Connection,
) -> dict[str, tuple[ClaimEvidenceRow, ...]]:
    """Return current claim-evidence rows grouped by claim key."""
    rows = connection.execute(
        """
        SELECT
          evidence_id,
          claim_key,
          domain,
          value_json,
          source_confidence,
          evidence_observed_at,
          source_kind,
          source_ref,
          valid_from,
          adr_anchor
        FROM claim_evidence
        WHERE valid_to IS NULL
        ORDER BY claim_key, evidence_id
        """
    ).fetchall()
    grouped: dict[str, list[ClaimEvidenceRow]] = {}
    for row in rows:
        evidence = ClaimEvidenceRow(
            evidence_id=str(row[0]),
            claim_key=str(row[1]),
            domain=str(row[2]),
            value_json=str(row[3]),
            source_confidence=int(row[4]),
            evidence_observed_at=str(row[5]),
            source_kind=str(row[6]),
            source_ref=str(row[7]),
            valid_from=str(row[8]),
            adr_anchor=str(row[9]),
        )
        grouped.setdefault(evidence.claim_key, []).append(evidence)
    return {
        claim_key: tuple(evidence_rows)
        for claim_key, evidence_rows in grouped.items()
    }


def _latest_claim_evidence_valid_from(
    connection: sqlite3.Connection,
) -> str | None:
    """Return the newest current claim-evidence validity timestamp."""
    row = connection.execute(
        "SELECT MAX(valid_from) FROM claim_evidence WHERE valid_to IS NULL"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _winning_claim_evidence(
    evidence_rows: tuple[ClaimEvidenceRow, ...],
) -> ClaimEvidenceRow:
    """Return the deterministic winning evidence row for one conflict group."""
    highest_confidence = max(row.source_confidence for row in evidence_rows)
    confidence_candidates = tuple(
        row
        for row in evidence_rows
        if row.source_confidence == highest_confidence
    )
    newest_observed_at = max(
        row.evidence_observed_at for row in confidence_candidates
    )
    recency_candidates = tuple(
        row
        for row in confidence_candidates
        if row.evidence_observed_at == newest_observed_at
    )
    return min(recency_candidates, key=lambda row: row.evidence_id)


def _claim_arbitration_outcome(
    *,
    winner: ClaimEvidenceRow,
    loser: ClaimEvidenceRow,
) -> tuple[str, str]:
    """Return the resolution status and reason for one conflict pair."""
    if winner.source_confidence > loser.source_confidence:
        return "resolved", "higher source confidence"
    if winner.evidence_observed_at > loser.evidence_observed_at:
        return "resolved", "newer evidence observed_at"
    return (
        "needs_review",
        "equal confidence and recency; stable evidence_id tiebreaker",
    )


def _claim_conflict_id(
    *,
    claim_key: str,
    winning_evidence_id: str,
    losing_evidence_id: str,
) -> str:
    """Return the computed result for the caller."""
    suffix = payload_fingerprint(
        {
            "claim_key": claim_key,
            "winning_evidence_id": winning_evidence_id,
            "losing_evidence_id": losing_evidence_id,
        }
    )[:16]
    return f"claim-conflict:{suffix}"


def _close_omitted_claim_conflicts(
    *,
    connection: sqlite3.Connection,
    emitted_conflict_ids: set[str],
    valid_to: str,
) -> None:
    """Close current conflicts that no longer have conflicting evidence."""
    if emitted_conflict_ids:
        placeholders = ", ".join("?" for _ in emitted_conflict_ids)
        connection.execute(
            "UPDATE claim_conflicts SET valid_to = ? WHERE valid_to IS NULL "
            f"AND conflict_id NOT IN ({placeholders})",
            (valid_to, *sorted(emitted_conflict_ids)),
        )
        return
    connection.execute(
        "UPDATE claim_conflicts SET valid_to = ? WHERE valid_to IS NULL",
        (valid_to,),
    )


def _status_from_connection(
    *,
    connection: sqlite3.Connection,
    repo_root: Path,
    database_path: Path,
    raw_spec_manifest_path: Path,
    manifest: RawSpecManifest | None,
) -> KnowledgeStoreStatusReport:
    """Build a status report from an open SQLite connection.

    Returns:
        The current knowledge-store status.
    """
    schema_version = _schema_version(connection)
    gaps = _native_module_gaps(connection)
    database_ingest = _latest_raw_spec_manifest_ingest(connection)
    database_manifest_generated_at = (
        None if database_ingest is None else database_ingest[0]
    )
    database_manifest_sha256 = (
        None if database_ingest is None else database_ingest[1]
    )
    manifest_matches_database = _manifest_matches_database(
        manifest=manifest,
        database_manifest_sha256=database_manifest_sha256,
    )
    status_label = _knowledge_status_label(
        native_module_gaps=gaps,
        raw_spec_manifest_matches_database=manifest_matches_database,
    )
    return KnowledgeStoreStatusReport(
        status=status_label,
        database_path=relative_to_repo(repo_root, database_path),
        database_available=True,
        schema_version=schema_version,
        raw_spec_manifest_path=relative_to_repo(
            repo_root, raw_spec_manifest_path
        ),
        missing_paths=_knowledge_status_missing_paths(
            repo_root=repo_root,
            database_path=database_path,
            raw_spec_manifest_path=raw_spec_manifest_path,
        ),
        recommended_commands=_knowledge_status_recommended_commands(
            status_label
        ),
        raw_spec_manifest_available=manifest is not None,
        raw_spec_manifest_generated_at_utc=None
        if manifest is None
        else manifest.generated_at_utc,
        raw_spec_manifest_sha256=None
        if manifest is None
        else manifest.manifest_sha256,
        database_raw_spec_manifest_generated_at_utc=database_manifest_generated_at,
        database_raw_spec_manifest_sha256=database_manifest_sha256,
        raw_spec_manifest_matches_database=manifest_matches_database,
        raw_spec_record_count=0 if manifest is None else len(manifest.records),
        app_count=_current_count(connection, "apps"),
        app_version_count=_current_count(connection, "app_versions"),
        module_count=_current_count(connection, "modules"),
        alias_count=_current_count(connection, "module_aliases"),
        rule_count=_current_count(connection, "rule_facts"),
        optimizer_hint_count=_current_count(connection, "optimizer_hints"),
        transaction_profile_count=_current_count(
            connection, "module_transaction_profiles"
        ),
        course_claim_count=_current_count(connection, "course_claims"),
        claim_evidence_count=_current_count(connection, "claim_evidence"),
        claim_conflict_count=_current_count(connection, "claim_conflicts"),
        native_expectation_count=_current_count(
            connection, "native_module_expectations"
        ),
        native_module_gaps=gaps,
        fingerprint=_database_fingerprint(connection),
    )


def _knowledge_status_label(
    *,
    native_module_gaps: tuple[NativeModuleGap, ...],
    raw_spec_manifest_matches_database: bool | None,
) -> str:
    """Return the status label for native coverage and raw-spec freshness."""
    if raw_spec_manifest_matches_database is False:
        return "stale_manifest"
    if native_module_gaps:
        return "degraded"
    return "ok"


def _manifest_matches_database(
    *,
    manifest: RawSpecManifest | None,
    database_manifest_sha256: str | None,
) -> bool | None:
    """Return if the generated DB was built from the current raw manifest."""
    if manifest is None:
        return None
    return database_manifest_sha256 == manifest.manifest_sha256


def _latest_raw_spec_manifest_ingest(
    connection: sqlite3.Connection,
) -> tuple[str, str] | None:
    """Return the latest raw-spec manifest ingest timestamp and fingerprint."""
    row = connection.execute(
        """
        SELECT generated_at_utc, fingerprint
        FROM ingest_runs
        WHERE source_kind = 'raw_spec_manifest'
        ORDER BY generated_at_utc DESC, run_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def _schema_version(connection: sqlite3.Connection) -> int | None:
    """Return the declared knowledge schema version."""
    row = connection.execute(
        "SELECT value FROM snapshot_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return None
    return int(str(row[0]))


def _knowledge_schema_exists(connection: sqlite3.Connection) -> bool:
    """Return whether the SQLite file contains the knowledge-store schema."""
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = "
        "'snapshot_metadata'"
    ).fetchone()
    return row is not None


def _current_count(connection: sqlite3.Connection, table: str) -> int:
    """Return the current row count for one temporal table."""
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE valid_to IS NULL"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _native_module_gaps(
    connection: sqlite3.Connection,
) -> tuple[NativeModuleGap, ...]:
    """Return Make-native module coverage gaps from current facts."""
    rows = connection.execute(
        """
        SELECT app_slug, expected_module_count, expected_kinds_csv, critical
        FROM native_module_expectations
        WHERE valid_to IS NULL
        ORDER BY app_slug
        """
    ).fetchall()
    gaps: list[NativeModuleGap] = []
    for row in rows:
        app_slug = str(row[0])
        expected_count = int(row[1])
        expected_kinds = _csv_tuple(row[2])
        critical = bool(row[3])
        observed_count = _observed_module_count(connection, app_slug)
        observed_kinds = _observed_module_kinds(connection, app_slug)
        missing_kinds = tuple(
            kind for kind in expected_kinds if kind not in observed_kinds
        )
        if observed_count < expected_count or missing_kinds:
            gaps.append(
                NativeModuleGap(
                    app_slug=app_slug,
                    expected_module_count=expected_count,
                    observed_module_count=observed_count,
                    expected_kinds=expected_kinds,
                    observed_kinds=observed_kinds,
                    missing_kinds=missing_kinds,
                    critical=critical,
                )
            )
    return tuple(gaps)


def _observed_module_count(
    connection: sqlite3.Connection, app_slug: str
) -> int:
    """Return current module count for one app slug."""
    row = connection.execute(
        "SELECT COUNT(*) FROM modules WHERE app_slug = ? AND valid_to IS NULL",
        (app_slug,),
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _observed_module_kinds(
    connection: sqlite3.Connection, app_slug: str
) -> tuple[str, ...]:
    """Return sorted current module kinds for one app slug."""
    rows = connection.execute(
        """
        SELECT DISTINCT module_kind
        FROM modules
        WHERE app_slug = ? AND valid_to IS NULL
        ORDER BY module_kind
        """,
        (app_slug,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _database_fingerprint(connection: sqlite3.Connection) -> str:
    """Return a compact deterministic fingerprint for knowledge-store facts."""
    return _fingerprint_for_tables(connection=connection, tables=DUMP_TABLES)


def _query_fingerprint(
    *,
    connection: sqlite3.Connection,
    include_structural_facts: bool,
) -> str:
    """Return the deterministic fingerprint for a loaded query projection."""
    tables = (
        DUMP_TABLES
        if include_structural_facts
        else LIGHTWEIGHT_QUERY_FINGERPRINT_TABLES
    )
    return _fingerprint_for_tables(connection=connection, tables=tables)


def _fingerprint_for_tables(
    *,
    connection: sqlite3.Connection,
    tables: tuple[str, ...],
) -> str:
    """Return the computed result for the caller."""
    payload: JsonObject = {}
    for table in tables:
        payload[table] = _table_fingerprint_summary(connection, table)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _table_fingerprint_summary(
    connection: sqlite3.Connection, table: str
) -> JsonObject:
    """Return compact fingerprint inputs for one table.

    Returns:
        The table count and boundary values.
    """
    columns = set(_table_columns(connection, table))
    if "fingerprint" in columns and "valid_from" in columns:
        sql = (
            f"SELECT COUNT(*), MIN(fingerprint), MAX(fingerprint), "
            "MIN(valid_from), MAX(valid_from), "
            "MIN(COALESCE(valid_to, '')), MAX(COALESCE(valid_to, '')) "
            f"FROM {table}"
        )
        row = connection.execute(sql).fetchone()
        if row is None:
            return {"row_count": 0}
        return {
            "row_count": int(row[0]),
            "min_fingerprint": None if row[1] is None else str(row[1]),
            "max_fingerprint": None if row[2] is None else str(row[2]),
            "min_valid_from": None if row[3] is None else str(row[3]),
            "max_valid_from": None if row[4] is None else str(row[4]),
            "min_valid_to": None if row[5] is None else str(row[5]),
            "max_valid_to": None if row[6] is None else str(row[6]),
        }
    if "fingerprint" in columns:
        sql = (
            f"SELECT COUNT(*), MIN(fingerprint), MAX(fingerprint) FROM {table}"
        )
        row = connection.execute(sql).fetchone()
        if row is None:
            return {"row_count": 0}
        return {
            "row_count": int(row[0]),
            "min_fingerprint": None if row[1] is None else str(row[1]),
            "max_fingerprint": None if row[2] is None else str(row[2]),
        }
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        return {"row_count": 0}
    return {"row_count": int(row[0])}


def _load_aliases(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeModuleAlias, ...]:
    """Load current module aliases.

    Returns:
        Current module aliases.
    """
    rows = connection.execute(
        """
        SELECT alias_text, canonical_token, canonical_module_id, confidence,
        adr_anchor
        FROM module_aliases
        WHERE valid_to IS NULL
        ORDER BY alias_text, canonical_token
        """
    ).fetchall()
    return tuple(
        KnowledgeModuleAlias(
            alias_text=str(row[0]),
            canonical_token=str(row[1]),
            canonical_module_id=None if row[2] is None else str(row[2]),
            confidence=str(row[3]),
            adr_anchor=str(row[4]),
        )
        for row in rows
    )


def _load_rule_facts(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeRuleFact, ...]:
    """Load current deterministic rule facts.

    Returns:
        Current deterministic rule facts.
    """
    rows = connection.execute(
        """
        SELECT rule_id, domain, rule_code, severity, description, adr_anchor
        FROM rule_facts
        WHERE valid_to IS NULL
        ORDER BY rule_id
        """
    ).fetchall()
    return tuple(
        KnowledgeRuleFact(
            rule_id=str(row[0]),
            domain=str(row[1]),
            rule_code=str(row[2]),
            severity=str(row[3]),
            description=str(row[4]),
            adr_anchor=str(row[5]),
        )
        for row in rows
    )


def _load_optimizer_hints(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeOptimizerHint, ...]:
    """Load current optimization hints.

    Returns:
        Current optimization hints.
    """
    rows = connection.execute(
        """
        SELECT hint_id, domain, hint_code, severity, description, adr_anchor
        FROM optimizer_hints
        WHERE valid_to IS NULL
        ORDER BY hint_id
        """
    ).fetchall()
    return tuple(
        KnowledgeOptimizerHint(
            hint_id=str(row[0]),
            domain=str(row[1]),
            hint_code=str(row[2]),
            severity=str(row[3]),
            description=str(row[4]),
            adr_anchor=str(row[5]),
        )
        for row in rows
    )


def _load_transaction_profiles(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeTransactionProfile, ...]:
    """Load current transaction-safety profiles.

    Returns:
        Current transaction profiles.
    """
    rows = connection.execute(
        """
        SELECT
          profile_id,
          module_selector_kind,
          module_selector,
          operation_kind,
          mutates_state,
          rollback_capability,
          acid_compatibility,
          safety_level,
          description,
          adr_anchor
        FROM module_transaction_profiles
        WHERE valid_to IS NULL
        ORDER BY profile_id
        """
    ).fetchall()
    return tuple(
        KnowledgeTransactionProfile(
            profile_id=str(row[0]),
            module_selector_kind=str(row[1]),
            module_selector=str(row[2]),
            operation_kind=str(row[3]),
            mutates_state=bool(row[4]),
            rollback_capability=str(row[5]),
            acid_compatibility=str(row[6]),
            safety_level=str(row[7]),
            description=str(row[8]),
            adr_anchor=str(row[9]),
        )
        for row in rows
    )


def _load_claim_conflicts(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeClaimConflict, ...]:
    """Load current claim-conflict arbitration rows.

    Returns:
        Current claim conflicts.
    """
    rows = connection.execute(
        """
        SELECT
          conflict_id,
          claim_key,
          domain,
          winning_evidence_id,
          losing_evidence_id,
          winning_value_json,
          losing_value_json,
          winning_source_kind,
          winning_source_ref,
          losing_source_kind,
          losing_source_ref,
          winning_source_confidence,
          losing_source_confidence,
          winning_evidence_observed_at,
          losing_evidence_observed_at,
          resolution_status,
          arbitration_reason,
          fingerprint,
          adr_anchor
        FROM claim_conflicts
        WHERE valid_to IS NULL
        ORDER BY claim_key, conflict_id
        """
    ).fetchall()
    return tuple(
        KnowledgeClaimConflict(
            conflict_id=str(row[0]),
            claim_key=str(row[1]),
            domain=str(row[2]),
            winning_evidence_id=str(row[3]),
            losing_evidence_id=str(row[4]),
            winning_value_json=str(row[5]),
            losing_value_json=str(row[6]),
            winning_source_kind=str(row[7]),
            winning_source_ref=str(row[8]),
            losing_source_kind=str(row[9]),
            losing_source_ref=str(row[10]),
            winning_source_confidence=int(row[11]),
            losing_source_confidence=int(row[12]),
            winning_evidence_observed_at=str(row[13]),
            losing_evidence_observed_at=str(row[14]),
            resolution_status=str(row[15]),
            arbitration_reason=str(row[16]),
            fingerprint=str(row[17]),
            adr_anchor=str(row[18]),
        )
        for row in rows
    )


def _load_designer_message_evidence(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeDesignerMessageEvidence, ...]:
    """Load current reviewed Make designer-message evidence rows.

    Returns:
        Current designer-message evidence.
    """
    rows = connection.execute(
        """
        SELECT
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
          fingerprint,
          adr_anchor
        FROM designer_message_evidence
        WHERE valid_to IS NULL
          AND review_status = 'reviewed'
          AND source_kind = 'designer_message'
          AND severity = 'warning'
        ORDER BY node_id, finding_id
        """
    ).fetchall()
    return tuple(
        KnowledgeDesignerMessageEvidence(
            finding_id=str(row[0]),
            node_id=None if row[1] is None else str(row[1]),
            module_slug=None if row[2] is None else str(row[2]),
            severity=str(row[3]),
            message=str(row[4]),
            category=None if row[5] is None else str(row[5]),
            field_path=None if row[6] is None else str(row[6]),
            review_status=str(row[7]),
            source_kind=str(row[8]),
            source_ref=str(row[9]),
            fingerprint=str(row[10]),
            adr_anchor=str(row[11]),
        )
        for row in rows
    )


def _knowledge_module_search_terms(terms: Sequence[str]) -> tuple[str, ...]:
    """Return SQL-safe, useful module search terms in source order."""
    return _dedupe_values(
        tuple(
            term.casefold().strip()
            for term in terms
            if len(term.casefold().strip())
            >= KNOWLEDGE_MODULE_SEARCH_MIN_TERM_LENGTH
        )
    )


def _search_current_modules_by_terms(
    *,
    connection: sqlite3.Connection,
    terms: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    """Return matching current module IDs from module text columns."""
    condition, parameters = _knowledge_search_clause(
        columns=(
            "module_id",
            "app_slug",
            "module_kind",
            "internal_name",
            "display_name",
        ),
        terms=terms,
    )
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT module_id, app_slug, module_kind, internal_name, display_name
        FROM modules
        WHERE valid_to IS NULL
          AND ({condition})
        ORDER BY app_slug, app_version, module_kind, internal_name, module_id
        """,
        parameters,
    ).fetchall()
    ranked = _rank_search_rows(rows=tuple(rows), terms=terms)
    return ranked[: limit + 1]


def _search_current_field_modules_by_terms(
    *,
    connection: sqlite3.Connection,
    terms: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    """Return matching current module IDs from field text columns."""
    condition, parameters = _knowledge_search_clause(
        columns=(
            "f.path",
            "f.label",
            "COALESCE(f.field_type, '')",
            "f.module_id",
        ),
        terms=terms,
    )
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT DISTINCT m.module_id
        FROM modules AS m
        INNER JOIN fields AS f
          ON f.module_id = m.module_id
         AND f.valid_to IS NULL
        WHERE m.valid_to IS NULL
          AND ({condition})
        ORDER BY m.app_slug, m.app_version, m.module_kind, m.internal_name,
        m.module_id
        LIMIT ?
        """,
        (*parameters, limit + 1),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _rank_search_rows(
    *,
    rows: tuple[object, ...],
    terms: tuple[str, ...],
) -> tuple[str, ...]:
    """Return module IDs whose text hits a meaningful share of query terms."""
    scored: list[tuple[int, int, str]] = []
    for row in rows:
        values = cast("Sequence[object]", row)
        module_id = str(values[0])
        app_slug = str(values[1]).casefold()
        haystack = " ".join(str(value).casefold() for value in values)
        score = sum(1 for term in terms if term in haystack)
        if score > 0:
            app_score = sum(1 for term in terms if term in app_slug)
            scored.append((score, app_score, module_id))
    if not scored:
        return ()
    max_score = max(score for score, _app_score, _module_id in scored)
    threshold = 1 if len(terms) == 1 else max_score
    selected = tuple(item for item in scored if item[0] >= threshold)
    max_app_score = max(app_score for _score, app_score, _module_id in selected)
    if max_app_score >= MIN_PROVIDER_TERM_SCORE_FOR_SEARCH_NARROWING:
        selected = tuple(item for item in selected if item[1] == max_app_score)
    module_ids = tuple(module_id for _score, _app_score, module_id in selected)
    return _dedupe_values(module_ids)


def _knowledge_search_clause(
    *,
    columns: tuple[str, ...],
    terms: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """Return the computed result for the caller."""
    clauses: list[str] = []
    parameters: list[str] = []
    for term in terms:
        pattern = _sql_like_pattern(term)
        term_clauses = tuple(
            f"LOWER({column}) LIKE ? ESCAPE '\\'" for column in columns
        )
        clauses.append(f"({' OR '.join(term_clauses)})")
        parameters.extend(pattern for _ in columns)
    return (" OR ".join(clauses), tuple(parameters))


def _sql_like_pattern(term: str) -> str:
    """Return an escaped LIKE pattern for one normalized search term."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _sorted_current_module_ids(
    connection: sqlite3.Connection,
    module_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return selected current module IDs in canonical module order."""
    if not module_ids:
        return ()
    return tuple(
        module.module_id
        for module in _load_modules_for_ids(connection, module_ids)
    )


def _load_modules(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeModuleFact, ...]:
    """Load current normalized module facts.

    Returns:
        Current normalized module facts.
    """
    rows = connection.execute(
        """
        SELECT
          module_id,
          app_slug,
          app_version,
          module_kind,
          internal_name,
          display_name,
          deprecated,
          fingerprint,
          adr_anchor
        FROM modules
        WHERE valid_to IS NULL
        ORDER BY app_slug, app_version, module_kind, internal_name, module_id
        """
    ).fetchall()
    return tuple(_module_fact_from_row(row) for row in rows)


def _load_modules_for_ids(
    connection: sqlite3.Connection,
    module_ids: tuple[str, ...],
) -> tuple[KnowledgeModuleFact, ...]:
    """Load current normalized module facts for selected IDs.

    Returns:
        The selected current module facts.
    """
    rows: list[object] = []
    for chunk in _chunks(module_ids):
        placeholders = _sql_placeholders(chunk)
        rows.extend(
            connection.execute(
                f"""  # noqa: S608
                SELECT
                  module_id,
                  app_slug,
                  app_version,
                  module_kind,
                  internal_name,
                  display_name,
                  deprecated,
                  fingerprint,
                  adr_anchor
                FROM modules
                WHERE valid_to IS NULL
                  AND module_id IN ({placeholders})
                """,
                chunk,
            ).fetchall()
        )
    facts = tuple(_module_fact_from_row(row) for row in rows)
    return tuple(
        sorted(
            facts,
            key=lambda module: (
                module.app_slug,
                module.app_version,
                module.module_kind,
                module.internal_name,
                module.module_id,
            ),
        )
    )


def _module_fact_from_row(row: object) -> KnowledgeModuleFact:
    """Return one module fact from a SQLite row."""
    values = cast("Sequence[object]", row)
    return KnowledgeModuleFact(
        module_id=str(values[0]),
        app_slug=str(values[1]),
        app_version=str(values[2]),
        module_kind=str(values[3]),
        internal_name=str(values[4]),
        display_name=str(values[5]),
        deprecated=bool(values[6]),
        fingerprint=str(values[7]),
        adr_anchor=str(values[8]),
    )


def _load_fields(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeFieldFact, ...]:
    """Load current normalized field facts.

    Returns:
        Current normalized field facts.
    """
    rows = connection.execute(
        """
        SELECT
          field_id,
          module_id,
          direction,
          path,
          label,
          required,
          field_type,
          fingerprint,
          adr_anchor
        FROM fields
        WHERE valid_to IS NULL
        ORDER BY module_id, direction, path, field_id
        """
    ).fetchall()
    return tuple(_field_fact_from_row(row) for row in rows)


def _load_fields_for_module_ids(
    connection: sqlite3.Connection,
    module_ids: tuple[str, ...],
) -> tuple[KnowledgeFieldFact, ...]:
    """Load current normalized field facts for selected module IDs.

    Returns:
        The selected current field facts.
    """
    rows: list[object] = []
    for chunk in _chunks(module_ids):
        placeholders = _sql_placeholders(chunk)
        rows.extend(
            connection.execute(
                f"""  # noqa: S608
                SELECT
                  field_id,
                  module_id,
                  direction,
                  path,
                  label,
                  required,
                  field_type,
                  fingerprint,
                  adr_anchor
                FROM fields
                WHERE valid_to IS NULL
                  AND module_id IN ({placeholders})
                ORDER BY module_id, direction, path, field_id
                """,
                chunk,
            ).fetchall()
        )
    facts = tuple(_field_fact_from_row(row) for row in rows)
    return tuple(
        sorted(
            facts,
            key=lambda field: (
                field.module_id,
                field.direction,
                field.path,
                field.field_id,
            ),
        )
    )


def _field_fact_from_row(row: object) -> KnowledgeFieldFact:
    """Return one field fact from a SQLite row."""
    values = cast("Sequence[object]", row)
    return KnowledgeFieldFact(
        field_id=str(values[0]),
        module_id=str(values[1]),
        direction=str(values[2]),
        path=_field_path_tuple(values[3]),
        label=str(values[4]),
        required=bool(values[5]),
        field_type=None if values[6] is None else str(values[6]),
        fingerprint=str(values[7]),
        adr_anchor=str(values[8]),
    )


def _load_constraints(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeConstraintFact, ...]:
    """Load current normalized field-constraint facts.

    Returns:
        Current normalized field-constraint facts.
    """
    rows = connection.execute(
        """
        SELECT constraint_id, field_id, constraint_key, value_json, fingerprint,
        adr_anchor
        FROM constraints
        WHERE valid_to IS NULL
        ORDER BY field_id, constraint_key, constraint_id
        """
    ).fetchall()
    return tuple(_constraint_fact_from_row(row) for row in rows)


def _load_constraints_for_field_ids(
    connection: sqlite3.Connection,
    field_ids: tuple[str, ...],
) -> tuple[KnowledgeConstraintFact, ...]:
    """Load current normalized field constraints for selected field IDs.

    Returns:
        The selected current field-constraint facts.
    """
    rows: list[object] = []
    for chunk in _chunks(field_ids):
        placeholders = _sql_placeholders(chunk)
        rows.extend(
            connection.execute(
                f"""  # noqa: S608
                SELECT constraint_id, field_id, constraint_key, value_json,
                fingerprint, adr_anchor
                FROM constraints
                WHERE valid_to IS NULL
                  AND field_id IN ({placeholders})
                ORDER BY field_id, constraint_key, constraint_id
                """,
                chunk,
            ).fetchall()
        )
    facts = tuple(_constraint_fact_from_row(row) for row in rows)
    return tuple(
        sorted(
            facts,
            key=lambda constraint: (
                constraint.field_id,
                constraint.constraint_key,
                constraint.constraint_id,
            ),
        )
    )


def _constraint_fact_from_row(row: object) -> KnowledgeConstraintFact:
    """Return one constraint fact from a SQLite row."""
    values = cast("Sequence[object]", row)
    return KnowledgeConstraintFact(
        constraint_id=str(values[0]),
        field_id=str(values[1]),
        constraint_key=str(values[2]),
        value_json=str(values[3]),
        fingerprint=str(values[4]),
        adr_anchor=str(values[5]),
    )


def _selected_structural_fingerprint(
    *,
    modules: tuple[KnowledgeModuleFact, ...],
    fields: tuple[KnowledgeFieldFact, ...],
    constraints: tuple[KnowledgeConstraintFact, ...],
) -> str:
    """Return a deterministic fingerprint for a selected structural slice."""
    return payload_fingerprint(
        normalize_json_object(
            {
                "projection": "knowledge-module-slice",
                "modules": tuple(module._asdict() for module in modules),
                "fields": tuple(field._asdict() for field in fields),
                "constraints": tuple(
                    constraint._asdict() for constraint in constraints
                ),
            }
        )
    )


def _dedupe_values(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return non-empty strings in source order without duplicates."""
    deduped: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in deduped:
            deduped.append(text)
    return tuple(deduped)


def _chunks(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Return SQLite parameter chunks for bounded IN clauses."""
    if not values:
        return ()
    return tuple(
        values[index : index + SQL_PARAMETER_CHUNK_SIZE]
        for index in range(0, len(values), SQL_PARAMETER_CHUNK_SIZE)
    )


def _sql_placeholders(values: tuple[str, ...]) -> str:
    """Return positional SQL placeholders for one non-empty value chunk."""
    return ",".join("?" for _ in values)


def _load_native_expectations(
    connection: sqlite3.Connection,
) -> tuple[KnowledgeNativeExpectation, ...]:
    """Load current Make-native/platform coverage expectations.

    Returns:
        Current Make-native/platform coverage expectations.
    """
    rows = connection.execute(
        """
        SELECT
          app_slug,
          expected_module_count,
          expected_kinds_csv,
          critical,
          fingerprint,
          adr_anchor
        FROM native_module_expectations
        WHERE valid_to IS NULL
        ORDER BY app_slug
        """
    ).fetchall()
    return tuple(
        KnowledgeNativeExpectation(
            app_slug=str(row[0]),
            expected_module_count=int(row[1]),
            expected_kinds=_csv_tuple(row[2]),
            critical=bool(row[3]),
            fingerprint=str(row[4]),
            adr_anchor=str(row[5]),
        )
        for row in rows
    )


def _iter_module_payloads(
    app_payload: JsonObject,
) -> Iterable[tuple[CatalogModuleKind, JsonObject]]:
    """Yield raw module payloads from known Make module collections.

    Raises:
        TypeError: If a module collection has an invalid shape.
    """
    for collection_key, module_kind in MODULE_COLLECTIONS:
        collection = app_payload.get(collection_key)
        if collection is None:
            continue
        if not isinstance(collection, list):
            message = (
                f"Raw spec module collection {collection_key!r} must be a list."
            )
            raise TypeError(message)
        for index, item in enumerate(cast("list[object]", collection)):
            if not isinstance(item, dict):
                message = (
                    f"Module {collection_key}[{index}] must be a JSON object."
                )
                raise TypeError(message)
            yield (
                module_kind,
                normalize_json_object(cast("Mapping[str, object]", item)),
            )


def _iter_field_payloads(
    module_payload: JsonObject,
    *,
    diagnostic_context: RawFieldDiagnosticContext,
) -> Iterable[RawFieldPayload]:
    """Yield raw field payloads from known Make field collections."""
    for collection_key, direction in FIELD_COLLECTIONS:
        collection = module_payload.get(collection_key)
        if collection is None:
            continue
        if not isinstance(collection, list):
            _append_field_diagnostic(
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.field_collection_shape_invalid",
                    field_path=(),
                    collection_path=(collection_key,),
                    message=(
                        f"Raw field collection {collection_key!r} must be a"
                        f"list."
                    ),
                ),
            )
            continue
        for index, item in enumerate(cast("list[object]", collection)):
            if not isinstance(item, dict):
                _append_field_diagnostic(
                    context=diagnostic_context,
                    issue=RawFieldIssue(
                        code="raw_spec.field_item_shape_invalid",
                        field_path=(),
                        collection_path=(collection_key, index),
                        message=(
                            f"Field {collection_key}[{index}] must be a JSON"
                            f"object."
                        ),
                    ),
                )
                continue
            yield from _iter_field_tree(
                direction=direction,
                payload=normalize_json_object(
                    cast("Mapping[str, object]", item)
                ),
                parent_path=(),
                collection_path=(collection_key, index),
                diagnostic_context=diagnostic_context,
            )


def _iter_field_tree(
    *,
    direction: CatalogFieldDirection,
    payload: JsonObject,
    parent_path: tuple[str, ...],
    collection_path: tuple[str | int, ...],
    diagnostic_context: RawFieldDiagnosticContext,
) -> Iterable[RawFieldPayload]:
    """Yield one raw field and nested raw field payloads."""
    field_name = _optional_text(payload, "name")
    if field_name is None:
        _append_field_diagnostic(
            context=diagnostic_context,
            issue=RawFieldIssue(
                code="raw_spec.field_name_missing",
                field_path=parent_path,
                collection_path=collection_path,
                message="Raw field metadata is missing a non-empty name.",
            ),
        )
        return
    current_path = (*parent_path, field_name)
    yield RawFieldPayload(
        direction=direction,
        payload=payload,
        path=current_path,
        collection_path=collection_path,
    )
    for nested_key in sorted(NESTED_FIELD_KEYS):
        nested = payload.get(nested_key)
        if nested is None:
            continue
        if not isinstance(nested, list):
            _append_field_diagnostic(
                context=diagnostic_context,
                issue=RawFieldIssue(
                    code="raw_spec.nested_field_collection_shape_invalid",
                    field_path=current_path,
                    collection_path=(*collection_path, nested_key),
                    message=(
                        f"Nested field collection {nested_key!r} under "
                        f"{'.'.join(current_path)} must be a list."
                    ),
                ),
            )
            continue
        for index, item in enumerate(cast("list[object]", nested)):
            if not isinstance(item, dict):
                _append_field_diagnostic(
                    context=diagnostic_context,
                    issue=RawFieldIssue(
                        code="raw_spec.nested_field_item_shape_invalid",
                        field_path=current_path,
                        collection_path=(*collection_path, nested_key, index),
                        message=(
                            f"Nested field {nested_key}[{index}] under "
                            f"{'.'.join(current_path)} must be a JSON object."
                        ),
                    ),
                )
                continue
            yield from _iter_field_tree(
                direction=direction,
                payload=normalize_json_object(
                    cast("Mapping[str, object]", item)
                ),
                parent_path=current_path,
                collection_path=(*collection_path, nested_key, index),
                diagnostic_context=diagnostic_context,
            )


def _append_field_diagnostic(
    *,
    context: RawFieldDiagnosticContext,
    issue: RawFieldIssue,
) -> None:
    """Record one quarantined raw-spec field metadata issue."""
    context.diagnostics.append(
        CatalogRawSpecDiagnostic(
            code=issue.code,
            severity="warning",
            module_id=context.durable_module_id,
            app_slug=context.record.app_slug,
            app_version=context.record.app_version,
            module_kind=context.module_kind,
            internal_name=context.internal_name,
            field_path=issue.field_path,
            collection_path=issue.collection_path,
            source_ref=context.record.relative_path,
            message=issue.message,
        )
    )


def _diagnostic_sort_key(
    diagnostic: CatalogRawSpecDiagnostic,
) -> tuple[str, str, str, str, tuple[str, ...], str]:
    """Return the deterministic ordering key for raw-spec diagnostics."""
    return (
        diagnostic.module_id,
        diagnostic.code,
        diagnostic.source_ref,
        ".".join(diagnostic.field_path),
        tuple(str(part) for part in diagnostic.collection_path),
        diagnostic.message,
    )


def _constraint_payloads(
    field_payload: JsonObject,
) -> tuple[tuple[str, JsonObject], ...]:
    """Return normalized constraint payloads for one raw field."""
    payloads: list[tuple[str, JsonObject]] = []
    for key in sorted(FIELD_CONSTRAINT_KEYS):
        if key not in field_payload:
            continue
        payloads.append((key, {key: field_payload[key]}))
    validate = field_payload.get("validate")
    if isinstance(validate, dict):
        validate_payload = normalize_json_object(
            cast("Mapping[str, object]", validate)
        )
        payloads.extend(
            (f"validate_{key}", {key: validate_payload[key]})
            for key in sorted(FIELD_CONSTRAINT_KEYS)
            if key in validate_payload and key not in field_payload
        )
    return tuple(payloads)


def _table_columns(
    connection: sqlite3.Connection, table: str
) -> tuple[str, ...]:
    """Return table columns in SQLite declaration order."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return tuple(str(row[1]) for row in rows)


def _dump_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> tuple[tuple[object, ...], ...]:
    """Return deterministic rows for one table."""
    if not columns:
        return ()
    column_sql = ", ".join(columns)
    order_sql = ", ".join(columns)
    rows = connection.execute(
        f"SELECT {column_sql} FROM {table} ORDER BY {order_sql}"
    ).fetchall()
    return tuple(tuple(cast("Sequence[object]", row)) for row in rows)


def _insert_sql(
    *, table: str, columns: tuple[str, ...], row: tuple[object, ...]
) -> str:
    """Return one deterministic insert statement."""
    column_sql = ", ".join(columns)
    value_sql = ", ".join(_sql_literal(value) for value in row)
    return (
        f"INSERT OR REPLACE INTO {table} ({column_sql}) VALUES ({value_sql});"
    )


def _sql_literal(value: object) -> str:
    """Return a SQLite string literal for one scalar value."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _record_payload(record: RawSpecRecord) -> JsonObject:
    """Return the fingerprint payload for one raw-spec manifest record."""
    return {
        "app_slug": record.app_slug,
        "app_version": record.app_version,
        "app_label": record.app_label,
        "latest": record.latest,
        "manifest_version": record.manifest_version,
        "relative_path": record.relative_path,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "module_count": record.module_count,
        "module_kinds": list(record.module_kinds),
    }


def _object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one required object member.

    Raises:
        TypeError: If the member is not a JSON object.
    """
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Raw spec member {key!r} must be an object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", value))


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional non-empty text member."""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _optional_bool(payload: JsonObject, key: str) -> bool:
    """Return one optional boolean raw-spec member.

    Raises:
        TypeError: If a present raw-spec member is not boolean.
    """
    value = payload.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        message = f"Raw spec member {key!r} must be boolean when present."
        raise TypeError(message)
    return value


def _canonical_json_text(payload: JsonObject) -> str:
    """Return deterministic compact JSON text for one payload."""
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _csv_tuple(value: object) -> tuple[str, ...]:
    """Return sorted text values from a comma-separated string."""
    if value is None:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _field_path_tuple(value: object) -> tuple[str, ...]:
    """Return one normalized field path from the stored path text."""
    return tuple(part for part in str(value).split(".") if part)
