# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Live Make API adapter for the scraper boundary.

Boundary contract:
- Owns: public exports for the explicit live scraper adapter.
- Must not: execute HTTP, parse raw specs, write manifests, or resolve config.
- Allows: re-exporting live client, source, and scraper-local errors.
- Split when: live exports need provider-specific runtime branching.
- Merge when: another live package surface duplicates these exports.
"""

from __future__ import annotations

from languages.make.raw_specs.live.client import (
    MakeApiClient,
    MakeApiClientConfig,
)
from languages.make.raw_specs.live.errors import (
    MakeApiConfigurationError,
    MakeApiError,
    MakeApiRateLimitError,
    MakeApiRemoteError,
)
from languages.make.raw_specs.live.source import (
    MakeLiveRawSpecSource,
    MakeLocalNativeRawSpecSource,
    MakeNativeFallbackRawSpecSource,
    MakeNativeVersionedRawSpecSource,
    local_native_raw_spec_slugs,
)

__all__ = (
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
    "local_native_raw_spec_slugs",
)
