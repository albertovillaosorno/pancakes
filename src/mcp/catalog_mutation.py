# ruff: noqa: PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Typed MCP mutation tools for catalog intelligence state.

Boundary contract:
- Owns: typed local catalog mutation receipts for units, nodes, edges, and
reviews.
- Must not: expose raw SQL, author semantic answers, call providers, or touch
live Make state.
- Allows: local SQLite writes through fixed operations with durable audit
events.
- Split when: graph proposal workflow or review backlog becomes an independent
service.
- Merge when: another MCP module owns the same typed catalog mutation tool
surface.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast

from catalog.knowledge import (
    CATALOG_UNIT_NOTE_SURFACES,
    DEFAULT_KNOWLEDGE_DB_PATH,
)
from catalog.knowledge.catalog_plan_ssot import connect_catalog_plan_ssot
from catalog.value_index import (
    require_catalog_graph_edge_kind_canonical,
    require_catalog_graph_entity_kind_canonical,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping
    from pathlib import Path

    from mcp.models import JsonObject

CATALOG_MUTATION_SOURCE_KIND: Final = "mcp_catalog_mutation"
CATALOG_MUTATION_INGEST_RUN_ID: Final = "mcp_catalog_mutation"
MAX_TEXT_ARGUMENT_CHARS: Final = 2_000
MAX_PAYLOAD_JSON_BYTES: Final = 262_144
DEFAULT_WORKER_ID: Final = "mcp-catalog-tool"
TEXT_ARGUMENT_ALLOWED_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/@ "
)
CATALOG_MODIFY_TOOL_NAME: Final = "catalog.modify"
CATALOG_NODE_MODIFY_TOOL_NAME: Final = "catalog.node.modify"
CATALOG_EDGE_PROPOSE_TOOL_NAME: Final = "catalog.edge.propose"
CATALOG_EDGE_APPLY_TOOL_NAME: Final = "catalog.edge.apply"
CATALOG_REVIEW_ADD_TOOL_NAME: Final = "catalog.review.add"


def catalog_modify(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Apply one typed catalog unit or proposal mutation without raw SQL.

    Returns:
        A local SQLite mutation receipt.
    """
    operation = _required_text(arguments, "operation")
    worker_id = _worker_id(arguments)
    dry_run = _optional_bool(arguments.get("dry_run"))

    observed_at_utc = _utc_now()
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        if dry_run:
            return _catalog_modify_dry_run_payload(
                connection=connection,
                arguments=arguments,
                operation=operation,
                worker_id=worker_id,
            )
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            receipt = _apply_catalog_modify(
                connection=connection,
                arguments=arguments,
                operation=operation,
                worker_id=worker_id,
                observed_at_utc=observed_at_utc,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return receipt


def catalog_node_modify(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Upsert one typed graph node projection without exposing raw SQL.

    Returns:
        A local SQLite node mutation receipt.
    """
    worker_id = _worker_id(arguments)
    node_id = _required_text(arguments, "node_id")
    domain = _required_text(arguments, "domain")
    entity_kind = _required_text(arguments, "entity_kind")
    require_catalog_graph_entity_kind_canonical(entity_kind)
    canonical_label = _required_text(arguments, "canonical_label")
    payload_text = _canonical_json_text(
        _json_object_argument(arguments.get("payload_json"))
    )
    source_kind = (
        _optional_text(arguments.get("source_kind"))
        or CATALOG_MUTATION_SOURCE_KIND
    )
    source_ref = _optional_text(arguments.get("source_ref")) or (
        f"mcp:{CATALOG_NODE_MODIFY_TOOL_NAME}/{node_id}"
    )
    if _optional_bool(arguments.get("dry_run")):
        return _dry_run_payload(
            tool_name=CATALOG_NODE_MODIFY_TOOL_NAME,
            operation="upsert_node",
            worker_id=worker_id,
            target_id=node_id,
        )

    observed_at_utc = _utc_now()
    fingerprint = _stable_id(
        "catalog-node", node_id, domain, entity_kind, payload_text
    )
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            _ = connection.execute(
                """
                UPDATE entity_nodes
                SET valid_to = ?
                WHERE node_id = ?
                  AND domain = ?
                  AND valid_to IS NULL
                """,
                (observed_at_utc, node_id, domain),
            )
            _ = connection.execute(
                """
                INSERT INTO entity_nodes (
                  node_id, domain, entity_kind, canonical_label, payload_json,
                  source_kind,
                  source_ref, valid_from, valid_to, fingerprint, ingest_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    node_id,
                    domain,
                    entity_kind,
                    canonical_label,
                    payload_text,
                    source_kind,
                    source_ref,
                    observed_at_utc,
                    fingerprint,
                    CATALOG_MUTATION_INGEST_RUN_ID,
                ),
            )
            _log_event(
                connection=connection,
                tool_name=CATALOG_NODE_MODIFY_TOOL_NAME,
                operation="upsert_node",
                target_kind="entity_node",
                target_id=node_id,
                payload={
                    "domain": domain,
                    "entity_kind": entity_kind,
                    "source_ref": source_ref,
                },
                worker_id=worker_id,
                observed_at_utc=observed_at_utc,
                source_ref=source_ref,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return _write_receipt(
        tool_name=CATALOG_NODE_MODIFY_TOOL_NAME,
        operation="upsert_node",
        worker_id=worker_id,
        target_id=node_id,
        write_actions=[
            "upsert_entity_node ",
            "record_catalog_modification_event",
        ],
        extra={"domain": domain, "entity_kind": entity_kind},
    )


def catalog_edge_propose(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Create or replace one typed graph edge proposal.

    Returns:
        A local SQLite edge-proposal receipt.
    """
    worker_id = _worker_id(arguments)
    domain = _required_text(arguments, "domain")
    edge_kind = _required_text(arguments, "edge_kind")
    require_catalog_graph_edge_kind_canonical(edge_kind)
    from_node_id = _required_text(arguments, "from_node_id")
    to_node_id = _required_text(arguments, "to_node_id")
    payload_text = _canonical_json_text(
        _json_object_argument(arguments.get("payload_json"))
    )
    rationale = _required_text(arguments, "rationale")
    proposal_id = _optional_text(arguments.get("proposal_id")) or _stable_id(
        "catalog-edge-proposal",
        domain,
        edge_kind,
        from_node_id,
        to_node_id,
        payload_text,
    )
    source_kind = (
        _optional_text(arguments.get("source_kind"))
        or CATALOG_MUTATION_SOURCE_KIND
    )
    source_ref = _optional_text(arguments.get("source_ref")) or (
        f"mcp:{CATALOG_EDGE_PROPOSE_TOOL_NAME}/{proposal_id}"
    )
    if _optional_bool(arguments.get("dry_run")):
        return _dry_run_payload(
            tool_name=CATALOG_EDGE_PROPOSE_TOOL_NAME,
            operation="propose_edge",
            worker_id=worker_id,
            target_id=proposal_id,
        )

    observed_at_utc = _utc_now()
    fingerprint = _stable_id(
        "catalog-edge-proposal", proposal_id, payload_text, rationale
    )
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            _ = connection.execute(
                """
                INSERT OR REPLACE INTO catalog_edge_proposals (
                  proposal_id, domain, edge_kind, from_node_id, to_node_id,
                  payload_json,
                  rationale, proposal_status, proposed_by, applied_edge_id,
                  created_at_utc,
                  applied_at_utc, source_kind, source_ref, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, NULL, ?, NULL, ?,
                ?, ?)
                """,
                (
                    proposal_id,
                    domain,
                    edge_kind,
                    from_node_id,
                    to_node_id,
                    payload_text,
                    rationale,
                    worker_id,
                    observed_at_utc,
                    source_kind,
                    source_ref,
                    fingerprint,
                ),
            )
            _log_event(
                connection=connection,
                tool_name=CATALOG_EDGE_PROPOSE_TOOL_NAME,
                operation="propose_edge",
                target_kind="catalog_edge_proposal",
                target_id=proposal_id,
                payload={
                    "domain": domain,
                    "edge_kind": edge_kind,
                    "from_node_id": from_node_id,
                    "to_node_id": to_node_id,
                },
                worker_id=worker_id,
                observed_at_utc=observed_at_utc,
                source_ref=source_ref,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return _write_receipt(
        tool_name=CATALOG_EDGE_PROPOSE_TOOL_NAME,
        operation="propose_edge",
        worker_id=worker_id,
        target_id=proposal_id,
        write_actions=[
            "write_catalog_edge_proposal ",
            "record_catalog_modification_event",
        ],
        extra={"proposal_status": "proposed"},
    )


def catalog_edge_apply(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Apply one approved edge proposal into the typed graph projection.

    Returns:
        A local SQLite graph-edge mutation receipt.
    """
    worker_id = _worker_id(arguments)
    proposal_id = _required_text(arguments, "proposal_id")
    edge_id = _optional_text(arguments.get("edge_id"))
    dry_run = _optional_bool(arguments.get("dry_run"))

    observed_at_utc = _utc_now()
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        if dry_run:
            return _edge_apply_dry_run_payload(
                connection=connection,
                worker_id=worker_id,
                proposal_id=proposal_id,
                edge_id=edge_id,
            )
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            proposal = _approved_edge_proposal(
                connection=connection, proposal_id=proposal_id
            )
            require_catalog_graph_edge_kind_canonical(
                _row_text(proposal, "edge_kind")
            )
            actual_edge_id = _edge_id_for_proposal(
                proposal=proposal,
                edge_id=edge_id,
            )
            fingerprint = _stable_id(
                "catalog-edge",
                actual_edge_id,
                _row_text(proposal, "payload_json"),
            )
            _ = connection.execute(
                """
                UPDATE entity_edges
                SET valid_to = ?
                WHERE edge_id = ?
                  AND domain = ?
                  AND valid_to IS NULL
                """,
                (
                    observed_at_utc,
                    actual_edge_id,
                    _row_text(proposal, "domain"),
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO entity_edges (
                  edge_id, domain, edge_kind, from_node_id, to_node_id,
                  payload_json,
                  source_kind, source_ref, valid_from, valid_to, fingerprint,
                  ingest_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    actual_edge_id,
                    _row_text(proposal, "domain"),
                    _row_text(proposal, "edge_kind"),
                    _row_text(proposal, "from_node_id"),
                    _row_text(proposal, "to_node_id"),
                    _row_text(proposal, "payload_json"),
                    CATALOG_MUTATION_SOURCE_KIND,
                    f"sqlite:catalog_edge_proposals/{proposal_id}",
                    observed_at_utc,
                    fingerprint,
                    CATALOG_MUTATION_INGEST_RUN_ID,
                ),
            )
            _ = connection.execute(
                """
                UPDATE catalog_edge_proposals
                SET proposal_status = 'applied',
                    applied_edge_id = ?,
                    applied_at_utc = ?
                WHERE proposal_id = ?
                """,
                (actual_edge_id, observed_at_utc, proposal_id),
            )
            _log_event(
                connection=connection,
                tool_name=CATALOG_EDGE_APPLY_TOOL_NAME,
                operation="apply_edge",
                target_kind="entity_edge",
                target_id=actual_edge_id,
                payload={"proposal_id": proposal_id},
                worker_id=worker_id,
                observed_at_utc=observed_at_utc,
                source_ref=f"sqlite:catalog_edge_proposals/{proposal_id}",
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return _write_receipt(
        tool_name=CATALOG_EDGE_APPLY_TOOL_NAME,
        operation="apply_edge",
        worker_id=worker_id,
        target_id=actual_edge_id,
        write_actions=[
            "apply_entity_edge ",
            "record_catalog_modification_event",
        ],
        extra={"proposal_id": proposal_id, "proposal_status": "applied"},
    )


def _catalog_modify_dry_run_payload(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    operation: str,
    worker_id: str,
) -> JsonObject:
    target_id = _catalog_modify_dry_run_target(
        connection=connection,
        arguments=arguments,
        operation=operation,
    )
    payload = _dry_run_payload(
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation=operation,
        worker_id=worker_id,
        target_id=target_id,
    )
    payload.update(
        {
            "validation_status": "validated_without_write",
            "would_change": True,
            "permission_posture": "local_sqlite_dry_run_no_write",
        }
    )
    return payload


def _catalog_modify_dry_run_target(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    operation: str,
) -> str:
    if operation == "update_unit_note":
        run_id = _required_text(arguments, "run_id")
        unit_id = _required_text(arguments, "unit_id")
        note_surface = _required_text(arguments, "note_surface")
        if note_surface not in CATALOG_UNIT_NOTE_SURFACES:
            allowed = ", ".join(CATALOG_UNIT_NOTE_SURFACES)
            message = (
                f"Unknown note_surface {note_surface!r}; expected one of:"
                f"{allowed}."
            )
            raise ValueError(message)
        _ = _required_text(arguments, "note_text")
        _assert_catalog_unit(
            connection=connection, run_id=run_id, unit_id=unit_id
        )
        return f"{run_id}/{unit_id}/{note_surface}"
    if operation == "update_unit_status":
        run_id = _required_text(arguments, "run_id")
        unit_id = _required_text(arguments, "unit_id")
        if (
            _optional_text(arguments.get("status")) is None
            and _optional_text(arguments.get("validation_status")) is None
            and _optional_text(arguments.get("coverage_status")) is None
        ):
            message = (
                "update_unit_status requires status, validation_status, or "
                "coverage_status."
            )
            raise ValueError(message)
        _assert_catalog_unit(
            connection=connection, run_id=run_id, unit_id=unit_id
        )
        return f"{run_id}/{unit_id}"
    if operation in {"approve_edge_proposal", "reject_edge_proposal"}:
        proposal_id = _required_text(arguments, "proposal_id")
        _assert_edge_proposal(connection=connection, proposal_id=proposal_id)
        return proposal_id
    message = (
        "catalog.modify operation must be update_unit_note, "
        "update_unit_status, "
        ""
        "approve_edge_proposal, or reject_edge_proposal."
    )
    raise ValueError(message)


def _edge_apply_dry_run_payload(
    *,
    connection: sqlite3.Connection,
    worker_id: str,
    proposal_id: str,
    edge_id: str | None,
) -> JsonObject:
    proposal = _edge_proposal(connection=connection, proposal_id=proposal_id)
    payload = _dry_run_payload(
        tool_name=CATALOG_EDGE_APPLY_TOOL_NAME,
        operation="apply_edge",
        worker_id=worker_id,
        target_id=proposal_id,
    )
    if proposal is None:
        payload.update(
            {
                "status": "proposal_not_found",
                "proposal_id": proposal_id,
                "validation_status": "missing_proposal",
                "would_change": False,
            }
        )
        return payload
    proposal_status = _row_text(proposal, "proposal_status")
    payload["proposal_id"] = proposal_id
    payload["proposal_status"] = proposal_status
    if proposal_status != "approved":
        payload.update(
            {
                "status": "proposal_not_approved ",
                "validation_status": "proposal_status_not_approved",
                "would_change": False,
            }
        )
        return payload
    require_catalog_graph_edge_kind_canonical(_row_text(proposal, "edge_kind"))
    actual_edge_id = _edge_id_for_proposal(proposal=proposal, edge_id=edge_id)
    payload.update(
        {
            "status": "dry_run ",
            "validation_status": "approved_proposal",
            "would_change": True,
            "edge_id": actual_edge_id,
            "source_ref": f"sqlite:catalog_edge_proposals/{proposal_id}",
        }
    )
    return payload


def _edge_id_for_proposal(*, proposal: sqlite3.Row, edge_id: str | None) -> str:
    if edge_id is not None:
        return edge_id
    return _stable_id(
        "catalog-edge",
        _row_text(proposal, "domain"),
        _row_text(proposal, "edge_kind"),
        _row_text(proposal, "from_node_id"),
        _row_text(proposal, "to_node_id"),
        _row_text(proposal, "payload_json"),
    )


def catalog_review_add(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Add one typed catalog review/backlog record without raw SQL mutation.

    access.

    Returns:
        A local SQLite catalog review receipt.
    """
    worker_id = _worker_id(arguments)
    domain = _required_text(arguments, "domain")
    target_kind = _required_text(arguments, "target_kind")
    target_id = _required_text(arguments, "target_id")
    review_status = _optional_text(arguments.get("review_status")) or "open"
    priority = _optional_int(arguments.get("priority"), default=100)
    payload_text = _canonical_json_text(
        _json_object_argument(arguments.get("payload_json"))
    )
    review_id = _optional_text(arguments.get("review_id")) or _stable_id(
        "catalog-review",
        domain,
        target_kind,
        target_id,
        payload_text,
    )
    source_kind = (
        _optional_text(arguments.get("source_kind"))
        or CATALOG_MUTATION_SOURCE_KIND
    )
    source_ref = _optional_text(arguments.get("source_ref")) or (
        f"mcp:{CATALOG_REVIEW_ADD_TOOL_NAME}/{review_id}"
    )
    if _optional_bool(arguments.get("dry_run")):
        payload = _dry_run_payload(
            tool_name=CATALOG_REVIEW_ADD_TOOL_NAME,
            operation="add_review",
            worker_id=worker_id,
            target_id=review_id,
        )
        payload.update(
            {
                "would_change": True,
                "review_status": review_status,
                "priority": priority,
                "permission_posture": "local_sqlite_dry_run_no_write",
            }
        )
        return payload

    observed_at_utc = _utc_now()
    fingerprint = _stable_id(
        "catalog-review", review_id, review_status, payload_text
    )
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            _ = connection.execute(
                """
                INSERT OR REPLACE INTO catalog_review_records (
                  review_id, domain, target_kind, target_id, review_status,
                  priority,
                  payload_json, source_kind, source_ref, created_at_utc,
                  updated_at_utc,
                  fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    domain,
                    target_kind,
                    target_id,
                    review_status,
                    priority,
                    payload_text,
                    source_kind,
                    source_ref,
                    observed_at_utc,
                    observed_at_utc,
                    fingerprint,
                ),
            )
            _log_event(
                connection=connection,
                tool_name=CATALOG_REVIEW_ADD_TOOL_NAME,
                operation="add_review",
                target_kind="catalog_review_record",
                target_id=review_id,
                payload={
                    "domain": domain,
                    "target_kind": target_kind,
                    "target_id": target_id,
                },
                worker_id=worker_id,
                observed_at_utc=observed_at_utc,
                source_ref=source_ref,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return _write_receipt(
        tool_name=CATALOG_REVIEW_ADD_TOOL_NAME,
        operation="add_review",
        worker_id=worker_id,
        target_id=review_id,
        write_actions=[
            "write_catalog_review_record ",
            "record_catalog_modification_event",
        ],
        extra={"review_status": review_status, "priority": priority},
    )


def _apply_catalog_modify(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    operation: str,
    worker_id: str,
    observed_at_utc: str,
) -> JsonObject:
    if operation == "update_unit_note":
        return _update_unit_note(
            connection=connection,
            arguments=arguments,
            worker_id=worker_id,
            observed_at_utc=observed_at_utc,
        )
    if operation == "update_unit_status":
        return _update_unit_status(
            connection=connection,
            arguments=arguments,
            worker_id=worker_id,
            observed_at_utc=observed_at_utc,
        )
    if operation == "approve_edge_proposal":
        return _set_edge_proposal_status(
            connection=connection,
            arguments=arguments,
            worker_id=worker_id,
            observed_at_utc=observed_at_utc,
            proposal_status="approved",
        )
    if operation == "reject_edge_proposal":
        return _set_edge_proposal_status(
            connection=connection,
            arguments=arguments,
            worker_id=worker_id,
            observed_at_utc=observed_at_utc,
            proposal_status="rejected",
        )
    message = (
        "catalog.modify operation must be update_unit_note, "
        "update_unit_status, "
        ""
        "approve_edge_proposal, or reject_edge_proposal."
    )
    raise ValueError(message)


def _update_unit_note(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    worker_id: str,
    observed_at_utc: str,
) -> JsonObject:
    run_id = _required_text(arguments, "run_id")
    unit_id = _required_text(arguments, "unit_id")
    note_surface = _required_text(arguments, "note_surface")
    if note_surface not in CATALOG_UNIT_NOTE_SURFACES:
        allowed = ", ".join(CATALOG_UNIT_NOTE_SURFACES)
        message = (
            f"Unknown note_surface {note_surface!r}; expected one of:{allowed}."
        )
        raise ValueError(message)
    note_text = _required_text(arguments, "note_text")
    _assert_catalog_unit(connection=connection, run_id=run_id, unit_id=unit_id)
    _ = connection.execute(
        """
        INSERT INTO catalog_unit_notes (
          run_id, unit_id, note_surface, note_text, note_status, updated_at_utc
        ) VALUES (?, ?, ?, ?, 'present', ?)
        ON CONFLICT(run_id, unit_id, note_surface) DO UPDATE SET
          note_text = excluded.note_text,
          note_status = excluded.note_status,
          updated_at_utc = excluded.updated_at_utc
        """,
        (run_id, unit_id, note_surface, note_text, observed_at_utc),
    )
    _log_event(
        connection=connection,
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation="update_unit_note",
        target_kind="catalog_unit_note",
        target_id=f"{run_id}/{unit_id}/{note_surface}",
        payload={
            "run_id": run_id,
            "unit_id": unit_id,
            "note_surface": note_surface,
        },
        worker_id=worker_id,
        observed_at_utc=observed_at_utc,
        source_ref=f"sqlite:catalog_unit_notes/{run_id}/{unit_id}/{note_surface}",
    )
    return _write_receipt(
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation="update_unit_note",
        worker_id=worker_id,
        target_id=f"{run_id}/{unit_id}/{note_surface}",
        write_actions=[
            "update_catalog_unit_note ",
            "record_catalog_modification_event",
        ],
        extra={
            "run_id": run_id,
            "unit_id": unit_id,
            "note_surface": note_surface,
        },
    )


def _update_unit_status(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    worker_id: str,
    observed_at_utc: str,
) -> JsonObject:
    run_id = _required_text(arguments, "run_id")
    unit_id = _required_text(arguments, "unit_id")
    status = _optional_text(arguments.get("status"))
    validation_status = _optional_text(arguments.get("validation_status"))
    coverage_status = _optional_text(arguments.get("coverage_status"))
    if status is None and validation_status is None and coverage_status is None:
        message = (
            "update_unit_status requires status, validation_status, or "
            "coverage_status."
        )
        raise ValueError(message)
    _assert_catalog_unit(connection=connection, run_id=run_id, unit_id=unit_id)
    _ = connection.execute(
        """
        UPDATE catalog_units
        SET status = COALESCE(?, status),
            validation_status = COALESCE(?, validation_status),
            coverage_status = COALESCE(?, coverage_status),
            updated_at_utc = ?
        WHERE run_id = ?
          AND unit_id = ?
        """,
        (
            status,
            validation_status,
            coverage_status,
            observed_at_utc,
            run_id,
            unit_id,
        ),
    )
    _log_event(
        connection=connection,
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation="update_unit_status",
        target_kind="catalog_unit",
        target_id=f"{run_id}/{unit_id}",
        payload={
            "run_id": run_id,
            "unit_id": unit_id,
            "status": status,
            "validation_status": validation_status,
            "coverage_status": coverage_status,
        },
        worker_id=worker_id,
        observed_at_utc=observed_at_utc,
        source_ref=f"sqlite:catalog_units/{run_id}/{unit_id}",
    )
    return _write_receipt(
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation="update_unit_status",
        worker_id=worker_id,
        target_id=f"{run_id}/{unit_id}",
        write_actions=[
            "update_catalog_unit_status ",
            "record_catalog_modification_event",
        ],
        extra={"run_id": run_id, "unit_id": unit_id},
    )


def _set_edge_proposal_status(
    *,
    connection: sqlite3.Connection,
    arguments: Mapping[str, object],
    worker_id: str,
    observed_at_utc: str,
    proposal_status: str,
) -> JsonObject:
    proposal_id = _required_text(arguments, "proposal_id")
    _assert_edge_proposal(connection=connection, proposal_id=proposal_id)
    _ = connection.execute(
        """
        UPDATE catalog_edge_proposals
        SET proposal_status = ?
        WHERE proposal_id = ?
        """,
        (proposal_status, proposal_id),
    )
    _log_event(
        connection=connection,
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation=f"{proposal_status}_edge_proposal",
        target_kind="catalog_edge_proposal",
        target_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "proposal_status": proposal_status,
        },
        worker_id=worker_id,
        observed_at_utc=observed_at_utc,
        source_ref=f"sqlite:catalog_edge_proposals/{proposal_id}",
    )
    return _write_receipt(
        tool_name=CATALOG_MODIFY_TOOL_NAME,
        operation=f"{proposal_status}_edge_proposal",
        worker_id=worker_id,
        target_id=proposal_id,
        write_actions=[
            "update_catalog_edge_proposal_status ",
            "record_catalog_modification_event",
        ],
        extra={"proposal_status": proposal_status},
    )


def _approved_edge_proposal(
    *,
    connection: sqlite3.Connection,
    proposal_id: str,
) -> sqlite3.Row:
    proposal = _edge_proposal(connection=connection, proposal_id=proposal_id)
    if proposal is None:
        message = f"Unknown catalog edge proposal: {proposal_id}"
        raise ValueError(message)
    if _row_text(proposal, "proposal_status") != "approved":
        message = "catalog.edge.apply requires an approved edge proposal."
        raise ValueError(message)
    return proposal


def _edge_proposal(
    *, connection: sqlite3.Connection, proposal_id: str
) -> sqlite3.Row | None:
    row = connection.execute(
        """
        SELECT
          proposal_id,
          domain,
          edge_kind,
          from_node_id,
          to_node_id,
          payload_json,
          proposal_status
        FROM catalog_edge_proposals
        WHERE proposal_id = ?
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    return None if row is None else cast("sqlite3.Row", row)


def _assert_catalog_unit(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    unit_id: str,
) -> None:
    row = connection.execute(
        """
        SELECT unit_id
        FROM catalog_units
        WHERE run_id = ?
          AND unit_id = ?
        LIMIT 1
        """,
        (run_id, unit_id),
    ).fetchone()
    if row is None:
        message = f"Unknown catalog unit: {run_id}/{unit_id}"
        raise ValueError(message)


def _assert_edge_proposal(
    *, connection: sqlite3.Connection, proposal_id: str
) -> None:
    row = connection.execute(
        """
        SELECT proposal_id
        FROM catalog_edge_proposals
        WHERE proposal_id = ?
        LIMIT 1
        """,
        (proposal_id,),
    ).fetchone()
    if row is None:
        message = f"Unknown catalog edge proposal: {proposal_id}"
        raise ValueError(message)


def _log_event(
    *,
    connection: sqlite3.Connection,
    tool_name: str,
    operation: str,
    target_kind: str,
    target_id: str,
    payload: Mapping[str, object],
    worker_id: str,
    observed_at_utc: str,
    source_ref: str,
) -> None:
    payload_text = _canonical_json_text(payload)
    event_id = _stable_id(
        tool_name, operation, target_kind, target_id, observed_at_utc
    )
    fingerprint = _stable_id(
        "catalog-modification-event", event_id, payload_text
    )
    _ = connection.execute(
        """
        INSERT INTO catalog_modification_events (
          event_id, tool_name, operation, target_kind, target_id, payload_json,
          worker_id,
          created_at_utc, source_kind, source_ref, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            tool_name,
            operation,
            target_kind,
            target_id,
            payload_text,
            worker_id,
            observed_at_utc,
            CATALOG_MUTATION_SOURCE_KIND,
            source_ref,
            fingerprint,
        ),
    )


def _write_receipt(
    *,
    tool_name: str,
    operation: str,
    worker_id: str,
    target_id: str,
    write_actions: list[str],
    extra: Mapping[str, object] | None = None,
) -> JsonObject:
    payload: JsonObject = {
        "status": "saved",
        "response_kind": tool_name.replace(".", "_"),
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_ssot": True,
        "operation": operation,
        "worker_id": worker_id,
        "target_id": target_id,
        "cursor_advanced": False,
        "writes_performed": True,
        "write_actions": write_actions,
        "raw_sql_agent_mutation": False,
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }
    if extra is not None:
        payload.update(dict(extra))
    return payload


def _dry_run_payload(
    *,
    tool_name: str,
    operation: str,
    worker_id: str,
    target_id: str | None = None,
) -> JsonObject:
    return {
        "status": "dry_run",
        "response_kind": tool_name.replace(".", "_"),
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_ssot": True,
        "operation": operation,
        "worker_id": worker_id,
        "target_id": target_id,
        "cursor_advanced": False,
        "writes_performed": False,
        "write_actions": [],
        "raw_sql_agent_mutation": False,
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _worker_id(arguments: Mapping[str, object]) -> str:
    worker_id = _optional_text(arguments.get("worker_id")) or DEFAULT_WORKER_ID
    if any(char not in TEXT_ARGUMENT_ALLOWED_CHARS for char in worker_id):
        message = "worker_id contains unsupported characters."
        raise ValueError(message)
    return worker_id


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    text = _optional_text(arguments.get(key))
    if text is None:
        message = f"{key} is required."
        raise ValueError(message)
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Text arguments must be strings."
        raise TypeError(message)
    text = " ".join(value.split())
    if len(text) > MAX_TEXT_ARGUMENT_CHARS:
        message = "Text argument is too long."
        raise ValueError(message)
    return text or None


def _optional_bool(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        message = "Boolean arguments must be true or false."
        raise TypeError(message)
    return value


def _optional_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        message = "Integer arguments must be numbers."
        raise TypeError(message)
    return value


def _json_object_argument(value: object) -> JsonObject:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {
            str(key): item
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if not isinstance(value, str) or not value.strip():
        message = "JSON object arguments must be objects or encoded objects."
        raise ValueError(message)
    parsed = cast("object", json.loads(value))
    if not isinstance(parsed, dict):
        message = "JSON object argument must decode to an object."
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", parsed).items()
    }


def _canonical_json_text(value: Mapping[str, object]) -> str:
    text = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    if len(text.encode("utf-8")) > MAX_PAYLOAD_JSON_BYTES:
        message = (
            f"Catalog mutation payloads are capped at {MAX_PAYLOAD_JSON_BYTES}"
            f"bytes."
        )
        raise ValueError(message)
    return text


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = cast("object", row[key])
    return "" if value is None else str(value)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    return _sha256_text(payload)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
