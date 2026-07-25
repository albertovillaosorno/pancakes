# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Scenario self-documentation notes for MCP project drafts.

Boundary contract:
- Owns: project-draft note style, note coverage, and local note mutation
helpers.
- Must not: call Make.com, render Make blueprints, own catalog validation, or
persist files.
- Allows: deterministic validation findings and scenario JSON transformations.
- Split when: a language-neutral IR note model exists outside the Make MCP loop.
- Merge when: project-loop code owns the same note schema and coverage rules.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from html import escape
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.findings import build_validation_finding
from languages.make.notes import (
    MAKE_CONNECTION_NOTE_COLOR,
    MAKE_MODULE_NOTE_COLOR,
    MAKE_NOTE_COLOR_PALETTE,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import BlueprintValidationFinding

type ScenarioNoteKind = Literal["module", "connection"]
type ScenarioNoteWriteMode = Literal["add", "modify"]

MODULE_NOTE_MISSING_CODE: Final = "notes.module_note_missing"
CONNECTION_NOTE_MISSING_CODE: Final = "notes.connection_note_missing"
MODULE_NOTE_STYLE_INVALID_CODE: Final = "notes.module_note_style_invalid"
CONNECTION_NOTE_STYLE_INVALID_CODE: Final = (
    "notes.connection_note_style_invalid"
)
NOTE_CONTENT_NOT_USEFUL_CODE: Final = "notes.content_not_useful"
NOTE_SURFACE_UNKNOWN_CODE: Final = "notes.surface_unknown"
NOTE_TEMPLATE_UNFILLED_CODE: Final = "notes.template_unfilled"
NOTE_ZERO_TRACE_UNSAFE_CODE: Final = "notes.zero_trace_unsafe_language"
NOTE_PDF_INDEX_MISSING_CODE: Final = "notes.pdf_index_missing"
NOTE_PLACEHOLDER_PREFIX: Final = "[PLACEHOLDER_NOTE_"
MODULE_NOTE_PLACEHOLDER_MARKER: Final = "[PLACEHOLDER_NOTE_MODULE]"
CONNECTION_NOTE_PLACEHOLDER_MARKER: Final = "[PLACEHOLDER_NOTE_LINK]"
NOTE_FINDING_PATH_MIN_PARTS: Final = 3
NOTE_FINDING_INDEX_POSITION: Final = 2

MODULE_NOTE_SECTIONS: Final[tuple[str, ...]] = (
    "Purpose ",
    "Input ",
    "Output ",
    "Operator check",
)
CONNECTION_NOTE_SECTIONS: Final[tuple[str, ...]] = (
    "Handoff ",
    "Data contract ",
    "Failure signal",
)
SECTION_PATTERN_TEMPLATE: Final = (
    r"<strong>{section}:</strong>\s*(?P<body>.*?)</p>"
)
HTML_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")
MIN_NOTE_SECTION_CHARACTERS: Final = 16
MIN_NOTE_TEXT_CHARACTERS: Final = 110
CONNECTION_NOTE_MODULE_ID_COUNT: Final = 2
FILLER_PHRASES: Final[tuple[str, ...]] = (
    "connects to next module ",
    "does the thing ",
    "generic note ",
    "not applicable ",
    "placeholder note ",
    "same as above ",
    "tbd ",
    "this module does this ",
    "todo",
)
ZERO_TRACE_UNSAFE_LANGUAGE_MARKERS: Final[tuple[str, ...]] = (
    "{{runtime.",
    "__imtconn__",
    ".env",
    ".git ",
    "blueprints.ast ",
    "candidate id ",
    "candidate_id ",
    "debug dump ",
    "draft_id ",
    "languages/make ",
    "linter predicate ",
    "local draft ",
    "local-only ",
    "provider payload ",
    "raw payload ",
    "repos/",
    "rule-corpus ",
    "schoenwald ",
    "source_draft",
)
ZERO_TRACE_WINDOWS_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[a-z]:[\\/]",
    re.IGNORECASE,
)
ZERO_TRACE_UNIX_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)/(?:home|mnt|users|var|tmp)/",
    re.IGNORECASE,
)
ZERO_TRACE_INTERNAL_RULE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z]{3}-\d{3}\b"
)


class ScenarioConnection(NamedTuple):
    """One deterministic graph edge that requires a connection note."""

    source_node_id: str
    target_node_id: str
    source_path: tuple[AstPathPart, ...]


class ScenarioNoteDraft(NamedTuple):
    """One rendered note object and its logical target."""

    note_kind: ScenarioNoteKind
    note: JsonObject
    source_node_id: str | None
    target_node_id: str


class ScenarioNoteMutation(NamedTuple):
    """A local scenario note mutation preview."""

    status: str
    scenario: JsonObject
    note: JsonObject
    target: JsonObject
    message: str


class ScenarioNoteTemplateMutation(NamedTuple):
    """A scenario copy with generated note templates for missing note.

    surfaces.
    """

    scenario: JsonObject
    added_module_note_count: int
    added_connection_note_count: int
    added_notes: tuple[JsonObject, ...]


class ScenarioNoteReviewItem(NamedTuple):
    """One numbered note review item for LLM/human quality checks."""

    note_index: int
    citation_ref: str
    note_kind: str
    target: JsonObject
    status: str
    zero_trace_safe: bool
    title: str
    text: str
    required_action: str


def scenario_note_schema_help() -> JsonObject:
    """Return compact schema guidance for the note tools."""
    return {
        "schema_version": 1,
        "required_note_surfaces": {
            "module": {
                "required_count": "one per module node",
                "color": MAKE_MODULE_NOTE_COLOR,
                "title": "MOD-<node_id> | <public module label>",
                "pdf_index": "PDF index: NOTE-MOD-<node_id>",
                "sections": list(MODULE_NOTE_SECTIONS),
                "purpose": (
                    "Explain the module responsibility, input contract, "
                    "output contract, "
                    "and the operator check needed before handoff."
                ),
            },
            "connection": {
                "required_count": "one per graph connection",
                "color": MAKE_CONNECTION_NOTE_COLOR,
                "title": (
                    "CONN-<source_node_id>-<target_node_id> | <source> -> "
                    "<target>"
                ),
                "pdf_index": (
                    "PDF index: NOTE-CONN-<source_node_id>-<target_node_id>"
                ),
                "sections": list(CONNECTION_NOTE_SECTIONS),
                "purpose": (
                    "Explain why data or control moves across the line, "
                    "what fields must "
                    "survive the handoff, and what failure signal should "
                    "stop handoff."
                ),
            },
        },
        "allowed_colors": sorted(MAKE_NOTE_COLOR_PALETTE),
        "usefulness_rule": (
            "Notes must be specific contracts, not filler. Each required "
            "section must contain "
            "meaningful, target-specific text."
        ),
        "template_rule": (
            f"Generated templates contain {MODULE_NOTE_PLACEHOLDER_MARKER} or "
            f"{CONNECTION_NOTE_PLACEHOLDER_MARKER}. Replace every "
            f"placeholder with useful, "
            "client-ready documentation; placeholders always fail validation."
        ),
        "zero_trace_rule": (
            "Notes are public Make canvas documentation. They must not "
            "include private "
            "implementation names, secrets, local paths, raw payload dumps, "
            "or internal rule ids."
        ),
        "citation_rule": (
            "project.notes.list returns stable citation_ref values for "
            "PDF-ready note citations. "
            "Make-visible note HTML must include the same value as "
            "`PDF index: NOTE-MOD-<node_id>` or "
            "`PDF index: NOTE-CONN-<source_node_id>-<target_node_id>`."
        ),
    }


def scenario_note_schema_example() -> JsonObject:
    """Return a copy-pasteable example for module and connection note tools."""
    return {
        "module_note": {
            "project_id": "lead-routing-demo ",
            "note_kind": "module ",
            "target_node_id": "1",
            "purpose": (
                "Receives the inbound lead bundle and starts the triage "
                "workflow."
            ),
            "input_contract": (
                "Webhook payload must provide request_id, email, company, and "
                "score."
            ),
            "output_contract": (
                "The same lead bundle is available to downstream router "
                "branches."
            ),
            "operator_check": (
                "Confirm the webhook runtime hook is selected before "
                "activation."
            ),
            "dry_run": True,
        },
        "connection_note": {
            "project_id": "lead-routing-demo ",
            "note_kind": "connection ",
            "source_node_id": "1 ",
            "target_node_id": "2",
            "handoff": (
                "Sends the validated intake bundle into the branch decision "
                "point."
            ),
            "data_contract": (
                "request_id and email must remain mapped for downstream audit "
                "records."
            ),
            "failure_signal": (
                "Missing request_id or email should block client handoff."
            ),
            "dry_run": True,
        },
    }


def scenario_note_quality_contract_payload() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "module": {
            "required_sections": list(MODULE_NOTE_SECTIONS),
            "required_arguments": [
                "target_node_id ",
                "purpose ",
                "input_contract ",
                "output_contract ",
                "operator_check",
            ],
            "citation_ref_pattern": "NOTE-MOD-<target_node_id>",
            "make_canvas_pdf_index": "PDF index: NOTE-MOD-<target_node_id>",
            "quality_goal": (
                "Explain the module purpose, input contract, output or side "
                "effect, "
                "and the operator handoff check."
            ),
        },
        "connection": {
            "required_sections": list(CONNECTION_NOTE_SECTIONS),
            "required_arguments": [
                "source_node_id ",
                "target_node_id ",
                "handoff ",
                "data_contract ",
                "failure_signal",
            ],
            "citation_ref_pattern": (
                "NOTE-CONN-<source_node_id>-<target_node_id>"
            ),
            "make_canvas_pdf_index": (
                "PDF index: NOTE-CONN-<source_node_id>-<target_node_id>"
            ),
            "quality_goal": (
                "Explain the handoff reason, the data contract across the "
                "line, "
                "and the failure signal that should stop delivery."
            ),
        },
        "batching_rule": (
            "Repeated modules may share a writing pattern, but each "
            "generated note must name "
            "the node-specific role, input, output, and check."
        ),
        "zero_trace_rule": (
            "Use public operator-facing language only; omit private "
            "implementation names, "
            "local paths, raw payload dumps, credentials, unresolved "
            "runtime placeholders, "
            "and internal rule ids."
        ),
    }


def scenario_note_batch_requirements(note_kind: str) -> JsonObject:
    """Return note-kind specific batch-writing requirements."""
    contract = scenario_note_quality_contract_payload()
    if note_kind == "module":
        return cast("JsonObject", contract["module"])
    if note_kind == "connection":
        return cast("JsonObject", contract["connection"])
    return {}


def scenario_note_coverage_payload(
    root: MakeAstRoot,
    *,
    include_all: bool = True,
    group_limit: int = 5,
    example_limit: int = 3,
) -> JsonObject:
    """Return current self-documentation coverage for one parsed scenario."""
    nodes = _documentable_nodes(root)
    connections = collect_scenario_connections(root)
    notes = _root_note_objects(root)
    module_notes = _module_note_targets(notes)
    connection_notes = _connection_note_targets(notes)
    documentable_node_ids = frozenset(node.node_id for node in nodes)
    documentable_connection_ids = frozenset(
        (connection.source_node_id, connection.target_node_id)
        for connection in connections
    )
    missing_module_notes = tuple(
        node.node_id for node in nodes if node.node_id not in module_notes
    )
    missing_connection_notes = tuple(
        connection
        for connection in connections
        if (connection.source_node_id, connection.target_node_id)
        not in connection_notes
    )
    findings = validate_scenario_self_documentation_notes(root)
    payload: JsonObject = {
        "status": "passed" if not findings else "failed",
        "required_module_note_count": len(nodes),
        "required_connection_note_count": len(connections),
        "present_module_note_count": len(module_notes & documentable_node_ids),
        "present_connection_note_count": len(
            connection_notes & documentable_connection_ids
        ),
        "missing_module_note_count": len(missing_module_notes),
        "missing_connection_note_count": len(missing_connection_notes),
        "grouped_missing_notes": _grouped_missing_note_payloads(
            nodes=nodes,
            missing_module_notes=missing_module_notes,
            missing_connection_notes=missing_connection_notes,
            group_limit=group_limit,
            example_limit=example_limit,
        ),
        "raw_missing_notes_available": bool(
            missing_module_notes or missing_connection_notes
        ),
        "next_query": (
            "Use include_all=true or output_mode=full to inspect raw missing "
            "notes."
        ),
        "finding_count": len(findings),
        "module_note_color": MAKE_MODULE_NOTE_COLOR,
        "connection_note_color": MAKE_CONNECTION_NOTE_COLOR,
        "template_placeholder_prefix": NOTE_PLACEHOLDER_PREFIX,
        "quality_contract": scenario_note_quality_contract_payload(),
        "next_action": _coverage_next_action(
            missing_modules=missing_module_notes,
            missing_connections=missing_connection_notes,
            finding_count=len(findings),
        ),
    }
    if include_all:
        payload["missing_module_notes"] = list(missing_module_notes)
        payload["missing_connection_notes"] = [
            {
                "source_node_id": connection.source_node_id,
                "target_node_id": connection.target_node_id,
            }
            for connection in missing_connection_notes
        ]
    return payload


def _grouped_missing_note_payloads(
    *,
    nodes: tuple[MakeAstNode, ...],
    missing_module_notes: tuple[str, ...],
    missing_connection_notes: tuple[ScenarioConnection, ...],
    group_limit: int,
    example_limit: int,
) -> tuple[JsonObject, ...]:
    """Return bounded missing-note groups while preserving exact counts."""
    node_by_id = {node.node_id: node for node in nodes}
    groups: dict[tuple[str, str], JsonObject] = {}
    for node_id in missing_module_notes:
        node = node_by_id.get(node_id)
        module = _node_module_token(node)
        key = ("module", module)
        group = groups.setdefault(
            key,
            {
                "note_kind": "module",
                "module": module,
                "count": 0,
                "example_node_ids": [],
            },
        )
        group["count"] = _note_group_count(group) + 1
        examples = cast("list[str]", group["example_node_ids"])
        if len(examples) < example_limit:
            examples.append(node_id)
    for connection in missing_connection_notes:
        node = node_by_id.get(connection.target_node_id)
        module = _node_module_token(node)
        key = ("connection", module)
        group = groups.setdefault(
            key,
            {
                "note_kind": "connection",
                "module": module,
                "count": 0,
                "example_connections": [],
            },
        )
        group["count"] = _note_group_count(group) + 1
        examples = cast("list[str]", group["example_connections"])
        if len(examples) < example_limit:
            examples.append(
                f"{connection.source_node_id}->{connection.target_node_id}"
            )
    return tuple(
        sorted(
            groups.values(),
            key=lambda item: (
                -_note_group_count(item),
                0 if item.get("note_kind") == "module" else 1,
                str(item.get("module") or ""),
            ),
        )[:group_limit]
    )


def _note_group_count(group: JsonObject) -> int:
    value = group.get("count")
    return value if isinstance(value, int) else 0


def _node_module_token(node: MakeAstNode | None) -> str:
    if node is None:
        return "unknown"
    return node.module_token.strip() or "unknown"


def validate_scenario_self_documentation_notes(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return blocking findings for missing or weak self-documentation notes."""
    notes = _root_note_objects(root)
    module_notes = _module_note_targets(notes)
    connection_notes = _connection_note_targets(notes)
    findings = list(_note_surface_findings(root))
    findings.extend(
        _missing_module_note_finding(node)
        for node in _documentable_nodes(root)
        if node.node_id not in module_notes
    )
    findings.extend(
        _missing_connection_note_finding(connection)
        for connection in collect_scenario_connections(root)
        if (connection.source_node_id, connection.target_node_id)
        not in connection_notes
    )
    for index, note in notes:
        findings.extend(_note_style_findings(index=index, note=note, root=root))
    return tuple(findings)


def collect_scenario_connections(
    root: MakeAstRoot,
) -> tuple[ScenarioConnection, ...]:
    """Return graph connections that must be documented by connection notes."""
    connections: list[ScenarioConnection] = []
    _collect_flow_connections(
        root.flow, source_path=("flow",), connections=connections
    )
    return tuple(connections)


def add_missing_scenario_note_templates(
    *,
    scenario: JsonObject,
    root: MakeAstRoot,
) -> ScenarioNoteTemplateMutation:
    """Return the computed result for the caller."""
    updated = deepcopy(scenario)
    metadata = _ensure_json_object_member(updated, "metadata")
    raw_notes = metadata.get("notes")
    if not isinstance(raw_notes, list):
        raw_notes = []
        metadata["notes"] = raw_notes
    notes = cast("list[object]", raw_notes)
    existing_notes = tuple(
        (index, note)
        for index, note in enumerate(notes)
        if _is_json_object(note)
    )
    module_note_targets = _module_note_targets(existing_notes)
    connection_note_targets = _connection_note_targets(existing_notes)
    added_notes: list[JsonObject] = []
    added_module_note_count = 0
    added_connection_note_count = 0
    for node in _documentable_nodes(root):
        if node.node_id in module_note_targets:
            continue
        draft = _module_note_template(node)
        notes.append(deepcopy(draft.note))
        added_notes.append(_note_target_payload(draft))
        added_module_note_count += 1
    for connection in collect_scenario_connections(root):
        target = (connection.source_node_id, connection.target_node_id)
        if target in connection_note_targets:
            continue
        draft = _connection_note_template(root=root, connection=connection)
        notes.append(deepcopy(draft.note))
        added_notes.append(_note_target_payload(draft))
        added_connection_note_count += 1
    return ScenarioNoteTemplateMutation(
        scenario=updated,
        added_module_note_count=added_module_note_count,
        added_connection_note_count=added_connection_note_count,
        added_notes=tuple(added_notes),
    )


def scenario_note_review_payload(
    root: MakeAstRoot,
    *,
    limit: int = 20,
    include_all: bool = False,
) -> JsonObject:
    """Return numbered notes for cheap LLM/human quality review."""
    findings_by_note_index: dict[int, list[str]] = {}
    for finding in validate_scenario_self_documentation_notes(root):
        if len(
            finding.source_path
        ) >= NOTE_FINDING_PATH_MIN_PARTS and finding.source_path[:2] == (
            "metadata ",
            "notes",
        ):
            raw_index = finding.source_path[NOTE_FINDING_INDEX_POSITION]
            if isinstance(raw_index, int):
                findings_by_note_index.setdefault(raw_index, []).append(
                    finding.code
                )
    all_items = tuple(
        _note_review_item(
            index=index,
            note=note,
            finding_codes=findings_by_note_index.get(index, ()),
        )
        for index, note in _root_note_objects(root)
    )
    resolved_limit = (
        len(all_items) if include_all else max(0, min(limit, len(all_items)))
    )
    visible_items = all_items[:resolved_limit]
    hidden_review_item_count = max(0, len(all_items) - len(visible_items))
    next_action = _note_review_next_action(
        total_count=len(all_items),
        visible_count=len(visible_items),
    )
    return {
        "status": "ok",
        "review_item_count": len(all_items),
        "returned_review_item_count": len(visible_items),
        "hidden_review_item_count": hidden_review_item_count,
        "limit": resolved_limit,
        "all": include_all,
        "include_all": include_all,
        "hidden_context": (
            f"Showing {len(visible_items)} of {len(all_items)} note(s); "
            f"{hidden_review_item_count} note(s) hidden."
        ),
        "quality_contract": scenario_note_quality_contract_payload(),
        "items": [
            {
                "number": item.note_index + 1,
                "citation_ref": item.citation_ref,
                "note_kind": item.note_kind,
                "target": item.target,
                "status": item.status,
                "zero_trace_safe": item.zero_trace_safe,
                "title": item.title,
                "text": item.text,
                "required_action": item.required_action,
            }
            for item in visible_items
        ],
        "next_action": next_action,
    }


def _note_review_next_action(*, total_count: int, visible_count: int) -> str:
    """Return review guidance that does not invent visible notes."""
    if total_count == 0:
        return (
            "No existing notes to review. Add required module and "
            "connection notes or use "
            "include_all/full to inspect missing note targets."
        )
    if visible_count == 0:
        return (
            "Increase limit or use include_all/full to inspect existing note "
            "review items."
        )
    return (
        "Review every numbered note and use project.notes.modify to replace "
        "placeholders "
        "or lazy text with specific client-ready documentation."
    )


def build_scenario_note_from_arguments(
    arguments: Mapping[str, object],
    root: MakeAstRoot,
) -> ScenarioNoteDraft:
    """Build one self-documenting scenario note from MCP tool arguments.

    Returns:
        The canonical note draft for the requested module or connection.
    """
    note_kind = _required_note_kind(arguments.get("note_kind"))
    if note_kind == "module":
        return _build_module_note(arguments=arguments, root=root)
    return _build_connection_note(arguments=arguments, root=root)


def apply_scenario_note_mutation(
    *,
    scenario: JsonObject,
    draft: ScenarioNoteDraft,
    mode: ScenarioNoteWriteMode,
) -> ScenarioNoteMutation:
    """Apply an add or modify note mutation to a scenario copy.

    Returns:
        The mutation preview and updated scenario payload.
    """
    updated = deepcopy(scenario)
    metadata = _ensure_json_object_member(updated, "metadata")
    raw_notes = metadata.get("notes")
    if not isinstance(raw_notes, list):
        raw_notes = []
        metadata["notes"] = raw_notes
    notes = cast("list[object]", raw_notes)
    existing_index = _matching_note_index(notes=notes, draft=draft)
    if mode == "add" and existing_index is not None:
        return ScenarioNoteMutation(
            status="already_exists",
            scenario=updated,
            note=draft.note,
            target=_note_target_payload(draft),
            message=(
                "The target already has a self-documentation note; use "
                "project.notes.modify."
            ),
        )
    if mode == "modify" and existing_index is None:
        return ScenarioNoteMutation(
            status="not_found",
            scenario=updated,
            note=draft.note,
            target=_note_target_payload(draft),
            message=(
                "No matching self-documentation note exists; use "
                "project.notes.add first."
            ),
        )
    if existing_index is None:
        notes.append(deepcopy(draft.note))
        status = "added"
    else:
        notes[existing_index] = deepcopy(draft.note)
        status = "modified"
    return ScenarioNoteMutation(
        status=status,
        scenario=updated,
        note=draft.note,
        target=_note_target_payload(draft),
        message="Self-documentation note prepared.",
    )


def _build_module_note(
    *,
    arguments: Mapping[str, object],
    root: MakeAstRoot,
) -> ScenarioNoteDraft:
    target_node_id = _required_text(
        arguments.get("target_node_id"), "target_node_id"
    )
    node = _require_node(root=root, node_id=target_node_id)
    purpose = _required_text(arguments.get("purpose"), "purpose")
    input_contract = _required_text(
        arguments.get("input_contract"), "input_contract"
    )
    output_contract = _required_text(
        arguments.get("output_contract"), "output_contract"
    )
    operator_check = _required_text(
        arguments.get("operator_check"), "operator_check"
    )
    title = f"MOD-{node.node_id} | {_public_node_label(node)}"
    note = _note_object(
        content=_html_note(
            title=title,
            pdf_index=_module_pdf_index(node.node_id),
            sections=(
                ("Purpose", purpose),
                ("Input", input_contract),
                ("Output", output_contract),
                ("Operator check", operator_check),
            ),
        ),
        color=MAKE_MODULE_NOTE_COLOR,
        module_ids=(node.node_id,),
        is_filter_note=False,
    )
    return ScenarioNoteDraft(
        note_kind="module",
        note=note,
        source_node_id=None,
        target_node_id=node.node_id,
    )


def _build_connection_note(
    *,
    arguments: Mapping[str, object],
    root: MakeAstRoot,
) -> ScenarioNoteDraft:
    source_node_id = _required_text(
        arguments.get("source_node_id"), "source_node_id"
    )
    target_node_id = _required_text(
        arguments.get("target_node_id"), "target_node_id"
    )
    source = _require_node(root=root, node_id=source_node_id)
    target = _require_node(root=root, node_id=target_node_id)
    _require_existing_connection(
        root=root,
        source_node_id=source.node_id,
        target_node_id=target.node_id,
    )
    handoff = _required_text(arguments.get("handoff"), "handoff")
    data_contract = _required_text(
        arguments.get("data_contract"), "data_contract"
    )
    failure_signal = _required_text(
        arguments.get("failure_signal"), "failure_signal"
    )
    title = (
        f"CONN-{source.node_id}-{target.node_id} | {_public_node_label(source)}"
        f"->"
    )
    title = f"{title}{_public_node_label(target)}"
    note = _note_object(
        content=_html_note(
            title=title,
            pdf_index=_connection_pdf_index(source.node_id, target.node_id),
            sections=(
                ("Handoff", handoff),
                ("Data contract", data_contract),
                ("Failure signal", failure_signal),
            ),
        ),
        color=MAKE_CONNECTION_NOTE_COLOR,
        module_ids=(source.node_id, target.node_id),
        is_filter_note=True,
    )
    return ScenarioNoteDraft(
        note_kind="connection",
        note=note,
        source_node_id=source.node_id,
        target_node_id=target.node_id,
    )


def _module_note_template(node: MakeAstNode) -> ScenarioNoteDraft:
    label = _public_node_label(node)
    title = f"MOD-{node.node_id} | {label}"
    note = _note_object(
        content=_html_note(
            title=title,
            pdf_index=_module_pdf_index(node.node_id),
            sections=(
                (
                    "Purpose",
                    (
                        f"{MODULE_NOTE_PLACEHOLDER_MARKER} Replace with the "
                        f"exact business "
                        f"responsibility of {label}."
                    ),
                ),
                (
                    "Input",
                    (
                        f"{MODULE_NOTE_PLACEHOLDER_MARKER} Replace with the "
                        f"upstream fields, "
                        "runtime resource, or operator selection this "
                        "module requires."
                    ),
                ),
                (
                    "Output",
                    (
                        f"{MODULE_NOTE_PLACEHOLDER_MARKER} Replace with the "
                        f"data, side effect, "
                        "or state this module makes available to downstream "
                        "steps."
                    ),
                ),
                (
                    "Operator check",
                    (
                        f"{MODULE_NOTE_PLACEHOLDER_MARKER} Replace with the "
                        f"concrete setup or "
                        "handoff check a human should verify before activation."
                    ),
                ),
            ),
        ),
        color=MAKE_MODULE_NOTE_COLOR,
        module_ids=(node.node_id,),
        is_filter_note=False,
    )
    return ScenarioNoteDraft(
        note_kind="module",
        note=note,
        source_node_id=None,
        target_node_id=node.node_id,
    )


def _connection_note_template(
    *,
    root: MakeAstRoot,
    connection: ScenarioConnection,
) -> ScenarioNoteDraft:
    source = _require_node(root=root, node_id=connection.source_node_id)
    target = _require_node(root=root, node_id=connection.target_node_id)
    source_label = _public_node_label(source)
    target_label = _public_node_label(target)
    title = (
        f"CONN-{source.node_id}-{target.node_id} | {source_label} ->"
        f"{target_label}"
    )
    note = _note_object(
        content=_html_note(
            title=title,
            pdf_index=_connection_pdf_index(source.node_id, target.node_id),
            sections=(
                (
                    "Handoff",
                    (
                        f"{CONNECTION_NOTE_PLACEHOLDER_MARKER} Replace with "
                        f"why this line moves "
                        f"work from {source_label} to {target_label}."
                    ),
                ),
                (
                    "Data contract",
                    (
                        f"{CONNECTION_NOTE_PLACEHOLDER_MARKER} Replace with "
                        f"the exact fields or "
                        "state that must survive this handoff."
                    ),
                ),
                (
                    "Failure signal",
                    (
                        f"{CONNECTION_NOTE_PLACEHOLDER_MARKER} Replace with "
                        f"the condition that "
                        "should stop this handoff or trigger repair."
                    ),
                ),
            ),
        ),
        color=MAKE_CONNECTION_NOTE_COLOR,
        module_ids=(source.node_id, target.node_id),
        is_filter_note=True,
    )
    return ScenarioNoteDraft(
        note_kind="connection",
        note=note,
        source_node_id=source.node_id,
        target_node_id=target.node_id,
    )


def _collect_flow_connections(
    flow: tuple[MakeAstNode, ...],
    *,
    source_path: tuple[AstPathPart, ...],
    connections: list[ScenarioConnection],
) -> None:
    previous: MakeAstNode | None = None
    for index, node in enumerate(flow):
        if previous is not None:
            connections.append(
                ScenarioConnection(
                    source_node_id=previous.node_id,
                    target_node_id=node.node_id,
                    source_path=(*source_path, index),
                )
            )
        _collect_child_connections(node=node, connections=connections)
        previous = node


def _collect_child_connections(
    *,
    node: MakeAstNode,
    connections: list[ScenarioConnection],
) -> None:
    for route in (*node.routes, *node.branches, *node.tools):
        if route.flow:
            first = route.flow[0]
            connections.append(
                ScenarioConnection(
                    source_node_id=node.node_id,
                    target_node_id=first.node_id,
                    source_path=route.source_trace.path,
                )
            )
        _collect_flow_connections(
            route.flow,
            source_path=(*route.source_trace.path, "flow"),
            connections=connections,
        )
    if node.error_handlers:
        first_handler = node.error_handlers[0]
        connections.append(
            ScenarioConnection(
                source_node_id=node.node_id,
                target_node_id=first_handler.node_id,
                source_path=first_handler.source_trace.path,
            )
        )
        _collect_flow_connections(
            node.error_handlers,
            source_path=(*node.source_trace.path, "onerror"),
            connections=connections,
        )


def _note_style_findings(
    *,
    index: int,
    note: JsonObject,
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    if _note_module_ids_are_malformed(note):
        findings = (
            _note_finding(
                code=NOTE_SURFACE_UNKNOWN_CODE,
                path=("metadata", "notes", index, "moduleIds"),
                internal_message=(
                    "Note moduleIds must be a list of non-empty string or "
                    "integer module IDs."
                ),
            ),
        )
    else:
        module_ids = _note_module_ids(note)
        findings = _note_style_findings_for_ids(
            index=index,
            note=note,
            root=root,
            module_ids=module_ids,
        )
    return findings


def _note_style_findings_for_ids(
    *,
    index: int,
    note: JsonObject,
    root: MakeAstRoot,
    module_ids: tuple[str, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    if len(module_ids) == 1 and note.get("isFilterNote") is not True:
        node = _optional_node(root=root, node_id=module_ids[0])
        if node is None:
            return (_unknown_note_target_finding(index=index),)
        return _validate_module_note_style(index=index, note=note, node=node)
    if (
        len(module_ids) == CONNECTION_NOTE_MODULE_ID_COUNT
        and note.get("isFilterNote") is True
    ):
        connection = _optional_connection(
            root=root,
            source_node_id=module_ids[0],
            target_node_id=module_ids[1],
        )
        if connection is None:
            return (_unknown_note_target_finding(index=index),)
        return _validate_connection_note_style(
            index=index, note=note, connection=connection
        )
    if note.get("isFilterNote") is True or module_ids:
        return (
            _note_finding(
                code=NOTE_SURFACE_UNKNOWN_CODE,
                path=("metadata", "notes", index),
                internal_message=(
                    "Self-documentation notes must target exactly one "
                    "module or one ordered "
                    "source-to-target connection."
                ),
            ),
        )
    return ()


def _unknown_note_target_finding(*, index: int) -> BlueprintValidationFinding:
    return _note_finding(
        code=NOTE_SURFACE_UNKNOWN_CODE,
        path=("metadata", "notes", index, "moduleIds"),
        internal_message=(
            "Self-documentation note targets must reference existing "
            "modules or "
            "edges."
        ),
    )


def _validate_module_note_style(
    *,
    index: int,
    note: JsonObject,
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    content = _note_content(note)
    findings: list[BlueprintValidationFinding] = []
    expected_title = f"<h2>MOD-{node.node_id} | "
    if not content.startswith(expected_title):
        findings.append(
            _note_finding(
                code=MODULE_NOTE_STYLE_INVALID_CODE,
                path=("metadata", "notes", index, "content"),
                internal_message=(
                    f"Module note for node {node.node_id} must start with "
                    f"{expected_title!r}."
                ),
            )
        )
    findings.extend(
        _pdf_index_findings(
            index=index,
            content=content,
            expected_index=_module_pdf_index(node.node_id),
        )
    )
    findings.extend(
        _style_findings_for_note(
            index=index,
            note=note,
            expected_color=MAKE_MODULE_NOTE_COLOR,
            sections=MODULE_NOTE_SECTIONS,
            code=MODULE_NOTE_STYLE_INVALID_CODE,
        )
    )
    return tuple(findings)


def _validate_connection_note_style(
    *,
    index: int,
    note: JsonObject,
    connection: ScenarioConnection,
) -> tuple[BlueprintValidationFinding, ...]:
    content = _note_content(note)
    findings: list[BlueprintValidationFinding] = []
    expected_title = (
        f"<h2>CONN-{connection.source_node_id}-{connection.target_node_id} | "
    )
    heading = content.split("</h2>", 1)[0]
    if not content.startswith(expected_title) or (
        " -> " not in heading and " -&gt; " not in heading
    ):
        findings.append(
            _note_finding(
                code=CONNECTION_NOTE_STYLE_INVALID_CODE,
                path=("metadata", "notes", index, "content"),
                internal_message=(
                    "Connection notes must start with "
                    f"{expected_title!r} and include the source-to-target "
                    f"arrow."
                ),
            )
        )
    findings.extend(
        _pdf_index_findings(
            index=index,
            content=content,
            expected_index=_connection_pdf_index(
                connection.source_node_id,
                connection.target_node_id,
            ),
        )
    )
    findings.extend(
        _style_findings_for_note(
            index=index,
            note=note,
            expected_color=MAKE_CONNECTION_NOTE_COLOR,
            sections=CONNECTION_NOTE_SECTIONS,
            code=CONNECTION_NOTE_STYLE_INVALID_CODE,
        )
    )
    return tuple(findings)


def _pdf_index_findings(
    *,
    index: int,
    content: str,
    expected_index: str,
) -> tuple[BlueprintValidationFinding, ...]:
    expected_text = f"PDF index: {expected_index}"
    if expected_text in _plain_text(content):
        return ()
    return (
        _note_finding(
            code=NOTE_PDF_INDEX_MISSING_CODE,
            path=("metadata", "notes", index, "content"),
            internal_message=(
                "Make-visible note HTML must include "
                f"{expected_text!r} so the Make canvas and generated PDF "
                f"share the same anchor."
            ),
        ),
    )


def _style_findings_for_note(
    *,
    index: int,
    note: JsonObject,
    expected_color: str,
    sections: tuple[str, ...],
    code: str,
) -> tuple[BlueprintValidationFinding, ...]:
    findings: list[BlueprintValidationFinding] = []
    color = _note_color(note)
    if color != expected_color:
        findings.append(
            _note_finding(
                code=code,
                path=("metadata", "notes", index, "metadata", "color"),
                internal_message=f"Note color must be {expected_color}.",
            )
        )
    content = _note_content(note)
    findings.extend(
        _zero_trace_unsafe_language_findings(index=index, content=content)
    )
    if NOTE_PLACEHOLDER_PREFIX.casefold() in content.casefold():
        findings.append(
            _note_finding(
                code=NOTE_TEMPLATE_UNFILLED_CODE,
                path=("metadata", "notes", index, "content"),
                internal_message=(
                    "Generated note templates must be filled with useful "
                    "client-ready "
                    "documentation before validation or export."
                ),
            )
        )
    if _plain_text(content).casefold() in {"", "none", "n/a"}:
        findings.append(
            _content_not_useful_finding(
                index=index, detail="Note content is empty."
            )
        )
    for section in sections:
        section_text = _section_text(content=content, section=section)
        if section_text is None:
            findings.append(
                _note_finding(
                    code=code,
                    path=("metadata", "notes", index, "content"),
                    internal_message=(
                        f"Note is missing the required {section!r} section."
                    ),
                )
            )
            continue
        if not _section_is_useful(section_text):
            findings.append(
                _content_not_useful_finding(
                    index=index,
                    detail=f"The {section!r} section is too generic.",
                )
            )
    if len(_plain_text(content)) < MIN_NOTE_TEXT_CHARACTERS:
        findings.append(
            _content_not_useful_finding(
                index=index,
                detail=(
                    "The note is too short to be useful scenario documentation."
                ),
            )
        )
    return tuple(findings)


def _section_is_useful(value: str) -> bool:
    text = _plain_text(value)
    normalized = text.casefold()
    if len(text) < MIN_NOTE_SECTION_CHARACTERS:
        return False
    if NOTE_PLACEHOLDER_PREFIX.casefold() in normalized:
        return False
    return not any(phrase in normalized for phrase in FILLER_PHRASES)


def _zero_trace_unsafe_language_findings(
    *,
    index: int,
    content: str,
) -> tuple[BlueprintValidationFinding, ...]:
    plain_text = _plain_text(content)
    normalized = plain_text.casefold().replace("\\", "/")
    unsafe_marker = any(
        marker in normalized for marker in ZERO_TRACE_UNSAFE_LANGUAGE_MARKERS
    )
    unsafe_path = (
        ZERO_TRACE_WINDOWS_PATH_PATTERN.search(plain_text) is not None
        or ZERO_TRACE_UNIX_PATH_PATTERN.search(plain_text) is not None
    )
    unsafe_rule_id = (
        ZERO_TRACE_INTERNAL_RULE_ID_PATTERN.search(plain_text) is not None
    )
    if not unsafe_marker and not unsafe_path and not unsafe_rule_id:
        return ()
    return (
        _note_finding(
            code=NOTE_ZERO_TRACE_UNSAFE_CODE,
            path=("metadata", "notes", index, "content"),
            internal_message=(
                "Note content must use public operator-facing language and "
                "omit private "
                "implementation names, local paths, raw payload dumps, "
                "unresolved runtime "
                "placeholders, and internal rule ids."
            ),
        ),
    )


def _missing_module_note_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=MODULE_NOTE_MISSING_CODE,
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "Every module must have a useful module note before export.",
            (
                f"Node {node.node_id} is missing a MOD-{node.node_id} note "
                f"with "
                "Purpose, Input, Output, and Operator check sections."
            ),
        ),
    )


def _missing_connection_note_finding(
    connection: ScenarioConnection,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=CONNECTION_NOTE_MISSING_CODE,
        severity="error",
        node=(connection.target_node_id, connection.source_path),
        catalog_module_id=None,
        messages=(
            (
                "Every connection must have a useful connection note before "
                "export."
            ),
            (
                f"Connection "
                f"{connection.source_node_id}->{connection.target_node_id} "
                f"is "
                "missing a CONN note with Handoff, Data contract, and "
                "Failure signal sections."
            ),
        ),
    )


def _note_finding(
    *,
    code: str,
    path: tuple[AstPathPart, ...],
    internal_message: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=code,
        severity="error",
        node=(None, path),
        catalog_module_id=None,
        messages=(
            "Scenario self-documentation notes must follow the required style.",
            internal_message,
        ),
    )


def _content_not_useful_finding(
    *, index: int, detail: str
) -> BlueprintValidationFinding:
    return _note_finding(
        code=NOTE_CONTENT_NOT_USEFUL_CODE,
        path=("metadata", "notes", index, "content"),
        internal_message=f"Note {index + 1} is not useful enough: {detail}",
    )


def _documentable_nodes(root: MakeAstRoot) -> tuple[MakeAstNode, ...]:
    return tuple(
        node for node in iter_ast_nodes(root) if node.module_token.strip()
    )


def _root_note_objects(root: MakeAstRoot) -> tuple[tuple[int, JsonObject], ...]:
    raw_notes = root.scenario.metadata.get("notes")
    if not isinstance(raw_notes, list):
        return ()
    notes: list[tuple[int, JsonObject]] = []
    for index, note in enumerate(cast("list[object]", raw_notes)):
        if _is_json_object(note):
            notes.append((index, note))
    return tuple(notes)


def _note_surface_findings(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    raw_notes = root.scenario.metadata.get("notes")
    if raw_notes is None:
        return ()
    if not isinstance(raw_notes, list):
        return (
            _note_finding(
                code=NOTE_SURFACE_UNKNOWN_CODE,
                path=("metadata", "notes"),
                internal_message=(
                    "metadata.notes must be a list of note objects."
                ),
            ),
        )
    return tuple(
        _note_finding(
            code=NOTE_SURFACE_UNKNOWN_CODE,
            path=("metadata", "notes", index),
            internal_message="Every metadata.notes item must be a note object.",
        )
        for index, note in enumerate(cast("list[object]", raw_notes))
        if not _is_json_object(note)
    )


def _module_note_targets(
    notes: tuple[tuple[int, JsonObject], ...],
) -> frozenset[str]:
    return frozenset(
        module_ids[0]
        for _, note in notes
        for module_ids in (_note_module_ids(note),)
        if not _note_module_ids_are_malformed(note)
        and len(module_ids) == 1
        and note.get("isFilterNote") is not True
    )


def _connection_note_targets(
    notes: tuple[tuple[int, JsonObject], ...],
) -> frozenset[tuple[str, str]]:
    return frozenset(
        (module_ids[0], module_ids[1])
        for _, note in notes
        for module_ids in (_note_module_ids(note),)
        if not _note_module_ids_are_malformed(note)
        and len(module_ids) == CONNECTION_NOTE_MODULE_ID_COUNT
        and note.get("isFilterNote") is True
    )


def _note_object(
    *,
    content: str,
    color: str,
    module_ids: tuple[str, ...],
    is_filter_note: bool,
) -> JsonObject:
    return {
        "content": content,
        "isFilterNote": is_filter_note,
        "metadata": {"color": color},
        "moduleIds": list(module_ids),
    }


def _html_note(
    *,
    title: str,
    pdf_index: str,
    sections: tuple[tuple[str, str], ...],
) -> str:
    paragraphs = [
        f"<p><strong>PDF index:</strong> {escape(pdf_index.strip())}</p>"
    ]
    paragraphs.extend(
        f"<p><strong>{escape(section)}:</strong> {escape(body.strip())}</p>"
        for section, body in sections
    )
    return "".join((f"<h2>{escape(title.strip())}</h2>", *paragraphs))


def _module_pdf_index(node_id: str) -> str:
    return f"NOTE-MOD-{_citation_token(node_id)}"


def _connection_pdf_index(source_node_id: str, target_node_id: str) -> str:
    source_token = _citation_token(source_node_id)
    target_token = _citation_token(target_node_id)
    return f"NOTE-CONN-{source_token}-{target_token}"


def _note_content(note: JsonObject) -> str:
    content = note.get("content")
    return content if isinstance(content, str) else ""


def _note_color(note: JsonObject) -> str:
    metadata = note.get("metadata")
    if not _is_json_object(metadata):
        return ""
    color = metadata.get("color")
    return color.strip().upper() if isinstance(color, str) else ""


def _note_module_ids(note: JsonObject) -> tuple[str, ...]:
    module_ids = note.get("moduleIds")
    if not isinstance(module_ids, list):
        return ()
    normalized: list[str] = []
    for module_id in cast("list[object]", module_ids):
        if isinstance(module_id, bool):
            continue
        if isinstance(module_id, str | int):
            text = str(module_id).strip()
            if text:
                normalized.append(text)
    return tuple(normalized)


def _note_module_ids_are_malformed(note: JsonObject) -> bool:
    if "moduleIds" not in note:
        return False
    module_ids = note.get("moduleIds")
    if not isinstance(module_ids, list):
        return True
    for module_id in cast("list[object]", module_ids):
        if isinstance(module_id, bool):
            return True
        if not isinstance(module_id, str | int):
            return True
        if not str(module_id).strip():
            return True
    return False


def _section_text(*, content: str, section: str) -> str | None:
    pattern = re.compile(
        SECTION_PATTERN_TEMPLATE.format(section=re.escape(section)),
        re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        return None
    return match.group("body")


def _plain_text(value: str) -> str:
    without_tags = HTML_TAG_PATTERN.sub(" ", value)
    return WHITESPACE_PATTERN.sub(" ", without_tags).strip()


def _public_node_label(node: MakeAstNode) -> str:
    label = (
        node.label.strip()
        or node.module_token.strip()
        or f"Node {node.node_id}"
    )
    label = label.replace(":", " ")
    return WHITESPACE_PATTERN.sub(" ", label).strip()[:80]


def _coverage_next_action(
    *,
    missing_modules: tuple[str, ...],
    missing_connections: tuple[ScenarioConnection, ...],
    finding_count: int,
) -> str:
    if missing_modules:
        return "Add useful module notes with project.notes.add before export."
    if missing_connections:
        return (
            "Add useful connection notes with project.notes.add before export."
        )
    if finding_count:
        return "Repair existing notes with project.notes.modify before export."
    return "Scenario self-documentation notes are complete."


def _matching_note_index(
    *,
    notes: list[object],
    draft: ScenarioNoteDraft,
) -> int | None:
    for index, raw_note in enumerate(notes):
        if not _is_json_object(raw_note):
            continue
        module_ids = _note_module_ids(raw_note)
        if draft.note_kind == "module":
            if (
                len(module_ids) == 1
                and module_ids[0] == draft.target_node_id
                and raw_note.get("isFilterNote") is not True
            ):
                return index
        elif (
            len(module_ids) == CONNECTION_NOTE_MODULE_ID_COUNT
            and module_ids[0] == draft.source_node_id
            and module_ids[1] == draft.target_node_id
            and raw_note.get("isFilterNote") is True
        ):
            return index
    return None


def _note_target_payload(draft: ScenarioNoteDraft) -> JsonObject:
    if draft.note_kind == "module":
        return {"note_kind": "module", "target_node_id": draft.target_node_id}
    return {
        "note_kind": "connection",
        "source_node_id": draft.source_node_id,
        "target_node_id": draft.target_node_id,
    }


def _note_review_item(
    *,
    index: int,
    note: JsonObject,
    finding_codes: tuple[str, ...] | list[str],
) -> ScenarioNoteReviewItem:
    module_ids = _note_module_ids(note)
    if len(module_ids) == 1 and note.get("isFilterNote") is not True:
        note_kind = "module"
        target: JsonObject = {
            "note_kind": "module",
            "target_node_id": module_ids[0],
        }
    elif (
        len(module_ids) == CONNECTION_NOTE_MODULE_ID_COUNT
        and note.get("isFilterNote") is True
    ):
        note_kind = "connection"
        target = {
            "note_kind": "connection",
            "source_node_id": module_ids[0],
            "target_node_id": module_ids[1],
        }
    else:
        note_kind = "unknown"
        target = {"note_kind": "unknown", "moduleIds": list(module_ids)}
    content = _note_content(note)
    text = _plain_text(content)
    status = "needs_update" if finding_codes else "review"
    zero_trace_safe = NOTE_ZERO_TRACE_UNSAFE_CODE not in set(finding_codes)
    return ScenarioNoteReviewItem(
        note_index=index,
        citation_ref=_note_citation_ref(
            index=index, note_kind=note_kind, target=target
        ),
        note_kind=note_kind,
        target=target,
        status=status,
        zero_trace_safe=zero_trace_safe,
        title=_note_title(content),
        text=text,
        required_action=_note_review_required_action(
            finding_codes=finding_codes
        ),
    )


def _note_title(content: str) -> str:
    if not content.startswith("<h2>") or "</h2>" not in content:
        return ""
    return _plain_text(content.split("</h2>", 1)[0])


def _note_review_required_action(
    *, finding_codes: tuple[str, ...] | list[str]
) -> str:
    codes = set(finding_codes)
    actions: tuple[tuple[tuple[str, ...], str], ...] = (
        (
            (NOTE_ZERO_TRACE_UNSAFE_CODE,),
            (
                "Rewrite this note in public operator-facing language and "
                "remove private names, "
                "local paths, raw payload dumps, runtime placeholders, and "
                "internal rule ids."
            ),
        ),
        (
            (NOTE_TEMPLATE_UNFILLED_CODE,),
            (
                "Replace every [PLACEHOLDER_NOTE_*] token with specific, "
                "useful client-ready "
                "scenario documentation."
            ),
        ),
        (
            (NOTE_CONTENT_NOT_USEFUL_CODE,),
            (
                "Replace lazy or generic note text with concrete contracts and "
                "checks."
            ),
        ),
        (
            (NOTE_PDF_INDEX_MISSING_CODE,),
            (
                "Add the visible PDF index paragraph with the note "
                "citation_ref "
                "value."
            ),
        ),
        (
            (
                MODULE_NOTE_STYLE_INVALID_CODE,
                CONNECTION_NOTE_STYLE_INVALID_CODE,
            ),
            (
                "Fix naming, color, and required section style with "
                "project.notes.modify."
            ),
        ),
        (
            (NOTE_SURFACE_UNKNOWN_CODE,),
            (
                "Convert this note into a module or connection note with the "
                "required anchors."
            ),
        ),
    )
    for relevant_codes, action in actions:
        if codes.intersection(relevant_codes):
            return action
    return (
        "Review for usefulness; update if the note states only visibletopology."
    )


def _note_citation_ref(
    *, index: int, note_kind: str, target: JsonObject
) -> str:
    if note_kind == "module":
        return f"NOTE-MOD-{_citation_token(target.get('target_node_id'))}"
    if note_kind == "connection":
        source = _citation_token(target.get("source_node_id"))
        target_node = _citation_token(target.get("target_node_id"))
        return f"NOTE-CONN-{source}-{target_node}"
    return f"NOTE-UNRESOLVED-{index + 1:04d}"


def _citation_token(value: object) -> str:
    if not isinstance(value, str | int):
        return "UNKNOWN"
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", str(value).strip()).strip("-")
    return normalized.upper() or "UNKNOWN"


def _require_node(*, root: MakeAstRoot, node_id: str) -> MakeAstNode:
    node = _optional_node(root=root, node_id=node_id)
    if node is None:
        message = f"Scenario node does not exist: {node_id}"
        raise ValueError(message)
    return node


def _optional_node(*, root: MakeAstRoot, node_id: str) -> MakeAstNode | None:
    for node in iter_ast_nodes(root):
        if node.node_id == node_id:
            return node
    return None


def _require_existing_connection(
    *,
    root: MakeAstRoot,
    source_node_id: str,
    target_node_id: str,
) -> None:
    if (
        _optional_connection(
            root=root,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )
        is not None
    ):
        return
    message = (
        f"Scenario connection does not exist:{source_node_id}->{target_node_id}"
    )
    raise ValueError(message)


def _optional_connection(
    *,
    root: MakeAstRoot,
    source_node_id: str,
    target_node_id: str,
) -> ScenarioConnection | None:
    for connection in collect_scenario_connections(root):
        if (
            connection.source_node_id == source_node_id
            and connection.target_node_id == target_node_id
        ):
            return connection
    return None


def _required_note_kind(value: object) -> ScenarioNoteKind:
    text = _required_text(value, "note_kind").casefold().replace("-", "_")
    if text in {"module", "module_note"}:
        return "module"
    if text in {"connection", "connection_note", "line", "route"}:
        return "connection"
    message = "note_kind must be module or connection."
    raise ValueError(message)


def _required_text(value: object, argument_name: str) -> str:
    if not isinstance(value, str):
        message = f"{argument_name} must be non-empty text."
        raise TypeError(message)
    text = value.strip()
    if not text:
        message = f"{argument_name} must be non-empty text."
        raise ValueError(message)
    return text


def _ensure_json_object_member(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if _is_json_object(value):
        return value
    child: JsonObject = {}
    payload[key] = child
    return child


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)


def canonical_note_json(note: JsonObject) -> str:
    """Return deterministic JSON text for a note preview."""
    return json.dumps(note, ensure_ascii=True, indent=2, sort_keys=True)
