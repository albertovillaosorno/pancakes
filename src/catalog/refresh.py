# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.schema-policy
# - 001062#repo.paths.data.persistent-root-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Source-injected raw-spec and catalog refresh command.

Boundary contract:
- Owns: the local command flow from injected raw-spec source to persisted
catalog.
- Must not: create live clients, run services, validate blueprints, or call AI.
- Allows: coordinating scraper sync, catalog compilation, and data/ persistence.
- Split when: live credential setup, scheduling, or drift reporting becomes
separate.
- Merge when: another command runs the same refresh flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from languages.make.raw_specs.manifest import load_raw_spec_manifest
from languages.make.raw_specs.sqlite_store import (
    RAW_SPEC_SQLITE_MANIFEST_PATH,
    load_sqlite_raw_spec_bundle,
)
from languages.make.raw_specs.sync import sync_raw_specs

from catalog.compiler import compile_catalog_from_manifest
from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH, build_knowledge_store
from catalog.storage import (
    DEFAULT_CATALOG_SNAPSHOT_PATH,
    write_catalog_snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path

    from languages.make.raw_specs.config import MakeScraperConfig
    from languages.make.raw_specs.models import (
        MakeRawSpecSource,
        RawSpecSourceMetadata,
    )


class CatalogRefreshReport(NamedTuple):
    """Summary for one repository-local catalog refresh command."""

    raw_spec_dir: str
    raw_spec_manifest_path: str
    raw_spec_manifest_sha256: str
    catalog_snapshot_path: str
    catalog_fingerprint: str
    knowledge_database_path: str
    knowledge_fingerprint: str
    targets_seen: int
    files_written: int


def refresh_catalog_from_source(
    *,
    config: MakeScraperConfig,
    source: MakeRawSpecSource,
    source_metadata: RawSpecSourceMetadata,
    catalog_snapshot_path: Path = DEFAULT_CATALOG_SNAPSHOT_PATH,
    generated_at_utc: str | None = None,
) -> CatalogRefreshReport:
    """Refresh raw specs and persist the compiled catalog snapshot.

    Returns:
        The result produced by refresh raw specs and persist the compiled
        catalog snapshot.
    """
    sync_report = sync_raw_specs(
        config=config,
        source=source,
        source_metadata=source_metadata,
        generated_at_utc=generated_at_utc,
    )
    sqlite_bundle = load_sqlite_raw_spec_bundle(
        database_path=config.resolved_sqlite_database_path()
    )
    manifest = (
        sqlite_bundle.manifest
        if sqlite_bundle is not None
        else load_raw_spec_manifest(config.resolved_manifest_path())
    )
    snapshot = compile_catalog_from_manifest(
        repo_root=config.repo_root, manifest=manifest
    )
    catalog_report = write_catalog_snapshot(
        repo_root=config.repo_root,
        snapshot=snapshot,
        snapshot_path=catalog_snapshot_path,
    )
    knowledge_report = build_knowledge_store(
        repo_root=config.repo_root,
        database_path=DEFAULT_KNOWLEDGE_DB_PATH,
    )
    return CatalogRefreshReport(
        raw_spec_dir=manifest.raw_spec_dir,
        raw_spec_manifest_path=RAW_SPEC_SQLITE_MANIFEST_PATH,
        raw_spec_manifest_sha256=manifest.manifest_sha256,
        catalog_snapshot_path=catalog_report.snapshot_path,
        catalog_fingerprint=catalog_report.fingerprint,
        knowledge_database_path=knowledge_report.database_path,
        knowledge_fingerprint=knowledge_report.fingerprint,
        targets_seen=sync_report.targets_seen,
        files_written=sync_report.files_written,
    )
