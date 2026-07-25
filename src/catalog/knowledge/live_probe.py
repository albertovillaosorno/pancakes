# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.live-probe-evidence
# - 001055#repo.mcp.live-roundtrip-review-tool
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Operator-gated live Make roundtrip probe staging.

Boundary contract:
- Owns: live-probe planning, fake-transport test hooks, diffs, and SQL staging.
- Must not: own db:build, mutate SQLite directly, or store raw credentials.
- Allows: explicit operator-approved live transport use and reviewed evidence
SQL.
- Split when: real Make scenario upload/download adapters become independent.
- Merge when: another knowledge module stages the same live_probe evidence rows.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Protocol, cast

from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
    safe_path_token,
)

from catalog.json_payloads import normalize_json_object, payload_fingerprint
from catalog.knowledge.storage import load_knowledge_store_query

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog.knowledge.models import KnowledgeClaimConflict
    from catalog.models import JsonObject

LIVE_PROBE_SOURCE_KIND = "live_probe"
LIVE_PROBE_SOURCE_CONFIDENCE = 900
DEFAULT_LIVE_PROBE_EVIDENCE_PATH = Path(
    "src/data/sql_snapshots/live_probe_evidence.sql"
)
LIVE_PROBE_ADR_ANCHOR = "001064#repo.make-knowledge.live-probe-evidence"
MAX_CREDENTIAL_REF_LENGTH = 120
SECRET_CREDENTIAL_PREFIXES = (
    "authorization:",
    "authorization=",
    "bearer ",
    "pat_",
    "raw-token",
    "sk-",
    "mk_",
    "token ",
)


class MakeLiveRoundtripTransport(Protocol):
    """Transport boundary for operator-approved Make scenario roundtrip.

    probes.
    """

    def upload_scenario(self, scenario: JsonObject) -> str:
        """Upload the probe scenario and return the live scenario id."""
        ...

    def auto_align_scenario(self, scenario_id: str) -> bool:
        """Request Make auto-align if available and return whether it ran."""
        ...

    def download_scenario(self, scenario_id: str) -> JsonObject:
        """Download the scenario JSON after Make processes it."""
        ...


class LiveProbeAuthorization(NamedTuple):
    """Reviewed operator authorization for one live Make probe."""

    operator_approved: bool
    approved_by: str
    credential_ref: str
    purpose: str


class LiveRoundtripProbeRequest(NamedTuple):
    """Request for one operator-approved live roundtrip probe."""

    repo_root: Path
    conflict_id: str
    authorization: LiveProbeAuthorization
    transport: MakeLiveRoundtripTransport
    reviewed_value_json: str
    observed_at_utc: str
    evidence_path: Path = DEFAULT_LIVE_PROBE_EVIDENCE_PATH


class LiveProbeStageRequest(NamedTuple):
    """Request for staging reviewed live-probe evidence."""

    repo_root: Path
    conflict_id: str
    authorization: LiveProbeAuthorization
    returned_scenario: JsonObject
    reviewed_value_json: str
    observed_at_utc: str
    original_scenario: JsonObject | None = None
    evidence_path: Path = DEFAULT_LIVE_PROBE_EVIDENCE_PATH
    scenario_id: str | None = None
    auto_aligned: bool = False


class JsonDiffAccumulator(NamedTuple):
    """Mutable JSON diff buckets shared by recursive diff traversal."""

    removed: list[str]
    added: list[str]
    changed: list[JsonObject]


def live_probe_authorization_from_json(
    source_text: str,
) -> LiveProbeAuthorization:
    """Parse one live-probe authorization JSON object.

    Returns:
        The parsed live-probe authorization.
    """
    payload = _json_text_object(source_text)
    return LiveProbeAuthorization(
        operator_approved=_required_bool(
            payload.get("operator_approved"), "operator_approved"
        ),
        approved_by=_required_string(payload.get("approved_by"), "approved_by"),
        credential_ref=_required_string(
            payload.get("credential_ref"), "credential_ref"
        ),
        purpose=_required_string(payload.get("purpose"), "purpose"),
    )


def list_needs_review_conflicts(*, repo_root: Path) -> JsonObject:
    """Return current knowledge-store conflicts that require operator review."""
    query = load_knowledge_store_query(repo_root=repo_root)
    conflicts = tuple(
        conflict
        for conflict in query.claim_conflicts
        if conflict.resolution_status == "needs_review"
    )
    return {
        "status": "ok",
        "conflict_count": len(conflicts),
        "conflicts": [_conflict_summary(conflict) for conflict in conflicts],
    }


def build_live_probe_plan(*, repo_root: Path, conflict_id: str) -> JsonObject:
    """Build the minimal live-probe scenario plan for one needs_review conflict.

    Returns:
        A local plan payload for operator review.
    """
    conflict = _needs_review_conflict(
        repo_root=repo_root, conflict_id=conflict_id
    )
    scenario = _probe_scenario(conflict)
    return {
        "status": "planned",
        "unattended_allowed": False,
        "operator_working_name": "operator-gated conflict review",
        "conflict": _conflict_summary(conflict),
        "probe_scenario": scenario,
    }


def run_live_roundtrip_probe(
    request: LiveRoundtripProbeRequest | None = None,
    **legacy_arguments: object,
) -> JsonObject:
    """Run an authorized live roundtrip through an injected transport.

    Returns:
        A report with diff and staged evidence metadata.
    """
    request = _live_roundtrip_probe_request(request, legacy_arguments)
    _require_authorization(request.authorization)
    conflict = _needs_review_conflict(
        repo_root=request.repo_root, conflict_id=request.conflict_id
    )
    original_scenario = _probe_scenario(conflict)
    scenario_id = request.transport.upload_scenario(original_scenario)
    auto_aligned = request.transport.auto_align_scenario(scenario_id)
    returned_scenario = request.transport.download_scenario(scenario_id)
    return stage_live_probe_result(
        LiveProbeStageRequest(
            repo_root=request.repo_root,
            conflict_id=request.conflict_id,
            authorization=request.authorization,
            original_scenario=original_scenario,
            returned_scenario=returned_scenario,
            reviewed_value_json=request.reviewed_value_json,
            observed_at_utc=request.observed_at_utc,
            evidence_path=request.evidence_path,
            scenario_id=scenario_id,
            auto_aligned=auto_aligned,
        )
    )


def stage_live_probe_result(
    request: LiveProbeStageRequest | None = None,
    **legacy_arguments: object,
) -> JsonObject:
    """Stage reviewed live_probe evidence without mutating SQLite.

    Returns:
        A staging report with diff and evidence metadata.
    """
    request = _live_probe_stage_request(request, legacy_arguments)
    _require_authorization(request.authorization)
    _validate_observed_at(request.observed_at_utc)
    conflict = _needs_review_conflict(
        repo_root=request.repo_root, conflict_id=request.conflict_id
    )
    source_scenario = (
        _probe_scenario(conflict)
        if request.original_scenario is None
        else request.original_scenario
    )
    diff = diff_json_payloads(source_scenario, request.returned_scenario)
    evidence = _evidence_payload(
        conflict=conflict,
        reviewed_value_json=request.reviewed_value_json,
        observed_at_utc=request.observed_at_utc,
        diff=diff,
        scenario_id=request.scenario_id,
    )
    output_path = resolve_repo_relative_path(
        request.repo_root, request.evidence_path
    )
    _append_evidence_sql(output_path, evidence)
    return {
        "status": "staged",
        "conflict": _conflict_summary(conflict),
        "scenario_id": request.scenario_id,
        "auto_aligned": request.auto_aligned,
        "diff": diff,
        "evidence": evidence,
        "evidence_sql_path": relative_to_repo(request.repo_root, output_path),
    }


def diff_json_payloads(before: JsonObject, after: JsonObject) -> JsonObject:
    """Return a compact recursive JSON diff for Make roundtrip reports."""
    accumulator = JsonDiffAccumulator(removed=[], added=[], changed=[])
    _diff_value(path="$", before=before, after=after, accumulator=accumulator)
    return {
        "removed_fields": accumulator.removed,
        "added_fields": accumulator.added,
        "changed_values": accumulator.changed,
        "make_side_errors": _make_side_errors(after),
    }


def _live_roundtrip_probe_request(
    request: LiveRoundtripProbeRequest | None,
    legacy_arguments: Mapping[str, object],
) -> LiveRoundtripProbeRequest:
    if request is not None:
        if legacy_arguments:
            message = (
                "Pass either LiveRoundtripProbeRequest or legacy keyword"
                "arguments."
            )
            raise TypeError(message)
        return request
    return LiveRoundtripProbeRequest(
        repo_root=cast(
            "Path", _required_legacy_argument(legacy_arguments, "repo_root")
        ),
        conflict_id=cast(
            "str", _required_legacy_argument(legacy_arguments, "conflict_id")
        ),
        authorization=cast(
            "LiveProbeAuthorization",
            _required_legacy_argument(legacy_arguments, "authorization"),
        ),
        transport=cast(
            "MakeLiveRoundtripTransport",
            _required_legacy_argument(legacy_arguments, "transport"),
        ),
        reviewed_value_json=cast(
            "str",
            _required_legacy_argument(legacy_arguments, "reviewed_value_json"),
        ),
        observed_at_utc=cast(
            "str",
            _required_legacy_argument(legacy_arguments, "observed_at_utc"),
        ),
        evidence_path=cast(
            "Path",
            legacy_arguments.get(
                "evidence_path", DEFAULT_LIVE_PROBE_EVIDENCE_PATH
            ),
        ),
    )


def _live_probe_stage_request(
    request: LiveProbeStageRequest | None,
    legacy_arguments: Mapping[str, object],
) -> LiveProbeStageRequest:
    if request is not None:
        if legacy_arguments:
            message = (
                "Pass either LiveProbeStageRequest or legacy keyword arguments."
            )
            raise TypeError(message)
        return request
    return LiveProbeStageRequest(
        repo_root=cast(
            "Path", _required_legacy_argument(legacy_arguments, "repo_root")
        ),
        conflict_id=cast(
            "str", _required_legacy_argument(legacy_arguments, "conflict_id")
        ),
        authorization=cast(
            "LiveProbeAuthorization",
            _required_legacy_argument(legacy_arguments, "authorization"),
        ),
        returned_scenario=cast(
            "JsonObject",
            _required_legacy_argument(legacy_arguments, "returned_scenario"),
        ),
        reviewed_value_json=cast(
            "str",
            _required_legacy_argument(legacy_arguments, "reviewed_value_json"),
        ),
        observed_at_utc=cast(
            "str",
            _required_legacy_argument(legacy_arguments, "observed_at_utc"),
        ),
        original_scenario=cast(
            "JsonObject | None", legacy_arguments.get("original_scenario")
        ),
        evidence_path=cast(
            "Path",
            legacy_arguments.get(
                "evidence_path", DEFAULT_LIVE_PROBE_EVIDENCE_PATH
            ),
        ),
        scenario_id=cast("str | None", legacy_arguments.get("scenario_id")),
        auto_aligned=cast("bool", legacy_arguments.get("auto_aligned", False)),
    )


def _required_legacy_argument(
    arguments: Mapping[str, object], key: str
) -> object:
    if key in arguments:
        return arguments[key]
    message = f"Missing live-probe argument: {key}"
    raise TypeError(message)


def _needs_review_conflict(
    *, repo_root: Path, conflict_id: str
) -> KnowledgeClaimConflict:
    query = load_knowledge_store_query(repo_root=repo_root)
    for conflict in query.claim_conflicts:
        if conflict.conflict_id == conflict_id:
            if conflict.resolution_status != "needs_review":
                message = f"Claim conflict is not needs_review: {conflict_id}"
                raise ValueError(message)
            return conflict
    message = f"needs_review claim conflict not found: {conflict_id}"
    raise ValueError(message)


def _probe_scenario(conflict: KnowledgeClaimConflict) -> JsonObject:
    return {
        "name": f"live-probe-{safe_path_token(conflict.claim_key)}",
        "flow": [],
        "metadata": {
            "scenario": {
                "name": f"live-probe-{safe_path_token(conflict.claim_key)}"
            },
            "designer": {"messages": []},
            "live_probe": {
                "conflict_id": conflict.conflict_id,
                "claim_key": conflict.claim_key,
                "domain": conflict.domain,
                "winning_evidence_id": conflict.winning_evidence_id,
                "losing_evidence_id": conflict.losing_evidence_id,
                "winning_value_json": conflict.winning_value_json,
                "losing_value_json": conflict.losing_value_json,
            },
        },
    }


def _evidence_payload(
    *,
    conflict: KnowledgeClaimConflict,
    reviewed_value_json: str,
    observed_at_utc: str,
    diff: JsonObject,
    scenario_id: str | None,
) -> JsonObject:
    reviewed_value = _json_text_value(reviewed_value_json)
    normalized_value_json = json.dumps(
        reviewed_value, ensure_ascii=True, sort_keys=True
    )
    evidence_fingerprint = payload_fingerprint(
        {
            "claim_key": conflict.claim_key,
            "value_json": normalized_value_json,
            "observed_at": observed_at_utc,
            "diff": diff,
            "scenario_id": scenario_id,
        }
    )
    evidence_id = f"live-probe-{evidence_fingerprint[:16]}"
    return {
        "evidence_id": evidence_id,
        "claim_key": conflict.claim_key,
        "domain": conflict.domain,
        "value_json": normalized_value_json,
        "claim_text": f"Live Make roundtrip reviewed {conflict.claim_key}.",
        "source_confidence": LIVE_PROBE_SOURCE_CONFIDENCE,
        "evidence_observed_at": observed_at_utc,
        "source_kind": LIVE_PROBE_SOURCE_KIND,
        "source_ref": f"make-live-roundtrip:{scenario_id or evidence_id}",
        "claim_ref": conflict.conflict_id,
        "valid_from": observed_at_utc,
        "valid_to": None,
        "fingerprint": evidence_fingerprint,
        "adr_anchor": LIVE_PROBE_ADR_ANCHOR,
    }


def _append_evidence_sql(output_path: Path, evidence: JsonObject) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    )
    block = _evidence_insert_sql(evidence)
    separator = "\n\n" if existing.strip() else ""
    _ = output_path.write_text(
        f"{existing.rstrip()}{separator}{block}\n", encoding="utf-8"
    )


def _evidence_insert_sql(evidence: JsonObject) -> str:
    columns = (
        "evidence_id",
        "claim_key",
        "domain",
        "value_json",
        "claim_text",
        "source_confidence",
        "evidence_observed_at",
        "source_kind",
        "source_ref",
        "claim_ref",
        "valid_from",
        "valid_to",
        "fingerprint",
        "adr_anchor",
    )
    prefix = (
        "INSERT OR REPLACE INTO claim_evidence (\n"
        "  evidence_id,\n"
        "  claim_key,\n"
        "  domain,\n"
        "  value_json,\n"
        "  claim_text,\n"
        "  source_confidence,\n"
        "  evidence_observed_at,\n"
        "  source_kind,\n"
        "  source_ref,\n"
        "  claim_ref,\n"
        "  valid_from,\n"
        "  valid_to,\n"
        "  fingerprint,\n"
        "  adr_anchor\n"
        ") VALUES (\n    "
    )
    values = ",\n    ".join(_sql_value(evidence[column]) for column in columns)
    return prefix + values + "\n);"


def _diff_value(
    *,
    path: str,
    before: object,
    after: object,
    accumulator: JsonDiffAccumulator,
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        before_map = cast("Mapping[str, object]", before)
        after_map = cast("Mapping[str, object]", after)
        accumulator.removed.extend(
            f"{path}.{key}"
            for key in sorted(before_map.keys() - after_map.keys())
        )
        accumulator.added.extend(
            f"{path}.{key}"
            for key in sorted(after_map.keys() - before_map.keys())
        )
        for key in sorted(before_map.keys() & after_map.keys()):
            _diff_value(
                path=f"{path}.{key}",
                before=before_map[key],
                after=after_map[key],
                accumulator=accumulator,
            )
        return
    if isinstance(before, list) and isinstance(after, list):
        if before != after:
            accumulator.changed.append(
                {"path": path, "before": before, "after": after}
            )
        return
    if before != after:
        accumulator.changed.append(
            {"path": path, "before": before, "after": after}
        )


def _make_side_errors(payload: JsonObject) -> list[object]:
    errors = payload.get("errors")
    if isinstance(errors, list):
        return cast("list[object]", errors)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        live_probe = cast("Mapping[str, object]", metadata).get("live_probe")
        if isinstance(live_probe, dict):
            nested_errors = cast("Mapping[str, object]", live_probe).get(
                "errors"
            )
            if isinstance(nested_errors, list):
                return cast("list[object]", nested_errors)
    return []


def _conflict_summary(conflict: KnowledgeClaimConflict) -> JsonObject:
    return {
        "conflict_id": conflict.conflict_id,
        "claim_key": conflict.claim_key,
        "domain": conflict.domain,
        "resolution_status": conflict.resolution_status,
        "winning_evidence_id": conflict.winning_evidence_id,
        "losing_evidence_id": conflict.losing_evidence_id,
        "arbitration_reason": conflict.arbitration_reason,
    }


def _require_authorization(authorization: LiveProbeAuthorization) -> None:
    authorization_error = _authorization_error(authorization)
    if authorization_error is not None:
        raise PermissionError(authorization_error)


def _authorization_error(authorization: LiveProbeAuthorization) -> str | None:
    if authorization.operator_approved is not True:
        return "Live roundtrip probe requires operator_approved=true."
    purpose = _optional_string(authorization.purpose)
    if purpose != "resolve_claim_conflict":
        return "Live roundtrip probe purpose must be resolve_claim_conflict."
    approved_by = _optional_string(authorization.approved_by)
    if approved_by is None:
        return "Live roundtrip probe requires approved_by."
    credential_ref = _optional_string(authorization.credential_ref)
    if credential_ref is None:
        return "Live roundtrip probe requires credential_ref."
    if _looks_like_secret(credential_ref):
        return "credential_ref must be a non-secret reference, not a raw token."
    return None


def _looks_like_secret(value: str) -> bool:
    lowered = " ".join(value.casefold().strip().split())
    return (
        lowered.startswith(SECRET_CREDENTIAL_PREFIXES)
        or len(value) > MAX_CREDENTIAL_REF_LENGTH
    )


def _validate_observed_at(observed_at_utc: str) -> None:
    try:
        parsed = datetime.fromisoformat(observed_at_utc)
    except ValueError as exc:
        message = f"observed_at_utc must be ISO-8601: {observed_at_utc}"
        raise ValueError(message) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        message = "observed_at_utc must include a timezone offset."
        raise ValueError(message)


def _json_text_object(source_text: str) -> JsonObject:
    payload = _json_text_value(source_text)
    if not isinstance(payload, dict):
        message = "Expected a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _json_text_value(source_text: str) -> object:
    return cast("object", json.loads(source_text))


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _required_string(value: object, name: str) -> str:
    text = _optional_string(value)
    if text is None:
        message = f"Live roundtrip probe requires non-empty string {name}."
        raise ValueError(message)
    return text


def _required_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    message = f"Live roundtrip probe requires boolean {name}."
    raise TypeError(message)


def _sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"
