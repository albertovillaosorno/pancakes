# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Make catalog evidence source ranking.

Boundary contract:
- Owns: deterministic source precedence for catalog module evidence labels.
- Must not: call live Make.com, inspect completed TODO archives, or depend on
credentials.
- Allows: synthetic SQLite fixtures, raw-spec/catalog fixtures, and MCP payload
checks.
- Split when: source arbitration gains persistence or live evidence promotion.
- Merge when: catalog-plan contracts own the same source-ranking payload fields.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import (
    parse_make_ast_json_text,
    require_module_resolution,
    resolve_ast_modules,
)
from catalog import (
    ModulePlannerHints,
    build_catalog_planning_hints,
    build_semantic_requirement_plan,
)
from catalog.fallback.results import (
    FALLBACK_ADVISORY_CONFIDENCE_WEIGHT,
    FALLBACK_RESOLUTION_ADVISORY,
    SOURCE_LABEL_FALLBACK_ALIAS,
    SOURCE_LABEL_FIXTURE_SNAPSHOT,
    SOURCE_LABEL_KNOWLEDGE_DB,
    SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE,
    SOURCE_LABEL_RAW_SPEC_MANIFEST,
    CatalogModuleCandidate,
    catalog_candidate_source_sort_key,
    catalog_source_rank,
)
from catalog.json_payloads import (
    catalog_snapshot_from_json,
    normalize_json_object,
)
from mcp import execute_mcp_tool

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog import CatalogSnapshot

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
AST_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "make_ast"
    / "lead_routing_blueprint.json"
)
HTTP_MODULE_ID = "module:http:1.0:action:makeRequest"


def test_catalog_source_precedence_is_explicit_and_deterministic() -> None:
    """Knowledge DB outranks raw specs, default coverage, fixtures, and.

    aliases.
    """
    labels = (
        SOURCE_LABEL_FALLBACK_ALIAS,
        SOURCE_LABEL_FIXTURE_SNAPSHOT,
        SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE,
        SOURCE_LABEL_RAW_SPEC_MANIFEST,
        SOURCE_LABEL_KNOWLEDGE_DB,
    )

    ordered = tuple(sorted(labels, key=catalog_source_rank))

    assert ordered == (
        SOURCE_LABEL_KNOWLEDGE_DB,
        SOURCE_LABEL_RAW_SPEC_MANIFEST,
        SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE,
        SOURCE_LABEL_FIXTURE_SNAPSHOT,
        SOURCE_LABEL_FALLBACK_ALIAS,
    ), f"Catalog source precedence drifted: {ordered}"

    tied_raw_specs = tuple(
        sorted(
            (
                _candidate(
                    SOURCE_LABEL_RAW_SPEC_MANIFEST,
                    "module:http:2.0:action:makeRequest",
                ),
                _candidate(SOURCE_LABEL_RAW_SPEC_MANIFEST, HTTP_MODULE_ID),
            ),
            key=catalog_candidate_source_sort_key,
        )
    )
    assert tuple(candidate.module_id for candidate in tied_raw_specs) == (
        HTTP_MODULE_ID,
        "module:http:2.0:action:makeRequest",
    ), f"Same-source tie-breaking is not deterministic: {tied_raw_specs}"


def test_catalog_plan_candidates_record_source_label_and_rank() -> None:
    """Catalog plan module entries expose the source label and numeric rank."""
    snapshot = _load_catalog_fixture()

    plan = build_semantic_requirement_plan(
        snapshot=snapshot,
        requirements_text="send an http request",
        hints=ModulePlannerHints(source_label=SOURCE_LABEL_RAW_SPEC_MANIFEST),
    )
    candidate = plan.candidate_modules[0]

    assert candidate.source_label == SOURCE_LABEL_RAW_SPEC_MANIFEST, (
        f"Semantic plan candidate lost source label: {candidate}"
    )
    assert candidate.source_rank == catalog_source_rank(
        SOURCE_LABEL_RAW_SPEC_MANIFEST
    ), f"Semantic plan candidate lost source rank: {candidate}"

    hints = build_catalog_planning_hints(
        snapshot=snapshot,
        goal_text="send an http request",
        limit=2,
        source_label=SOURCE_LABEL_FIXTURE_SNAPSHOT,
    )
    hint_candidate = hints.candidate_modules[0]
    assert hint_candidate.source_label == SOURCE_LABEL_FIXTURE_SNAPSHOT, (
        f"Planning hint candidate lost fixture source: {hint_candidate}"
    )


def test_removed_scenario_module_tools_are_not_public_mcp(
    tmp_path: Path,
) -> None:
    """Scenario module lookup is internal and no longer part of the public.

    MCP.
    """
    for tool_name in ("scenario.modules.search", "scenario.modules.expand"):
        report = execute_mcp_tool(
            tool_name=tool_name,
            arguments={"query": "request", "limit": "5"},
            repo_root=tmp_path,
        )
        assert not report.ok, (
            f"Removed public MCP tool stayed callable: {report}"
        )
        assert report.error == f"Unknown MCP tool: {tool_name}"


def test_ast_module_resolution_labels_catalog_snapshot_source() -> None:
    """AST module resolution keeps catalog snapshot source evidence visible."""
    root = parse_make_ast_json_text(AST_FIXTURE.read_text(encoding="utf-8"))
    report = resolve_ast_modules(root=root, catalog=_load_catalog_fixture())
    resolution = require_module_resolution(report, "3")

    assert resolution.source_label == SOURCE_LABEL_RAW_SPEC_MANIFEST, (
        f"AST resolution lost raw-spec manifest source label: {resolution}"
    )
    assert resolution.source_rank == catalog_source_rank(
        SOURCE_LABEL_RAW_SPEC_MANIFEST
    ), f"AST resolution lost raw-spec manifest source rank: {resolution}"


def _candidate(source_label: str, module_id: str) -> CatalogModuleCandidate:
    return CatalogModuleCandidate(
        module_id=module_id,
        app_slug="http",
        app_label="HTTP",
        app_version="1.0",
        module_kind="action",
        internal_name="makeRequest",
        display_name="Make a request",
        deprecated=False,
        score=10,
        match_reasons=("exact:request",),
        source_label=source_label,
        source_rank=catalog_source_rank(source_label),
        resolution_kind=FALLBACK_RESOLUTION_ADVISORY,
        confidence_weight=FALLBACK_ADVISORY_CONFIDENCE_WEIGHT,
    )


def _load_catalog_fixture() -> CatalogSnapshot:
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )
