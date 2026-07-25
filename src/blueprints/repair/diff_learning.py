# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001049#repo.blueprint-repair.diagnostics.no-automatic-mutation
# - 001068#repo.operator-commands.diff-blueprint.structured-comparison
# - 001068#repo.operator-commands.follow-up-todo-generation
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Draft review-only learning suggestions from repeated blueprint diffs.

Boundary contract:
- Owns: deterministic grouping of repeated diff findings into review
suggestions.
- Must not: mutate generation rules, persist TODOs, or expose blueprint values.
- Allows: JSON-ready suggestion records and temp-scoped TODO draft text.
- Split when: a mutating repair planner or persisted TODO writer owns behavior.
- Merge when: repair diagnostics absorbs identical review-only learning output.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast.models import JsonObject

TEMP_DIFF_LEARNING_ROOT: Final[str] = "temp/diff-blueprint"
REPEATED_FINDING_THRESHOLD: Final[int] = 2
UNKNOWN_MODULE_TYPE: Final[str] = "unknown"
TOP_LEVEL_FLOW_INDEX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\$\.flow\[(?P<index>\d+)\]"
)
UNSAFE_SLUG_CHAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9._/-]+")


class DiffLearningSuggestion(NamedTuple):
    """One review-only follow-up suggestion derived from repeated diff.

    findings.
    """

    category: str
    module_type: str
    finding_count: int
    target_surface: str
    rationale: str
    evidence_path: str
    suggested_test_path: str
    proposed_todo_path: str
    todo_markdown: str

    def as_dict(self) -> JsonObject:
        """Return a JSON-ready suggestion payload."""
        return {
            "category": self.category,
            "module_type": self.module_type,
            "finding_count": self.finding_count,
            "target_surface": self.target_surface,
            "rationale": self.rationale,
            "evidence_path": self.evidence_path,
            "suggested_test_path": self.suggested_test_path,
            "proposed_todo_path": self.proposed_todo_path,
            "todo_markdown": self.todo_markdown,
        }


class _TodoDraftContext(NamedTuple):
    """Internal context for one temp-scoped TODO draft."""

    category: str
    module_type: str
    finding_count: int
    target_surface: str
    evidence_path: str
    suggested_test_path: str


def draft_diff_learning_suggestions(
    *,
    findings: Sequence[Mapping[str, object]],
    source_payloads: Sequence[JsonObject],
) -> tuple[DiffLearningSuggestion, ...]:
    """Return review-only suggestions for repeated diff finding groups."""
    grouped_findings: defaultdict[
        tuple[str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    for finding in findings:
        category = _text_member(finding, "category")
        if category is None:
            continue
        path = _text_member(finding, "path") or "$"
        module_type = _module_type_for_path(
            path=path, source_payloads=source_payloads
        )
        grouped_findings[category, module_type].append(finding)

    suggestions: list[DiffLearningSuggestion] = []
    for group_key in sorted(grouped_findings):
        group = tuple(grouped_findings[group_key])
        if len(group) < REPEATED_FINDING_THRESHOLD:
            continue
        category, module_type = group_key
        target_surface = _target_surface_for_category(category)
        suggested_test_path = _suggested_test_path_for_category(category)
        evidence_path = _representative_evidence_path(group)
        todo_context = _TodoDraftContext(
            category=category,
            module_type=module_type,
            finding_count=len(group),
            target_surface=target_surface,
            evidence_path=evidence_path,
            suggested_test_path=suggested_test_path,
        )
        rationale = _rationale(
            category=category,
            module_type=module_type,
            finding_count=len(group),
        )
        proposed_todo_path = _proposed_todo_path(
            category=category, module_type=module_type
        )
        suggestions.append(
            DiffLearningSuggestion(
                category=category,
                module_type=module_type,
                finding_count=len(group),
                target_surface=target_surface,
                rationale=rationale,
                evidence_path=evidence_path,
                suggested_test_path=suggested_test_path,
                proposed_todo_path=proposed_todo_path,
                todo_markdown=_todo_markdown(todo_context),
            )
        )
    return tuple(suggestions)


def _module_type_for_path(
    *, path: str, source_payloads: Sequence[JsonObject]
) -> str:
    """Return a safe coarse module type for a JSON path."""
    match = TOP_LEVEL_FLOW_INDEX_PATTERN.search(path)
    if match is None:
        return UNKNOWN_MODULE_TYPE
    flow_index = int(match.group("index"))
    for payload in source_payloads:
        module_type = _module_type_at_flow_index(
            payload=payload, flow_index=flow_index
        )
        if module_type != UNKNOWN_MODULE_TYPE:
            return module_type
    return UNKNOWN_MODULE_TYPE


def _module_type_at_flow_index(*, payload: JsonObject, flow_index: int) -> str:
    flow = payload.get("flow")
    if not isinstance(flow, list):
        return UNKNOWN_MODULE_TYPE
    flow_items = cast("list[object]", flow)
    if flow_index >= len(flow_items):
        return UNKNOWN_MODULE_TYPE
    node = flow_items[flow_index]
    if not isinstance(node, dict):
        return UNKNOWN_MODULE_TYPE
    node_payload = cast("dict[object, object]", node)
    module_token = node_payload.get("module")
    if not isinstance(module_token, str):
        return UNKNOWN_MODULE_TYPE
    module_family = module_token.split(":", 1)[0].strip().casefold()
    return _safe_slug(module_family) or UNKNOWN_MODULE_TYPE


def _target_surface_for_category(category: str) -> str:
    if category in {"route/filter", "semantic", "module-version"}:
        return "src/blueprints/validation"
    if category in {"designer-layout", "metadata"}:
        return "src/languages/make/blueprint_export.py"
    if category in {"connection", "placeholder"}:
        return "src/blueprints/validation/handoff_manifest.py"
    return "docs/todo/pending review"


def _suggested_test_path_for_category(category: str) -> str:
    if category in {"route/filter", "semantic", "module-version"}:
        return "tests/blueprints/validation/blueprint_validation_contract.py"
    if category in {"designer-layout", "metadata"}:
        return "tests/languages/make/make_blueprint_export_contract.py"
    if category in {"connection", "placeholder"}:
        return "tests/blueprints/validation/test_placeholder_handoff_bridge.py"
    return "tests/mcp/tool_contracts/mcp_diff_blueprint_command_contract.py"


def _representative_evidence_path(
    findings: Sequence[Mapping[str, object]],
) -> str:
    paths = sorted(
        path
        for finding in findings
        if (path := _text_member(finding, "path")) is not None
    )
    return paths[0] if paths else "$"


def _rationale(*, category: str, module_type: str, finding_count: int) -> str:
    return (
        f"Repeated {category} blueprint diff findings appeared on "
        f"{module_type} "
        f"module paths ({finding_count} findings). Review whether an explicit "
        "rule, fixture, or TODO is warranted before changing generation "
        "behavior."
    )


def _proposed_todo_path(*, category: str, module_type: str) -> str:
    safe_category = _safe_slug(category.replace("/", "-")) or "unknown"
    safe_module = _safe_slug(module_type) or UNKNOWN_MODULE_TYPE
    return (
        f"{TEMP_DIFF_LEARNING_ROOT}/"
        f"{safe_category}-{safe_module}-learning-followup.md"
    )


def _todo_markdown(context: _TodoDraftContext) -> str:
    title = (
        f"Review repeated {context.category} blueprint diffs for"
        f"{context.module_type} modules"
    )
    return "\n".join(
        (
            f"# {title}",
            "",
            "## Task",
            (
                f"Decide whether {context.finding_count} repeated "
                f"{context.category} "
                f"diff findings on {context.module_type} module paths "
                f"require an "
                "explicit generation rule, fixture, or bounded follow-up TODO."
            ),
            "",
            "## Affected Files",
            f"- Target surface: `{context.target_surface}`",
            f"- Evidence path: `{context.evidence_path}`",
            f"- Suggested test path: `{context.suggested_test_path}`",
            "",
            "## ADR Impact",
            (
                "No ADR update is needed unless this follow-up starts creating "
                "pending "
                "TODO files directly or changes blueprint generation behavior."
            ),
            "",
            "## Validation",
            (
                f"- Add or update `{context.suggested_test_path}` if the rule "
                f"is accepted."
            ),
            "- Run the Diff blueprint MCP contract tests.",
            "",
            "## Stop Conditions",
            (
                "- Do not use private blueprint values as fixture names or "
                "expected "
                "output."
            ),
            "- Do not call Make.com or live services.",
            (
                "- Do not modify generation behavior without an explicit "
                "reviewed "
                "test."
            ),
            "",
        )
    )


def _safe_slug(value: str) -> str:
    lowered = value.strip().casefold().replace(" ", "-")
    sanitized = UNSAFE_SLUG_CHAR_PATTERN.sub("-", lowered)
    collapsed = re.sub(r"-{2,}", "-", sanitized)
    return collapsed.strip("-._/")


def _text_member(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
