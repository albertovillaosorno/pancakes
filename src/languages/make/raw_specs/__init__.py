# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make raw-spec scraper and catalog updater slice boundary.

Boundary contract:
- Owns: public exports for the raw-spec scraper bounded context.
- Must not: implement config, live HTTP, manifest, parser, or sync logic.
- Allows: re-exporting stable scraper APIs from focused sibling modules.
- Split when: exports need runtime branching or adapter-specific behavior.
- Merge when: another scraper package surface duplicates these exports.
"""

from __future__ import annotations

from languages.make.raw_specs.config import (
    MakeScraperConfig,
    repo_env_values,
    require_live_ready,
)
from languages.make.raw_specs.external_ids import (
    normalize_make_external_id,
    normalize_optional_make_external_id,
)
from languages.make.raw_specs.live import (
    MakeApiClient,
    MakeApiClientConfig,
    MakeApiConfigurationError,
    MakeApiError,
    MakeApiRateLimitError,
    MakeApiRemoteError,
    MakeLiveRawSpecSource,
    MakeLocalNativeRawSpecSource,
    MakeNativeFallbackRawSpecSource,
    MakeNativeVersionedRawSpecSource,
    local_native_raw_spec_slugs,
)
from languages.make.raw_specs.local_stubs import (
    OPERATOR_APPROVED_LOCAL_STUB_SOURCE,
    OperatorApprovedRawSpecStub,
    find_operator_approved_raw_spec_stub,
    operator_approved_raw_spec_stub_from_json,
)
from languages.make.raw_specs.manifest import (
    build_raw_spec_manifest_for_store,
    load_raw_spec_manifest,
    write_raw_spec_manifest,
)
from languages.make.raw_specs.models import (
    AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecSource,
    MakeRawSpecTarget,
    RawSpecManifest,
    RawSpecRecord,
    RawSpecRefreshStatus,
    RawSpecSourceMetadata,
    RawSpecSyncReport,
)
from languages.make.raw_specs.parser import (
    ParsedMakeRawSpec,
    parse_make_raw_spec,
)
from languages.make.raw_specs.refresh import refresh_raw_specs_from_live_config
from languages.make.raw_specs.status import raw_spec_refresh_status
from languages.make.raw_specs.sync import sync_raw_specs

__all__ = (
    "AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA",
    "OPERATOR_APPROVED_LOCAL_STUB_SOURCE",
    "SYNTHETIC_RAW_SPEC_SOURCE_METADATA",
    "MakeApiClient",
    "MakeApiClientConfig",
    "MakeApiConfigurationError",
    "MakeApiError",
    "MakeApiRateLimitError",
    "MakeApiRemoteError",
    "MakeLiveRawSpecSource",
    "MakeLocalNativeRawSpecSource",
    "MakeNativeFallbackRawSpecSource",
    "MakeNativeVersionedRawSpecSource",
    "MakeRawSpecSource",
    "MakeRawSpecTarget",
    "MakeScraperConfig",
    "OperatorApprovedRawSpecStub",
    "ParsedMakeRawSpec",
    "RawSpecManifest",
    "RawSpecRecord",
    "RawSpecRefreshStatus",
    "RawSpecSourceMetadata",
    "RawSpecSyncReport",
    "build_raw_spec_manifest_for_store",
    "find_operator_approved_raw_spec_stub",
    "load_raw_spec_manifest",
    "local_native_raw_spec_slugs",
    "normalize_make_external_id",
    "normalize_optional_make_external_id",
    "operator_approved_raw_spec_stub_from_json",
    "parse_make_raw_spec",
    "raw_spec_refresh_status",
    "refresh_raw_specs_from_live_config",
    "repo_env_values",
    "require_live_ready",
    "sync_raw_specs",
    "write_raw_spec_manifest",
)
