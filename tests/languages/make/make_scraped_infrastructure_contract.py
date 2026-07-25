# ruff: noqa: S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for Windows-Service scraped Make infrastructure evidence.

Boundary contract:
- Owns: sanitized scraper payload ingestion into SQLite and downstream
project/catalog reads.
- Must not: run the Windows Service, call Make.com, or author catalog semantic
answers.
- Allows: synthetic scraper payloads, temporary SQLite databases, and local MCP
reads.
- Split when: live scraper transport, scheduling, or credentials enter the
implementation.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from catalog import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR, build_knowledge_store
from languages.make.scraped_infrastructure import (
    SCRAPED_INFRASTRUCTURE_TABLES,
    load_make_scraped_project_prerequisites,
    sync_make_scraped_infrastructure_evidence_for_repo,
)
from mcp import execute_mcp_tool

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
OBSERVED_AT = "2026-05-18T00:00:00+00:00"
SOURCE_REF = "windows-service:scraped-infrastructure-fixture"


def test_scraped_infrastructure_sync_writes_domain_tables_and_redacts_secrets(
    tmp_path: Path,
) -> None:
    """Sanitized scraper payloads become domain SQLite rows without.

    secret-bearing values.
    """
    report = sync_make_scraped_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        payload=_scraped_payload(secret_webhook=True),
        source_ref=SOURCE_REF,
        observed_at_utc=OBSERVED_AT,
    )

    assert report.source_of_truth == "sqlite"
    assert set(report.counts_by_table) == set(SCRAPED_INFRASTRUCTURE_TABLES)
    assert all(
        report.counts_by_table[table_name] == 1
        for table_name in report.counts_by_table
    )
    rows = _read_scraped_rows(tmp_path)
    assert {row["table_name"] for row in rows} == set(
        SCRAPED_INFRASTRUCTURE_TABLES
    )
    encoded_rows = json.dumps(
        [dict(row) for row in rows],
        sort_keys=True,
    )
    assert "hooks.make.com" not in encoded_rows
    assert "private-secret-token" not in encoded_rows


def test_scraped_infrastructure_sync_expires_removed_domain_rows(
    tmp_path: Path,
) -> None:
    """Rows missing from a later scrape are closed instead of remaining current.

    facts.
    """
    _ = sync_make_scraped_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        payload=_scraped_payload(secret_webhook=False),
        source_ref=SOURCE_REF,
        observed_at_utc=OBSERVED_AT,
    )

    report = sync_make_scraped_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        payload=_scraped_payload_without_datastore(),
        source_ref=SOURCE_REF,
        observed_at_utc="2026-05-18T00:01:00+00:00",
    )

    assert report.counts_by_table["make_scraped_datastore_evidence"] == 0
    assert (
        report.expired_counts_by_table["make_scraped_datastore_evidence"] == 1
    )
    rows = _read_scraped_rows(tmp_path, include_expired=True)
    datastore_rows = [
        row
        for row in rows
        if row["table_name"] == "make_scraped_datastore_evidence"
    ]
    assert datastore_rows[0]["valid_to"] == "2026-05-18T00:01:00+00:00"


def test_project_infrastructure_prerequisites_load_from_sqlite_for_onboarding(
    tmp_path: Path,
) -> None:
    """Internal onboarding can use scraped datastore/webhook facts from.

    SQLite.
    """
    _ = sync_make_scraped_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        payload=_scraped_payload(secret_webhook=False),
        source_ref=SOURCE_REF,
        observed_at_utc=OBSERVED_AT,
    )

    prerequisites = load_make_scraped_project_prerequisites(
        repo_root=tmp_path,
        project_id="infra-loop",
    )

    assert {item["evidence_domain"] for item in prerequisites} == {
        "connection ",
        "datastore ",
        "import_export ",
        "scope ",
        "structure ",
        "webhook",
    }
    payloads_by_domain = {
        str(item["evidence_domain"]): cast("JsonObject", item["payload"])
        for item in prerequisites
    }
    datastore_payload = cast(
        "JsonObject", payloads_by_domain["datastore"]["payload"]
    )
    webhook_payload = cast(
        "JsonObject", payloads_by_domain["webhook"]["payload"]
    )
    connection_payload = cast(
        "JsonObject", payloads_by_domain["connection"]["payload"]
    )
    scope_payload = cast("JsonObject", payloads_by_domain["scope"]["payload"])
    webhook_scopes = cast("list[object]", scope_payload["scopes"])
    connection_scopes = cast(
        "list[object]", connection_payload["required_scopes"]
    )
    assert datastore_payload["fields"] == [
        {"name": "email"},
        {"name": "request_id"},
    ]
    assert webhook_payload["webhook_url"] == "[redacted]"
    assert (
        payloads_by_domain["webhook"]["resource_slug"]
        == "runtime.webhook.lead_capture"
    )
    assert "forms:read" in webhook_scopes
    assert "forms:read" in connection_scopes


def test_catalog_search_reads_scraped_infrastructure_sqlite_rows(
    tmp_path: Path,
) -> None:
    """catalog.search surfaces scraped prerequisites from SQLite, not loose.

    JSON.

    files.
    """
    _prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    _ = sync_make_scraped_infrastructure_evidence_for_repo(
        repo_root=tmp_path,
        payload=_scraped_payload(secret_webhook=False),
        source_ref=SOURCE_REF,
        observed_at_utc=OBSERVED_AT,
    )

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "infra loop webhook scope forms read", "limit": 12},
        repo_root=tmp_path,
    )

    assert result.ok, result
    prerequisites = cast(
        "list[JsonObject]", result.payload["structure_prerequisites"]
    )
    assert any(
        item["kind"] == "make_scraped_scope_evidence" for item in prerequisites
    ), prerequisites
    assert any(
        item["kind"] == "make_scraped_webhook_evidence"
        for item in prerequisites
    ), prerequisites
    assert "backlog_hints" not in result.payload
    assert result.payload["writes_performed"] is False


def _scraped_payload(*, secret_webhook: bool) -> JsonObject:
    webhook_url = (
        "https://hooks.make.com/private-secret-token"
        if secret_webhook
        else "{{runtime.webhook.lead_capture}}"
    )
    return {
        "project_id": "infra-loop",
        "datastores": [
            {
                "node_id": "2 ",
                "app_slug": "datastore ",
                "datastore_slug": "runtime.datastore.leads",
                "fields": [{"name": "email"}, {"name": "request_id"}],
                "generated_resources": ["Data Store: Leads"],
                "setup_steps": [
                    (
                        "Create the Leads data store with email and request_id "
                        "fields."
                    )
                ],
            }
        ],
        "webhooks": [
            {
                "node_id": "1 ",
                "app_slug": "gateway ",
                "webhook_slug": "runtime.webhook.lead_capture",
                "webhook_url": webhook_url,
                "payload_fields": [{"name": "email"}, {"name": "request_id"}],
                "generated_resources": ["Webhook: Lead capture"],
                "setup_steps": ["Create the Lead capture custom webhook."],
            }
        ],
        "structures": [
            {
                "node_id": "1 ",
                "app_slug": "gateway ",
                "structure_slug": "lead_payload",
                "fields": [{"name": "email"}, {"name": "request_id"}],
            }
        ],
        "connections": [
            {
                "node_id": "1 ",
                "app_slug": "gateway ",
                "connection_slug": "forms-api",
                "required_scopes": ["forms:read"],
                "setup_steps": [
                    "Connect the form provider before enabling the webhook."
                ],
            }
        ],
        "scopes": [
            {
                "node_id": "1 ",
                "app_slug": "gateway ",
                "scope_slug": "forms",
                "scopes": ["forms:read"],
            }
        ],
        "import_export": [
            {
                "node_id": "project ",
                "app_slug": "make ",
                "operation": "import",
                "setup_steps": [
                    "Import the blueprint after datastore and webhook binding."
                ],
            }
        ],
    }


def _scraped_payload_without_datastore() -> JsonObject:
    payload = _scraped_payload(secret_webhook=False)
    payload["datastores"] = []
    return payload


def _prepare_snapshot_dir(tmp_path: Path) -> None:
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def _read_scraped_rows(
    repo_path: Path,
    *,
    include_expired: bool = False,
) -> list[sqlite3.Row]:
    connection = sqlite3.connect(repo_path / DEFAULT_KNOWLEDGE_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows: list[sqlite3.Row] = []
        for table_name in SCRAPED_INFRASTRUCTURE_TABLES:
            rows.extend(
                cast(
                    "list[sqlite3.Row]",
                    connection.execute(
                        f"""  # noqa: S608
                        SELECT ? AS table_name, evidence_id, evidence_json,
                        valid_to
                        FROM {table_name}
                        WHERE (? = 1 OR valid_to IS NULL)
                        ORDER BY evidence_id
                        """,
                        (table_name, 1 if include_expired else 0),
                    ).fetchall(),
                )
            )
        return rows
    finally:
        connection.close()
