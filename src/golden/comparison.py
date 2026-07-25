# ruff: noqa: PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno. All rights reserved.
"""Deterministic Golden blueprint comparison helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(frozen=True)
class GoldenFinding:
    """One Golden comparison finding."""

    code: str
    message: str
    path: str
    severity: str = "error"

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-shaped finding."""
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class GoldenEvidenceGap:
    """One unresolved evidence gap that blocks promotion."""

    code: str
    message: str
    path: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-shaped evidence gap."""
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True)
class GoldenComparison:
    """Semantic and layout comparison details."""

    semantic_findings: tuple[GoldenFinding, ...]
    layout_findings: tuple[GoldenFinding, ...]
    removed_nodes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-shaped comparison payload."""
        return {
            "semantic_findings": [
                item.as_dict() for item in self.semantic_findings
            ],
            "layout_findings": [
                item.as_dict() for item in self.layout_findings
            ],
            "removed_nodes": list(self.removed_nodes),
        }


@dataclass(frozen=True)
class GoldenSetupReadinessReport:
    """Setup readiness dimension for Golden completion."""

    client_ready: bool
    diagnostics: tuple[Mapping[str, object], ...] = ()
    dimension: str = "setup_readiness"

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-shaped setup readiness payload."""
        return {
            "dimension": self.dimension,
            "client_ready": self.client_ready,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


@dataclass(frozen=True)
class GoldenComparisonReport:
    """Golden comparison report."""

    label: str
    semantic_parity: bool
    layout_parity: bool
    completion_allowed: bool
    completion_blockers: tuple[str, ...]
    comparison: GoldenComparison
    evidence_gaps: tuple[GoldenEvidenceGap, ...]
    privacy_findings: tuple[GoldenFinding, ...] = ()
    setup_readiness: GoldenSetupReadinessReport = GoldenSetupReadinessReport(
        client_ready=True
    )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-shaped report."""
        return {
            "label": self.label,
            "semantic_parity": self.semantic_parity,
            "layout_parity": self.layout_parity,
            "completion_allowed": self.completion_allowed,
            "completion_blockers": list(self.completion_blockers),
            "comparison": self.comparison.as_dict(),
            "evidence_gaps": [item.as_dict() for item in self.evidence_gaps],
            "privacy_findings": [
                item.as_dict() for item in self.privacy_findings
            ],
            "setup_readiness": self.setup_readiness.as_dict(),
        }


def compare_golden_blueprint_texts(
    *,
    reference_text: str,
    generated_text: str,
    label: str,
    evidence_gaps: tuple[GoldenEvidenceGap, ...] = (),
    enable_privacy_filter: bool = False,
    designer_diagnostics: tuple[Mapping[str, object], ...] = (),
) -> GoldenComparisonReport:
    """Compare reference and generated Golden blueprint JSON text.

    Returns:
        Golden comparison report.
    """
    reference = json.loads(reference_text)
    generated = json.loads(generated_text)
    privacy_findings: tuple[GoldenFinding, ...] = ()
    setup_readiness: GoldenSetupReadinessReport = GoldenSetupReadinessReport(
        client_ready=True
    )
    if enable_privacy_filter:
        reference, generated, privacy_findings = apply_privacy_review(
            reference, generated
        )
    semantic_findings = tuple(
        compare_values(strip_layout(reference), strip_layout(generated))
    )
    layout_findings = tuple(compare_layout(reference, generated))
    removed_nodes = tuple(removed_flow_nodes(reference, generated))
    blockers: list[str] = []
    setup_readiness = GoldenSetupReadinessReport(
        client_ready=not designer_diagnostics,
        diagnostics=designer_diagnostics,
    )
    if not setup_readiness.client_ready:
        blockers.append("setup_readiness")
    if semantic_findings:
        blockers.append("semantic_difference")
    if evidence_gaps:
        blockers.append("evidence_gap")
    privacy_errors = [
        item for item in privacy_findings if item.severity == "error"
    ]
    privacy_critical = [
        item for item in privacy_findings if item.severity == "critical"
    ]
    if privacy_errors:
        blockers.append("privacy_error")
    if privacy_critical:
        blockers.append("privacy_critical")
    return GoldenComparisonReport(
        label=label,
        semantic_parity=not semantic_findings,
        layout_parity=not layout_findings,
        completion_allowed=not blockers,
        completion_blockers=tuple(dict.fromkeys(blockers)),
        comparison=GoldenComparison(
            semantic_findings=semantic_findings,
            layout_findings=layout_findings,
            removed_nodes=removed_nodes,
        ),
        evidence_gaps=evidence_gaps,
        privacy_findings=privacy_findings,
        setup_readiness=setup_readiness,
    )


def strip_layout(value: JsonValue) -> JsonValue:
    """Return value without designer layout coordinates."""
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if key == "designer":
                continue
            nested = strip_layout(item)
            if key == "metadata" and nested == {}:
                result[key] = nested
                continue
            result[key] = nested
        return result
    if isinstance(value, list):
        return [strip_layout(item) for item in value]
    return value


def compare_values(
    reference: JsonValue, generated: JsonValue, path: str = "$"
) -> list[GoldenFinding]:
    """Return semantic findings between two JSON-shaped values."""
    if type(reference) is not type(generated):
        return [GoldenFinding("semantic.type", "JSON type changed.", path)]
    if isinstance(reference, dict) and isinstance(generated, dict):
        findings: list[GoldenFinding] = []
        for key in sorted(set(reference) | set(generated)):
            child_path = f"{path}.{key}"
            if key not in generated:
                findings.append(
                    GoldenFinding(
                        "semantic.missing", "Value removed.", child_path
                    )
                )
            elif key not in reference:
                findings.append(
                    GoldenFinding("semantic.added", "Value added.", child_path)
                )
            else:
                findings.extend(
                    compare_values(reference[key], generated[key], child_path)
                )
        return findings
    if isinstance(reference, list) and isinstance(generated, list):
        findings = []
        common = min(len(reference), len(generated))
        for index in range(common):
            child_path = f"{path}[{index}]"
            findings.extend(
                compare_values(reference[index], generated[index], child_path)
            )
        if len(reference) != len(generated):
            findings.append(
                GoldenFinding("semantic.length", "List length changed.", path)
            )
        return findings
    if reference != generated:
        return [GoldenFinding("semantic.value", "Value changed.", path)]
    return []


def compare_layout(
    reference: JsonValue, generated: JsonValue, path: str = "$"
) -> list[GoldenFinding]:
    """Return layout-only findings."""
    if isinstance(reference, dict) and isinstance(generated, dict):
        findings: list[GoldenFinding] = []
        if (
            "designer" in reference or "designer" in generated
        ) and reference.get("designer") != generated.get("designer"):
            findings.append(
                GoldenFinding(
                    "layout.designer",
                    "Designer layout changed.",
                    f"{path}.designer",
                    "warning",
                )
            )
        for key in sorted(set(reference) & set(generated)):
            findings.extend(
                compare_layout(reference[key], generated[key], f"{path}.{key}")
            )
        return findings
    if isinstance(reference, list) and isinstance(generated, list):
        findings = []
        for index, (left, right) in enumerate(
            zip(reference, generated, strict=False)
        ):
            child_path = f"{path}[{index}]"
            findings.extend(compare_layout(left, right, child_path))
        return findings
    return []


def removed_flow_nodes(reference: JsonValue, generated: JsonValue) -> list[str]:
    """Return node ids present in reference but absent from generated."""
    reference_ids = flow_ids(reference)
    generated_ids = flow_ids(generated)
    return [str(item) for item in sorted(reference_ids - generated_ids)]


def flow_ids(value: JsonValue) -> set[int]:
    """Return Make flow node ids from a JSON-shaped value."""
    ids: set[int] = set()
    if isinstance(value, dict):
        node_id = value.get("id")
        if isinstance(node_id, int) and "module" in value:
            ids.add(node_id)
        for item in value.values():
            ids.update(flow_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(flow_ids(item))
    return ids


def apply_privacy_review(
    reference: JsonValue, generated: JsonValue
) -> tuple[JsonValue, JsonValue, tuple[GoldenFinding, ...]]:
    """Apply privacy-aware comparison normalization.

    Returns:
        Sanitized reference, sanitized generated value, and privacy findings.
    """
    findings: list[GoldenFinding] = []
    if contains_account_label(generated):
        findings.append(
            GoldenFinding(
                "privacy.private_label_preserved",
                "Generated output preserved a nonfunctional "
                "private/account label.",
                "$.metadata.account_label",
                "critical",
            )
        )
    reference_safe = remove_account_label(reference)
    generated_safe = remove_account_label(generated)
    if reference_safe != reference and generated_safe == generated:
        findings.append(
            GoldenFinding(
                "privacy.private_label_removed",
                "Generated output removed a nonfunctional "
                "private/account label.",
                "$.metadata.account_label",
                "info",
            )
        )
    if contains_private_url(reference) and not contains_private_url(generated):
        findings.append(
            GoldenFinding(
                "privacy.behavior_required_value_removed",
                "Behavior-required private-like value was removed from "
                "generated output.",
                "$.flow",
                "error",
            )
        )
    return reference_safe, generated_safe, tuple(findings)


def contains_account_label(value: JsonValue) -> bool:
    """Return whether a nonfunctional account label is present."""
    if isinstance(value, dict):
        return "account_label" in value or any(
            contains_account_label(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(contains_account_label(item) for item in value)
    return False


def remove_account_label(value: JsonValue) -> JsonValue:
    """Remove nonfunctional account labels.

    Returns:
        Value with account labels removed.
    """
    if isinstance(value, dict):
        return {
            key: remove_account_label(item)
            for key, item in value.items()
            if key != "account_label"
        }
    if isinstance(value, list):
        return [remove_account_label(item) for item in value]
    return value


def contains_private_url(value: JsonValue) -> bool:
    """Return whether a behavior-required private-like URL remains."""
    if isinstance(value, str):
        return "synthetic-private" in value
    if isinstance(value, dict):
        return any(contains_private_url(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_private_url(item) for item in value)
    return False
