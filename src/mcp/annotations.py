# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.no-obsolete-domain-tools
# - docs/adr/catalog-semantic-graph-preview-policy.md
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Explicit MCP tool annotation classifications for the minimal public surface.

Boundary contract:
- Owns: semantic annotation policy for the active public MCP tools.
- Must not: register tools, execute handlers, parse intents, or perform IO.
- Allows: read-only and local non-destructive write-like classification specs.
- Split when: annotations require transport-specific or write-capable policies.
- Merge when: another annotation module classifies the same public MCP tools.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Final

from mcp.linter_rule_editor_contracts import LINTER_RULE_EDITOR_TOOL_NAMES
from mcp.models import JsonObject, McpToolAnnotations
from mcp.session import MCP_SESSION_START_TOOL

if TYPE_CHECKING:
    from collections.abc import Mapping

CATALOG_SEARCH_READ_ONLY_RATIONALE: Final[str] = (
    "Searches local Pancakes Core SQLite catalog data only; never advances "
    "catalog units "
    "or calls providers."
)
CATALOG_NEXT_UNIT_DEVTOOL_RATIONALE: Final[str] = (
    "Development-only operator-approved semantic-worker read from SQLite; "
    "no provider calls."
)
CATALOG_SAVE_UNIT_DEVTOOL_RATIONALE: Final[str] = (
    "Development-only operator-approved semantic-worker local SQLite "
    "checkpoint for generated "
    "catalog metadata only; no provider call, no credential transfer, and "
    "no per-unit confirmation."
)
LOCAL_PROJECT_SEARCH_RATIONALE: Final[str] = (
    "Reads repository-local Make scenario draft metadata and artifacts "
    "only; no external "
    "business database, provider, or credential access."
)
PROJECT_VERIFY_LOCAL_RATIONALE_PREFIX: Final[str] = (
    "Runs deterministic local project verification and local import "
    "projection only;"
)
PROJECT_VERIFY_LOCAL_RATIONALE_SUFFIX: Final[str] = (
    "live Make import remains outside this read-only tool and requires "
    "operator gating."
)
PROJECT_VERIFY_LOCAL_RATIONALE: Final[str] = (
    f"{PROJECT_VERIFY_LOCAL_RATIONALE_PREFIX} "
    f"{PROJECT_VERIFY_LOCAL_RATIONALE_SUFFIX}"
)
LINTER_RULE_EDITOR_WRITE_RATIONALE_PREFIX: Final[str] = (
    "Edits local Make linter rule evidence through typed lease, proof, "
    "snapshot,"
)
LINTER_RULE_EDITOR_WRITE_RATIONALE_SUFFIX: Final[str] = (
    "and git guards without raw SQL, raw file editor access, provider "
    "calls, or push."
)
LINTER_RULE_EDITOR_WRITE_RATIONALE: Final[str] = (
    f"{LINTER_RULE_EDITOR_WRITE_RATIONALE_PREFIX} "
    f"{LINTER_RULE_EDITOR_WRITE_RATIONALE_SUFFIX}"
)

PUBLIC_TOOL_ANNOTATION_NAMES: Final[tuple[str, ...]] = (
    MCP_SESSION_START_TOOL,
    "catalog.index",
    "catalog.search",
    "catalog.inspect",
    "catalog.graph.search",
    "catalog.semantic.preview",
    "catalog.modify",
    "catalog.node.modify",
    "catalog.edge.propose",
    "catalog.edge.apply",
    "catalog.review.add",
    "project.search",
    "project.draft.stage",
    "project.draft.import",
    "project.create",
    "project.health",
    "project.view",
    "project.edit",
    "project.verify",
    "project.capabilities.inspect",
    "project.make",
    "project.package.inspect",
    "project.next",
    "project.modules.view",
    "project.modules.add",
    "project.modules.modify",
    "project.modules.delete",
    "project.links.view",
    "project.filters.view",
    "project.filters.add",
    "project.filters.modify",
    "project.filters.delete",
    "project.error_handlers.view",
    "project.error_handlers.add",
    "project.error_handlers.modify",
    "project.error_handlers.delete",
    "documentation.generate",
    "documentation.validate",
    "onboarding.validate",
    "linter.quarantine.write",
    *LINTER_RULE_EDITOR_TOOL_NAMES,
    "backlog.add",
    "backlog.list",
    "backlog.end",
)


def read_only_annotation(rationale: str) -> McpToolAnnotations:
    """Return a read-only, idempotent annotation spec."""
    return McpToolAnnotations(
        classification="read_only",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
        local_only=True,
        provider_api_call=False,
        credential_value_transfer=False,
        secret_output=False,
        rationale=rationale,
    )


def local_workspace_write_annotation(rationale: str) -> McpToolAnnotations:
    """Return a non-destructive local workspace write annotation spec."""
    return McpToolAnnotations(
        classification="write_like",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
        local_only=True,
        provider_api_call=False,
        credential_value_transfer=False,
        secret_output=False,
        rationale=rationale,
    )


def local_catalog_worker_autosave_annotation(
    rationale: str,
) -> McpToolAnnotations:
    """Return the computed result for the caller."""
    return McpToolAnnotations(
        classification="read_only",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
        local_only=True,
        provider_api_call=False,
        credential_value_transfer=False,
        secret_output=False,
        rationale=rationale,
    )


def local_workspace_destructive_annotation(
    rationale: str,
) -> McpToolAnnotations:
    """Return a destructive local workspace annotation spec."""
    return McpToolAnnotations(
        classification="destructive",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
        local_only=True,
        provider_api_call=False,
        credential_value_transfer=False,
        secret_output=False,
        rationale=rationale,
    )


def public_tool_annotation_specs() -> dict[str, McpToolAnnotations]:
    """Return annotation specs for every active public MCP tool."""
    session_rationale_prefix = (
        "Creates a process-local Make scenario session intent receipt"
    )
    session_rationale_suffix = (
        "without file, SQLite, provider, or live Make writes."
    )
    session_rationale = f"{session_rationale_prefix} {session_rationale_suffix}"
    return {
        MCP_SESSION_START_TOOL: read_only_annotation(session_rationale),
        "catalog.index": read_only_annotation(
            "Returns static canonical catalog indexes and example "
            "placeholder matches only."
        ),
        "catalog.search": read_only_annotation(
            CATALOG_SEARCH_READ_ONLY_RATIONALE
        ),
        "catalog.inspect": read_only_annotation(
            "Inspects one local Pancakes Core SQLite catalog entity without "
            "cursor movement."
        ),
        "catalog.graph.search": read_only_annotation(
            "Searches local SQLite graph and saved semantic output tables "
            "without writes."
        ),
        "catalog.semantic.preview": read_only_annotation(
            "Previews unsaved semantic graph output against local SQLite "
            "without writes."
        ),
        "catalog.work.next": local_workspace_write_annotation(
            "Leases source-backed semantic catalog work units without "
            "implicit run resets."
        ),
        "catalog.work.save": local_workspace_write_annotation(
            "Saves validated semantic catalog work outputs and progress "
            "receipts locally."
        ),
        "catalog.modify": local_workspace_write_annotation(
            "Applies typed local catalog unit and edge-proposal mutations "
            "without raw SQL."
        ),
        "catalog.node.modify": local_workspace_write_annotation(
            "Upserts typed local graph node projections without raw SQL."
        ),
        "catalog.edge.propose": local_workspace_write_annotation(
            "Records typed local graph edge proposals without applying raw SQL."
        ),
        "catalog.edge.apply": local_workspace_write_annotation(
            "Applies approved typed local graph edge proposals without "
            "provider calls."
        ),
        "catalog.review.add": local_workspace_write_annotation(
            "Records typed local catalog review/backlog rows without "
            "provider calls."
        ),
        "project.search": read_only_annotation(LOCAL_PROJECT_SEARCH_RATIONALE),
        "project.draft.stage": local_workspace_write_annotation(
            "Dry-runs or writes one local staged Make scenario intake draft "
            "only."
        ),
        "project.draft.import": local_workspace_write_annotation(
            "Dry-runs or writes one local staged Make artifact intake draft "
            "only."
        ),
        "project.create": local_workspace_write_annotation(
            "Dry-runs or creates one repository-local Make scenario draft only."
        ),
        "project.health": read_only_annotation(
            "Reads local technical project health only; no external "
            "lifecycle state."
        ),
        "project.view": read_only_annotation(
            "Reads a bounded local project graph only."
        ),
        "project.edit": local_workspace_write_annotation(
            "Routes semantic local module, filter, and error-handler edits "
            "only."
        ),
        "project.verify": read_only_annotation(PROJECT_VERIFY_LOCAL_RATIONALE),
        "project.capabilities.inspect": read_only_annotation(
            "Reads local Make.com MCP capability metadata only; no provider "
            "or live Make calls."
        ),
        "project.make": local_workspace_write_annotation(
            "Previews or writes local Make artifact projections without "
            "provider calls."
        ),
        "project.package.inspect": read_only_annotation(
            "Reads one bounded local package section without raw blueprint "
            "JSON or provider calls."
        ),
        "project.next": read_only_annotation(
            "Computes the next local IDE action from project graph health."
        ),
        "project.modules.view": read_only_annotation(
            "Reads local Make scenario module summaries only."
        ),
        "project.modules.add": local_workspace_write_annotation(
            "Dry-runs or writes one repository-local Make module node only."
        ),
        "project.modules.modify": local_workspace_write_annotation(
            "Dry-runs or modifies one repository-local Make module node only."
        ),
        "project.modules.delete": read_only_annotation(
            "Previews one repository-local Make module removal without writing."
        ),
        "project.links.view": read_only_annotation(
            "Reads derived local Make scenario graph links only."
        ),
        "project.filters.view": read_only_annotation(
            "Reads bounded local Make scenario route filter summaries only."
        ),
        "project.filters.add": local_workspace_write_annotation(
            "Dry-runs or writes one repository-local Make route filter only."
        ),
        "project.filters.modify": local_workspace_write_annotation(
            "Dry-runs or modifies one repository-local Make route filter only."
        ),
        "project.filters.delete": read_only_annotation(
            "Previews one repository-local Make route filter removal "
            "without writing."
        ),
        "project.error_handlers.view": read_only_annotation(
            "Reads bounded local Make scenario error-handler summaries only."
        ),
        "project.error_handlers.add": local_workspace_write_annotation(
            "Dry-runs or writes one repository-local Make error-handler "
            "container only."
        ),
        "project.error_handlers.modify": local_workspace_write_annotation(
            "Dry-runs or modifies one repository-local Make error-handler "
            "container only."
        ),
        "project.error_handlers.delete": read_only_annotation(
            "Previews one repository-local Make error-handler removal "
            "without writing."
        ),
        "documentation.generate": read_only_annotation(
            "Generates bounded documentation payloads from local project "
            "state only."
        ),
        "documentation.validate": read_only_annotation(
            "Validates local documentation payloads without rendering PDFs "
            "or calling providers."
        ),
        "onboarding.validate": read_only_annotation(
            "Validates redacted local onboarding payloads without storing "
            "credentials or providers."
        ),
        "linter.quarantine.write": local_workspace_write_annotation(
            "Records candidate-only linter quarantine state in the Pancakes "
            "Core SQLite SSOT only."
        ),
        **{
            tool_name: local_workspace_write_annotation(
                LINTER_RULE_EDITOR_WRITE_RATIONALE
            )
            for tool_name in LINTER_RULE_EDITOR_TOOL_NAMES
            if tool_name
            not in {
                "linter.rule.inspect",
                "linter.rule.rollback",
                "linter.rule.status",
            }
        },
        "linter.rule.inspect": read_only_annotation(
            "Inspects local linter candidate evidence and taxonomy metadata "
            "without mutation."
        ),
        "linter.rule.status": read_only_annotation(
            "Summarizes local linter editor and quarantine state without "
            "mutation."
        ),
        "linter.rule.rollback": local_workspace_destructive_annotation(
            "Reverts one MCP-created local linter rule commit only after "
            "confirmation or evidence."
        ),
        "backlog.add": local_workspace_write_annotation(
            "Records one local backlog item in the Pancakes Core SQLite "
            "SSOT only."
        ),
        "backlog.list": read_only_annotation(
            "Lists local MCP backlog rows from the Pancakes Core SQLite "
            "SSOT only."
        ),
        "backlog.end": local_workspace_write_annotation(
            "Closes one local backlog item in the Pancakes Core SQLite SSOT "
            "only."
        ),
    }


def build_public_tool_annotation_matrix(
    *,
    tool_descriptions: Mapping[str, str] | None = None,
) -> JsonObject:
    """Build a machine-readable annotation matrix for the active MCP surface.

    Returns:
        The active tool annotation matrix.
    """
    all_specs = public_tool_annotation_specs()
    specs = {
        tool_name: all_specs[tool_name]
        for tool_name in PUBLIC_TOOL_ANNOTATION_NAMES
    }
    counts = Counter(spec.classification for spec in specs.values())
    return {
        "schema_version": 1,
        "tool_count": len(specs),
        "classification_counts": {
            "read_only": counts["read_only"],
            "destructive": counts["destructive"],
            "mixed": counts["mixed"],
            "write_like": counts["write_like"],
        },
        "tools": {
            name: {
                "description": (tool_descriptions or {}).get(name, ""),
                "classification": spec.classification,
                "read_only_hint": spec.read_only_hint,
                "destructive_hint": spec.destructive_hint,
                "idempotent_hint": spec.idempotent_hint,
                "open_world_hint": spec.open_world_hint,
                "local_only": spec.local_only,
                "provider_api_call": spec.provider_api_call,
                "credential_value_transfer": spec.credential_value_transfer,
                "secret_output": spec.secret_output,
                "rationale": spec.rationale,
            }
            for name, spec in specs.items()
        },
    }
