# ruff: noqa: PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001033#repo.paths.no-output-outside-repository
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Read-side raw-spec refresh status helpers.

Boundary contract:
- Owns: read-side availability status for retained raw-spec artifacts.
- Must not: fetch upstream data, mutate manifests, compile catalogs, or repair
specs.
- Allows: repo-confined manifest loading and missing-file detection.
- Split when: status needs live health checks or service orchestration.
- Merge when: another status module reports the same raw-spec availability view.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Final

from languages.make.raw_specs.manifest import load_raw_spec_manifest
from languages.make.raw_specs.models import RawSpecRefreshStatus
from languages.make.raw_specs.paths import resolve_repo_relative_path
from languages.make.raw_specs.sqlite_store import (
    RAW_SPEC_SQLITE_DIR,
    RAW_SPEC_SQLITE_MANIFEST_PATH,
    load_sqlite_raw_spec_bundle,
)

if TYPE_CHECKING:
    from languages.make.raw_specs.config import MakeScraperConfig
    from languages.make.raw_specs.models import RawSpecManifest

AUTOMATED_REFRESH_STEPS: Final = (
    "Read the raw-spec manifest rows from pancakes.sqlite.",
    (
        "Verify every retained raw-spec payload row against manifest size and "
        "SHA-256."
    ),
    (
        "Expose manifest freshness, source provenance, and blocker details "
        "without "
        "live calls."
    ),
    "Rebuild generated knowledge projections from SQLite raw-spec rows.",
    "Run the guarded ensure command when SQLite raw-spec rows change.",
)
OPERATOR_GATED_REFRESH_STEPS: Final = (
    (
        "Enable MAKE_LIVE_SCRAPER_ENABLED only in an operator-controlled "
        "service "
        "context."
    ),
    (
        "Provide MAKE_API_TOKEN, MAKE_ZONE, and MAKE_ORGANIZATION_ID through "
        "private runtime env."
    ),
    "Run python -B -m languages.make.raw_specs --repo-root <repo> refresh.",
    "Review refreshed SQLite raw-spec rows before compiler promotion.",
    "Promote generalized evidence into manifests, matrix rows, or diff rules.",
)
FORBIDDEN_REFRESH_INPUTS: Final = (
    "provider credential values in source control ",
    "OAuth or bearer tokens in raw-spec manifests ",
    (
        "manual scenario-by-scenario JSON patches as the catalog maintenance "
        "model "
    ),
    "generated SQLite files treated as source of truth ",
    "raw authenticated payloads copied into customer-facing output",
)
EVIDENCE_GENERALIZATION_PATH: Final = (
    "pancakes_sqlite_raw_specs ",
    "pancakes_sqlite_generated_knowledge ",
    "make_module_manifests ",
    "native_semantics_matrix ",
    "blueprint_diff_rules",
)


def raw_spec_refresh_status(config: MakeScraperConfig) -> RawSpecRefreshStatus:
    """Return current raw-spec manifest and file availability status."""
    try:
        sqlite_bundle = load_sqlite_raw_spec_bundle(
            database_path=config.resolved_sqlite_database_path()
        )
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return RawSpecRefreshStatus(
            status="invalid_manifest",
            manifest_path=RAW_SPEC_SQLITE_MANIFEST_PATH,
            manifest_available=True,
            raw_spec_dir=RAW_SPEC_SQLITE_DIR,
            record_count=0,
            missing_records=(),
            manifest_sha256=None,
            invalid_records=("make_raw_spec_manifest_records",),
            freshness_status="invalid_manifest",
            refresh_surface="sqlite_raw_spec_manifest",
            refresh_mode="local_sqlite_status_only",
            live_refresh_enabled=config.live_enabled,
            complete_refresh_available=_complete_refresh_available(config),
            automated_refresh_steps=AUTOMATED_REFRESH_STEPS,
            operator_gated_refresh_steps=OPERATOR_GATED_REFRESH_STEPS,
            complete_refresh_blockers=_complete_refresh_blockers(
                config=config,
                status="invalid_manifest",
                missing_records=(),
                invalid_records=("make_raw_spec_manifest_records",),
            ),
            forbidden_refresh_inputs=FORBIDDEN_REFRESH_INPUTS,
            evidence_generalization_path=EVIDENCE_GENERALIZATION_PATH,
        )
    if sqlite_bundle is not None:
        return _manifest_status(
            config=config,
            manifest=sqlite_bundle.manifest,
            manifest_path=RAW_SPEC_SQLITE_MANIFEST_PATH,
            raw_spec_dir=RAW_SPEC_SQLITE_DIR,
            missing_records=(),
            invalid_records=(),
            refresh_surface="sqlite_raw_spec_manifest",
            refresh_mode="local_sqlite_status_only",
        )

    manifest_path = config.resolved_manifest_path()
    raw_spec_dir = config.resolved_raw_spec_dir()
    if not manifest_path.exists():
        return RawSpecRefreshStatus(
            status="missing_manifest",
            manifest_path=_repo_relative(config.repo_root, manifest_path),
            manifest_available=False,
            raw_spec_dir=_repo_relative(config.repo_root, raw_spec_dir),
            record_count=0,
            missing_records=(),
            manifest_sha256=None,
            freshness_status="missing_manifest",
            live_refresh_enabled=config.live_enabled,
            complete_refresh_available=_complete_refresh_available(config),
            automated_refresh_steps=AUTOMATED_REFRESH_STEPS,
            operator_gated_refresh_steps=OPERATOR_GATED_REFRESH_STEPS,
            complete_refresh_blockers=_complete_refresh_blockers(
                config=config,
                status="missing_manifest",
                missing_records=(),
                invalid_records=(),
            ),
            forbidden_refresh_inputs=FORBIDDEN_REFRESH_INPUTS,
            evidence_generalization_path=EVIDENCE_GENERALIZATION_PATH,
        )
    try:
        manifest = load_raw_spec_manifest(manifest_path)
    except (OSError, TypeError, ValueError):
        return RawSpecRefreshStatus(
            status="invalid_manifest",
            manifest_path=_repo_relative(config.repo_root, manifest_path),
            manifest_available=True,
            raw_spec_dir=_repo_relative(config.repo_root, raw_spec_dir),
            record_count=0,
            missing_records=(),
            manifest_sha256=None,
            invalid_records=(),
            freshness_status="invalid_manifest",
            live_refresh_enabled=config.live_enabled,
            complete_refresh_available=_complete_refresh_available(config),
            automated_refresh_steps=AUTOMATED_REFRESH_STEPS,
            operator_gated_refresh_steps=OPERATOR_GATED_REFRESH_STEPS,
            complete_refresh_blockers=_complete_refresh_blockers(
                config=config,
                status="invalid_manifest",
                missing_records=(),
                invalid_records=("manifest",),
            ),
            forbidden_refresh_inputs=FORBIDDEN_REFRESH_INPUTS,
            evidence_generalization_path=EVIDENCE_GENERALIZATION_PATH,
        )
    missing_records, invalid_records = _record_status_issues(
        config.repo_root, manifest
    )
    return _manifest_status(
        config=config,
        manifest=manifest,
        manifest_path=_repo_relative(config.repo_root, manifest_path),
        raw_spec_dir=manifest.raw_spec_dir,
        missing_records=missing_records,
        invalid_records=invalid_records,
        refresh_surface="legacy_local_raw_spec_manifest",
        refresh_mode="legacy_local_status_only",
    )


def _manifest_status(
    *,
    config: MakeScraperConfig,
    manifest: RawSpecManifest,
    manifest_path: str,
    raw_spec_dir: str,
    missing_records: tuple[str, ...],
    invalid_records: tuple[str, ...],
    refresh_surface: str,
    refresh_mode: str,
) -> RawSpecRefreshStatus:
    """Return read-side status for one raw-spec manifest projection."""
    status = (
        "ready" if not missing_records and not invalid_records else "degraded"
    )
    return RawSpecRefreshStatus(
        status=status,
        manifest_path=manifest_path,
        manifest_available=True,
        raw_spec_dir=raw_spec_dir,
        record_count=len(manifest.records),
        missing_records=missing_records,
        manifest_sha256=manifest.manifest_sha256,
        invalid_records=invalid_records,
        generated_at_utc=manifest.generated_at_utc,
        freshness_status="manifest_verified"
        if status == "ready"
        else "manifest_degraded",
        refresh_surface=refresh_surface,
        refresh_mode=refresh_mode,
        live_refresh_enabled=config.live_enabled,
        complete_refresh_available=_complete_refresh_available(config),
        latest_record_count=sum(
            1 for record in manifest.records if record.latest
        ),
        total_module_count=sum(
            record.module_count for record in manifest.records
        ),
        source_type_counts=_source_type_counts(manifest),
        sanitization_status_counts=_sanitization_status_counts(manifest),
        automated_refresh_steps=AUTOMATED_REFRESH_STEPS,
        operator_gated_refresh_steps=OPERATOR_GATED_REFRESH_STEPS,
        complete_refresh_blockers=_complete_refresh_blockers(
            config=config,
            status=status,
            missing_records=missing_records,
            invalid_records=invalid_records,
        ),
        forbidden_refresh_inputs=FORBIDDEN_REFRESH_INPUTS,
        evidence_generalization_path=EVIDENCE_GENERALIZATION_PATH,
    )


def _record_status_issues(
    repo_root: Path,
    manifest: RawSpecManifest,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return missing and invalid raw-spec records from a manifest."""
    missing: list[str] = []
    invalid: list[str] = []
    for record in manifest.records:
        try:
            path = resolve_repo_relative_path(
                repo_root, Path(record.relative_path)
            )
        except ValueError:
            invalid.append(record.relative_path)
            continue
        if not path.exists():
            missing.append(record.relative_path)
            continue
        try:
            payload_bytes = path.read_bytes()
        except OSError:
            invalid.append(record.relative_path)
            continue
        if (
            len(payload_bytes) != record.size_bytes
            or hashlib.sha256(payload_bytes).hexdigest() != record.sha256
        ):
            invalid.append(record.relative_path)
    return tuple(sorted(missing)), tuple(sorted(invalid))


def _repo_relative(repo_root: Path, path: Path) -> str:
    """Return one path relative to the repository root."""
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _complete_refresh_available(config: MakeScraperConfig) -> bool:
    """Return if a live complete refresh is configured for an explicit run."""
    return (
        config.live_enabled
        and config.api_token is not None
        and config.zone is not None
        and config.organization_id is not None
    )


def _complete_refresh_blockers(
    *,
    config: MakeScraperConfig,
    status: str,
    missing_records: tuple[str, ...],
    invalid_records: tuple[str, ...],
) -> tuple[str, ...]:
    """Return human-readable blockers for complete catalog refresh readiness."""
    blockers: list[str] = []
    if not _complete_refresh_available(config):
        blockers.extend(
            (
                "Complete live raw-spec refresh is operator-gated.",
                "Required env: MAKE_LIVE_SCRAPER_ENABLED and MAKE_API_TOKEN.",
                "Required env: MAKE_ZONE and MAKE_ORGANIZATION_ID.",
            )
        )
    if status == "missing_manifest":
        blockers.append(
            "No SQLite raw-spec manifest rows are available for catalog "
            "rebuild "
            "evidence."
        )
    elif status == "invalid_manifest":
        blockers.append(
            "The SQLite raw-spec manifest failed integrity validation."
        )
    if missing_records:
        blockers.append(
            f"{len(missing_records)} manifest records are missing payloads."
        )
    if invalid_records:
        blockers.append(
            f"{len(invalid_records)} manifest records failed integrity checks."
        )
    return tuple(blockers)


def _source_type_counts(
    manifest: RawSpecManifest,
) -> tuple[tuple[str, int], ...]:
    """Return deterministic counts by raw-spec source type."""
    counter = Counter(
        record.source_metadata.source_type for record in manifest.records
    )
    return tuple(sorted(counter.items()))


def _sanitization_status_counts(
    manifest: RawSpecManifest,
) -> tuple[tuple[str, int], ...]:
    """Return deterministic counts by raw-spec sanitization status."""
    counter = Counter(
        record.source_metadata.sanitization_status
        for record in manifest.records
    )
    return tuple(sorted(counter.items()))
