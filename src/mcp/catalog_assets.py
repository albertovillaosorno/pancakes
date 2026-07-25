# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-specs.repo-local-cache
# - 001042#repo.make-catalog.raw-specs-and-catalog-authority
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Shared MCP missing-catalog asset payloads.

Boundary contract:
- Owns: missing local catalog asset model and recovery payload projection for
MCP tools.
- Must not: load catalogs, validate blueprints, execute recovery commands, or do
live calls.
- Allows: deterministic repository-relative missing path discovery and
JSON-ready payloads.
- Split when: non-MCP catalog packages need their own missing-asset domain
model.
- Merge when: project, executor, and scenario-builder tools stop sharing this
response shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from catalog import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.fallback.query import DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT
from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
)
from languages.make.raw_specs.sqlite_store import load_sqlite_raw_spec_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.models import JsonObject, MissingCatalogAssetsPayload

MISSING_LOCAL_ASSETS_STATUS: Final = "missing_local_assets"
CATALOG_BACKED_IMPORT_READY_CLAIM_LEVEL: Final = "catalog_backed_import_ready"
LOCAL_CATALOG_ASSET_RECOVERY_COMMANDS: Final[tuple[str, ...]] = (
    "python -B -m languages.make.raw_specs --repo-root <repo> refresh",
    "python -B -m catalog.knowledge --repo-root <repo> build",
)


class MissingCatalogAssets(NamedTuple):
    """Missing local catalog assets required by MCP tools."""

    missing_paths: tuple[str, ...]
    recommended_commands: tuple[str, ...] = (
        LOCAL_CATALOG_ASSET_RECOVERY_COMMANDS
    )
    required_for_claim_level: str = CATALOG_BACKED_IMPORT_READY_CLAIM_LEVEL
    status: str = MISSING_LOCAL_ASSETS_STATUS

    def payload(self) -> MissingCatalogAssetsPayload:
        """Return the shared JSON-ready missing-asset payload."""
        return {
            "status": self.status,
            "missing_paths": list(self.missing_paths),
            "recommended_commands": list(self.recommended_commands),
            "required_for_claim_level": self.required_for_claim_level,
        }

    def catalog_plan_payload(self) -> JsonObject:
        """Return missing-asset payload fields for catalog planning surfaces."""
        return {
            **self.payload(),
            "advisory_only": False,
            "required_for_workflow": True,
            "fallback_candidate_limit": DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT,
        }

    def source_payload(self, *, database_path: str | None = None) -> JsonObject:
        """Return missing-asset payload fields for scenario-builder source.

        metadata.
        """
        payload: JsonObject = dict(self.payload())
        if database_path is not None:
            payload["database_path"] = database_path
        return payload


def missing_local_catalog_assets(repo_root: Path) -> MissingCatalogAssets:
    """Return the shared missing local catalog asset model for one repository.

    root.
    """
    return MissingCatalogAssets(
        missing_paths=missing_local_catalog_asset_paths(repo_root)
    )


def missing_local_assets_catalog_plan(
    *, missing_paths: tuple[str, ...]
) -> JsonObject:
    """Return structured recovery guidance for absent local catalog assets."""
    return MissingCatalogAssets(
        missing_paths=missing_paths
    ).catalog_plan_payload()


def missing_local_catalog_asset_paths(repo_root: Path) -> tuple[str, ...]:
    """Return the computed result for the caller."""
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    missing_paths: list[str] = []
    if not database_path.is_file():
        missing_paths.append(relative_to_repo(repo_root, database_path))
        return tuple(missing_paths)
    if load_sqlite_raw_spec_bundle(database_path=database_path) is None:
        missing_paths.append(relative_to_repo(repo_root, database_path))
    return tuple(missing_paths)
