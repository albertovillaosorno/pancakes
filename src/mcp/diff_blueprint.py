# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001062#repo.paths.data.repository-relative-only
# - 001068#repo.operator-commands.command-registry
# - 001068#repo.operator-commands.diff-blueprint.structured-comparison
# - 001068#repo.operator-commands.live-service-boundary
# - 001069#repo.system-locations.major-path-map
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""MCP workflow for the Diff blueprint operator command.

Boundary contract:
- Owns: repository-local file inputs and aggregate response shape for internal
blueprint deltas.
- Must not: call Make.com, mutate blueprints, persist reports, or run live
validation.
- Allows: AST parsing, classified local comparisons, and strict redaction by
default.
- Split when: validation or repair sections become independently executable
tools.
- Merge when: the MCP executor directly owns the same Diff blueprint workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from blueprints.ast import compare_blueprints, parse_make_ast_json_text
from blueprints.repair.diff_learning import draft_diff_learning_suggestions
from languages.make.evidence import (
    make_evidence_entry,
    make_internal_evidence_availability,
    make_internal_evidence_ledger,
)
from languages.make.module_manifests import (
    make_module_projector_manifest_for_native_token,
)
from languages.make.parity_confidence import (
    MakeParityConfidence,
    make_native_parity_confidence_summary,
    normalize_make_parity_confidence,
    tune_make_native_diff_severity,
)
from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast import BlueprintComparisonReport
    from blueprints.ast.models import JsonObject

REDACTION_MODE_STRICT: Final = "strict"
REDACTION_MODE_NONE: Final = "none"
SUPPORTED_REDACTION_MODES: Final[frozenset[str]] = frozenset(
    (REDACTION_MODE_STRICT, REDACTION_MODE_NONE)
)
BLUEPRINT_DIFF_TEMP_ROOT: Final[Path] = Path("temp") / "diff-blueprint"
BLUEPRINT_DIFF_PROJECT_ROOT: Final[Path] = Path("projects")
BLUEPRINT_DIFF_FIXTURE_ROOT: Final[Path] = (
    Path("tests") / "blueprints" / "fixtures" / "diff_blueprint"
)
APPROVED_BLUEPRINT_DIFF_ROOTS: Final[tuple[Path, ...]] = (
    BLUEPRINT_DIFF_PROJECT_ROOT,
    BLUEPRINT_DIFF_TEMP_ROOT,
    BLUEPRINT_DIFF_FIXTURE_ROOT,
)
APPROVED_BLUEPRINT_DIFF_ROOTS_BY_ARGUMENT: Final[
    dict[str, tuple[Path, ...]]
] = {
    "generated_path": APPROVED_BLUEPRINT_DIFF_ROOTS,
    "make_exported_path": APPROVED_BLUEPRINT_DIFF_ROOTS,
    "known_good_path": APPROVED_BLUEPRINT_DIFF_ROOTS,
}
MAKE_NATIVE_DIFF_CATEGORIES: Final[tuple[str, ...]] = (
    "layout_delta ",
    "filter_shape_delta ",
    "mapper_shape_delta ",
    "metadata_expect_missing ",
    "restore_missing ",
    "runtime_resource_placeholder ",
    "zero_trace_violation ",
    "native_parity_gap ",
    "volatile_make_noise ",
    "semantic_lineage_breakage ",
    "pass_through_unknown_module",
)
MAKE_NATIVE_DIFF_SEVERITY: Final[dict[str, str]] = {
    "filter_shape_delta": "P0 ",
    "mapper_shape_delta": "P0 ",
    "semantic_lineage_breakage": "P0 ",
    "zero_trace_violation": "P0 ",
    "metadata_expect_missing": "P1 ",
    "native_parity_gap": "P1 ",
    "pass_through_unknown_module": "P1 ",
    "restore_missing": "P1 ",
    "runtime_resource_placeholder": "P1 ",
    "layout_delta": "P2 ",
    "volatile_make_noise": "P2",
}
ROUNDTRIP_DISCOVERY_CLASSES: Final[tuple[str, ...]] = (
    "volatile_noise ",
    "native_shape_rule ",
    "layout_rule ",
    "restore_expect_rule ",
    "runtime_binding_rule ",
    "semantic_breakage ",
    "zero_trace_violation ",
    "unknown_requires_evidence",
)
ROUNDTRIP_GENERALIZATION_TARGETS: Final[dict[str, tuple[str, ...]]] = {
    "volatile_noise": ("canonicalizer_rule",),
    "native_shape_rule": (
        "fixture_family ",
        "semantic_diff_finding ",
        "projector_rule ",
        "manifest_or_matrix_update",
    ),
    "layout_rule": ("fixture_family", "layout_rule"),
    "restore_expect_rule": (
        "fixture_family ",
        "manifest_or_matrix_update ",
        "projector_rule",
    ),
    "runtime_binding_rule": ("risk_model_rule", "semantic_diff_finding"),
    "semantic_breakage": (
        "semantic_diff_finding ",
        "projector_rule ",
        "risk_model_rule",
    ),
    "zero_trace_violation": ("semantic_diff_finding", "risk_model_rule"),
    "unknown_requires_evidence": ("quarantine_evidence",),
}
ROUNDTRIP_CLASS_ACTIONS: Final[dict[str, str]] = {
    "volatile_noise": (
        "Add a canonicalizer rule only after proving the field is volatile."
    ),
    "native_shape_rule": (
        "Promote the delta into a module projector, manifest, or matrix rule."
    ),
    "layout_rule": (
        "Promote repeated editor geometry deltas into the Make layout policy."
    ),
    "restore_expect_rule": (
        "Promote UI schema deltas into metadata.expect or restore generation."
    ),
    "runtime_binding_rule": (
        "Review resource placeholders and update readiness or binding policy."
    ),
    "semantic_breakage": (
        "Treat the delta as behavior-changing until a fixture proves otherwise."
    ),
    "zero_trace_violation": (
        "Block export parity until private/local trace text is removed."
    ),
    "unknown_requires_evidence": (
        "Quarantine until another fixture or corpus sample exists."
    ),
}
MAKE_NATIVE_DIFF_GROUP_ACTIONS: Final[dict[str, str]] = {
    "filter_shape_delta": (
        "Lower route filters into the Make-native module filter shape."
    ),
    "mapper_shape_delta": (
        "Update the Make module projector so mapper shape matches native "
        "exports."
    ),
    "metadata_expect_missing": (
        "Generate Make-native metadata.expect for this module family."
    ),
    "restore_missing": (
        "Generate safe metadata.restore entries for known Make UI selectors."
    ),
    "runtime_resource_placeholder": (
        "Review runtime resource placeholders before client handoff."
    ),
    "zero_trace_violation": (
        "Remove private/local trace strings before exporting the Make "
        "blueprint."
    ),
    "layout_delta": (
        "Apply the Make-native layout policy or accept the visual delta."
    ),
    "semantic_lineage_breakage": (
        "Review as behavior-changing until a DAMP lineage or roundtrip "
        "fixture proves otherwise."
    ),
    "volatile_make_noise": (
        "Promote to canonicalizer rules only when repeated Make exports "
        "prove volatility."
    ),
    "pass_through_unknown_module": (
        "Keep the module pass-through safe and collect corpus evidence "
        "before projector promotion."
    ),
}
ZERO_TRACE_PRIVATE_MARKERS: Final[tuple[str, ...]] = (
    "pancakes ",
    "schoenwald ",
    "local-only ",
    "local draft ",
    "runtime placeholder ",
    "source_draft ",
    "draft_id ",
    "project_id ",
    "blueprints.ast ",
    "languages/make",
    "/mnt/",
    "c:\\",
    "apikey ",
    "api key ",
    "accesstoken ",
    "access token ",
    "credential value ",
    "secret",
)
ZERO_TRACE_FINDING_LIMIT: Final = 25
VOLATILE_MAKE_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    (
        "lastModified ",
        "last_modified ",
        "lastRun ",
        "last_run ",
        "modifiedAt ",
        "modified_at ",
        "revision ",
        "timestamp ",
        "updatedAt ",
        "updated_at",
    )
)
VOLATILE_MAKE_FIELD_PATH_FRAGMENTS: Final[tuple[str, ...]] = (
    ".metadata.designer.messages",
)
VOLATILE_MAKE_FALSE_DEFAULT_FIELD_PATHS: Final[frozenset[str]] = frozenset(
    ("$.metadata.instant",)
)


def blueprint_diff_artifact_policy() -> JsonObject:
    """Return the approved artifact roots and privacy posture for local.

    blueprint.

    deltas.
    """
    return {
        "approved_roots": _root_texts(APPROVED_BLUEPRINT_DIFF_ROOTS),
        "generated_roots": _root_texts(
            APPROVED_BLUEPRINT_DIFF_ROOTS_BY_ARGUMENT["generated_path"]
        ),
        "make_exported_roots": _root_texts(
            APPROVED_BLUEPRINT_DIFF_ROOTS_BY_ARGUMENT["make_exported_path"]
        ),
        "known_good_roots": _root_texts(
            APPROVED_BLUEPRINT_DIFF_ROOTS_BY_ARGUMENT["known_good_path"]
        ),
        "real_export_root": BLUEPRINT_DIFF_TEMP_ROOT.as_posix(),
        "real_export_git_posture": "ignored_by_default",
        "sanitized_committed_roots": _root_texts(
            (BLUEPRINT_DIFF_PROJECT_ROOT, BLUEPRINT_DIFF_FIXTURE_ROOT)
        ),
        "required_posture": (
            (
                "Real Make exports stay under temp/diff-blueprint unless "
                "sanitized."
            ),
            (
                "Committed project and fixture artifacts must be synthetic or "
                "redacted."
            ),
            "Paths must be repository-relative and stay inside approved roots.",
        ),
    }


def diff_blueprint(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Run the local Diff blueprint workflow.

    Returns:
        The structured, machine-readable comparison report.
    """
    generated_path = _required_path(arguments, "generated_path", repo_root)
    make_exported_path = _required_path(
        arguments, "make_exported_path", repo_root
    )
    known_good_path = _required_path(arguments, "known_good_path", repo_root)
    label = _optional_text(arguments.get("label")) or "diff-blueprint"
    redaction_mode = _redaction_mode(arguments.get("redaction_mode"))
    output_mode = _output_mode(arguments.get("output_mode"))
    generated = _read_blueprint(generated_path)
    make_exported = _read_blueprint(make_exported_path)
    known_good = _read_blueprint(known_good_path)
    source_payloads = (generated, make_exported, known_good)
    comparison_payloads, canonicalization = _canonicalized_source_payloads(
        source_payloads=source_payloads
    )
    reports = (
        compare_blueprints(
            comparison_payloads[0],
            comparison_payloads[1],
            label=f"{label}:generated_vs_make_exported",
        ),
        compare_blueprints(
            comparison_payloads[0],
            comparison_payloads[2],
            label=f"{label}:generated_vs_known_good",
        ),
        compare_blueprints(
            comparison_payloads[1],
            comparison_payloads[2],
            label=f"{label}:make_exported_vs_known_good",
        ),
    )
    payload = _aggregate_reports(
        reports=reports,
        source_payloads=source_payloads,
        include_values=redaction_mode == REDACTION_MODE_NONE,
        label=label,
        redaction_mode=redaction_mode,
    )
    summary = cast("JsonObject", payload["summary"])
    summary["canonicalization_removed_field_count"] = canonicalization.get(
        "removed_volatile_field_count", 0
    )
    payload["canonicalization"] = canonicalization
    payload["status"] = "ok"
    _attach_diff_internal_evidence(
        payload=payload,
        canonicalization=canonicalization,
        include_internal_evidence=_optional_bool(
            arguments.get("include_internal_evidence"),
            default=False,
        ),
    )
    payload["inputs"] = {
        "generated_path": relative_to_repo(repo_root, generated_path),
        "make_exported_path": relative_to_repo(repo_root, make_exported_path),
        "known_good_path": relative_to_repo(repo_root, known_good_path),
        "label": label,
        "redaction_mode": redaction_mode,
    }
    payload["artifact_policy"] = blueprint_diff_artifact_policy()
    if output_mode == "compact":
        return _compact_diff_payload(payload)
    payload["output_mode"] = output_mode
    return payload


def _output_mode(value: object) -> str:
    text = _optional_text(value)
    if text is None:
        return "full"
    normalized = text.strip().casefold()
    if normalized not in {"compact", "full"}:
        message = "output_mode must be compact or full."
        raise ValueError(message)
    return normalized


def _compact_diff_payload(payload: JsonObject) -> JsonObject:
    """Return grouped and bounded blueprint diff output without raw finding.

    walls.
    """
    summary = _object_member(payload, "summary")
    grouped_deltas = tuple(
        cast("list[JsonObject]", payload.get("grouped_deltas", []))[:20]
    )
    return {
        "status": payload.get("status"),
        "output_mode": "compact",
        "summary": summary,
        "grouped_deltas": grouped_deltas,
        "grouped_delta_count": len(
            cast("list[JsonObject]", payload.get("grouped_deltas", []))
        ),
        "raw_findings_available": bool(payload.get("findings")),
        "raw_comparisons_available": bool(payload.get("comparisons")),
        "learning_suggestion_count": len(
            cast("list[object]", payload.get("learning_suggestions", []))
        ),
        "roundtrip_discovery": payload.get("roundtrip_discovery"),
        "internal_evidence": payload.get("internal_evidence"),
        "inputs": payload.get("inputs"),
        "artifact_policy": payload.get("artifact_policy"),
        "next_query": (
            "Use output_mode=full to inspect raw diff findings and comparisons."
        ),
    }


def _attach_diff_internal_evidence(
    *,
    payload: JsonObject,
    canonicalization: JsonObject,
    include_internal_evidence: bool,
) -> None:
    """Attach public-safe or opt-in private evidence to a diff payload."""
    evidence_ledger = _diff_internal_evidence_ledger(
        findings=cast("Sequence[JsonObject]", payload["findings"]),
        canonicalization=canonicalization,
    )
    payload["internal_evidence"] = make_internal_evidence_availability(
        evidence_ledger
    )
    if include_internal_evidence:
        payload["internal_evidence_ledger"] = evidence_ledger


def _required_path(
    arguments: Mapping[str, object], key: str, repo_root: Path
) -> Path:
    text = _optional_text(arguments.get(key))
    if text is None:
        message = f"Missing required argument: {key}"
        raise ValueError(message)
    path = resolve_repo_relative_path(repo_root, Path(text))
    _require_approved_artifact_root(
        argument_name=key,
        repo_root=repo_root,
        path=path,
        submitted_path=text,
    )
    if not path.is_file():
        message = f"Blueprint input file is missing: {text}"
        raise FileNotFoundError(message)
    return path


def _read_blueprint(path: Path) -> JsonObject:
    try:
        source_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        message = f"Blueprint input must be UTF-8 JSON: {path.name}"
        raise ValueError(message) from exc
    root = parse_make_ast_json_text(source_text)
    return root.raw_payload


def _canonicalized_source_payloads(
    *,
    source_payloads: Sequence[JsonObject],
) -> tuple[tuple[JsonObject, ...], JsonObject]:
    """Return Make-canonical comparison payloads and redacted canonicalization.

    evidence.

    Raises:
    TypeError: If canonicalization ever changes the blueprint root away from an
    object.
    """
    source_names = ("generated", "make_exported", "known_good")
    canonicalized: list[JsonObject] = []
    source_reports: list[JsonObject] = []
    removed_total = 0
    for source_name, payload in zip(
        source_names, source_payloads, strict=False
    ):
        removed_paths: list[str] = []
        canonicalized_payload = _canonicalize_make_value(
            payload,
            path="$",
            removed_paths=removed_paths,
        )
        if not isinstance(canonicalized_payload, dict):
            message = "Canonicalized blueprint root must remain an object."
            raise TypeError(message)
        canonicalized.append(cast("JsonObject", canonicalized_payload))
        removed_total += len(removed_paths)
        source_reports.append(
            {
                "source": source_name,
                "removed_volatile_field_count": len(removed_paths),
                "example_paths": tuple(removed_paths[:5]),
            }
        )
    return (
        tuple(canonicalized),
        {
            "enabled": True,
            "key_order_normalized": True,
            "removed_volatile_field_count": removed_total,
            "volatile_field_names": tuple(sorted(VOLATILE_MAKE_FIELD_NAMES)),
            "sources": tuple(source_reports),
        },
    )


def _canonicalize_make_value(
    value: object,
    *,
    path: str,
    removed_paths: list[str],
) -> object:
    """Return the computed result for the caller."""
    if isinstance(value, dict):
        canonical: dict[str, object] = {}
        for key, item in sorted(
            cast("dict[object, object]", value).items(), key=_key_sort_text
        ):
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_volatile_make_field(key_text, child_path, item):
                removed_paths.append(child_path)
                continue
            canonical[key_text] = _canonicalize_make_value(
                item,
                path=child_path,
                removed_paths=removed_paths,
            )
        return canonical
    if isinstance(value, list):
        return [
            _canonicalize_make_value(
                item, path=f"{path}[{index}]", removed_paths=removed_paths
            )
            for index, item in enumerate(cast("list[object]", value))
        ]
    return value


def _diff_internal_evidence_ledger(
    *,
    findings: Sequence[JsonObject],
    canonicalization: JsonObject,
) -> JsonObject:
    """Return private evidence rows for diff classification judgments."""
    entries: list[JsonObject] = [
        make_evidence_entry(
            evidence_type="canonicalizer_rule",
            judgment="volatile_make_field_canonicalization",
            source_id="mcp.diff_blueprint.canonicalizer",
            rule_id="make.diff.volatile_fields",
            confidence="local_rule",
            detail={
                "removed_volatile_field_count": _int_member(
                    canonicalization,
                    "removed_volatile_field_count",
                ),
            },
        )
    ]
    grouped = _grouped_native_parity_deltas(findings)
    for group in grouped:
        category = str(group.get("category") or "native_parity_gap")
        entries.append(
            make_evidence_entry(
                evidence_type="semantic_diff_category",
                judgment="make_native_diff_classification",
                source_id=f"make.diff.category.{category}",
                rule_id=f"make.diff.category.{category}",
                category=category,
                confidence=str(group.get("confidence") or "low"),
                detail={
                    "confidence": str(group.get("confidence") or "low"),
                    "count": _diff_count(group),
                    "roundtrip_discovery_class": str(
                        group.get("roundtrip_discovery_class")
                        or "unknown_requires_evidence"
                    ),
                },
            )
        )
        discovery_class = str(group.get("roundtrip_discovery_class") or "")
        if discovery_class:
            entries.append(
                make_evidence_entry(
                    evidence_type="risk_model_rule",
                    judgment="roundtrip_discovery_risk_model",
                    source_id=f"make.diff.discovery.{discovery_class}",
                    rule_id=f"make.diff.discovery.{discovery_class}",
                    category=category,
                    confidence=str(group.get("confidence") or "low"),
                )
            )
    if any(
        finding.get("native_parity_category") == "zero_trace_violation"
        for finding in findings
    ):
        entries.append(
            make_evidence_entry(
                evidence_type="zero_trace_rule",
                judgment="diff_input_private_trace_scan",
                source_id="mcp.diff_blueprint.zero_trace_scan",
                rule_id="make.diff.zero_trace.private_markers",
                confidence="hard_gate",
            )
        )
    return make_internal_evidence_ledger(tuple(entries))


def _is_volatile_make_field(key: str, path: str, value: object) -> bool:
    """Return whether a field is known volatile editor/export noise."""
    normalized_key = key.casefold()
    normalized_path = path.casefold()
    if normalized_key in {
        field.casefold() for field in VOLATILE_MAKE_FIELD_NAMES
    }:
        return True
    if (
        isinstance(value, bool)
        and not value
        and normalized_path
        in {
            field_path.casefold()
            for field_path in VOLATILE_MAKE_FALSE_DEFAULT_FIELD_PATHS
        }
    ):
        return True
    return any(
        fragment in normalized_path
        for fragment in VOLATILE_MAKE_FIELD_PATH_FRAGMENTS
    )


def _aggregate_reports(
    *,
    reports: Sequence[BlueprintComparisonReport],
    source_payloads: Sequence[JsonObject],
    include_values: bool,
    label: str,
    redaction_mode: str,
) -> JsonObject:
    comparisons = tuple(
        report.as_dict(include_values=include_values) for report in reports
    )
    findings = _make_native_classified_findings(_tagged_findings(comparisons))
    findings.extend(
        _runtime_resource_source_findings(
            source_payloads=source_payloads, label=label
        )
    )
    findings.extend(
        _zero_trace_source_findings(
            source_payloads=source_payloads, label=label
        )
    )
    findings.extend(
        _pass_through_unknown_module_source_findings(
            source_payloads=source_payloads, label=label
        )
    )
    validation_findings: list[object] = []
    repair_candidates: list[object] = []
    evidence_gaps = [_local_only_evidence_gap()]
    learning_suggestions = draft_diff_learning_suggestions(
        findings=findings,
        source_payloads=source_payloads,
    )
    grouped_deltas = _grouped_native_parity_deltas(findings)
    return {
        "summary": {
            "label": label,
            "comparison_count": len(comparisons),
            "finding_count": len(findings),
            "grouped_delta_count": len(grouped_deltas),
            "learning_suggestion_count": len(learning_suggestions),
            "semantic_finding_count": sum(
                1
                for finding in findings
                if isinstance(finding.get("semantic"), bool)
                and finding.get("semantic")
            ),
            "native_parity_category_counts": _native_parity_category_counts(
                findings
            ),
            "native_parity_confidence_counts": _native_parity_confidence_counts(
                findings
            ),
            "native_parity_confidence": make_native_parity_confidence_summary(),
            "roundtrip_discovery_class_counts": (
                _roundtrip_discovery_class_counts(findings)
            ),
            "p0_delta_count": _native_parity_severity_count(findings, "P0"),
            "p1_delta_count": _native_parity_severity_count(findings, "P1"),
            "p2_delta_count": _native_parity_severity_count(findings, "P2"),
            "redaction_mode": redaction_mode,
            "human_summary": _human_summary(label=label, findings=findings),
        },
        "comparisons": list(comparisons),
        "findings": findings,
        "grouped_deltas": grouped_deltas,
        "added_nodes": _findings_for_change(findings, "added"),
        "removed_nodes": _findings_for_change(findings, "removed"),
        "changed_nodes": _findings_for_change(findings, "changed"),
        "mapping_changes": _findings_for_paths(
            findings, ("mapper", "parameters")
        ),
        "control_flow_changes": _findings_for_categories(
            findings,
            ("connection", "route/filter"),
        ),
        "make_native_parity_changes": {
            category: _findings_for_native_category(findings, category)
            for category in MAKE_NATIVE_DIFF_CATEGORIES
        },
        "roundtrip_discovery": _roundtrip_discovery_payload(findings),
        "validation_findings": validation_findings,
        "repair_candidates": repair_candidates,
        "learning_suggestions": [
            suggestion.as_dict() for suggestion in learning_suggestions
        ],
        "proposed_follow_up_todos": [
            suggestion.proposed_todo_path for suggestion in learning_suggestions
        ],
        "evidence_gaps": evidence_gaps,
    }


def _tagged_findings(comparisons: Sequence[JsonObject]) -> list[JsonObject]:
    tagged: list[JsonObject] = []
    for comparison in comparisons:
        summary = _object_member(comparison, "summary")
        comparison_label = _optional_text(summary.get("label")) or "comparison"
        raw_findings = comparison.get("findings")
        if not isinstance(raw_findings, list):
            continue
        for item in cast("list[object]", raw_findings):
            if not isinstance(item, dict):
                continue
            finding = {
                str(key): value
                for key, value in cast("dict[object, object]", item).items()
            }
            finding["comparison"] = comparison_label
            tagged.append(finding)
    return tagged


def _make_native_classified_findings(
    findings: Sequence[JsonObject],
) -> list[JsonObject]:
    """Add Make-native parity categories without replacing existing categories.

    Returns:
    New finding payloads with Make-native parity category and severity fields.
    """
    classified: list[JsonObject] = []
    for finding in findings:
        payload = dict(finding)
        category = _make_native_diff_category(payload)
        confidence = _make_native_rule_confidence(
            payload=payload, category=category
        )
        payload["native_parity_category"] = category
        payload["native_parity_confidence"] = confidence
        payload["native_parity_base_severity"] = MAKE_NATIVE_DIFF_SEVERITY[
            category
        ]
        payload["native_parity_severity"] = tune_make_native_diff_severity(
            category=category,
            base_severity=MAKE_NATIVE_DIFF_SEVERITY[category],
            confidence=confidence,
        )
        payload["native_parity_confidence_effect"] = _confidence_effect(
            base_severity=MAKE_NATIVE_DIFF_SEVERITY[category],
            tuned_severity=str(payload["native_parity_severity"]),
        )
        discovery_class = _roundtrip_discovery_class(payload, category)
        payload["roundtrip_discovery_class"] = discovery_class
        payload["generalization_targets"] = ROUNDTRIP_GENERALIZATION_TARGETS[
            discovery_class
        ]
        payload["pipeline_next_action"] = ROUNDTRIP_CLASS_ACTIONS[
            discovery_class
        ]
        payload["hardcoding_rejected"] = True
        classified.append(payload)
    return classified


def _make_native_rule_confidence(
    *,
    payload: JsonObject,
    category: str,
) -> MakeParityConfidence:
    """Return confidence for one Make-native diff classification."""
    explicit = payload.get("native_parity_confidence") or payload.get(
        "confidence"
    )
    if explicit is not None:
        return normalize_make_parity_confidence(explicit)
    if category == "zero_trace_violation":
        return "corpus_confirmed"
    if category == "semantic_lineage_breakage":
        return "high"
    if category in {"pass_through_unknown_module", "native_parity_gap"}:
        return "low"
    return "medium"


def _confidence_effect(*, base_severity: str, tuned_severity: str) -> str:
    if base_severity == tuned_severity:
        return "severity_unchanged"
    return f"{base_severity.lower()}_downgraded_to_{tuned_severity.lower()}"


def _make_native_diff_category(finding: JsonObject) -> str:
    text = _finding_search_text(finding)
    category = str(finding.get("category") or "").casefold()
    path = str(finding.get("path") or "").casefold()
    if _volatile_noise_finding(finding):
        return "volatile_make_noise"
    if any(
        term in text
        for term in ("pancakes", "schoenwald", "source_draft", "local draft")
    ):
        return "zero_trace_violation"
    structural_category = _structural_native_diff_category(
        path=path, category=category
    )
    if structural_category is not None:
        return structural_category
    if _placeholder_native_finding(text=text, category=category):
        return "runtime_resource_placeholder"
    return "native_parity_gap"


def _structural_native_diff_category(*, path: str, category: str) -> str | None:
    """Return the Make-native structural category for a path-level finding."""
    structural_rules: tuple[tuple[bool, str], ...] = (
        ("mapper" in path, "mapper_shape_delta"),
        ("metadata.expect" in path, "metadata_expect_missing"),
        ("metadata.restore" in path, "restore_missing"),
        ("designer" in path or path.endswith((".x", ".y")), "layout_delta"),
        (
            path.endswith(".version") or category == "module-version",
            "native_parity_gap",
        ),
        (
            "filter" in path
            or "conditions" in path
            or category == "route/filter",
            ("filter_shape_delta"),
        ),
        (
            category == "semantic" or path.endswith(".module"),
            "semantic_lineage_breakage",
        ),
    )
    for matches, native_category in structural_rules:
        if matches:
            return native_category
    return None


def _placeholder_native_finding(*, text: str, category: str) -> bool:
    """Return if a finding is about runtime resource placeholder handling."""
    return (
        category == "placeholder"
        or "__imtconn__" in text
        or "{{runtime." in text
        or "placeholder" in text
    )


def _roundtrip_discovery_class(
    finding: JsonObject, native_category: str
) -> str:
    """Return the generalization workflow class for one roundtrip delta."""
    category_map = {
        "filter_shape_delta": "native_shape_rule ",
        "layout_delta": "layout_rule ",
        "mapper_shape_delta": "native_shape_rule ",
        "metadata_expect_missing": "restore_expect_rule ",
        "restore_missing": "restore_expect_rule ",
        "runtime_resource_placeholder": "runtime_binding_rule ",
        "semantic_lineage_breakage": "semantic_breakage ",
        "volatile_make_noise": "volatile_noise ",
        "pass_through_unknown_module": "unknown_requires_evidence ",
        "zero_trace_violation": "zero_trace_violation",
    }
    mapped_class = category_map.get(native_category)
    if mapped_class is not None:
        return mapped_class
    if _semantic_finding(finding):
        return "semantic_breakage"
    if _volatile_noise_finding(finding):
        return "volatile_noise"
    return "unknown_requires_evidence"


def _semantic_finding(finding: JsonObject) -> bool:
    """Return whether one finding is marked semantic."""
    return isinstance(finding.get("semantic"), bool) and bool(
        finding.get("semantic")
    )


def _volatile_noise_finding(finding: JsonObject) -> bool:
    """Return whether one finding is likely canonicalizable volatile noise."""
    text = _finding_search_text(finding)
    return any(
        term in text
        for term in ("updated_at", "lastmodified", "revision", "timestamp")
    )


def _finding_search_text(finding: JsonObject) -> str:
    search_values = (
        finding.get("category"),
        finding.get("code"),
        finding.get("path"),
        finding.get("message"),
        finding.get("change_type"),
        finding.get("comparison"),
    )
    return " ".join(
        str(value) for value in search_values if value is not None
    ).casefold()


def _native_parity_category_counts(
    findings: Sequence[JsonObject],
) -> JsonObject:
    return {
        category: len(_findings_for_native_category(findings, category))
        for category in MAKE_NATIVE_DIFF_CATEGORIES
    }


def _native_parity_confidence_counts(
    findings: Sequence[JsonObject],
) -> JsonObject:
    return {
        confidence: len(_findings_for_native_confidence(findings, confidence))
        for confidence in ("low", "medium", "high", "corpus_confirmed")
    }


def _roundtrip_discovery_class_counts(
    findings: Sequence[JsonObject],
) -> JsonObject:
    """Return counts for the generalization workflow classes."""
    return {
        discovery_class: len(
            _findings_for_roundtrip_class(findings, discovery_class)
        )
        for discovery_class in ROUNDTRIP_DISCOVERY_CLASSES
    }


def _roundtrip_discovery_payload(findings: Sequence[JsonObject]) -> JsonObject:
    """Return the observed-delta-to-general-rule workflow guidance."""
    class_counts = _roundtrip_discovery_class_counts(findings)
    return {
        "classes": ROUNDTRIP_DISCOVERY_CLASSES,
        "class_counts": class_counts,
        "workflow": (
            "capture_reexport_fixture ",
            "classify_semantic_delta ",
            "promote_general_rule ",
            "add_or_update_contract ",
            "reject_one_off_patch",
        ),
        "generalization_targets": ROUNDTRIP_GENERALIZATION_TARGETS,
        "hardcoding_policy": (
            "Do not hardcode project names, demo ids, node ids beyond "
            "fixture-local "
            "structure, or one-off Make values."
        ),
        "unknown_delta_policy": (
            "Unknown deltas require quarantine evidence before they become "
            "canonicalizer, projector, layout, or readiness rules."
        ),
        "next_actions": ROUNDTRIP_CLASS_ACTIONS,
    }


def _zero_trace_source_findings(
    *,
    source_payloads: Sequence[JsonObject],
    label: str,
) -> list[JsonObject]:
    """Return strict-redacted zero-trace findings found directly in input.

    payloads.
    """
    findings: list[JsonObject] = []
    source_names = ("generated", "make_exported", "known_good")
    for source_name, payload in zip(
        source_names, source_payloads, strict=False
    ):
        for path in _private_trace_paths(payload, path="$"):
            findings.append(
                {
                    "finding_id": _source_finding_id(
                        label, "zero_trace", source_name, len(findings)
                    ),
                    "change_type": "changed ",
                    "category": "metadata",
                    "path": path,
                    "comparison": f"{label}:zero_trace_scan:{source_name}",
                    "semantic": True,
                    "native_parity_category": "zero_trace_violation ",
                    "native_parity_confidence": "corpus_confirmed ",
                    "native_parity_base_severity": "P0 ",
                    "native_parity_severity": "P0 ",
                    "native_parity_confidence_effect": "severity_unchanged ",
                    "roundtrip_discovery_class": "zero_trace_violation",
                    "generalization_targets": ROUNDTRIP_GENERALIZATION_TARGETS[
                        "zero_trace_violation"
                    ],
                    "pipeline_next_action": ROUNDTRIP_CLASS_ACTIONS[
                        "zero_trace_violation"
                    ],
                    "hardcoding_rejected": True,
                    "code": "zero_trace.private_export_trace",
                    "message": (
                        "Blueprint input contains private/local trace text "
                        "at this path; "
                        "strict diff redacted the value."
                    ),
                }
            )
            if len(findings) >= ZERO_TRACE_FINDING_LIMIT:
                return findings
    return findings


def _source_finding_id(
    label: str, category: str, source_name: str, finding_count: int
) -> str:
    """Return a stable source-scoped finding id.

    Returns:
        The generated finding id.
    """
    return f"{label}:{category}:{source_name}:{finding_count + 1:04d}"


def _runtime_resource_source_findings(
    *,
    source_payloads: Sequence[JsonObject],
    label: str,
) -> list[JsonObject]:
    """Return strict-redacted runtime resource placeholder findings."""
    findings: list[JsonObject] = []
    source_names = ("generated", "make_exported", "known_good")
    for source_name, payload in zip(
        source_names, source_payloads, strict=False
    ):
        for path in _runtime_resource_paths(payload, path="$"):
            findings.append(
                {
                    "finding_id": _source_finding_id(
                        label, "runtime_resource", source_name, len(findings)
                    ),
                    "change_type": "changed ",
                    "category": "placeholder",
                    "path": path,
                    "comparison": (
                        f"{label}:runtime_resource_scan:{source_name}"
                    ),
                    "semantic": True,
                    "native_parity_category": "runtime_resource_placeholder ",
                    "native_parity_confidence": "medium ",
                    "native_parity_base_severity": "P1 ",
                    "native_parity_severity": "P1 ",
                    "native_parity_confidence_effect": "severity_unchanged ",
                    "roundtrip_discovery_class": "runtime_binding_rule",
                    "generalization_targets": ROUNDTRIP_GENERALIZATION_TARGETS[
                        "runtime_binding_rule"
                    ],
                    "pipeline_next_action": ROUNDTRIP_CLASS_ACTIONS[
                        "runtime_binding_rule"
                    ],
                    "hardcoding_rejected": True,
                    "code": "diff.runtime_resource_placeholder",
                    "message": (
                        "Blueprint input contains a runtime resource "
                        "placeholder at this path; "
                        "strict diff redacted the value."
                    ),
                }
            )
    return findings


def _pass_through_unknown_module_source_findings(
    *,
    source_payloads: Sequence[JsonObject],
    label: str,
) -> list[JsonObject]:
    """Return findings for Make modules that lack a local projector manifest."""
    findings: list[JsonObject] = []
    source_names = ("generated", "make_exported", "known_good")
    for source_name, payload in zip(
        source_names, source_payloads, strict=False
    ):
        for path, module_token in _module_token_paths(payload, path="$"):
            if not _is_unknown_make_module_token(module_token):
                continue
            findings.append(
                {
                    "finding_id": _source_finding_id(
                        label, "unknown_module", source_name, len(findings)
                    ),
                    "change_type": "observed ",
                    "category": "module",
                    "path": path,
                    "comparison": f"{label}:module_manifest_scan:{source_name}",
                    "semantic": False,
                    "native_parity_category": "pass_through_unknown_module ",
                    "native_parity_confidence": "low ",
                    "native_parity_base_severity": "P1 ",
                    "native_parity_severity": "P1 ",
                    "native_parity_confidence_effect": "severity_unchanged ",
                    "roundtrip_discovery_class": "unknown_requires_evidence",
                    "generalization_targets": ROUNDTRIP_GENERALIZATION_TARGETS[
                        "unknown_requires_evidence"
                    ],
                    "pipeline_next_action": ROUNDTRIP_CLASS_ACTIONS[
                        "unknown_requires_evidence"
                    ],
                    "hardcoding_rejected": True,
                    "code": "diff.pass_through_unknown_module",
                    "module_prefix": _module_prefix(module_token),
                    "message": (
                        "Blueprint input contains a module without a local "
                        "Make projector "
                        "manifest; preserve pass-through behavior until "
                        "corpus evidence "
                        "supports a native projector."
                    ),
                }
            )
    return findings


def _module_token_paths(
    value: object, *, path: str
) -> tuple[tuple[str, str], ...]:
    """Return module token locations from a blueprint-like JSON value."""
    if isinstance(value, dict):
        paths: list[tuple[str, str]] = []
        for key, item in sorted(
            cast("dict[object, object]", value).items(), key=_key_sort_text
        ):
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text == "module" and isinstance(item, str) and item:
                paths.append((child_path, item))
                continue
            paths.extend(_module_token_paths(item, path=child_path))
        return tuple(paths)
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(cast("list[object]", value)):
            paths.extend(_module_token_paths(item, path=f"{path}[{index}]"))
        return tuple(paths)
    return ()


def _is_unknown_make_module_token(module_token: str) -> bool:
    """Return if a module token has no local Make-native projector manifest."""
    return make_module_projector_manifest_for_native_token(module_token) is None


def _module_prefix(module_token: str) -> str:
    """Return a non-secret module family prefix for reporting."""
    prefix, separator, _rest = module_token.partition(":")
    if not separator:
        return "unknown"
    return prefix or "unknown"


def _private_trace_paths(value: object, *, path: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (path,) if _has_private_trace_marker(value) else ()
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in sorted(
            cast("dict[object, object]", value).items(), key=_key_sort_text
        ):
            paths.extend(_private_trace_paths(item, path=f"{path}.{key}"))
        return tuple(paths)
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(cast("list[object]", value)):
            paths.extend(_private_trace_paths(item, path=f"{path}[{index}]"))
        return tuple(paths)
    return ()


def _runtime_resource_paths(value: object, *, path: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (path,) if _has_runtime_resource_placeholder(value) else ()
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in sorted(
            cast("dict[object, object]", value).items(), key=_key_sort_text
        ):
            paths.extend(_runtime_resource_paths(item, path=f"{path}.{key}"))
        return tuple(paths)
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(cast("list[object]", value)):
            paths.extend(_runtime_resource_paths(item, path=f"{path}[{index}]"))
        return tuple(paths)
    return ()


def _has_private_trace_marker(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in ZERO_TRACE_PRIVATE_MARKERS)


def _has_runtime_resource_placeholder(value: str) -> bool:
    normalized = value.casefold()
    if "{{runtime." in normalized or "__imtconn__" in normalized:
        return True
    return any(
        _is_non_module_placeholder_body(body)
        for body in _placeholder_bodies(value)
    )


def _placeholder_bodies(value: str) -> tuple[str, ...]:
    bodies: list[str] = []
    cursor = 0
    while True:
        start = value.find("{{", cursor)
        if start < 0:
            return tuple(bodies)
        end = value.find("}}", start + 2)
        if end < 0:
            return tuple(bodies)
        bodies.append(value[start + 2 : end].strip())
        cursor = end + 2


def _is_non_module_placeholder_body(body: str) -> bool:
    return bool(body) and not body[0].isdigit()


def _key_sort_text(item: tuple[object, object]) -> str:
    return str(item[0])


def _grouped_native_parity_deltas(
    findings: Sequence[JsonObject],
) -> list[JsonObject]:
    """Return grouped Make-native diff categories while keeping raw findings.

    intact.
    """
    grouped: dict[tuple[str, str, str, str, str, str], JsonObject] = {}
    paths_by_key: dict[tuple[str, str, str, str, str, str], list[str]] = {}
    comparisons_by_key: dict[
        tuple[str, str, str, str, str, str], list[str]
    ] = {}
    for finding in findings:
        category = str(
            finding.get("native_parity_category") or "native_parity_gap"
        )
        severity = str(finding.get("native_parity_severity") or "P1")
        confidence = str(finding.get("native_parity_confidence") or "low")
        discovery_class = str(
            finding.get("roundtrip_discovery_class")
            or "unknown_requires_evidence"
        )
        change_type = str(
            finding.get("change_type") or finding.get("category") or ""
        )
        code = str(finding.get("code") or "")
        key = (
            category,
            severity,
            confidence,
            discovery_class,
            change_type,
            code,
        )
        if key not in grouped:
            grouped[key] = {
                "category": category,
                "severity": severity,
                "confidence": confidence,
                "roundtrip_discovery_class": discovery_class,
                "change_type": change_type,
                "code": code,
                "count": 0,
                "example_paths": [],
                "comparisons": [],
                "next_action": _native_parity_group_next_action(category),
                "pipeline_next_action": ROUNDTRIP_CLASS_ACTIONS[
                    discovery_class
                ],
                "generalization_targets": ROUNDTRIP_GENERALIZATION_TARGETS[
                    discovery_class
                ],
            }
            paths_by_key[key] = []
            comparisons_by_key[key] = []
        current_count = grouped[key].get("count")
        grouped[key]["count"] = (
            current_count if isinstance(current_count, int) else 0
        ) + 1
        path = _optional_text(finding.get("path"))
        if path is not None and path not in paths_by_key[key]:
            paths_by_key[key].append(path)
        comparison = _optional_text(finding.get("comparison"))
        if comparison is not None and comparison not in comparisons_by_key[key]:
            comparisons_by_key[key].append(comparison)
    rows: list[JsonObject] = []
    for key, payload in grouped.items():
        payload["example_paths"] = tuple(paths_by_key[key][:3])
        payload["comparisons"] = tuple(comparisons_by_key[key])
        rows.append(payload)
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("severity") or ""),
            -_diff_count(item),
            str(item.get("category") or ""),
        ),
    )


def _diff_count(item: JsonObject) -> int:
    value = item.get("count")
    return value if isinstance(value, int) else 0


def _int_member(item: JsonObject, key: str) -> int:
    """Return an integer member or zero."""
    value = item.get(key)
    return value if isinstance(value, int) else 0


def _native_parity_group_next_action(category: str) -> str:
    return MAKE_NATIVE_DIFF_GROUP_ACTIONS.get(
        category,
        "Review this Make-native parity gap against the fixture corpus.",
    )


def _native_parity_severity_count(
    findings: Sequence[JsonObject], severity: str
) -> int:
    return sum(
        1
        for finding in findings
        if finding.get("native_parity_severity") == severity
    )


def _findings_for_native_category(
    findings: Sequence[JsonObject],
    category: str,
) -> list[JsonObject]:
    return [
        finding
        for finding in findings
        if finding.get("native_parity_category") == category
    ]


def _findings_for_native_confidence(
    findings: Sequence[JsonObject],
    confidence: str,
) -> list[JsonObject]:
    return [
        finding
        for finding in findings
        if finding.get("native_parity_confidence") == confidence
    ]


def _findings_for_roundtrip_class(
    findings: Sequence[JsonObject],
    discovery_class: str,
) -> list[JsonObject]:
    return [
        finding
        for finding in findings
        if finding.get("roundtrip_discovery_class") == discovery_class
    ]


def _local_only_evidence_gap() -> JsonObject:
    return {
        "code": "diff.live_verification_not_performed",
        "message": (
            "Local structured comparison only; no live Make import or runtime "
            "equivalence was claimed."
        ),
    }


def _human_summary(*, label: str, findings: Sequence[JsonObject]) -> str:
    semantic_count = sum(
        1
        for finding in findings
        if isinstance(finding.get("semantic"), bool) and finding.get("semantic")
    )
    if not findings:
        return f"{label}: no differences found. No auto-patch was applied."
    return (
        f"{label}: {len(findings)} structured difference(s), {semantic_count} "
        f"semantic. No auto-patch was applied."
    )


def _findings_for_change(
    findings: Sequence[JsonObject], change_type: str
) -> list[JsonObject]:
    return [
        finding
        for finding in findings
        if finding.get("change_type") == change_type
    ]


def _findings_for_categories(
    findings: Sequence[JsonObject],
    categories: tuple[str, ...],
) -> list[JsonObject]:
    category_set = set(categories)
    return [
        finding
        for finding in findings
        if finding.get("category") in category_set
    ]


def _findings_for_paths(
    findings: Sequence[JsonObject],
    fragments: tuple[str, ...],
) -> list[JsonObject]:
    return [
        finding
        for finding in findings
        if any(
            fragment in str(finding.get("path", "")).casefold()
            for fragment in fragments
        )
    ]


def _object_member(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return {
            str(item_key): item
            for item_key, item in cast("dict[object, object]", value).items()
        }
    return {}


def _redaction_mode(value: object) -> str:
    text = _optional_text(value) or REDACTION_MODE_STRICT
    if text not in SUPPORTED_REDACTION_MODES:
        message = f"Unsupported redaction_mode: {text}"
        raise ValueError(message)
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Expected a string value."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _optional_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        message = "Expected a boolean value."
        raise TypeError(message)
    return value


def _require_approved_artifact_root(
    *,
    argument_name: str,
    repo_root: Path,
    path: Path,
    submitted_path: str,
) -> None:
    approved_roots = APPROVED_BLUEPRINT_DIFF_ROOTS_BY_ARGUMENT[argument_name]
    resolved_path = path.resolve()
    resolved_root = repo_root.resolve()
    for root in approved_roots:
        approved_root = (resolved_root / root).resolve()
        if resolved_path.is_relative_to(approved_root):
            return
    roots_text = ", ".join(_root_texts(approved_roots))
    message = (
        f"{argument_name} must be under an approved blueprint diff artifact "
        f"root ({roots_text}): {submitted_path}"
    )
    raise ValueError(message)


def _root_texts(roots: tuple[Path, ...]) -> list[str]:
    return [root.as_posix() for root in roots]
