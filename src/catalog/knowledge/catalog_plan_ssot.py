# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - repo.catalog-plan-artifact.workspace-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Catalog-plan SSOT helpers for the Make knowledge SQLite database.

Boundary contract:
- Owns: SQLite runtime connection policy and non-semantic legacy artifact
intake.
- Must not: author catalog answers, call providers, mutate live Make accounts,
or store secrets.
- Allows: importing existing progress rows and ChatGPT.com answer JSON into
SQLite.
- Split when: MCP tool orchestration or Windows service scheduling needs
separate ownership.
- Merge when: another module owns the same catalog-plan SQLite intake behavior.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.paths import resolve_repo_relative_path

from catalog.knowledge.models import DEFAULT_KNOWLEDGE_DB_PATH

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

CATALOG_PLAN_SEMANTIC_ANSWER_STATUS: Final = "semantic_answered"
DEFAULT_CATALOG_PLAN_SOURCE_REF: Final = "legacy:catalog_plan_artifact"
CATALOG_PLAN_SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = 2_147_483_647
CATALOG_PLAN_SQLITE_BUSY_TIMEOUT_SECONDS: Final = (
    CATALOG_PLAN_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
)
CATALOG_PLAN_SQLITE_WRITE_RETRIES: Final = 4
CATALOG_PLAN_SQLITE_RETRY_BASE_DELAY_SECONDS: Final = 0.1
UNIT_ID_WIDTH: Final = 6
ANSWER_FILE_SUFFIX: Final = ".answer.json"
INSUFFICIENT_EVIDENCE_MARKERS: Final[tuple[str, ...]] = (
    "no sufficient evidence ",
    "insufficient evidence",
)


class CatalogPlanMigrationReport(NamedTuple):
    """Summary for one legacy catalog-plan artifact import into SQLite."""

    metadata_count: int
    range_count: int
    unit_count: int
    progress_event_count: int
    semantic_answer_count: int
    quarantined_answer_count: int


class CatalogPlanPlaceholderCleanupReport(NamedTuple):
    """Summary for one placeholder cleanup pass over semantic answer files."""

    scanned_answer_count: int
    migrated_answer_count: int
    quarantined_answer_count: int
    removed_placeholder_count: int
    retained_answer_file_count: int


class LegacyRangeRow(NamedTuple):
    """One legacy catalog-plan range row."""

    range_id: int
    range_label: str
    range_start: int
    range_end: int
    surface: str
    status: str


class LegacyUnitRow(NamedTuple):
    """One legacy catalog-plan unit row."""

    unit_number: int
    range_id: int
    status: str
    surface: str
    evidence_path: str
    commit_hash: str
    updated_at_utc: str


class LegacyEventRow(NamedTuple):
    """One legacy progress event row."""

    legacy_event_id: int
    unit_number: int | None
    event_type: str
    event_json: str
    created_at_utc: str


class SemanticAnswerImport(NamedTuple):
    """One semantic answer file classified for SQLite intake."""

    unit_number: int | None
    unit_id: str | None
    normalized_json: str
    answer_sha256: str
    source_ref: str
    created_at_utc: str
    quarantine_reason: str | None
    placeholder_phrases: tuple[str, ...]


class AnswerQuarantineClassification(NamedTuple):
    """Why one semantic answer file must be quarantined instead of imported."""

    reason: str
    placeholder_phrases: tuple[str, ...]


def connect_catalog_plan_ssot(
    *,
    repo_root: Path,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
) -> sqlite3.Connection:
    """Open the Pancakes catalog-plan SQLite SSOT with runtime write pragmas.

    Returns:
        The opened SQLite connection.
    """
    resolved_database = resolve_repo_relative_path(repo_root, database_path)
    connection = sqlite3.connect(
        resolved_database,
        timeout=CATALOG_PLAN_SQLITE_BUSY_TIMEOUT_SECONDS,
    )
    connection.row_factory = sqlite3.Row
    _configure_catalog_plan_connection(connection, enable_wal=True)
    return connection


def migrate_legacy_catalog_plan_artifacts_with_retry(
    *,
    repo_root: Path,
    legacy_database_path: Path,
    semantic_answer_dir: Path | None = None,
    database_path: Path = DEFAULT_KNOWLEDGE_DB_PATH,
    observed_at_utc: str,
) -> CatalogPlanMigrationReport:
    """Import legacy catalog-plan artifacts into the main SQLite SSOT with lock.

    retries.

    Returns:
        The import report.

    Raises:
        RuntimeError: If retry bookkeeping reaches an impossible state.
        sqlite3.OperationalError: If SQLite remains locked or another write
        error occurs.
    """
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(CATALOG_PLAN_SQLITE_WRITE_RETRIES):
        connection = connect_catalog_plan_ssot(
            repo_root=repo_root, database_path=database_path
        )
        try:
            return migrate_legacy_catalog_plan_artifacts(
                connection=connection,
                legacy_database_path=legacy_database_path,
                semantic_answer_dir=semantic_answer_dir,
                source_ref=DEFAULT_CATALOG_PLAN_SOURCE_REF,
                observed_at_utc=observed_at_utc,
            )
        except sqlite3.OperationalError as exc:
            last_error = exc
            if (
                not _is_locked_sqlite_error(exc)
                or attempt + 1 >= CATALOG_PLAN_SQLITE_WRITE_RETRIES
            ):
                raise
            time.sleep(
                CATALOG_PLAN_SQLITE_RETRY_BASE_DELAY_SECONDS * (2**attempt)
            )
        finally:
            connection.close()
    if last_error is None:
        message = (
            "Catalog-plan SQLite migration exhausted retries without an error."
        )
        raise RuntimeError(message)
    raise last_error


def migrate_legacy_catalog_plan_artifacts(
    *,
    connection: sqlite3.Connection,
    legacy_database_path: Path,
    semantic_answer_dir: Path | None = None,
    source_ref: str,
    observed_at_utc: str,
) -> CatalogPlanMigrationReport:
    """Import legacy progress rows and answer files without changing their.

    source files.

    Returns:
        The import report.
    """
    _configure_catalog_plan_connection(connection, enable_wal=False)
    metadata = _read_legacy_metadata(legacy_database_path)
    ranges = _read_legacy_ranges(legacy_database_path)
    units = _read_legacy_units(legacy_database_path)
    events = _read_legacy_events(legacy_database_path)
    unit_numbers = frozenset(unit.unit_number for unit in units)
    answers = _read_semantic_answers(
        semantic_answer_dir=semantic_answer_dir,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    with connection:
        _insert_metadata(
            connection=connection,
            rows=metadata,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
        )
        _insert_ranges(
            connection=connection,
            rows=ranges,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
        )
        _insert_units(
            connection=connection,
            rows=units,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
        )
        _insert_events(
            connection=connection,
            rows=events,
            source_ref=source_ref,
        )
        answer_count, quarantine_count = _insert_answers(
            connection=connection,
            answers=answers,
            unit_numbers=unit_numbers,
        )
    return CatalogPlanMigrationReport(
        metadata_count=len(metadata),
        range_count=len(ranges),
        unit_count=len(units),
        progress_event_count=len(events),
        semantic_answer_count=answer_count,
        quarantined_answer_count=quarantine_count,
    )


def cleanup_placeholder_semantic_answers(
    *,
    connection: sqlite3.Connection,
    semantic_answer_dir: Path,
    source_ref: str,
    observed_at_utc: str,
    delete_files: bool = True,
) -> CatalogPlanPlaceholderCleanupReport:
    """Import generated answer files, then remove only insufficient-evidence.

    placeholders.

    Returns:
        The cleanup report.
    """
    _configure_catalog_plan_connection(connection, enable_wal=False)
    answers = _read_semantic_answers(
        semantic_answer_dir=semantic_answer_dir,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    unit_numbers = _catalog_plan_unit_numbers(connection)
    placeholder_answers = tuple(
        answer
        for answer in answers
        if answer.quarantine_reason
        == "semantic_answer_has_insufficient_evidence_placeholder"
    )
    with connection:
        answer_count, quarantine_count = _insert_answers(
            connection=connection,
            answers=answers,
            unit_numbers=unit_numbers,
        )
    removed_count = 0
    if delete_files:
        for answer in placeholder_answers:
            if _remove_semantic_answer_file(
                semantic_answer_dir=semantic_answer_dir,
                source_ref=answer.source_ref,
            ):
                removed_count += 1
    return CatalogPlanPlaceholderCleanupReport(
        scanned_answer_count=len(answers),
        migrated_answer_count=answer_count,
        quarantined_answer_count=quarantine_count,
        removed_placeholder_count=removed_count,
        retained_answer_file_count=len(answers) - removed_count,
    )


def _configure_catalog_plan_connection(
    connection: sqlite3.Connection,
    *,
    enable_wal: bool,
) -> None:
    """Apply catalog-plan SQLite concurrency pragmas."""
    _ = connection.execute("PRAGMA foreign_keys = ON")
    _ = connection.execute(
        f"PRAGMA busy_timeout = {CATALOG_PLAN_SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
    )
    if enable_wal:
        _ = connection.execute("PRAGMA journal_mode = WAL")


def _catalog_plan_unit_numbers(
    connection: sqlite3.Connection,
) -> frozenset[int]:
    """Return catalog-plan unit numbers already present in the SQLite SSOT.

    Returns:
        The known unit numbers.
    """
    rows = cast(
        "list[tuple[int]]",
        connection.execute(
            "SELECT unit_number FROM catalog_plan_units"
        ).fetchall(),
    )
    return frozenset(int(row[0]) for row in rows)


def _remove_semantic_answer_file(
    *, semantic_answer_dir: Path, source_ref: str
) -> bool:
    """Remove one placeholder answer file if it still exists under the answer.

    directory.

    Returns:
        Whether a file was removed.

    Raises:
        ValueError: If the computed file path escapes the answer directory.
    """
    filename = source_ref.rsplit("/", maxsplit=1)[-1]
    if not filename.endswith(ANSWER_FILE_SUFFIX):
        return False
    root = semantic_answer_dir.resolve(strict=False)
    path = (semantic_answer_dir / filename).resolve(strict=False)
    if not path.is_relative_to(root):
        message = (
            f"Semantic answer cleanup path escapes answer directory: {filename}"
        )
        raise ValueError(message)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _read_legacy_metadata(path: Path) -> tuple[tuple[str, str], ...]:
    """Read legacy progress metadata rows.

    Returns:
        The metadata key/value rows.
    """
    connection = _legacy_connection(path)
    try:
        rows = connection.execute(
            "SELECT key, value FROM metadata ORDER BY key"
        ).fetchall()
    finally:
        connection.close()
    return tuple((str(row[0]), str(row[1])) for row in rows)


def _read_legacy_ranges(path: Path) -> tuple[LegacyRangeRow, ...]:
    """Read legacy progress range rows.

    Returns:
        The range rows.
    """
    connection = _legacy_connection(path)
    try:
        rows = connection.execute(
            """
            SELECT range_id, range_label, range_start, range_end, surface,
            status
            FROM ranges
            ORDER BY range_id
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        LegacyRangeRow(
            range_id=int(row[0]),
            range_label=str(row[1]),
            range_start=int(row[2]),
            range_end=int(row[3]),
            surface=str(row[4]),
            status=str(row[5]),
        )
        for row in rows
    )


def _read_legacy_units(path: Path) -> tuple[LegacyUnitRow, ...]:
    """Read legacy progress unit rows.

    Returns:
        The unit rows.
    """
    connection = _legacy_connection(path)
    try:
        rows = connection.execute(
            """
            SELECT unit_number, range_id, status, surface, evidence_path,
            commit_hash,
                   updated_at_utc
            FROM units
            ORDER BY unit_number
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        LegacyUnitRow(
            unit_number=int(row[0]),
            range_id=int(row[1]),
            status=str(row[2]),
            surface=str(row[3]),
            evidence_path=str(row[4] or ""),
            commit_hash=str(row[5] or ""),
            updated_at_utc=str(row[6] or ""),
        )
        for row in rows
    )


def _read_legacy_events(path: Path) -> tuple[LegacyEventRow, ...]:
    """Read legacy progress event rows.

    Returns:
        The progress event rows.
    """
    connection = _legacy_connection(path)
    try:
        rows = connection.execute(
            """
            SELECT event_id, unit_number, event_type, event_json, created_at_utc
            FROM progress_events
            ORDER BY event_id
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        LegacyEventRow(
            legacy_event_id=int(row[0]),
            unit_number=None if row[1] is None else int(row[1]),
            event_type=str(row[2]),
            event_json=str(row[3]),
            created_at_utc=str(row[4]),
        )
        for row in rows
    )


def _legacy_connection(path: Path) -> sqlite3.Connection:
    """Open a legacy catalog-plan progress database.

    Returns:
        The opened SQLite connection.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _read_semantic_answers(
    *,
    semantic_answer_dir: Path | None,
    source_ref: str,
    observed_at_utc: str,
) -> tuple[SemanticAnswerImport, ...]:
    """Classify existing semantic answer JSON files for SQLite intake.

    Returns:
        The classified answer intake rows.
    """
    if semantic_answer_dir is None or not semantic_answer_dir.is_dir():
        return ()
    return tuple(
        (
            _read_semantic_answer(
                path=path,
                source_ref=f"{source_ref}/{path.name}",
                observed_at_utc=observed_at_utc,
            )
        )
        for path in sorted(semantic_answer_dir.glob(f"*{ANSWER_FILE_SUFFIX}"))
    )


def _read_semantic_answer(
    *,
    path: Path,
    source_ref: str,
    observed_at_utc: str,
) -> SemanticAnswerImport:
    """Read one semantic answer file as data, not as new catalog reasoning.

    Returns:
        A classified semantic answer import row.
    """
    raw_text = path.read_text(encoding="utf-8")
    answer_sha256 = _sha256_text(raw_text)
    placeholder_phrases = _placeholder_phrases(raw_text)
    filename_unit_id = _unit_id_from_answer_path(path)
    try:
        raw_payload = cast("object", json.loads(raw_text))
    except json.JSONDecodeError:
        return _quarantined_answer(
            unit_id=filename_unit_id,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
            classification=AnswerQuarantineClassification(
                reason="semantic_answer_json_invalid",
                placeholder_phrases=placeholder_phrases,
            ),
        )
    if not isinstance(raw_payload, dict):
        return _quarantined_answer(
            unit_id=filename_unit_id,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
            classification=AnswerQuarantineClassification(
                reason="semantic_answer_json_not_object",
                placeholder_phrases=placeholder_phrases,
            ),
        )
    payload = cast("Mapping[str, object]", raw_payload)
    payload_unit_id = _unit_id_from_payload(payload)
    unit_id = payload_unit_id or filename_unit_id
    if (
        filename_unit_id is not None
        and payload_unit_id is not None
        and filename_unit_id != unit_id
    ):
        return _quarantined_answer(
            unit_id=filename_unit_id,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
            classification=AnswerQuarantineClassification(
                reason="semantic_answer_unit_id_mismatch",
                placeholder_phrases=placeholder_phrases,
            ),
        )
    if unit_id is None:
        return _quarantined_answer(
            unit_id=None,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
            classification=AnswerQuarantineClassification(
                reason="semantic_answer_unit_id_missing",
                placeholder_phrases=placeholder_phrases,
            ),
        )
    if placeholder_phrases:
        return _quarantined_answer(
            unit_id=unit_id,
            answer_sha256=answer_sha256,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
            classification=AnswerQuarantineClassification(
                reason="semantic_answer_has_insufficient_evidence_placeholder",
                placeholder_phrases=placeholder_phrases,
            ),
        )
    normalized = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    )
    return SemanticAnswerImport(
        unit_number=_unit_number_from_id(unit_id),
        unit_id=unit_id,
        normalized_json=normalized,
        answer_sha256=_sha256_text(normalized),
        source_ref=source_ref,
        created_at_utc=observed_at_utc,
        quarantine_reason=None,
        placeholder_phrases=(),
    )


def _quarantined_answer(
    *,
    unit_id: str | None,
    answer_sha256: str,
    source_ref: str,
    observed_at_utc: str,
    classification: AnswerQuarantineClassification,
) -> SemanticAnswerImport:
    """Return one answer-classification record that must enter quarantine."""
    return SemanticAnswerImport(
        unit_number=None if unit_id is None else _unit_number_from_id(unit_id),
        unit_id=unit_id,
        normalized_json="",
        answer_sha256=answer_sha256,
        source_ref=source_ref,
        created_at_utc=observed_at_utc,
        quarantine_reason=classification.reason,
        placeholder_phrases=classification.placeholder_phrases,
    )


def _insert_metadata(
    *,
    connection: sqlite3.Connection,
    rows: tuple[tuple[str, str], ...],
    source_ref: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_plan_metadata (
          key, value, source_kind, source_ref, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                key,
                value,
                "legacy_catalog_plan_progress",
                source_ref,
                observed_at_utc,
            )
            for key, value in rows
        ],
    )


def _insert_ranges(
    *,
    connection: sqlite3.Connection,
    rows: tuple[LegacyRangeRow, ...],
    source_ref: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_plan_ranges (
          range_id, range_label, range_start, range_end, surface, status,
          source_kind,
          source_ref, fingerprint, valid_from, valid_to
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        [
            (
                row.range_id,
                row.range_label,
                row.range_start,
                row.range_end,
                row.surface,
                row.status,
                "legacy_catalog_plan_progress",
                source_ref,
                _fingerprint(row),
                observed_at_utc,
            )
            for row in rows
        ],
    )


def _insert_units(
    *,
    connection: sqlite3.Connection,
    rows: tuple[LegacyUnitRow, ...],
    source_ref: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_plan_units (
          unit_number, range_id, status, surface, evidence_path, commit_hash,
          semantic_answer_sha256, updated_at_utc, source_kind, source_ref,
          fingerprint,
          valid_from, valid_to
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL)
        """,
        [
            (
                row.unit_number,
                row.range_id,
                row.status,
                row.surface,
                row.evidence_path,
                row.commit_hash,
                row.updated_at_utc or observed_at_utc,
                "legacy_catalog_plan_progress",
                source_ref,
                _fingerprint(row),
                observed_at_utc,
            )
            for row in rows
        ],
    )


def _insert_events(
    *,
    connection: sqlite3.Connection,
    rows: tuple[LegacyEventRow, ...],
    source_ref: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_plan_progress_events (
          event_id, legacy_event_id, unit_number, event_type, event_json,
          created_at_utc,
          source_kind, source_ref, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                _stable_id(
                    "catalog-plan-event", source_ref, row.legacy_event_id
                ),
                row.legacy_event_id,
                row.unit_number,
                row.event_type,
                row.event_json,
                row.created_at_utc,
                "legacy_catalog_plan_progress",
                source_ref,
                _fingerprint(row),
            )
            for row in rows
        ],
    )


def _insert_answers(
    *,
    connection: sqlite3.Connection,
    answers: tuple[SemanticAnswerImport, ...],
    unit_numbers: frozenset[int],
) -> tuple[int, int]:
    answer_count = 0
    quarantine_count = 0
    for answer in answers:
        reason = answer.quarantine_reason
        if (
            answer.unit_number is not None
            and answer.unit_number not in unit_numbers
        ):
            reason = "semantic_answer_unit_not_in_legacy_progress"
        if (
            reason is not None
            or answer.unit_number is None
            or answer.unit_id is None
        ):
            _insert_answer_quarantine(
                connection=connection,
                answer=answer,
                reason=reason or "semantic_answer_unit_id_missing",
            )
            quarantine_count += 1
            continue
        _ = connection.execute(
            """
            INSERT OR REPLACE INTO catalog_plan_semantic_answers (
              unit_number, unit_id, answer_json, answer_sha256, answer_status,
              evidence_status, source_kind, source_ref, created_at_utc,
              saved_by_tool,
              valid_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                answer.unit_number,
                answer.unit_id,
                answer.normalized_json,
                answer.answer_sha256,
                CATALOG_PLAN_SEMANTIC_ANSWER_STATUS,
                "evidence_present ",
                "legacy_semantic_answer_json",
                answer.source_ref,
                answer.created_at_utc,
                "catalog.work.save",
            ),
        )
        _ = connection.execute(
            """
            UPDATE catalog_plan_units
            SET status = ?, evidence_path = ?, semantic_answer_sha256 = ?,
                updated_at_utc = ?
            WHERE unit_number = ?
            """,
            (
                CATALOG_PLAN_SEMANTIC_ANSWER_STATUS,
                answer.source_ref,
                answer.answer_sha256,
                answer.created_at_utc,
                answer.unit_number,
            ),
        )
        answer_count += 1
    return answer_count, quarantine_count


def _insert_answer_quarantine(
    *,
    connection: sqlite3.Connection,
    answer: SemanticAnswerImport,
    reason: str,
) -> None:
    evidence_gap_json = json.dumps(
        {
            "answer_sha256": answer.answer_sha256,
            "placeholder_phrases": list(answer.placeholder_phrases),
            "source_ref": answer.source_ref,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    retry_policy_json = json.dumps(
        {
            "manual_codex_cataloging_allowed": False,
            "retry_worker": "ChatGPT.com ",
            "retry_tool_flow": "catalog.next_unit -> catalog.save_unit",
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
            _stable_id("catalog-plan-quarantine", reason, answer.source_ref),
            answer.unit_number,
            answer.unit_id,
            "semantic_answer_intake",
            reason,
            evidence_gap_json,
            retry_policy_json,
            10,
            "legacy_semantic_answer_json",
            answer.source_ref,
            "needs_retry",
            answer.created_at_utc,
        ),
    )


def _unit_id_from_payload(payload: Mapping[str, object]) -> str | None:
    value = payload.get("unit_id")
    if not isinstance(value, str) or not _is_unit_id(value):
        return None
    return value


def _unit_id_from_answer_path(path: Path) -> str | None:
    name = path.name
    if not name.endswith(ANSWER_FILE_SUFFIX):
        return None
    unit_id = name.removesuffix(ANSWER_FILE_SUFFIX)
    if not _is_unit_id(unit_id):
        return None
    return unit_id


def _is_unit_id(value: str) -> bool:
    return len(value) == UNIT_ID_WIDTH and value.isdecimal()


def _unit_number_from_id(unit_id: str) -> int:
    return int(unit_id)


def _placeholder_phrases(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    return tuple(
        marker
        for marker in INSUFFICIENT_EVIDENCE_MARKERS
        if marker in normalized
    )


def _is_locked_sqlite_error(error: sqlite3.OperationalError) -> bool:
    message = str(error).casefold()
    return "locked" in message or "busy" in message


def _fingerprint(value: object) -> str:
    return _sha256_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    )


def _stable_id(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
