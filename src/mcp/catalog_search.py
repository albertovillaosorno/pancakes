# ruff: noqa: ERA001, PLR0911, PLR0913, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns the SQLite catalog search and inspect read model for MCP clients.
# split: Move module, unit, graph-neighbor, and query-ranking surfaces into
# focused modules.
# validation: pancakes.mcp.smoke and focused catalog inspect/search contract
# tests.
# review: Operator-requested safety-block repair for Catalog Intelligence
# workers.
# pyright: reportAny=false

"""SQLite-backed catalog search for the public MCP surface.

Boundary contract:
- Owns: read-only catalog.search payloads over the Make knowledge SQLite SSOT.
- Must not: advance catalog-plan units, author semantic answers, or write files.
- Allows: compact search over modules, indexed catalog facts, and evidence gaps.
- Split when: full-text indexing becomes a catalog.knowledge storage
responsibility.
- Merge when: another public MCP module owns the canonical catalog lookup
surface.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from operator import itemgetter
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.knowledge import CATALOG_UNIT_NOTE_SURFACES
from catalog.placeholder_index import (
    catalog_placeholder_matches,
    catalog_placeholder_normalized_text,
    catalog_placeholder_replacement_plan,
)
from catalog.value_index import catalog_database_value_index_payload
from languages.make.raw_specs.paths import resolve_repo_relative_path
from languages.make.scraped_infrastructure import (
    SCRAPED_INFRASTRUCTURE_DOMAIN_BY_TABLE,
    SCRAPED_INFRASTRUCTURE_TABLES,
)

from mcp.catalog_index import catalog_index_lookup_summary_payload

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from mcp.models import JsonObject

CATALOG_SEARCH_OPERATION_MODE: Final = "read_only_local_catalog_search"
CATALOG_SQLITE_SOURCE_OF_TRUTH: Final[dict[str, object]] = {
    "sqlite_ssot": True,
    "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
    "module_lookup": "sqlite:modules ",
    "field_lookup": "sqlite:fields",
    "semantic_lookup": (
        "sqlite:catalog_units/catalog_unit_outputs/catalog_search_documents/"
        "catalog_plan_semantic_answers/catalog_plan_quarantine_records"
    ),
    "module_intelligence_lookup": (
        "sqlite:catalog_module_intelligence_metadata "
    ),
    "graph_lookup": "sqlite:entity_nodes/entity_edges/catalog_edge_proposals",
    "structure_lookup": (
        "sqlite:make_datastore_structure_evidence/make_webhook_structure_ev "
        "idence/"
        "make_scraped_*_evidence"
    ),
    "legacy_json_authority": False,
}
CATALOG_SEARCH_DEFAULT_LIMIT: Final = 8
CATALOG_SEARCH_MAX_LIMIT: Final = 20
CATALOG_SEARCH_MAX_QUERY_CHARS: Final = 300
CATALOG_SEARCH_MAX_TOKEN_COUNT: Final = 8
CATALOG_SEARCH_MAX_SNIPPET_CHARS: Final = 240
CATALOG_SEARCH_MIN_TERM_LENGTH: Final = 2
CATALOG_SEARCH_FIELD_CANDIDATE_LIMIT: Final = 4
CATALOG_SEARCH_FIELD_CANDIDATE_MODULE_LIMIT: Final = 3
CATALOG_STRUCTURE_FIELD_PATH_LIMIT: Final = 8
CATALOG_SEARCH_SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = 5_000
CATALOG_SEARCH_SQLITE_TIMEOUT_SECONDS: Final = (
    CATALOG_SEARCH_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
)
CATALOG_SEARCH_SQLITE_SLOW_MAINTENANCE_TIMEOUT_MILLISECONDS: Final = 300_000
CATALOG_SEARCHABLE_KNOWLEDGE_STATUSES: Final[frozenset[str]] = frozenset(
    ("ok", "degraded")
)
CATALOG_LOOKUP_REQUIRED_TABLES: Final[tuple[str, ...]] = ("modules", "fields")
CATALOG_LOOKUP_ENSURE_COMMAND: Final = "python -B -m catalog.knowledge ensure"
CATALOG_LOOKUP_READY_WITHOUT_ACTIVE_WORKER: Final = (
    "lookup_ready_without_active_worker"
)
CATALOG_LOOKUP_READY_COVERAGE_STATUS: Final = "lookup_ready_non_blocking"
CATALOG_SEARCH_OUTPUT_MODES: Final[frozenset[str]] = frozenset(
    (
        "compact ",
        "micro ",
        "outline ",
        "full ",
        "debug",
    )
)
CATALOG_SEARCH_STOPWORDS: Final[frozenset[str]] = frozenset(
    (
        "a ",
        "an ",
        "and ",
        "for ",
        "in ",
        "make ",
        "module ",
        "of ",
        "or ",
        "the ",
        "to ",
        "with",
    )
)
CATALOG_SEARCH_FIELD_INTENT_TERMS: Final[frozenset[str]] = frozenset(
    (
        "attachment ",
        "attachments ",
        "fallback ",
        "field ",
        "fields ",
        "input ",
        "mapping ",
        "mapper ",
        "optional ",
        "output ",
        "parameter ",
        "parameters ",
        "path ",
        "required ",
        "schema ",
        "type",
    )
)
CATALOG_SEARCH_GENERIC_FIELD_TERMS: Final[frozenset[str]] = frozenset(
    (
        "field ",
        "fields ",
        "input ",
        "mapping ",
        "mapper ",
        "optional ",
        "output ",
        "parameter ",
        "parameters ",
        "path ",
        "required ",
        "schema ",
        "type",
    )
)
CATALOG_SEARCH_TOKEN_PATTERN: Final = re.compile(r"[a-z0-9_:.+-]+")
CATALOG_IDENTIFIER_PATTERN: Final = re.compile(r"[^a-z0-9]+")
CATALOG_KNOWN_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "basicrouter": ("router", "basic router"),
    "addrecord": ("add record", "create record", "datastore record"),
    "actioncreatemessage": ("create message", "send message"),
}
CATALOG_APP_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "builtin": ("basic", "router"),
    "datastore": ("data store", "data stores", "store"),
    "gateway": ("webhook", "hook", "custom webhook"),
    "google-email": ("gmail", "google mail", "google email"),
    "hubspot-marketing-hub": ("hubspot", "hubspot marketing hub"),
    "json": ("json", "parse json"),
    "microsoft-email": (
        "microsoft email ",
        "office 365 email ",
        "outlook",
    ),
    "microsoft-graph": ("microsoft graph", "ms graph"),
    "monday": ("monday", "monday.com", "monday graphql"),
    "slack": ("slack",),
}
CATALOG_GRAPH_GENERIC_APP_INTENT_SLUGS: Final[frozenset[str]] = frozenset(
    ("json",)
)
CATALOG_GRAPH_GENERIC_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "api ",
        "collection ",
        "data ",
        "endpoint ",
        "field ",
        "fields ",
        "graphql ",
        "id ",
        "json ",
        "object ",
        "payload ",
        "payload_json ",
        "rest ",
        "schema",
    )
)
CATALOG_GRAPH_CONTROL_SURFACE_TERMS: Final[frozenset[str]] = frozenset(
    (
        "datastore ",
        "error ",
        "fallback ",
        "filter ",
        "filters ",
        "handler ",
        "retry ",
        "router ",
        "routers ",
        "webhook ",
        "webhooks",
    )
)
CATALOG_CONTROL_SURFACE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "datastore": ("data store", "data stores", "datastore"),
    "data_structure": ("data structure", "data structures"),
    "edge_case": ("edge case", "edge cases"),
    "error_handler": ("error handler", "error handlers", "error handling"),
    "fallback": ("fallback", "fallback behavior"),
    "filter": ("filter", "filters"),
    "retry": ("failed", "retry", "retries"),
    "router": ("router", "routers", "route", "routing"),
    "usage_guidance": ("usage guidance", "guide", "guidance"),
    "webhook": ("custom webhook", "webhook", "webhooks"),
}
CATALOG_GRAPH_GENERIC_FIELD_TOKEN_ONLY_CAP: Final = 20
CATALOG_GRAPH_GENERIC_FIELD_TOKEN_ONLY_PENALTY: Final = 70
CATALOG_GRAPH_NO_APP_MATCH_CAP: Final = 70
CATALOG_GRAPH_NO_APP_CONTROL_SURFACE_CAP: Final = 145
CATALOG_GRAPH_NO_APP_MISMATCH_PENALTY: Final = 85
CATALOG_GRAPH_WRONG_APP_PENALTY: Final = 120
CATALOG_GRAPH_GENERIC_UTILITY_PENALTY: Final = 75
CATALOG_GRAPH_ENDPOINT_ONLY_PENALTY: Final = 55
CATALOG_GRAPH_EDGE_KIND_ONLY_PENALTY: Final = 30
CATALOG_GRAPH_EXPLICIT_APP_MATCH_BONUS: Final = 125
CATALOG_GRAPH_MULTI_APP_BRIDGE_BONUS: Final = 95
CATALOG_GRAPH_MULTI_APP_BRIDGE_MIN_MATCHES: Final = 2
CATALOG_GRAPH_CONTROL_SURFACE_BONUS: Final = 90
CATALOG_GRAPH_EXPLICIT_UTILITY_BONUS: Final = 80
CATALOG_GRAPH_GENERIC_UTILITY_TERMS: Final[frozenset[str]] = frozenset(
    (
        "api ",
        "data ",
        "endpoint ",
        "field ",
        "fields ",
        "graphql ",
        "json ",
        "object ",
        "payload ",
        "rest ",
        "schema ",
        "xml",
    )
)
CATALOG_GENERIC_UTILITY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "api": ("api", "api call", "arbitrary api", "generic api", "universal api"),
    "endpoint": ("endpoint", "rest base", "rest endpoint"),
    "field": ("field", "fields", "mapped fields"),
    "graphql": ("graphql", "graphql endpoint", "graphql query"),
    "json": ("json", "json payload", "parse json"),
    "object": ("object", "objects"),
    "payload": ("payload", "payload json"),
    "schema": ("schema", "schemas"),
    "xml": ("xml", "json to xml"),
}
CATALOG_GRAPH_API_SURFACE_TERMS: Final[frozenset[str]] = frozenset(
    (
        "api ",
        "call ",
        "endpoint ",
        "graphql ",
        "request ",
        "rest",
    )
)
CATALOG_APP_DEFAULT_MODULE_IDENTIFIERS: Final[dict[str, tuple[str, ...]]] = {
    "google-email": ("sendemail", "actionsendemail"),
    "hubspot-marketing-hub": ("makeapicall", "createcontact", "updatecontact"),
    "json": ("createjson", "parsejson"),
    "microsoft-email": ("sendmail", "sendemail"),
    "microsoft-graph": ("microsoftgraphapicall", "makeapicall"),
    "monday": ("executegraphqlquery", "graphqlquery"),
    "slack": (
        "actioncreatemessage ",
        "createmessage ",
        "sendmessage ",
        "postmessage",
    ),
}
CATALOG_GRAPH_WORKFLOW_TERMS: Final[frozenset[str]] = frozenset(
    (
        "connect ",
        "datastore ",
        "dedupe ",
        "email ",
        "error ",
        "failed ",
        "filter ",
        "filters ",
        "gmail ",
        "http ",
        "incoming ",
        "json ",
        "lead ",
        "leads ",
        "request ",
        "retry ",
        "router ",
        "routers ",
        "runs ",
        "slack ",
        "state ",
        "webhook",
    )
)
CATALOG_STRUCTURE_GENERIC_TERMS: Final[frozenset[str]] = frozenset(
    (
        "evidence ",
        "hook ",
        "hooks ",
        "json ",
        "payload ",
        "structure ",
        "webhook ",
        "webhooks",
    )
)


class CatalogSearchQuery(NamedTuple):
    """Parsed local catalog search intent used only for deterministic.

    ranking.
    """

    raw_query: str
    terms: tuple[str, ...]
    normalized_query: str
    module_id: str | None
    app_slug: str | None
    app_slugs: tuple[str, ...]
    app_alias: str | None
    action_phrase: str
    control_surface_terms: tuple[str, ...]
    generic_utility_terms: tuple[str, ...]
    api_surface_terms: tuple[str, ...]
    version: str | None


class CatalogLookupStoreStatus(NamedTuple):
    """Lightweight catalog lookup readiness state for MCP search/inspect."""

    status: str
    missing_paths: tuple[str, ...]
    recommended_commands: tuple[str, ...]


class CatalogModuleCandidateAccumulator(NamedTuple):
    """Mutable state for ranked module candidate accumulation."""

    candidates: list[JsonObject]
    seen: set[str]
    seen_app_surfaces: set[tuple[str, str]]


class CatalogFieldCandidateRow(NamedTuple):
    """SQLite field row scoped to compact catalog search candidates."""

    field_id: str
    module_id: str
    app_slug: str
    module_display_name: str
    field_path: str
    field_label: str
    field_type: str
    required: bool
    source_ref: str


class CatalogGraphRankSignals(NamedTuple):
    """Computed graph ranking signals for one catalog edge."""

    score: int
    score_before_policy: int
    score_after_policy: int
    candidate_app_bindings: tuple[str, ...]
    matched_apps: tuple[str, ...]
    unmatched_app_intents: tuple[str, ...]
    endpoint_term_matches: int
    control_surface_matches: tuple[str, ...]
    workflow_term_matches: int
    generic_field_token_matches: tuple[str, ...]
    generic_utility_matches: tuple[str, ...]
    api_surface_matches: tuple[str, ...]
    generic_field_token_only: bool
    generic_utility_candidate: bool
    endpoint_only_candidate: bool
    edge_kind_only_match: bool
    no_app_score_cap_applied: bool
    wrong_app_penalty_applied: bool
    applied_penalties: tuple[str, ...]
    applied_bonuses: tuple[str, ...]


class CatalogGraphAppSignals(NamedTuple):
    """App intent and candidate binding signals for one graph edge."""

    explicit_app_intents: tuple[str, ...]
    candidate_app_bindings: tuple[str, ...]
    matched_apps: tuple[str, ...]
    unmatched_app_intents: tuple[str, ...]


class CatalogGraphTermSignals(NamedTuple):
    """Term-level rank signals for one graph edge."""

    endpoint_matched_terms: tuple[str, ...]
    edge_matched_terms: tuple[str, ...]
    non_generic_endpoint_term_matches: int
    non_generic_edge_term_matches: int
    workflow_term_matches: int
    generic_field_token_matches: tuple[str, ...]
    control_surface_matches: tuple[str, ...]
    generic_utility_matches: tuple[str, ...]
    api_surface_matches: tuple[str, ...]


class CatalogGraphCandidateFlags(NamedTuple):
    """Boolean graph-candidate classifications used by v10 policy."""

    generic_field_token_only: bool
    generic_utility_candidate: bool
    endpoint_only_candidate: bool
    edge_kind_only_match: bool
    explicit_utility_only_query: bool


class CatalogGraphNoAppPolicy(NamedTuple):
    """No-app policy result for graph candidates that miss explicit app.

    intent.
    """

    score: int
    no_app_score_cap_applied: bool
    wrong_app_penalty_applied: bool
    applied_penalties: tuple[str, ...]


class CatalogGraphPolicyResult(NamedTuple):
    """Final v10 score and explainable policy applications."""

    score: int
    no_app_score_cap_applied: bool
    wrong_app_penalty_applied: bool
    applied_penalties: tuple[str, ...]
    applied_bonuses: tuple[str, ...]


def catalog_search(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Search local catalog facts without moving catalog-plan cursors.

    Returns:
        A compact local-only catalog search payload.

    Raises:
        sqlite3.OperationalError: If a non-lock SQLite operational error occurs.
    """
    query = _required_query(arguments)
    limit = _optional_limit(arguments.get("limit"))
    output_mode = _optional_output_mode(arguments.get("output_mode"))
    terms = _search_terms(query)
    status = _catalog_lookup_store_status(repo_root=repo_root)
    payload = _base_payload(
        query=query,
        terms=terms,
        limit=limit,
        output_mode=output_mode,
        knowledge_status=status.status,
    )
    if status.status not in CATALOG_SEARCHABLE_KNOWLEDGE_STATUSES:
        payload.update(
            {
                "status": "blocked ",
                "blocker_code": "knowledge_sqlite_not_searchable ",
                "blocked_surface": "catalog_evidence",
                "blocked_surfaces": ["catalog_evidence"],
                "unblocked_surfaces": [],
                "status_reason": (
                    "Local Make knowledge SQLite is not searchable."
                ),
                "missing_paths": list(status.missing_paths),
                "recommended_commands": list(status.recommended_commands),
            }
        )
        return payload

    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    try:
        with closing(
            _connect_catalog_search_readonly(database_path)
        ) as connection:
            active_catalog_run = _active_catalog_coverage(connection=connection)
            canonical_value_index_status = catalog_database_value_index_payload(
                connection=connection,
            )
            exact_matches = _exact_module_matches(
                connection=connection, query=query, limit=limit
            )
            parsed_query = _parse_catalog_query(query=query, terms=terms)
            sections = _sqlite_search_sections(
                connection=connection,
                limit=limit,
                exact_matches=exact_matches,
                output_mode=output_mode,
                parsed_query=parsed_query,
            )
    except sqlite3.OperationalError as exc:
        if _is_sqlite_lock_error(exc):
            return _sqlite_read_lock_payload(
                payload=payload, operation="catalog.search"
            )
        raise

    result_counts = _catalog_search_result_counts(
        sections=sections,
        exact_match_count=len(exact_matches),
    )
    payload.update(
        {
            "status": "ok"
            if result_counts["returned_result_count"]
            else "no_results",
            "exact_matches": exact_matches,
            **sections,
            **result_counts,
            "active_catalog_run": active_catalog_run,
            "canonical_value_index_status": canonical_value_index_status,
            "catalog_usable": active_catalog_run["catalog_usable"],
            "catalog_coverage_status": active_catalog_run["coverage_status"],
            **_active_catalog_visibility_fields(active_catalog_run),
            "limit_semantics": "per_candidate_family",
            "off_intent_semantic_candidates_available": bool(
                sections.get("off_intent_semantic_candidate_count")
            ),
        }
    )
    return payload


def catalog_inspect(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Inspect one SQLite-backed catalog entity without moving catalog work.

    cursors.

    Returns:
        A bounded local-only catalog entity payload.

    Raises:
        sqlite3.OperationalError: If a non-lock SQLite operational error occurs.
        ValueError: If the caller does not provide exactly one supported
            identifier.
    """
    module_id = _optional_text_argument(arguments.get("module_id"))
    document_id = _optional_text_argument(arguments.get("document_id"))
    unit_id = _optional_text_argument(arguments.get("unit_id"))
    output_mode = _optional_output_mode(arguments.get("output_mode"))
    requested_keys = tuple(
        value for value in (module_id, document_id, unit_id) if value
    )
    if len(requested_keys) != 1:
        message = (
            "catalog.inspect requires exactly one of module_id, "
            "document_id, or "
            "unit_id."
        )
        raise ValueError(message)

    status = _catalog_lookup_store_status(repo_root=repo_root)
    payload = _inspect_base_payload(
        output_mode=output_mode,
        knowledge_status=status.status,
        module_id=module_id,
        document_id=document_id,
        unit_id=unit_id,
    )
    if status.status not in CATALOG_SEARCHABLE_KNOWLEDGE_STATUSES:
        payload.update(
            {
                "status": "blocked ",
                "blocker_code": "knowledge_sqlite_not_inspectable ",
                "blocked_surface": "catalog_evidence",
                "blocked_surfaces": ["catalog_evidence"],
                "unblocked_surfaces": [],
                "status_reason": (
                    "Local Make knowledge SQLite is not inspectable."
                ),
                "missing_paths": list(status.missing_paths),
                "recommended_commands": list(status.recommended_commands),
            }
        )
        return payload

    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    try:
        with closing(
            _connect_catalog_search_readonly(database_path)
        ) as connection:
            active_catalog_run = _active_catalog_coverage(connection=connection)
            if module_id is not None:
                inspected = _inspect_module(
                    connection=connection,
                    module_id=module_id,
                    output_mode=output_mode,
                )
            elif document_id is not None:
                inspected = _inspect_document(
                    connection=connection, document_id=document_id
                )
            else:
                inspected = _inspect_catalog_unit(
                    connection=connection, unit_id=unit_id or ""
                )
    except sqlite3.OperationalError as exc:
        if _is_sqlite_lock_error(exc):
            return _sqlite_read_lock_payload(
                payload=payload, operation="catalog.inspect"
            )
        raise

    payload.update(
        {
            "active_catalog_run": active_catalog_run,
            "catalog_usable": active_catalog_run["catalog_usable"],
            "catalog_coverage_status": active_catalog_run["coverage_status"],
            **_active_catalog_visibility_fields(active_catalog_run),
        }
    )
    payload.update(inspected)
    return payload


def _sqlite_search_sections(
    *,
    connection: sqlite3.Connection,
    limit: int,
    exact_matches: Sequence[JsonObject],
    output_mode: str,
    parsed_query: CatalogSearchQuery,
) -> JsonObject:
    """Return grouped SQLite search result sections."""
    if parsed_query.module_id and exact_matches:
        return _exact_module_search_sections()

    _register_search_match(connection=connection, terms=parsed_query.terms)
    module_candidates = _module_candidates(
        connection=connection,
        query=parsed_query.raw_query,
        terms=parsed_query.terms,
        limit=limit + 1,
        excluded_module_ids=tuple(
            str(item["module_id"]) for item in exact_matches
        ),
    )
    module_candidates = _attach_module_intelligence_summaries(
        connection=connection,
        candidates=module_candidates,
        metadata_limit=3,
    )
    field_candidates = _field_candidates_for_top_modules(
        connection=connection,
        parsed_query=parsed_query,
        module_candidates=module_candidates,
        limit=CATALOG_SEARCH_FIELD_CANDIDATE_LIMIT + 1,
    )
    raw_semantic_candidates = (
        *_catalog_unit_output_candidates(
            connection=connection, limit=limit + 1
        ),
        *_search_documents(connection=connection, limit=limit + 1),
        *_semantic_answers(connection=connection, limit=limit + 1),
    )
    semantic_candidates, off_intent_semantic_candidates = (
        _split_semantic_candidates_by_intent(
            candidates=raw_semantic_candidates,
            parsed_query=parsed_query,
        )
    )
    graph_candidates = _graph_candidates(
        connection=connection,
        limit=max((limit + 1) * 8, 32),
        parsed_query=parsed_query,
    )
    structure_prerequisites = _structure_prerequisites(
        connection=connection,
        limit=limit + 1,
        terms=parsed_query.terms,
    )
    missing_evidence = (
        *_quarantine_gaps(connection=connection, limit=limit + 1),
        *_planned_structure_gaps(
            terms=parsed_query.terms,
            structure_prerequisites=structure_prerequisites,
        ),
    )
    return {
        "module_candidates": module_candidates[:limit],
        "field_candidates": field_candidates[
            :CATALOG_SEARCH_FIELD_CANDIDATE_LIMIT
        ],
        "semantic_candidates": semantic_candidates[:limit],
        "off_intent_semantic_candidates": (
            _returned_off_intent_semantic_candidates(
                off_intent_semantic_candidates=off_intent_semantic_candidates,
                limit=limit,
                output_mode=output_mode,
            )
        ),
        "graph_candidates": graph_candidates[:limit],
        "structure_prerequisites": structure_prerequisites[:limit],
        "missing_evidence": missing_evidence[:limit],
        "hidden_module_candidate_count": max(len(module_candidates) - limit, 0),
        "hidden_field_candidate_count": max(
            len(field_candidates) - CATALOG_SEARCH_FIELD_CANDIDATE_LIMIT,
            0,
        ),
        "hidden_semantic_candidate_count": max(
            len(semantic_candidates) - limit, 0
        )
        + len(off_intent_semantic_candidates),
        "off_intent_semantic_candidate_count": len(
            off_intent_semantic_candidates
        ),
        "hidden_graph_candidate_count": max(len(graph_candidates) - limit, 0),
        "hidden_structure_prerequisite_count": max(
            len(structure_prerequisites) - limit, 0
        ),
        "hidden_missing_evidence_count": max(len(missing_evidence) - limit, 0),
        "ranker_query_intent": _ranker_query_intent_payload(
            parsed_query=parsed_query
        ),
        "ranker_policy_version": "catalog_search_ranker_v10",
    }


def _returned_off_intent_semantic_candidates(
    *,
    off_intent_semantic_candidates: tuple[JsonObject, ...],
    limit: int,
    output_mode: str,
) -> list[JsonObject]:
    """Return off-intent semantic payloads only when explicitly requested.

    Compact catalog search should expose that off-intent rows exist without
    spending response
    tokens on legacy snippets that were deliberately demoted behind active reset
    results.
    """
    if output_mode not in {"full", "debug"}:
        return []
    return list(off_intent_semantic_candidates[:limit])


def _exact_module_search_sections() -> JsonObject:
    """Return empty broad-search sections for exact module-id hits.

    Exact module-id queries are already resolved by indexed primary module
    lookup, so the public
    MCP response should not spend time scanning semantic documents, structure
    evidence, or field
    rows just to prove a broader query is also possible.
    """
    return {
        "module_candidates": [],
        "field_candidates": [],
        "semantic_candidates": [],
        "off_intent_semantic_candidates": [],
        "graph_candidates": [],
        "structure_prerequisites": [],
        "missing_evidence": [],
        "hidden_module_candidate_count": 0,
        "hidden_field_candidate_count": 0,
        "hidden_semantic_candidate_count": 0,
        "off_intent_semantic_candidate_count": 0,
        "hidden_graph_candidate_count": 0,
        "hidden_structure_prerequisite_count": 0,
        "hidden_missing_evidence_count": 0,
        "search_short_circuit": "exact_module_id",
        "ranker_query_intent": {},
        "ranker_policy_version": "catalog_search_ranker_v10",
    }


def _ranker_query_intent_payload(
    *, parsed_query: CatalogSearchQuery
) -> JsonObject:
    """Return debug metadata for v10 scoring policy inputs."""
    explicit_app_intents = [
        app_slug
        for app_slug in parsed_query.app_slugs
        if app_slug not in CATALOG_GRAPH_GENERIC_APP_INTENT_SLUGS
    ]
    return {
        "policy_version": "catalog_search_ranker_v10",
        "explicit_app_intents": explicit_app_intents,
        "all_app_intents": list(parsed_query.app_slugs),
        "app_alias": parsed_query.app_alias,
        "control_surface_terms": list(parsed_query.control_surface_terms),
        "generic_utility_terms": list(parsed_query.generic_utility_terms),
        "api_surface_terms": list(parsed_query.api_surface_terms),
        "no_app_graph_cap": CATALOG_GRAPH_NO_APP_MATCH_CAP,
        "no_app_control_surface_graph_cap": (
            CATALOG_GRAPH_NO_APP_CONTROL_SURFACE_CAP
        ),
        "wrong_app_penalty": CATALOG_GRAPH_WRONG_APP_PENALTY,
        "generic_utility_penalty": CATALOG_GRAPH_GENERIC_UTILITY_PENALTY,
        "endpoint_only_penalty": CATALOG_GRAPH_ENDPOINT_ONLY_PENALTY,
    }


def _base_payload(
    *,
    query: str,
    terms: tuple[str, ...],
    limit: int,
    output_mode: str,
    knowledge_status: str,
) -> JsonObject:
    """Return shared local-only catalog search metadata."""
    return {
        "response_kind": "catalog_search",
        "operation_mode": CATALOG_SEARCH_OPERATION_MODE,
        "query": query,
        "search_terms": list(terms),
        "output_mode": output_mode,
        "limit": limit,
        "limit_semantics": "per_candidate_family",
        "knowledge_status": knowledge_status,
        "source_of_truth": _catalog_sqlite_source_of_truth(),
        "canonical_index_lookup": catalog_index_lookup_summary_payload(),
        "canonical_placeholder_matches": catalog_placeholder_matches(
            query,
            include_alias_only=True,
        ),
        "canonical_placeholder_replacement_plan": (
            catalog_placeholder_replacement_plan(query)
        ),
        "canonical_placeholder_normalized_query": (
            catalog_placeholder_normalized_text(query)
        ),
        "canonical_value_index_status": {
            "status": "not_evaluated",
            "violation_count": None,
            "violations": [],
        },
        "sqlite_read_policy": _sqlite_read_policy_payload(),
        "search_order": [
            "exact_matches ",
            "module_candidates ",
            "field_candidates ",
            "semantic_candidates ",
            "graph_candidates ",
            "structure_prerequisites ",
            "missing_evidence",
        ],
        "cursor_advanced": False,
        "writes_performed": False,
        "write_actions": [],
        "live_make_called": False,
        "credentials_required": False,
        "provider_api_call": False,
        "provider_execution": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "sends_email": False,
        "requires_operator_confirmation": False,
        "permission_posture": "text_editor_like_local_read",
        "next_queries": (
            {
                "tool": "catalog.inspect",
                "arguments": {
                    "module_id": "<module_id>",
                    "output_mode": "full",
                },
                "reason": "Inspect the exact local catalog module evidence.",
            },
        ),
    }


def _catalog_search_result_counts(
    *,
    sections: Mapping[str, object],
    exact_match_count: int,
) -> JsonObject:
    """Return the computed result for the caller."""
    returned_module_candidate_count = len(
        cast("list[JsonObject]", sections["module_candidates"])
    )
    returned_field_candidate_count = len(
        cast("list[JsonObject]", sections["field_candidates"])
    )
    returned_semantic_candidate_count = len(
        cast("list[JsonObject]", sections["semantic_candidates"])
    )
    returned_graph_candidate_count = len(
        cast("list[JsonObject]", sections["graph_candidates"])
    )
    returned_result_count = (
        exact_match_count
        + returned_module_candidate_count
        + returned_field_candidate_count
        + returned_semantic_candidate_count
        + returned_graph_candidate_count
        + len(cast("list[JsonObject]", sections["structure_prerequisites"]))
        + len(cast("list[JsonObject]", sections["missing_evidence"]))
    )
    hidden_result_count = sum(
        _int_mapping_value(sections, key)
        for key in (
            "hidden_module_candidate_count ",
            "hidden_field_candidate_count ",
            "hidden_semantic_candidate_count ",
            "hidden_graph_candidate_count ",
            "hidden_structure_prerequisite_count ",
            "hidden_missing_evidence_count",
        )
    )
    return {
        "returned_result_count": returned_result_count,
        "total_result_count": returned_result_count + hidden_result_count,
        "returned_exact_match_count": exact_match_count,
        "total_exact_match_count": exact_match_count,
        "returned_module_candidate_count": returned_module_candidate_count,
        "total_module_candidate_count": (
            returned_module_candidate_count
            + _int_mapping_value(sections, "hidden_module_candidate_count")
        ),
        "returned_field_candidate_count": returned_field_candidate_count,
        "total_field_candidate_count": (
            returned_field_candidate_count
            + _int_mapping_value(sections, "hidden_field_candidate_count")
        ),
        "returned_semantic_candidate_count": returned_semantic_candidate_count,
        "total_semantic_candidate_count": (
            returned_semantic_candidate_count
            + _int_mapping_value(sections, "hidden_semantic_candidate_count")
        ),
        "returned_graph_candidate_count": returned_graph_candidate_count,
        "total_graph_candidate_count": (
            returned_graph_candidate_count
            + _int_mapping_value(sections, "hidden_graph_candidate_count")
        ),
        "hidden_result_count": hidden_result_count,
    }


def _active_catalog_coverage(*, connection: sqlite3.Connection) -> JsonObject:
    """Return explicit active-run coverage metadata without blocking lookup.

    tools.
    """
    if not (
        _sqlite_table_exists(connection=connection, table_name="catalog_runs")
        and _sqlite_table_exists(
            connection=connection, table_name="catalog_run_progress"
        )
    ):
        return _inactive_catalog_coverage_payload()
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT
              runs.run_id,
              runs.run_status,
              runs.incomplete_coverage_policy,
              progress.total_unit_count,
              progress.completed_unit_count,
              progress.total_complexity_score,
              progress.completed_complexity_score,
              progress.incomplete_unit_count,
              progress.unit_count_progress_ratio,
              progress.weighted_progress_ratio,
              progress.coverage_status
            FROM catalog_runs AS runs
            JOIN catalog_run_progress AS progress
              ON progress.run_id = runs.run_id
            WHERE runs.run_status = 'active'
            ORDER BY runs.created_at_utc DESC, runs.run_id
            LIMIT 1
            """
        ).fetchone(),
    )
    if row is None:
        return _inactive_catalog_coverage_payload()
    coverage_status = _row_text(row, "coverage_status")
    total_unit_count = _row_int(row, "total_unit_count")
    completed_unit_count = _row_int(row, "completed_unit_count")
    weighted_progress_ratio = float(row["weighted_progress_ratio"])
    run_id = _row_text(row, "run_id")
    payload: JsonObject = {
        "run_id": run_id,
        "run_status": _row_text(row, "run_status"),
        "lookup_status": "ready ",
        "lookup_tables_status": "ready",
        "worker_run_status": _row_text(row, "run_status"),
        "worker_progress_available": True,
        "metrics_semantics": (
            "lookup readiness and worker progress are separate surfaces"
        ),
        "progress_counters_apply_to": "catalog_semantic_worker_run",
        "incomplete_coverage_policy": _row_text(
            row, "incomplete_coverage_policy"
        ),
        "total_unit_count": total_unit_count,
        "active_work_unit_count": total_unit_count,
        "completed_unit_count": completed_unit_count,
        "total_complexity_score": _row_int(row, "total_complexity_score"),
        "completed_complexity_score": _row_int(
            row, "completed_complexity_score"
        ),
        "incomplete_unit_count": _row_int(row, "incomplete_unit_count"),
        "unit_count_progress_ratio": float(row["unit_count_progress_ratio"]),
        "weighted_progress_ratio": weighted_progress_ratio,
        "coverage_status": coverage_status,
        "catalog_usable": coverage_status
        in {"complete", "incomplete_non_blocking"},
        "incomplete_coverage_explicit": coverage_status != "complete ",
        "active_unit_granularity": "leaseable_complete_source_units",
        "legacy_semantic_unit_baseline": _legacy_semantic_baseline_payload(
            connection=connection,
            run_id=run_id,
            active_work_unit_count=total_unit_count,
        ),
        "active_unit_source_surfaces": _active_unit_source_surfaces_payload(),
        "semantic_graph_output_contract": (
            _semantic_graph_output_contract_payload()
        ),
    }
    payload["catalog_completion_snapshot"] = (
        _catalog_completion_snapshot_payload(
            lookup_status=str(payload["lookup_status"]),
            worker_run_status=str(payload["worker_run_status"]),
            worker_progress_available=True,
            coverage_status=coverage_status,
            total_unit_count=total_unit_count,
            active_work_unit_count=total_unit_count,
            completed_unit_count=completed_unit_count,
            weighted_progress_ratio=weighted_progress_ratio,
        )
    )
    return payload


def _inactive_catalog_coverage_payload() -> JsonObject:
    """Return the computed result for the caller."""
    payload: JsonObject = {
        "run_status": CATALOG_LOOKUP_READY_WITHOUT_ACTIVE_WORKER,
        "lookup_status": "ready ",
        "lookup_tables_status": "ready ",
        "worker_run_status": "not_started",
        "worker_progress_available": False,
        "metrics_semantics": (
            "lookup readiness and worker progress are separate surfaces"
        ),
        "progress_counters_apply_to": "catalog_semantic_worker_run",
        "coverage_status": CATALOG_LOOKUP_READY_COVERAGE_STATUS,
        "catalog_usable": True,
        "incomplete_coverage_explicit": True,
        "total_unit_count": 0,
        "active_work_unit_count": 0,
        "completed_unit_count": 0,
        "total_complexity_score": 0,
        "completed_complexity_score": 0,
        "incomplete_unit_count": 0,
        "unit_count_progress_ratio": 0.0,
        "weighted_progress_ratio": 0.0,
        "active_unit_granularity": "none",
        "legacy_semantic_unit_baseline": _empty_legacy_semantic_baseline(),
        "active_unit_source_surfaces": _active_unit_source_surfaces_payload(),
        "semantic_graph_output_contract": (
            _semantic_graph_output_contract_payload()
        ),
    }
    payload["catalog_completion_snapshot"] = (
        _catalog_completion_snapshot_payload(
            lookup_status="ready",
            worker_run_status="not_started",
            worker_progress_available=False,
            coverage_status=CATALOG_LOOKUP_READY_COVERAGE_STATUS,
            total_unit_count=0,
            active_work_unit_count=0,
            completed_unit_count=0,
            weighted_progress_ratio=0.0,
        )
    )
    return payload


def _catalog_completion_snapshot_payload(
    *,
    lookup_status: str,
    worker_run_status: str,
    worker_progress_available: bool,
    coverage_status: str,
    total_unit_count: int,
    active_work_unit_count: int,
    completed_unit_count: int,
    weighted_progress_ratio: float,
) -> JsonObject:
    snapshot_status = (
        "worker_progress_active"
        if worker_progress_available
        else CATALOG_LOOKUP_READY_WITHOUT_ACTIVE_WORKER
    )
    if not worker_progress_available:
        status_reason = (
            "Catalog lookup tables are ready; worker progress counters are "
            "zero because "
            "no active semantic worker run is in progress."
        )
    else:
        status_reason = (
            "Catalog lookup tables are ready and progress counters describe "
            "the active "
            "semantic worker run."
        )
    return {
        "snapshot_status": snapshot_status,
        "lookup_status": lookup_status,
        "worker_run_status": worker_run_status,
        "worker_progress_available": worker_progress_available,
        "coverage_status": coverage_status,
        "total_unit_count": total_unit_count,
        "active_work_unit_count": active_work_unit_count,
        "completed_unit_count": completed_unit_count,
        "weighted_progress_ratio": weighted_progress_ratio,
        "progress_counters_apply_to": "catalog_semantic_worker_run",
        "status_reason": status_reason,
    }


def _active_catalog_visibility_fields(
    active_catalog_run: Mapping[str, object],
) -> JsonObject:
    """Return top-level catalog reset visibility aliases for normal lookup.

    tools.
    """
    return {
        "active_run_id": active_catalog_run.get("run_id"),
        "catalog_run_status": active_catalog_run.get("run_status"),
        "catalog_lookup_status": active_catalog_run.get("lookup_status"),
        "catalog_worker_run_status": active_catalog_run.get(
            "worker_run_status"
        ),
        "lookup_tables_status": active_catalog_run.get("lookup_tables_status"),
        "worker_progress_available": active_catalog_run.get(
            "worker_progress_available"
        ),
        "metrics_semantics": active_catalog_run.get("metrics_semantics"),
        "progress_counters_apply_to": active_catalog_run.get(
            "progress_counters_apply_to"
        ),
        "coverage_status": active_catalog_run.get("coverage_status"),
        "catalog_completion_snapshot": active_catalog_run.get(
            "catalog_completion_snapshot"
        ),
        "total_unit_count": active_catalog_run.get("total_unit_count"),
        "active_work_unit_count": active_catalog_run.get(
            "active_work_unit_count"
        ),
        "completed_unit_count": active_catalog_run.get("completed_unit_count"),
        "total_complexity_score": active_catalog_run.get(
            "total_complexity_score"
        ),
        "weighted_progress_ratio": active_catalog_run.get(
            "weighted_progress_ratio"
        ),
        "active_unit_granularity": active_catalog_run.get(
            "active_unit_granularity"
        ),
        "legacy_semantic_unit_baseline": active_catalog_run.get(
            "legacy_semantic_unit_baseline",
        ),
        "active_unit_source_surfaces": active_catalog_run.get(
            "active_unit_source_surfaces"
        ),
        "semantic_graph_output_contract": active_catalog_run.get(
            "semantic_graph_output_contract",
        ),
    }


def _active_unit_source_surfaces_payload() -> JsonObject:
    """Return the source-surface explanation for compressed active catalog.

    units.
    """
    return {
        "complete_raw_app_version_specs": True,
        "raw_spec_manifest_records": True,
        "raw_spec_payloads": True,
        "module_operation_fields_inside_raw_specs": True,
        "control_surfaces_first_class_units": list(CATALOG_UNIT_NOTE_SURFACES),
        "manifest_and_control_surfaces_not_module_only": True,
    }


def _semantic_graph_output_contract_payload() -> JsonObject:
    """Return the semantic and graph output requirement for each active lease.

    unit.
    """
    return {
        "semantic_output_per_active_unit": True,
        "graph_output_per_active_unit": True,
        "graph_outputs_expand_answer_payload_not_lease_unit_count": True,
    }


def _empty_legacy_semantic_baseline() -> JsonObject:
    """Return the no-baseline legacy catalog explanation."""
    return {
        "legacy_unit_count": 0,
        "legacy_answer_count": 0,
        "obsolete_status": "none",
        "counts_are_comparable": False,
        "active_work_units_less_than_legacy_baseline": False,
        "relationship": "no_legacy_semantic_baseline",
    }


def _legacy_semantic_baseline_payload(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    active_work_unit_count: int,
) -> JsonObject:
    """Return the computed result for the caller."""
    if not _sqlite_table_exists(
        connection=connection,
        table_name="catalog_legacy_semantic_archives",
    ):
        return _empty_legacy_semantic_baseline()
    row = connection.execute(
        """
        SELECT legacy_unit_count, legacy_answer_count, obsolete_status
        FROM catalog_legacy_semantic_archives
        WHERE run_id = ?
        ORDER BY archived_at_utc DESC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return _empty_legacy_semantic_baseline()
    typed = cast("sqlite3.Row", row)
    legacy_unit_count = _row_int(typed, "legacy_unit_count")
    if legacy_unit_count == 0:
        return {
            **_empty_legacy_semantic_baseline(),
            "legacy_answer_count": _row_int(typed, "legacy_answer_count"),
        }
    active_less_than_legacy = active_work_unit_count < legacy_unit_count
    return {
        "legacy_unit_count": legacy_unit_count,
        "legacy_answer_count": _row_int(typed, "legacy_answer_count"),
        "obsolete_status": _row_text(typed, "obsolete_status"),
        "counts_are_comparable": False,
        "active_work_units_less_than_legacy_baseline": active_less_than_legacy,
        "relationship": (
            "active_work_units_are_quality_batches_not_legacy_semantic_units"
            if active_less_than_legacy
            else "active_work_units_cover_or_exceed_legacy_semantic_unit_count"
        ),
        "quality_guard": (
            "A lower active work-unit count is allowed only because each "
            "leased unit requires "
            "both semantic and graph output while preserving complete "
            "source payloads."
        ),
    }


def _split_semantic_candidates_by_intent(
    *,
    candidates: Sequence[JsonObject],
    parsed_query: CatalogSearchQuery,
) -> tuple[tuple[JsonObject, ...], tuple[JsonObject, ...]]:
    """Separate semantic rows that do not match an explicit app intent.

    Returns:
    A tuple of on-intent semantic candidates and off-intent semantic candidates.
    """
    app_slugs = tuple(
        app_slug
        for app_slug in parsed_query.app_slugs
        if app_slug not in {"builtin", "datastore"}
    )
    if not app_slugs:
        return tuple(candidates), ()
    on_intent: list[JsonObject] = []
    off_intent: list[JsonObject] = []
    for candidate in candidates:
        haystack = " ".join(
            str(candidate.get(key, ""))
            for key in (
                "document_id ",
                "surface ",
                "title ",
                "record_kind ",
                "snippet ",
                "unit_id",
            )
        ).casefold()
        if _haystack_mentions_app_intent(
            haystack=haystack, app_slugs=app_slugs
        ):
            on_intent.append(candidate)
            continue
        candidate_copy = dict(candidate)
        candidate_copy["intent_status"] = "off_intent"
        candidate_copy["rank_reason"] = "semantic_candidate_off_app_intent"
        candidate_copy["app_intent"] = ",".join(app_slugs)
        off_intent.append(candidate_copy)
    return tuple(on_intent), tuple(off_intent)


def _haystack_mentions_app_intent(
    *, haystack: str, app_slugs: Sequence[str]
) -> bool:
    """Return if text mentions any explicitly requested app slug or alias."""
    for app_slug in app_slugs:
        if app_slug in haystack:
            return True
        aliases = CATALOG_APP_ALIASES.get(app_slug, ())
        if any(alias in haystack for alias in aliases):
            return True
    return False


def _inspect_base_payload(
    *,
    output_mode: str,
    knowledge_status: str,
    module_id: str | None,
    document_id: str | None,
    unit_id: str | None,
) -> JsonObject:
    """Return shared local-only catalog inspection metadata."""
    return {
        "response_kind": "catalog_inspect ",
        "operation_mode": "read_only_local_catalog_inspect",
        "output_mode": output_mode,
        "knowledge_status": knowledge_status,
        "module_id": module_id,
        "document_id": document_id,
        "unit_id": unit_id,
        "source_of_truth": _catalog_sqlite_source_of_truth(),
        "sqlite_read_policy": _sqlite_read_policy_payload(),
        "cursor_advanced": False,
        "writes_performed": False,
        "write_actions": [],
        "live_make_called": False,
        "credentials_required": False,
        "provider_api_call": False,
        "provider_execution": False,
        "secret_output": False,
        "credential_value_transfer": False,
        "permission_posture": "text_editor_like_local_read",
    }


def _catalog_sqlite_source_of_truth() -> JsonObject:
    """Return the immutable catalog lookup authority descriptor for MCP.

    payloads.
    """
    return dict(CATALOG_SQLITE_SOURCE_OF_TRUTH)


def _sqlite_read_policy_payload() -> JsonObject:
    """Return the public SQLite read policy for catalog lookup tools."""
    return {
        "operation_class": "routine_mcp_read ",
        "connection_mode": "read_only_uri",
        "query_only": True,
        "shared_cache": True,
        "busy_timeout_milliseconds": (
            CATALOG_SEARCH_SQLITE_BUSY_TIMEOUT_MILLISECONDS
        ),
        "busy_timeout_seconds": CATALOG_SEARCH_SQLITE_TIMEOUT_SECONDS,
        "busy_timeout_policy": "bounded_read_timeout ",
        "lock_error_code": "sqlite_read_busy_timeout",
        "slow_maintenance_mode": False,
        "slow_maintenance_mode_required": True,
        "slow_maintenance_timeout_milliseconds": (
            CATALOG_SEARCH_SQLITE_SLOW_MAINTENANCE_TIMEOUT_MILLISECONDS
        ),
        "slow_maintenance_scope": (
            "offline catalog rebuild or refresh commands only"
        ),
    }


def _is_sqlite_lock_error(exception: sqlite3.OperationalError) -> bool:
    text = str(exception).casefold()
    return "locked" in text or "busy" in text


def _sqlite_read_lock_payload(
    *, payload: JsonObject, operation: str
) -> JsonObject:
    blocked_payload = dict(payload)
    blocked_payload.update(
        {
            "status": "blocked ",
            "blocker_code": "sqlite_read_busy_timeout ",
            "blocked_surface": "catalog_evidence",
            "blocked_surfaces": ["catalog_evidence"],
            "unblocked_surfaces": [],
            "status_reason": (
                "Local Make knowledge SQLite stayed locked past the bounded "
                "read timeout."
            ),
            "sqlite_operation": operation,
            "recommended_action": (
                "Retry after the writer commits or inspect the local "
                "process holding the "
                "Pancakes SQLite lock."
            ),
        }
    )
    return blocked_payload


def _required_query(arguments: Mapping[str, object]) -> str:
    """Return the bounded catalog search query.

    Raises:
        TypeError: If the query argument is not text.
        ValueError: If the query is empty or too long.
    """
    value = arguments.get("query")
    if not isinstance(value, str):
        message = "catalog.search requires a non-empty query string."
        raise TypeError(message)
    query = " ".join(value.split())
    if not query:
        message = "catalog.search requires a non-empty query string."
        raise ValueError(message)
    if len(query) > CATALOG_SEARCH_MAX_QUERY_CHARS:
        message = (
            "catalog.search query is too long; narrow it before searching the "
            "local catalog."
        )
        raise ValueError(message)
    return query


def _optional_limit(value: object) -> int:
    """Return a bounded search limit.

    Raises:
        TypeError: If the limit argument is not an integer.
        ValueError: If the limit is not positive.
    """
    if value is None:
        return CATALOG_SEARCH_DEFAULT_LIMIT
    if not isinstance(value, int) or isinstance(value, bool):
        message = "catalog.search limit must be an integer."
        raise TypeError(message)
    if value < 1:
        message = "catalog.search limit must be positive."
        raise ValueError(message)
    return min(value, CATALOG_SEARCH_MAX_LIMIT)


def _optional_output_mode(value: object) -> str:
    """Return the requested compact output mode.

    Raises:
        TypeError: If the output mode argument is not text.
        ValueError: If the output mode is unsupported.
    """
    if value is None:
        return "compact"
    if not isinstance(value, str):
        message = "catalog.search output_mode must be text."
        raise TypeError(message)
    output_mode = value.casefold().strip()
    if output_mode not in CATALOG_SEARCH_OUTPUT_MODES:
        message = (
            "catalog.search output_mode must be micro, compact, outline, full,"
            "or debug."
        )
        raise ValueError(message)
    return output_mode


def _catalog_lookup_store_status(
    *, repo_root: Path
) -> CatalogLookupStoreStatus:
    """Return fast SQLite lookup readiness without loading raw spec payloads."""
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    if not database_path.is_file():
        return CatalogLookupStoreStatus(
            status="missing_database",
            missing_paths=(DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),),
            recommended_commands=(CATALOG_LOOKUP_ENSURE_COMMAND,),
        )
    try:
        with closing(
            _connect_catalog_search_readonly(database_path)
        ) as connection:
            missing_tables = _missing_catalog_lookup_tables(
                connection=connection
            )
    except (OSError, sqlite3.Error, ValueError):
        return CatalogLookupStoreStatus(
            status="stale_schema",
            missing_paths=(),
            recommended_commands=(CATALOG_LOOKUP_ENSURE_COMMAND,),
        )
    if missing_tables:
        return CatalogLookupStoreStatus(
            status="stale_schema",
            missing_paths=(),
            recommended_commands=(CATALOG_LOOKUP_ENSURE_COMMAND,),
        )
    return CatalogLookupStoreStatus(
        status="ok", missing_paths=(), recommended_commands=()
    )


def _missing_catalog_lookup_tables(
    *, connection: sqlite3.Connection
) -> tuple[str, ...]:
    """Return required lookup tables missing from the local SQLite catalog."""
    cursor = connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    )
    try:
        rows = cursor.fetchall()
    finally:
        cursor.close()
    tables = frozenset(str(row[0]) for row in rows)
    return tuple(
        table for table in CATALOG_LOOKUP_REQUIRED_TABLES if table not in tables
    )


def _optional_text_argument(value: object) -> str | None:
    """Return a trimmed optional text argument."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _search_terms(query: str) -> tuple[str, ...]:
    """Return bounded normalized search terms."""
    terms: list[str] = []
    for match in CATALOG_SEARCH_TOKEN_PATTERN.finditer(query.casefold()):
        term = match.group(0).strip()
        if (
            len(term) < CATALOG_SEARCH_MIN_TERM_LENGTH
            or term in CATALOG_SEARCH_STOPWORDS
            or term in terms
        ):
            continue
        terms.append(term)
        if len(terms) >= CATALOG_SEARCH_MAX_TOKEN_COUNT:
            break
    if not terms:
        terms.append(query.casefold())
    return tuple(terms)


def _connect_catalog_search_readonly(database_path: Path) -> sqlite3.Connection:
    """Open a read-only shared-cache SQLite connection for parallel MCP lookups.

    Returns:
        A query-only SQLite connection for local catalog reads.
    """
    uri = f"{database_path.resolve().as_uri()}?mode=ro&cache=shared"
    connection = sqlite3.connect(
        uri,
        timeout=CATALOG_SEARCH_SQLITE_TIMEOUT_SECONDS,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        _enable_query_only(connection)
        _execute_and_close_cursor(
            connection,
            (
                f"PRAGMA busy_timeout = "
                f"{CATALOG_SEARCH_SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
            ),
        )
    except BaseException:
        connection.close()
        raise
    return connection


def _execute_and_close_cursor(
    connection: sqlite3.Connection,
    statement: str,
) -> None:
    """Execute one trusted SQLite statement and close the cursor immediately."""
    cursor = connection.execute(statement)
    cursor.close()


def _enable_query_only(connection: sqlite3.Connection) -> None:
    """Fail closed if this handler accidentally attempts a SQLite write."""
    _execute_and_close_cursor(connection, "PRAGMA query_only = ON")


def _register_search_match(
    *, connection: sqlite3.Connection, terms: Sequence[str]
) -> None:
    """Register the per-query SQLite search predicate."""

    def search_match(*values: object) -> int:
        return int(_values_match_terms(values=values, terms=terms))

    connection.create_function(
        "pancakes_catalog_search_match",
        -1,
        search_match,
    )


def _values_match_terms(
    *, values: Sequence[object], terms: Sequence[str]
) -> bool:
    """Return if any normalized term appears in one row's searchable columns."""
    haystack = " ".join(
        str(value) for value in values if value is not None
    ).casefold()
    return any(term in haystack for term in terms)


def _exact_module_matches(
    *,
    connection: sqlite3.Connection,
    query: str,
    limit: int,
) -> list[JsonObject]:
    """Return exact current module matches before broader candidates."""
    normalized = query.casefold()
    rows = cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT module_id, app_slug, module_kind, internal_name,
            display_name, source_ref
            FROM modules
            WHERE valid_to IS NULL
              AND deprecated = 0
              AND lower(module_id) = ?
            ORDER BY app_slug, module_kind, display_name, module_id
            LIMIT ?
            """,
            (normalized, limit),
        ).fetchall(),
    )
    return [
        _module_payload(
            row=row, match_kind="exact_module", rank_reason="exact_module_id"
        )
        for row in rows
    ]


def _module_candidates(
    *,
    connection: sqlite3.Connection,
    query: str,
    terms: Sequence[str],
    limit: int,
    excluded_module_ids: Sequence[str],
) -> list[JsonObject]:
    """Return current module candidates from module and field facts."""
    parsed_query = _parse_catalog_query(query=query, terms=terms)
    candidate_limit = max(limit * 100, 500)
    app_rows: list[tuple[bool, tuple[str, str, str, str, str, str]]] = []
    if parsed_query.app_slugs:
        per_app_limit = candidate_limit
        if len(parsed_query.app_slugs) > 1:
            per_app_limit = min(candidate_limit, max(50, limit * 4))
        for app_slug in parsed_query.app_slugs:
            app_rows.extend(
                (False, row)
                for row in _app_intent_candidate_module_rows(
                    connection=connection,
                    app_slug=app_slug,
                    limit=per_app_limit,
                )
            )
    explicit_app_slugs = frozenset(parsed_query.app_slugs)
    module_rows = [
        (False, row)
        for row in _candidate_module_rows(
            connection=connection,
            limit=candidate_limit,
        )
        if row[1] not in explicit_app_slugs
    ]
    ranked_rows = sorted(
        (*app_rows, *module_rows),
        key=lambda item: _module_rank_key(
            row=item[1],
            parsed_query=parsed_query,
            field_match=item[0],
        ),
    )
    excluded = frozenset(excluded_module_ids)
    accumulator = CatalogModuleCandidateAccumulator(
        candidates=[],
        seen=set(excluded),
        seen_app_surfaces=set(),
    )
    _append_ranked_module_candidates(
        accumulator=accumulator,
        ranked_rows=ranked_rows,
        parsed_query=parsed_query,
        limit=limit,
    )
    # The caller asks for one extra row only to compute hidden counts. Do not
    # pay the
    # field-table fallback cost just to improve a hidden count when visible
    # module hits are full.
    visible_limit = max(limit - 1, 1)
    if len(accumulator.candidates) >= visible_limit:
        return accumulator.candidates
    field_rows = [
        (True, row)
        for row in _field_candidate_module_rows(
            connection=connection,
            limit=candidate_limit,
        )
        if row[1] not in explicit_app_slugs
    ]
    ranked_field_rows = sorted(
        field_rows,
        key=lambda item: _module_rank_key(
            row=item[1],
            parsed_query=parsed_query,
            field_match=item[0],
        ),
    )
    _append_ranked_module_candidates(
        accumulator=accumulator,
        ranked_rows=ranked_field_rows,
        parsed_query=parsed_query,
        limit=limit,
    )
    return accumulator.candidates


def _append_ranked_module_candidates(
    *,
    accumulator: CatalogModuleCandidateAccumulator,
    ranked_rows: Sequence[tuple[bool, tuple[str, str, str, str, str, str]]],
    parsed_query: CatalogSearchQuery,
    limit: int,
) -> None:
    """Append ranked module rows, preserving app-intent diversity."""
    for field_match, row in ranked_rows:
        module_id = row[0]
        if module_id in accumulator.seen:
            continue
        accumulator.seen.add(module_id)
        rank_reason = _module_rank_reason(
            row=row,
            parsed_query=parsed_query,
            field_match=field_match,
        )
        if parsed_query.app_slugs and rank_reason == "app_slug_intent_match":
            surface_key = _app_module_surface_key(row)
            if surface_key in accumulator.seen_app_surfaces:
                continue
            accumulator.seen_app_surfaces.add(surface_key)
        accumulator.candidates.append(
            _module_payload(
                row=row,
                match_kind="module_candidate",
                rank_reason=rank_reason,
            )
        )
        if len(accumulator.candidates) >= limit:
            break


def _app_module_surface_key(
    row: tuple[str, str, str, str, str, str],
) -> tuple[str, str]:
    """Return a version-agnostic app module surface for app-intent result.

    diversity.
    """
    return (
        row[1].casefold(),
        _normalized_identifier(row[4]),
    )


def _app_intent_candidate_module_rows(
    *,
    connection: sqlite3.Connection,
    app_slug: str,
    limit: int,
) -> list[tuple[str, str, str, str, str, str]]:
    """Return current modules for an explicitly requested app before broad.

    fuzzy.

    rows.
    """
    return cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT module_id, app_slug, module_kind, internal_name,
            display_name, source_ref
            FROM modules
            WHERE valid_to IS NULL
              AND deprecated = 0
              AND app_slug = ?
            ORDER BY module_kind, display_name, module_id
            LIMIT ?
            """,
            (app_slug, limit),
        ).fetchall(),
    )


def _candidate_module_rows(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[tuple[str, str, str, str, str, str]]:
    """Return module rows matching normalized terms."""
    return cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT module_id, app_slug, module_kind, internal_name,
            display_name, source_ref
            FROM modules
            WHERE valid_to IS NULL
              AND deprecated = 0
              AND pancakes_catalog_search_match(
                module_id, app_slug, module_kind, internal_name, display_name
              ) = 1
            ORDER BY app_slug, module_kind, display_name, module_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )


def _field_candidate_module_rows(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[tuple[str, str, str, str, str, str]]:
    """Return modules whose current fields match normalized terms."""
    return cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT DISTINCT
            m.module_id, m.app_slug, m.module_kind, m.internal_name,
            m.display_name,
              m.source_ref
            FROM fields f
            JOIN modules m
              ON m.module_id = f.module_id
             AND m.valid_to IS NULL
             AND m.deprecated = 0
            WHERE f.valid_to IS NULL
              AND pancakes_catalog_search_match(
                f.path, f.label, f.field_type, f.raw_schema_json
              ) = 1
            ORDER BY m.app_slug, m.module_kind, m.display_name, m.module_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )


def _field_candidates_for_top_modules(
    *,
    connection: sqlite3.Connection,
    parsed_query: CatalogSearchQuery,
    module_candidates: Sequence[JsonObject],
    limit: int,
) -> list[JsonObject]:
    """Return compact field matches for the top module hits when the query asks.

    for.

    fields.
    """
    if not _query_has_field_candidate_intent(parsed_query=parsed_query):
        return []
    module_ids = _field_candidate_module_ids(
        module_candidates=module_candidates
    )
    if not module_ids:
        return []
    rows: list[CatalogFieldCandidateRow] = []
    for module_id in module_ids:
        rows.extend(
            _field_candidate_rows_for_module(
                connection=connection,
                module_id=module_id,
                limit=limit,
            )
        )
    module_rank = {
        module_id: index for index, module_id in enumerate(module_ids)
    }
    ranked_rows = sorted(
        rows,
        key=lambda row: _field_candidate_rank_key(
            row=row,
            parsed_query=parsed_query,
            module_rank=module_rank,
        ),
    )
    return [_field_candidate_payload(row=row) for row in ranked_rows[:limit]]


def _query_has_field_candidate_intent(
    *, parsed_query: CatalogSearchQuery
) -> bool:
    """Return whether compact search should spend SQLite reads on field rows."""
    return any(
        term in CATALOG_SEARCH_FIELD_INTENT_TERMS for term in parsed_query.terms
    )


def _field_candidate_module_ids(
    *, module_candidates: Sequence[JsonObject]
) -> tuple[str, ...]:
    """Return unique top module IDs that may expose compact field candidates."""
    module_ids: list[str] = []
    for candidate in module_candidates:
        module_id = candidate.get("module_id")
        if not isinstance(module_id, str) or module_id in module_ids:
            continue
        module_ids.append(module_id)
        if len(module_ids) >= CATALOG_SEARCH_FIELD_CANDIDATE_MODULE_LIMIT:
            break
    return tuple(module_ids)


def _field_candidate_rows_for_module(
    *,
    connection: sqlite3.Connection,
    module_id: str,
    limit: int,
) -> list[CatalogFieldCandidateRow]:
    """Return compact matching field rows for one already-ranked module."""
    rows = cast(
        "list[tuple[str, str, str, str, str, str, str, int, str]]",
        connection.execute(
            """
            SELECT
            f.field_id, f.module_id, m.app_slug, m.display_name, f.path,
            f.label,
              f.field_type, f.required, f.source_ref
            FROM fields f
            JOIN modules m
              ON m.module_id = f.module_id
             AND m.valid_to IS NULL
             AND m.deprecated = 0
            WHERE f.valid_to IS NULL
              AND f.module_id = ?
              AND pancakes_catalog_search_match(
                f.path, f.label, f.field_type, f.raw_schema_json
              ) = 1
            ORDER BY f.path, f.field_id
            LIMIT ?
            """,
            (module_id, limit),
        ).fetchall(),
    )
    return [
        CatalogFieldCandidateRow(
            field_id=row[0],
            module_id=row[1],
            app_slug=row[2],
            module_display_name=row[3],
            field_path=row[4],
            field_label=row[5],
            field_type=row[6],
            required=bool(row[7]),
            source_ref=row[8],
        )
        for row in rows
    ]


def _field_candidate_rank_key(
    *,
    row: CatalogFieldCandidateRow,
    parsed_query: CatalogSearchQuery,
    module_rank: Mapping[str, int],
) -> tuple[int, int, str, str]:
    """Rank field hits by module rank, concrete field-term coverage, and stable.

    path.

    Returns:
        A stable sort key for compact field candidates.
    """
    haystack = f"{row.field_path} {row.field_label} {row.field_type}".casefold()
    target_terms = _field_candidate_target_terms(parsed_query=parsed_query)
    matched_term_count = sum(1 for term in target_terms if term in haystack)
    missing_term_count = max(len(target_terms) - matched_term_count, 0)
    return (
        module_rank.get(row.module_id, len(module_rank)),
        missing_term_count,
        row.field_path.casefold(),
        row.field_id.casefold(),
    )


def _field_candidate_target_terms(
    *, parsed_query: CatalogSearchQuery
) -> tuple[str, ...]:
    """Return non-app, non-generic query terms that should rank field.

    candidates.
    """
    app_terms = {
        app_term.casefold()
        for app_slug in parsed_query.app_slugs
        for app_term in (app_slug, *CATALOG_APP_ALIASES.get(app_slug, ()))
    }
    normalized_app_terms = {_normalized_identifier(term) for term in app_terms}
    target_terms: list[str] = []
    for term in parsed_query.terms:
        normalized = _normalized_identifier(term)
        if (
            term in CATALOG_SEARCH_GENERIC_FIELD_TERMS
            or normalized in normalized_app_terms
            or not normalized
        ):
            continue
        target_terms.append(term)
    return tuple(target_terms)


def _field_candidate_payload(*, row: CatalogFieldCandidateRow) -> JsonObject:
    """Return one compact field hit without raw schema payloads."""
    return {
        "kind": "catalog_module_field ",
        "rank_reason": "field_match_for_top_module_candidate",
        "module_id": row.module_id,
        "app_slug": row.app_slug,
        "module_display_name": row.module_display_name,
        "field_id": row.field_id,
        "field_path": row.field_path,
        "label": row.field_label,
        "field_type": row.field_type,
        "required": row.required,
        "source_ref": row.source_ref,
        "next_query": {
            "tool": "catalog.inspect",
            "arguments": {"module_id": row.module_id, "output_mode": "full"},
            "reason": (
                "Inspect the full module field schema if compact field "
                "metadata is not enough."
            ),
        },
    }


def _module_payload(
    *,
    row: tuple[str, str, str, str, str, str],
    match_kind: str,
    rank_reason: str,
) -> JsonObject:
    """Return a compact module hit payload."""
    return {
        "kind": match_kind,
        "rank_reason": rank_reason,
        "module_id": row[0],
        "app_slug": row[1],
        "module_kind": row[2],
        "internal_name": row[3],
        "display_name": row[4],
        "source_ref": row[5],
    }


def _attach_module_intelligence_summaries(
    *,
    connection: sqlite3.Connection,
    candidates: list[JsonObject],
    metadata_limit: int,
) -> list[JsonObject]:
    """Attach compact module intelligence only to the most relevant module hits.

    Returns:
    Module candidates with bounded intelligence summaries on the first few hits.
    """
    if not _sqlite_table_exists(
        connection=connection,
        table_name="catalog_module_intelligence_metadata",
    ):
        return candidates
    enriched: list[JsonObject] = []
    for index, candidate in enumerate(candidates):
        if index >= metadata_limit:
            enriched.append(candidate)
            continue
        module_id = candidate.get("module_id")
        if not isinstance(module_id, str):
            enriched.append(candidate)
            continue
        summary = _module_intelligence_summary(
            connection=connection, module_id=module_id
        )
        if summary is None:
            enriched.append(candidate)
            continue
        enriched_candidate = dict(candidate)
        enriched_candidate["module_intelligence"] = summary
        enriched.append(enriched_candidate)
    return enriched


def _module_intelligence_summary(
    *,
    connection: sqlite3.Connection,
    module_id: str,
) -> JsonObject | None:
    row = _module_intelligence_row(connection=connection, module_id=module_id)
    if row is None:
        return None
    available_detail_fields = [
        field_name
        for field_name in (
            "input_schema_json ",
            "output_schema_json ",
            "field_constraints_json ",
            "common_error_codes_json ",
            "required_scopes_json ",
            "suggested_control_structures_json",
        )
        if _row_text(row, field_name)
    ]
    return {
        "evidence_status": _row_text(row, "evidence_status"),
        "auth_type": _optional_row_text(row, "auth_type"),
        "output_cardinality": _optional_row_text(row, "output_cardinality"),
        "requires_iterator": _optional_row_bool(row, "requires_iterator"),
        "batch_processing_supported": _optional_row_bool(
            row, "batch_processing_supported"
        ),
        "operation_cost_multiplier": _optional_row_float(
            row,
            "operation_cost_multiplier",
        ),
        "cheaper_alternative_module_id": _optional_row_text(
            row,
            "cheaper_alternative_module_id",
        ),
        "available_detail_fields": available_detail_fields,
        "detail_policy": (
            "Full schemas, constraints, scopes, and error-code details are "
            "available through "
            "catalog.inspect, not broad catalog.search results."
        ),
    }


def _module_intelligence_row(
    *,
    connection: sqlite3.Connection,
    module_id: str,
) -> sqlite3.Row | None:
    if not _sqlite_table_exists(
        connection=connection,
        table_name="catalog_module_intelligence_metadata",
    ):
        return None
    return cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT *
            FROM catalog_module_intelligence_metadata
            WHERE module_id = ?
              AND valid_to IS NULL
            ORDER BY created_at_utc DESC, run_id DESC, unit_id DESC
            LIMIT 1
            """,
            (module_id,),
        ).fetchone(),
    )


def _module_intelligence_details(
    *,
    connection: sqlite3.Connection,
    module_id: str,
    output_mode: str,
) -> JsonObject | None:
    row = _module_intelligence_row(connection=connection, module_id=module_id)
    if row is None:
        return None
    payload = _module_intelligence_summary(
        connection=connection, module_id=module_id
    )
    if payload is None:
        return None
    payload = dict(payload)
    payload.update(
        {
            "run_id": _row_text(row, "run_id"),
            "unit_id": _row_text(row, "unit_id"),
            "source_ref": _row_text(row, "source_ref"),
            "created_at_utc": _row_text(row, "created_at_utc"),
            "telemetry": {
                "error_rate_percentage": _optional_row_float(
                    row,
                    "error_rate_percentage",
                ),
                "api_rate_limit_rpm": _optional_row_int(
                    row, "api_rate_limit_rpm"
                ),
                "avg_execution_time_ms": _optional_row_int(
                    row,
                    "avg_execution_time_ms",
                ),
                "common_error_codes_present": bool(
                    _row_text(row, "common_error_codes_json")
                ),
                "evidence_policy": (
                    "Runtime telemetry remains null unless local evidence "
                    "exists; this tool "
                    "does not fetch provider telemetry."
                ),
            },
        }
    )
    if output_mode not in {"full", "debug"}:
        return payload
    payload.update(
        {
            "input_schema": _json_value_from_row(row, "input_schema_json"),
            "output_schema": _json_value_from_row(row, "output_schema_json"),
            "field_constraints": _json_value_from_row(
                row, "field_constraints_json"
            ),
            "common_error_codes": _json_value_from_row(
                row, "common_error_codes_json"
            ),
            "required_scopes": _json_value_from_row(
                row, "required_scopes_json"
            ),
            "suggested_control_structures": _json_value_from_row(
                row,
                "suggested_control_structures_json",
            ),
            "token_refresh_supported": _optional_row_bool(
                row,
                "token_refresh_supported",
            ),
        }
    )
    return payload


def _parse_catalog_query(
    *, query: str, terms: Sequence[str]
) -> CatalogSearchQuery:
    """Return parsed query intent for deterministic module ranking."""
    normalized_query = _normalized_identifier(query)
    lowered_query = query.casefold()
    module_id = lowered_query if lowered_query.startswith("module:") else None
    version = next(
        (term for term in terms if re.fullmatch(r"\d+(?:\.\d+)+", term)), None
    )
    app_intents = _app_intents_from_query(
        lowered_query=lowered_query, terms=terms
    )
    app_slugs = tuple(app_slug for app_slug, _alias in app_intents)
    app_alias = next(
        (alias for _app_slug, alias in app_intents if alias is not None), None
    )
    app_slug = app_slugs[0] if app_slugs else None
    app_excluded_terms = {
        _normalized_identifier(app_token)
        for app in app_slugs
        for app_token in (app, *CATALOG_APP_ALIASES.get(app, ()))
    }
    action_terms = tuple(
        _normalized_identifier(term)
        for term in terms
        if _normalized_identifier(term) not in app_excluded_terms
    )
    return CatalogSearchQuery(
        raw_query=query,
        terms=tuple(terms),
        normalized_query=normalized_query,
        module_id=module_id,
        app_slug=app_slug,
        app_slugs=app_slugs,
        app_alias=app_alias,
        action_phrase="".join(action_terms),
        control_surface_terms=_control_surface_terms_from_query(
            lowered_query=lowered_query,
            terms=terms,
        ),
        generic_utility_terms=_generic_utility_terms_from_query(
            lowered_query=lowered_query,
            terms=terms,
        ),
        api_surface_terms=_api_surface_terms_from_query(terms=terms),
        version=version,
    )


def _app_intents_from_query(
    *,
    lowered_query: str,
    terms: Sequence[str],
) -> tuple[tuple[str, str | None], ...]:
    """Return explicit app intents in the order they appear in the query."""
    term_set = {term.casefold() for term in terms}
    matches: list[tuple[int, str, str | None]] = []
    for candidate_app, aliases in CATALOG_APP_ALIASES.items():
        positions: list[tuple[int, str | None]] = []
        if candidate_app in term_set:
            position = lowered_query.find(candidate_app)
            positions.append(
                (position if position >= 0 else len(lowered_query), None)
            )
        for alias in aliases:
            position = lowered_query.find(alias)
            if position >= 0:
                positions.append((position, alias))
        if positions:
            position, alias = min(positions, key=itemgetter(0))
            matches.append((position, candidate_app, alias))
    ordered: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for _position, app_slug, alias in sorted(matches, key=itemgetter(0)):
        if app_slug in seen:
            continue
        seen.add(app_slug)
        ordered.append((app_slug, alias))
    return tuple(ordered)


def _control_surface_terms_from_query(
    *,
    lowered_query: str,
    terms: Sequence[str],
) -> tuple[str, ...]:
    """Return first-class control surfaces explicitly requested by the query."""
    term_set = {term.casefold() for term in terms}
    requested: list[str] = []
    for surface, aliases in CATALOG_CONTROL_SURFACE_ALIASES.items():
        if surface in term_set or any(
            alias in lowered_query for alias in aliases
        ):
            requested.append(surface)
    return tuple(requested)


def _generic_utility_terms_from_query(
    *,
    lowered_query: str,
    terms: Sequence[str],
) -> tuple[str, ...]:
    """Return low-authority utility terms explicitly requested by the query."""
    term_set = {term.casefold() for term in terms}
    requested: list[str] = []
    for utility, aliases in CATALOG_GENERIC_UTILITY_ALIASES.items():
        if utility == "api" and _query_names_api_app(
            lowered_query=lowered_query
        ):
            continue
        if utility == "field" and "data store" in lowered_query:
            continue
        if utility in term_set or any(
            alias in lowered_query for alias in aliases
        ):
            requested.append(utility)
    return tuple(requested)


def _api_surface_terms_from_query(*, terms: Sequence[str]) -> tuple[str, ...]:
    """Return API-surface terms without treating API itself as app intent."""
    return tuple(
        term.casefold()
        for term in terms
        if term.casefold() in CATALOG_GRAPH_API_SURFACE_TERMS
    )


def _query_names_api_app(*, lowered_query: str) -> bool:
    """Return whether an API word is part of a named provider product phrase."""
    return "microsoft graph api" in lowered_query


def _module_rank_key(
    *,
    row: tuple[str, str, str, str, str, str],
    parsed_query: CatalogSearchQuery,
    field_match: bool,
) -> tuple[int, int, int, str, str, str]:
    """Return a deterministic app-intent-aware module rank key."""
    reason = _module_rank_reason(
        row=row,
        parsed_query=parsed_query,
        field_match=field_match,
    )
    priority_by_reason = {
        "exact_module_id": 0,
        "exact_app_slug_and_internal_name": 1,
        "exact_app_slug_and_display_name": 2,
        "app_slug_intent_match": 3,
        "known_alias_match": 4,
        "internal_name_match": 5,
        "display_name_match": 6,
        "semantic_candidate": 7,
        "fuzzy_raw_spec_match": 8,
    }
    return (
        priority_by_reason[reason],
        _preferred_app_module_rank(row=row, parsed_query=parsed_query),
        _app_intent_order(parsed_query=parsed_query, app_slug=row[1]),
        row[1].casefold(),
        row[2].casefold(),
        row[0].casefold(),
    )


def _preferred_app_module_rank(
    *,
    row: tuple[str, str, str, str, str, str],
    parsed_query: CatalogSearchQuery,
) -> int:
    """Prefer representative workflow modules for broad app-connection queries.

    Returns:
        Zero for preferred app modules and one for all other candidates.
    """
    app_slug = row[1].casefold()
    if app_slug not in parsed_query.app_slugs:
        return 1
    preferred_identifiers = CATALOG_APP_DEFAULT_MODULE_IDENTIFIERS.get(
        app_slug, ()
    )
    if not preferred_identifiers:
        return 1
    internal_identifier = _normalized_identifier(row[3])
    display_identifier = _normalized_identifier(row[4])
    if any(
        preferred in {internal_identifier, display_identifier}
        or preferred in internal_identifier
        or preferred in display_identifier
        for preferred in preferred_identifiers
    ):
        return 0
    return 1


def _app_intent_order(
    *, parsed_query: CatalogSearchQuery, app_slug: str
) -> int:
    """Return the query-order position for an explicit app intent."""
    try:
        return parsed_query.app_slugs.index(app_slug.casefold())
    except ValueError:
        return len(parsed_query.app_slugs) + 1


def _query_targets_app(
    *, parsed_query: CatalogSearchQuery, app_slug: str
) -> bool:
    """Return whether the parsed query contains an app slug or known alias for.

    one.

    app.
    """
    app_token = app_slug.casefold()
    if app_token in parsed_query.app_slugs:
        return True
    if parsed_query.app_slug == app_token:
        return True
    if app_token in {term.casefold() for term in parsed_query.terms}:
        return True
    aliases = CATALOG_APP_ALIASES.get(app_token, ())
    return any(alias in parsed_query.raw_query.casefold() for alias in aliases)


def _module_rank_reason(
    *,
    row: tuple[str, str, str, str, str, str],
    parsed_query: CatalogSearchQuery,
    field_match: bool,
) -> str:
    """Return the computed result for the caller."""
    (
        module_id,
        app_slug,
        module_kind,
        internal_name,
        display_name,
        _source_ref,
    ) = row
    normalized_query = parsed_query.normalized_query
    normalized_terms = tuple(
        _normalized_identifier(term) for term in parsed_query.terms
    )
    app_token = app_slug.casefold()
    app_intent = _query_targets_app(
        parsed_query=parsed_query, app_slug=app_slug
    )
    internal_identifier = _normalized_identifier(internal_name)
    display_identifier = _normalized_identifier(display_name)
    module_identifier = _normalized_identifier(module_id)
    module_kind_identifier = _normalized_identifier(module_kind)
    action_identifiers = tuple(
        term for term in normalized_terms if term != app_token
    )

    if parsed_query.module_id == module_id.casefold():
        return "exact_module_id"
    if app_intent and _app_action_matches(
        candidate=internal_identifier,
        action_identifiers=action_identifiers,
        action_phrase=parsed_query.action_phrase,
    ):
        return "exact_app_slug_and_internal_name"
    if app_intent and _app_action_matches(
        candidate=display_identifier,
        action_identifiers=action_identifiers,
        action_phrase=parsed_query.action_phrase,
    ):
        return "exact_app_slug_and_display_name"
    if app_intent and any(
        term
        in {internal_identifier, display_identifier, module_kind_identifier}
        or term in module_identifier
        for term in normalized_terms
        if term != app_token
    ):
        return "app_slug_intent_match"
    if app_intent:
        return "app_slug_intent_match"
    if _known_alias_matches(
        internal_identifier=internal_identifier,
        display_identifier=display_identifier,
        query=parsed_query.raw_query,
    ):
        return "known_alias_match"
    if _identifier_matches(
        candidate=internal_identifier,
        query_identifier=normalized_query,
        terms=normalized_terms,
    ):
        return "internal_name_match"
    if _identifier_matches(
        candidate=display_identifier,
        query_identifier=normalized_query,
        terms=normalized_terms,
    ):
        return "display_name_match"
    if field_match:
        return "fuzzy_raw_spec_match"
    return "semantic_candidate"


def _app_action_matches(
    *,
    candidate: str,
    action_identifiers: Sequence[str],
    action_phrase: str,
) -> bool:
    """Return whether a candidate matches all non-app action intent terms."""
    if not candidate:
        return False
    meaningful_terms = tuple(term for term in action_identifiers if term)
    if not meaningful_terms:
        return False
    return (
        candidate == action_phrase
        or bool(action_phrase and action_phrase in candidate)
        or all(term in candidate for term in meaningful_terms)
    )


def _identifier_matches(
    *,
    candidate: str,
    query_identifier: str,
    terms: Sequence[str],
) -> bool:
    """Return if a query or any term exactly identifies a module surface."""
    if not candidate:
        return False
    return (
        candidate == query_identifier
        or candidate in terms
        or any(term in candidate for term in terms)
    )


def _known_alias_matches(
    *,
    internal_identifier: str,
    display_identifier: str,
    query: str,
) -> bool:
    """Return whether the query uses a known module alias."""
    normalized_query = query.casefold()
    for canonical, aliases in CATALOG_KNOWN_ALIASES.items():
        if canonical not in {internal_identifier, display_identifier}:
            continue
        if any(alias in normalized_query for alias in aliases):
            return True
    return False


def _normalized_identifier(value: str) -> str:
    """Return a compact casefolded identifier for rank comparisons."""
    return CATALOG_IDENTIFIER_PATTERN.sub("", value.casefold())


def _inspect_module(
    *,
    connection: sqlite3.Connection,
    module_id: str,
    output_mode: str,
) -> JsonObject:
    """Return one module and bounded field summaries from SQLite."""
    row = cast(
        "tuple[str, str, str, str, str, str, int, str] | None",
        connection.execute(
            """
            SELECT module_id, app_slug, module_kind, internal_name,
            display_name,
                   source_ref, deprecated, fingerprint
            FROM modules
            WHERE module_id = ?
              AND valid_to IS NULL
            LIMIT 1
            """,
            (module_id,),
        ).fetchone(),
    )
    if row is None:
        return {
            "status": "no_results ",
            "entity_kind": "module",
            "field_count": 0,
            "fields": [],
        }
    field_limit = 100 if output_mode == "debug" else 20
    field_rows = cast(
        "list[tuple[str, str, str, str, str]]",
        connection.execute(
            """
            SELECT path, label, field_type, required, source_ref
            FROM fields
            WHERE module_id = ?
              AND valid_to IS NULL
            ORDER BY path
            LIMIT ?
            """,
            (module_id, field_limit + 1),
        ).fetchall(),
    )
    fields = [
        {
            "path": field_row[0],
            "label": field_row[1],
            "field_type": field_row[2],
            "required": bool(field_row[3]),
            "source_ref": field_row[4],
        }
        for field_row in field_rows[:field_limit]
    ]
    hidden_field_count = max(len(field_rows) - field_limit, 0)
    module_intelligence = _module_intelligence_details(
        connection=connection,
        module_id=module_id,
        output_mode=output_mode,
    )
    return {
        "status": "ok ",
        "entity_kind": "module",
        "module": {
            "module_id": row[0],
            "app_slug": row[1],
            "module_kind": row[2],
            "internal_name": row[3],
            "display_name": row[4],
            "source_ref": row[5],
            "deprecated": bool(row[6]),
            "fingerprint": row[7],
        },
        "field_count": len(field_rows),
        "returned_field_count": len(fields),
        "hidden_field_count": hidden_field_count,
        "next_query": (
            f"catalog.inspect module_id={module_id} output_mode=debug"
            if hidden_field_count
            else None
        ),
        "fields": fields,
        "module_intelligence": module_intelligence,
    }


def _inspect_document(
    *, connection: sqlite3.Connection, document_id: str
) -> JsonObject:
    """Return one catalog search document from SQLite."""
    row = cast(
        "tuple[str, str, str, str, str, str] | None",
        connection.execute(
            """
            SELECT document_id, surface, title, record_kind, source_ref, body
            FROM catalog_search_documents
            WHERE document_id = ?
              AND valid_to IS NULL
            LIMIT 1
            """,
            (document_id,),
        ).fetchone(),
    )
    if row is None:
        return {
            "status": "no_results ",
            "entity_kind": "catalog_search_document",
        }
    return {
        "status": "ok ",
        "entity_kind": "catalog_search_document",
        "document": {
            "document_id": row[0],
            "surface": row[1],
            "title": row[2],
            "record_kind": row[3],
            "source_ref": row[4],
            "snippet": _snippet(row[5]),
        },
    }


def _inspect_catalog_unit(
    *, connection: sqlite3.Connection, unit_id: str
) -> JsonObject:
    """Return the computed result for the caller."""
    active_unit = _inspect_active_catalog_unit(
        connection=connection, unit_id=unit_id
    )
    if active_unit is not None:
        return active_unit

    row = cast(
        "tuple[int, str, str, str, str] | None",
        connection.execute(
            """
            SELECT unit_number, status, surface, source_ref, evidence_path
            FROM catalog_plan_units
            WHERE printf('%06d', unit_number) = ?
               OR unit_number = CAST(? AS INTEGER)
            ORDER BY valid_to IS NULL DESC, unit_number
            LIMIT 1
            """,
            (unit_id, unit_id),
        ).fetchone(),
    )
    if row is None:
        return {"status": "no_results", "entity_kind": "catalog_unit"}
    answer_row = cast(
        "tuple[str, str, str] | None",
        connection.execute(
            """
            SELECT answer_status, evidence_status, source_ref
            FROM catalog_plan_semantic_answers
            WHERE unit_number = ?
              AND valid_to IS NULL
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (row[0],),
        ).fetchone(),
    )
    quarantine_rows = cast(
        "list[tuple[str, str, int, str]]",
        connection.execute(
            """
            SELECT quarantine_kind, reason, priority, status
            FROM catalog_plan_quarantine_records
            WHERE unit_number = ?
              AND resolved_at_utc IS NULL
            ORDER BY priority DESC, created_at_utc
            LIMIT 5
            """,
            (row[0],),
        ).fetchall(),
    )
    return {
        "status": "ok ",
        "entity_kind": "catalog_unit",
        "unit": {
            "unit_number": row[0],
            "unit_id": f"{row[0]:06d}",
            "status": row[1],
            "surface": row[2],
            "source_ref": row[3],
            "evidence_path": row[4],
        },
        "answer": (
            None
            if answer_row is None
            else {
                "answer_status": answer_row[0],
                "evidence_status": answer_row[1],
                "source_ref": answer_row[2],
            }
        ),
        "open_quarantine": [
            {
                "quarantine_kind": quarantine_row[0],
                "reason": quarantine_row[1],
                "priority": quarantine_row[2],
                "status": quarantine_row[3],
            }
            for quarantine_row in quarantine_rows
        ],
    }


def _inspect_active_catalog_unit(
    *,
    connection: sqlite3.Connection,
    unit_id: str,
) -> JsonObject | None:
    """Return one canonical catalog unit without exposing lease tokens."""
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_units"
    ):
        return None
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT
              units.run_id,
              units.unit_id,
              units.unit_type,
              units.priority_band,
              units.priority_order,
              units.source_ref,
              units.source_hash,
              units.source_size_bytes,
              units.complexity_score,
              units.status,
              units.locked_by,
              units.locked_at_utc,
              units.lease_expires_at_utc,
              units.attempt_count,
              units.completed_at_utc,
              units.validation_status,
              units.coverage_status,
              runs.run_status
            FROM catalog_units AS units
            JOIN catalog_runs AS runs
              ON runs.run_id = units.run_id
            WHERE units.unit_id = ?
            ORDER BY
              CASE WHEN runs.run_status = 'active' THEN 0 ELSE 1 END,
              units.priority_order,
              units.run_id
            LIMIT 1
            """,
            (unit_id,),
        ).fetchone(),
    )
    if row is None:
        return None
    run_id = _row_text(row, "run_id")
    actual_unit_id = _row_text(row, "unit_id")
    notes = _catalog_unit_notes(
        connection=connection,
        run_id=run_id,
        unit_id=actual_unit_id,
    )
    outputs = _catalog_unit_outputs(
        connection=connection,
        run_id=run_id,
        unit_id=actual_unit_id,
    )
    return {
        "status": "ok ",
        "entity_kind": "catalog_unit ",
        "catalog_run_kind": "hard_reset",
        "unit": {
            "run_id": run_id,
            "run_status": _row_text(row, "run_status"),
            "unit_id": actual_unit_id,
            "unit_type": _row_text(row, "unit_type"),
            "priority_band": _row_text(row, "priority_band"),
            "priority_order": _row_int(row, "priority_order"),
            "source_ref": _row_text(row, "source_ref"),
            "source_hash": _row_text(row, "source_hash"),
            "source_size_bytes": _row_int(row, "source_size_bytes"),
            "complexity_score": _row_int(row, "complexity_score"),
            "status": _row_text(row, "status"),
            "attempt_count": _row_int(row, "attempt_count"),
            "completed_at_utc": _row_text(row, "completed_at_utc") or None,
            "validation_status": _row_text(row, "validation_status"),
            "coverage_status": _row_text(row, "coverage_status"),
        },
        "lease": {
            "locked_by": _row_text(row, "locked_by") or None,
            "locked_at_utc": _row_text(row, "locked_at_utc") or None,
            "lease_expires_at_utc": _row_text(row, "lease_expires_at_utc")
            or None,
            "lease_handle_exposed": False,
        },
        "notes": notes,
        "outputs": outputs,
        "note_surfaces": [note["note_surface"] for note in notes],
        "incomplete_coverage_non_blocking": _row_text(row, "coverage_status")
        != "complete",
    }


def _catalog_unit_notes(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    unit_id: str,
) -> list[JsonObject]:
    rows = cast(
        "list[sqlite3.Row]",
        connection.execute(
            """
            SELECT note_surface, note_status, note_text, updated_at_utc
            FROM catalog_unit_notes
            WHERE run_id = ?
              AND unit_id = ?
            ORDER BY note_surface
            """,
            (run_id, unit_id),
        ).fetchall(),
    )
    return [
        {
            "note_surface": _row_text(row, "note_surface"),
            "note_status": _row_text(row, "note_status"),
            "note_text": _snippet(_row_text(row, "note_text")),
            "updated_at_utc": _row_text(row, "updated_at_utc"),
        }
        for row in rows
    ]


def _catalog_unit_outputs(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    unit_id: str,
) -> list[JsonObject]:
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_unit_outputs"
    ):
        return []
    rows = cast(
        "list[sqlite3.Row]",
        connection.execute(
            """
            SELECT output_sha256, validation_status, saved_by_tool,
            created_at_utc, source_ref
            FROM catalog_unit_outputs
            WHERE run_id = ?
              AND unit_id = ?
            ORDER BY created_at_utc DESC, output_sha256
            LIMIT 5
            """,
            (run_id, unit_id),
        ).fetchall(),
    )
    return [
        {
            "output_sha256": _row_text(row, "output_sha256"),
            "validation_status": _row_text(row, "validation_status"),
            "saved_by_tool": _row_text(row, "saved_by_tool"),
            "created_at_utc": _row_text(row, "created_at_utc"),
            "source_ref": _row_text(row, "source_ref"),
        }
        for row in rows
    ]


def _catalog_unit_output_candidates(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return hits from saved canonical catalog semantic and graph outputs."""
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_unit_outputs"
    ):
        return []
    rows = cast(
        "list[sqlite3.Row]",
        connection.execute(
            """
            SELECT
              outputs.run_id,
              outputs.unit_id,
              units.unit_type,
              units.priority_band,
              outputs.validation_status,
              outputs.source_ref,
              units.source_ref AS unit_source_ref,
              outputs.output_json
            FROM catalog_unit_outputs AS outputs
            JOIN catalog_units AS units
              ON units.run_id = outputs.run_id
             AND units.unit_id = outputs.unit_id
            WHERE pancakes_catalog_search_match(
                outputs.unit_id,
                outputs.output_json,
                outputs.validation_status,
                outputs.source_ref,
                units.unit_type,
                units.priority_band,
                units.source_ref
              ) = 1
            ORDER BY outputs.created_at_utc DESC, units.priority_order,
            outputs.unit_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": "catalog_unit_output",
            "rank_reason": (
                "Saved canonical catalog semantic/graph output matched the "
                "query terms."
            ),
            "run_id": _row_text(row, "run_id"),
            "unit_id": _row_text(row, "unit_id"),
            "unit_type": _row_text(row, "unit_type"),
            "priority_band": _row_text(row, "priority_band"),
            "validation_status": _row_text(row, "validation_status"),
            "source_ref": _row_text(row, "source_ref"),
            "unit_source_ref": _row_text(row, "unit_source_ref"),
            "snippet": _snippet(_row_text(row, "output_json")),
        }
        for row in rows
    ]


def _graph_candidates(
    *,
    connection: sqlite3.Connection,
    limit: int,
    parsed_query: CatalogSearchQuery,
) -> list[JsonObject]:
    """Return fast graph-edge hits for connection-style catalog queries."""
    if not _sqlite_table_exists(
        connection=connection, table_name="entity_edges"
    ):
        return []
    rows = cast(
        "list[sqlite3.Row]",
        connection.execute(
            """
            SELECT
              edges.edge_id,
              edges.domain,
              edges.edge_kind,
              edges.from_node_id,
              edges.to_node_id,
              edges.payload_json,
              edges.source_ref,
              from_nodes.canonical_label AS from_label,
              to_nodes.canonical_label AS to_label,
              from_nodes.payload_json AS from_payload_json,
              to_nodes.payload_json AS to_payload_json
            FROM entity_edges AS edges
            LEFT JOIN entity_nodes AS from_nodes
              ON from_nodes.node_id = edges.from_node_id
             AND from_nodes.domain = edges.domain
             AND from_nodes.valid_to IS NULL
            LEFT JOIN entity_nodes AS to_nodes
              ON to_nodes.node_id = edges.to_node_id
             AND to_nodes.domain = edges.domain
             AND to_nodes.valid_to IS NULL
            WHERE edges.valid_to IS NULL
              AND pancakes_catalog_search_match(
                edges.edge_id,
                edges.domain,
                edges.edge_kind,
                edges.from_node_id,
                edges.to_node_id,
                edges.payload_json,
                edges.source_ref,
                from_nodes.canonical_label,
                from_nodes.payload_json,
                to_nodes.canonical_label,
                to_nodes.payload_json
              ) = 1
            ORDER BY edges.domain, edges.edge_kind, edges.edge_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    candidates = [
        _graph_candidate_payload(row=row, parsed_query=parsed_query)
        for row in rows
    ]
    return sorted(candidates, key=_graph_rank_key)


def _graph_candidate_payload(
    *,
    row: sqlite3.Row,
    parsed_query: CatalogSearchQuery,
) -> JsonObject:
    edge_payload = _row_text(row, "payload_json")
    from_payload = _row_text(row, "from_payload_json")
    to_payload = _row_text(row, "to_payload_json")
    endpoint_haystack = " ".join(
        (
            _row_text(row, "from_node_id"),
            _row_text(row, "to_node_id"),
            _row_text(row, "from_label"),
            _row_text(row, "to_label"),
            from_payload,
            to_payload,
        )
    )
    edge_haystack = " ".join((_row_text(row, "edge_kind"), edge_payload))
    full_haystack = f"{endpoint_haystack} {edge_haystack}".casefold()
    signals = _graph_rank_signals(
        parsed_query=parsed_query,
        full_haystack=full_haystack,
        endpoint_text=endpoint_haystack.casefold(),
        edge_text=edge_haystack.casefold(),
    )
    source_ref = _row_text(row, "source_ref")
    return {
        "kind": "catalog_graph_edge",
        "rank_reason": _graph_rank_reason(signals=signals),
        "rationale": _graph_candidate_rationale(signals=signals),
        "rank_score": signals.score,
        "score_before_policy": signals.score_before_policy,
        "score_after_policy": signals.score_after_policy,
        "candidate_app_bindings": signals.candidate_app_bindings,
        "matched_app_intents": signals.matched_apps,
        "unmatched_app_intents": signals.unmatched_app_intents,
        "matched_endpoint_term_count": signals.endpoint_term_matches,
        "matched_control_surface_term_count": len(
            signals.control_surface_matches
        ),
        "matched_control_surface_terms": signals.control_surface_matches,
        "matched_workflow_term_count": signals.workflow_term_matches,
        "matched_generic_field_tokens": signals.generic_field_token_matches,
        "matched_generic_utility_terms": signals.generic_utility_matches,
        "matched_api_surface_terms": signals.api_surface_matches,
        "generic_field_token_only": signals.generic_field_token_only,
        "generic_utility_candidate": signals.generic_utility_candidate,
        "endpoint_only_candidate": signals.endpoint_only_candidate,
        "edge_kind_only_match": signals.edge_kind_only_match,
        "no_app_score_cap_applied": signals.no_app_score_cap_applied,
        "wrong_app_penalty_applied": signals.wrong_app_penalty_applied,
        "applied_penalties": signals.applied_penalties,
        "applied_bonuses": signals.applied_bonuses,
        "edge_id": _row_text(row, "edge_id"),
        "domain": _row_text(row, "domain"),
        "edge_kind": _row_text(row, "edge_kind"),
        "from_node_id": _row_text(row, "from_node_id"),
        "to_node_id": _row_text(row, "to_node_id"),
        "from_label": _row_text(row, "from_label"),
        "to_label": _row_text(row, "to_label"),
        "source_ref": source_ref,
        "source_refs": [source_ref] if source_ref else [],
        "snippet": _snippet(edge_payload),
    }


def _graph_rank_key(
    candidate: Mapping[str, object],
) -> tuple[int, int, str, str, str]:
    return (
        -_int_mapping_value(candidate, "rank_score"),
        1 if candidate.get("edge_kind_only_match") is True else 0,
        str(candidate.get("domain") or ""),
        str(candidate.get("edge_kind") or ""),
        str(candidate.get("edge_id") or ""),
    )


def _graph_rank_signals(
    *,
    parsed_query: CatalogSearchQuery,
    full_haystack: str,
    endpoint_text: str,
    edge_text: str,
) -> CatalogGraphRankSignals:
    """Return v10 graph ranking signals with executable app-intent authority."""
    app_signals = _graph_app_signals(
        parsed_query=parsed_query,
        full_haystack=full_haystack,
    )
    term_signals = _graph_term_signals(
        parsed_query=parsed_query,
        full_haystack=full_haystack,
        endpoint_text=endpoint_text,
        edge_text=edge_text,
    )
    flags = _graph_candidate_flags(
        parsed_query=parsed_query,
        app_signals=app_signals,
        term_signals=term_signals,
    )
    score_before_policy = _graph_base_score(term_signals=term_signals)
    policy = _graph_policy_result(
        score_before_policy=score_before_policy,
        app_signals=app_signals,
        term_signals=term_signals,
        flags=flags,
    )
    return CatalogGraphRankSignals(
        score=policy.score,
        score_before_policy=score_before_policy,
        score_after_policy=policy.score,
        candidate_app_bindings=app_signals.candidate_app_bindings,
        matched_apps=app_signals.matched_apps,
        unmatched_app_intents=app_signals.unmatched_app_intents,
        endpoint_term_matches=len(term_signals.endpoint_matched_terms),
        control_surface_matches=term_signals.control_surface_matches,
        workflow_term_matches=term_signals.workflow_term_matches,
        generic_field_token_matches=term_signals.generic_field_token_matches,
        generic_utility_matches=term_signals.generic_utility_matches,
        api_surface_matches=term_signals.api_surface_matches,
        generic_field_token_only=flags.generic_field_token_only,
        generic_utility_candidate=flags.generic_utility_candidate,
        endpoint_only_candidate=flags.endpoint_only_candidate,
        edge_kind_only_match=flags.edge_kind_only_match,
        no_app_score_cap_applied=policy.no_app_score_cap_applied,
        wrong_app_penalty_applied=policy.wrong_app_penalty_applied,
        applied_penalties=policy.applied_penalties,
        applied_bonuses=policy.applied_bonuses,
    )


def _graph_app_signals(
    *,
    parsed_query: CatalogSearchQuery,
    full_haystack: str,
) -> CatalogGraphAppSignals:
    """Return explicit app intent matches for one graph candidate."""
    explicit_app_intents = tuple(
        app_slug
        for app_slug in parsed_query.app_slugs
        if app_slug not in CATALOG_GRAPH_GENERIC_APP_INTENT_SLUGS
    )
    candidate_app_bindings = _graph_candidate_app_bindings(full_haystack)
    matched_apps = tuple(
        app_slug
        for app_slug in explicit_app_intents
        if app_slug in candidate_app_bindings
    )
    unmatched_app_intents = tuple(
        app_slug
        for app_slug in explicit_app_intents
        if app_slug not in matched_apps
    )
    return CatalogGraphAppSignals(
        explicit_app_intents=explicit_app_intents,
        candidate_app_bindings=candidate_app_bindings,
        matched_apps=matched_apps,
        unmatched_app_intents=unmatched_app_intents,
    )


def _graph_term_signals(
    *,
    parsed_query: CatalogSearchQuery,
    full_haystack: str,
    endpoint_text: str,
    edge_text: str,
) -> CatalogGraphTermSignals:
    """Return matched query terms for one graph candidate."""
    endpoint_matched_terms = _graph_matched_terms(
        terms=parsed_query.terms,
        text=endpoint_text,
    )
    edge_matched_terms = _graph_matched_terms(
        terms=parsed_query.terms, text=edge_text
    )
    return CatalogGraphTermSignals(
        endpoint_matched_terms=endpoint_matched_terms,
        edge_matched_terms=edge_matched_terms,
        non_generic_endpoint_term_matches=_non_generic_graph_term_count(
            endpoint_matched_terms,
        ),
        non_generic_edge_term_matches=_non_generic_graph_term_count(
            edge_matched_terms
        ),
        workflow_term_matches=_graph_workflow_match_count(
            terms=parsed_query.terms,
            text=full_haystack,
        ),
        generic_field_token_matches=_generic_graph_field_token_matches(
            endpoint_terms=endpoint_matched_terms,
            edge_terms=edge_matched_terms,
        ),
        control_surface_matches=_graph_control_surface_matches(
            surfaces=parsed_query.control_surface_terms,
            text=full_haystack,
        ),
        generic_utility_matches=_graph_generic_utility_matches(
            utilities=parsed_query.generic_utility_terms,
            text=full_haystack,
        ),
        api_surface_matches=_graph_matched_terms(
            terms=parsed_query.api_surface_terms,
            text=full_haystack,
        ),
    )


def _graph_candidate_flags(
    *,
    parsed_query: CatalogSearchQuery,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
) -> CatalogGraphCandidateFlags:
    """Return fallback candidate kinds used by v10 graph policy."""
    generic_field_token_only = _generic_field_token_only_candidate(
        app_signals=app_signals,
        term_signals=term_signals,
    )
    return CatalogGraphCandidateFlags(
        generic_field_token_only=generic_field_token_only,
        generic_utility_candidate=_generic_utility_graph_candidate(
            candidate_app_bindings=app_signals.candidate_app_bindings,
            control_surface_matches=term_signals.control_surface_matches,
            generic_field_token_matches=term_signals.generic_field_token_matches,
            generic_utility_matches=term_signals.generic_utility_matches,
        ),
        endpoint_only_candidate=_endpoint_only_graph_candidate(
            app_signals=app_signals,
            term_signals=term_signals,
        ),
        edge_kind_only_match=_edge_kind_only_graph_candidate(
            generic_field_token_only=generic_field_token_only,
            term_signals=term_signals,
        ),
        explicit_utility_only_query=(
            bool(term_signals.generic_utility_matches)
            and not app_signals.explicit_app_intents
            and not parsed_query.control_surface_terms
        ),
    )


def _generic_field_token_only_candidate(
    *,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
) -> bool:
    """Return whether only generic field tokens support this graph candidate."""
    return (
        bool(term_signals.generic_field_token_matches)
        and not app_signals.matched_apps
        and not term_signals.control_surface_matches
        and term_signals.workflow_term_matches == 0
        and term_signals.non_generic_endpoint_term_matches == 0
        and term_signals.non_generic_edge_term_matches == 0
    )


def _endpoint_only_graph_candidate(
    *,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
) -> bool:
    """Return whether API terms matched only a generic endpoint surface."""
    return (
        bool(term_signals.api_surface_matches)
        and not app_signals.matched_apps
        and not term_signals.control_surface_matches
        and not _non_generic_app_bindings(app_signals.candidate_app_bindings)
    )


def _edge_kind_only_graph_candidate(
    *,
    generic_field_token_only: bool,
    term_signals: CatalogGraphTermSignals,
) -> bool:
    """Return whether only the edge-kind text matched a non-generic term."""
    return (
        term_signals.non_generic_endpoint_term_matches == 0
        and term_signals.non_generic_edge_term_matches > 0
        and not generic_field_token_only
    )


def _graph_base_score(*, term_signals: CatalogGraphTermSignals) -> int:
    """Return the pre-policy graph score from normal term overlap."""
    return (
        term_signals.non_generic_endpoint_term_matches * 12
        + term_signals.non_generic_edge_term_matches * 5
        + term_signals.workflow_term_matches * 4
        + len(term_signals.generic_field_token_matches) * 2
    )


def _graph_policy_result(
    *,
    score_before_policy: int,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
    flags: CatalogGraphCandidateFlags,
) -> CatalogGraphPolicyResult:
    """Return the score after v10 bonuses, caps, and penalties."""
    score = score_before_policy
    applied_bonuses: list[str] = []
    applied_penalties: list[str] = []
    score = _apply_graph_bonuses(
        score=score,
        app_signals=app_signals,
        term_signals=term_signals,
        flags=flags,
        applied_bonuses=applied_bonuses,
    )
    no_app_policy = _graph_no_app_policy(
        score=score,
        app_signals=app_signals,
        term_signals=term_signals,
    )
    score = no_app_policy.score
    applied_penalties.extend(no_app_policy.applied_penalties)
    score = _apply_graph_fallback_penalties(
        score=score,
        app_signals=app_signals,
        flags=flags,
        applied_penalties=applied_penalties,
    )
    return CatalogGraphPolicyResult(
        score=score,
        no_app_score_cap_applied=no_app_policy.no_app_score_cap_applied,
        wrong_app_penalty_applied=no_app_policy.wrong_app_penalty_applied,
        applied_penalties=tuple(applied_penalties),
        applied_bonuses=tuple(applied_bonuses),
    )


def _apply_graph_bonuses(
    *,
    score: int,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
    flags: CatalogGraphCandidateFlags,
    applied_bonuses: list[str],
) -> int:
    """Return score after v10 authority bonuses."""
    if app_signals.matched_apps:
        score += (
            len(app_signals.matched_apps)
            * CATALOG_GRAPH_EXPLICIT_APP_MATCH_BONUS
        )
        applied_bonuses.append("explicit_app_match_bonus")
    if (
        len(app_signals.matched_apps)
        >= CATALOG_GRAPH_MULTI_APP_BRIDGE_MIN_MATCHES
    ):
        score += CATALOG_GRAPH_MULTI_APP_BRIDGE_BONUS
        applied_bonuses.append("multi_app_bridge_bonus")
    if term_signals.control_surface_matches:
        score += (
            len(term_signals.control_surface_matches)
            * CATALOG_GRAPH_CONTROL_SURFACE_BONUS
        )
        applied_bonuses.append("explicit_control_surface_bonus")
    if flags.explicit_utility_only_query:
        score += (
            len(term_signals.generic_utility_matches)
            * CATALOG_GRAPH_EXPLICIT_UTILITY_BONUS
        )
        applied_bonuses.append("explicit_generic_utility_bonus")
    return score


def _graph_no_app_policy(
    *,
    score: int,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
) -> CatalogGraphNoAppPolicy:
    """Return the computed result for the caller."""
    if not app_signals.explicit_app_intents or app_signals.matched_apps:
        return CatalogGraphNoAppPolicy(
            score=score,
            no_app_score_cap_applied=False,
            wrong_app_penalty_applied=False,
            applied_penalties=(),
        )
    return _missed_explicit_app_policy(
        score=score,
        app_signals=app_signals,
        term_signals=term_signals,
    )


def _missed_explicit_app_policy(
    *,
    score: int,
    app_signals: CatalogGraphAppSignals,
    term_signals: CatalogGraphTermSignals,
) -> CatalogGraphNoAppPolicy:
    """Return policy effects for graph edges that miss explicit app intent."""
    applied_penalties: list[str] = []
    score_cap = (
        CATALOG_GRAPH_NO_APP_CONTROL_SURFACE_CAP
        if term_signals.control_surface_matches
        else CATALOG_GRAPH_NO_APP_MATCH_CAP
    )
    no_app_score_cap_applied = score > score_cap
    if no_app_score_cap_applied:
        score = score_cap
        applied_penalties.append("no_app_score_cap")
    wrong_app_penalty_applied = bool(
        _non_generic_app_bindings(app_signals.candidate_app_bindings),
    )
    if wrong_app_penalty_applied:
        score -= CATALOG_GRAPH_WRONG_APP_PENALTY
        applied_penalties.append("wrong_app_penalty")
    else:
        score -= CATALOG_GRAPH_NO_APP_MISMATCH_PENALTY
        applied_penalties.append("no_app_mismatch_penalty")
    return CatalogGraphNoAppPolicy(
        score=score,
        no_app_score_cap_applied=no_app_score_cap_applied,
        wrong_app_penalty_applied=wrong_app_penalty_applied,
        applied_penalties=tuple(applied_penalties),
    )


def _apply_graph_fallback_penalties(
    *,
    score: int,
    app_signals: CatalogGraphAppSignals,
    flags: CatalogGraphCandidateFlags,
    applied_penalties: list[str],
) -> int:
    """Return score after fallback-specific penalties."""
    if app_signals.explicit_app_intents and flags.generic_utility_candidate:
        score -= CATALOG_GRAPH_GENERIC_UTILITY_PENALTY
        applied_penalties.append("generic_utility_penalty")
    if app_signals.explicit_app_intents and flags.endpoint_only_candidate:
        score -= CATALOG_GRAPH_ENDPOINT_ONLY_PENALTY
        applied_penalties.append("endpoint_only_penalty")
    if flags.edge_kind_only_match:
        score -= CATALOG_GRAPH_EDGE_KIND_ONLY_PENALTY
        applied_penalties.append("edge_kind_only_penalty")
    if flags.generic_field_token_only and not flags.explicit_utility_only_query:
        score = min(
            score - CATALOG_GRAPH_GENERIC_FIELD_TOKEN_ONLY_PENALTY,
            CATALOG_GRAPH_GENERIC_FIELD_TOKEN_ONLY_CAP,
        )
        applied_penalties.append("generic_field_token_only_cap")
    return score


def _graph_text_mentions_app(*, text: str, app_slug: str) -> bool:
    app_tokens = (app_slug, *CATALOG_APP_ALIASES.get(app_slug, ()))
    return any(token.casefold() in text for token in app_tokens)


def _graph_candidate_app_bindings(text: str) -> tuple[str, ...]:
    """Return app slugs bound to a graph candidate by node IDs, labels, or.

    payload.
    """
    return tuple(
        app_slug
        for app_slug in CATALOG_APP_ALIASES
        if _graph_text_mentions_app(text=text, app_slug=app_slug)
    )


def _non_generic_app_bindings(
    candidate_app_bindings: Sequence[str],
) -> tuple[str, ...]:
    """Return app bindings that are not generic utility pseudo-apps."""
    return tuple(
        app_slug
        for app_slug in candidate_app_bindings
        if app_slug not in CATALOG_GRAPH_GENERIC_APP_INTENT_SLUGS
    )


def _graph_matched_terms(*, terms: Sequence[str], text: str) -> tuple[str, ...]:
    return tuple(term.casefold() for term in terms if term.casefold() in text)


def _generic_graph_field_token_matches(
    *,
    endpoint_terms: Sequence[str],
    edge_terms: Sequence[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            frozenset(
                term
                for term in (*endpoint_terms, *edge_terms)
                if term in CATALOG_GRAPH_GENERIC_FIELD_TOKENS
            )
        )
    )


def _non_generic_graph_term_count(terms: Sequence[str]) -> int:
    return sum(
        1 for term in terms if term not in CATALOG_GRAPH_GENERIC_FIELD_TOKENS
    )


def _graph_control_surface_matches(
    *,
    surfaces: Sequence[str],
    text: str,
) -> tuple[str, ...]:
    """Return requested control surfaces represented by a graph candidate."""
    matches: list[str] = []
    for surface in surfaces:
        aliases = CATALOG_CONTROL_SURFACE_ALIASES.get(surface, (surface,))
        if surface in text or any(alias in text for alias in aliases):
            matches.append(surface)
    return tuple(matches)


def _graph_generic_utility_matches(
    *,
    utilities: Sequence[str],
    text: str,
) -> tuple[str, ...]:
    """Return requested generic utilities represented by a graph candidate."""
    matches: list[str] = []
    for utility in utilities:
        aliases = CATALOG_GENERIC_UTILITY_ALIASES.get(utility, (utility,))
        if utility in text or any(alias in text for alias in aliases):
            matches.append(utility)
    return tuple(matches)


def _generic_utility_graph_candidate(
    *,
    candidate_app_bindings: Sequence[str],
    control_surface_matches: Sequence[str],
    generic_field_token_matches: Sequence[str],
    generic_utility_matches: Sequence[str],
) -> bool:
    """Return whether a graph candidate is generic utility evidence, not app.

    evidence.
    """
    if control_surface_matches:
        return False
    if not generic_field_token_matches and not generic_utility_matches:
        return False
    return not _non_generic_app_bindings(candidate_app_bindings)


def _graph_workflow_match_count(*, terms: Sequence[str], text: str) -> int:
    return sum(
        1
        for term in terms
        if term in CATALOG_GRAPH_WORKFLOW_TERMS
        and term not in CATALOG_GRAPH_GENERIC_FIELD_TOKENS
        and term in text
    )


def _graph_rank_reason(*, signals: CatalogGraphRankSignals) -> str:
    reason = "graph_contextual_fallback"
    if signals.matched_apps:
        reason = "graph_explicit_app_intent_match"
    elif signals.control_surface_matches:
        reason = "graph_control_surface_match"
    elif signals.endpoint_only_candidate:
        reason = "graph_endpoint_only_fallback"
    elif signals.generic_utility_candidate:
        reason = "graph_generic_utility_match"
    elif signals.generic_field_token_only:
        reason = "graph_generic_field_token_fallback"
    elif signals.endpoint_term_matches:
        reason = "graph_resource_or_workflow_term_match"
    elif signals.edge_kind_only_match:
        reason = "graph_edge_kind_only_fallback"
    return reason


def _graph_candidate_rationale(*, signals: CatalogGraphRankSignals) -> str:
    """Return a concise human-facing graph ranking rationale."""
    rationale = "Matched the catalog graph context."
    if signals.matched_apps:
        rationale = (
            "Matches explicit app intent: "
            + ", ".join(signals.matched_apps)
            + "."
        )
    elif signals.control_surface_matches:
        rationale = (
            "Matches explicit control surface: "
            + ", ".join(signals.control_surface_matches)
            + "."
        )
    elif signals.endpoint_only_candidate:
        rationale = "Endpoint-only API surface kept as fallback."
    elif signals.generic_utility_candidate:
        rationale = "Matches a requested generic utility."
    elif signals.generic_field_token_only:
        rationale = (
            "Only generic JSON or field tokens matched; ranked as fallback."
        )
    elif signals.endpoint_term_matches:
        rationale = "Matches workflow terms on graph endpoints."
    elif signals.edge_kind_only_match:
        rationale = "Only the generic edge kind matched; ranked as fallback."
    return rationale


def _search_documents(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return hits from indexed catalog search documents."""
    rows = cast(
        "list[tuple[str, str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT document_id, surface, title, record_kind, source_ref, body,
            search_text
            FROM catalog_search_documents
            WHERE valid_to IS NULL
              AND pancakes_catalog_search_match(
                title, body, tags_json, search_text, surface, record_kind
              ) = 1
            ORDER BY surface, record_kind, title, document_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": "catalog_search_document",
            "rank_reason": (
                "Indexed catalog document text matched the normalized query "
                "terms."
            ),
            "document_id": row[0],
            "surface": row[1],
            "title": row[2],
            "record_kind": row[3],
            "source_ref": row[4],
            "snippet": _snippet(row[5] or row[6]),
        }
        for row in rows
    ]


def _semantic_answers(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return compact semantic answer hits already persisted in SQLite."""
    rows = cast(
        "list[tuple[str, int, str, str, str, str, str | None]]",
        connection.execute(
            """
            SELECT
            a.unit_id, a.unit_number, a.answer_status, a.evidence_status,
            a.source_ref,
              a.answer_json, u.surface
            FROM catalog_plan_semantic_answers a
            LEFT JOIN catalog_plan_units u
              ON u.unit_number = a.unit_number
             AND u.valid_to IS NULL
            WHERE a.valid_to IS NULL
              AND pancakes_catalog_search_match(
                a.unit_id, a.answer_json, a.evidence_status, u.surface
              ) = 1
            ORDER BY a.unit_number, a.created_at_utc
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": "catalog_semantic_answer",
            "rank_reason": (
                "Persisted semantic answer matched the normalized query terms."
            ),
            "unit_id": row[0],
            "unit_number": row[1],
            "answer_status": row[2],
            "evidence_status": row[3],
            "source_ref": row[4],
            "surface": "" if row[6] is None else row[6],
            "snippet": _snippet(row[5]),
        }
        for row in rows
    ]


def _structure_prerequisites(
    *,
    connection: sqlite3.Connection,
    limit: int,
    terms: Sequence[str],
) -> list[JsonObject]:
    """Return datastore and webhook structure evidence rows."""
    return [
        *_datastore_prerequisites(connection=connection, limit=limit),
        *_webhook_prerequisites(
            connection=connection, limit=limit, terms=terms
        ),
        *_scraped_infrastructure_prerequisites(
            connection=connection, limit=limit
        ),
    ][:limit]


def _datastore_prerequisites(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return matching datastore structure evidence."""
    rows = cast(
        "list[tuple[str, str, str, str, str]]",
        connection.execute(
            """
            SELECT evidence_id, app_slug, datastore_slug, source_ref,
            structure_json
            FROM make_datastore_structure_evidence
            WHERE valid_to IS NULL
              AND pancakes_catalog_search_match(
                app_slug, datastore_slug, structure_json, source_ref
              ) = 1
            ORDER BY app_slug, datastore_slug, observed_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": "make_datastore_structure_evidence",
            "rank_reason": (
                "Datastore structure evidence matched the normalized query "
                "terms."
            ),
            "evidence_id": row[0],
            "app_slug": row[1],
            "datastore_slug": row[2],
            "source_ref": row[3],
            "snippet": _snippet(row[4]),
        }
        for row in rows
    ]


def _webhook_prerequisites(
    *,
    connection: sqlite3.Connection,
    limit: int,
    terms: Sequence[str],
) -> list[JsonObject]:
    """Return matching webhook structure evidence."""
    rows = cast(
        "list[tuple[str, str, str, str, str]]",
        connection.execute(
            """
            SELECT evidence_id, app_slug, webhook_slug, source_ref,
            structure_json
            FROM make_webhook_structure_evidence
            WHERE valid_to IS NULL
              AND pancakes_catalog_search_match(
                app_slug, webhook_slug, structure_json, source_ref
              ) = 1
            ORDER BY app_slug, webhook_slug, observed_at_utc DESC
            LIMIT ?
            """,
            (max(limit * 5, 25),),
        ).fetchall(),
    )
    candidates: list[JsonObject] = []
    for row in rows:
        matched_terms = _matched_structure_terms(
            terms=terms,
            values=(row[1], row[2], row[3], row[4]),
        )
        material_terms = _material_structure_terms(
            terms=terms,
            matched_terms=matched_terms,
        )
        if not _structure_row_is_material_match(
            terms=terms,
            material_terms=material_terms,
            matched_terms=matched_terms,
        ):
            continue
        candidates.append(
            {
                "kind": "make_webhook_structure_evidence",
                "rank_reason": (
                    "Webhook structure evidence matched the normalized query "
                    "terms."
                ),
                "sqlite_table": "make_webhook_structure_evidence",
                "expected_sqlite_columns": [
                    "evidence_id ",
                    "app_slug ",
                    "webhook_slug ",
                    "structure_json ",
                    "source_ref ",
                    "observed_at_utc",
                ],
                "evidence_status": "populated",
                "blocking": False,
                "evidence_id": row[0],
                "app_slug": row[1],
                "webhook_slug": row[2],
                "source_ref": row[3],
                "matched_terms": matched_terms,
                "material_matched_terms": material_terms,
                "structure_field_paths": _structure_field_paths(row[4]),
                "snippet": _snippet(row[4]),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def _matched_structure_terms(
    *, terms: Sequence[str], values: Sequence[str]
) -> tuple[str, ...]:
    """Return normalized query terms matched by one structure evidence row."""
    haystack = " ".join(values).casefold()
    return tuple(term for term in terms if term in haystack)


def _material_structure_terms(
    *,
    terms: Sequence[str],
    matched_terms: Sequence[str],
) -> tuple[str, ...]:
    """Return matched terms that identify the specific structure row, not the.

    table.

    family.
    """
    term_set = frozenset(terms)
    if not term_set.difference(CATALOG_STRUCTURE_GENERIC_TERMS):
        return tuple(matched_terms)
    return tuple(
        term
        for term in matched_terms
        if term not in CATALOG_STRUCTURE_GENERIC_TERMS
    )


def _structure_row_is_material_match(
    *,
    terms: Sequence[str],
    material_terms: Sequence[str],
    matched_terms: Sequence[str],
) -> bool:
    """Return whether a structure row should satisfy a query-specific evidence.

    request.
    """
    if material_terms:
        return True
    non_generic_terms = frozenset(terms).difference(
        CATALOG_STRUCTURE_GENERIC_TERMS
    )
    return not non_generic_terms and bool(matched_terms)


def _structure_field_paths(structure_json: str) -> list[str]:
    """Return the computed result for the caller."""
    if not structure_json:
        return []
    try:
        payload = cast("JsonObject", json.loads(structure_json))
    except json.JSONDecodeError:
        return []
    fields_value = payload.get("fields")
    if not isinstance(fields_value, list):
        return []
    fields = cast("list[object]", fields_value)
    paths: list[str] = []
    for item in fields:
        if len(paths) >= CATALOG_STRUCTURE_FIELD_PATH_LIMIT:
            break
        path = _structure_field_path(item)
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def _structure_field_path(item: object) -> str | None:
    """Return the computed result for the caller."""
    if isinstance(item, str):
        return item.strip() or None
    if not isinstance(item, dict):
        return None
    field = cast("Mapping[str, object]", item)
    for key in ("path", "field_path", "name", "source_path"):
        value = field.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _scraped_infrastructure_prerequisites(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return matching Windows-Service scraped infrastructure evidence."""
    rows: list[JsonObject] = []
    for table_name in SCRAPED_INFRASTRUCTURE_TABLES:
        rows.extend(
            _scraped_infrastructure_prerequisites_for_table(
                connection=connection,
                table_name=table_name,
                limit=limit,
            )
        )
    return rows[:limit]


def _scraped_infrastructure_prerequisites_for_table(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    limit: int,
) -> list[JsonObject]:
    rows = cast(
        "list[tuple[str, str, str, str, str, str, str]]",
        connection.execute(
            f"""  # noqa: S608
            SELECT evidence_id, project_id, node_id, app_slug, resource_slug,
                   source_ref, evidence_json
            FROM {table_name}
            WHERE valid_to IS NULL
              AND pancakes_catalog_search_match(
            project_id, node_id, app_slug, resource_slug, evidence_json,
            source_ref
              ) = 1
            ORDER BY project_id, node_id, app_slug, resource_slug,
            observed_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": table_name,
            "rank_reason": (
                "Scraped infrastructure evidence matched the normalized query "
                "terms."
            ),
            "evidence_domain": SCRAPED_INFRASTRUCTURE_DOMAIN_BY_TABLE[
                table_name
            ],
            "evidence_id": row[0],
            "project_id": row[1],
            "node_id": row[2],
            "app_slug": row[3],
            "resource_slug": row[4],
            "source_ref": row[5],
            "snippet": _snippet(row[6]),
        }
        for row in rows
    ]


def _quarantine_gaps(
    *,
    connection: sqlite3.Connection,
    limit: int,
) -> list[JsonObject]:
    """Return current catalog-plan quarantine gaps relevant to the query."""
    rows = cast(
        "list[tuple[str | None, str, str, int, str, str, str]]",
        connection.execute(
            """
            SELECT
              unit_id, quarantine_kind, reason, priority, status, source_ref,
              retry_policy_json
            FROM catalog_plan_quarantine_records
            WHERE resolved_at_utc IS NULL
              AND pancakes_catalog_search_match(
            unit_id, quarantine_kind, reason, evidence_gap_json,
            retry_policy_json,
                source_ref
              ) = 1
            ORDER BY priority DESC, created_at_utc, quarantine_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall(),
    )
    return [
        {
            "kind": "catalog_missing_evidence",
            "rank_reason": (
                "Open catalog work gap matched the normalized query terms."
            ),
            "unit_id": "" if row[0] is None else row[0],
            "quarantine_kind": row[1],
            "reason": row[2],
            "priority": row[3],
            "status": row[4],
            "source_ref": row[5],
            "retry_policy": _snippet(row[6]),
        }
        for row in rows
    ]


def _planned_structure_gaps(
    *,
    terms: Sequence[str],
    structure_prerequisites: Sequence[JsonObject],
) -> list[JsonObject]:
    """Return explicit gaps for future datastore/webhook reverse-engineering.

    rows.
    """
    existing_kinds = frozenset(
        str(item.get("kind")) for item in structure_prerequisites
    )
    gaps: list[JsonObject] = []
    term_set = frozenset(terms)
    if (
        term_set & frozenset(("data", "datastore", "store", "table"))
        and "make_datastore_structure_evidence" not in existing_kinds
    ):
        gaps.append(_planned_structure_gap("make_datastore_structure_evidence"))
    if (
        term_set & frozenset(("hook", "webhook", "webhooks"))
        and "make_webhook_structure_evidence" not in existing_kinds
    ):
        gaps.append(_planned_structure_gap("make_webhook_structure_evidence"))
    if term_set & frozenset(
        ("connection", "scope", "import", "export", "onboarding")
    ):
        gaps.extend(
            _planned_structure_gap(table_name)
            for table_name in SCRAPED_INFRASTRUCTURE_TABLES
            if table_name not in existing_kinds
        )
    return gaps


def _planned_structure_gap(table_name: str) -> JsonObject:
    """Return one future evidence acquisition pointer."""
    return {
        "kind": "structure_evidence_not_yet_populated",
        "rank_reason": (
            "Query terms indicate a global catalog structure evidence "
            "surface with no "
            "populated row."
        ),
        "table": table_name,
        "evidence_scope": "global_catalog_structure_evidence ",
        "global_catalog_structure_evidence": "missing ",
        "project_local_structure_evidence": "not_evaluated_by_catalog_search ",
        "evidence_status": "missing",
        "blocking": False,
        "reason": (
            "SQLite SSOT table exists, but no matching reverse-engineered "
            "global catalog rows "
            "exist yet. This does not block project-local manifests."
        ),
        "blocking_reason": (
            "Global catalog structure evidence is missing; project-local "
            "structure evidence is "
            "evaluated by project package tools when a project_id is available."
        ),
        "project_local_manifest_lookup": {
            "tool": "project.package.inspect ",
            "section": "live_resources ",
            "status_when_manifest_declares_resource": "available",
        },
        "next_acquisition_path": (
            "windows_service_scraper -> sqlite_ingestion -> catalog.search"
        ),
    }


def _sqlite_table_exists(
    *, connection: sqlite3.Connection, table_name: str
) -> bool:
    """Return whether one optional local extension table exists."""
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _row_text(row: sqlite3.Row, key: str) -> str:
    """Return one SQLite row field as text, preserving null as empty text."""
    value = cast("object", row[key])
    return "" if value is None else str(value)


def _row_int(row: sqlite3.Row, key: str) -> int:
    """Return one SQLite row field as an integer.

    Raises:
        TypeError: If the SQLite value is not an integer-compatible value.
    """
    value = cast("object", row[key])
    if isinstance(value, bool):
        message = f"Catalog search column {key} must be an integer."
        raise TypeError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    message = f"Catalog search column {key} must be an integer."
    raise TypeError(message)


def _optional_row_text(row: sqlite3.Row, key: str) -> str | None:
    text = _row_text(row, key).strip()
    return text or None


def _optional_row_int(row: sqlite3.Row, key: str) -> int | None:
    value = cast("object", row[key])
    if value is None:
        return None
    if isinstance(value, bool):
        message = f"Catalog search column {key} must be an integer."
        raise TypeError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    message = f"Catalog search column {key} must be an integer or null."
    raise TypeError(message)


def _optional_row_float(row: sqlite3.Row, key: str) -> float | None:
    value = cast("object", row[key])
    if value is None:
        return None
    if isinstance(value, bool):
        message = f"Catalog search column {key} must be a number."
        raise TypeError(message)
    if isinstance(value, (int, float)):
        return float(value)
    message = f"Catalog search column {key} must be a number or null."
    raise TypeError(message)


def _optional_row_bool(row: sqlite3.Row, key: str) -> bool | None:
    value = cast("object", row[key])
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    message = f"Catalog search column {key} must be boolean-compatible or null."
    raise TypeError(message)


def _json_value_from_row(row: sqlite3.Row, key: str) -> object:
    value = _row_text(row, key)
    if not value:
        return None
    return cast("object", json.loads(value))


def _snippet(value: str) -> str:
    """Return a whitespace-normalized bounded snippet."""
    normalized = " ".join(value.split())
    if len(normalized) <= CATALOG_SEARCH_MAX_SNIPPET_CHARS:
        return normalized
    return f"{normalized[: CATALOG_SEARCH_MAX_SNIPPET_CHARS - 3].rstrip()}..."


def _int_mapping_value(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0
