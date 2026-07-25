# ruff: noqa: S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make-native infrastructure JSON evidence extraction for SQLite.

Boundary contract:
- Owns: extracting datastore and webhook setup structures from sanitized Make
AST payloads.
- Must not: call Make.com, author catalog semantic answers, or persist loose
JSON ledgers.
- Allows: redacted shape extraction and SQLite evidence synchronization for
project tooling.
- Split when: live scraper ingestion, catalog semantic planning, or customer
docs need ownership.
- Merge when: another Make adapter module writes the same evidence rows
identically.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from blueprints.ast.parser import normalize_json_object, parse_make_ast
from blueprints.ast.traversal import iter_ast_nodes
from catalog.json_payloads import (
    normalize_json_object as normalize_catalog_json_object,
)
from catalog.json_payloads import payload_fingerprint
from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH

from languages.make.raw_specs.paths import resolve_repo_relative_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoot

type MakeInfrastructureEvidenceKind = Literal[
    "datastore_structure", "webhook_structure"
]

MAKE_INFRASTRUCTURE_SCHEMA_VERSION: Final = 1
MAKE_INFRASTRUCTURE_SOURCE_KIND: Final = "make_native_json_analyzer"
MAKE_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = 2_147_483_647
MAKE_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_SECONDS: Final = (
    MAKE_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
)
RESOURCE_SLUG_FALLBACK_PREFIXES: Final[
    dict[MakeInfrastructureEvidenceKind, str]
] = {
    "datastore_structure": "datastore ",
    "webhook_structure": "webhook",
}
SECRETISH_RESOURCE_MARKERS: Final[tuple[str, ...]] = (
    "://",
    "access_token ",
    "apikey ",
    "api_key ",
    "authorization ",
    "bearer ",
    "hooks.make.com ",
    "password ",
    "private_key ",
    "refresh_token ",
    "secret ",
    "token",
)
RUNTIME_PLACEHOLDER_RE: Final = re.compile(
    r"\{\{\s*(runtime\.[A-Za-z0-9_.-]+)\s*}}"
)
SLUG_TOKEN_RE: Final = re.compile(r"[^a-z0-9_.-]+")
INFRASTRUCTURE_EVIDENCE_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS make_datastore_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  datastore_slug TEXT NOT NULL,
  structure_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_webhook_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  webhook_slug TEXT NOT NULL,
  structure_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE INDEX IF NOT EXISTS idx_make_datastore_evidence_current
  ON make_datastore_structure_evidence (app_slug, datastore_slug, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_webhook_evidence_current
  ON make_webhook_structure_evidence (app_slug, webhook_slug, valid_to);
"""


class MakeInfrastructureEvidenceRecord(NamedTuple):
    """One redacted Make-native infrastructure evidence row."""

    evidence_id: str
    evidence_kind: MakeInfrastructureEvidenceKind
    app_slug: str
    resource_slug: str
    structure_json: str
    source_kind: str
    source_ref: str
    observed_at_utc: str
    fingerprint: str


class MakeInfrastructureSyncReport(NamedTuple):
    """Summary for one SQLite infrastructure evidence sync."""

    source_of_truth: str
    sqlite_ssot_path: str
    source_kind: str
    source_ref: str
    observed_at_utc: str
    datastore_record_count: int
    webhook_record_count: int
    expired_datastore_record_count: int
    expired_webhook_record_count: int
    current_evidence_ids: tuple[str, ...]


class _NodeEvidenceInput(NamedTuple):
    evidence_kind: MakeInfrastructureEvidenceKind
    node: MakeAstNode
    source_ref: str
    observed_at_utc: str
    fields: tuple[JsonObject, ...]
    resource_value: object


class _StructurePayloadInput(NamedTuple):
    evidence_kind: MakeInfrastructureEvidenceKind
    node: MakeAstNode
    app_slug: str
    resource_slug: str
    fields: tuple[JsonObject, ...]
    resource_value: object
    source_ref: str


def extract_make_infrastructure_evidence_from_payload(
    payload: Mapping[str, object],
    *,
    source_ref: str,
    observed_at_utc: str,
) -> tuple[MakeInfrastructureEvidenceRecord, ...]:
    """Extract redacted infrastructure evidence from one Make blueprint payload.

    Returns:
        The datastore and webhook structure evidence rows found in the payload.
    """
    root = parse_make_ast(normalize_json_object(payload))
    return extract_make_infrastructure_evidence(
        root=root,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )


def extract_make_infrastructure_evidence(
    *,
    root: MakeAstRoot,
    source_ref: str,
    observed_at_utc: str,
) -> tuple[MakeInfrastructureEvidenceRecord, ...]:
    """Extract redacted datastore and webhook evidence rows from a parsed AST.

    Returns:
        Redacted SQLite-ready evidence rows.
    """
    source_ref = _required_text(source_ref, field_name="source_ref")
    observed_at_utc = _required_text(
        observed_at_utc, field_name="observed_at_utc"
    )
    records: list[MakeInfrastructureEvidenceRecord] = []
    for node in iter_ast_nodes(root):
        if _node_is_datastore(node):
            records.append(
                _infrastructure_record(
                    _NodeEvidenceInput(
                        evidence_kind="datastore_structure",
                        node=node,
                        source_ref=source_ref,
                        observed_at_utc=observed_at_utc,
                        fields=_datastore_fields(node),
                        resource_value=_node_parameter(node, "datastore"),
                    )
                )
            )
        if _node_is_webhook(node):
            records.append(
                _infrastructure_record(
                    _NodeEvidenceInput(
                        evidence_kind="webhook_structure",
                        node=node,
                        source_ref=source_ref,
                        observed_at_utc=observed_at_utc,
                        fields=_webhook_fields(node),
                        resource_value=_node_parameter(node, "hook"),
                    )
                )
            )
    return tuple(records)


def sync_make_infrastructure_evidence_for_repo(
    *,
    repo_root: Path,
    root: MakeAstRoot,
    source_ref: str,
    observed_at_utc: str | None = None,
) -> MakeInfrastructureSyncReport:
    """Synchronize infrastructure evidence into the repository SQLite SSOT.

    Returns:
        The SQLite sync report for current and expired rows.
    """
    resolved_observed_at_utc = observed_at_utc or _utc_now()
    connection = _connect_infrastructure_database(repo_root)
    try:
        with connection:
            ensure_make_infrastructure_evidence_schema(connection)
            return sync_make_infrastructure_evidence(
                connection=connection,
                root=root,
                source_ref=source_ref,
                observed_at_utc=resolved_observed_at_utc,
            )
    finally:
        connection.close()


def sync_make_infrastructure_evidence(
    *,
    connection: sqlite3.Connection,
    root: MakeAstRoot,
    source_ref: str,
    observed_at_utc: str,
) -> MakeInfrastructureSyncReport:
    """Synchronize parsed infrastructure evidence into an open SQLite.

    connection.

    Returns:
        The SQLite sync report for current and expired rows.
    """
    ensure_make_infrastructure_evidence_schema(connection)
    records = extract_make_infrastructure_evidence(
        root=root,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    datastore_ids = tuple(
        record.evidence_id
        for record in records
        if record.evidence_kind == "datastore_structure"
    )
    webhook_ids = tuple(
        record.evidence_id
        for record in records
        if record.evidence_kind == "webhook_structure"
    )
    _upsert_records(connection=connection, records=records)
    expired_datastore_count = _expire_missing_source_rows(
        connection=connection,
        table_name="make_datastore_structure_evidence",
        evidence_ids=datastore_ids,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    expired_webhook_count = _expire_missing_source_rows(
        connection=connection,
        table_name="make_webhook_structure_evidence",
        evidence_ids=webhook_ids,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    return MakeInfrastructureSyncReport(
        source_of_truth="sqlite",
        sqlite_ssot_path=DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        source_kind=MAKE_INFRASTRUCTURE_SOURCE_KIND,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
        datastore_record_count=len(datastore_ids),
        webhook_record_count=len(webhook_ids),
        expired_datastore_record_count=expired_datastore_count,
        expired_webhook_record_count=expired_webhook_count,
        current_evidence_ids=tuple(
            sorted(record.evidence_id for record in records)
        ),
    )


def ensure_make_infrastructure_evidence_schema(
    connection: sqlite3.Connection,
) -> None:
    """Ensure the SQLite SSOT has Make infrastructure evidence tables."""
    _ = connection.executescript(INFRASTRUCTURE_EVIDENCE_SCHEMA_SQL)


def _infrastructure_record(
    input_data: _NodeEvidenceInput,
) -> MakeInfrastructureEvidenceRecord:
    app_slug = _app_slug(input_data.node.module_token)
    resource_slug = _resource_slug(
        value=input_data.resource_value,
        evidence_kind=input_data.evidence_kind,
        source_ref=input_data.source_ref,
        node_id=input_data.node.node_id,
    )
    structure = _structure_payload(
        _StructurePayloadInput(
            evidence_kind=input_data.evidence_kind,
            node=input_data.node,
            app_slug=app_slug,
            resource_slug=resource_slug,
            fields=input_data.fields,
            resource_value=input_data.resource_value,
            source_ref=input_data.source_ref,
        )
    )
    structure_json = _canonical_json_text(structure)
    fingerprint = payload_fingerprint(structure)
    return MakeInfrastructureEvidenceRecord(
        evidence_id=_evidence_id(
            evidence_kind=input_data.evidence_kind,
            source_ref=input_data.source_ref,
            node_id=input_data.node.node_id,
        ),
        evidence_kind=input_data.evidence_kind,
        app_slug=app_slug,
        resource_slug=resource_slug,
        structure_json=structure_json,
        source_kind=MAKE_INFRASTRUCTURE_SOURCE_KIND,
        source_ref=input_data.source_ref,
        observed_at_utc=input_data.observed_at_utc,
        fingerprint=fingerprint,
    )


def _structure_payload(input_data: _StructurePayloadInput) -> JsonObject:
    resource_name = (
        "datastore"
        if input_data.evidence_kind == "datastore_structure"
        else "webhook"
    )
    return normalize_catalog_json_object(
        {
            "schema_version": MAKE_INFRASTRUCTURE_SCHEMA_VERSION,
            "source_of_truth": "sqlite",
            "evidence_kind": input_data.evidence_kind,
            "app_slug": input_data.app_slug,
            "resource_slug": input_data.resource_slug,
            "resource": resource_name,
            "node": {
                "node_id": input_data.node.node_id,
                "module": input_data.node.module_token,
                "kind": input_data.node.kind,
                "json_pointer": _json_pointer_from_path(
                    input_data.node.source_trace.path
                ),
            },
            "setup_flow": {
                "requires_native_make_setup": True,
                "requires_runtime_selection": True,
                "import_prompt_family": (
                    f"{resource_name}_selector_and_structure "
                ),
                "customer_facing_behavior_status": (
                    "internal_sqlite_evidence_only"
                ),
            },
            "resource_binding": _resource_binding_payload(
                input_data.resource_value
            ),
            "field_count": len(input_data.fields),
            "fields": input_data.fields,
            "source_ref": input_data.source_ref,
        }
    )


def _resource_binding_payload(value: object) -> JsonObject:
    placeholder = _runtime_placeholder(value)
    if placeholder is not None:
        return {
            "binding_source": "runtime_placeholder",
            "placeholder": placeholder,
            "raw_value_redacted": False,
        }
    if _is_meaningful_json_scalar(value):
        return {
            "binding_source": "literal_redacted",
            "placeholder": None,
            "raw_value_redacted": True,
        }
    return {
        "binding_source": "missing",
        "placeholder": None,
        "raw_value_redacted": False,
    }


def _datastore_fields(node: MakeAstNode) -> tuple[JsonObject, ...]:
    mapper = _json_object_or_empty(node.raw_payload.get("mapper"))
    data = _json_object_or_empty(mapper.get("data"))
    fields = _fields_from_mapping(data, source_path="mapper.data")
    if fields:
        return fields
    metadata = _json_object_or_empty(node.raw_payload.get("metadata"))
    return _fields_from_interface(
        metadata.get("interface"), source_path="metadata.interface"
    )


def _webhook_fields(node: MakeAstNode) -> tuple[JsonObject, ...]:
    metadata = _json_object_or_empty(node.raw_payload.get("metadata"))
    interface_fields = _fields_from_interface(
        metadata.get("interface"),
        source_path="metadata.interface",
    )
    mapper_fields = _fields_from_mapping(
        _json_object_or_empty(node.raw_payload.get("mapper")),
        source_path="mapper",
    )
    return _dedupe_fields((*interface_fields, *mapper_fields))


def _fields_from_mapping(
    mapping: JsonObject, *, source_path: str
) -> tuple[JsonObject, ...]:
    fields = [
        _field_payload(
            name=key, source_path=f"{source_path}.{key}", value=value
        )
        for key, value in sorted(mapping.items())
    ]
    return tuple(fields)


def _fields_from_interface(
    value: object, *, source_path: str
) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        return ()
    fields: list[JsonObject] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not isinstance(item, dict):
            continue
        field = normalize_catalog_json_object(
            cast("Mapping[str, object]", item)
        )
        name = _first_text(field, ("name", "key", "label"))
        if not name:
            continue
        fields.append(
            _field_payload(
                name=name,
                source_path=f"{source_path}[{index}]",
                value=field,
            )
        )
    return tuple(fields)


def _field_payload(*, name: str, source_path: str, value: object) -> JsonObject:
    return {
        "name": name,
        "source_path": source_path,
        "value_shape": _shape_label(value),
    }


def _dedupe_fields(fields: tuple[JsonObject, ...]) -> tuple[JsonObject, ...]:
    deduped: dict[str, JsonObject] = {}
    for field in fields:
        name = str(field.get("name") or "")
        if not name or name in deduped:
            continue
        deduped[name] = field
    return tuple(deduped[name] for name in sorted(deduped))


def _node_parameter(node: MakeAstNode, key: str) -> object:
    parameters = _json_object_or_empty(node.raw_payload.get("parameters"))
    return parameters.get(key)


def _node_is_datastore(node: MakeAstNode) -> bool:
    module = node.module_token.casefold()
    return node.kind == "data_store" or module.startswith("datastore:")


def _node_is_webhook(node: MakeAstNode) -> bool:
    module = node.module_token.casefold()
    return node.kind == "webhook" or module.startswith(("gateway:", "webhook:"))


def _app_slug(module_token: str) -> str:
    if ":" not in module_token:
        return "unknown"
    app_slug = module_token.split(":", 1)[0].strip().casefold()
    return _safe_slug(app_slug) or "unknown"


def _resource_slug(
    *,
    value: object,
    evidence_kind: MakeInfrastructureEvidenceKind,
    source_ref: str,
    node_id: str,
) -> str:
    placeholder = _runtime_placeholder(value)
    if placeholder is not None:
        return _safe_slug(placeholder.casefold()) or _fallback_resource_slug(
            evidence_kind=evidence_kind,
            source_ref=source_ref,
            node_id=node_id,
        )
    if isinstance(value, str) and not _looks_secretish(value):
        slug = _safe_slug(value.casefold())
        if slug:
            return slug
    return _fallback_resource_slug(
        evidence_kind=evidence_kind,
        source_ref=source_ref,
        node_id=node_id,
    )


def _fallback_resource_slug(
    *,
    evidence_kind: MakeInfrastructureEvidenceKind,
    source_ref: str,
    node_id: str,
) -> str:
    source_hash = _stable_hash(f"{source_ref}:{node_id}")[:12]
    return f"{RESOURCE_SLUG_FALLBACK_PREFIXES[evidence_kind]}-{source_hash}"


def _safe_slug(value: str) -> str:
    normalized = SLUG_TOKEN_RE.sub("-", value.strip().casefold()).strip("-_.")
    return normalized[:80].strip("-_.")


def _runtime_placeholder(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = RUNTIME_PLACEHOLDER_RE.fullmatch(value.strip())
    return match.group(1) if match is not None else None


def _looks_secretish(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in SECRETISH_RESOURCE_MARKERS)


def _shape_label(value: object) -> str:
    if value is None:
        label = "null"
    elif isinstance(value, bool):
        label = "boolean"
    elif isinstance(value, int | float):
        label = "number"
    elif isinstance(value, str):
        label = (
            "mapping_expression"
            if "{{" in value and "}}" in value
            else "string"
        )
    elif isinstance(value, dict):
        label = "object"
    elif isinstance(value, list):
        label = "array"
    else:
        label = type(value).__name__
    return label


def _json_object_or_empty(value: object) -> JsonObject:
    if not isinstance(value, dict):
        return {}
    return normalize_catalog_json_object(cast("Mapping[str, object]", value))


def _first_text(mapping: Mapping[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if _is_meaningful_json_scalar(value):
            return str(value).strip()
    return ""


def _is_meaningful_json_scalar(value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, str | int | float) and bool(str(value).strip())


def _evidence_id(
    *,
    evidence_kind: MakeInfrastructureEvidenceKind,
    source_ref: str,
    node_id: str,
) -> str:
    source_hash = _stable_hash(source_ref)[:12]
    node_hash = _stable_hash(node_id)[:12]
    return f"make-native-json:{evidence_kind}:{source_hash}:{node_hash}"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_text(payload: JsonObject) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _json_pointer_from_path(path: Sequence[object]) -> str:
    pointer = "".join(f"/{_json_pointer_part(part)}" for part in path)
    return pointer or "/"


def _json_pointer_part(part: object) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _upsert_records(
    *,
    connection: sqlite3.Connection,
    records: tuple[MakeInfrastructureEvidenceRecord, ...],
) -> None:
    for record in records:
        if record.evidence_kind == "datastore_structure":
            _upsert_datastore_record(connection=connection, record=record)
        else:
            _upsert_webhook_record(connection=connection, record=record)


def _upsert_datastore_record(
    *,
    connection: sqlite3.Connection,
    record: MakeInfrastructureEvidenceRecord,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO make_datastore_structure_evidence (
          evidence_id, app_slug, datastore_slug, structure_json, source_kind,
          source_ref,
          observed_at_utc, fingerprint, valid_from, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(evidence_id) DO UPDATE SET
          app_slug = excluded.app_slug,
          datastore_slug = excluded.datastore_slug,
          structure_json = excluded.structure_json,
          source_kind = excluded.source_kind,
          source_ref = excluded.source_ref,
          observed_at_utc = excluded.observed_at_utc,
          fingerprint = excluded.fingerprint,
          valid_from = excluded.valid_from,
          valid_to = NULL
        """,
        (
            record.evidence_id,
            record.app_slug,
            record.resource_slug,
            record.structure_json,
            record.source_kind,
            record.source_ref,
            record.observed_at_utc,
            record.fingerprint,
            record.observed_at_utc,
        ),
    )


def _upsert_webhook_record(
    *,
    connection: sqlite3.Connection,
    record: MakeInfrastructureEvidenceRecord,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO make_webhook_structure_evidence (
          evidence_id, app_slug, webhook_slug, structure_json, source_kind,
          source_ref,
          observed_at_utc, fingerprint, valid_from, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(evidence_id) DO UPDATE SET
          app_slug = excluded.app_slug,
          webhook_slug = excluded.webhook_slug,
          structure_json = excluded.structure_json,
          source_kind = excluded.source_kind,
          source_ref = excluded.source_ref,
          observed_at_utc = excluded.observed_at_utc,
          fingerprint = excluded.fingerprint,
          valid_from = excluded.valid_from,
          valid_to = NULL
        """,
        (
            record.evidence_id,
            record.app_slug,
            record.resource_slug,
            record.structure_json,
            record.source_kind,
            record.source_ref,
            record.observed_at_utc,
            record.fingerprint,
            record.observed_at_utc,
        ),
    )


def _expire_missing_source_rows(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    evidence_ids: tuple[str, ...],
    source_ref: str,
    observed_at_utc: str,
) -> int:
    rows = cast(
        "list[tuple[str]]",
        connection.execute(
            f"""  # noqa: S608
            SELECT evidence_id
            FROM {table_name}
            WHERE source_kind = ?
              AND source_ref = ?
              AND valid_to IS NULL
            """,
            (MAKE_INFRASTRUCTURE_SOURCE_KIND, source_ref),
        ).fetchall(),
    )
    current_ids = frozenset(evidence_ids)
    stale_ids = tuple(row[0] for row in rows if row[0] not in current_ids)
    if not stale_ids:
        return 0
    _ = connection.executemany(
        f"UPDATE {table_name} SET valid_to = ? WHERE evidence_id = ?",
        ((observed_at_utc, evidence_id) for evidence_id in stale_ids),
    )
    return len(stale_ids)


def _connect_infrastructure_database(repo_root: Path) -> sqlite3.Connection:
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        database_path,
        timeout=MAKE_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_SECONDS,
    )
    _ = connection.execute(
        f"PRAGMA busy_timeout = "
        f"{MAKE_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
    )
    _ = connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _required_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise ValueError(message)
    return text


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
