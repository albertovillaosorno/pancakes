# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog-only fallback result records.

Boundary contract:
- Owns: immutable catalog-only fallback typed result records.
- Must not: compute scores, traverse catalogs, validate IDs, plan goals, or do
IO.
- Allows: typed result shapes shared by fallback query and planning flows.
- Split when: result shapes gain behavior beyond derived properties.
- Merge when: another module defines the same fallback result records.
"""

from __future__ import annotations

from typing import Final, NamedTuple, TypedDict

FALLBACK_RESOLUTION_ADVISORY: Final = "advisory_fallback"
FALLBACK_ADVISORY_CONFIDENCE_WEIGHT: Final = 0.35
SOURCE_LABEL_KNOWLEDGE_DB: Final = "knowledge_db"
SOURCE_LABEL_RAW_SPEC_MANIFEST: Final = "raw_spec_manifest"
SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE: Final = (
    "make_default_manifest_coverage"
)
SOURCE_LABEL_FIXTURE_SNAPSHOT: Final = "fixture_snapshot"
SOURCE_LABEL_FALLBACK_ALIAS: Final = "fallback_alias"
SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE: Final = (
    "public_api_connector_candidate"
)
SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE: Final = (
    "client_business_custom_module"
)
SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE: Final = (
    "private_third_party_or_customer_private_module"
)
UNKNOWN_CATALOG_SOURCE_RANK: Final = 9000
CATALOG_SOURCE_RANKS: Final[dict[str, int]] = {
    SOURCE_LABEL_KNOWLEDGE_DB: 0,
    SOURCE_LABEL_RAW_SPEC_MANIFEST: 10,
    SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE: 15,
    SOURCE_LABEL_FIXTURE_SNAPSHOT: 20,
    SOURCE_LABEL_FALLBACK_ALIAS: 30,
    SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE: 40,
    SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE: 400,
    SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE: 800,
}


class CatalogSourcePayload(TypedDict):
    """JSON-ready source evidence fields shared by catalog response payloads."""

    source_label: str
    source_rank: int


def catalog_source_rank(source_label: str) -> int:
    """Return the deterministic precedence rank for one source label."""
    return CATALOG_SOURCE_RANKS.get(source_label, UNKNOWN_CATALOG_SOURCE_RANK)


def catalog_source_payload(source_label: str) -> CatalogSourcePayload:
    """Return the stable JSON-ready source evidence payload."""
    return {
        "source_label": source_label,
        "source_rank": catalog_source_rank(source_label),
    }


def catalog_candidate_source_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, str, str, str, str, str]:
    """Return the computed result for the caller."""
    return (
        catalog_source_rank(candidate.source_label),
        candidate.module_id.casefold(),
        candidate.app_slug.casefold(),
        candidate.app_version.casefold(),
        candidate.module_kind.casefold(),
        candidate.internal_name.casefold(),
    )


class CatalogModuleCandidate(NamedTuple):
    """One catalog-only module candidate."""

    module_id: str
    app_slug: str
    app_label: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    deprecated: bool
    score: int
    match_reasons: tuple[str, ...]
    source_label: str
    source_rank: int
    resolution_kind: str
    confidence_weight: float


class CatalogFallbackDiagnostic(NamedTuple):
    """One catalog fallback query diagnostic."""

    code: str
    message: str
    requested_limit: int | None
    effective_limit: int
    total_candidate_count: int


class CatalogOnlyRetrievalReport(NamedTuple):
    """Catalog-only retrieval output for one query."""

    catalog_fingerprint: str
    query_text: str
    fallback_mode: str
    candidates: tuple[CatalogModuleCandidate, ...]
    requested_limit: int | None
    effective_limit: int
    total_candidate_count: int
    is_truncated: bool
    truncation_reason: str | None
    diagnostics: tuple[CatalogFallbackDiagnostic, ...]

    @property
    def truncated(self) -> bool:
        """Return legacy truncation status for existing callers."""
        return self.is_truncated


class CatalogRetrievalTruncatedError(ValueError):
    """Raised when a planner attempts to consume partial catalog retrieval.

    data.
    """

    def __init__(self, retrieval: CatalogOnlyRetrievalReport) -> None:
        """Initialize the truncated retrieval error.

        Args:
            retrieval: The partial retrieval report that must not feed planning.
        """
        self.reason = retrieval.truncation_reason or "unknown"
        self.returned_count = len(retrieval.candidates)
        self.total_candidate_count = retrieval.total_candidate_count
        self.effective_limit = retrieval.effective_limit
        message = (
            "Catalog fallback retrieval was truncated; refusing to plan from "
            "partial data "
            f"(reason={self.reason}, returned={self.returned_count}, "
            f"total={self.total_candidate_count}, "
            f"limit={self.effective_limit})."
        )
        super().__init__(message)


def require_complete_catalog_retrieval(
    retrieval: CatalogOnlyRetrievalReport,
) -> None:
    """Fail before downstream planners operate on a partial candidate set.

    Raises:
        CatalogRetrievalTruncatedError: When retrieval did not include all
        matching candidates.
    """
    if not retrieval.is_truncated:
        return
    raise CatalogRetrievalTruncatedError(retrieval)


class CatalogOnlyPlanningHints(NamedTuple):
    """Catalog-only planning hints for one goal text."""

    catalog_fingerprint: str
    goal_text: str
    fallback_mode: str
    candidate_apps: tuple[str, ...]
    candidate_module_ids: tuple[str, ...]
    required_parameter_ids: tuple[str, ...]
    candidate_modules: tuple[CatalogModuleCandidate, ...]


class CatalogOnlyValidationReport(NamedTuple):
    """Deterministic validation for requested module selections."""

    catalog_fingerprint: str
    requested_modules: tuple[str, ...]
    resolved_module_ids: tuple[str, ...]
    missing_modules: tuple[str, ...]
    ambiguous_modules: dict[str, tuple[str, ...]]
    valid: bool
