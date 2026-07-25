# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed records for Make raw-spec refresh commands and queries.

Boundary contract:
- Owns: scraper typed records, JSON object alias, and raw-spec source protocol.
- Must not: parse payloads, write files, fetch live data, or resolve paths.
- Allows: immutable command, query, manifest, and status record shapes.
- Split when: records gain behavior or source protocols diverge by adapter.
- Merge when: another module defines the same scraper record types.
"""

from __future__ import annotations

from typing import Literal, NamedTuple, Protocol

type JsonObject = dict[str, object]
type RawSpecSourceType = Literal[
    "client_authorized_authenticated_api_response",
    "public_make_docs",
    "derived_fixture",
    "third_party_connector_material",
]
type RawSpecSanitizationStatus = Literal[
    "internal_raw_ignored",
    "synthetic_fixture",
    "sanitized_functional_facts",
]


class RawSpecSourceMetadata(NamedTuple):
    """Required source metadata shared by all records in one raw-spec sync."""

    source_type: RawSpecSourceType
    is_truncated: bool
    truncation_reason: str
    sanitization_status: RawSpecSanitizationStatus


class MakeRawSpecTarget(NamedTuple):
    """One Make IMT app/version target to fetch from a source."""

    app_slug: str
    app_version: str


class MakeModuleSummary(NamedTuple):
    """One normalized module summary parsed from a raw Make spec."""

    module_kind: str
    internal_name: str
    display_name: str
    parameter_count: int
    output_count: int


class RawSpecRecord(NamedTuple):
    """One raw-spec file recorded in the manifest."""

    app_slug: str
    app_version: str
    app_label: str
    latest: bool
    manifest_version: int
    source_metadata: RawSpecSourceMetadata
    relative_path: str
    sha256: str
    size_bytes: int
    module_count: int
    module_kinds: tuple[str, ...]


class RawSpecManifest(NamedTuple):
    """Deterministic manifest for retained Make raw specs."""

    generated_at_utc: str
    raw_spec_dir: str
    records: tuple[RawSpecRecord, ...]
    manifest_sha256: str


class RawSpecSyncReport(NamedTuple):
    """Summary for one raw-spec sync command."""

    raw_spec_dir: str
    manifest_path: str
    targets_seen: int
    files_written: int
    manifest_sha256: str
    source_metadata: RawSpecSourceMetadata
    records: tuple[RawSpecRecord, ...]


class RawSpecRefreshStatus(NamedTuple):
    """Read-side status for retained raw-spec refresh artifacts."""

    status: str
    manifest_path: str
    manifest_available: bool
    raw_spec_dir: str
    record_count: int
    missing_records: tuple[str, ...]
    manifest_sha256: str | None
    invalid_records: tuple[str, ...] = ()
    generated_at_utc: str | None = None
    freshness_status: str = "unknown"
    refresh_surface: str = "local_raw_spec_manifest"
    refresh_mode: str = "local_status_only"
    live_refresh_enabled: bool = False
    complete_refresh_available: bool = False
    latest_record_count: int = 0
    total_module_count: int = 0
    source_type_counts: tuple[tuple[str, int], ...] = ()
    sanitization_status_counts: tuple[tuple[str, int], ...] = ()
    automated_refresh_steps: tuple[str, ...] = ()
    operator_gated_refresh_steps: tuple[str, ...] = ()
    complete_refresh_blockers: tuple[str, ...] = ()
    forbidden_refresh_inputs: tuple[str, ...] = ()
    evidence_generalization_path: tuple[str, ...] = ()


class MakeRawSpecSource(Protocol):
    """Source boundary for Make raw specs.

    Implementations may be a mock, a fixture, or a future credentialed live
    Make API adapter. Tests must use a mock or fixture source.
    """

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return the app/version targets available for this sync."""
        ...

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return one raw IMT app payload for a target."""
        ...


SYNTHETIC_RAW_SPEC_SOURCE_METADATA = RawSpecSourceMetadata(
    source_type="derived_fixture",
    is_truncated=False,
    truncation_reason="not_truncated",
    sanitization_status="synthetic_fixture",
)
AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA = RawSpecSourceMetadata(
    source_type="client_authorized_authenticated_api_response",
    is_truncated=False,
    truncation_reason="not_truncated",
    sanitization_status="internal_raw_ignored",
)
