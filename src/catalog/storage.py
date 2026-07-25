# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001033#repo.paths.no-output-outside-repository
# - 001042#repo.make-catalog.schema-policy
# - 001062#repo.paths.data.domain-owned-data-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Persistent catalog snapshot storage.

Boundary contract:
- Owns: repository-confined catalog snapshot writes under persistent data paths.
- Must not: compile raw specs, fetch upstream data, or choose refresh sources.
- Allows: deterministic JSON persistence and repo-relative write reports.
- Split when: catalog storage gains readers, indexes, or versioned retention.
- Merge when: another module writes the same catalog snapshot artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
)

from catalog.json_payloads import (
    canonical_catalog_bytes,
    catalog_snapshot_to_json,
)
from catalog.validation import validate_catalog_snapshot

if TYPE_CHECKING:
    from catalog.models import CatalogSnapshot

DEFAULT_CATALOG_SNAPSHOT_PATH: Final[Path] = Path(
    "src/languages/make/data/catalog/catalog.json"
)


class CatalogSnapshotWriteReport(NamedTuple):
    """Result for one persistent catalog snapshot write."""

    snapshot_path: str
    fingerprint: str
    raw_spec_manifest_sha256: str


def write_catalog_snapshot(
    *,
    repo_root: Path,
    snapshot: CatalogSnapshot,
    snapshot_path: Path = DEFAULT_CATALOG_SNAPSHOT_PATH,
) -> CatalogSnapshotWriteReport:
    """Write one catalog snapshot under the repository data workspace.

    Returns:
        The written repository-local path or status.

    Raises:
        OSError: If filesystem access fails.
    """
    validate_catalog_snapshot(snapshot)
    output_path = resolve_repo_relative_path(repo_root, snapshot_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = canonical_catalog_bytes(catalog_snapshot_to_json(snapshot))
    written_bytes = output_path.write_bytes(payload_bytes)
    if written_bytes != len(payload_bytes):
        message = f"Could not write full catalog snapshot to {output_path}."
        raise OSError(message)
    return CatalogSnapshotWriteReport(
        snapshot_path=relative_to_repo(repo_root, output_path),
        fingerprint=snapshot.fingerprint,
        raw_spec_manifest_sha256=snapshot.raw_spec_manifest_sha256,
    )
