# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001062#repo.paths.data.repository-relative-only
# - 001068#repo.operator-commands.diff-blueprint.structured-comparison
# - 001068#repo.operator-commands.live-service-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local Make re-export evidence ingestion harness.

Boundary contract:
- Owns: converting local generated/re-export blueprint pairs into inactive
evidence reports.
- Must not: call Make.com, require provider credentials, mutate compiler
behavior, or store secrets.
- Allows: local canonical diff classification and follow-up candidate
generation.
- Split when: accepted evidence promotion becomes a separate reviewed
persistence workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from languages.make.evidence import make_internal_evidence_availability
from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
)

from mcp.diff_blueprint import diff_blueprint

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast.models import JsonObject

SECRET_LIKE_EVIDENCE_MARKERS: Final[tuple[str, ...]] = (
    "access_token ",
    "api key ",
    "apikey ",
    "authorization:",
    "bearer ",
    "client_secret ",
    "password ",
    "private_key ",
    "refresh_token",
)
REEXPORT_REPOSITORY_PATH_DIAGNOSTIC: Final = "[redacted repository path]"
REEXPORT_EVIDENCE_CANDIDATE_TARGETS: Final[dict[str, str]] = {
    "filter_shape_delta": "module_or_filter_lowering_rule ",
    "layout_delta": "canonicalizer_or_layout_policy ",
    "mapper_shape_delta": "module_projector_manifest ",
    "metadata_expect_missing": "module_projector_manifest ",
    "native_parity_gap": "semantics_matrix_record ",
    "pass_through_unknown_module": "semantics_matrix_quarantine_record ",
    "restore_missing": "module_projector_manifest ",
    "runtime_resource_placeholder": "readiness_binding_policy ",
    "semantic_lineage_breakage": "damp_test_or_projector_rule ",
    "volatile_make_noise": "canonicalizer_rule ",
    "zero_trace_violation": "zero_trace_blocker",
}


def ingest_make_reexport_evidence(
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    """Return a local structured evidence report for one Make re-export pair."""
    generated_path = _required_repo_path(arguments, "generated_path", repo_root)
    reexport_path = _required_repo_path(
        arguments, "make_reexport_path", repo_root
    )
    known_good_path = (
        _optional_repo_path(arguments, "known_good_path", repo_root)
        or reexport_path
    )
    label = _optional_text(arguments.get("label")) or "local-reexport-evidence"

    diff_payload = diff_blueprint(
        {
            "generated_path": relative_to_repo(repo_root, generated_path),
            "make_exported_path": relative_to_repo(repo_root, reexport_path),
            "known_good_path": relative_to_repo(repo_root, known_good_path),
            "label": label,
            "redaction_mode": "strict",
            "include_internal_evidence": True,
        },
        repo_root,
    )
    findings = _json_object_sequence(diff_payload.get("findings"))
    zero_trace_findings = _findings_for_category(
        findings, "zero_trace_violation"
    )
    secret_hits = _secret_like_file_hits(
        (generated_path, reexport_path, known_good_path)
    )
    candidate_updates = _candidate_updates(diff_payload)
    status = "blocked" if zero_trace_findings or secret_hits else "report_ready"
    return {
        "status": status,
        "evidence_kind": "local_make_reexport_pair",
        "generated_path": relative_to_repo(repo_root, generated_path),
        "make_reexport_path": relative_to_repo(repo_root, reexport_path),
        "known_good_path": relative_to_repo(repo_root, known_good_path),
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "raw_evidence_persistence": "caller_owned_local_files_only ",
        "zero_trace_status": "failed" if zero_trace_findings else "passed",
        "zero_trace_finding_count": len(zero_trace_findings),
        "secret_like_evidence_count": len(secret_hits),
        "secret_like_evidence": tuple(secret_hits),
        "diff_summary": diff_payload.get("summary", {}),
        "native_parity_changes": diff_payload.get(
            "make_native_parity_changes", {}
        ),
        "roundtrip_discovery": diff_payload.get("roundtrip_discovery", {}),
        "candidate_updates": tuple(candidate_updates),
        "candidate_update_count": len(candidate_updates),
        "candidate_updates_active": False,
        "candidate_activation_policy": (
            "Candidates are inactive until accepted by tests or operator "
            "review."
        ),
        "internal_evidence": make_internal_evidence_availability(
            cast("JsonObject", diff_payload.get("internal_evidence_ledger", {}))
        ),
    }


def _candidate_updates(diff_payload: Mapping[str, object]) -> list[JsonObject]:
    candidates: list[JsonObject] = []
    for index, group in enumerate(
        _json_object_sequence(diff_payload.get("grouped_deltas")), 1
    ):
        category = str(group.get("category") or "native_parity_gap")
        candidate_target = REEXPORT_EVIDENCE_CANDIDATE_TARGETS.get(
            category,
            "semantics_matrix_record",
        )
        candidates.append(
            {
                "candidate_id": f"reexport-evidence-candidate-{index:04d}",
                "status": "inactive_pending_acceptance",
                "target": candidate_target,
                "category": category,
                "severity": group.get("severity"),
                "confidence": group.get("confidence"),
                "count": group.get("count"),
                "example_paths": group.get("example_paths", ()),
                "generalization_targets": group.get(
                    "generalization_targets", ()
                ),
                "next_action": group.get("next_action"),
                "activation_requirements": (
                    "add or update fixture coverage ",
                    "prove zero-trace and secret-scan cleanliness",
                    (
                        "review manifest, matrix, or canonicalizer change "
                        "before "
                        "activation"
                    ),
                ),
            }
        )
    return candidates


def _required_repo_path(
    arguments: Mapping[str, object],
    field: str,
    repo_root: Path,
) -> Path:
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        message = f"{field} is required."
        raise ValueError(message)
    path = resolve_repo_relative_path(repo_root, Path(value))
    if not path.is_file():
        message = (
            f"{field} must point at a local file:"
            f"{_repository_path_diagnostic()}"
        )
        raise FileNotFoundError(message)
    return path


def _optional_repo_path(
    arguments: Mapping[str, object],
    field: str,
    repo_root: Path,
) -> Path | None:
    value = arguments.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        message = f"{field} must be a repository-relative path when provided."
        raise ValueError(message)
    path = resolve_repo_relative_path(repo_root, Path(value))
    if not path.is_file():
        message = (
            f"{field} must point at a local file:"
            f"{_repository_path_diagnostic()}"
        )
        raise FileNotFoundError(message)
    return path


def _repository_path_diagnostic() -> str:
    return REEXPORT_REPOSITORY_PATH_DIAGNOSTIC


def _secret_like_file_hits(paths: Sequence[Path]) -> list[JsonObject]:
    hits: list[JsonObject] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        markers = tuple(
            marker for marker in SECRET_LIKE_EVIDENCE_MARKERS if marker in text
        )
        if markers:
            hits.append(
                {
                    "path": path.name,
                    "marker_count": len(markers),
                    "markers": markers,
                    "value_redacted": True,
                }
            )
    return hits


def _findings_for_category(
    findings: Sequence[JsonObject],
    category: str,
) -> tuple[JsonObject, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.get("native_parity_category") == category
    )


def _json_object_sequence(value: object) -> tuple[JsonObject, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(_json_object(item) for item in cast("Sequence[object]", value))


def _json_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return {
            str(key): item
            for key, item in cast("dict[object, object]", value).items()
        }
    return {}


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
