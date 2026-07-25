# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for Make-native infrastructure JSON evidence extraction.

Boundary contract:
- Owns: datastore and webhook setup-shape evidence ingestion into SQLite.
- Must not: call Make.com, author catalog semantic answers, or use loose JSON
ledgers.
- Allows: synthetic sanitized Make blueprints and temporary SQLite databases.
- Split when: Windows service scraper ingestion owns live datastore/webhook
collection.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from blueprints.ast.parser import parse_make_ast
from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR, DEFAULT_KNOWLEDGE_DB_PATH
from catalog.knowledge.storage import build_knowledge_store
from languages.make.native_infrastructure import (
    extract_make_infrastructure_evidence_from_payload,
    sync_make_infrastructure_evidence_for_repo,
)
from mcp import execute_mcp_tool

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
OBSERVED_AT = "2026-05-18T00:00:00+00:00"
SCENARIO_REF = "projects/infra-loop/scenario.json"


def test_make_native_infrastructure_extraction_redacts_resource_values() -> (
    None
):
    """Datastore and webhook structures are extracted without durable.

    secret-bearing values.
    """
    records = extract_make_infrastructure_evidence_from_payload(
        _infrastructure_scenario(secret_webhook_url=True),
        source_ref=SCENARIO_REF,
        observed_at_utc=OBSERVED_AT,
    )

    assert len(records) == 2
    datastore = next(
        record
        for record in records
        if record.evidence_kind == "datastore_structure"
    )
    webhook = next(
        record
        for record in records
        if record.evidence_kind == "webhook_structure"
    )
    datastore_payload = cast("JsonObject", json.loads(datastore.structure_json))
    webhook_payload = cast("JsonObject", json.loads(webhook.structure_json))
    datastore_fields = cast("list[JsonObject]", datastore_payload["fields"])

    assert datastore.resource_slug == "runtime.datastore.leads"
    assert datastore_payload["field_count"] == 2
    assert [field["name"] for field in datastore_fields] == [
        "email",
        "request_id",
    ]
    assert webhook_payload["resource_binding"] == {
        "binding_source": "literal_redacted",
        "placeholder": None,
        "raw_value_redacted": True,
    }
    encoded_webhook_payload = json.dumps(webhook_payload, sort_keys=True)
    assert "hooks.make.com" not in encoded_webhook_payload
    assert "private-secret-token" not in encoded_webhook_payload


def test_make_native_infrastructure_sync_writes_current_sqlite_rows(
    tmp_path: Path,
) -> None:
    """SQLite becomes the durable ledger for parsed Make infrastructure.

    shapes.
    """
    root = parse_make_ast(_infrastructure_scenario(secret_webhook_url=False))

    report = sync_make_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        root=root,
        source_ref=SCENARIO_REF,
        observed_at_utc=OBSERVED_AT,
    )

    assert report.source_of_truth == "sqlite"
    assert report.datastore_record_count == 1
    assert report.webhook_record_count == 1
    assert report.expired_datastore_record_count == 0
    rows = _read_structure_rows(tmp_path)
    assert {row["table_name"] for row in rows} == {
        "make_datastore_structure_evidence",
        "make_webhook_structure_evidence",
    }
    assert all(
        row["source_kind"] == "make_native_json_analyzer" for row in rows
    )
    assert all(row["valid_to"] is None for row in rows)


def test_make_native_infrastructure_sync_expires_removed_source_rows(
    tmp_path: Path,
) -> None:
    """Rows for removed infrastructure nodes are closed instead of becoming.

    orphan facts.
    """
    first_root = parse_make_ast(
        _infrastructure_scenario(secret_webhook_url=False)
    )
    second_root = parse_make_ast(
        {
            "name": "Infrastructure Loop",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {"hook": "{{runtime.webhook.lead_capture}}"},
                    "metadata": {
                        "interface": [{"name": "email", "type": "text"}]
                    },
                }
            ],
        }
    )

    _ = sync_make_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        root=first_root,
        source_ref=SCENARIO_REF,
        observed_at_utc=OBSERVED_AT,
    )
    second_report = sync_make_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        root=second_root,
        source_ref=SCENARIO_REF,
        observed_at_utc="2026-05-18T00:01:00+00:00",
    )

    assert second_report.datastore_record_count == 0
    assert second_report.expired_datastore_record_count == 1
    rows = _read_structure_rows(tmp_path)
    datastore_rows = [
        row
        for row in rows
        if row["table_name"] == "make_datastore_structure_evidence"
    ]
    assert datastore_rows[0]["valid_to"] == "2026-05-18T00:01:00+00:00"


def test_make_native_infrastructure_evidence_is_visible_to_catalog_search(
    tmp_path: Path,
) -> None:
    """catalog.search reads the ingested SQLite evidence instead of loose JSON.

    files.
    """
    _prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    root = parse_make_ast(_infrastructure_scenario(secret_webhook_url=False))
    _ = sync_make_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        root=root,
        source_ref=SCENARIO_REF,
        observed_at_utc=OBSERVED_AT,
    )

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "webhook payload email fields", "limit": 8},
        repo_root=tmp_path,
    )

    assert result.ok, result
    structure_rows = cast(
        "list[JsonObject]", result.payload["structure_prerequisites"]
    )
    webhook_row = next(
        row
        for row in structure_rows
        if row["kind"] == "make_webhook_structure_evidence"
    )
    assert {row["kind"] for row in structure_rows} >= {
        "make_datastore_structure_evidence",
        "make_webhook_structure_evidence",
    }
    assert webhook_row["evidence_status"] == "populated"
    assert webhook_row["blocking"] is False
    assert set(cast("list[str]", webhook_row["structure_field_paths"])) >= {
        "email",
        "request_id",
    }
    assert result.payload["writes_performed"] is False


def _infrastructure_scenario(*, secret_webhook_url: bool) -> JsonObject:
    hook_value = (
        "https://hooks.make.com/private-secret-token"
        if secret_webhook_url
        else "{{runtime.webhook.lead_capture}}"
    )
    return {
        "name": "Infrastructure Loop",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": hook_value},
                "mapper": {
                    "email": "{{1.email}}",
                    "request_id": "{{1.request_id}}",
                },
                "metadata": {
                    "interface": [
                        {"name": "email", "type": "email"},
                        {"name": "request_id", "type": "text"},
                    ]
                },
            },
            {
                "id": 2,
                "module": "datastore:AddRecord",
                "parameters": {"datastore": "{{runtime.datastore.leads}}"},
                "mapper": {
                    "key": "{{1.request_id}}",
                    "data": {
                        "email": "{{1.email}}",
                        "request_id": "{{1.request_id}}",
                    },
                },
            },
        ],
    }


def _prepare_snapshot_dir(tmp_path: Path) -> None:
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def _read_structure_rows(repo_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(repo_path / DEFAULT_KNOWLEDGE_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        datastore_rows = cast(
            "list[sqlite3.Row]",
            connection.execute(
                """
                SELECT 'make_datastore_structure_evidence' AS table_name,
                       evidence_id, source_kind, valid_to
                FROM make_datastore_structure_evidence
                ORDER BY evidence_id
                """
            ).fetchall(),
        )
        webhook_rows = cast(
            "list[sqlite3.Row]",
            connection.execute(
                """
                SELECT 'make_webhook_structure_evidence' AS table_name,
                       evidence_id, source_kind, valid_to
                FROM make_webhook_structure_evidence
                ORDER BY evidence_id
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    return [*datastore_rows, *webhook_rows]
