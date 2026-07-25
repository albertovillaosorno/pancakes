# ruff: noqa: PLR0913, PLR0914, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - docs/adr/catalog-semantic-graph-preview-policy.md
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false, reportUnknownVariableType=false,

"""SQLite-native catalog graph search and semantic-output preview tools.

Boundary contract:
- Owns: read-only graph lookup and unsaved semantic graph preview over Pancakes
SQLite.
- Must not: mutate SQLite, lease work, save work, call providers, call live
Make.com, or emit
  credential values.
- Allows: compact graph overview, requested node/edge/unit expansion, and
pre-save validation.
- Split when: preview becomes a dedicated planner service or graph ranking
model.
- Merge when: catalog.search owns the same graph preview contract directly.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from typing import TYPE_CHECKING, Final, cast

from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH

from mcp.inactive_catalog_work import (
    validate_catalog_work_save_unit_for_preview,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from mcp.models import JsonObject

CATALOG_GRAPH_SQLITE_TIMEOUT_SECONDS: Final = 5
CATALOG_GRAPH_BUSY_TIMEOUT_MILLISECONDS: Final = 5_000
CATALOG_GRAPH_DEFAULT_LIMIT: Final = 8
CATALOG_GRAPH_MAX_LIMIT: Final = 50
CATALOG_GRAPH_MIN_TERM_LENGTH: Final = 2
CATALOG_GRAPH_TEXT_PATTERN: Final = re.compile(r"[A-Za-z0-9_.:-]+")
CATALOG_GRAPH_SECRET_MARKERS: Final = (
    r"api[_ -]?key",
    r"access[_ -]?token",
    r"auth[_ -]?token",
    r"bearer",
    r"refresh[_ -]?token",
    r"secret",
    r"password",
)
CATALOG_GRAPH_SECRET_MARKER_PATTERN: Final = re.compile(
    "|".join(CATALOG_GRAPH_SECRET_MARKERS),
    re.IGNORECASE,
)
CATALOG_GRAPH_OUTPUT_MODES: Final = frozenset(("compact", "full", "debug"))


def catalog_graph_search(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Search and expand the current SQLite catalog graph without writes.

    Returns:
        A compact MCP payload with graph overview, matches, and requested
        expansion.
    """
    query = _optional_text(arguments.get("query"))
    node_id = _optional_text(arguments.get("node_id"))
    edge_id = _optional_text(arguments.get("edge_id"))
    unit_id = _optional_text(arguments.get("unit_id"))
    output_mode = _optional_output_mode(arguments.get("output_mode"))
    limit = _optional_limit(arguments.get("limit"))
    database_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    payload = _base_payload(
        tool_name="catalog.graph.search",
        database_path=database_path,
        output_mode=output_mode,
    )
    if not database_path.exists():
        payload.update(_missing_database_payload(database_path=database_path))
        return payload

    seed_query = " ".join(
        value for value in (query, node_id, edge_id, unit_id) if value
    )
    with closing(_connect_readonly(database_path)) as connection:
        overview = _graph_overview(connection=connection, limit=limit)
        terms = _search_terms(seed_query)
        node_matches = _node_matches(
            connection=connection, terms=terms, limit=limit
        )
        edge_matches = _edge_matches(
            connection=connection, terms=terms, limit=limit
        )
        output_matches = _semantic_output_matches(
            connection=connection,
            terms=terms,
            limit=limit,
        )
        document_matches = _search_document_matches(
            connection=connection,
            terms=terms,
            limit=limit,
        )
        expansion = _requested_expansion(
            connection=connection,
            node_id=node_id,
            edge_id=edge_id,
            unit_id=unit_id,
            limit=limit,
            output_mode=output_mode,
        )

    returned_count = (
        len(node_matches)
        + len(edge_matches)
        + len(output_matches)
        + len(document_matches)
    )
    payload.update(
        {
            "status": "ok" if returned_count or expansion else "overview",
            "query": query,
            "terms": list(terms),
            "limit": limit,
            "graph_overview": overview,
            "node_matches": node_matches,
            "edge_matches": edge_matches,
            "semantic_output_matches": output_matches,
            "search_document_matches": document_matches,
            "expansion": expansion,
            "result_counts": {
                "node_matches": len(node_matches),
                "edge_matches": len(edge_matches),
                "semantic_output_matches": len(output_matches),
                "search_document_matches": len(document_matches),
                "returned_result_count": returned_count,
            },
            "expansion_contract": {
                "default_mode": "compact_overview",
                "expand_with": [
                    "node_id ",
                    "edge_id ",
                    "unit_id ",
                    "output_mode=full",
                ],
            },
        }
    )
    return payload


def catalog_semantic_preview(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Preview proposed catalog semantic graph output before a leased save.

    Returns:
        A read-only MCP payload with save validation, graph quality, and query
        preview.

    Raises:
        ValueError: When no answer payload is supplied.
    """
    database_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    output_mode = _optional_output_mode(arguments.get("output_mode"))
    limit = _optional_limit(arguments.get("limit"))
    payload = _base_payload(
        tool_name="catalog.semantic.preview",
        database_path=database_path,
        output_mode=output_mode,
    )
    raw_units = _preview_raw_units(arguments)
    if not raw_units:
        message = (
            "catalog.semantic.preview requires answer_json or "
            "answers_json.units."
        )
        raise ValueError(message)
    preview_queries = _preview_queries(arguments)
    validated_units: list[JsonObject] = []
    validation_errors: list[JsonObject] = []
    for index, raw_unit in enumerate(raw_units):
        try:
            save = validate_catalog_work_save_unit_for_preview(raw_unit)
        except (TypeError, ValueError) as exc:
            validation_errors.append(
                {
                    "unit_index": index,
                    "unit_id": _safe_unit_id(raw_unit),
                    "error": str(exc),
                }
            )
            continue
        validated_units.append(
            _preview_unit_payload(
                unit_id=save.unit_id,
                output_json=save.output_json,
                output_size_bytes=len(save.output_text.encode("utf-8")),
                output_sha256=save.output_sha256,
            )
        )

    if not database_path.exists():
        payload.update(_missing_database_payload(database_path=database_path))
        payload.update(
            {
                "unit_count": len(raw_units),
                "validated_unit_count": len(validated_units),
                "validation_errors": validation_errors,
            }
        )
        return payload

    with closing(_connect_readonly(database_path)) as connection:
        existing_node_ids = _existing_node_ids_for_preview(
            connection=connection,
            units=validated_units,
        )
        for unit in validated_units:
            unit["graph_quality"] = _graph_quality(
                unit=unit,
                existing_node_ids=existing_node_ids,
            )
        search_preview = [
            _preview_query_result(
                connection=connection,
                query=query,
                units=validated_units,
                limit=limit,
            )
            for query in preview_queries
        ]
        overview = _graph_overview(connection=connection, limit=limit)

    aggregate = _preview_aggregate(validated_units)
    quality_findings = _quality_findings(
        validated_units=validated_units,
        validation_errors=validation_errors,
        search_preview=search_preview,
    )
    status = (
        "ready_to_save"
        if not quality_findings and not validation_errors
        else "needs_revision"
    )
    payload.update(
        {
            "status": status,
            "unit_count": len(raw_units),
            "validated_unit_count": len(validated_units),
            "validation_errors": validation_errors,
            "quality_findings": quality_findings,
            "aggregate_graph_counts": aggregate,
            "unit_previews": _bounded_units(
                validated_units, output_mode=output_mode
            ),
            "preview_queries": preview_queries,
            "search_preview": search_preview,
            "existing_graph_overview": overview,
            "save_gate": {
                "same_validation_family_as_catalog_work_save": True,
                "empty_graph_nodes_rejected": True,
                "empty_graph_edges_rejected": True,
                "full_leased_batch_still_required_by_catalog_work_save": True,
            },
            "writes_performed": False,
        }
    )
    return payload


def _base_payload(
    *,
    tool_name: str,
    database_path: Path,
    output_mode: str,
) -> JsonObject:
    _ = database_path
    return {
        "tool_name": tool_name,
        "database_ref": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "output_mode": output_mode,
        "local_only": True,
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _missing_database_payload(*, database_path: Path) -> JsonObject:
    _ = database_path
    return {
        "status": "blocked ",
        "blocker_code": "knowledge_sqlite_missing",
        "missing_paths": [DEFAULT_KNOWLEDGE_DB_PATH.as_posix()],
        "recommended_commands": ["pancakes.validate", "pancakes.mcp.smoke"],
    }


def _connect_readonly(database_path: Path) -> sqlite3.Connection:
    uri = f"{database_path.resolve().as_uri()}?mode=ro&cache=shared"
    connection = sqlite3.connect(
        uri,
        timeout=CATALOG_GRAPH_SQLITE_TIMEOUT_SECONDS,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        _execute_and_close(connection, "PRAGMA query_only = ON")
        _execute_and_close(
            connection,
            f"PRAGMA busy_timeout = {CATALOG_GRAPH_BUSY_TIMEOUT_MILLISECONDS}",
        )
    except BaseException:
        connection.close()
        raise
    return connection


def _execute_and_close(connection: sqlite3.Connection, statement: str) -> None:
    cursor = connection.execute(statement)
    cursor.close()


def _graph_overview(
    *, connection: sqlite3.Connection, limit: int
) -> JsonObject:
    return {
        "valid_node_count": _count(
            connection, "entity_nodes", "valid_to IS NULL"
        ),
        "valid_edge_count": _count(
            connection, "entity_edges", "valid_to IS NULL"
        ),
        "semantic_output_count": _count(
            connection, "catalog_unit_outputs", "1 = 1"
        ),
        "search_document_count": _count(
            connection,
            "catalog_search_documents ",
            "valid_to IS NULL",
        ),
        "entity_kind_counts": _top_counts(
            connection=connection,
            table_name="entity_nodes",
            column_name="entity_kind",
            where_clause="valid_to IS NULL",
            limit=limit,
        ),
        "edge_kind_counts": _top_counts(
            connection=connection,
            table_name="entity_edges",
            column_name="edge_kind",
            where_clause="valid_to IS NULL",
            limit=limit,
        ),
        "source_kind_counts": _top_counts(
            connection=connection,
            table_name="entity_nodes",
            column_name="source_kind",
            where_clause="valid_to IS NULL",
            limit=limit,
        ),
    }


def _count(
    connection: sqlite3.Connection, table_name: str, where_clause: str
) -> int:
    if table_name not in {
        "entity_nodes ",
        "entity_edges ",
        "catalog_unit_outputs ",
        "catalog_search_documents",
    }:
        message = f"Unsupported count table: {table_name}"
        raise ValueError(message)
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"
    ).fetchone()
    return 0 if row is None else int(row[0])


def _top_counts(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    where_clause: str,
    limit: int,
) -> list[JsonObject]:
    if table_name not in {"entity_nodes", "entity_edges"}:
        message = f"Unsupported top-count table: {table_name}"
        raise ValueError(message)
    if column_name not in {"entity_kind", "edge_kind", "source_kind"}:
        message = f"Unsupported top-count column: {column_name}"
        raise ValueError(message)
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT {column_name} AS value, COUNT(*) AS row_count
        FROM {table_name}
        WHERE {where_clause}
        GROUP BY {column_name}
        ORDER BY row_count DESC, value
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {"value": str(row["value"]), "row_count": int(row["row_count"])}
        for row in rows
    ]


def _node_matches(
    *,
    connection: sqlite3.Connection,
    terms: Sequence[str],
    limit: int,
) -> list[JsonObject]:
    if not terms:
        return []
    rows = connection.execute(
        """
        SELECT node_id, domain, entity_kind, canonical_label, payload_json,
        source_kind,
               source_ref, ingest_run_id
        FROM entity_nodes
        WHERE valid_to IS NULL
        ORDER BY domain, entity_kind, canonical_label, node_id
        """
    ).fetchall()
    return [
        _node_payload(row=row, output_mode="compact")
        for row in _matching_rows(rows=rows, terms=terms, limit=limit)
    ]


def _edge_matches(
    *,
    connection: sqlite3.Connection,
    terms: Sequence[str],
    limit: int,
) -> list[JsonObject]:
    if not terms:
        return []
    rows = connection.execute(
        """
        SELECT edges.edge_id, edges.domain, edges.edge_kind, edges.from_node_id,
               edges.to_node_id, edges.payload_json, edges.source_kind,
               edges.source_ref,
               edges.ingest_run_id, from_nodes.canonical_label AS from_label,
               to_nodes.canonical_label AS to_label
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
        ORDER BY edges.domain, edges.edge_kind, edges.edge_id
        """
    ).fetchall()
    return [
        _edge_payload(row=row, output_mode="compact")
        for row in _matching_rows(rows=rows, terms=terms, limit=limit)
    ]


def _semantic_output_matches(
    *,
    connection: sqlite3.Connection,
    terms: Sequence[str],
    limit: int,
) -> list[JsonObject]:
    if not terms:
        return []
    rows = connection.execute(
        """
        SELECT outputs.run_id, outputs.unit_id, outputs.output_json,
        outputs.source_ref,
               outputs.created_at_utc, units.unit_type, units.priority_band
        FROM catalog_unit_outputs AS outputs
        LEFT JOIN catalog_units AS units
          ON units.run_id = outputs.run_id
         AND units.unit_id = outputs.unit_id
        ORDER BY outputs.created_at_utc DESC, outputs.unit_id
        """
    ).fetchall()
    return [
        {
            "kind": "catalog_unit_output",
            "run_id": str(row["run_id"]),
            "unit_id": str(row["unit_id"]),
            "unit_type": str(row["unit_type"]),
            "priority_band": str(row["priority_band"]),
            "source_ref": str(row["source_ref"]),
            "snippet": _snippet(str(row["output_json"])),
        }
        for row in _matching_rows(rows=rows, terms=terms, limit=limit)
    ]


def _search_document_matches(
    *,
    connection: sqlite3.Connection,
    terms: Sequence[str],
    limit: int,
) -> list[JsonObject]:
    if not terms:
        return []
    rows = connection.execute(
        """
        SELECT document_id, surface, title, record_kind, search_text, source_ref
        FROM catalog_search_documents
        WHERE valid_to IS NULL
        ORDER BY surface, record_kind, title, document_id
        """
    ).fetchall()
    return [
        {
            "kind": "catalog_search_document",
            "document_id": str(row["document_id"]),
            "surface": str(row["surface"]),
            "title": str(row["title"]),
            "record_kind": str(row["record_kind"]),
            "source_ref": str(row["source_ref"]),
            "snippet": _snippet(str(row["search_text"])),
        }
        for row in _matching_rows(rows=rows, terms=terms, limit=limit)
    ]


def _requested_expansion(
    *,
    connection: sqlite3.Connection,
    node_id: str | None,
    edge_id: str | None,
    unit_id: str | None,
    limit: int,
    output_mode: str,
) -> JsonObject:
    expansion: JsonObject = {}
    if node_id is not None:
        expansion["node"] = _node_expansion(
            connection=connection,
            node_id=node_id,
            limit=limit,
            output_mode=output_mode,
        )
    if edge_id is not None:
        expansion["edge"] = _edge_expansion(
            connection=connection,
            edge_id=edge_id,
            output_mode=output_mode,
        )
    if unit_id is not None:
        expansion["unit"] = _unit_expansion(
            connection=connection,
            unit_id=unit_id,
            output_mode=output_mode,
        )
    return expansion


def _node_expansion(
    *,
    connection: sqlite3.Connection,
    node_id: str,
    limit: int,
    output_mode: str,
) -> JsonObject:
    row = connection.execute(
        """
        SELECT node_id, domain, entity_kind, canonical_label, payload_json,
        source_kind,
               source_ref, ingest_run_id
        FROM entity_nodes
        WHERE node_id = ?
          AND valid_to IS NULL
        LIMIT 1
        """,
        (node_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_found", "node_id": node_id}
    neighbors = connection.execute(
        """
        SELECT edge_id, domain, edge_kind, from_node_id, to_node_id,
        payload_json,
               source_kind, source_ref, ingest_run_id
        FROM entity_edges
        WHERE valid_to IS NULL
          AND (from_node_id = ? OR to_node_id = ?)
        ORDER BY edge_kind, edge_id
        LIMIT ?
        """,
        (node_id, node_id, limit),
    ).fetchall()
    return {
        "status": "ok",
        "node": _node_payload(row=row, output_mode=output_mode),
        "neighbor_edges": [
            _edge_payload(row=neighbor, output_mode="compact")
            for neighbor in neighbors
        ],
    }


def _edge_expansion(
    *,
    connection: sqlite3.Connection,
    edge_id: str,
    output_mode: str,
) -> JsonObject:
    row = connection.execute(
        """
        SELECT edges.edge_id, edges.domain, edges.edge_kind, edges.from_node_id,
               edges.to_node_id, edges.payload_json, edges.source_kind,
               edges.source_ref,
               edges.ingest_run_id, from_nodes.canonical_label AS from_label,
               to_nodes.canonical_label AS to_label
        FROM entity_edges AS edges
        LEFT JOIN entity_nodes AS from_nodes
          ON from_nodes.node_id = edges.from_node_id
         AND from_nodes.domain = edges.domain
         AND from_nodes.valid_to IS NULL
        LEFT JOIN entity_nodes AS to_nodes
          ON to_nodes.node_id = edges.to_node_id
         AND to_nodes.domain = edges.domain
         AND to_nodes.valid_to IS NULL
        WHERE edges.edge_id = ?
          AND edges.valid_to IS NULL
        LIMIT 1
        """,
        (edge_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_found", "edge_id": edge_id}
    return {
        "status": "ok",
        "edge": _edge_payload(row=row, output_mode=output_mode),
    }


def _unit_expansion(
    *,
    connection: sqlite3.Connection,
    unit_id: str,
    output_mode: str,
) -> JsonObject:
    row = connection.execute(
        """
        SELECT outputs.run_id, outputs.unit_id, outputs.output_json,
        outputs.source_ref,
               outputs.created_at_utc, units.unit_type, units.priority_band
        FROM catalog_unit_outputs AS outputs
        LEFT JOIN catalog_units AS units
          ON units.run_id = outputs.run_id
         AND units.unit_id = outputs.unit_id
        WHERE outputs.unit_id = ?
        ORDER BY outputs.created_at_utc DESC
        LIMIT 1
        """,
        (unit_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_found", "unit_id": unit_id}
    output_json = _json_object_from_text(str(row["output_json"]))
    return {
        "status": "ok",
        "unit_id": unit_id,
        "run_id": str(row["run_id"]),
        "unit_type": str(row["unit_type"]),
        "priority_band": str(row["priority_band"]),
        "source_ref": str(row["source_ref"]),
        "semantic_summary": str(output_json.get("semantic_summary", "")),
        "graph_node_count": _json_list_count(output_json.get("graph_nodes")),
        "graph_edge_count": _json_list_count(output_json.get("graph_edges")),
        "output_json": output_json
        if output_mode in {"full", "debug"}
        else None,
    }


def _node_payload(*, row: sqlite3.Row, output_mode: str) -> JsonObject:
    payload: JsonObject = {
        "kind": "catalog_graph_node",
        "node_id": str(row["node_id"]),
        "domain": str(row["domain"]),
        "entity_kind": str(row["entity_kind"]),
        "canonical_label": str(row["canonical_label"]),
        "source_kind": str(row["source_kind"]),
        "source_ref": str(row["source_ref"]),
    }
    if output_mode in {"full", "debug"}:
        payload["payload_json"] = _json_object_from_text(
            str(row["payload_json"])
        )
        payload["ingest_run_id"] = str(row["ingest_run_id"])
    return payload


def _edge_payload(*, row: sqlite3.Row, output_mode: str) -> JsonObject:
    payload: JsonObject = {
        "kind": "catalog_graph_edge",
        "edge_id": str(row["edge_id"]),
        "domain": str(row["domain"]),
        "edge_kind": str(row["edge_kind"]),
        "from_node_id": str(row["from_node_id"]),
        "to_node_id": str(row["to_node_id"]),
        "from_label": _nullable_text(row, "from_label"),
        "to_label": _nullable_text(row, "to_label"),
        "source_kind": str(row["source_kind"]),
        "source_ref": str(row["source_ref"]),
    }
    if output_mode in {"full", "debug"}:
        payload["payload_json"] = _json_object_from_text(
            str(row["payload_json"])
        )
        payload["ingest_run_id"] = str(row["ingest_run_id"])
    return payload


def _preview_unit_payload(
    *,
    unit_id: str,
    output_json: JsonObject,
    output_size_bytes: int,
    output_sha256: str,
) -> JsonObject:
    graph_nodes = _mapping_list(output_json.get("graph_nodes"))
    graph_edges = _mapping_list(output_json.get("graph_edges"))
    semantic_summary = str(output_json.get("semantic_summary", ""))
    return {
        "unit_id": unit_id,
        "output_sha256": output_sha256,
        "output_size_bytes": output_size_bytes,
        "semantic_summary": semantic_summary,
        "proposed_graph_nodes": graph_nodes,
        "proposed_graph_edges": graph_edges,
        "graph_node_count": len(graph_nodes),
        "graph_edge_count": len(graph_edges),
        "inferred_node_count": _inferred_count(graph_nodes),
        "inferred_edge_count": _inferred_count(graph_edges),
        "source_backed_node_count": _source_backed_count(graph_nodes),
        "source_backed_edge_count": _source_backed_count(graph_edges),
        "secret_marker_detected": bool(
            CATALOG_GRAPH_SECRET_MARKER_PATTERN.search(
                json.dumps(output_json, ensure_ascii=True, sort_keys=True)
            )
        ),
    }


def _graph_quality(
    *, unit: JsonObject, existing_node_ids: set[str]
) -> JsonObject:
    nodes = cast("list[JsonObject]", unit["proposed_graph_nodes"])
    edges = cast("list[JsonObject]", unit["proposed_graph_edges"])
    node_ids = [
        str(node.get("node_id", "")) for node in nodes if node.get("node_id")
    ]
    edge_ids = [
        str(edge.get("edge_id", "")) for edge in edges if edge.get("edge_id")
    ]
    known_node_ids = set(node_ids) | existing_node_ids
    disconnected_edges = [
        {
            "edge_id": str(edge.get("edge_id", "")),
            "from_node_id": str(edge.get("from_node_id", "")),
            "to_node_id": str(edge.get("to_node_id", "")),
        }
        for edge in edges
        if str(edge.get("from_node_id", "")) not in known_node_ids
        or str(edge.get("to_node_id", "")) not in known_node_ids
    ]
    duplicate_node_ids = sorted(_duplicates(node_ids))
    duplicate_edge_ids = sorted(_duplicates(edge_ids))
    findings: list[str] = []
    if not nodes:
        findings.append("empty_graph_nodes")
    if not edges:
        findings.append("empty_graph_edges")
    if disconnected_edges:
        findings.append("disconnected_edges")
    if duplicate_node_ids:
        findings.append("duplicate_node_ids")
    if duplicate_edge_ids:
        findings.append("duplicate_edge_ids")
    if unit["secret_marker_detected"]:
        findings.append("secret_marker_detected")
    return {
        "status": "ready" if not findings else "needs_revision",
        "findings": findings,
        "duplicate_node_ids": duplicate_node_ids,
        "duplicate_edge_ids": duplicate_edge_ids,
        "disconnected_edges": disconnected_edges[:10],
    }


def _existing_node_ids_for_preview(
    *,
    connection: sqlite3.Connection,
    units: Sequence[JsonObject],
) -> set[str]:
    requested = sorted(
        {
            str(edge.get("from_node_id", ""))
            for unit in units
            for edge in cast("list[JsonObject]", unit["proposed_graph_edges"])
            if edge.get("from_node_id")
        }
        | {
            str(edge.get("to_node_id", ""))
            for unit in units
            for edge in cast("list[JsonObject]", unit["proposed_graph_edges"])
            if edge.get("to_node_id")
        }
    )
    if not requested:
        return set()
    placeholders = ",".join("?" for _ in requested)
    rows = connection.execute(
        f"""  # noqa: S608
        SELECT node_id
        FROM entity_nodes
        WHERE valid_to IS NULL
          AND node_id IN ({placeholders})
        """,
        requested,
    ).fetchall()
    return {str(row["node_id"]) for row in rows}


def _preview_query_result(
    *,
    connection: sqlite3.Connection,
    query: str,
    units: Sequence[JsonObject],
    limit: int,
) -> JsonObject:
    terms = _search_terms(query)
    proposed_nodes = [
        node
        for unit in units
        for node in cast("list[JsonObject]", unit["proposed_graph_nodes"])
        if _mapping_matches_terms(node, terms)
    ][:limit]
    proposed_edges = [
        edge
        for unit in units
        for edge in cast("list[JsonObject]", unit["proposed_graph_edges"])
        if _mapping_matches_terms(edge, terms)
    ][:limit]
    return {
        "query": query,
        "terms": list(terms),
        "existing_nodes": _node_matches(
            connection=connection, terms=terms, limit=limit
        ),
        "existing_edges": _edge_matches(
            connection=connection, terms=terms, limit=limit
        ),
        "existing_semantic_outputs": _semantic_output_matches(
            connection=connection,
            terms=terms,
            limit=limit,
        ),
        "proposed_nodes": proposed_nodes,
        "proposed_edges": proposed_edges,
        "matched_any_proposed_graph": bool(proposed_nodes or proposed_edges),
    }


def _quality_findings(
    *,
    validated_units: Sequence[JsonObject],
    validation_errors: Sequence[JsonObject],
    search_preview: Sequence[JsonObject],
) -> list[JsonObject]:
    findings: list[JsonObject] = [
        {
            "kind": "validation_error",
            "unit_id": error.get("unit_id"),
            "detail": error["error"],
        }
        for error in validation_errors
    ]
    for unit in validated_units:
        graph_quality = cast("JsonObject", unit["graph_quality"])
        findings.extend(
            {
                "kind": finding,
                "unit_id": unit["unit_id"],
                "detail": "Revise proposed semantic graph before saving.",
            }
            for finding in cast("list[str]", graph_quality["findings"])
        )
    findings.extend(
        {
            "kind": "preview_query_miss",
            "query": preview["query"],
            "detail": (
                "No proposed graph node or edge matches this preview query."
            ),
        }
        for preview in search_preview
        if not preview["matched_any_proposed_graph"]
    )
    return findings


def _preview_aggregate(units: Sequence[JsonObject]) -> JsonObject:
    return {
        "graph_node_count": sum(
            _payload_int(unit["graph_node_count"]) for unit in units
        ),
        "graph_edge_count": sum(
            _payload_int(unit["graph_edge_count"]) for unit in units
        ),
        "inferred_node_count": sum(
            _payload_int(unit["inferred_node_count"]) for unit in units
        ),
        "inferred_edge_count": sum(
            _payload_int(unit["inferred_edge_count"]) for unit in units
        ),
        "source_backed_node_count": sum(
            _payload_int(unit["source_backed_node_count"]) for unit in units
        ),
        "source_backed_edge_count": sum(
            _payload_int(unit["source_backed_edge_count"]) for unit in units
        ),
    }


def _preview_raw_units(
    arguments: Mapping[str, object],
) -> list[Mapping[str, object]]:
    answers_json = arguments.get("answers_json")
    if answers_json is not None:
        payload = _mapping_argument(answers_json, field_name="answers_json")
        raw_units = payload.get("units")
        if not isinstance(raw_units, list):
            message = "answers_json.units must be an array."
            raise ValueError(message)
        unit_items = cast("list[object]", raw_units)
        return [
            _mapping_argument(item, field_name="answers_json.units")
            for item in unit_items
        ]
    answer_json = arguments.get("answer_json")
    if answer_json is not None:
        unit_id = _optional_text(arguments.get("unit_id"))
        payload = dict(_mapping_argument(answer_json, field_name="answer_json"))
        if unit_id is not None:
            _ = payload.setdefault("unit_id", unit_id)
        return [payload]
    return []


def _preview_queries(arguments: Mapping[str, object]) -> list[str]:
    queries: list[str] = []
    query = _optional_text(arguments.get("query"))
    if query is not None:
        queries.append(query)
    preview_queries = arguments.get("preview_queries")
    if preview_queries is not None:
        payload = _mapping_argument(
            preview_queries, field_name="preview_queries"
        )
        raw_queries = payload.get("queries")
        if not isinstance(raw_queries, list):
            message = "preview_queries.queries must be an array."
            raise ValueError(message)
        query_items = cast("list[object]", raw_queries)
        queries.extend(
            str(item).strip() for item in query_items if str(item).strip()
        )
    return list(dict.fromkeys(queries))[:8]


def _bounded_units(
    units: Sequence[JsonObject], *, output_mode: str
) -> list[JsonObject]:
    if output_mode in {"full", "debug"}:
        return list(units)
    bounded: list[JsonObject] = []
    for unit in units:
        graph_quality = cast("JsonObject", unit["graph_quality"])
        bounded.append(
            {
                "unit_id": unit["unit_id"],
                "semantic_summary": _snippet(str(unit["semantic_summary"])),
                "graph_node_count": unit["graph_node_count"],
                "graph_edge_count": unit["graph_edge_count"],
                "inferred_node_count": unit["inferred_node_count"],
                "inferred_edge_count": unit["inferred_edge_count"],
                "graph_quality": graph_quality,
            }
        )
    return bounded


def _matching_rows(
    *,
    rows: Sequence[sqlite3.Row],
    terms: Sequence[str],
    limit: int,
) -> list[sqlite3.Row]:
    matched: list[sqlite3.Row] = []
    for row in rows:
        if _values_match_terms(values=tuple(row), terms=terms):
            matched.append(row)
        if len(matched) >= limit:
            break
    return matched


def _values_match_terms(
    *, values: Sequence[object], terms: Sequence[str]
) -> bool:
    haystack = " ".join(
        str(value) for value in values if value is not None
    ).casefold()
    return any(term in haystack for term in terms)


def _mapping_matches_terms(
    value: Mapping[str, object], terms: Sequence[str]
) -> bool:
    haystack = json.dumps(value, ensure_ascii=True, sort_keys=True).casefold()
    return any(term in haystack for term in terms)


def _mapping_list(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [
        {
            str(key): item_value
            for key, item_value in cast("Mapping[object, object]", item).items()
        }
        for item in items
        if isinstance(item, dict)
    ]


def _json_object_from_text(value: str) -> JsonObject:
    try:
        parsed = cast("object", json.loads(value))
    except json.JSONDecodeError:
        return {"raw_text": _snippet(value)}
    if isinstance(parsed, dict):
        parsed_mapping = cast("Mapping[object, object]", parsed)
        return {str(key): item for key, item in parsed_mapping.items()}
    return {"value": parsed}


def _search_terms(query: str) -> tuple[str, ...]:
    if not query.strip():
        return ()
    tokens = cast("list[str]", CATALOG_GRAPH_TEXT_PATTERN.findall(query))
    terms = [
        token.casefold()
        for token in tokens
        if len(token) >= CATALOG_GRAPH_MIN_TERM_LENGTH
    ]
    return tuple(dict.fromkeys(terms))


def _optional_limit(value: object) -> int:
    if value is None:
        return CATALOG_GRAPH_DEFAULT_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        message = "limit must be an integer."
        raise TypeError(message)
    return max(1, min(value, CATALOG_GRAPH_MAX_LIMIT))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "text arguments must be strings."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _optional_output_mode(value: object) -> str:
    if value is None:
        return "compact"
    if not isinstance(value, str):
        message = "output_mode must be a string."
        raise TypeError(message)
    output_mode = value.strip().casefold()
    if output_mode not in CATALOG_GRAPH_OUTPUT_MODES:
        allowed = ", ".join(sorted(CATALOG_GRAPH_OUTPUT_MODES))
        message = (
            f"Unsupported output_mode {output_mode!r}; expected {allowed}."
        )
        raise ValueError(message)
    return output_mode


def _mapping_argument(
    value: object, *, field_name: str
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        message = f"{field_name} must be a JSON object."
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", value).items()
    }


def _safe_unit_id(raw_unit: Mapping[str, object]) -> str | None:
    value = raw_unit.get("unit_id")
    return value if isinstance(value, str) else None


def _nullable_text(row: sqlite3.Row, key: str) -> str | None:
    value = dict(row).get(key)
    return None if value is None else str(value)


def _snippet(value: str, *, limit: int = 240) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _json_list_count(value: object) -> int:
    return len(cast("list[object]", value)) if isinstance(value, list) else 0


def _payload_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _inferred_count(rows: Iterable[Mapping[str, object]]) -> int:
    return sum(
        1
        for row in rows
        if "inferred"
        in json.dumps(row, ensure_ascii=True, sort_keys=True).casefold()
    )


def _source_backed_count(rows: Iterable[Mapping[str, object]]) -> int:
    markers = (
        "source_backed ",
        "raw_spec_evidence ",
        "source-backed ",
        "source backed",
    )
    return sum(
        1
        for row in rows
        if any(
            marker
            in json.dumps(row, ensure_ascii=True, sort_keys=True).casefold()
            for marker in markers
        )
    )


def _duplicates(values: Sequence[str]) -> set[str]:
    counts = Counter(value for value in values if value)
    return {value for value, count in counts.items() if count > 1}
