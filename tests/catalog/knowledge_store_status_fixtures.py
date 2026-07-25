# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Shared fixtures for Make knowledge-store status contracts.

Boundary contract:
- Owns: reusable raw-spec, SQL snapshot, and manifest-tamper fixtures for
  knowledge-store status tests.
- Must not: assert status behavior, invoke CLI, or contact live services.
- Allows: temporary repository setup, deterministic raw-spec fixtures, and
  DAMP helper data shared by focused status contracts.
- Split when: status fixtures diverge from CLI fixtures or need live adapters.
- Merge when: direct and CLI status tests no longer share setup behavior.
"""

from __future__ import annotations

import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING

from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    sync_raw_specs,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from languages.make.raw_specs.models import JsonObject

REPO_ROOT = repo_root()
FIXED_GENERATED_AT = "2026-04-30T00:00:00+00:00"
NEXT_GENERATED_AT = "2026-05-01T00:00:00+00:00"
EXPECTED_PROMOTED_COURSE_CLAIMS = 59
EXPECTED_CLAIM_EVIDENCE = 0
EXPECTED_CLAIM_CONFLICTS = 0
EXPECTED_NATIVE_EXPECTATIONS = 12
EXPECTED_TRANSACTION_PROFILES = 3
DEFAULT_DATABASE_PATH = "src/data/pancakes.sqlite"
DEFAULT_RAW_SPEC_MANIFEST_PATH = "temp/raw-specs-json/manifest.json"
EXPECTED_DB_ENSURE_COMMAND = "python -B -m catalog.knowledge ensure"
EXPECTED_RECOMMENDED_COMMANDS = (EXPECTED_DB_ENSURE_COMMAND,)


class InMemoryRawSpecSource:
    """Deterministic raw-spec source for status tests."""

    def __init__(self, specs: Mapping[MakeRawSpecTarget, JsonObject]) -> None:
        """Store raw specs by target."""
        self._specs = dict(specs)

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return the in-memory targets."""
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return the in-memory raw spec payload for one target."""
        return self._specs[target]


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def create_empty_sqlite_database(tmp_path: Path) -> None:
    """Create an empty SQLite DB file at the default knowledge-store path."""
    database_path = tmp_path / DEFAULT_DATABASE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.close()


def sync_http_raw_spec(
    tmp_path: Path,
    *,
    generated_at: str,
    action_label: str = "Make a request",
) -> None:
    """Write one HTTP raw spec fixture and manifest into a temporary repo."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource(
            {target: http_raw_spec(action_label=action_label)}
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=generated_at,
    )


def corrupt_manifest_timestamp(tmp_path: Path) -> None:
    """Tamper SQLite raw-spec rows without updating their stored digest."""
    database_path = tmp_path / DEFAULT_DATABASE_PATH
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            """
            UPDATE make_raw_spec_payloads
            SET payload_json = ?
            WHERE valid_to IS NULL
            """,
            ("{}",),
        )
        connection.commit()
    finally:
        connection.close()


def http_raw_spec(*, action_label: str) -> JsonObject:
    """Return a minimal HTTP raw spec fixture."""
    return {
        "app": {
            "name": "http",
            "version": "1.0",
            "label": "HTTP",
            "latest": True,
            "manifest": {"version": 2},
            "actions": [
                {
                    "name": "makeRequest",
                    "label": action_label,
                    "parameters": [
                        {"name": "url", "type": "url", "required": True}
                    ],
                    "interface": [{"name": "statusCode", "type": "number"}],
                }
            ],
        }
    }
