# ruff: noqa: E501
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

"""Read-only MCP access to canonical catalog indexes.

Boundary contract:
- Owns: direct MCP lookup for placeholder and finite catalog value indexes.
- Must not: search raw provider payloads, mutate SQLite, lease work, or save
catalog answers.
- Allows: static canonical indexes and optional example-value placeholder
matching.
- Split when: index rows move into a generated SQLite-backed table.
- Merge when: catalog.search owns every public index-only lookup path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from catalog.placeholder_index import (
    CATALOG_PLACEHOLDER_INDEX,
    catalog_placeholder_index_payload,
    catalog_placeholder_matches,
    catalog_placeholder_normalized_text,
    catalog_placeholder_replacement_plan,
)
from catalog.value_index import (
    CATALOG_COLUMN_VALUE_INDEX,
    CATALOG_JSON_ARRAY_VALUE_INDEX,
    CATALOG_PATTERN_VALUE_INDEX,
    CATALOG_SPANISH_TEXT_SCAN_INDEX,
    catalog_canonical_value_index_payload,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mcp.models import JsonObject

CATALOG_INDEX_OPERATION_MODE: Final = "read_only_local_catalog_index"
CATALOG_INDEX_MAX_QUERY_CHARS: Final = 300


def catalog_index_lookup_summary_payload() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "tool_name": "catalog.index",
        "operation_mode": CATALOG_INDEX_OPERATION_MODE,
        "query_argument": "optional concise text for placeholder matching",
        "returned_indexes": [
            "canonical_placeholder_index",
            "canonical_value_index",
            "canonical_placeholder_matches",
            "canonical_placeholder_replacement_plan",
            "canonical_placeholder_normalized_query",
        ],
        "placeholder_index_row_count": len(CATALOG_PLACEHOLDER_INDEX),
        "value_index_row_count": _catalog_value_index_row_count(),
        "spanish_text_scan_count": len(CATALOG_SPANISH_TEXT_SCAN_INDEX),
        "full_index_payload_embedded_in_prompt": False,
        "full_index_payload_embedded_in_search": False,
    }


def catalog_index(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Return canonical placeholder and value indexes without running a catalog.

    search.
    """
    del repo_root
    query = _optional_query(arguments.get("query"))
    return {
        "response_kind": "catalog_index",
        "operation_mode": CATALOG_INDEX_OPERATION_MODE,
        "canonical_index_lookup": catalog_index_lookup_summary_payload(),
        "query": query,
        "canonical_placeholder_index": catalog_placeholder_index_payload(),
        "canonical_placeholder_matches": catalog_placeholder_matches(
            query,
            include_alias_only=True,
        ),
        "canonical_placeholder_replacement_plan": catalog_placeholder_replacement_plan(
            query
        ),
        "canonical_placeholder_normalized_query": catalog_placeholder_normalized_text(
            query
        ),
        "canonical_value_index": catalog_canonical_value_index_payload(),
        "sample_value_policy": {
            "example_values_must_use_placeholders": True,
            "real_values_must_not_be_invented": True,
            "replacement_plan_available": True,
            "examples": ["John Doe", "+55 55555", "jdoe@example.com"],
            "replacement_examples": {
                "John Doe": "[PERSON_FULL_NAME_FORMAT_1]",
                "+55 55555": "[PHONE_NUMBER_FORMAT_1]",
                "jdoe@example.com": "[EMAIL_ADDRESS_FORMAT_1]",
            },
        },
        "sqlite_read_policy": {
            "sqlite_ssot": True,
            "static_index_only": True,
            "raw_sql_allowed": False,
        },
        "cursor_advanced": False,
        "writes_performed": False,
        "write_actions": [],
        "live_make_called": False,
        "credentials_required": False,
        "provider_api_call": False,
        "provider_execution": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "requires_operator_confirmation": False,
    }


def _catalog_value_index_row_count() -> int:
    """Return the public canonical value-index row count without materializing.

    rows.
    """
    return (
        len(CATALOG_COLUMN_VALUE_INDEX)
        + len(CATALOG_PATTERN_VALUE_INDEX)
        + len(CATALOG_JSON_ARRAY_VALUE_INDEX)
        + 2
    )


def _optional_query(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        message = "catalog.index query must be text."
        raise TypeError(message)
    query = value.strip()
    if len(query) > CATALOG_INDEX_MAX_QUERY_CHARS:
        message = (
            f"catalog.index query is capped at {CATALOG_INDEX_MAX_QUERY_CHARS}"
            f"characters."
        )
        raise ValueError(message)
    return query
