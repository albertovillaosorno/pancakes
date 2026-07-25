# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for repository-local raw-spec and catalog refresh data.

Boundary contract:
- Owns: tests for repository-local data/ outputs of the refresh command.
- Must not: contact live Make services, test Windows SCM, or validate
blueprints.
- Allows: deterministic injected raw-spec sources and catalog snapshot
assertions.
- Split when: live refresh, drift reports, or retention policies need coverage.
- Merge when: another raw-spec test owns the same data refresh behavior.
"""

from __future__ import annotations

import json
from shutil import copy2
from typing import TYPE_CHECKING, cast

from catalog import catalog_snapshot_from_json, refresh_catalog_from_source
from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog.models import JsonObject

FIXED_GENERATED_AT = "2026-04-28T00:00:00+00:00"
REPO_ROOT = repo_root()
TRACKED_KNOWLEDGE_RESTORE_SNAPSHOT_NAMES = (
    "schema.sql",
    "aliases.sql",
    "course_rules.sql",
    "designer_message_evidence.sql",
    "live_probe_evidence.sql",
    "native_module_expectations.sql",
    "transaction_profiles.sql",
)


class DataRefreshSource:
    """Deterministic source for data refresh tests."""

    def __init__(self, specs: Mapping[MakeRawSpecTarget, JsonObject]) -> None:
        """Store raw specs by target."""
        self._specs = dict(specs)

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return available targets."""
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return one raw spec payload."""
        return self._specs[target]


def test_refresh_writes_raw_specs_and_catalog_under_make_language_data(
    tmp_path: Path,
) -> None:
    """The refresh command writes repository-local Make data under the language.

    data root.
    """
    copy_knowledge_snapshots(tmp_path)
    generated_dump_path = tmp_path / DEFAULT_DB_SNAPSHOT_DIR / "make.sql"
    _ = generated_dump_path.write_text(
        "select * from generated_dump_must_not_be_executed;\n",
        encoding="utf-8",
    )

    report = refresh_catalog_from_source(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=DataRefreshSource(
            {
                MakeRawSpecTarget(
                    app_slug="http", app_version="1.0"
                ): raw_spec_payload(),
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    assert report.raw_spec_dir == "sqlite:make_raw_spec_payloads", (
        f"Raw specs must be SQLite-backed ingest data: {report}"
    )
    assert (
        report.raw_spec_manifest_path == "sqlite:make_raw_spec_manifest_records"
    ), f"Manifest must be SQLite-backed ingest data: {report}"
    assert report.raw_spec_manifest_sha256, (
        f"Refresh report lost manifest evidence: {report}"
    )
    assert report.targets_seen == 1, (
        f"Refresh report lost manifest evidence: {report}"
    )
    assert (
        report.catalog_snapshot_path
        == "src/languages/make/data/catalog/catalog.json"
    ), f"Catalog snapshot must be persistent data: {report}"
    assert (tmp_path / "src/data/pancakes.sqlite").is_file(), (
        "Refresh command must persist raw-spec evidence in the SQLite SSOT."
    )
    assert not ((tmp_path / "temp").exists()), (
        "Refresh command must delete temp raw-spec JSON after SQLite ingest."
    )

    snapshot_payload = cast(
        "object",
        json.loads(
            (tmp_path / report.catalog_snapshot_path).read_text(
                encoding="utf-8"
            )
        ),
    )
    assert isinstance(snapshot_payload, dict), (
        f"Catalog snapshot must be a JSON object: {snapshot_payload}"
    )
    snapshot_json = cast("JsonObject", snapshot_payload)
    snapshot = catalog_snapshot_from_json(snapshot_json)
    assert snapshot.fingerprint == report.catalog_fingerprint, (
        f"Refresh report and catalog snapshot diverged: {report}"
    )
    assert (
        snapshot.raw_spec_manifest_sha256 == report.raw_spec_manifest_sha256
    ), f"Catalog snapshot must reference the raw-spec manifest: {snapshot}"


def test_raw_spec_ingest_outputs_are_gitignored() -> None:
    """Generated raw-spec ingest payloads stay local-only."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    gitignore_lines = gitignore.splitlines()
    required_patterns = {
        "cache/",
        "src/data/*.sqlite",
        "src/data/*.sqlite*",
        "src/data/*.db",
        "src/data/*.db-*",
        "src/data/sql_snapshots/make.sql",
        "src/data/sql_snapshots/*.dump.sql",
        "src/data/sql_snapshots/*.full.sql",
        "src/data/sql_snapshots/*.backup.sql",
        "src/data/sql_snapshots/*.generated.sql",
    }
    missing_patterns = sorted(required_patterns.difference(gitignore_lines))
    assert not missing_patterns, (
        f"Generated raw-spec ingest payloads are not ignored: "
        f"{missing_patterns}"
    )


def copy_knowledge_snapshots(repo_path: Path) -> None:
    """Copy tracked Make knowledge snapshots into a temporary repository."""
    target_dir = repo_path / DEFAULT_DB_SNAPSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    for snapshot_name in TRACKED_KNOWLEDGE_RESTORE_SNAPSHOT_NAMES:
        _ = copy2(
            REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR / snapshot_name,
            target_dir / snapshot_name,
        )


def raw_spec_payload() -> JsonObject:
    """Build one small Make raw-spec payload.

    Returns:
        The constructed value.
    """
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
                    "label": "Make a request",
                    "parameters": [{"name": "url"}],
                    "interface": [{"name": "statusCode"}],
                }
            ],
        }
    }
