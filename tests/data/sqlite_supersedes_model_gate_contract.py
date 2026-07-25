# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Decision-gate tests for the SQLite supersedes model.

Boundary contract:
- Owns: temporal validity fixtures for raw-spec refresh, catalog invalidation,
dashboard history,
  and rollback evidence.
- Must not: add graph implementation, run catalog semantic batches, or inspect
live Make.com state.
- Allows: in-memory SQLite fixtures and static checks over tracked data
documentation.
- Split when: a future task adds explicit supersedes edges and needs schema
migration coverage.
- Merge when: another data test owns this exact temporal-decision gate.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "data"
    / "fixtures"
    / "sqlite_supersedes_model_gate"
    / "temporal_decision_fixture.json"
)
SCHEMA_SNAPSHOT = REPO_ROOT / "src" / "data" / "sql_snapshots" / "schema.sql"
SQL_SNAPSHOT_README = REPO_ROOT / "src" / "data" / "sql_snapshots" / "README.md"


def test_temporal_validity_answers_raw_spec_refresh_and_rollback() -> None:
    """Raw-spec refresh history needs current and point-in-time queries, not.

    edge traversal.
    """
    fixture = load_fixture()
    timestamps = cast("Mapping[str, str]", fixture["timestamps"])
    with closing(build_fixture_database(fixture)) as connection:
        current_row = fetch_required_row(
            connection.execute(
                """
            SELECT sha256, ingest_run_id
            FROM make_raw_spec_payloads
            WHERE app_slug = ? AND app_version = ? AND valid_to IS NULL
            """,
                ("http", "1.0"),
            )
        )
        first_history_row = raw_spec_at(
            connection, timestamps["between_refreshes"]
        )
        second_history_row = raw_spec_at(
            connection, timestamps["after_second_refresh"]
        )
        rollback_row = fetch_required_row(
            connection.execute(
                """
            SELECT sha256, fingerprint, ingest_run_id
            FROM make_raw_spec_payloads
            WHERE app_slug = ? AND app_version = ? AND valid_to = ?
            ORDER BY valid_from DESC
            LIMIT 1
            """,
                ("http", "1.0", timestamps["second_refresh"]),
            )
        )

    assert row_dict(current_row) == {
        "sha256": "hash-http-v2 ",
        "ingest_run_id": "raw-refresh-0002",
    }
    assert first_history_row["sha256"] == "hash-http-v1"
    assert second_history_row["sha256"] == "hash-http-v2"
    assert row_dict(rollback_row) == {
        "sha256": "hash-http-v1 ",
        "fingerprint": "fingerprint-http-v1 ",
        "ingest_run_id": "raw-refresh-0001",
    }


def test_source_hashes_answer_catalog_invalidation_97393eaf() -> None:
    """Catalog invalidation is a hash comparison against current source.

    truth.
    """
    fixture = load_fixture()
    with closing(build_fixture_database(fixture)) as connection:
        stale_units = fetch_rows(
            connection.execute(
                """
            SELECT units.run_id, units.unit_id, units.source_hash,
            current_sources.sha256
            FROM catalog_units AS units
            JOIN make_raw_spec_payloads AS current_sources
              ON current_sources.source_ref = units.source_ref
             AND current_sources.valid_to IS NULL
            WHERE units.source_hash != current_sources.sha256
            ORDER BY units.unit_id
            """
            )
        )
        active_units = fetch_rows(
            connection.execute(
                """
            SELECT units.run_id, units.unit_id, units.source_hash,
            units.validation_status
            FROM catalog_runs AS runs
            JOIN catalog_units AS units
              ON units.run_id = runs.run_id
            JOIN make_raw_spec_payloads AS current_sources
              ON current_sources.source_ref = units.source_ref
             AND current_sources.valid_to IS NULL
            WHERE runs.run_status = 'active'
              AND runs.reset_strategy = 'canonical_catalog'
              AND units.source_hash = current_sources.sha256
            ORDER BY units.unit_id
            """
            )
        )

    assert [row_dict(row) for row in stale_units] == [
        {
            "run_id": "catalog-run-old ",
            "unit_id": "unit-http-v1 ",
            "source_hash": "hash-http-v1 ",
            "sha256": "hash-http-v2",
        }
    ]
    assert [row_dict(row) for row in active_units] == [
        {
            "run_id": "catalog-run-active ",
            "unit_id": "unit-http-v2 ",
            "source_hash": "hash-http-v2 ",
            "validation_status": "pending",
        }
    ]


def test_temporal_validity_answers_dashboard_history_10c081a9() -> None:
    """Dashboard and package-readiness facts can use the same temporal lookup.

    shape.
    """
    fixture = load_fixture()
    timestamps = cast("Mapping[str, str]", fixture["timestamps"])
    with closing(build_fixture_database(fixture)) as connection:
        before_refresh = readiness_at(
            connection, timestamps["between_refreshes"]
        )
        after_refresh = readiness_at(
            connection, timestamps["after_second_refresh"]
        )
        rollback_evidence = fetch_required_row(
            connection.execute(
                """
            SELECT readiness_status, source_hash, fingerprint, ingest_run_id
            FROM package_readiness_facts
            WHERE subject_id = ? AND valid_to = ?
            ORDER BY valid_from DESC
            LIMIT 1
            """,
                ("package:http-import", timestamps["second_refresh"]),
            )
        )

    assert row_dict(before_refresh) == {
        "readiness_status": "ready ",
        "source_hash": "hash-http-v1",
    }
    assert row_dict(after_refresh) == {
        "readiness_status": "needs_review ",
        "source_hash": "hash-http-v2",
    }
    assert row_dict(rollback_evidence) == {
        "readiness_status": "ready ",
        "source_hash": "hash-http-v1 ",
        "fingerprint": "readiness-fingerprint-v1 ",
        "ingest_run_id": "readiness-run-0001",
    }


def test_supersedes_decision_is_documented_and_schema_free() -> None:
    """The gate remains a measured decision, not an unowned graph schema.

    change.
    """
    fixture = load_fixture()
    schema_text = SCHEMA_SNAPSHOT.read_text(encoding="utf-8").casefold()
    readme_text = SQL_SNAPSHOT_README.read_text(encoding="utf-8")

    assert fixture["decision"] == "no_explicit_supersedes_edges_required"
    assert "supersedes" not in schema_text
    assert "SQLite Supersedes Model Gate" in readme_text
    assert (
        "no query currently requires explicit supersedes edges" in readme_text
    )
    assert "raw-spec refresh" in readme_text
    assert "catalog invalidation" in readme_text
    assert "dashboard history" in readme_text
    assert "rollback evidence" in readme_text
    assert "Future explicit supersedes edges" in readme_text
    assert "require a new TODO" in readme_text
    assert fixture["measured_queries"] == [
        "current raw spec by app/version ",
        "point-in-time raw spec by app/version ",
        "catalog units stale against current source hash ",
        "active canonical catalog run by source hash ",
        "point-in-time package readiness history ",
        "previous package readiness row for rollback evidence",
    ]


def raw_spec_at(connection: sqlite3.Connection, timestamp: str) -> sqlite3.Row:
    """Return the raw spec row visible at one timestamp."""
    return fetch_required_row(
        connection.execute(
            """
        SELECT sha256, ingest_run_id
        FROM make_raw_spec_payloads
        WHERE app_slug = ?
          AND app_version = ?
          AND valid_from <= ?
          AND (valid_to > ? OR valid_to IS NULL)
        """,
            ("http", "1.0", timestamp, timestamp),
        ),
        context=f"raw-spec row at {timestamp}",
    )


def readiness_at(connection: sqlite3.Connection, timestamp: str) -> sqlite3.Row:
    """Return the package-readiness fact visible at one timestamp."""
    return fetch_required_row(
        connection.execute(
            """
        SELECT readiness_status, source_hash
        FROM package_readiness_facts
        WHERE subject_id = ?
          AND valid_from <= ?
          AND (valid_to > ? OR valid_to IS NULL)
        """,
            ("package:http-import", timestamp, timestamp),
        ),
        context=f"readiness row at {timestamp}",
    )


def load_fixture() -> Mapping[str, object]:
    """Return the computed result for the caller."""
    payload = cast(
        "object", json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, Mapping)
    return cast("Mapping[str, object]", payload)


def build_fixture_database(fixture: Mapping[str, object]) -> sqlite3.Connection:
    """Return the computed result for the caller."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    _ = connection.executescript(
        """
        CREATE TABLE make_raw_spec_payloads (
          app_slug TEXT NOT NULL,
          app_version TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          fingerprint TEXT NOT NULL,
          ingest_run_id TEXT NOT NULL,
          PRIMARY KEY (app_slug, app_version, valid_from)
        );

        CREATE TABLE catalog_runs (
          run_id TEXT PRIMARY KEY,
          run_status TEXT NOT NULL,
          reset_strategy TEXT NOT NULL
        );

        CREATE TABLE catalog_units (
          run_id TEXT NOT NULL,
          unit_id TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          validation_status TEXT NOT NULL,
          PRIMARY KEY (run_id, unit_id)
        );

        CREATE TABLE package_readiness_facts (
          fact_id TEXT PRIMARY KEY,
          subject_id TEXT NOT NULL,
          readiness_status TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          fingerprint TEXT NOT NULL,
          ingest_run_id TEXT NOT NULL
        );
        """
    )
    insert_raw_spec_rows(connection, fixture)
    insert_catalog_rows(connection, fixture)
    insert_readiness_rows(connection, fixture)
    return connection


def insert_raw_spec_rows(
    connection: sqlite3.Connection, fixture: Mapping[str, object]
) -> None:
    """Insert raw-spec refresh rows."""
    rows = cast("list[Mapping[str, object]]", fixture["raw_spec_refresh_rows"])
    _ = connection.executemany(
        """
        INSERT INTO make_raw_spec_payloads (
          app_slug, app_version, source_ref, sha256, valid_from, valid_to,
          fingerprint, ingest_run_id
        )
        VALUES (
          :app_slug, :app_version, :source_ref, :sha256, :valid_from, :valid_to,
          :fingerprint, :ingest_run_id
        )
        """,
        rows,
    )


def insert_catalog_rows(
    connection: sqlite3.Connection, fixture: Mapping[str, object]
) -> None:
    """Insert canonical catalog run and unit rows."""
    runs = cast("list[Mapping[str, object]]", fixture["catalog_runs"])
    units = cast("list[Mapping[str, object]]", fixture["catalog_units"])
    _ = connection.executemany(
        """
        INSERT INTO catalog_runs (run_id, run_status, reset_strategy)
        VALUES (:run_id, :run_status, :reset_strategy)
        """,
        runs,
    )
    _ = connection.executemany(
        """
        INSERT INTO catalog_units (
          run_id, unit_id, source_ref, source_hash, validation_status
        )
        VALUES (
          :run_id, :unit_id, :source_ref, :source_hash, :validation_status
        )
        """,
        units,
    )


def insert_readiness_rows(
    connection: sqlite3.Connection, fixture: Mapping[str, object]
) -> None:
    """Insert dashboard package-readiness history rows."""
    rows = cast(
        "list[Mapping[str, object]]", fixture["package_readiness_facts"]
    )
    _ = connection.executemany(
        """
        INSERT INTO package_readiness_facts (
          fact_id, subject_id, readiness_status, source_hash, valid_from,
          valid_to,
          fingerprint, ingest_run_id
        )
        VALUES (
          :fact_id, :subject_id, :readiness_status, :source_hash, :valid_from,
          :valid_to,
          :fingerprint, :ingest_run_id
        )
        """,
        rows,
    )


def fetch_required_row(
    cursor: sqlite3.Cursor, context: str = "query row"
) -> sqlite3.Row:
    """Return the computed result for the caller."""
    row = cast("object", cursor.fetchone())
    assert isinstance(row, sqlite3.Row), f"Expected {context}"
    return row


def fetch_rows(cursor: sqlite3.Cursor) -> list[sqlite3.Row]:
    """Return the computed result for the caller."""
    rows = cast("list[object]", cursor.fetchall())
    typed_rows: list[sqlite3.Row] = []
    for raw_row in rows:
        assert isinstance(raw_row, sqlite3.Row)
        typed_rows.append(raw_row)
    return typed_rows


def row_dict(row: sqlite3.Row) -> dict[str, object]:
    """Return the computed result for the caller."""
    keys = row.keys()
    return {key: cast("object", row[key]) for key in keys}
