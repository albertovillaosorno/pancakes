# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for bounded catalog fallback query results.

Boundary contract:
- Owns: catalog-only fallback query limit validation and advisory result
  metadata.
- Must not: call live Make.com, read completed TODO archives, or depend on
  credentials.
- Allows: synthetic catalog snapshots and direct fallback retrieval assertions.
- Split when: MCP payload contracts need separate transport-level limit tests.
- Merge when: catalog fallback query contracts already own this exact behavior.
"""

from __future__ import annotations

from typing import cast

import pytest
from catalog.fallback.intent import build_semantic_requirement_plan
from catalog.fallback.planning import build_catalog_planning_hints
from catalog.fallback.query import (
    DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT,
    MAX_CATALOG_FALLBACK_QUERY_LIMIT,
    retrieve_catalog_modules,
)
from catalog.fallback.results import (
    FALLBACK_RESOLUTION_ADVISORY,
    CatalogOnlyRetrievalReport,
    CatalogRetrievalTruncatedError,
)
from catalog.json_payloads import payload_fingerprint
from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogModule,
    CatalogSnapshot,
)

ADVISORY_MODULE_COUNT = 3


def test_catalog_fallback_query_omitted_limit_uses_default_maximum() -> None:
    """Omitted fallback limits are capped by the repository default."""
    snapshot = _snapshot(module_count=DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT + 2)

    result = retrieve_catalog_modules(snapshot=snapshot, query_text="shared")

    assert result.effective_limit == DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT, (
        f"Omitted limit did not use default maximum: {result}"
    )
    assert len(result.candidates) == DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT, (
        f"Omitted limit returned an unbounded candidate list: {result}"
    )
    assert result.truncated, (
        f"Limited fallback results must report truncation: {result}"
    )
    assert result.is_truncated, (
        f"Fallback result must declare why it was truncated: {result}"
    )
    assert result.truncation_reason == "effective_limit_applied", (
        f"Fallback result must declare why it was truncated: {result}"
    )
    _assert_truncation_diagnostic(result.diagnostics)


def test_catalog_fallback_query_validates_bounded_limits() -> None:
    """Fallback query limits are normalized before candidates are returned."""
    snapshot = _snapshot(module_count=MAX_CATALOG_FALLBACK_QUERY_LIMIT + 3)

    zero = retrieve_catalog_modules(
        snapshot=snapshot, query_text="shared", limit=0
    )
    negative = retrieve_catalog_modules(
        snapshot=snapshot, query_text="shared", limit=-5
    )
    huge = retrieve_catalog_modules(
        snapshot=snapshot, query_text="shared", limit=10_000
    )

    assert not (zero.candidates), (
        f"Zero limit must return no fallback candidates: {zero}"
    )
    assert zero.effective_limit == 0, (
        f"Zero limit must return no fallback candidates: {zero}"
    )
    assert not (negative.candidates), (
        f"Negative limit must return no fallback candidates: {negative}"
    )
    assert negative.effective_limit == 0, (
        f"Negative limit must return no fallback candidates: {negative}"
    )
    assert huge.effective_limit == MAX_CATALOG_FALLBACK_QUERY_LIMIT, (
        f"Huge limit must be clamped to the extended maximum: {huge}"
    )
    assert len(huge.candidates) == MAX_CATALOG_FALLBACK_QUERY_LIMIT, (
        f"Huge limit returned too many fallback candidates: {huge}"
    )
    if not zero.truncated or not negative.truncated or not huge.truncated:
        message = (
            f"All bounded fallback results should expose truncation: {zero}"
        )
        message = f"{message} {negative} {huge}"
        assert zero.truncated, message
        assert negative.truncated, message
        assert huge.truncated, message
    assert zero.truncation_reason == "requested_limit_non_positive", (
        f"Zero limit should declare a non-positive truncation reason: {zero}"
    )
    assert negative.truncation_reason == "requested_limit_non_positive", (
        "Negative limit should declare a non-positive truncation reason: "
        f"{negative}"
    )
    assert huge.truncation_reason == "requested_limit_normalized", (
        f"Huge limit should declare a normalization truncation reason: {huge}"
    )


def test_catalog_fallback_query_rejects_non_integer_runtime_limits() -> None:
    """Fallback query limits must not accept bools or text at runtime."""
    snapshot = _snapshot(module_count=ADVISORY_MODULE_COUNT)
    raw_bool_limit: object = True
    raw_text_limit: object = "1"

    with pytest.raises(TypeError, match="limit"):
        _ = retrieve_catalog_modules(
            snapshot=snapshot,
            query_text="shared",
            limit=cast("int | None", raw_bool_limit),
        )
    with pytest.raises(TypeError, match="limit"):
        _ = retrieve_catalog_modules(
            snapshot=snapshot,
            query_text="shared",
            limit=cast("int | None", raw_text_limit),
        )


def test_catalog_fallback_candidates_stay_advisory() -> None:
    """Fallback candidates stay visibly lower-confidence."""
    snapshot = _snapshot(module_count=ADVISORY_MODULE_COUNT)

    result = retrieve_catalog_modules(
        snapshot=snapshot, query_text="shared", limit=2
    )
    candidate = result.candidates[0]

    assert candidate.resolution_kind == FALLBACK_RESOLUTION_ADVISORY, (
        f"Fallback candidate masqueraded as exact resolution: {candidate}"
    )
    assert 0 < candidate.confidence_weight < 1, (
        f"Fallback candidate confidence must be advisory: {candidate}"
    )
    assert result.total_candidate_count == ADVISORY_MODULE_COUNT, (
        f"Fallback result must preserve pre-limit candidate count: {result}"
    )


def test_catalog_fallback_retrieval_report_requires_truncation_fields() -> None:
    """Constructors must require truncation metadata."""
    if CatalogOnlyRetrievalReport._field_defaults:
        message = (
            "CatalogOnlyRetrievalReport must not default truncation metadata: "
            f"{CatalogOnlyRetrievalReport._field_defaults}"
        )
        assert not (CatalogOnlyRetrievalReport._field_defaults), message


def test_catalog_fallback_planners_fail_fast_on_truncated_retrieval() -> None:
    """Planning helpers must reject partial catalog data."""
    snapshot = _snapshot(module_count=ADVISORY_MODULE_COUNT)

    with pytest.raises(CatalogRetrievalTruncatedError, match="truncated"):
        _ = build_catalog_planning_hints(
            snapshot=snapshot, goal_text="shared", limit=1
        )

    with pytest.raises(CatalogRetrievalTruncatedError, match="truncated"):
        _ = build_semantic_requirement_plan(
            snapshot=snapshot,
            requirements_text="shared",
            limit=1,
        )


def test_semantic_requirement_plan_default_limit_matches_fallback() -> None:
    """Semantic planning should not truncate below the fallback default."""
    snapshot = _snapshot(module_count=DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT)

    plan = build_semantic_requirement_plan(
        snapshot=snapshot, requirements_text="shared"
    )

    assert (
        len(plan.candidate_modules) == DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT
    ), f"Semantic planner default limit drifted below fallback default: {plan}"


def _assert_truncation_diagnostic(diagnostics: tuple[object, ...]) -> None:
    assert diagnostics, "Expected a truncation diagnostic."
    diagnostic = diagnostics[0]
    code = getattr(diagnostic, "code", None)
    assert code == "catalog_fallback.results_truncated", (
        f"Unexpected fallback diagnostic: {diagnostics}"
    )


def _snapshot(*, module_count: int) -> CatalogSnapshot:
    modules = tuple(_module(index) for index in range(module_count))
    version = CatalogAppVersion(
        app_version_id="app-version:test:1.0",
        app_id="app:test",
        app_slug="test",
        version="1.0",
        latest=True,
        manifest_version=1,
        modules=modules,
        raw_spec_sha256="1" * 64,
        fingerprint=payload_fingerprint({"version": "test"}),
    )
    app = CatalogApp(
        app_id="app:test",
        app_slug="test",
        label="Test",
        external_id="test",
        deprecated=False,
        versions=(version,),
        fingerprint=payload_fingerprint({"app": "test"}),
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-06T00:00:00+00:00",
        raw_spec_manifest_sha256="2" * 64,
        apps=(app,),
        fingerprint=payload_fingerprint({"snapshot": "fallback-limit"}),
    )


def _module(index: int) -> CatalogModule:
    module_id = f"module:test:1.0:action:shared{index:02d}"
    return CatalogModule(
        module_id=module_id,
        app_version_id="app-version:test:1.0",
        app_slug="test",
        app_version="1.0",
        module_kind="action",
        internal_name=f"shared{index:02d}",
        display_name=f"Shared {index:02d}",
        external_id=module_id,
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256="3" * 64,
        fingerprint=payload_fingerprint({"module": module_id}),
    )
