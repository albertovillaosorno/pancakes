# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compute deterministic deltas between two Make AST JSON payloads.

Boundary contract:
- Owns: bounded recursive JSON-path deltas and local classified diff reports.
- Must not: interpret runtime equivalence, mutate payloads, or persist reports.
- Allows: added, removed, changed paths and ADR-shaped JSON-ready summaries.
- Split when validation, repair, or live comparison needs ownership.
- Merge when: another delta file reports the same path sets identically.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject
    from blueprints.validation.models import BlueprintDeltaCategory

type BlueprintDeltaChangeType = Literal["added", "removed", "changed"]
STRUCTURAL_NODE_PATH_SEGMENTS = (
    ".flow[",
    ".routes[",
    ".branches[",
    ".tools[",
    ".onerror[",
)
LAYOUT_DELTA_CATEGORIES: Final[frozenset[str]] = frozenset(("designer-layout",))
NON_SEMANTIC_DELTA_CATEGORIES: Final[frozenset[str]] = frozenset(
    ("designer-layout", "metadata")
)
LAYOUT_METADATA_ROOT_PATHS: Final[tuple[str, ...]] = (
    "$.metadata.groups",
    "$.metadata.notes",
    "$.metadata.orphans",
)
LAYOUT_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    ("designer", "groups", "notes", "orphans")
)


class BlueprintAstDelta(NamedTuple):
    """Bounded recursive diff summary for two AST payloads."""

    added_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        """Return whether any path changed."""
        return bool(
            self.added_paths or self.removed_paths or self.changed_paths
        )

    def as_dict(self) -> JsonObject:
        """Return a JSON-ready delta payload."""
        return {
            "has_changes": self.has_changes,
            "added_paths": list(self.added_paths),
            "removed_paths": list(self.removed_paths),
            "changed_paths": list(self.changed_paths),
        }


class BlueprintDeltaFinding(NamedTuple):
    """One classified difference between two blueprint payloads."""

    finding_id: str
    change_type: BlueprintDeltaChangeType
    category: BlueprintDeltaCategory
    path: str
    before: object = None
    after: object = None
    node_id: str | None = None

    @property
    def is_semantic(self) -> bool:
        """Return whether this finding can affect scenario behavior."""
        return self.category not in NON_SEMANTIC_DELTA_CATEGORIES

    def as_dict(self, *, include_values: bool = False) -> JsonObject:
        """Return a JSON-ready finding payload."""
        payload: JsonObject = {
            "finding_id": self.finding_id,
            "change_type": self.change_type,
            "category": self.category,
            "path": self.path,
            "node_id": self.node_id,
            "semantic": self.is_semantic,
        }
        if include_values:
            payload["before"] = _json_safe_value(self.before)
            payload["after"] = _json_safe_value(self.after)
        return payload


class BlueprintComparisonReport(NamedTuple):
    """ADR-shaped classified comparison report for two blueprint payloads."""

    label: str
    delta: BlueprintAstDelta
    findings: tuple[BlueprintDeltaFinding, ...]
    validation_findings: tuple[JsonObject, ...] = ()
    repair_candidates: tuple[JsonObject, ...] = ()
    evidence_gaps: tuple[JsonObject, ...] = ()

    @property
    def semantic_findings(self) -> tuple[BlueprintDeltaFinding, ...]:
        """Return findings that may affect scenario behavior."""
        return tuple(
            finding for finding in self.findings if finding.is_semantic
        )

    @property
    def layout_findings(self) -> tuple[BlueprintDeltaFinding, ...]:
        """Return findings that only affect designer layout parity."""
        return tuple(
            finding
            for finding in self.findings
            if finding.category in LAYOUT_DELTA_CATEGORIES
        )

    @property
    def summary(self) -> JsonObject:
        """Return compact deterministic report totals."""
        categories = sorted({finding.category for finding in self.findings})
        return {
            "label": self.label,
            "has_changes": self.delta.has_changes,
            "finding_count": len(self.findings),
            "semantic_finding_count": len(self.semantic_findings),
            "layout_finding_count": len(self.layout_findings),
            "categories": categories,
            "human_summary": _human_summary(
                label=self.label,
                finding_count=len(self.findings),
                semantic_count=len(self.semantic_findings),
            ),
        }

    def as_dict(self, *, include_values: bool = False) -> JsonObject:
        """Return a JSON-ready comparison report."""
        findings = tuple(
            finding.as_dict(include_values=include_values)
            for finding in self.findings
        )
        return {
            "summary": self.summary,
            "findings": list(findings),
            "added_nodes": list(_findings_for_change(findings, "added")),
            "removed_nodes": list(_findings_for_change(findings, "removed")),
            "changed_nodes": list(_findings_for_change(findings, "changed")),
            "layout_changes": list(
                _findings_for_categories(findings, ("designer-layout",))
            ),
            "mapping_changes": list(
                _findings_for_paths(findings, ("mapper", "parameters"))
            ),
            "control_flow_changes": list(
                _findings_for_categories(
                    findings, ("connection", "route/filter")
                )
            ),
            "layout_delta": list(
                _findings_for_categories(findings, ("designer-layout",))
            ),
            "filter_shape_delta": list(
                _findings_for_categories(findings, ("route/filter",))
            ),
            "mapper_shape_delta": list(
                _findings_for_paths(findings, ("mapper",))
            ),
            "metadata_expect_missing": list(
                _findings_for_paths(findings, ("metadata.expect",))
            ),
            "restore_missing": list(
                _findings_for_paths(findings, ("metadata.restore",))
            ),
            "runtime_resource_placeholder": list(
                _findings_for_categories(findings, ("placeholder",))
            ),
            "zero_trace_violation": list(
                _zero_trace_violation_findings(findings)
            ),
            "native_parity_gap": list(_native_parity_gap_findings(findings)),
            "validation_findings": list(self.validation_findings),
            "repair_candidates": list(self.repair_candidates),
            "evidence_gaps": list(self.evidence_gaps),
        }


def compute_ast_delta(
    before: JsonObject, after: JsonObject
) -> BlueprintAstDelta:
    """Return a deterministic recursive diff summary for two AST payloads."""
    _validate_json_payload(before)
    _validate_json_payload(after)
    builder = _DeltaBuilder()
    builder.diff(before, after, path="$")
    return BlueprintAstDelta(
        added_paths=tuple(builder.added_paths),
        removed_paths=tuple(builder.removed_paths),
        changed_paths=tuple(builder.changed_paths),
    )


def compare_blueprints(
    before: JsonObject,
    after: JsonObject,
    *,
    label: str,
) -> BlueprintComparisonReport:
    """Return a classified structured comparison report for two blueprints."""
    changes = _collect_path_changes(before, after)
    delta = BlueprintAstDelta(
        added_paths=tuple(
            change.path for change in changes if change.change_type == "added"
        ),
        removed_paths=tuple(
            change.path for change in changes if change.change_type == "removed"
        ),
        changed_paths=tuple(
            change.path for change in changes if change.change_type == "changed"
        ),
    )
    findings = tuple(
        BlueprintDeltaFinding(
            finding_id=f"{label}:{index + 1:04d}",
            change_type=change.change_type,
            category=_classify_change(change),
            path=change.path,
            before=change.before,
            after=change.after,
            node_id=_node_id_for_change(change),
        )
        for index, change in enumerate(changes)
    )
    return BlueprintComparisonReport(
        label=label, delta=delta, findings=findings
    )


class _DeltaBuilder:
    """Mutable collector scoped to one recursive delta walk."""

    __slots__ = ("added_paths", "changed_paths", "removed_paths")

    def __init__(self) -> None:
        """Create empty path buckets for one recursive delta walk."""
        self.added_paths: list[str] = []
        self.removed_paths: list[str] = []
        self.changed_paths: list[str] = []

    def diff(self, before: object, after: object, *, path: str) -> None:
        """Collect added, removed, and changed JSON paths recursively."""
        if isinstance(before, dict) and isinstance(after, dict):
            self._diff_mappings(
                cast("dict[object, object]", before),
                cast("dict[object, object]", after),
                path=path,
            )
            return
        if isinstance(before, list) and isinstance(after, list):
            self._diff_lists(
                cast("list[object]", before),
                cast("list[object]", after),
                path=path,
            )
            return
        if isinstance(before, dict | list) or isinstance(after, dict | list):
            self.changed_paths.append(path)
            return
        if _objects_differ(before, after):
            self.changed_paths.append(path)

    def _diff_mappings(
        self,
        before: dict[object, object],
        after: dict[object, object],
        *,
        path: str,
    ) -> None:
        """Collect mapping-level JSON path differences."""
        before_keys = _string_keys(before)
        after_keys = _string_keys(after)
        self.removed_paths.extend(
            f"{path}.{key}" for key in sorted(before_keys - after_keys)
        )
        self.added_paths.extend(
            f"{path}.{key}" for key in sorted(after_keys - before_keys)
        )
        for key in sorted(before_keys & after_keys):
            self.diff(before[key], after[key], path=f"{path}.{key}")

    def _diff_lists(
        self, before: list[object], after: list[object], *, path: str
    ) -> None:
        """Collect list-level JSON path differences."""
        shared_length = min(len(before), len(after))
        if len(before) > len(after):
            self.removed_paths.extend(
                f"{path}[{index}]"
                for index in range(shared_length, len(before))
            )
        elif len(after) > len(before):
            self.added_paths.extend(
                f"{path}[{index}]" for index in range(shared_length, len(after))
            )
        for index in range(shared_length):
            self.diff(before[index], after[index], path=f"{path}[{index}]")


def _objects_differ(before: object, after: object) -> bool:
    """Return whether two scalar-ish values differ by type or value."""
    return type(before) is not type(after) or before != after


def _string_keys(value: dict[object, object]) -> set[str]:
    """Return JSON object keys after validating that every key is text.

    Raises:
        TypeError: If a key has an invalid JSON shape.
    """
    keys: set[str] = set()
    for key in value:
        if not isinstance(key, str):
            message = "Blueprint delta object keys must be strings."
            raise TypeError(message)
        keys.add(key)
    return keys


def _validate_json_payload(value: object) -> None:
    """Validate JSON-like payloads recursively before path-level reporting.

    Raises:
        TypeError: If a key or value has an invalid JSON shape.
    """
    if isinstance(value, float) and not math.isfinite(value):
        message = "Blueprint delta JSON numbers must be finite."
        raise TypeError(message)
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        for key in _string_keys(mapping):
            _validate_json_payload(mapping[key])
        return
    if isinstance(value, list):
        for item in cast("list[object]", value):
            _validate_json_payload(item)


class _PathChange(NamedTuple):
    """Internal path change with optional before/after values."""

    change_type: BlueprintDeltaChangeType
    path: str
    before: object = None
    after: object = None


def _collect_path_changes(
    before: object, after: object
) -> tuple[_PathChange, ...]:
    _validate_json_payload(before)
    _validate_json_payload(after)
    builder = _ChangeBuilder()
    builder.diff(before, after, path="$")
    return tuple(builder.changes)


class _ChangeBuilder:
    """Mutable collector for classified delta input records."""

    __slots__ = ("changes",)

    def __init__(self) -> None:
        """Create an empty change bucket for one recursive delta walk."""
        self.changes: list[_PathChange] = []

    def diff(self, before: object, after: object, *, path: str) -> None:
        """Collect path-level change records recursively."""
        if isinstance(before, dict) and isinstance(after, dict):
            self._diff_mappings(
                cast("dict[object, object]", before),
                cast("dict[object, object]", after),
                path=path,
            )
            return
        if isinstance(before, list) and isinstance(after, list):
            self._diff_lists(
                cast("list[object]", before),
                cast("list[object]", after),
                path=path,
            )
            return
        if isinstance(before, dict | list) or isinstance(after, dict | list):
            self.changes.append(
                _PathChange(
                    "changed",
                    path,
                    cast("object", before),
                    cast("object", after),
                )
            )
            return
        if _objects_differ(before, after):
            self.changes.append(_PathChange("changed", path, before, after))

    def _diff_mappings(
        self,
        before: dict[object, object],
        after: dict[object, object],
        *,
        path: str,
    ) -> None:
        before_keys = _string_keys(before)
        after_keys = _string_keys(after)
        for key in sorted(before_keys - after_keys):
            self.changes.append(
                _PathChange("removed", f"{path}.{key}", before[key], None)
            )
        for key in sorted(after_keys - before_keys):
            self.changes.append(
                _PathChange("added", f"{path}.{key}", None, after[key])
            )
        for key in sorted(before_keys & after_keys):
            self.diff(before[key], after[key], path=f"{path}.{key}")

    def _diff_lists(
        self, before: list[object], after: list[object], *, path: str
    ) -> None:
        shared_length = min(len(before), len(after))
        for index in range(shared_length, len(before)):
            self.changes.append(
                _PathChange("removed", f"{path}[{index}]", before[index], None)
            )
        for index in range(shared_length, len(after)):
            self.changes.append(
                _PathChange("added", f"{path}[{index}]", None, after[index])
            )
        for index in range(shared_length):
            self.diff(before[index], after[index], path=f"{path}[{index}]")


def _classify_change(change: _PathChange) -> BlueprintDeltaCategory:
    path = change.path.casefold()
    category = cast("BlueprintDeltaCategory", "unknown")
    if _is_layout_change(change):
        category = "designer-layout"
    elif _path_has_any(
        path, (".routes", ".branches", ".tools", ".filter", ".conditions")
    ):
        category = "route/filter"
    elif (
        path.endswith(".version")
        or "module_version" in path
        or "app_version" in path
    ):
        category = "module-version"
    elif _value_has_placeholder(change.before) or _value_has_placeholder(
        change.after
    ):
        category = "placeholder"
    elif _is_connection_path(path):
        category = "connection"
    elif path == "$.metadata" or path.startswith("$.metadata."):
        category = "metadata"
    elif _path_has_any(
        path,
        (
            ".module",
            ".mapper",
            ".parameters",
            ".schedule",
            ".onerror",
            ".on_error",
        ),
    ):
        category = "semantic"
    return category


def _is_layout_change(change: _PathChange) -> bool:
    path = change.path.casefold()
    return (
        ".metadata.designer" in path
        or path.startswith(LAYOUT_METADATA_ROOT_PATHS)
        or _change_value_has_layout_metadata(change)
    )


def _change_value_has_layout_metadata(change: _PathChange) -> bool:
    return _value_has_layout_metadata(
        change.before
    ) or _value_has_layout_metadata(change.after)


def _value_has_layout_metadata(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    keys = {str(key).casefold() for key in cast("dict[object, object]", value)}
    return bool(keys & LAYOUT_METADATA_KEYS)


def _is_connection_path(path: str) -> bool:
    return _path_has_any(
        path,
        (
            ".connection",
            ".connections",
            ".source",
            ".target",
            ".from",
            ".to",
            ".next",
            *STRUCTURAL_NODE_PATH_SEGMENTS,
        ),
    )


def _path_has_any(path: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in path for fragment in fragments)


def _value_has_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return "{{" in value or "}}" in value
    if isinstance(value, dict):
        return any(
            _value_has_placeholder(item)
            for item in cast("dict[object, object]", value).values()
        )
    if isinstance(value, list):
        return any(
            _value_has_placeholder(item) for item in cast("list[object]", value)
        )
    return False


def _node_id_for_change(change: _PathChange) -> str | None:
    for value in (change.after, change.before):
        if isinstance(value, dict):
            raw_id = cast("dict[object, object]", value).get("id")
            if isinstance(raw_id, bool):
                continue
            if isinstance(raw_id, int) and raw_id > 0:
                return str(raw_id)
            if isinstance(raw_id, str):
                text = str(raw_id).strip()
                if text:
                    return text
    return None


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe_value(item)
            for key, item in cast("dict[object, object]", value).items()
        }
    if isinstance(value, list):
        return [_json_safe_value(item) for item in cast("list[object]", value)]
    return repr(value)


def _findings_for_change(
    findings: tuple[JsonObject, ...],
    change_type: BlueprintDeltaChangeType,
) -> tuple[JsonObject, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.get("change_type") == change_type
    )


def _findings_for_categories(
    findings: tuple[JsonObject, ...],
    categories: tuple[str, ...],
) -> tuple[JsonObject, ...]:
    category_set = set(categories)
    return tuple(
        finding
        for finding in findings
        if finding.get("category") in category_set
    )


def _findings_for_paths(
    findings: tuple[JsonObject, ...],
    fragments: tuple[str, ...],
) -> tuple[JsonObject, ...]:
    return tuple(
        finding
        for finding in findings
        if any(
            fragment in str(finding.get("path", "")).casefold()
            for fragment in fragments
        )
    )


def _zero_trace_violation_findings(
    findings: tuple[JsonObject, ...],
) -> tuple[JsonObject, ...]:
    return tuple(
        finding
        for finding in findings
        if _path_or_payload_has_private_export_trace(finding)
    )


def _path_or_payload_has_private_export_trace(finding: JsonObject) -> bool:
    serialized = json.dumps(finding, sort_keys=True).casefold()
    return any(
        marker in serialized
        for marker in (
            "local-only",
            "local draft",
            "runtime placeholder",
            "source_draft",
            "pancakes",
        )
    )


def _native_parity_gap_findings(
    findings: tuple[JsonObject, ...],
) -> tuple[JsonObject, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.get("category")
        in {
            "connection",
            "metadata",
            "module-version",
            "placeholder",
            "route/filter",
            "semantic",
        }
    )


def _human_summary(
    *, label: str, finding_count: int, semantic_count: int
) -> str:
    if finding_count == 0:
        return (
            f"{label}: no structural blueprint differences found. "
            "No auto-patch was applied."
        )
    return (
        f"{label}: {finding_count} structured difference(s), "
        f"{semantic_count} semantic. No auto-patch was applied."
    )
