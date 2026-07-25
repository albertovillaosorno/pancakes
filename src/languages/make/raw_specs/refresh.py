# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-specs.command-query-boundary
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# - 001041#repo.make-scraper.raw-specs.persistent-data-output
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Live raw-spec refresh command assembly.

Boundary contract:
- Owns: wiring live Make source configuration into the raw-spec sync command.
- Must not: implement HTTP transport, write manifests directly, or compile
catalogs.
- Allows: explicit live readiness checks and full-target refresh orchestration.
- Split when: live refresh gains pagination state, resume support, or service
locks.
- Merge when: another module wires the same live source into `sync_raw_specs`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages.make.raw_specs.config import (
    MakeScraperConfig,
    require_live_ready,
)
from languages.make.raw_specs.live import (
    MakeApiClient,
    MakeApiClientConfig,
    MakeLiveRawSpecSource,
    MakeLocalNativeRawSpecSource,
    MakeNativeFallbackRawSpecSource,
    MakeNativeVersionedRawSpecSource,
    local_native_raw_spec_slugs,
)
from languages.make.raw_specs.models import (
    AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
)
from languages.make.raw_specs.sync import sync_raw_specs

if TYPE_CHECKING:
    from languages.make.raw_specs.models import RawSpecSyncReport


def refresh_raw_specs_from_live_config(
    *,
    config: MakeScraperConfig,
    search: str | None = None,
    limit: int | None = None,
    generated_at_utc: str | None = None,
    client: MakeApiClient | None = None,
) -> RawSpecSyncReport:
    """Refresh all configured live Make raw specs into repository data.

    Returns:
        The raw-spec sync report for the completed refresh.

    Raises:
        RuntimeError: If live configuration is incomplete or raw-spec sync
        fails.
    """
    require_live_ready(config)
    if config.organization_id is None:
        message = "Live Make scraping requires organization id."
        raise RuntimeError(message)
    normalized_search = None if search is None else search.strip().casefold()
    if (
        limit is None
        and normalized_search is not None
        and normalized_search in local_native_raw_spec_slugs()
    ):
        source = MakeLocalNativeRawSpecSource(app_slugs=(normalized_search,))
    else:
        live_client = client or MakeApiClient(
            MakeApiClientConfig(api_token=config.api_token, zone=config.zone)
        )
        primary_source = MakeLiveRawSpecSource(
            client=live_client,
            organization_id=config.organization_id,
            search=search,
            limit=limit,
        )
        source = MakeNativeFallbackRawSpecSource(
            primary_source=primary_source,
            native_fallback_source=MakeNativeVersionedRawSpecSource(
                client=live_client
            ),
            include_missing_native_targets=search is None or not search.strip(),
        )
    return sync_raw_specs(
        config=config,
        source=source,
        source_metadata=AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=generated_at_utc,
        merge_existing=search is not None or limit is not None,
    )
