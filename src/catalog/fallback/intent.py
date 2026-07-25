# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# - 001061#repo.delivery.assisted-stack-selection-auditable
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Deterministic catalog-backed intent planning.

Boundary contract:
- Owns: auditable semantic plans from requirement text and catalog retrieval.
- Must not: call AI providers, mutate catalogs, validate imports, or perform IO.
- Allows: exact token extraction, capability terms, and operator hint filtering.
- Split when: planning needs generated reasoning, credentials, or workflow
state.
- Merge when: another module builds the same catalog-backed intent plan.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

from catalog.fallback.query import (
    DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT,
    retrieve_catalog_modules,
)
from catalog.fallback.results import (
    catalog_candidate_source_sort_key,
    require_complete_catalog_retrieval,
)
from catalog.fallback.scoring import datastore_intent_active
from catalog.fallback.text import tokenize
from catalog.identifiers import module_version_sort_key

if TYPE_CHECKING:
    from collections.abc import Callable

    from catalog.fallback.results import CatalogModuleCandidate
    from catalog.models import CatalogSnapshot

EXACT_MODULE_TOKEN_PATTERN: Final = re.compile(
    r"(?<![A-Za-z0-9:_-])([A-Za-z0-9-]+:[A-Za-z0-9][A-Za-z0-9_-]*)(?![A-Za-"
    r"z0-9:_-])"
)
MIN_CAPABILITY_TERM_LENGTH: Final = 2
HIGH_CONFIDENCE_SCORE_FLOOR: Final = 20
MIN_ROUTE_SPLIT_MATCHES: Final = 2
TRIGGER_KINDS: Final[frozenset[str]] = frozenset(("trigger",))
ACTION_KINDS: Final[frozenset[str]] = frozenset(("action",))
DATASOURCE_LOOKUP_TERMS: Final[frozenset[str]] = frozenset(
    ("check", "exist", "exists", "find", "get", "lookup", "search")
)
ROUTE_SPLIT_GROUPS: Final[tuple[tuple[str, ...], ...]] = (
    ("qualified", "incomplete"),
    ("valid", "invalid"),
    ("accepted", "rejected"),
    ("success", "failure"),
)
WEBHOOK_RESPONSE_TERMS: Final[frozenset[str]] = frozenset(
    ("reply", "respond", "response")
)
WEBHOOK_TRIGGER_TERMS: Final[frozenset[str]] = frozenset(("custom", "webhook"))
ROUTER_TERMS: Final[frozenset[str]] = frozenset(
    (
        "branch",
        "condition",
        "conditional",
        "incomplete",
        "qualified",
        "route",
        "router",
    )
)
AGGREGATOR_TERMS: Final[frozenset[str]] = frozenset(
    ("aggregate", "aggregator", "array")
)
ITERATOR_TERMS: Final[frozenset[str]] = frozenset(
    ("each", "iterate", "iterator", "loop")
)
PARSER_TERMS: Final[frozenset[str]] = frozenset(
    ("csv", "json", "parse", "parser", "text", "transform", "xml")
)
PARSER_FORMAT_ORDER: Final[tuple[str, ...]] = ("text", "csv", "json", "xml")
TEXT_PARSER_REQUEST_TERMS: Final[frozenset[str]] = frozenset(
    ("parse", "parser", "text", "transform")
)
HTTP_TERMS: Final[frozenset[str]] = frozenset(
    ("api", "http", "request", "requests")
)
AI_AGENT_TERMS: Final[frozenset[str]] = frozenset(
    ("agent", "agents", "ai", "model", "models", "toolkit")
)
EMAIL_REQUEST_TERMS: Final[frozenset[str]] = frozenset(
    ("email", "emails", "gmail", "mail")
)
EMAIL_CANDIDATE_TERMS: Final[frozenset[str]] = frozenset(
    ("attachment", "email", "emails", "gmail", "imap", "mail", "smtp")
)
EMAIL_CORE_APP_SLUGS: Final[frozenset[str]] = frozenset(
    (
        "google-email",
        "microsoft-email",
    )
)
EMAIL_ADJACENT_APP_SLUGS: Final[frozenset[str]] = frozenset(
    (
        "gateway",
        "regexp",
        "text-parser",
    )
)
EMAIL_LOOKUP_ONLY_CONTEXT_TERMS: Final[frozenset[str]] = frozenset(
    ("address", "by")
)
GOOGLE_SHEETS_TERMS: Final[frozenset[str]] = frozenset(
    ("google-sheets", "sheet", "sheets", "spreadsheet", "spreadsheets")
)
GOOGLE_SHEETS_UPDATE_TERMS: Final[frozenset[str]] = frozenset(
    ("edit", "update", "upsert")
)
GOOGLE_SHEETS_ROW_TERMS: Final[frozenset[str]] = frozenset(("row", "rows"))
ROW_IDENTIFIER_TERMS: Final[frozenset[str]] = frozenset(
    ("id", "identifier", "number", "rowid", "rownumber")
)
ROW_IDENTIFIER_MISSING_TERMS: Final[frozenset[str]] = frozenset(
    ("missing", "not", "present", "unknown", "without")
)
MONEY_AMOUNT_TERMS: Final[frozenset[str]] = frozenset(
    (
        "amount",
        "balance",
        "charge",
        "invoice",
        "payment",
        "price",
        "stripe",
        "total",
    )
)
MINOR_UNIT_TERMS: Final[frozenset[str]] = frozenset(
    ("cent", "cents", "minor", "smallest", "subunit")
)
CUSTOMER_VISIBLE_TEXT_TERMS: Final[frozenset[str]] = frozenset(
    (
        "currency",
        "email",
        "message",
        "receipt",
        "sheet",
        "sheets",
        "slack",
        "text",
    )
)
ATTACHMENT_TERMS: Final[frozenset[str]] = frozenset(
    ("attachment", "attachments")
)
SINGLE_FILE_TERMS: Final[frozenset[str]] = frozenset(
    ("file", "single", "upload")
)
SEARCH_RESULT_UNIQUENESS_TERMS: Final[frozenset[str]] = frozenset(
    ("filter", "lookup", "search", "unique")
)
REQUESTED_COMPANION_ACTION_ORDER: Final[dict[str, int]] = {
    "slack": 0,
    "email": 1,
}
FILTER_TERMS: Final[frozenset[str]] = frozenset(("filter", "filters"))
ERROR_HANDLER_TERMS: Final[frozenset[str]] = frozenset(
    ("error", "errors", "failure", "handler", "handling", "rollback")
)
SETUP_FREE_APP_SLUGS: Final[frozenset[str]] = frozenset(
    (
        "builtin",
        "csv",
        "datastore",
        "gateway",
        "json",
        "tools",
        "webhooks",
        "xml",
    )
)


class ModulePlannerHints(NamedTuple):
    """Operator-supplied planning constraints."""

    required_terms: tuple[str, ...] = ()
    prohibited_terms: tuple[str, ...] = ()
    source_label: str | None = None


class PlannerStep(NamedTuple):
    """One selected catalog-backed module step in an advisory semantic plan."""

    category: str
    module_id: str
    module_kind: str
    status: str


class PlannerGapRecord(NamedTuple):
    """One explicit planner advisory gap that remains outside catalog truth."""

    gap_id: str
    category: str
    status: str
    message: str


class SemanticExpansionRecord(NamedTuple):
    """One compact natural-language expansion applied by the semantic.

    planner.
    """

    intent: str
    aliases: tuple[str, ...]
    module_families: tuple[str, ...]
    evidence_status: str
    message: str


class WiringPlanRecord(NamedTuple):
    """One Make grammar wiring note derived from selected catalog families."""

    wiring_id: str
    category: str
    status: str
    module_ids: tuple[str, ...]
    message: str
    evidence_status: str


class RepairValidationRecord(NamedTuple):
    """One repair or validation warning surfaced by catalog.plan."""

    repair_id: str
    severity: str
    promotion_state: str
    message: str


class RequestedGapSpec(NamedTuple):
    """One requested semantic gap descriptor."""

    gap_id: str
    category: str
    message: str


class SemanticRequirementPlan(NamedTuple):
    """Auditable catalog-backed plan for one requirements text."""

    catalog_fingerprint: str
    source_text: str
    goal_text: str
    explicit_module_tokens: tuple[str, ...]
    capability_terms: tuple[str, ...]
    candidate_modules: tuple[CatalogModuleCandidate, ...]
    module_sequence: tuple[str, ...]
    unresolved_ambiguities: tuple[str, ...]
    planning_gaps: tuple[str, ...]
    planner_steps: tuple[PlannerStep, ...]
    planner_gap_records: tuple[PlannerGapRecord, ...]
    semantic_expansion: tuple[SemanticExpansionRecord, ...]
    wiring_plan: tuple[WiringPlanRecord, ...]
    repair_validation: tuple[RepairValidationRecord, ...]


def build_semantic_requirement_plan(
    *,
    snapshot: CatalogSnapshot,
    requirements_text: str,
    goal_text: str = "",
    hints: ModulePlannerHints | None = None,
    limit: int = DEFAULT_CATALOG_FALLBACK_QUERY_LIMIT,
) -> SemanticRequirementPlan:
    """Return the computed result for the caller."""
    effective_hints = hints or ModulePlannerHints()
    combined_text = " ".join(
        item for item in (goal_text, requirements_text) if item.strip()
    )
    explicit_tokens = _explicit_module_tokens(combined_text)
    capability_terms = _capability_terms(combined_text)
    query_terms = frozenset(capability_terms)
    retrieval = retrieve_catalog_modules(
        snapshot=snapshot,
        query_text=_query_text(combined_text, effective_hints),
        limit=limit,
        source_label=effective_hints.source_label,
    )
    require_complete_catalog_retrieval(retrieval)
    candidates = tuple(
        candidate
        for candidate in retrieval.candidates
        if not _candidate_blocked(candidate, effective_hints.prohibited_terms)
    )
    candidates = _prune_low_confidence_candidates(candidates)
    (
        module_sequence,
        planning_gaps,
        planner_steps,
        planner_gap_records,
        wiring_plan,
        repair_validation,
    ) = _module_sequence(
        candidates=candidates,
        explicit_tokens=explicit_tokens,
        query_terms=query_terms,
    )
    return SemanticRequirementPlan(
        catalog_fingerprint=snapshot.fingerprint,
        source_text=requirements_text,
        goal_text=goal_text,
        explicit_module_tokens=explicit_tokens,
        capability_terms=capability_terms,
        candidate_modules=candidates,
        module_sequence=module_sequence,
        unresolved_ambiguities=_ambiguities(explicit_tokens, candidates),
        planning_gaps=planning_gaps,
        planner_steps=planner_steps,
        planner_gap_records=planner_gap_records,
        semantic_expansion=_semantic_expansion_records(
            query_terms=query_terms,
            candidates=candidates,
        ),
        wiring_plan=wiring_plan,
        repair_validation=repair_validation,
    )


def _query_text(text: str, hints: ModulePlannerHints) -> str:
    """Return retrieval text enriched with required operator terms."""
    return " ".join((*hints.required_terms, text))


def _explicit_module_tokens(text: str) -> tuple[str, ...]:
    """Return exact app:module token mentions in source order."""
    tokens: list[str] = []
    for match in EXACT_MODULE_TOKEN_PATTERN.finditer(text):
        token = match.group(1)
        if token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def _capability_terms(text: str) -> tuple[str, ...]:
    """Return normalized capability terms for auditing planner behavior."""
    return tuple(
        sorted(
            {
                token
                for token in tokenize(text)
                if len(token) > MIN_CAPABILITY_TERM_LENGTH
            }
        )
    )


def _candidate_blocked(
    candidate: CatalogModuleCandidate,
    prohibited_terms: tuple[str, ...],
) -> bool:
    """Return whether a candidate matches an operator-prohibited term."""
    haystack = (
        f"{candidate.module_id} {candidate.app_slug} {candidate.internal_name} "
        f"{candidate.display_name} {candidate.module_kind}"
    ).casefold()
    return any(term.casefold() in haystack for term in prohibited_terms)


def _ambiguities(
    explicit_tokens: tuple[str, ...],
    candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[str, ...]:
    """Return exact tokens not represented by catalog candidates."""
    candidate_text = " ".join(
        candidate.module_id for candidate in candidates
    ).casefold()
    return tuple(
        token
        for token in explicit_tokens
        if token.casefold().replace(":", "-") not in candidate_text
    )


def _prune_low_confidence_candidates(
    candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[CatalogModuleCandidate, ...]:
    """Drop generic low-score filler once a high-confidence intent match exists.

    Returns:
        The filtered candidate tuple.
    """
    if not candidates:
        return ()
    has_high_confidence = any(
        any(
            reason.startswith(("intent:", "webhook:generic-receiver"))
            for reason in candidate.match_reasons
        )
        for candidate in candidates
    )
    if not has_high_confidence:
        return candidates
    return tuple(
        candidate
        for candidate in candidates
        if candidate.score >= HIGH_CONFIDENCE_SCORE_FLOOR
        or _candidate_has_native_planner_role(candidate)
    )


def _candidate_has_native_planner_role(
    candidate: CatalogModuleCandidate,
) -> bool:
    """Return whether a candidate owns a native semantic planner slot."""
    return candidate.module_kind.casefold() in {
        "aggregator",
        "router",
        "transformer",
    } or candidate.app_slug.casefold() in {"agent-ai", "ai-agent", "http"}


def _module_sequence(
    *,
    candidates: tuple[CatalogModuleCandidate, ...],
    explicit_tokens: tuple[str, ...],
    query_terms: frozenset[str],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[PlannerStep, ...],
    tuple[PlannerGapRecord, ...],
    tuple[WiringPlanRecord, ...],
    tuple[RepairValidationRecord, ...],
]:
    """Return a coherent scenario-oriented module sequence and planning gaps.

    Returns:
    The planned module sequence, explicit planning gaps, steps, and gap records.
    """
    del explicit_tokens
    if not candidates:
        gap = PlannerGapRecord(
            gap_id="catalog_sequence_missing",
            category="catalog",
            status="catalog_module_not_selected",
            message="No catalog-backed module sequence could be inferred.",
        )
        return ((), (gap.message,), (), (gap,), (), ())
    selected_candidates = _dedupe_module_families(candidates)
    planning_gaps: list[str] = []
    sequence_candidates: list[CatalogModuleCandidate] = []
    trigger = _select_trigger(selected_candidates, query_terms=query_terms)
    _append_candidate(sequence_candidates, trigger)
    for parser in _select_parser_transformers(
        selected_candidates, query_terms=query_terms
    ):
        _append_candidate(sequence_candidates, parser)
    for selector in (
        _select_http_module,
        _select_ai_agent_module,
        _select_aggregator,
        _select_iterator,
        _select_router,
    ):
        _append_candidate(
            sequence_candidates,
            selector(selected_candidates, query_terms=query_terms),
        )
    for chain_candidate in _select_google_sheets_row_chain(
        selected_candidates,
        query_terms=query_terms,
    ):
        _append_candidate(sequence_candidates, chain_candidate)
    actions = _select_actions(
        selected_candidates,
        query_terms=query_terms,
        selected_module_ids=frozenset(
            candidate.module_id for candidate in sequence_candidates
        ),
    )
    sequence_candidates.extend(actions)
    sequence = tuple(candidate.module_id for candidate in sequence_candidates)
    if WEBHOOK_RESPONSE_TERMS.intersection(query_terms) and not any(
        _is_webhook_response(candidate) for candidate in sequence_candidates
    ):
        webhook_response_gap = (
            "Webhook response is conditional; confirm whether to include "
        )
        webhook_response_gap += "a catalog-backed response module."
        planning_gaps.append(webhook_response_gap)
    if not any(
        candidate.module_kind.casefold() == "action"
        for candidate in sequence_candidates
    ):
        planning_gaps.append(
            "Planner could not infer a concrete action sequence from the "
            "request."
        )
    gap_records = _planner_gap_records(
        query_terms=query_terms,
        selected_candidates=selected_candidates,
        sequence_candidates=tuple(sequence_candidates),
    )
    for record in gap_records:
        if (
            record.status == "catalog_module_not_selected"
            and record.message not in planning_gaps
        ):
            planning_gaps.append(record.message)
    wiring_plan = _wiring_plan_records(
        query_terms=query_terms,
        selected_candidates=selected_candidates,
        sequence_candidates=tuple(sequence_candidates),
    )
    return (
        sequence,
        tuple(planning_gaps),
        _planner_steps(tuple(sequence_candidates)),
        gap_records,
        wiring_plan,
        _repair_validation_records(
            query_terms=query_terms, wiring_plan=wiring_plan
        ),
    )


def _append_candidate(
    sequence_candidates: list[CatalogModuleCandidate],
    candidate: CatalogModuleCandidate | None,
) -> None:
    """Append one candidate when it is present and not already selected."""
    if candidate is None:
        return
    if any(
        item.module_id == candidate.module_id for item in sequence_candidates
    ):
        return
    sequence_candidates.append(candidate)


def _planner_steps(
    sequence_candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[PlannerStep, ...]:
    """Return JSON-ready planner step records for selected module candidates."""
    return tuple(
        PlannerStep(
            category=_candidate_step_category(candidate),
            module_id=candidate.module_id,
            module_kind=candidate.module_kind,
            status="catalog_module_selected",
        )
        for candidate in sequence_candidates
    )


def _candidate_step_category(candidate: CatalogModuleCandidate) -> str:
    """Return the semantic category represented by one selected candidate."""
    category = "action"
    if candidate.module_kind.casefold() == "trigger":
        category = "trigger"
    elif _is_router(candidate):
        category = "router"
    elif _is_aggregator(candidate):
        category = "aggregator"
    elif _is_iterator(candidate):
        category = "iterator"
    elif _is_parser_transformer(candidate):
        category = "parser_transformer"
    elif _is_http_module(candidate):
        category = "http"
    elif _is_ai_agent_module(candidate):
        category = "ai_agent"
    elif _is_google_sheets_row_search(candidate):
        category = "lookup"
    elif candidate.app_slug.casefold() == "datastore":
        category = "datastore"
    return category


def _dedupe_module_families(
    candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[CatalogModuleCandidate, ...]:
    """Return candidates without older duplicate module families.

    Returns:
        The family-deduplicated candidate tuple.
    """
    selected_by_family: dict[tuple[str, str, str], CatalogModuleCandidate] = {}
    ordered: list[CatalogModuleCandidate] = []
    for candidate in candidates:
        family_key = _candidate_family_key(candidate)
        existing = selected_by_family.get(family_key)
        if existing is not None:
            preferred = _preferred_family_candidate(
                existing=existing, candidate=candidate
            )
            if preferred is existing:
                continue
            selected_by_family[family_key] = preferred
            ordered[ordered.index(existing)] = preferred
            continue
        selected_by_family[family_key] = candidate
        ordered.append(candidate)
    return tuple(ordered)


def _preferred_family_candidate(
    *,
    existing: CatalogModuleCandidate,
    candidate: CatalogModuleCandidate,
) -> CatalogModuleCandidate:
    """Return the preferred same-family candidate by source rank and stable.

    identity.
    """
    return min(
        (existing, candidate),
        key=lambda item: (
            item.source_rank,
            -item.score,
            item.deprecated,
            _candidate_version_sort_key(item),
            catalog_candidate_source_sort_key(item),
        ),
    )


def _candidate_version_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, ...]:
    """Return a descending-friendly version key for source-tied candidates."""
    return module_version_sort_key(candidate.app_version)


def _candidate_family_key(
    candidate: CatalogModuleCandidate,
) -> tuple[str, str, str]:
    """Return a stable family key for planner-level deduplication."""
    return (
        candidate.app_slug.casefold(),
        candidate.module_kind.casefold(),
        _module_name_key(candidate.internal_name),
    )


def _module_name_key(value: str) -> str:
    """Return a separator-insensitive module name key."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _select_trigger(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return the best trigger candidate for the planned sequence."""
    trigger_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.module_kind.casefold() in TRIGGER_KINDS
        and not _unrelated_to_first_party_intent(
            candidate, query_terms=query_terms
        )
    )
    if not trigger_candidates:
        return None
    webhook_candidates = tuple(
        candidate
        for candidate in trigger_candidates
        if _is_custom_webhook_trigger(candidate)
    )
    if WEBHOOK_TRIGGER_TERMS.issubset(query_terms) and webhook_candidates:
        return webhook_candidates[0]
    return trigger_candidates[0]


def _select_router(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return a router candidate when branching semantics are requested."""
    if not ROUTER_TERMS.intersection(query_terms):
        return None
    routers = tuple(
        candidate for candidate in candidates if _is_router(candidate)
    )
    if not routers:
        return None
    return min(routers, key=_router_sort_key)


def _select_aggregator(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return an aggregator candidate when aggregation is requested."""
    if not AGGREGATOR_TERMS.intersection(query_terms):
        return None
    return _first_matching_candidate(candidates, predicate=_is_aggregator)


def _select_iterator(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return an iterator candidate when iteration is requested."""
    if not ITERATOR_TERMS.intersection(query_terms):
        return None
    return _first_matching_candidate(candidates, predicate=_is_iterator)


def _select_parser_transformers(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> tuple[CatalogModuleCandidate, ...]:
    """Return parser or transformer candidates for each requested payload.

    format.
    """
    if not PARSER_TERMS.intersection(query_terms):
        return ()
    parser_candidates = tuple(
        candidate
        for candidate in candidates
        if _is_parser_transformer(candidate)
    )
    if not parser_candidates:
        return ()
    selected: list[CatalogModuleCandidate] = []
    for parser_format in PARSER_FORMAT_ORDER:
        if not _parser_format_requested(
            parser_format=parser_format, query_terms=query_terms
        ):
            continue
        _append_candidate(
            selected,
            _first_matching_candidate(
                parser_candidates,
                predicate=lambda candidate, format_name=parser_format: (
                    _parser_candidate_matches_format(
                        candidate, parser_format=format_name
                    )
                ),
            ),
        )
    if selected:
        return tuple(selected)
    return (parser_candidates[0],)


def _parser_format_requested(
    *,
    parser_format: str,
    query_terms: frozenset[str],
) -> bool:
    """Return whether a concrete parser format was requested."""
    if parser_format == "text":
        return bool(TEXT_PARSER_REQUEST_TERMS.intersection(query_terms))
    return parser_format in query_terms


def _parser_candidate_matches_format(
    candidate: CatalogModuleCandidate,
    *,
    parser_format: str,
) -> bool:
    """Return if a parser candidate handles one requested payload format."""
    text = _candidate_text(candidate)
    tokens = set(tokenize(text))
    module_key = _module_name_key(candidate.internal_name)
    if parser_format == "text":
        if candidate.app_slug.casefold() in {"regexp", "text-parser"}:
            return True
        return "text" in tokens and not {"csv", "json", "xml"}.intersection(
            tokens
        )
    return parser_format in tokens or parser_format in module_key


def _select_http_module(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return an HTTP candidate when API request semantics are requested."""
    if not HTTP_TERMS.intersection(query_terms):
        return None
    return _first_matching_candidate(candidates, predicate=_is_http_module)


def _select_ai_agent_module(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> CatalogModuleCandidate | None:
    """Return an AI-agent candidate when agent semantics are requested."""
    if not AI_AGENT_TERMS.intersection(query_terms):
        return None
    return _first_matching_candidate(candidates, predicate=_is_ai_agent_module)


def _select_google_sheets_row_chain(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
) -> tuple[CatalogModuleCandidate, ...]:
    """Return row lookup then update modules when a Sheets update lacks row.

    identity.
    """
    if not _google_sheets_lookup_before_update_active(query_terms):
        return ()
    selected: list[CatalogModuleCandidate] = []
    _append_candidate(
        selected,
        _preferred_google_sheets_row_search(candidates),
    )
    _append_candidate(
        selected,
        _preferred_google_sheets_row_update(candidates),
    )
    return tuple(selected)


def _preferred_google_sheets_row_search(
    candidates: tuple[CatalogModuleCandidate, ...],
) -> CatalogModuleCandidate | None:
    """Return the best Google Sheets row lookup candidate."""
    matches = tuple(
        candidate
        for candidate in candidates
        if _is_google_sheets_row_search(candidate)
    )
    if not matches:
        return None
    return min(matches, key=_google_sheets_row_search_sort_key)


def _preferred_google_sheets_row_update(
    candidates: tuple[CatalogModuleCandidate, ...],
) -> CatalogModuleCandidate | None:
    """Return the best single-row Google Sheets update candidate."""
    matches = tuple(
        candidate
        for candidate in candidates
        if _is_google_sheets_row_update(candidate)
    )
    if not matches:
        return None
    return min(matches, key=_google_sheets_row_update_sort_key)


def _google_sheets_row_search_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, bool, tuple[int, ...], int, str]:
    """Return deterministic preference for row lookup modules."""
    module_key = _module_name_key(candidate.internal_name)
    return (
        0
        if module_key in {"filterrows", "filterrowsadvanced", "actiongetreport"}
        else 1,
        "advanced" not in module_key,
        _candidate_version_sort_key(candidate),
        -candidate.score,
        candidate.module_id,
    )


def _google_sheets_row_update_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, tuple[int, ...], int, str]:
    """Return deterministic preference for single-row update modules."""
    module_key = _module_name_key(candidate.internal_name)
    single_row_rank = 0 if module_key in {"updaterow", "actionupdaterow"} else 1
    return (
        single_row_rank,
        _candidate_version_sort_key(candidate),
        -candidate.score,
        candidate.module_id,
    )


def _select_actions(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
    selected_module_ids: frozenset[str],
) -> tuple[CatalogModuleCandidate, ...]:
    """Return ordered action modules for the planned sequence."""
    if _google_sheets_lookup_before_update_active(query_terms):
        return ()
    branch_count = _branch_count(query_terms)
    datastore_actions = tuple(
        candidate
        for candidate in candidates
        if _is_datastore_add_record(candidate)
        and candidate.module_id not in selected_module_ids
    )
    action_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.module_id not in selected_module_ids
        and candidate.module_kind.casefold() in ACTION_KINDS
        and not _is_structural_action(candidate)
        and not _is_webhook_response(candidate)
        and not _is_unrequested_datastore_lookup(
            candidate, query_terms=query_terms
        )
    )
    if datastore_intent_active(query_terms) and datastore_actions:
        selected_actions = [datastore_actions[0] for _ in range(branch_count)]
        selected_actions.extend(
            _select_requested_companion_actions(
                action_candidates,
                query_terms=query_terms,
                selected_module_ids=frozenset(
                    candidate.module_id for candidate in selected_actions
                ),
            )
        )
        return tuple(selected_actions)
    return tuple(
        candidate
        for candidate in action_candidates
        if not _unrelated_to_first_party_intent(
            candidate, query_terms=query_terms
        )
    )


def _select_requested_companion_actions(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    query_terms: frozenset[str],
    selected_module_ids: frozenset[str],
) -> tuple[CatalogModuleCandidate, ...]:
    """Return explicit provider actions that should accompany a Data Store.

    workflow.
    """
    candidates_by_category: dict[str, list[CatalogModuleCandidate]] = {}
    for candidate in candidates:
        if (
            candidate.module_id in selected_module_ids
            or _is_datastore_add_record(candidate)
        ):
            continue
        category = _requested_companion_action_category(
            candidate, query_terms=query_terms
        )
        if category is None:
            continue
        candidates_by_category.setdefault(category, []).append(candidate)
    return tuple(
        min(candidates_by_category[category], key=_companion_action_sort_key)
        for category in sorted(
            candidates_by_category,
            key=lambda item: REQUESTED_COMPANION_ACTION_ORDER[item],
        )
    )


def _requested_companion_action_category(
    candidate: CatalogModuleCandidate,
    *,
    query_terms: frozenset[str],
) -> str | None:
    """Return the explicit companion action category requested for a provider.

    module.
    """
    text_terms = set(tokenize(_candidate_text(candidate)))
    if "slack" in query_terms and candidate.app_slug.casefold() == "slack":
        return "slack"
    if EMAIL_REQUEST_TERMS.intersection(
        query_terms
    ) and EMAIL_CANDIDATE_TERMS.intersection(text_terms):
        return "email"
    return None


def _semantic_expansion_records(
    *,
    query_terms: frozenset[str],
    candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[SemanticExpansionRecord, ...]:
    """Return compact semantic expansions that explain non-literal module.

    discovery.
    """
    records: list[SemanticExpansionRecord] = []
    if _email_intent_active(query_terms):
        records.append(
            SemanticExpansionRecord(
                intent="email",
                aliases=(
                    "email",
                    "mail",
                    "gmail",
                    "google email",
                    "microsoft email",
                    "outlook",
                    "smtp",
                    "imap",
                    "mailhook",
                    "attachments",
                    "parser",
                    "router",
                    "notification",
                ),
                module_families=_selected_module_families(
                    candidates,
                    allowed_slugs=EMAIL_CORE_APP_SLUGS
                    | EMAIL_ADJACENT_APP_SLUGS,
                ),
                evidence_status="local_catalog_knowledge",
                message=(
                    "Expanded email intent across first-party mail "
                    "providers, inbound "
                    "mailhooks, SMTP/IMAP, attachment handling, parsing, "
                    "routing, and "
                    "notification-adjacent modules."
                ),
            )
        )
    if _google_sheets_lookup_before_update_active(query_terms):
        records.append(
            SemanticExpansionRecord(
                intent="google_sheets_update",
                aliases=(
                    "google sheets",
                    "spreadsheet row",
                    "search rows",
                    "lookup row",
                    "update row",
                    "row id",
                    "row number",
                    "unique result",
                ),
                module_families=_selected_module_families(
                    candidates,
                    allowed_slugs=frozenset(("google-sheets",)),
                ),
                evidence_status="local_catalog_knowledge",
                message=(
                    "Expanded a row update without a known row identifier "
                    "into a "
                    "search/list rows precondition, uniqueness guard, and "
                    "update row action."
                ),
            )
        )
    return tuple(records)


def _selected_module_families(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    allowed_slugs: frozenset[str],
) -> tuple[str, ...]:
    """Return selected app families in candidate order."""
    families: list[str] = []
    for candidate in candidates:
        slug = candidate.app_slug.casefold()
        if slug not in allowed_slugs or slug in families:
            continue
        families.append(slug)
    return tuple(families)


def _wiring_plan_records(
    *,
    query_terms: frozenset[str],
    selected_candidates: tuple[CatalogModuleCandidate, ...],
    sequence_candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[WiringPlanRecord, ...]:
    """Return the computed result for the caller."""
    records: list[WiringPlanRecord] = []
    sequence_module_ids = tuple(
        candidate.module_id for candidate in sequence_candidates
    )
    if _money_minor_units_to_text_active(query_terms):
        records.append(
            WiringPlanRecord(
                wiring_id="contract.money.minor_units_to_currency_text",
                category="unit_transform",
                status="transform_required",
                module_ids=sequence_module_ids,
                message=(
                    "Normalize Stripe-style minor currency units before "
                    "customer-visible "
                    "text: divide cents by 100 for common two-decimal "
                    "currencies, then "
                    "format with the currency code. Keep currency precision "
                    "provider-aware."
                ),
                evidence_status="quarantined_repair_candidate",
            )
        )
    if _attachment_iterator_bridge_active(query_terms):
        iterator = _first_matching_candidate(
            selected_candidates, predicate=_is_iterator
        )
        records.append(
            WiringPlanRecord(
                wiring_id="bridge.email_attachments_array_to_single_file",
                category="array_bridge",
                status=(
                    "bridge_module_selected"
                    if iterator in sequence_candidates
                    else "bridge_required"
                ),
                module_ids=(() if iterator is None else (iterator.module_id,)),
                message=(
                    "Email attachments are array-shaped. Insert an Iterator "
                    "before any "
                    "single-file upload/create module, then map each "
                    "attachment item into "
                    "the file field."
                ),
                evidence_status="local_catalog_knowledge",
            )
        )
    if _google_sheets_lookup_before_update_active(query_terms):
        chain_module_ids = tuple(
            candidate.module_id
            for candidate in sequence_candidates
            if _is_google_sheets_row_search(candidate)
            or _is_google_sheets_row_update(candidate)
        )
        records.append(
            WiringPlanRecord(
                wiring_id="chain.google_sheets.lookup_before_update",
                category="search_before_update",
                status="precondition_required",
                module_ids=chain_module_ids,
                message=(
                    "Do not wire a bare Google Sheets Update Row action "
                    "when row id or "
                    "row number is missing. Search rows by the stable "
                    "business key, guard "
                    "that exactly one row matched, then map the resolved "
                    "row identifier "
                    "into Update Row."
                ),
                evidence_status="local_catalog_knowledge",
            )
        )
    if _runtime_setup_required(sequence_candidates):
        records.append(
            WiringPlanRecord(
                wiring_id="setup.provider_runtime_prerequisites",
                category="runtime_setup",
                status="runtime_setup_required",
                module_ids=sequence_module_ids,
                message=(
                    "Provider modules remain local catalog selections until "
                    "the client "
                    "connects accounts, selects linked resources, and "
                    "resolves dynamic "
                    "options inside Make."
                ),
                evidence_status="local_catalog_knowledge",
            )
        )
    return tuple(records)


def _repair_validation_records(
    *,
    query_terms: frozenset[str],
    wiring_plan: tuple[WiringPlanRecord, ...],
) -> tuple[RepairValidationRecord, ...]:
    """Return repair warnings while keeping unpromoted rules explicitly.

    quarantined.
    """
    records: list[RepairValidationRecord] = []
    wiring_categories = {record.category for record in wiring_plan}
    if "unit_transform" in wiring_categories:
        records.append(
            RepairValidationRecord(
                repair_id="repair.money.normalize_minor_units_before_text",
                severity="warning",
                promotion_state="candidate_quarantined",
                message=(
                    "Warn when minor currency units flow into "
                    "customer-visible text "
                    "without an explicit normalization transform."
                ),
            )
        )
    if "array_bridge" in wiring_categories:
        records.append(
            RepairValidationRecord(
                repair_id="repair.cardinality.insert_iterator_for_attachment_array",
                severity="warning",
                promotion_state="candidate_quarantined",
                message=(
                    "Recommend an Iterator when an attachment array feeds a "
                    "single-file "
                    "consumer. This remains advisory until "
                    "field-cardinality rules are promoted."
                ),
            )
        )
    if "search_before_update" in wiring_categories:
        records.append(
            RepairValidationRecord(
                repair_id="repair.chain.insert_row_lookup_before_sheet_update",
                severity="warning",
                promotion_state="candidate_quarantined",
                message=(
                    "Require row lookup and unique-result handling before "
                    "Update Row when "
                    "the row id or row number is unavailable."
                ),
            )
        )
    if (
        _email_intent_active(query_terms)
        and "runtime_setup" in wiring_categories
    ):
        records.append(
            RepairValidationRecord(
                repair_id="repair.setup.surface_runtime_prerequisite",
                severity="warning",
                promotion_state="promoted_advisory",
                message=(
                    "Surface connection and dynamic setup prerequisites in the"
                    "planner output."
                ),
            )
        )
    return tuple(records)


def _companion_action_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, int, bool, tuple[int, ...], str]:
    """Return a deterministic preference key for requested companion actions."""
    return (
        candidate.source_rank,
        -candidate.score,
        candidate.deprecated,
        _candidate_version_sort_key(candidate),
        candidate.module_id,
    )


def _first_matching_candidate(
    candidates: tuple[CatalogModuleCandidate, ...],
    *,
    predicate: Callable[[CatalogModuleCandidate], bool],
) -> CatalogModuleCandidate | None:
    """Return the first candidate accepted by a local predicate."""
    return next(
        (candidate for candidate in candidates if predicate(candidate)), None
    )


def _is_structural_action(candidate: CatalogModuleCandidate) -> bool:
    """Return whether an action already has an earlier semantic planner slot."""
    return (
        _is_parser_transformer(candidate)
        or _is_http_module(candidate)
        or _is_ai_agent_module(candidate)
    )


def _planner_gap_records(
    *,
    query_terms: frozenset[str],
    selected_candidates: tuple[CatalogModuleCandidate, ...],
    sequence_candidates: tuple[CatalogModuleCandidate, ...],
) -> tuple[PlannerGapRecord, ...]:
    """Return explicit advisory gaps for semantics catalog planning cannot.

    finish.
    """
    records: list[PlannerGapRecord] = []
    _append_missing_domain_gap(
        records,
        requested=ROUTER_TERMS.intersection(query_terms),
        covered=any(_is_router(candidate) for candidate in sequence_candidates),
        spec=RequestedGapSpec(
            gap_id="router_module_not_selected",
            category="router",
            message=(
                "Branching was requested, but no catalog-backed router module"
                "was selected."
            ),
        ),
    )
    _append_missing_domain_gap(
        records,
        requested=PARSER_TERMS.intersection(query_terms),
        covered=any(
            _is_parser_transformer(candidate)
            for candidate in sequence_candidates
        ),
        spec=RequestedGapSpec(
            gap_id="parser_transformer_not_selected",
            category="parser_transformer",
            message=(
                "Parsing or transformation was requested, but no parser module"
                "was selected."
            ),
        ),
    )
    _append_missing_domain_gap(
        records,
        requested=HTTP_TERMS.intersection(query_terms),
        covered=any(
            _is_http_module(candidate) for candidate in sequence_candidates
        ),
        spec=RequestedGapSpec(
            gap_id="http_module_not_selected",
            category="http",
            message=(
                "HTTP/API work was requested, but no catalog-backed HTTP module"
                "was selected."
            ),
        ),
    )
    _append_missing_domain_gap(
        records,
        requested=AI_AGENT_TERMS.intersection(query_terms),
        covered=any(
            _is_ai_agent_module(candidate) for candidate in sequence_candidates
        ),
        spec=RequestedGapSpec(
            gap_id="ai_agent_module_not_selected",
            category="ai_agent",
            message=(
                "AI-agent work was requested, but no catalog-backed "
                "AI-agent module was selected."
            ),
        ),
    )
    _append_structure_gap_records(records=records, query_terms=query_terms)
    _append_setup_gap_records(
        records=records, selected_candidates=selected_candidates
    )
    return tuple(records)


def _append_missing_domain_gap(
    records: list[PlannerGapRecord],
    *,
    requested: object,
    covered: bool,
    spec: RequestedGapSpec,
) -> None:
    """Append a missing catalog-module gap when a requested domain is.

    uncovered.
    """
    if not requested or covered:
        return
    records.append(
        PlannerGapRecord(
            gap_id=spec.gap_id,
            category=spec.category,
            status="catalog_module_not_selected",
            message=spec.message,
        )
    )


def _append_structure_gap_records(
    *,
    records: list[PlannerGapRecord],
    query_terms: frozenset[str],
) -> None:
    """Append explicit gaps for non-module Make structures."""
    if FILTER_TERMS.intersection(query_terms):
        records.append(
            PlannerGapRecord(
                gap_id="filters_are_route_conditions",
                category="filter",
                status="ast_structure_required",
                message=(
                    "Filters are route-level AST conditions, not standalone "
                    "catalog modules."
                ),
            )
        )
    if ERROR_HANDLER_TERMS.intersection(query_terms):
        records.append(
            PlannerGapRecord(
                gap_id="error_handlers_are_route_structures",
                category="error_handler",
                status="ast_structure_required",
                message=(
                    "Error handlers require AST route semantics after "
                    "module selection."
                ),
            )
        )
    if WEBHOOK_RESPONSE_TERMS.intersection(query_terms):
        records.append(
            PlannerGapRecord(
                gap_id="webhook_response_conditional",
                category="conditional_module",
                status="requires_catalog_confirmation",
                message=(
                    "Webhook response remains conditional until a "
                    "catalog-backed response "
                    "module is selected."
                ),
            )
        )
    if {"dynamic", "selector", "select", "option"}.intersection(query_terms):
        records.append(
            PlannerGapRecord(
                gap_id="dynamic_selector_options",
                category="dynamic_selector",
                status="requires_import_readiness_validation",
                message=(
                    "Dynamic selector options require import-readiness"
                    "validation."
                ),
            )
        )


def _append_setup_gap_records(
    *,
    records: list[PlannerGapRecord],
    selected_candidates: tuple[CatalogModuleCandidate, ...],
) -> None:
    """Append setup advisory gaps implied by selected provider modules."""
    if not selected_candidates:
        return
    if any(
        candidate.module_kind.casefold() == "search"
        for candidate in selected_candidates
    ):
        records.append(
            PlannerGapRecord(
                gap_id="lookup_only_module",
                category="lookup_only_module",
                status="advisory_only",
                message=(
                    "Lookup/search modules may need action modules before"
                    "blueprint compile."
                ),
            )
        )
    has_provider_setup = any(
        candidate.app_slug.casefold() not in SETUP_FREE_APP_SLUGS
        for candidate in selected_candidates
    )
    if has_provider_setup:
        records.extend(
            (
                PlannerGapRecord(
                    gap_id="provider_credentials_required",
                    category="provider_credentials",
                    status="runtime_setup_required",
                    message=(
                        "Provider modules may require client-owned connections"
                        "or credentials."
                    ),
                ),
                PlannerGapRecord(
                    gap_id="manual_module_setup_required",
                    category="manual_setup",
                    status="runtime_setup_required",
                    message=(
                        "Catalog planning is advisory; manual setup remains "
                        "import-readiness work."
                    ),
                ),
            )
        )


def _router_sort_key(
    candidate: CatalogModuleCandidate,
) -> tuple[int, tuple[int, ...], str]:
    """Return a stable preference key for router candidates."""
    return (
        0 if _module_name_key(candidate.internal_name) == "basicrouter" else 1,
        _candidate_version_sort_key(candidate),
        candidate.module_id,
    )


def _is_router(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate is a Make router module."""
    return (
        candidate.module_kind.casefold() == "router"
        or "router" in _candidate_text(candidate)
    )


def _is_aggregator(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate is an aggregator module."""
    text = _candidate_text(candidate)
    return (
        candidate.module_kind.casefold() == "aggregator" or "aggregator" in text
    )


def _is_iterator(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate is an iterator module."""
    text = _candidate_text(candidate)
    return (
        "iterator" in text
        or _module_name_key(candidate.internal_name) == "basicfeeder"
    )


def _is_parser_transformer(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate parses or transforms payload content."""
    text = _candidate_text(candidate)
    return candidate.module_kind.casefold() == "transformer" and bool(
        {"csv", "json", "parse", "parser", "text", "xml"}.intersection(
            tokenize(text)
        )
    )


def _is_http_module(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate represents HTTP/API request work."""
    text = _candidate_text(candidate)
    return candidate.app_slug.casefold() == "http" or "http" in text


def _is_ai_agent_module(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate represents AI-agent work."""
    text = _candidate_text(candidate)
    return "agent" in text and ("ai" in text or "model" in text)


def _is_google_sheets_row_search(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate resolves Google Sheets rows before update."""
    if candidate.app_slug.casefold() != "google-sheets":
        return False
    text_terms = set(tokenize(_candidate_text(candidate)))
    module_key = _module_name_key(candidate.internal_name)
    return candidate.module_kind.casefold() == "search" and bool(
        {"row", "rows"}.intersection(text_terms) or "row" in module_key
    )


def _is_google_sheets_row_update(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate updates one Google Sheets row."""
    if candidate.app_slug.casefold() != "google-sheets":
        return False
    module_key = _module_name_key(candidate.internal_name)
    text_terms = set(tokenize(_candidate_text(candidate)))
    return candidate.module_kind.casefold() == "action" and bool(
        "updaterow" in module_key
        or ("update" in text_terms and {"row", "rows"}.intersection(text_terms))
    )


def _email_intent_active(query_terms: frozenset[str]) -> bool:
    """Return whether email terms should expand to mail workflow families."""
    if not EMAIL_REQUEST_TERMS.intersection(query_terms):
        return False
    if query_terms <= EMAIL_REQUEST_TERMS:
        return True
    if EMAIL_LOOKUP_ONLY_CONTEXT_TERMS.intersection(
        query_terms
    ) and GOOGLE_SHEETS_TERMS.intersection(query_terms):
        return False
    return bool(
        EMAIL_CANDIDATE_TERMS.intersection(query_terms)
        or {
            "notify",
            "receipt",
            "reply",
            "send",
            "sending",
            "watch",
        }.intersection(query_terms)
    )


def _google_sheets_lookup_before_update_active(
    query_terms: frozenset[str],
) -> bool:
    """Return whether Sheets update planning needs a lookup precondition."""
    if not GOOGLE_SHEETS_TERMS.intersection(query_terms):
        return False
    if not GOOGLE_SHEETS_UPDATE_TERMS.intersection(query_terms):
        return False
    if not GOOGLE_SHEETS_ROW_TERMS.intersection(query_terms):
        return False
    has_row_identifier = bool(ROW_IDENTIFIER_TERMS.intersection(query_terms))
    identifier_missing = bool(
        ROW_IDENTIFIER_MISSING_TERMS.intersection(query_terms)
    )
    return identifier_missing or not has_row_identifier


def _money_minor_units_to_text_active(query_terms: frozenset[str]) -> bool:
    """Return whether amount fields need minor-unit normalization before text.

    output.
    """
    return bool(
        MONEY_AMOUNT_TERMS.intersection(query_terms)
        and MINOR_UNIT_TERMS.intersection(query_terms)
        and CUSTOMER_VISIBLE_TEXT_TERMS.intersection(query_terms)
    )


def _attachment_iterator_bridge_active(query_terms: frozenset[str]) -> bool:
    """Return whether attachment arrays need an iterator before single-file.

    consumers.
    """
    return bool(
        ATTACHMENT_TERMS.intersection(query_terms)
        and SINGLE_FILE_TERMS.intersection(query_terms)
    )


def _runtime_setup_required(
    sequence_candidates: tuple[CatalogModuleCandidate, ...],
) -> bool:
    """Return whether selected modules imply provider setup prerequisites."""
    return any(
        candidate.app_slug.casefold() not in SETUP_FREE_APP_SLUGS
        for candidate in sequence_candidates
    )


def _candidate_text(candidate: CatalogModuleCandidate) -> str:
    """Return normalized text for candidate semantic predicates."""
    return (
        f"{candidate.module_id} {candidate.app_slug} {candidate.module_kind} "
        f"{candidate.internal_name} {candidate.display_name}"
    ).casefold()


def _branch_count(query_terms: frozenset[str]) -> int:
    """Return the computed result for the caller."""
    for group in ROUTE_SPLIT_GROUPS:
        matches = tuple(term for term in group if term in query_terms)
        if len(matches) >= MIN_ROUTE_SPLIT_MATCHES:
            return len(matches)
    return 1


def _is_custom_webhook_trigger(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate is Make's generic custom webhook trigger."""
    return (
        candidate.app_slug.casefold() == "gateway"
        and candidate.module_kind.casefold() == "trigger"
        and _module_name_key(candidate.internal_name) == "customwebhook"
    )


def _is_datastore_add_record(candidate: CatalogModuleCandidate) -> bool:
    """Return if a candidate is the first-party Data Store AddRecord action."""
    return (
        candidate.app_slug.casefold() == "datastore"
        and candidate.module_kind.casefold() == "action"
        and _module_name_key(candidate.internal_name) == "addrecord"
    )


def _is_webhook_response(candidate: CatalogModuleCandidate) -> bool:
    """Return whether a candidate is a webhook response module."""
    return "webhookresponse" in _module_name_key(candidate.internal_name)


def _is_unrequested_datastore_lookup(
    candidate: CatalogModuleCandidate,
    *,
    query_terms: frozenset[str],
) -> bool:
    """Return if a datastore lookup family is unrequested by the requirement."""
    if candidate.app_slug.casefold() != "datastore":
        return False
    module_key = _module_name_key(candidate.internal_name)
    if module_key in {"addrecord", "updaterecord"}:
        return False
    if DATASOURCE_LOOKUP_TERMS.intersection(query_terms):
        return False
    return module_key in {
        "existrecord",
        "getrecord",
        "searchrecords",
        "listrecords",
    }


def _unrelated_to_first_party_intent(
    candidate: CatalogModuleCandidate,
    *,
    query_terms: frozenset[str],
) -> bool:
    """Return whether a candidate should be excluded when first-party intent is.

    satisfied.
    """
    if datastore_intent_active(query_terms):
        return candidate.app_slug.casefold() not in {
            "datastore",
            "gateway",
            "webhooks",
        }
    return False
