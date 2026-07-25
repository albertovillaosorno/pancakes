# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.tool-annotation-posture
# - repo.catalog-plan-artifact.workspace-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Inactive catalog-plan worker loop implementation kept for future utility.

Boundary contract:
- Owns: retained historical ChatGPT.com catalog unit read/save orchestration
code.
- Must not: be imported by the active MCP executor or registered as a tool
alias.
- Allows: future reactivation research without rewriting the old SQLite worker
loop.
- Split when: catalog worker scheduling needs an independent service boundary.
- Merge when: a future approved catalog worker service reclaims this
implementation.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.knowledge.catalog_plan_ssot import (
    CATALOG_PLAN_SEMANTIC_ANSWER_STATUS,
    INSUFFICIENT_EVIDENCE_MARKERS,
    connect_catalog_plan_ssot,
)
from catalog.knowledge.models import DEFAULT_KNOWLEDGE_DB_PATH
from languages.make.raw_specs.parser import MODULE_COLLECTIONS
from languages.make.raw_specs.paths import DEFAULT_RAW_SPEC_SQLITE_DATABASE
from languages.make.raw_specs.sqlite_store import (
    RAW_SPEC_SQLITE_MANIFEST_PATH,
    load_sqlite_raw_spec_bundle,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping
    from pathlib import Path

    from mcp.models import JsonObject

MAX_WRITE_BYTES: Final[int] = 262_144
QUARANTINED_UNIT_STATUS: Final[str] = "quarantined"
CATALOG_SAVE_TOOL_NAME: Final[str] = "catalog.save_unit"
CATALOG_NEXT_TOOL_NAME: Final[str] = "catalog.next_unit"
CATALOG_WORKER_SOURCE_KIND: Final[str] = "mcp_catalog_worker"
UNIT_ID_WIDTH: Final[int] = 6
RAW_APP_VERSION_SURFACE: Final[str] = "raw Make app-version specs"
MAX_EVIDENCE_MODULES: Final[int] = 12
MAX_CANDIDATE_MODULE_IDS: Final[int] = 32
MAX_EVIDENCE_FIELDS_PER_MODULE: Final[int] = 12
MAX_EVIDENCE_SELECT_OPTIONS: Final[int] = 8
MAX_EVIDENCE_TEXT_CHARS: Final[int] = 500
MAX_QUARANTINE_PRIORITY: Final[int] = 100


class CatalogUnitSave(NamedTuple):
    """Validated catalog checkpoint payload ready for one SQLite transaction."""

    unit_id: str
    unit_number: int
    answer: JsonObject
    normalized_json: str
    byte_count: int
    answer_sha256: str
    is_quarantine: bool
    saved_status: str
    source_ref: str
    event_json: str
    updated_at_utc: str


def catalog_plan_next_unit(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Return the highest-priority pending catalog-plan semantic unit from.

    SQLite.

    The cursor does not move here. A unit advances only after
    :func:`catalog_plan_save_semantic_unit` writes its answer.

    Returns:
        JSON-ready one-unit work packet.
    """
    _reject_arguments(arguments, tool_name=CATALOG_NEXT_TOOL_NAME)
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        row = cast(
            "sqlite3.Row | None",
            connection.execute(
                """
                SELECT
                    units.unit_number,
                    units.surface,
                    units.evidence_path,
                    ranges.range_label,
                    ranges.range_start,
                    ranges.range_end,
                    COALESCE(MAX(quarantine.priority), 0) AS retry_priority
                FROM catalog_plan_units AS units
                LEFT JOIN catalog_plan_ranges AS ranges ON ranges.range_id =
                units.range_id
                LEFT JOIN catalog_plan_quarantine_records AS quarantine
                  ON quarantine.unit_number = units.unit_number
                 AND quarantine.status = 'needs_retry'
                WHERE units.status = 'pending'
                  AND units.valid_to IS NULL
                  AND ranges.valid_to IS NULL
                GROUP BY
                    units.unit_number,
                    units.surface,
                    units.evidence_path,
                    ranges.range_label,
                    ranges.range_start,
                    ranges.range_end
                ORDER BY retry_priority DESC, units.unit_number
                LIMIT 1
                """
            ).fetchone(),
        )
        if row is None:
            return {
                "status": "complete ",
                "response_contract": "catalog_plan.semantic_next_unit.v1",
                "sqlite_ssot_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
                "message": "No pending catalog-plan semantic units remain.",
                "development_only": True,
                "semantic_worker": "ChatGPT.com",
                "codex_catalog_authoring_allowed": False,
                "live_make_called": False,
                "provider_api_call": False,
                "credential_value_transfer": False,
                "secret_output": False,
            }

        unit_number = _row_int(row, "unit_number")
        unit_id = _unit_id_text(unit_number)
        surface = _row_text(row, "surface")
        range_label = _row_text(row, "range_label")
        ledger_snapshot = _sqlite_ledger_snapshot(
            connection, range_label=range_label
        )
        raw_catalog_evidence = _raw_catalog_evidence(
            repo_root=repo_root,
            row=row,
            unit_id=unit_id,
            surface=surface,
        )
    return {
        "status": "ok ",
        "response_contract": "catalog_plan.semantic_next_unit.v1",
        "sqlite_ssot_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "unit_id": unit_id,
        "unit_number": unit_number,
        "surface": surface,
        "range_label": range_label,
        "range_start": _row_int(row, "range_start"),
        "range_end": _row_int(row, "range_end"),
        "retry_priority": _row_int(row, "retry_priority"),
        "ledger": ledger_snapshot,
        "question": (
            f"Map catalog.next_unit semantic unit {unit_id} from surface "
            f"{surface!r} "
            "into one compact semantic graph answer."
        ),
        "raw_catalog_evidence": {
            "unit_id": unit_id,
            "unit_number": unit_number,
            "surface": surface,
            "range_label": range_label,
            "evidence_path": _row_text(row, "evidence_path"),
            "ledger": ledger_snapshot,
            **raw_catalog_evidence,
        },
        "candidate_module_ids": raw_catalog_evidence.get(
            "candidate_module_ids", []
        ),
        "answer_ref": _semantic_answer_source_ref(unit_id),
        "advance_rule": (
            "This unit remains the next unit until catalog.save_unit records "
            "this exact "
            "pending unit_id."
        ),
        "development_only": True,
        "semantic_worker": "ChatGPT.com",
        "codex_catalog_authoring_allowed": False,
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _raw_catalog_evidence(
    *,
    repo_root: Path,
    row: sqlite3.Row,
    unit_id: str,
    surface: str,
) -> JsonObject:
    """Return bounded local catalog evidence for one semantic unit.

    Returns:
        JSON-ready evidence sourced from local repository files.
    """
    if surface == RAW_APP_VERSION_SURFACE:
        return _raw_app_version_evidence(
            repo_root=repo_root,
            row=row,
            unit_id=unit_id,
        )
    return {
        "evidence_status": "ledger_only ",
        "evidence_kind": "progress_ledger_unit",
        "message": (
            "No unit-specific evidence resolver exists for this surface yet; "
            "save a quarantine answer rather than inventing catalog facts."
        ),
        "candidate_module_ids": [],
    }


def _raw_app_version_evidence(
    *,
    repo_root: Path,
    row: sqlite3.Row,
    unit_id: str,
) -> JsonObject:
    """Return one bounded Make raw app-version spec summary.

    Returns:
        JSON-ready app-version evidence.
    """
    bundle = load_sqlite_raw_spec_bundle(
        database_path=repo_root / DEFAULT_RAW_SPEC_SQLITE_DATABASE
    )
    if bundle is None:
        return _missing_source_evidence(
            message="SQLite raw-spec manifest rows are unavailable.",
            missing_path=RAW_SPEC_SQLITE_MANIFEST_PATH,
        )
    records = bundle.manifest.records
    range_label = _row_text(row, "range_label")
    unit_number = _row_int(row, "unit_number")
    record_index = unit_number - _row_int(row, "range_start")
    if record_index < 0 or record_index >= len(records):
        return {
            "evidence_status": "missing_catalog_record ",
            "evidence_kind": "raw_make_app_version_spec",
            "record_index": record_index + 1,
            "record_count": len(records),
            "manifest_path": RAW_SPEC_SQLITE_MANIFEST_PATH,
            "message": (
                f"Ledger unit {unit_id} in {range_label} has no matching "
                f"raw-spec "
                "manifest record."
            ),
            "candidate_module_ids": [],
        }

    record = records[record_index]
    raw_spec = bundle.payloads_by_ref.get(record.relative_path)
    if raw_spec is None:
        return _missing_source_evidence(
            message="SQLite raw-spec payload row is unavailable.",
            missing_path=record.relative_path,
        )
    app = _json_object_member(raw_spec, "app")
    app_slug = record.app_slug
    app_version = record.app_version
    operation_summaries = _operation_summaries(
        app, app_slug=app_slug, app_version=app_version
    )
    candidate_module_ids = [
        str(summary["module_id"])
        for summary in operation_summaries[:MAX_CANDIDATE_MODULE_IDS]
    ]
    return {
        "evidence_status": "sqlite_raw_spec_manifest ",
        "evidence_kind": "raw_make_app_version_spec",
        "record_index": record_index + 1,
        "record_count": len(records),
        "manifest_path": RAW_SPEC_SQLITE_MANIFEST_PATH,
        "spec_path": record.relative_path,
        "app_slug": app_slug,
        "app_label": record.app_label or app_slug,
        "app_version": app_version,
        "latest": record.latest,
        "manifest_version": record.manifest_version,
        "module_count": record.module_count,
        "module_kinds": record.module_kinds,
        "source_metadata": dict(record.source_metadata._asdict()),
        "operation_summaries": operation_summaries[:MAX_EVIDENCE_MODULES],
        "operation_summary_limit": MAX_EVIDENCE_MODULES,
        "candidate_module_ids": candidate_module_ids,
        "semantic_work": (
            "Map this app-version into provider/app-family aliases, module "
            "role "
            "nodes, "
            "setup dependencies, useful upstream/downstream workflow edges, "
            "and "
            "quarantine "
            "any weak assumptions."
        ),
    }


def _missing_source_evidence(*, message: str, missing_path: str) -> JsonObject:
    return {
        "evidence_status": "source_unavailable ",
        "evidence_kind": "raw_make_app_version_spec",
        "missing_path": missing_path,
        "message": message,
        "candidate_module_ids": [],
    }


def _operation_summaries(
    app: JsonObject, *, app_slug: str, app_version: str
) -> list[JsonObject]:
    summaries: list[JsonObject] = []
    for collection_key, module_kind in MODULE_COLLECTIONS:
        collection = app.get(collection_key)
        if not isinstance(collection, list):
            continue
        for item in cast("list[object]", collection):
            if not isinstance(item, dict):
                continue
            module = _json_object_from_mapping(
                cast("Mapping[object, object]", item)
            )
            internal_name = _optional_json_text(module, "name")
            if internal_name is None:
                continue
            display_name = _optional_json_text(module, "label") or internal_name
            module_id = (
                f"module:{app_slug}:{app_version}:{module_kind}:{internal_name}"
            )
            summaries.append(
                {
                    "module_id": module_id,
                    "collection": collection_key,
                    "module_kind": module_kind,
                    "internal_name": internal_name,
                    "display_name": display_name,
                    "description": _bounded_optional_text(
                        module, "description"
                    ),
                    "crud": _optional_json_text(module, "crud"),
                    "fields": _module_field_summaries(module),
                }
            )
    return summaries


def _module_field_summaries(module: JsonObject) -> list[JsonObject]:
    fields: list[JsonObject] = []
    for section in ("parameters", "expect", "interface"):
        value = module.get(section)
        if isinstance(value, list):
            _extend_field_summaries(
                fields,
                section=section,
                path=section,
                items=cast("list[object]", value),
            )
        if len(fields) >= MAX_EVIDENCE_FIELDS_PER_MODULE:
            break
    return fields[:MAX_EVIDENCE_FIELDS_PER_MODULE]


def _extend_field_summaries(
    fields: list[JsonObject], *, section: str, path: str, items: list[object]
) -> None:
    for item in items:
        if len(fields) >= MAX_EVIDENCE_FIELDS_PER_MODULE:
            return
        if not isinstance(item, dict):
            continue
        field = _json_object_from_mapping(cast("Mapping[object, object]", item))
        field_name = _optional_json_text(field, "name")
        field_path = f"{path}.{field_name}" if field_name is not None else path
        fields.append(_field_summary(field, section=section, path=field_path))
        options = field.get("options")
        if isinstance(options, dict):
            nested = _json_object_from_mapping(
                cast("Mapping[object, object]", options)
            ).get("nested")
            if isinstance(nested, dict):
                store = _json_object_from_mapping(
                    cast("Mapping[object, object]", nested)
                ).get("store")
                if isinstance(store, list):
                    _extend_field_summaries(
                        fields,
                        section=section,
                        path=f"{field_path}.options.nested",
                        items=cast("list[object]", store),
                    )


def _field_summary(field: JsonObject, *, section: str, path: str) -> JsonObject:
    summary: JsonObject = {
        "section": section,
        "path": path,
        "name": _optional_json_text(field, "name"),
        "label": _optional_json_text(field, "label"),
        "type": _optional_json_text(field, "type"),
        "required": _optional_json_bool(field, "required"),
        "advanced": _optional_json_bool(field, "advanced"),
    }
    options = field.get("options")
    if isinstance(options, str):
        summary["option_source"] = _bound_text(options)
    elif isinstance(options, list):
        summary["select_options"] = _select_option_summaries(
            cast("list[object]", options)
        )
    elif isinstance(options, dict):
        summary["options_kind"] = "object"
    return summary


def _select_option_summaries(items: list[object]) -> list[JsonObject]:
    summaries: list[JsonObject] = []
    for item in items:
        if len(summaries) >= MAX_EVIDENCE_SELECT_OPTIONS:
            break
        if isinstance(item, dict):
            option = _json_object_from_mapping(
                cast("Mapping[object, object]", item)
            )
            summaries.append(
                {
                    "label": _optional_json_text(option, "label"),
                    "value": _optional_json_text(option, "value")
                    or _optional_json_text(option, "name"),
                }
            )
        elif isinstance(item, str):
            summaries.append({"value": _bound_text(item)})
    return summaries


def catalog_plan_save_semantic_unit(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Persist one semantic unit answer or quarantine record in SQLite.

    Returns:
        JSON-ready write receipt.
    """
    save = _catalog_unit_save(arguments)
    with (
        closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection,
        connection,
    ):
        _assert_pending_unit(connection=connection, save=save)
        if save.is_quarantine:
            _insert_structured_quarantine(connection=connection, save=save)
        else:
            _insert_semantic_answer(connection=connection, save=save)
        _update_unit_after_save(connection=connection, save=save)
        _ = connection.execute(
            """
            INSERT OR REPLACE INTO catalog_plan_progress_events (
              event_id, legacy_event_id, unit_number, event_type, event_json,
              created_at_utc,
              source_kind, source_ref, fingerprint
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(
                    "catalog-plan-event", save.unit_id, save.answer_sha256
                ),
                save.unit_number,
                "semantic_unit_saved",
                save.event_json,
                save.updated_at_utc,
                CATALOG_WORKER_SOURCE_KIND,
                save.source_ref,
                _sha256_text(save.event_json),
            ),
        )
        next_row = cast(
            "sqlite3.Row | None",
            connection.execute(
                """
                SELECT unit_number
                FROM catalog_plan_units
                WHERE status = 'pending'
                  AND valid_to IS NULL
                ORDER BY unit_number
                LIMIT 1
                """
            ).fetchone(),
        )
        completed_units = _completed_unit_count(connection)

    next_unit_id = (
        _unit_id_text(_row_int(next_row, "unit_number"))
        if next_row is not None
        else None
    )
    return {
        "status": "saved ",
        "response_contract": "catalog_plan.semantic_unit_save.v1",
        "sqlite_ssot_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "unit_id": save.unit_id,
        "unit_number": save.unit_number,
        "source_ref": save.source_ref,
        "bytes_written": save.byte_count,
        "chars_written": len(save.normalized_json),
        "line_count": _line_count(save.normalized_json),
        "ledger_status": save.saved_status,
        "ledger_kind": "sqlite_ssot",
        "ledger_completed_units": completed_units,
        "next_unit_id": next_unit_id,
        "structured_quarantine": save.is_quarantine,
        "advance_rule": (
            "The SQLite ledger advanced because this unit save committed."
        ),
        "development_only": True,
        "semantic_worker": "ChatGPT.com",
        "codex_catalog_authoring_allowed": False,
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _sqlite_ledger_snapshot(
    connection: sqlite3.Connection, *, range_label: str
) -> JsonObject:
    return {
        "ledger_kind": "sqlite_ssot",
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "completed_units": _completed_unit_count(connection),
        "total_units": _total_unit_count(connection),
        "current_range": _sqlite_range_snapshot(
            connection, range_label=range_label
        ),
    }


def _sqlite_range_snapshot(
    connection: sqlite3.Connection, *, range_label: str
) -> JsonObject | None:
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT range_label, surface, status, range_start, range_end
            FROM catalog_plan_ranges
            WHERE range_label = ? AND valid_to IS NULL
            """,
            (range_label,),
        ).fetchone(),
    )
    if row is None:
        return None
    return {
        "range": _row_text(row, "range_label"),
        "surface": _row_text(row, "surface"),
        "status": _row_text(row, "status"),
        "range_start": _row_int(row, "range_start"),
        "range_end": _row_int(row, "range_end"),
    }


def _semantic_answer_source_ref(unit_id: str) -> str:
    return f"sqlite:catalog_plan_semantic_answers/{unit_id}"


def _quarantine_source_ref(unit_id: str, answer_sha256: str) -> str:
    return (
        f"sqlite:catalog_plan_quarantine_records/{unit_id}/{answer_sha256[:16]}"
    )


def _event_json(
    *,
    unit_id: str,
    answer_sha256: str,
    source_ref: str,
    status: str,
    updated_at: str,
) -> str:
    return json.dumps(
        {
            "unit_id": unit_id,
            "answer_sha256": answer_sha256,
            "source_ref": source_ref,
            "status": status,
            "saved_by_tool": CATALOG_SAVE_TOOL_NAME,
            "updated_at_utc": updated_at,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _catalog_unit_save(arguments: Mapping[str, object]) -> CatalogUnitSave:
    unit_id = _required_unit_id(arguments)
    unit_number = _unit_number_from_id(unit_id)
    answer = _required_json_object(arguments, "answer_json")
    if answer.get("unit_id") != unit_id:
        message = "answer_json.unit_id must match unit_id exactly."
        raise ValueError(message)
    normalized = json.dumps(answer, indent=2, sort_keys=True) + "\n"
    encoded = normalized.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        message = (
            f"Catalog plan semantic answer writes are capped at"
            f"{MAX_WRITE_BYTES} bytes."
        )
        raise ValueError(message)
    placeholder_phrases = _placeholder_phrases(normalized)
    if placeholder_phrases:
        marker_list = ", ".join(placeholder_phrases)
        message = (
            "catalog.save_unit rejects bare insufficient-evidence "
            "placeholders. "
            ""
            "Use a structured quarantine checkpoint with typed evidence gaps, "
            f"not these phrases: {marker_list}."
        )
        raise ValueError(message)
    updated_at = _utc_now()
    answer_sha256 = _sha256_text(normalized)
    is_quarantine = _is_structured_quarantine_answer(answer)
    saved_status = (
        QUARANTINED_UNIT_STATUS
        if is_quarantine
        else CATALOG_PLAN_SEMANTIC_ANSWER_STATUS
    )
    source_ref = (
        _quarantine_source_ref(unit_id, answer_sha256)
        if is_quarantine
        else _semantic_answer_source_ref(unit_id)
    )
    return CatalogUnitSave(
        unit_id=unit_id,
        unit_number=unit_number,
        answer=answer,
        normalized_json=normalized,
        byte_count=len(encoded),
        answer_sha256=answer_sha256,
        is_quarantine=is_quarantine,
        saved_status=saved_status,
        source_ref=source_ref,
        event_json=_event_json(
            unit_id=unit_id,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            status=saved_status,
            updated_at=updated_at,
        ),
        updated_at_utc=updated_at,
    )


def _assert_pending_unit(
    *, connection: sqlite3.Connection, save: CatalogUnitSave
) -> None:
    existing = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT status
            FROM catalog_plan_units
            WHERE unit_number = ? AND valid_to IS NULL
            """,
            (save.unit_number,),
        ).fetchone(),
    )
    if existing is None:
        message = f"Catalog plan progress unit does not exist: {save.unit_id}"
        raise ValueError(message)
    existing_status = _row_text(existing, "status")
    if existing_status != "pending":
        message = (
            f"Catalog plan unit {save.unit_id} is {existing_status!r}; "
            "catalog.save_unit only accepts pending units."
        )
        raise ValueError(message)


def _insert_semantic_answer(
    *,
    connection: sqlite3.Connection,
    save: CatalogUnitSave,
) -> None:
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO catalog_plan_semantic_answers (
          unit_number, unit_id, answer_json, answer_sha256, answer_status,
          evidence_status,
          source_kind, source_ref, created_at_utc, saved_by_tool, valid_to
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            save.unit_number,
            save.unit_id,
            save.normalized_json,
            save.answer_sha256,
            CATALOG_PLAN_SEMANTIC_ANSWER_STATUS,
            "evidence_present",
            CATALOG_WORKER_SOURCE_KIND,
            save.source_ref,
            save.updated_at_utc,
            CATALOG_SAVE_TOOL_NAME,
        ),
    )


def _insert_structured_quarantine(
    *,
    connection: sqlite3.Connection,
    save: CatalogUnitSave,
) -> None:
    quarantine_items = _structured_quarantine_items(save.answer)
    evidence_pointers = _required_non_empty_text_list(
        save.answer, "evidence_pointers"
    )
    priority = _quarantine_priority(save.answer)
    reason = _bounded_joined_reasons(quarantine_items)
    evidence_gap_json = json.dumps(
        {
            "answer_sha256": save.answer_sha256,
            "evidence_pointers": evidence_pointers,
            "quarantine": quarantine_items,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    retry_policy_json = json.dumps(
        {
            "manual_codex_cataloging_allowed": False,
            "retry_worker": "ChatGPT.com ",
            "retry_tool_flow": "catalog.next_unit -> catalog.save_unit",
            "retry_priority": priority,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO catalog_plan_quarantine_records (
          quarantine_id, unit_number, unit_id, quarantine_kind, reason,
          evidence_gap_json,
          retry_policy_json, priority, source_kind, source_ref, status,
          created_at_utc,
          resolved_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            _stable_id(
                "catalog-plan-quarantine", save.unit_id, save.answer_sha256
            ),
            save.unit_number,
            save.unit_id,
            "semantic_worker_save",
            reason,
            evidence_gap_json,
            retry_policy_json,
            priority,
            CATALOG_WORKER_SOURCE_KIND,
            save.source_ref,
            "needs_retry",
            save.updated_at_utc,
        ),
    )


def _update_unit_after_save(
    *,
    connection: sqlite3.Connection,
    save: CatalogUnitSave,
) -> None:
    _ = connection.execute(
        """
        UPDATE catalog_plan_units
        SET status = ?, evidence_path = ?, semantic_answer_sha256 = ?,
        updated_at_utc = ?
        WHERE unit_number = ? AND valid_to IS NULL
        """,
        (
            save.saved_status,
            save.source_ref,
            save.answer_sha256,
            save.updated_at_utc,
            save.unit_number,
        ),
    )


def _completed_unit_count(connection: sqlite3.Connection) -> int:
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT COUNT(*) AS completed_units
            FROM catalog_plan_units
            WHERE status IN (?, ?)
              AND valid_to IS NULL
            """,
            (CATALOG_PLAN_SEMANTIC_ANSWER_STATUS, QUARANTINED_UNIT_STATUS),
        ).fetchone(),
    )
    if row is None:
        return 0
    return _row_int(row, "completed_units")


def _total_unit_count(connection: sqlite3.Connection) -> int:
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT COUNT(*) AS total_units
            FROM catalog_plan_units
            WHERE valid_to IS NULL
            """
        ).fetchone(),
    )
    if row is None:
        return 0
    return _row_int(row, "total_units")


def _is_structured_quarantine_answer(answer: JsonObject) -> bool:
    status = _optional_json_text(answer, "status")
    return status in {"quarantine", "quarantined", "needs_retry"}


def _structured_quarantine_items(answer: JsonObject) -> list[JsonObject]:
    raw_items = answer.get("quarantine")
    if not isinstance(raw_items, list) or not raw_items:
        message = (
            "Structured quarantine saves require a non-empty quarantine array."
        )
        raise ValueError(message)
    items: list[JsonObject] = []
    for item in cast("list[object]", raw_items):
        if not isinstance(item, dict):
            message = "Each quarantine item must be a JSON object."
            raise TypeError(message)
        normalized = _json_object_from_mapping(
            cast("Mapping[object, object]", item)
        )
        reason = _optional_json_text(normalized, "reason")
        gap_type = _optional_json_text(normalized, "gap_type")
        if reason is None or gap_type is None:
            message = "Each quarantine item requires reason and gap_type text."
            raise ValueError(message)
        items.append(normalized)
    return items


def _required_non_empty_text_list(answer: JsonObject, key: str) -> list[str]:
    value = answer.get(key)
    if not isinstance(value, list):
        message = (
            f"Structured quarantine saves require {key} as a non-empty text "
            f"array."
        )
        raise TypeError(message)
    items = [
        item.strip()
        for item in cast("list[object]", value)
        if isinstance(item, str)
    ]
    if not items:
        message = (
            f"Structured quarantine saves require {key} as a non-empty text "
            f"array."
        )
        raise ValueError(message)
    return items


def _quarantine_priority(answer: JsonObject) -> int:
    value = answer.get("retry_priority")
    if isinstance(value, bool) or not isinstance(value, int):
        message = "Structured quarantine saves require integer retry_priority."
        raise TypeError(message)
    if value < 1 or value > MAX_QUARANTINE_PRIORITY:
        message = (
            f"retry_priority must be between 1 and {MAX_QUARANTINE_PRIORITY}."
        )
        raise ValueError(message)
    return value


def _bounded_joined_reasons(items: list[JsonObject]) -> str:
    reasons = [
        _optional_json_text(item, "reason")
        or "unspecified catalog evidence gap"
        for item in items
    ]
    return _bound_text("; ".join(reasons))


def _placeholder_phrases(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    return tuple(
        marker
        for marker in INSUFFICIENT_EVIDENCE_MARKERS
        if marker in normalized
    )


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = cast("object", row[key])
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    message = f"Catalog plan progress column {key} must be an integer."
    raise TypeError(message)


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = cast("object", row[key])
    if value is None:
        return ""
    return str(value)


def _required_text(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        message = f"{name} is required."
        raise ValueError(message)
    return value


def _required_unit_id(arguments: Mapping[str, object]) -> str:
    unit_id = _required_text(arguments, "unit_id")
    _ = _unit_number_from_id(unit_id)
    return unit_id


def _unit_number_from_id(unit_id: str) -> int:
    if len(unit_id) != UNIT_ID_WIDTH or not unit_id.isdecimal():
        message = "unit_id must be a six-digit catalog-plan unit id."
        raise ValueError(message)
    return int(unit_id)


def _unit_id_text(unit_number: int) -> str:
    return f"{unit_number:06d}"


def _required_json_object(
    arguments: Mapping[str, object], name: str
) -> JsonObject:
    value = arguments.get(name)
    if isinstance(value, dict):
        return _json_object_from_mapping(cast("Mapping[object, object]", value))
    if not isinstance(value, str) or not value.strip():
        message = f"{name} is required."
        raise ValueError(message)
    parsed = cast("object", json.loads(value))
    if not isinstance(parsed, dict):
        message = f"{name} must be a JSON object."
        raise TypeError(message)
    return cast("JsonObject", parsed)


def _reject_arguments(
    arguments: Mapping[str, object], *, tool_name: str
) -> None:
    if arguments:
        message = f"{tool_name} does not accept arguments."
        raise ValueError(message)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _line_count(content: str) -> int:
    if not content:
        return 0
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def _json_object_from_mapping(mapping: Mapping[object, object]) -> JsonObject:
    return {str(key): value for key, value in mapping.items()}


def _json_object_member(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"JSON member {key!r} must be an object."
        raise TypeError(message)
    return _json_object_from_mapping(cast("Mapping[object, object]", value))


def _optional_json_text(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _bounded_optional_text(payload: JsonObject, key: str) -> str | None:
    value = _optional_json_text(payload, key)
    return _bound_text(value) if value is not None else None


def _optional_json_bool(payload: JsonObject, key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


def _bound_text(value: str) -> str:
    normalized = " ".join(value.split())
    return (
        normalized
        if len(normalized) <= MAX_EVIDENCE_TEXT_CHARS
        else f"{normalized[:MAX_EVIDENCE_TEXT_CHARS]} [truncated]"
    )


def _stable_id(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    return _sha256_text(payload)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
