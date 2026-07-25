# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001067#repo.mcp.client-routing.native-gpt-latency-and-output
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local MCP documentation and onboarding validation tools.

Boundary contract:
- Owns: local documentation base generation and customer-safe wording validation
payloads.
- Must not: render PDFs, read credentials, contact providers, deploy, or expose
raw scenario JSON.
- Allows: bounded documentation summaries derived from
project.view/project.verify state.
- Split when: binary PDF rendering or customer portal delivery needs its own
tool group.
- Merge when: project.make fully owns the same documentation payloads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final, cast

from mcp.onboarding_coverage import build_onboarding_project_coverage
from mcp.onboarding_security import (
    onboarding_secret_class_counts,
    onboarding_secret_findings,
)
from mcp.project_loop import project_verify, view_project

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.models import JsonObject

DOCUMENTATION_SECTION_IDS: Final[tuple[str, ...]] = (
    "scenario_architecture ",
    "make_modules_and_data_flow ",
    "connections_filters_and_error_handlers ",
    "data_store_and_data_structure_references ",
    "numbered_make_note_references ",
    "operational_behavior ",
    "redaction_and_secret_free_evidence",
)
SECRET_VALUE_KEY_PATTERN_TEXT: Final[str] = (
    r"\b(?:access_token|api[_-]?key|authorization|bearer|password|secret|x-hook-key)\b"
)
SECRET_VALUE_SUFFIX_PATTERN_TEXT: Final[str] = (
    "\\s*[:=|]\\s*[A-Za-z0-9._~:/?#[\\]@!$&'()*+,;=-]{8,}"
)
SECRET_VALUE_PATTERN_TEXT: Final[str] = (
    f"{SECRET_VALUE_KEY_PATTERN_TEXT}{SECRET_VALUE_SUFFIX_PATTERN_TEXT}"
)
SECRET_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    SECRET_VALUE_PATTERN_TEXT,
    re.IGNORECASE,
)
UNSUPPORTED_CLAIM_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:100% secure|certified|guarantee|never fails|perfect "
    r"uptime|zero risk)\b",
    re.IGNORECASE,
)
PRIVATE_INTERNAL_PATTERN_PREFIX: Final[str] = (
    r"\b(?:ast|business strategy|graph algorithm|industrial "
    r"architecture|industrial logic|"
    r"internal architecture|internal dsl|internal graph|internal "
    r"prompt|linter logic|"
)
PRIVATE_INTERNAL_PATTERN_SUFFIX: Final[str] = (
    "private prompt|private prompts|raw provider payload|rule "
    "code|source path)\\b"
)
PRIVATE_INTERNAL_PATTERN_TEXT: Final[str] = (
    f"{PRIVATE_INTERNAL_PATTERN_PREFIX}{PRIVATE_INTERNAL_PATTERN_SUFFIX}"
)
PRIVATE_INTERNAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    PRIVATE_INTERNAL_PATTERN_TEXT,
    re.IGNORECASE,
)
LOCAL_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z]:[\\/]|(?:^|\s)/(?:home|mnt|users|var|tmp)/|\brepos[\\/]",
    re.IGNORECASE,
)
PROVIDED_PLACEHOLDERS_JSON_FIELD: Final = "provided_placeholders_json"
LEGACY_ONBOARDING_JSON_FIELD: Final = "onboarding_json"
SECRET_SHAPED_PLACEHOLDER_PREFIX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\A(?:sk|pk|rk|xox[a-z]?|ya29)[_-]",
    re.IGNORECASE,
)
SECRET_SHAPED_PLACEHOLDER_TEXT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:secret[_-]?like|bearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----)\b",
    re.IGNORECASE,
)


def generate_documentation(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Generate a bounded documentation base from local project state.

    Returns:
        Customer-safe documentation base and validation summary.
    """
    project_id = _required_text(
        arguments.get("project_id"), field_name="project_id"
    )
    output_mode = _documentation_output_mode(
        arguments.get("output_mode"),
        surface="documentation.generate",
    )
    dry_run = _optional_bool(
        arguments.get("dry_run"),
        field_name="documentation.generate dry_run",
        default=True,
    )
    overview = _project_view(
        project_id=project_id, surface="overview", repo_root=repo_root
    )
    modules = _project_view(
        project_id=project_id, surface="modules", repo_root=repo_root
    )
    links = _project_view(
        project_id=project_id, surface="links", repo_root=repo_root
    )
    filters = _project_view(
        project_id=project_id, surface="filters", repo_root=repo_root
    )
    error_handlers = _project_view(
        project_id=project_id,
        surface="error_handlers",
        repo_root=repo_root,
    )
    notes = _project_view(
        project_id=project_id, surface="notes", repo_root=repo_root
    )
    datastores = _project_view(
        project_id=project_id, surface="datastores", repo_root=repo_root
    )
    verification = project_verify(
        {
            "project_id": project_id,
            "profile": "handoff_test ",
            "output_mode": "compact",
        },
        repo_root,
    )
    views = {
        "overview": overview,
        "modules": modules,
        "links": links,
        "filters": filters,
        "error_handlers": error_handlers,
        "notes": notes,
        "datastores": datastores,
        "verification": verification,
    }
    documentation: JsonObject = {
        "schema_version": 1,
        "project_id": project_id,
        "surface": "documentation.generate ",
        "source_of_truth": "local_project_scenario ",
        "generation_mode": "realtime_project_state ",
        "document_type": "technical_manual ",
        "document_kind": "customer_technical_manual",
        "not_a_report": True,
        "output_mode": output_mode,
        "dry_run": dry_run,
        "documentation_write_status": "read_only_no_write",
        "write_performed": False,
        "documentation_sections": _documentation_sections(views),
        "summary": {
            "scenario": _mapping_value(overview, "scenario_overview"),
            "module_count": _int_value(modules, "module_count"),
            "link_count": _int_value(links, "link_count"),
            "filter_count": _int_value(filters, "filter_count"),
            "error_handler_count": _int_value(
                error_handlers, "error_handler_count"
            ),
            "note_count": _note_summary_count(notes, "note_count"),
            "missing_note_reference_count": (
                _note_summary_count(notes, "missing_module_note_count")
                + _note_summary_count(notes, "missing_connection_note_count")
            ),
            "note_section_issue_count": _note_summary_count(
                notes, "note_section_issue_count"
            ),
            "note_redaction_issue_count": _note_summary_count(
                notes, "note_redaction_issue_count"
            ),
        },
        "documentation_base": {
            "scenario_architecture": _mapping_value(
                overview, "scenario_overview"
            ),
            "modules": _bounded_payload_value(
                modules, "modules", output_mode=output_mode
            ),
            "links": _bounded_payload_value(
                links, "links", output_mode=output_mode
            ),
            "filters": _bounded_payload_value(
                filters, "filters", output_mode=output_mode
            ),
            "error_handlers": _bounded_payload_value(
                error_handlers,
                "error_handlers",
                output_mode=output_mode,
            ),
            "notes_summary": _mapping_value(notes, "scenario_notes_summary"),
            "note_redaction_evidence": _mapping_value(
                _mapping_value(notes, "scenario_notes_summary"),
                "redaction_evidence",
            ),
            "datastore_manifest": _mapping_value(
                datastores, "datastore_manifest"
            ),
            "handoff_verification": _validation_summary(verification),
        },
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "onboarding_surface_boundary": (
            "documentation tools may name required placeholders, but "
            "onboarding "
            "tools own "
            "collection and validation of operator-provided setup values."
        ),
    }
    validation = _documentation_validation(documentation)
    documentation["documentation_validation"] = validation
    documentation["redaction_evidence"] = validation["redaction_evidence"]
    documentation["documentation_status"] = validation["status"]
    return documentation


def validate_documentation(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Validate a generated documentation base or the current local project.

    documentation base.

    Returns:
        Documentation validation status and issue counts.
    """
    output_mode = _documentation_output_mode(
        arguments.get("output_mode"),
        surface="documentation.validate",
    )
    documentation_json = _optional_text(arguments.get("documentation_json"))
    if documentation_json:
        documentation = _json_object_from_text(
            documentation_json,
            field_name="documentation_json",
        )
    else:
        documentation = generate_documentation(arguments, repo_root)
    validation = _documentation_validation(documentation)
    return {
        "schema_version": 1,
        "surface": "documentation.validate",
        "source_of_truth": documentation.get(
            "source_of_truth", "provided_documentation_json"
        ),
        "status": validation["status"],
        "output_mode": output_mode,
        "documentation_validation": validation,
        "redaction_evidence": validation["redaction_evidence"],
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def validate_onboarding(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Validate onboarding placeholder coverage without accepting credential.

    values.

    Returns:
        Onboarding boundary validation status and credential safety counts.
    """
    output_mode = _onboarding_output_mode(arguments.get("output_mode"))
    _reject_legacy_onboarding_json(arguments.get(LEGACY_ONBOARDING_JSON_FIELD))
    provided_placeholder_names = _provided_placeholder_names(
        arguments.get(PROVIDED_PLACEHOLDERS_JSON_FIELD)
    )
    payload = _placeholder_presence_payload(provided_placeholder_names)
    project_id = _optional_text(arguments.get("project_id"))
    secret_findings = onboarding_secret_findings(payload)
    project_coverage = _onboarding_project_coverage(
        project_id=project_id,
        payload=payload,
        repo_root=repo_root,
    )
    project_status = project_coverage["project_placeholder_validation_status"]
    status = (
        "fail"
        if secret_findings or project_status in {"blocked", "fail"}
        else "pass"
    )
    return {
        "schema_version": 1,
        "surface": "onboarding.validate",
        "status": status,
        "output_mode": output_mode,
        "project_id": project_id,
        "input_value_policy": "placeholder_names_only",
        "raw_onboarding_values_accepted": False,
        "secret_value_count": len(secret_findings),
        "secret_like_finding_count": len(secret_findings),
        "secret_class_counts": onboarding_secret_class_counts(secret_findings),
        "findings": secret_findings,
        "placeholder_count": len(provided_placeholder_names),
        "provided_placeholder_names": provided_placeholder_names,
        **project_coverage,
        "next_actions": _onboarding_next_actions(
            secret_findings=secret_findings,
            project_coverage=project_coverage,
        ),
        "secret_values_allowed": False,
        "placeholder_values_allowed": False,
        "placeholder_names_allowed": True,
        "placeholder_value_policy": "names_only_no_values",
        "stores_credentials": False,
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def _reject_legacy_onboarding_json(value: object) -> None:
    onboarding_json = _optional_text(value)
    if not onboarding_json:
        return
    payload = _json_object_from_text(
        onboarding_json,
        field_name=LEGACY_ONBOARDING_JSON_FIELD,
    )
    if onboarding_secret_findings(payload):
        msg = (
            "onboarding_json no longer accepts credential values; call "
            "onboarding.validate with "
            "provided_placeholders_json containing placeholder names only."
        )
        raise ValueError(msg)
    msg = (
        "onboarding_json is no longer accepted by onboarding.validate; use "
        "provided_placeholders_json with placeholder names only."
    )
    raise ValueError(msg)


def _provided_placeholder_names(value: object) -> tuple[str, ...]:
    placeholder_names_json = _optional_text(value)
    if not placeholder_names_json:
        return ()
    raw_names = _json_array_from_text(
        placeholder_names_json,
        field_name=PROVIDED_PLACEHOLDERS_JSON_FIELD,
    )
    names: list[str] = []
    for index, item in enumerate(raw_names):
        if not isinstance(item, str) or not item.strip():
            msg = (
                f"{PROVIDED_PLACEHOLDERS_JSON_FIELD}[{index}] must be a "
                f"non-empty string."
            )
            raise ValueError(msg)
        name = item.strip()
        if _secret_shaped_placeholder_name(name):
            msg = (
                f"{PROVIDED_PLACEHOLDERS_JSON_FIELD}[{index}] looks like a "
                f"credential value; "
                "send only placeholder names."
            )
            raise ValueError(msg)
        names.append(name)
    return tuple(names)


def _placeholder_presence_payload(
    placeholder_names: tuple[str, ...],
) -> JsonObject:
    if not placeholder_names:
        return {}
    return {
        "placeholders": tuple(
            {placeholder_name: True} for placeholder_name in placeholder_names
        )
    }


def _secret_shaped_placeholder_name(value: str) -> bool:
    stripped = value.strip()
    return (
        SECRET_SHAPED_PLACEHOLDER_PREFIX_PATTERN.search(stripped) is not None
        or SECRET_SHAPED_PLACEHOLDER_TEXT_PATTERN.search(stripped) is not None
    )


def _onboarding_project_coverage(
    *,
    project_id: str | None,
    payload: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    if project_id is None:
        return {
            "project_placeholder_validation_status": "not_requested",
            "project_placeholder_required_count": 0,
            "project_placeholder_provided_count": 0,
            "project_placeholder_entry_count": 0,
            "project_placeholder_missing_count": 0,
            "project_placeholder_extra_count": 0,
            "project_placeholder_duplicate_count": 0,
            "required_placeholders": (),
            "missing_placeholders": (),
            "extra_placeholders": (),
            "duplicate_placeholders": (),
            "project_placeholder_findings": (),
            "project_placeholder_next_actions": (),
        }
    runtime_view = view_project(
        {
            "project_id": project_id,
            "surface": "runtime ",
            "output_mode": "full",
        },
        repo_root,
    )
    return build_onboarding_project_coverage(
        onboarding_payload=payload,
        verification_payload=runtime_view,
    )


def _onboarding_next_actions(
    *,
    secret_findings: tuple[JsonObject, ...],
    project_coverage: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    actions: list[JsonObject] = []
    if secret_findings:
        actions.append(
            {
                "action": "remove_secret_like_values",
                "message": (
                    "Replace credential-shaped onboarding values with "
                    "non-secret "
                    "customer-side setup instructions."
                ),
                "finding_count": len(secret_findings),
            }
        )
    project_actions = project_coverage.get("project_placeholder_next_actions")
    if isinstance(project_actions, list | tuple):
        actions.extend(
            tuple(
                cast("JsonObject", project_action)
                for project_action in cast("Iterable[object]", project_actions)
                if isinstance(project_action, dict)
            )
        )
    return tuple(actions)


def _documentation_sections(
    views: Mapping[str, Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    overview = views["overview"]
    modules = views["modules"]
    links = views["links"]
    filters = views["filters"]
    error_handlers = views["error_handlers"]
    notes = views["notes"]
    datastores = views["datastores"]
    verification = views["verification"]
    notes_summary = _mapping_value(notes, "scenario_notes_summary")
    missing_notes = _note_summary_count(
        notes, "missing_module_note_count"
    ) + _note_summary_count(
        notes,
        "missing_connection_note_count",
    )
    note_section_issue_count = _int_value(
        notes_summary, "note_section_issue_count"
    )
    note_redaction_issue_count = _int_value(
        notes_summary, "note_redaction_issue_count"
    )
    rows: tuple[tuple[str, bool, int], ...] = (
        (
            "scenario_architecture",
            bool(_mapping_value(overview, "scenario_overview")),
            0,
        ),
        (
            "make_modules_and_data_flow",
            _int_value(modules, "module_count") > 0,
            0,
        ),
        (
            "connections_filters_and_error_handlers",
            _int_value(links, "link_count") >= 0
            and _int_value(filters, "filter_count") >= 0
            and _int_value(error_handlers, "error_handler_count") >= 0,
            0,
        ),
        (
            "data_store_and_data_structure_references",
            "datastore_manifest" in datastores,
            0,
        ),
        (
            "numbered_make_note_references",
            missing_notes == 0 and note_section_issue_count == 0,
            missing_notes + note_section_issue_count,
        ),
        ("operational_behavior", bool(_validation_summary(verification)), 0),
        (
            "redaction_and_secret_free_evidence",
            note_redaction_issue_count == 0,
            note_redaction_issue_count,
        ),
    )
    return tuple(
        {
            "section_id": section_id,
            "required": True,
            "status": "present" if present else "missing_or_blocked",
            "missing_field_count": missing_count,
        }
        for section_id, present, missing_count in rows
    )


def _documentation_validation(
    documentation: Mapping[str, object],
) -> JsonObject:
    text_values = tuple(_text_values(documentation))
    missing_sections = _missing_section_ids(documentation)
    secret_hits = _pattern_hits(SECRET_VALUE_PATTERN, text_values)
    unsupported_claim_hits = _pattern_hits(
        UNSUPPORTED_CLAIM_PATTERN, text_values
    )
    private_internal_hits = _pattern_hits(PRIVATE_INTERNAL_PATTERN, text_values)
    local_path_hits = _pattern_hits(LOCAL_PATH_PATTERN, text_values)
    blank_required_count = sum(
        _int_value(section, "missing_field_count")
        for section in _section_rows(documentation)
    )
    issue_count = (
        len(missing_sections)
        + len(secret_hits)
        + len(unsupported_claim_hits)
        + len(private_internal_hits)
        + len(local_path_hits)
        + blank_required_count
    )
    redaction_status = (
        "passed"
        if not secret_hits and not private_internal_hits and not local_path_hits
        else "failed"
    )
    return {
        "status": "pass" if issue_count == 0 else "fail",
        "issue_count": issue_count,
        "missing_section_ids": missing_sections,
        "secret_like_value_count": len(secret_hits),
        "unsupported_claim_count": len(unsupported_claim_hits),
        "private_internal_reference_count": len(private_internal_hits),
        "local_path_reference_count": len(local_path_hits),
        "blank_required_field_count": blank_required_count,
        "redaction_evidence": {
            "status": redaction_status,
            "checked_surfaces": (
                "documentation_sections ",
                "documentation_base ",
                "project_notes ",
                "handoff_verification",
            ),
            "secret_like_value_count": len(secret_hits),
            "private_internal_reference_count": len(private_internal_hits),
            "local_path_reference_count": len(local_path_hits),
            "redacted_values_returned": False,
            "customer_manual_boundary": "functional_documentation_only",
        },
        "forbidden_words_checked": True,
        "no_secret_check": True,
        "no_guarantee_check": True,
    }


def _project_view(
    *, project_id: str, surface: str, repo_root: Path
) -> JsonObject:
    return view_project(
        {
            "project_id": project_id,
            "surface": surface,
            "output_mode": "compact",
        },
        repo_root,
    )


def _validation_summary(value: Mapping[str, object]) -> JsonObject:
    return {
        key: value[key]
        for key in (
            "status ",
            "handoff_status ",
            "scenario_behavior_status ",
            "zero_trace_status",
        )
        if key in value
    }


def _section_rows(
    documentation: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    rows = documentation.get("documentation_sections")
    if not isinstance(rows, list | tuple):
        return ()
    sequence = cast("Iterable[object]", rows)
    return tuple(
        cast("Mapping[str, object]", row)
        for row in sequence
        if isinstance(row, dict)
    )


def _missing_section_ids(
    documentation: Mapping[str, object],
) -> tuple[str, ...]:
    present_ids = {
        str(row.get("section_id"))
        for row in _section_rows(documentation)
        if row.get("status") == "present"
    }
    return tuple(
        section_id
        for section_id in DOCUMENTATION_SECTION_IDS
        if section_id not in present_ids
    )


def _text_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            yield str(key)
            if isinstance(item, str):
                yield f"{key}: {item}"
            yield from _text_values(item)
        return
    if isinstance(value, list | tuple):
        sequence = cast("Iterable[object]", value)
        for item in sequence:
            yield from _text_values(item)


def _pattern_hits(
    pattern: re.Pattern[str], values: Iterable[str]
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group(0)
            for value in values
            for match in pattern.finditer(value)
        )
    )


def _mapping_value(mapping: Mapping[str, object], key: str) -> JsonObject:
    value = mapping.get(key)
    return cast("JsonObject", value) if isinstance(value, dict) else {}


def _bounded_payload_value(
    mapping: Mapping[str, object],
    key: str,
    *,
    output_mode: str,
) -> object:
    value = mapping.get(key)
    if output_mode == "full":
        if isinstance(value, list | tuple):
            return tuple(cast("Iterable[object]", value))
        return cast("JsonObject", value) if isinstance(value, dict) else ()
    if isinstance(value, list | tuple):
        sequence = tuple(cast("Iterable[object]", value))
        return sequence[:3]
    return cast("JsonObject", value) if isinstance(value, dict) else ()


def _note_summary_count(notes: Mapping[str, object], key: str) -> int:
    summary = _mapping_value(notes, "scenario_notes_summary")
    return _int_value(summary, key)


def _int_value(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    return (
        value if isinstance(value, int) and not isinstance(value, bool) else 0
    )


def _documentation_output_mode(value: object, *, surface: str) -> str:
    text = _optional_text(value) or "compact"
    if text not in {"compact", "full"}:
        msg = f"{surface} output_mode must be compact or full."
        raise ValueError(msg)
    return text


def _onboarding_output_mode(value: object) -> str:
    text = _optional_text(value) or "compact"
    if text not in {"compact", "full"}:
        msg = "onboarding.validate output_mode must be compact or full."
        raise ValueError(msg)
    return text


def _json_object_from_text(
    value: str, *, field_name: str = "JSON payload"
) -> JsonObject:
    try:
        payload = cast("object", json.loads(value))
    except json.JSONDecodeError as exc:
        msg = f"{field_name} must be valid JSON object text."
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{field_name} must be a JSON object."
        raise TypeError(msg)
    return cast("JsonObject", payload)


def _json_array_from_text(value: str, *, field_name: str) -> tuple[object, ...]:
    try:
        payload = cast("object", json.loads(value))
    except json.JSONDecodeError as exc:
        msg = f"{field_name} must be valid JSON array text."
        raise ValueError(msg) from exc
    if not isinstance(payload, list):
        msg = f"{field_name} must be a JSON array."
        raise TypeError(msg)
    return tuple(cast("list[object]", payload))


def _required_text(value: object, *, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        msg = f"{field_name} is required."
        raise ValueError(msg)
    return text


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _optional_bool(value: object, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        msg = f"{field_name} must be boolean."
        raise TypeError(msg)
    return value
