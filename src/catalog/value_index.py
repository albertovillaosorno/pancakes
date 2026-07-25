# ruff: noqa: S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Canonical catalog value index and SQLite value validation.

Boundary contract:
- Owns: finite catalog value sets and deterministic noncanonical value
detection.
- Must not: delete rows, infer live provider state, or silently rewrite source
evidence.
- Allows: read-only database validation and save-time rejection for noncanonical
answers.
- Split when: canonical value definitions move into a dedicated generated SQLite
table.
- Merge when: another catalog module owns finite catalog value constraints.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.placeholder_index import catalog_placeholder_matches

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping

CANONICAL_WORK_COVERAGE_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "complete_evidence_bound ",
        "complete_with_evidence_gaps ",
        "minimal_evidence_bound ",
        "partial_evidence_gap ",
        "skipped_noncounted ",
        "blocked_non_counted_no_output",
    )
)
CATALOG_OUTPUT_VALUE_SCAN_LIMIT: Final = 50
SQLITE_IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CAMEL_CASE_BOUNDARY_PATTERN: Final = re.compile(
    r"(?<=[a-záéíóúñü])(?=[A-ZÁÉÍÓÚÑÜ])"
)
JSON_UNICODE_ESCAPE_PATTERN: Final = re.compile(r"\\u([0-9a-fA-F]{4})")
SPANISH_TOKEN_SPLIT_PATTERN: Final = re.compile(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
CANONICAL_MODULE_KINDS: Final[tuple[str, ...]] = (
    "action ",
    "agent ",
    "aggregator ",
    "router ",
    "search ",
    "transformer ",
    "trigger",
)
CANONICAL_FIELD_TYPE_VALUES: Final[tuple[str, ...]] = (
    "account ",
    "aiagent ",
    "any ",
    "array ",
    "binary ",
    "boolean ",
    "buffer ",
    "category ",
    "cert ",
    "collection ",
    "color ",
    "connection ",
    "credit ",
    "data ",
    "datastore ",
    "date ",
    "datetime ",
    "device ",
    "distance ",
    "email ",
    "file ",
    "filename ",
    "filter ",
    "hidden ",
    "html ",
    "id ",
    "integer ",
    "json ",
    "jsonb ",
    "name ",
    "number ",
    "object ",
    "password ",
    "path ",
    "phone ",
    "port ",
    "radio ",
    "scenario ",
    "select ",
    "spec ",
    "text ",
    "time ",
    "timestamp ",
    "timezone ",
    "token ",
    "type ",
    "udt ",
    "uid ",
    "uinteger ",
    "url ",
    "uuid ",
    "year",
)
CANONICAL_FIELD_TYPE_DYNAMIC_PREFIXES: Final[tuple[str, ...]] = (
    "account ",
    "device ",
    "hook ",
    "keychain ",
    "tokens",
)
CANONICAL_GRAPH_ENTITY_KINDS: Final[tuple[str, ...]] = (
    "api_surface ",
    "app ",
    "app_manifest ",
    "app_version ",
    "auth_scope ",
    "capability ",
    "capability_domain ",
    "catalog_priority_band ",
    "catalog_run ",
    "catalog_semantic_node ",
    "catalog_source_unit ",
    "catalog_unit ",
    "connection_type ",
    "control_surface ",
    "country_marker ",
    "crm_entity ",
    "data_entity ",
    "domain_entity ",
    "event_type ",
    "hook_type ",
    "make_app ",
    "make_app_version ",
    "make_module ",
    "module ",
    "module_batch ",
    "module_family ",
    "module_group ",
    "module_group_batch ",
    "module_operation ",
    "oauth_scope ",
    "operation ",
    "operation_batch ",
    "operation_collection ",
    "operation_profile ",
    "resource ",
    "rpc_selector ",
    "rpc_selector_family ",
    "source_unit ",
    "webhook_type",
)
CANONICAL_GRAPH_EDGE_KINDS: Final[tuple[str, ...]] = (
    "adds_member_to ",
    "adds_members_to ",
    "adds_relationship ",
    "belongs_to_booking ",
    "belongs_to_event ",
    "booked_by_contact ",
    "calls ",
    "calls_api_surface ",
    "can_correlate_by_transaction_id ",
    "can_correlate_with_movement_object ",
    "can_feed ",
    "can_feed_actions ",
    "can_feed_asin_to ",
    "can_inform ",
    "can_precede ",
    "can_redact ",
    "can_style_outputs_for ",
    "can_supply_context_to ",
    "can_supply_stage_context ",
    "can_translate_or_identify_speakers ",
    "can_wait_for ",
    "cancels ",
    "catalog_priority_band_has_unit ",
    "catalog_run_has_priority_band ",
    "catalog_semantic_edge ",
    "catalogs_app_version ",
    "connects_to ",
    "consumes ",
    "contact_feeds_communication ",
    "contains_group ",
    "contains_module ",
    "contains_module_family ",
    "contains_modules ",
    "contains_operation ",
    "creates ",
    "creates_alias_used_by ",
    "creates_and_sends_resource ",
    "creates_or_reads_resource ",
    "creates_or_updates ",
    "creates_or_updates_resource ",
    "creates_reply_for_resource ",
    "creates_resource ",
    "creates_ticket_readable_by ",
    "declares_country ",
    "declares_group ",
    "declares_manifest_profile ",
    "declares_operation ",
    "declares_operation_batch ",
    "declares_operation_collection ",
    "declares_operation_profile ",
    "deletes ",
    "deletes_or_archives_resource ",
    "deletes_or_recycles_resource ",
    "deletes_resource ",
    "describes_app_version ",
    "duplicates_resource ",
    "emits_context ",
    "emits_entity ",
    "enables_downstream ",
    "enriches_with ",
    "enrolls_resource_in ",
    "exposes_error_state ",
    "exposes_operation ",
    "fallback_for ",
    "feeds_attachment_token_to ",
    "feeds_filter ",
    "feeds_identifier_inputs_for ",
    "feeds_identifier_to ",
    "feeds_recipient_to ",
    "feeds_request_id_to ",
    "filters ",
    "finds ",
    "forwards_resource ",
    "groups_operation ",
    "has_capability ",
    "has_capability_domain ",
    "has_group ",
    "has_module_group ",
    "has_operation ",
    "has_operation_batch ",
    "has_source_unit ",
    "has_trigger ",
    "has_unit ",
    "has_version ",
    "hydrates_selector ",
    "hydrates_selector_for ",
    "implements_capability ",
    "inventory_feeds_configuration ",
    "inventory_feeds_create ",
    "inventory_feeds_filter ",
    "legacy_alternative ",
    "legacy_version_of ",
    "lifecycle_successor ",
    "manages ",
    "master_data_feeds_filter ",
    "moves_resource_to ",
    "operates_on ",
    "produces ",
    "provides_account_context_for ",
    "provides_customer_context ",
    "provides_customer_id_for ",
    "provides_oids_for ",
    "provides_price_context ",
    "provides_price_id_for ",
    "provides_product_id_context ",
    "provides_product_id_for ",
    "provides_user_identity_for ",
    "reads ",
    "reads_resource ",
    "removes_member_from ",
    "removes_relationship ",
    "required_by ",
    "required_connection ",
    "required_upstream ",
    "requires_account ",
    "requires_account_type ",
    "requires_connection ",
    "requires_connection_family ",
    "requires_connection_type ",
    "requires_existing_or_referenced ",
    "requires_hook ",
    "requires_hooks ",
    "requires_scope ",
    "requires_webhook ",
    "same_entity_surface ",
    "search_feeds_identifier_to ",
    "sends ",
    "sends_resource ",
    "supports_workflow ",
    "triggers_operation ",
    "updates ",
    "updates_resource ",
    "uses_connection_type ",
    "uses_dynamic_rpc_schema ",
    "uses_inbox_selector ",
    "uses_multiple_selectors ",
    "uses_optional_rpc_helper ",
    "uses_optional_rpc_selector ",
    "uses_rpc_selector ",
    "uses_rpc_selector_family ",
    "uses_rpc_selectors ",
    "uses_template ",
    "uses_workflow ",
    "version_has_module ",
    "version_has_module_group ",
    "version_of ",
    "watches ",
    "watches_membership ",
    "workflow_context ",
    "wraps_operation_family",
)
CANONICAL_MODULE_INTELLIGENCE_AUTH_TYPES: Final[tuple[str, ...]] = (
    "api_key ",
    "basic_auth ",
    "bearer_token ",
    "custom ",
    "none ",
    "oauth1 ",
    "oauth2 ",
    "unknown ",
    "webhook",
)
CANONICAL_MODULE_OUTPUT_CARDINALITIES: Final[tuple[str, ...]] = (
    "file ",
    "multi_bundle ",
    "side_effect_only ",
    "single_bundle ",
    "stream ",
    "unknown",
)
SPANISH_SEMANTIC_MARKERS: Final[tuple[str, ...]] = (
    "apellido ",
    "asociar ",
    "canal ",
    "canales ",
    "celular ",
    "cliente ",
    "clientes ",
    "comercial ",
    "consultar ",
    "contactos ",
    "catálogo ",
    "catalogo ",
    "correo ",
    "cuota ",
    "cuotas ",
    "descripción ",
    "descripcion ",
    "dirección ",
    "direccion ",
    "enviar ",
    "español ",
    "estado ",
    "evidencia suficiente ",
    "forma ",
    "formas ",
    "fulanito ",
    "informe ",
    "información ",
    "informacion ",
    "inmobiliaria ",
    "leerclientes ",
    "listar ",
    "mensaje ",
    "metodo ",
    "método ",
    "modelo ",
    "modelos ",
    "modificar ",
    "módulo ",
    "modulo ",
    "no hay ",
    "nombre ",
    "negocio ",
    "negocios ",
    "operación ",
    "operacion ",
    "pedido ",
    "producto ",
    "proyecto ",
    "proyectos ",
    "seguimiento ",
    "spanish ",
    "sin evidencia ",
    "suficiente ",
    "teléfono ",
    "telefono ",
    "tipo ",
    "vendedores",
)
CANONICAL_DYNAMIC_FIELD_TYPE_PATTERN_TEXT: Final = (
    r"(?:"
    + "|".join(CANONICAL_FIELD_TYPE_DYNAMIC_PREFIXES)
    + r"):[a-z0-9][a-z0-9_-]*(?:,[a-z0-9][a-z0-9_-]*)*"
)
CANONICAL_FIELD_TYPE_PATTERN_TEXT: Final = (
    r"^(?:"
    + "|".join(re.escape(value) for value in CANONICAL_FIELD_TYPE_VALUES)
    + r"|"
    + CANONICAL_DYNAMIC_FIELD_TYPE_PATTERN_TEXT
    + r")$"
)
CANONICAL_FIELD_TYPE_PATTERN: Final = re.compile(
    CANONICAL_FIELD_TYPE_PATTERN_TEXT
)
FIELD_TYPE_ALIASES: Final[dict[str, str]] = {
    "account id": "account ",
    "application/json": "json ",
    "array<text>": "array ",
    "array<uinteger>": "array ",
    "arrays": "array ",
    "bool": "boolean ",
    "boolena": "boolean ",
    "collectionmber": "collection ",
    "dat": "date ",
    "eetresponsibilityenum": "select ",
    "end lat": "number ",
    "end long": "number ",
    "file description": "text ",
    "filename": "filename ",
    "filestorage": "file ",
    "float": "number ",
    "int": "integer ",
    "legal entity": "text ",
    "nuumber": "number ",
    "numeric": "number ",
    "string": "text ",
    "tel": "phone ",
    "test": "text ",
    "teuuidxt": "text ",
    "tokens": "token ",
    "uietger": "uinteger ",
    "uiteger": "uinteger ",
    "uninteger": "uinteger ",
    "ur;": "url ",
    "uri": "url ",
    "uuis": "uuid ",
    "yyyy": "year",
}


class CatalogColumnValueDefinition(NamedTuple):
    """One finite catalog value set for an enum-like SQLite column."""

    table: str
    column: str
    allowed_values: tuple[str, ...]
    rationale: str


class CatalogPatternValueDefinition(NamedTuple):
    """One deterministic pattern-backed catalog value set."""

    table: str
    column: str
    allowed_pattern: str
    allowed_description: str
    rationale: str


class CatalogJsonArrayValueDefinition(NamedTuple):
    """One JSON array column whose items must use a finite catalog value set."""

    table: str
    column: str
    allowed_values: tuple[str, ...]
    rationale: str


class CatalogTextScanDefinition(NamedTuple):
    """One catalog text surface scanned for prohibited semantic language."""

    table: str
    column: str
    rationale: str


CATALOG_COLUMN_VALUE_INDEX: Final[tuple[CatalogColumnValueDefinition, ...]] = (
    CatalogColumnValueDefinition(
        table="catalog_runs",
        column="run_status",
        allowed_values=("active", "complete", "superseded_obsolete_evidence"),
        rationale="Catalog run lifecycle is a closed scheduler enum.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_runs",
        column="reset_strategy",
        allowed_values=("canonical_catalog",),
        rationale=(
            "The active catalog is the canonical catalog, not a versioned "
            "reset "
            "label."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_runs",
        column="incomplete_coverage_policy",
        allowed_values=("explicit_non_blocking",),
        rationale=(
            "Incomplete coverage remains visible but nonblocking for lookup."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_units",
        column="unit_type",
        allowed_values=(
            "app_manifest ",
            "app_spec ",
            "control_structure ",
            "field ",
            "module ",
            "note ",
            "operation ",
            "operation_batch ",
            "raw_spec",
        ),
        rationale="Unit types follow the catalog reset priority policy.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_units",
        column="priority_band",
        allowed_values=(
            "make_builtins_core ",
            "make_control_data_structures ",
            "make_ai_agents_tools_providers ",
            "popular_apps ",
            "alphabetical_remainder",
        ),
        rationale="Priority bands are deterministic reset scheduler buckets.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_units",
        column="status",
        allowed_values=("queued", "working", "completed"),
        rationale="Leaseable catalog units have a closed queue lifecycle.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_units",
        column="validation_status",
        allowed_values=(
            "pending ",
            "valid ",
            "local_response_blocked ",
            "safety_blocked_before_lease",
        ),
        rationale="Validation status is a closed receipt state.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_units",
        column="coverage_status",
        allowed_values=(
            "missing ",
            "complete ",
            "skipped_noncounted ",
            "blocked_non_counted_no_output",
        ),
        rationale=(
            "Coverage status must distinguish complete, missing, and "
            "noncounted "
            "rows."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_unit_notes",
        column="note_surface",
        allowed_values=(
            "error_handlers ",
            "filters ",
            "routers_control_structures ",
            "data_stores ",
            "data_structures ",
            "edge_cases ",
            "fallback_behavior ",
            "usage_guidance",
        ),
        rationale=(
            "Note surfaces are the first-class control surfaces for catalog "
            "reset."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_unit_notes",
        column="note_status",
        allowed_values=("missing", "complete"),
        rationale="Control-surface notes are either filled or still missing.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_unit_outputs",
        column="validation_status",
        allowed_values=("valid",),
        rationale=(
            "Saved output rows must already have passed save-time validation."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_module_intelligence_metadata",
        column="evidence_status",
        allowed_values=("unknown", "raw_spec_evidence", "raw_spec_manifest"),
        rationale=(
            "Module intelligence metadata records its local evidence posture."
        ),
    ),
    CatalogColumnValueDefinition(
        table="catalog_module_intelligence_metadata",
        column="auth_type",
        allowed_values=CANONICAL_MODULE_INTELLIGENCE_AUTH_TYPES,
        rationale="Module authentication type is a closed technical enum.",
    ),
    CatalogColumnValueDefinition(
        table="catalog_module_intelligence_metadata",
        column="output_cardinality",
        allowed_values=CANONICAL_MODULE_OUTPUT_CARDINALITIES,
        rationale="Module output cardinality is a closed technical enum.",
    ),
    CatalogColumnValueDefinition(
        table="entity_nodes",
        column="entity_kind",
        allowed_values=CANONICAL_GRAPH_ENTITY_KINDS,
        rationale=(
            "Graph node types must use the canonical catalog graph type index."
        ),
    ),
    CatalogColumnValueDefinition(
        table="entity_edges",
        column="edge_kind",
        allowed_values=CANONICAL_GRAPH_EDGE_KINDS,
        rationale=(
            "Graph edge types must use the canonical catalog graph type index."
        ),
    ),
    CatalogColumnValueDefinition(
        table="fields",
        column="direction",
        allowed_values=("expect", "interface", "parameter"),
        rationale="Make field facts use normalized raw-spec directions.",
    ),
    CatalogColumnValueDefinition(
        table="modules",
        column="module_kind",
        allowed_values=CANONICAL_MODULE_KINDS,
        rationale="Make module kinds are finite raw-spec surfaces.",
    ),
)
CATALOG_PATTERN_VALUE_INDEX: Final[
    tuple[CatalogPatternValueDefinition, ...]
] = (
    CatalogPatternValueDefinition(
        table="fields",
        column="field_type",
        allowed_pattern=CANONICAL_FIELD_TYPE_PATTERN_TEXT,
        allowed_description=(
            "Canonical lower-case Make field type or provider-scoped dynamic "
            "type with "
            "account:, device:, hook:, keychain:, or tokens: prefix."
        ),
        rationale=(
            "Field types must be canonical technical values, not raw aliases."
        ),
    ),
)
CATALOG_JSON_ARRAY_VALUE_INDEX: Final[
    tuple[CatalogJsonArrayValueDefinition, ...]
] = (
    CatalogJsonArrayValueDefinition(
        table="make_raw_spec_manifest_records",
        column="module_kinds_json",
        allowed_values=CANONICAL_MODULE_KINDS,
        rationale=(
            "Manifest module-kind arrays must use the canonical module-kind "
            "index."
        ),
    ),
    CatalogJsonArrayValueDefinition(
        table="make_raw_spec_payloads",
        column="module_kinds_json",
        allowed_values=CANONICAL_MODULE_KINDS,
        rationale=(
            "Raw-spec payload module-kind arrays must use the canonical "
            "module-kind index."
        ),
    ),
)
CATALOG_SPANISH_TEXT_SCAN_INDEX: Final[
    tuple[CatalogTextScanDefinition, ...]
] = (
    CatalogTextScanDefinition(
        table="catalog_unit_outputs",
        column="output_json",
        rationale="Saved catalog semantic answers must be English-only.",
    ),
    CatalogTextScanDefinition(
        table="catalog_module_intelligence_metadata",
        column="input_schema_json",
        rationale=(
            "Saved module intelligence schema metadata must be English-only."
        ),
    ),
    CatalogTextScanDefinition(
        table="catalog_module_intelligence_metadata",
        column="output_schema_json",
        rationale=(
            "Saved module intelligence schema metadata must be English-only."
        ),
    ),
    CatalogTextScanDefinition(
        table="catalog_module_intelligence_metadata",
        column="field_constraints_json",
        rationale="Saved module intelligence constraints must be English-only.",
    ),
    CatalogTextScanDefinition(
        table="entity_nodes",
        column="canonical_label",
        rationale="Catalog graph labels must be English-only.",
    ),
    CatalogTextScanDefinition(
        table="entity_nodes",
        column="payload_json",
        rationale="Catalog graph node payloads must be English-only.",
    ),
    CatalogTextScanDefinition(
        table="entity_edges",
        column="payload_json",
        rationale="Catalog graph edge payloads must be English-only.",
    ),
)


def catalog_canonical_value_index_payload() -> list[dict[str, object]]:
    """Return finite catalog value sets as JSON-compatible SSOT rows."""
    rows: list[dict[str, object]] = [
        {
            "table": definition.table,
            "column": definition.column,
            "allowed_values": list(definition.allowed_values),
            "rationale": definition.rationale,
        }
        for definition in CATALOG_COLUMN_VALUE_INDEX
    ]
    rows.extend(
        {
            "table": definition.table,
            "column": definition.column,
            "allowed_pattern": definition.allowed_pattern,
            "allowed_description": definition.allowed_description,
            "rationale": definition.rationale,
        }
        for definition in CATALOG_PATTERN_VALUE_INDEX
    )
    rows.extend(
        {
            "table": definition.table,
            "column": f"{definition.column}[]",
            "allowed_values": list(definition.allowed_values),
            "rationale": definition.rationale,
        }
        for definition in CATALOG_JSON_ARRAY_VALUE_INDEX
    )
    rows.extend(
        (
            {
                "table": "catalog_semantic_text ",
                "column": "text",
                "prohibited_markers": list(SPANISH_SEMANTIC_MARKERS),
                "rationale": (
                    "Catalog semantics, graph labels, and graph payloads are "
                    "English-only."
                ),
            },
            {
                "table": "catalog_unit_outputs ",
                "column": "output_json.coverage.status",
                "allowed_values": sorted(CANONICAL_WORK_COVERAGE_STATUSES),
                "rationale": (
                    "Saved semantic answers must use canonical coverage states."
                ),
            },
        )
    )
    return rows


def catalog_database_value_index_payload(
    *,
    connection: sqlite3.Connection,
) -> dict[str, object]:
    """Return canonical value-index status for the current SQLite database."""
    violations = catalog_database_value_violations(connection=connection)
    return {
        "status": "ok" if not violations else "error",
        "violation_count": len(violations),
        "violations": violations[:CATALOG_OUTPUT_VALUE_SCAN_LIMIT],
        "violation_limit": CATALOG_OUTPUT_VALUE_SCAN_LIMIT,
        "truncated": len(violations) > CATALOG_OUTPUT_VALUE_SCAN_LIMIT,
    }


def catalog_database_value_violations(
    *,
    connection: sqlite3.Connection,
) -> list[dict[str, object]]:
    """Return noncanonical catalog values without deleting or mutating rows."""
    violations: list[dict[str, object]] = []
    for definition in CATALOG_COLUMN_VALUE_INDEX:
        if not _table_has_column(
            connection=connection,
            table=definition.table,
            column=definition.column,
        ):
            continue
        violations.extend(
            _column_value_violations(
                connection=connection, definition=definition
            )
        )
    for definition in CATALOG_PATTERN_VALUE_INDEX:
        if not _table_has_column(
            connection=connection,
            table=definition.table,
            column=definition.column,
        ):
            continue
        violations.extend(
            _pattern_value_violations(
                connection=connection, definition=definition
            )
        )
    for definition in CATALOG_JSON_ARRAY_VALUE_INDEX:
        if not _table_has_column(
            connection=connection,
            table=definition.table,
            column=definition.column,
        ):
            continue
        violations.extend(
            _json_array_value_violations(
                connection=connection, definition=definition
            )
        )
    violations.extend(_output_coverage_status_violations(connection=connection))
    violations.extend(_spanish_text_violations(connection=connection))
    return violations


def require_catalog_work_output_canonical_values(
    output_json: Mapping[str, object],
) -> None:
    """Fail a catalog work answer when it contains noncanonical values.

    Raises:
        ValueError: If coverage status or sample placeholder values are
        noncanonical.
        TypeError: If coverage status is present but not text.
    """
    coverage = output_json.get("coverage")
    if not isinstance(coverage, dict):
        message = "missing_required_field: coverage"
        raise TypeError(message)
    status = cast("Mapping[object, object]", coverage).get("status")
    if not isinstance(status, str) or not status.strip():
        message = "missing_required_field: coverage.status"
        raise ValueError(message)
    if status not in CANONICAL_WORK_COVERAGE_STATUSES:
        allowed = ", ".join(sorted(CANONICAL_WORK_COVERAGE_STATUSES))
        message = (
            f"noncanonical_value: coverage.status={status!r}; expected one of:"
            f"{allowed}."
        )
        raise ValueError(message)

    _validate_catalog_work_graph_types(output_json)
    _validate_catalog_work_module_semantics(output_json)
    serialized = json.dumps(
        output_json, ensure_ascii=True, sort_keys=True, default=str
    )
    spanish_matches = catalog_spanish_text_matches(serialized)
    if spanish_matches:
        message = (
            "noncanonical_spanish_text: catalog semantics must be "
            "English-only; "
            ""
            f"first marker: {spanish_matches[0]!r}."
        )
        raise ValueError(message)
    placeholder_matches = catalog_placeholder_matches(serialized)
    if not placeholder_matches:
        return
    first = placeholder_matches[0]
    message = (
        "noncanonical_placeholder_value: replace sample value with "
        f"{first['placeholder']} before saving catalog work."
    )
    raise ValueError(message)


def require_catalog_graph_entity_kind_canonical(value: str) -> None:
    """Fail when a graph node entity kind is outside the canonical type.

    index.
    """
    _require_canonical_text_value(
        field_name="entity_kind",
        value=value,
        allowed_values=CANONICAL_GRAPH_ENTITY_KINDS,
    )


def require_catalog_graph_edge_kind_canonical(value: str) -> None:
    """Fail when a graph edge kind is outside the canonical type index."""
    _require_canonical_text_value(
        field_name="edge_kind",
        value=value,
        allowed_values=CANONICAL_GRAPH_EDGE_KINDS,
    )


def catalog_spanish_text_matches(text: str) -> list[str]:
    """Return prohibited Spanish markers found in catalog semantic text."""
    tokens = _catalog_semantic_text_tokens(text)
    if not tokens:
        return []
    normalized = f" {' '.join(tokens)} "
    matches: list[str] = []
    for marker in SPANISH_SEMANTIC_MARKERS:
        marker_tokens = _catalog_semantic_text_tokens(marker)
        if not marker_tokens:
            continue
        if f" {' '.join(marker_tokens)} " in normalized:
            matches.append(marker)
    return matches


def canonicalize_catalog_field_type(value: str | None) -> str | None:
    """Return the canonical field-type value used by the catalog value index."""
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    if not normalized:
        return None
    aliased = FIELD_TYPE_ALIASES.get(normalized)
    if aliased is not None:
        return aliased
    if normalized.startswith(CANONICAL_FIELD_TYPE_DYNAMIC_PREFIXES):
        return normalized.replace(" ", "")
    return normalized


def _catalog_semantic_text_tokens(text: str) -> list[str]:
    decoded = JSON_UNICODE_ESCAPE_PATTERN.sub(
        lambda match: chr(int(match.group(1), 16)),
        text,
    )
    split_text = CAMEL_CASE_BOUNDARY_PATTERN.sub(" ", decoded)
    return [
        token
        for token in SPANISH_TOKEN_SPLIT_PATTERN.split(split_text.casefold())
        if token
    ]


def _column_value_violations(
    *,
    connection: sqlite3.Connection,
    definition: CatalogColumnValueDefinition,
) -> list[dict[str, object]]:
    table = _safe_identifier(definition.table)
    column = _safe_identifier(definition.column)
    placeholders = ", ".join("?" for _ in definition.allowed_values)
    sql = f"""  # noqa: S608
        SELECT {column} AS observed_value, COUNT(*) AS row_count
        FROM {table}
        WHERE {column} IS NOT NULL
          AND {column} NOT IN ({placeholders})
        GROUP BY {column}
        ORDER BY row_count DESC, observed_value
        """
    rows = connection.execute(
        sql,
        definition.allowed_values,
    ).fetchall()
    return [
        {
            "table": definition.table,
            "column": definition.column,
            "observed_value": str(row[0]),
            "row_count": int(row[1]),
            "error_code": "noncanonical_catalog_value",
            "allowed_values": list(definition.allowed_values),
        }
        for row in rows
    ]


def _pattern_value_violations(
    *,
    connection: sqlite3.Connection,
    definition: CatalogPatternValueDefinition,
) -> list[dict[str, object]]:
    table = _safe_identifier(definition.table)
    column = _safe_identifier(definition.column)
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT {column} AS observed_value, COUNT(*) AS row_count
        FROM {table}
        WHERE {column} IS NOT NULL
        GROUP BY {column}
        ORDER BY row_count DESC, observed_value
        """
    ).fetchall()
    pattern = re.compile(definition.allowed_pattern)
    return [
        {
            "table": definition.table,
            "column": definition.column,
            "observed_value": str(row[0]),
            "row_count": int(row[1]),
            "error_code": "noncanonical_catalog_value",
            "allowed_pattern": definition.allowed_pattern,
            "allowed_description": definition.allowed_description,
        }
        for row in rows
        if pattern.fullmatch(str(row[0])) is None
    ]


def _json_array_value_violations(
    *,
    connection: sqlite3.Connection,
    definition: CatalogJsonArrayValueDefinition,
) -> list[dict[str, object]]:
    table = _safe_identifier(definition.table)
    column = _safe_identifier(definition.column)
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT {column} AS raw_value
        FROM {table}
        WHERE {column} IS NOT NULL
        """
    ).fetchall()
    counts: dict[str, int] = {}
    allowed = set(definition.allowed_values)
    for row in rows:
        raw_value = row[0]
        if not isinstance(raw_value, str):
            counts["<non_text_json>"] = counts.get("<non_text_json>", 0) + 1
            continue
        try:
            decoded = json.loads(raw_value)
        except json.JSONDecodeError:
            counts["<invalid_json>"] = counts.get("<invalid_json>", 0) + 1
            continue
        if not isinstance(decoded, list):
            counts["<non_array_json>"] = counts.get("<non_array_json>", 0) + 1
            continue
        for item in cast("list[object]", decoded):
            value = (
                item
                if isinstance(item, str) and item.strip()
                else "<non_text_value>"
            )
            if value in allowed:
                continue
            counts[value] = counts.get(value, 0) + 1
    return [
        {
            "table": definition.table,
            "column": f"{definition.column}[]",
            "observed_value": value,
            "row_count": count,
            "error_code": "noncanonical_catalog_value",
            "allowed_values": list(definition.allowed_values),
        }
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _output_coverage_status_violations(
    *,
    connection: sqlite3.Connection,
) -> list[dict[str, object]]:
    if not _table_has_column(
        connection=connection,
        table="catalog_unit_outputs",
        column="output_json",
    ):
        return []
    counts: dict[str, int] = {}
    rows = connection.execute(
        """
        SELECT output_json
        FROM catalog_unit_outputs
        """
    ).fetchall()
    for row in rows:
        raw_value = row[0]
        if not isinstance(raw_value, str):
            key = "<non_text_json>"
        else:
            key = _coverage_status_from_output(raw_value)
        if key in CANONICAL_WORK_COVERAGE_STATUSES:
            continue
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "table": "catalog_unit_outputs ",
            "column": "output_json.coverage.status",
            "observed_value": value,
            "row_count": count,
            "error_code": "noncanonical_catalog_value",
            "allowed_values": sorted(CANONICAL_WORK_COVERAGE_STATUSES),
        }
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _coverage_status_from_output(raw_value: str) -> str:
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return "<invalid_json>"
    if not isinstance(decoded, dict):
        return "<non_object_json>"
    decoded_object = cast("dict[str, object]", decoded)
    coverage = decoded_object.get("coverage")
    if not isinstance(coverage, dict):
        return "<missing_coverage>"
    coverage_object = cast("dict[str, object]", coverage)
    status = coverage_object.get("status")
    if not isinstance(status, str) or not status.strip():
        return "<missing_coverage_status>"
    return status


def _spanish_text_violations(
    *,
    connection: sqlite3.Connection,
) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str], int] = {}
    for definition in CATALOG_SPANISH_TEXT_SCAN_INDEX:
        if not _table_has_column(
            connection=connection,
            table=definition.table,
            column=definition.column,
        ):
            continue
        table = _safe_identifier(definition.table)
        column = _safe_identifier(definition.column)
        rows = connection.execute(
            f"""  # noqa: S608
            SELECT {column} AS raw_value
            FROM {table}
            WHERE {column} IS NOT NULL
            """
        ).fetchall()
        for row in rows:
            raw_value = row[0]
            if not isinstance(raw_value, str):
                continue
            for marker in catalog_spanish_text_matches(raw_value):
                key = (definition.table, definition.column, marker)
                counts[key] = counts.get(key, 0) + 1
    return [
        {
            "table": table,
            "column": column,
            "observed_value": marker,
            "row_count": count,
            "error_code": "noncanonical_spanish_catalog_text",
            "prohibited_markers": list(SPANISH_SEMANTIC_MARKERS),
        }
        for (table, column, marker), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _validate_catalog_work_graph_types(
    output_json: Mapping[str, object],
) -> None:
    nodes = output_json.get("graph_nodes")
    if isinstance(nodes, list):
        for index, item in enumerate(cast("list[object]", nodes)):
            if not isinstance(item, dict):
                continue
            node = cast("Mapping[object, object]", item)
            entity_kind = _optional_text_from_mapping(node, "entity_kind")
            if entity_kind is None:
                entity_kind = _optional_text_from_mapping(node, "node_kind")
            _require_canonical_text_value(
                field_name=f"graph_nodes[{index}].entity_kind",
                value=entity_kind or "catalog_semantic_node",
                allowed_values=CANONICAL_GRAPH_ENTITY_KINDS,
            )

    edges = output_json.get("graph_edges")
    if isinstance(edges, list):
        for index, item in enumerate(cast("list[object]", edges)):
            if not isinstance(item, dict):
                continue
            edge = cast("Mapping[object, object]", item)
            edge_kind = _optional_text_from_mapping(edge, "edge_kind")
            if edge_kind is None:
                edge_kind = _optional_text_from_mapping(edge, "kind")
            _require_canonical_text_value(
                field_name=f"graph_edges[{index}].edge_kind",
                value=edge_kind or "catalog_semantic_edge",
                allowed_values=CANONICAL_GRAPH_EDGE_KINDS,
            )


def _validate_catalog_work_module_semantics(
    output_json: Mapping[str, object],
) -> None:
    module_semantics = output_json.get("module_semantics")
    if not isinstance(module_semantics, list):
        return
    for index, item in enumerate(cast("list[object]", module_semantics)):
        if not isinstance(item, dict):
            continue
        metadata = cast("Mapping[object, object]", item)
        auth_type = _optional_text_from_mapping(metadata, "auth_type")
        if auth_type is not None:
            _require_canonical_text_value(
                field_name=f"module_semantics[{index}].auth_type",
                value=auth_type,
                allowed_values=CANONICAL_MODULE_INTELLIGENCE_AUTH_TYPES,
            )
        output_cardinality = _optional_text_from_mapping(
            metadata, "output_cardinality"
        )
        if output_cardinality is not None:
            _require_canonical_text_value(
                field_name=f"module_semantics[{index}].output_cardinality",
                value=output_cardinality,
                allowed_values=CANONICAL_MODULE_OUTPUT_CARDINALITIES,
            )


def _optional_text_from_mapping(
    mapping: Mapping[object, object], key: str
) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"noncanonical_value: {key} must be text."
        raise TypeError(message)
    stripped = value.strip()
    return stripped or None


def _require_canonical_text_value(
    *,
    field_name: str,
    value: str,
    allowed_values: tuple[str, ...],
) -> None:
    if value in allowed_values:
        return
    allowed = ", ".join(allowed_values)
    message = (
        f"noncanonical_value: {field_name}={value!r}; expected one of:"
        f"{allowed}."
    )
    raise ValueError(message)


def _table_has_column(
    *, connection: sqlite3.Connection, table: str, column: str
) -> bool:
    if not _sqlite_table_exists(connection=connection, table_name=table):
        return False
    rows = connection.execute(
        f"PRAGMA table_info({_safe_identifier(table)})"
    ).fetchall()
    return any(row[1] == column for row in rows)


def _sqlite_table_exists(
    *, connection: sqlite3.Connection, table_name: str
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _safe_identifier(value: str) -> str:
    if SQLITE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        message = f"Unsafe SQLite identifier in catalog value index: {value!r}"
        raise ValueError(message)
    return f'"{value}"'
