# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for the development-only catalog semantic unit loop.

Boundary contract:
- Owns: SQLite cursor behavior for ChatGPT.com semantic unit authoring.
- Must not: validate catalog knowledge quality, call providers, or mutate
generated Make SQLite.
- Allows: synthetic main knowledge SQLite rows and raw-spec evidence fixtures.
- Merge when: catalog-plan semantic worker coverage moves to a lower-level SSOT
contract.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, cast

import pytest
from catalog.knowledge.models import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.refresh_feedback import (
    MakeCatalogRefreshFeedbackRecord,
    record_make_catalog_refresh_feedback_for_repo,
)
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    sync_raw_specs,
)
from mcp import execute_mcp_tool

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

pytest.skip(
    "legacy catalog.next_unit/save_unit MCP aliases are inactive; tests are "
    "retained for future utility.",
    allow_module_level=True,
)

OBSERVED_AT = "2026-05-18T00:00:00+00:00"


def test_catalog_plan_semantic_unit_loop_advances_only_after_save(
    tmp_path: Path,
) -> None:
    """catalog.next_unit keeps returning the same row until catalog.save_unit.

    commits.
    """
    total_units = 2
    _seed_catalog_plan_ssot(tmp_path, total_units=total_units)

    first = execute_mcp_tool(
        tool_name="catalog.next_unit",
        arguments={},
        repo_root=tmp_path,
    )
    assert first.ok, (
        f"catalog.next_unit should return the first pending unit: {first}"
    )
    assert first.payload["unit_id"] == "000001", (
        f"Unexpected first unit: {first}"
    )
    assert "until catalog.save_unit" in str(first.payload["advance_rule"])
    assert first.payload["development_only"] is True
    assert first.payload["codex_catalog_authoring_allowed"] is False
    _assert_first_unit_evidence(first.payload, total_units=total_units)

    repeated = execute_mcp_tool(
        tool_name="catalog.next_unit",
        arguments={},
        repo_root=tmp_path,
    )
    assert repeated.ok, (
        f"catalog.next_unit should be repeatable before save: {repeated}"
    )
    assert repeated.payload["unit_id"] == "000001", (
        f"catalog.next_unit must not advance before save: {repeated}"
    )

    saved = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": _valid_answer("000001")},
        repo_root=tmp_path,
    )
    assert saved.ok, f"catalog.save_unit should persist one answer: {saved}"
    assert saved.payload["ledger_status"] == "semantic_answered", (
        f"catalog.save_unit should mark the row answered: {saved}"
    )
    assert saved.payload["ledger_kind"] == "sqlite_ssot"
    assert saved.payload["ledger_completed_units"] == 1
    assert saved.payload["next_unit_id"] == "000002", (
        f"Wrong next id after save: {saved}"
    )
    assert not (
        tmp_path / "src/catalog/plan_artifact/semantic_answers"
    ).exists(), (
        f"catalog.save_unit must not create orphan answer JSON files: {saved}"
    )
    _assert_saved_sqlite_state(tmp_path)

    second = execute_mcp_tool(
        tool_name="catalog.next_unit",
        arguments={},
        repo_root=tmp_path,
    )
    assert second.ok, f"catalog.next_unit should advance after save: {second}"
    assert second.payload["unit_id"] == "000002", f"Wrong second unit: {second}"


def test_catalog_plan_semantic_unit_loop_rejects_mismatched_answer(
    tmp_path: Path,
) -> None:
    """An invalid save does not move the SQLite cursor or write answer rows."""
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    bad = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={
            "unit_id": "000001",
            "answer_json": json.dumps(
                {"unit_id": "000002", "status": "answered"}
            ),
        },
        repo_root=tmp_path,
    )
    assert not bad.ok, (
        f"catalog.save_unit must reject mismatched unit ids: {bad}"
    )

    first = execute_mcp_tool(
        tool_name="catalog.next_unit",
        arguments={},
        repo_root=tmp_path,
    )
    assert first.ok, (
        f"catalog.next_unit should still return the unsaved row: {first}"
    )
    assert first.payload["unit_id"] == "000001", (
        f"Invalid save advanced the cursor: {first}"
    )
    _assert_unit_pending_without_saves(tmp_path)


def test_catalog_plan_checkpoint_unit_rejects_insufficient_evidence_placeholder(
    tmp_path: Path,
) -> None:
    """Bare insufficient-evidence answers are rejected instead of saved."""
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    answer = {
        "response_contract": "catalog_plan.semantic_unit_answer.v1 ",
        "unit_id": "000001 ",
        "status": "answered ",
        "summary": (
            "No sufficient evidence is available for this synthetic fixture."
        ),
    }

    rejected = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": json.dumps(answer)},
        repo_root=tmp_path,
    )

    assert not rejected.ok, f"Placeholder answers must fail closed: {rejected}"
    _assert_unit_pending_without_saves(tmp_path)


def test_catalog_plan_checkpoint_unit_accepts_structured_quarantine_save(
    tmp_path: Path,
) -> None:
    """Weak evidence saves become typed SQLite quarantine records and advance.

    the unit.
    """
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    answer = {
        "response_contract": "catalog_plan.semantic_unit_answer.v1 ",
        "unit_id": "000001 ",
        "status": "quarantined",
        "retry_priority": 80,
        "evidence_pointers": ["raw_catalog_evidence.spec_path"],
        "quarantine": [
            {
                "gap_type": "missing_datastore_structure ",
                "reason": (
                    "Synthetic datastore structure evidence is not present."
                ),
                "missing_evidence": ["sample datastore field list"],
            }
        ],
    }

    saved = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": json.dumps(answer)},
        repo_root=tmp_path,
    )

    assert saved.ok, f"Structured quarantine checkpoint should commit: {saved}"
    assert saved.payload["ledger_status"] == "quarantined"
    assert saved.payload["structured_quarantine"] is True
    assert saved.payload["next_unit_id"] is None
    _assert_quarantine_sqlite_state(tmp_path)


def test_catalog_plan_checkpoint_unit_accepts_empty_quarantine_on_normal_answer(
    tmp_path: Path,
) -> None:
    """ChatGPT.com prompt shape may include an empty quarantine array on valid.

    answers.
    """
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    answer: JsonObject = {
        "unit_id": "000001 ",
        "surface": "raw Make app-version specs ",
        "semantic_summary": "Synthetic app version answer.",
        "app": {"label": "Synthetic", "slug": "synthetic", "version": "1.0.0"},
        "module_roles": [],
        "resource_nodes": [],
        "dependency_edges": [],
        "workflow_edges": [],
        "coverage": {},
        "quarantine": [],
    }

    saved = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": answer},
        repo_root=tmp_path,
    )

    assert saved.ok, (
        f"Empty quarantine arrays should not force quarantine mode: {saved}"
    )
    assert saved.payload["ledger_status"] == "semantic_answered"
    assert saved.payload["structured_quarantine"] is False


def test_catalog_plan_checkpoint_unit_accepts_gap_notes_on_normal_answer(
    tmp_path: Path,
) -> None:
    """Normal semantic answers may include bounded gap notes without entering.

    quarantine mode.
    """
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    answer = {
        "unit_id": "000001 ",
        "surface": "raw Make app-version specs ",
        "semantic_summary": (
            "Synthetic app version answer with bounded gap notes."
        ),
        "app": {"label": "Synthetic", "slug": "synthetic", "version": "1.0.0"},
        "module_roles": [],
        "resource_nodes": [],
        "dependency_edges": [],
        "workflow_edges": [],
        "coverage": {"operation_summary_limit": 12},
        "quarantine": [
            {
                "gap_type": "limited_operation_summaries ",
                "reason": "Only compact operation summaries are present.",
                "evidence_pointers": [
                    "raw_catalog_evidence.operation_summary_limit"
                ],
                "handling": "Avoid field-level claims for unexpanded modules.",
            }
        ],
    }

    saved = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": answer},
        repo_root=tmp_path,
    )

    assert saved.ok, (
        f"Gap notes on normal answers should save semantically: {saved}"
    )
    assert saved.payload["ledger_status"] == "semantic_answered"
    assert saved.payload["structured_quarantine"] is False
    _assert_saved_sqlite_state(tmp_path)
    _assert_no_quarantine_records(tmp_path)


def test_catalog_plan_legacy_checkpoint_aliases_route_to_canonical_save(
    tmp_path: Path,
) -> None:
    """Legacy catalog save aliases route through the canonical SQLite save.

    handler.
    """
    for tool_name in ("catalog.save_unit", "catalog.checkpoint_unit"):
        alias_root = tmp_path / tool_name.replace(".", "_")
        _seed_catalog_plan_ssot(alias_root, total_units=1)
        result = execute_mcp_tool(
            tool_name=tool_name,
            arguments={
                "unit_id": "000001",
                "answer_json": _valid_answer("000001"),
            },
            repo_root=alias_root,
        )

        assert result.ok
        assert result.payload["ledger_status"] == "semantic_answered"

    retired = execute_mcp_tool(
        tool_name="catalog.autosave_unit",
        arguments={"unit_id": "000001", "answer_json": _valid_answer("000001")},
        repo_root=tmp_path,
    )
    assert not retired.ok
    assert retired.error == "Unknown MCP tool: catalog.autosave_unit"


def test_catalog_plan_checkpoint_unit_alias_saves_semantic_answer(
    tmp_path: Path,
) -> None:
    """The current ChatGPT.com checkpoint alias writes through the SQLite.

    ledger.

    path.
    """
    _seed_catalog_plan_ssot(tmp_path, total_units=1)

    saved = execute_mcp_tool(
        tool_name="catalog.checkpoint_unit",
        arguments={"unit_id": "000001", "answer_json": _valid_answer("000001")},
        repo_root=tmp_path,
    )

    assert saved.ok, (
        f"catalog.checkpoint_unit should persist one answer: {saved}"
    )
    assert (
        saved.payload["response_contract"]
        == "catalog_plan.semantic_unit_save.v1"
    )
    assert saved.payload["ledger_status"] == "semantic_answered"
    assert saved.payload["structured_quarantine"] is False
    _assert_saved_sqlite_state(tmp_path)


def test_catalog_refresh_feedback_prioritizes_next_unit_without_semantic_answer(
    tmp_path: Path,
) -> None:
    """Refresh feedback makes ChatGPT.com retry the targeted unit without Codex.

    answers.
    """
    _seed_catalog_plan_ssot(tmp_path, total_units=2)

    report = record_make_catalog_refresh_feedback_for_repo(
        repo_root=tmp_path,
        records=(
            MakeCatalogRefreshFeedbackRecord(
                feedback_key="raw-spec-delta:unit-000002",
                title=(
                    "Review refreshed Google Sheets evidence before semantic "
                    "save"
                ),
                priority=95,
                evidence_kind="raw-spec-delta",
                source_ref="tests/mcp/catalog-refresh-feedback",
                payload={
                    "unit_id": "000002",
                    "unit_number": 2,
                    "surface": "raw Make app-version specs",
                    "changed_source_ref": (
                        "sqlite:make_raw_spec_payloads/zz-google-sheets__1.0.0"
                    ),
                },
                unit_number=2,
            ),
        ),
        observed_at_utc=OBSERVED_AT,
    )
    next_unit = execute_mcp_tool(
        tool_name="catalog.next_unit",
        arguments={},
        repo_root=tmp_path,
    )

    assert report.semantic_answer_rows_written == 0
    assert report.backlog_entry_ids
    assert report.quarantine_record_ids
    assert next_unit.ok, (
        f"catalog.next_unit should read refresh priority: {next_unit}"
    )
    assert next_unit.payload["unit_id"] == "000002", next_unit
    assert next_unit.payload["retry_priority"] == 95
    _assert_refresh_feedback_sqlite_state(tmp_path)


def test_catalog_plan_checkpoint_unit_rejects_incomplete_quarantine_transaction(
    tmp_path: Path,
) -> None:
    """Malformed quarantine saves roll back without advancing the unit."""
    _seed_catalog_plan_ssot(tmp_path, total_units=1)
    answer = {
        "response_contract": "catalog_plan.semantic_unit_answer.v1 ",
        "unit_id": "000001 ",
        "status": "quarantined",
        "evidence_pointers": ["raw_catalog_evidence.spec_path"],
        "quarantine": [
            {"gap_type": "missing_structure", "reason": "Fixture gap."}
        ],
    }

    rejected = execute_mcp_tool(
        tool_name="catalog.save_unit",
        arguments={"unit_id": "000001", "answer_json": json.dumps(answer)},
        repo_root=tmp_path,
    )

    assert not rejected.ok, (
        f"Malformed quarantine checkpoint must fail atomically: {rejected}"
    )
    _assert_unit_pending_without_saves(tmp_path)


def _valid_answer(unit_id: str) -> JsonObject:
    return {
        "response_contract": "catalog_plan.semantic_unit_answer.v1",
        "unit_id": unit_id,
        "status": "answered ",
        "semantic_intent": "raw make app version",
        "aliases": ["make app version"],
        "module_families": [],
        "candidate_module_ids": [],
        "node_reasoning": {
            "semantic_role": (
                "Catalog inventory unit for one Make app-version surface."
            ),
            "consumes": ["supplied catalog unit evidence"],
            "produces": ["semantic graph metadata candidate"],
            "connects_from": ["catalog inventory"],
            "connects_to": ["app family semantic node"],
            "required_bridges": [],
            "setup_dependencies": [],
        },
        "semantic_nodes": [],
        "semantic_edges": [],
        "catalog_feedback": [],
        "confidence": "medium",
    }


def _assert_first_unit_evidence(
    payload: JsonObject, *, total_units: int
) -> None:
    raw_evidence = cast("JsonObject", payload["raw_catalog_evidence"])
    assert raw_evidence["evidence_status"] == "sqlite_raw_spec_manifest", (
        f"catalog.work.next must include useful raw catalog evidence: {payload}"
    )
    assert raw_evidence["app_slug"] == "slack", f"Wrong app evidence: {payload}"
    assert (
        raw_evidence["spec_path"]
        == "sqlite:make_raw_spec_payloads/slack__1.0.0"
    )
    ledger = cast("JsonObject", payload["ledger"])
    assert ledger["ledger_kind"] == "sqlite_ssot"
    assert ledger["database_path"] == DEFAULT_KNOWLEDGE_DB_PATH.as_posix()
    assert ledger["completed_units"] == 0
    assert ledger["total_units"] == total_units
    assert (
        payload["answer_ref"] == "sqlite:catalog_plan_semantic_answers/000001"
    )
    assert payload["candidate_module_ids"] == [
        "module:slack:1.0.0:action:sendMessage"
    ], f"Candidate modules should come from raw evidence: {payload}"
    operation_summaries = cast(
        "list[JsonObject]", raw_evidence["operation_summaries"]
    )
    assert operation_summaries[0]["display_name"] == "Send a Message"
    field_names = {
        str(field["name"])
        for field in cast("list[JsonObject]", operation_summaries[0]["fields"])
    }
    assert {"channel", "text"}.issubset(field_names), (
        f"Raw evidence should include bounded operation fields: {payload}"
    )


def _assert_saved_sqlite_state(repo_root: Path) -> None:
    with closing(_connect_seed_database(repo_root)) as connection:
        row = cast(
            "tuple[str, str, str | None] | None",
            connection.execute(
                """
                SELECT status, evidence_path, semantic_answer_sha256
                FROM catalog_plan_units
                WHERE unit_number = 1
                """
            ).fetchone(),
        )
        event_count_row = cast(
            "tuple[int] | None",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_progress_events WHERE "
                "unit_number = 1"
            ).fetchone(),
        )
        answer_row = cast(
            "tuple[str, str] | None",
            connection.execute(
                """
                SELECT unit_id, saved_by_tool
                FROM catalog_plan_semantic_answers
                WHERE unit_number = 1
                """
            ).fetchone(),
        )
    assert row is not None
    assert event_count_row is not None
    assert answer_row is not None
    assert row[0] == "semantic_answered"
    assert row[1] == "sqlite:catalog_plan_semantic_answers/000001"
    assert row[2] is not None
    assert event_count_row[0] == 1
    assert answer_row == ("000001", "catalog.save_unit")


def _assert_unit_pending_without_saves(repo_root: Path) -> None:
    with closing(_connect_seed_database(repo_root)) as connection:
        unit_status = cast(
            "tuple[str] | None",
            connection.execute(
                "SELECT status FROM catalog_plan_units WHERE unit_number = 1"
            ).fetchone(),
        )
        answer_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_semantic_answers"
            ).fetchone(),
        )[0]
        quarantine_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_quarantine_records"
            ).fetchone(),
        )[0]
        event_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_progress_events"
            ).fetchone(),
        )[0]
    assert unit_status == ("pending",)
    assert answer_count == 0
    assert quarantine_count == 0
    assert event_count == 0


def _assert_no_quarantine_records(repo_root: Path) -> None:
    with closing(_connect_seed_database(repo_root)) as connection:
        quarantine_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_quarantine_records"
            ).fetchone(),
        )[0]
    assert quarantine_count == 0


def _assert_quarantine_sqlite_state(repo_root: Path) -> None:
    with closing(_connect_seed_database(repo_root)) as connection:
        unit_status = cast(
            "tuple[str, str] | None",
            connection.execute(
                """
                SELECT status, evidence_path
                FROM catalog_plan_units
                WHERE unit_number = 1
                """
            ).fetchone(),
        )
        answer_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_semantic_answers"
            ).fetchone(),
        )[0]
        quarantine = cast(
            "tuple[str, int, str] | None",
            connection.execute(
                """
                SELECT status, priority, retry_policy_json
                FROM catalog_plan_quarantine_records
                WHERE unit_number = 1
                """
            ).fetchone(),
        )
        event_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_progress_events"
            ).fetchone(),
        )[0]
    assert unit_status is not None
    assert unit_status[0] == "quarantined"
    assert unit_status[1].startswith(
        "sqlite:catalog_plan_quarantine_records/000001/"
    )
    assert answer_count == 0
    assert quarantine is not None
    assert quarantine[0] == "needs_retry"
    assert quarantine[1] == 80
    assert "catalog.next_unit -> catalog.save_unit" in quarantine[2]
    assert event_count == 1


def _assert_refresh_feedback_sqlite_state(repo_root: Path) -> None:
    with closing(_connect_seed_database(repo_root)) as connection:
        answer_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_semantic_answers"
            ).fetchone(),
        )[0]
        backlog = cast(
            "tuple[str, str, str, int] | None",
            connection.execute(
                """
                SELECT domain, status, source_kind, priority
                FROM mcp_backlog_entries
                WHERE source_kind = 'make_catalog_refresh_feedback'
                """
            ).fetchone(),
        )
        quarantine = cast(
            "tuple[str, int, str] | None",
            connection.execute(
                """
                SELECT status, priority, retry_policy_json
                FROM catalog_plan_quarantine_records
                WHERE unit_number = 2
                """
            ).fetchone(),
        )
    assert answer_count == 0
    assert backlog == ("catalog", "open", "make_catalog_refresh_feedback", 95)
    assert quarantine is not None
    assert quarantine[0] == "needs_retry"
    assert quarantine[1] == 95
    assert "Catalog Work" in quarantine[2]
    assert "Catalog Intelligence" not in quarantine[2]


def _seed_catalog_plan_ssot(repo_root: Path, *, total_units: int) -> None:
    _seed_raw_spec_manifest(repo_root)
    database_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        _ = connection.executescript(
            """
            CREATE TABLE catalog_plan_ranges(
                range_id INTEGER PRIMARY KEY,
                range_label TEXT NOT NULL UNIQUE,
                range_start INTEGER NOT NULL,
                range_end INTEGER NOT NULL,
                surface TEXT NOT NULL,
                status TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT
            );
            CREATE TABLE catalog_plan_units(
                unit_number INTEGER PRIMARY KEY,
                range_id INTEGER NOT NULL REFERENCES
                catalog_plan_ranges(range_id),
                status TEXT NOT NULL,
                surface TEXT NOT NULL,
                evidence_path TEXT NOT NULL DEFAULT '',
                commit_hash TEXT NOT NULL DEFAULT '',
                semantic_answer_sha256 TEXT,
                updated_at_utc TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT
            );
            CREATE INDEX idx_catalog_plan_units_status
              ON catalog_plan_units(status, unit_number);
            CREATE TABLE catalog_plan_progress_events(
                event_id TEXT PRIMARY KEY,
                legacy_event_id INTEGER,
                unit_number INTEGER REFERENCES catalog_plan_units(unit_number),
                event_type TEXT NOT NULL,
                event_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                fingerprint TEXT NOT NULL
            );
            CREATE TABLE catalog_plan_semantic_answers(
                unit_number INTEGER NOT NULL REFERENCES
                catalog_plan_units(unit_number),
                unit_id TEXT NOT NULL,
                answer_json TEXT NOT NULL,
                answer_sha256 TEXT NOT NULL,
                answer_status TEXT NOT NULL,
                evidence_status TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                saved_by_tool TEXT NOT NULL,
                valid_to TEXT,
                PRIMARY KEY (unit_number, answer_sha256)
            );
            CREATE TABLE catalog_plan_quarantine_records(
                quarantine_id TEXT PRIMARY KEY,
                unit_number INTEGER,
                unit_id TEXT,
                quarantine_kind TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_gap_json TEXT NOT NULL,
                retry_policy_json TEXT NOT NULL,
                priority INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                resolved_at_utc TEXT
            );
            """
        )
        range_label = f"000001-{total_units:06d}"
        _ = connection.execute(
            """
            INSERT INTO catalog_plan_ranges(
              range_id, range_label, range_start, range_end, surface, status,
              source_kind,
              source_ref, fingerprint, valid_from, valid_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                1,
                range_label,
                1,
                total_units,
                "raw Make app-version specs ",
                "pending ",
                "test_fixture ",
                "tests/mcp/tool_contracts/mcp_catalog_plan_semantic_unit_loop_contract.py",
                _sha256_text(range_label),
                OBSERVED_AT,
            ),
        )
        _ = connection.executemany(
            """
            INSERT INTO catalog_plan_units(
              unit_number, range_id, status, surface, evidence_path,
              commit_hash,
              semantic_answer_sha256, updated_at_utc, source_kind, source_ref,
              fingerprint,
              valid_from, valid_to
            ) VALUES (?, 1, 'pending', 'raw Make app-version specs', '', '',
            NULL, ?, ?, ?, ?, ?, NULL)
            """,
            (
                (
                    unit_number,
                    OBSERVED_AT,
                    "test_fixture ",
                    "tests/mcp/tool_contracts/mcp_catalog_plan_semantic_unit_loop_contract.py",
                    _sha256_text(str(unit_number)),
                    OBSERVED_AT,
                )
                for unit_number in range(1, total_units + 1)
            ),
        )


def _seed_raw_spec_manifest(repo_root: Path) -> None:
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=repo_root),
        source=_SemanticUnitRawSpecSource(
            {
                MakeRawSpecTarget(
                    app_slug="slack", app_version="1.0.0"
                ): _slack_raw_spec(),
                MakeRawSpecTarget(
                    app_slug="zz-google-sheets",
                    app_version="1.0.0",
                ): _google_sheets_raw_spec(),
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=OBSERVED_AT,
    )


class _SemanticUnitRawSpecSource:
    """Deterministic raw-spec source for catalog semantic unit fixtures."""

    def __init__(self, specs: Mapping[MakeRawSpecTarget, JsonObject]) -> None:
        self._specs = dict(specs)

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        return self._specs[target]


def _slack_raw_spec() -> JsonObject:
    return {
        "app": {
            "name": "slack ",
            "label": "Slack ",
            "version": "1.0.0",
            "latest": True,
            "manifest": {"version": 2},
            "actions": [
                {
                    "name": "sendMessage ",
                    "label": "Send a Message ",
                    "description": "Sends a message to a Slack channel.",
                    "parameters": [
                        {
                            "name": "__IMTCONN__",
                            "label": "Connection ",
                            "type": "account",
                        }
                    ],
                    "expect": [
                        {
                            "name": "channel ",
                            "label": "Channel ",
                            "type": "select",
                            "required": True,
                            "options": "rpc://slack@1/listChannels",
                        },
                        {
                            "name": "text ",
                            "label": "Text ",
                            "type": "text",
                            "required": True,
                        },
                    ],
                    "interface": [
                        {
                            "name": "messageId ",
                            "label": "Message ID ",
                            "type": "text",
                        }
                    ],
                }
            ],
        }
    }


def _google_sheets_raw_spec() -> JsonObject:
    return {
        "app": {
            "name": "zz-google-sheets ",
            "label": "Google Sheets ",
            "version": "1.0.0",
            "latest": True,
            "manifest": {"version": 2},
            "actions": [],
        }
    }


def _connect_seed_database(repo_root: Path) -> sqlite3.Connection:
    return sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
