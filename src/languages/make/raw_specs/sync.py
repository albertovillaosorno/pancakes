# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001033#repo.paths.no-output-outside-repository
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Command boundary for syncing Make raw specs into repository-local SQLite.

Boundary contract:
- Owns: injected-source raw-spec sync into the repository-local SQLite SSOT.
- Must not: create live clients, compile catalogs, render blueprints, or leave
repo.
- Allows: orchestrating source reads, raw-spec rows, and manifest-table refresh.
- Split when: sync gains scheduling, service orchestration, or live credential
setup.
- Merge when: another command performs the same raw-spec sync workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages.make.raw_specs.sqlite_store import sync_raw_specs_to_sqlite

if TYPE_CHECKING:
    from languages.make.raw_specs.config import MakeScraperConfig
    from languages.make.raw_specs.models import (
        MakeRawSpecSource,
        RawSpecSourceMetadata,
        RawSpecSyncReport,
    )


def sync_raw_specs(
    *,
    config: MakeScraperConfig,
    source: MakeRawSpecSource,
    source_metadata: RawSpecSourceMetadata,
    generated_at_utc: str | None = None,
    merge_existing: bool = False,
) -> RawSpecSyncReport:
    """Write raw specs from an injected source into SQLite and refresh manifest.

    rows.

    Returns:
        The SQLite-backed path or status.

    """
    return sync_raw_specs_to_sqlite(
        config=config,
        source=source,
        source_metadata=source_metadata,
        generated_at_utc=generated_at_utc,
        merge_existing=merge_existing,
    )
