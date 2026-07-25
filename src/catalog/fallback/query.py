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

"""Catalog-only module retrieval.

Boundary contract:
- Owns: catalog-only ranked retrieval orchestration for one text query.
- Must not: define score weights, mutate catalogs, validate requested IDs,
  or do IO.
- Allows: deterministic candidate filtering, ordering, and result construction.
- Split when: retrieval needs external search, embeddings, or graph traversal.
- Merge when: another query module orchestrates the same catalog-only retrieval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from catalog.fallback.results import (
    SOURCE_LABEL_KNOWLEDGE_DB,
    SOURCE_LABEL_RAW_SPEC_MANIFEST,
    CatalogFallbackDiagnostic,
    CatalogOnlyRetrievalReport,
)
from catalog.fallback.scoring import score_module
from catalog.fallback.text import normalize_text, tokenize
from catalog.fallback.traversal import iter_app_modules
from catalog.identifiers import module_version_sort_key

if TYPE_CHECKING:
    from catalog.models import CatalogSnapshot

DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT: Final = 10
MAX_CATALOG_FALLBACK_QUERY_LIMIT: Final = 24


def retrieve_catalog_modules(
    *,
    snapshot: CatalogSnapshot,
    query_text: str,
    limit: int | None = None,
    source_label: str | None = None,
) -> CatalogOnlyRetrievalReport:
    """Return ranked module candidates.

    Excludes graph and generated planning data.
    """
    effective_source_label = source_label or _snapshot_source_label(snapshot)
    effective_limit = _effective_limit(limit)
    normalized_query = normalize_text(query_text)
    if not normalized_query:
        return CatalogOnlyRetrievalReport(
            catalog_fingerprint=snapshot.fingerprint,
            query_text=query_text,
            fallback_mode="catalog_only",
            candidates=(),
            requested_limit=limit,
            effective_limit=effective_limit,
            total_candidate_count=0,
            is_truncated=False,
            truncation_reason=None,
            diagnostics=(),
        )
    query_terms = frozenset(tokenize(normalized_query))
    candidates = tuple(
        candidate
        for candidate in (
            score_module(
                app=app,
                module=module,
                query_terms=query_terms,
                source_label=effective_source_label,
            )
            for app, module in iter_app_modules(snapshot.apps)
        )
        if candidate.score > 0
    )
    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                -item.score,
                item.source_rank,
                item.app_slug,
                module_version_sort_key(item.app_version),
                item.deprecated,
                item.module_kind,
                item.internal_name,
                item.module_id,
            ),
        )
    )
    ranked = ordered[:effective_limit]
    truncation_reason = _truncation_reason(
        requested_limit=limit,
        effective_limit=effective_limit,
        total_candidate_count=len(ordered),
        returned_count=len(ranked),
    )
    is_truncated = truncation_reason is not None
    return CatalogOnlyRetrievalReport(
        catalog_fingerprint=snapshot.fingerprint,
        query_text=query_text,
        fallback_mode="catalog_only",
        candidates=ranked,
        requested_limit=limit,
        effective_limit=effective_limit,
        total_candidate_count=len(ordered),
        is_truncated=is_truncated,
        truncation_reason=truncation_reason,
        diagnostics=_diagnostics(
            requested_limit=limit,
            effective_limit=effective_limit,
            total_candidate_count=len(ordered),
            truncated=is_truncated,
        ),
    )


def _effective_limit(limit: object) -> int:
    """Return the bounded fallback query limit.

    Raises:
        TypeError: If the provided limit is not an integer or None.
    """
    if limit is None:
        return DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int):
        message = "Catalog fallback query limit must be an integer or None."
        raise TypeError(message)
    if limit <= 0:
        return 0
    return min(limit, MAX_CATALOG_FALLBACK_QUERY_LIMIT)


def _diagnostics(
    *,
    requested_limit: int | None,
    effective_limit: int,
    total_candidate_count: int,
    truncated: bool,
) -> tuple[CatalogFallbackDiagnostic, ...]:
    """Return deterministic diagnostics.

    Diagnostics describe fallback query limit normalization.
    """
    diagnostics: list[CatalogFallbackDiagnostic] = []
    if requested_limit is not None and requested_limit != effective_limit:
        diagnostics.append(
            CatalogFallbackDiagnostic(
                code="catalog_fallback.limit_normalized",
                message=(
                    "Catalog fallback query limit was normalized before "
                    "returning advisory candidates."
                ),
                requested_limit=requested_limit,
                effective_limit=effective_limit,
                total_candidate_count=total_candidate_count,
            )
        )
    if truncated:
        diagnostics.append(
            CatalogFallbackDiagnostic(
                code="catalog_fallback.results_truncated",
                message=(
                    "Catalog fallback advisory candidates were truncated "
                    "by the query limit."
                ),
                requested_limit=requested_limit,
                effective_limit=effective_limit,
                total_candidate_count=total_candidate_count,
            )
        )
    return tuple(diagnostics)


def _truncation_reason(
    *,
    requested_limit: int | None,
    effective_limit: int,
    total_candidate_count: int,
    returned_count: int,
) -> str | None:
    """Return an explicit truncation reason.

    Covers every bounded retrieval report.
    """
    if total_candidate_count <= returned_count:
        return None
    if requested_limit is not None and requested_limit <= 0:
        return "requested_limit_non_positive"
    if requested_limit is not None and requested_limit != effective_limit:
        return "requested_limit_normalized"
    return "effective_limit_applied"


def _snapshot_source_label(snapshot: CatalogSnapshot) -> str:
    """Return the default source label implied by a catalog snapshot."""
    if snapshot.generated_at_utc == "knowledge-store":
        return SOURCE_LABEL_KNOWLEDGE_DB
    return SOURCE_LABEL_RAW_SPEC_MANIFEST
