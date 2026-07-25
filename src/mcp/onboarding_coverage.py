# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001067#repo.mcp.client-routing.native-gpt-latency-and-output
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Project-aware runtime placeholder coverage for MCP onboarding validation.

Boundary contract:
- Owns: local comparison between onboarding form placeholder inputs and project
runtime setup.
- Must not: store submitted values, return raw values, mutate projects, or call
live providers.
- Allows: placeholder-key normalization, duplicate detection, and customer
next-action summaries.
- Split when: onboarding gets persisted draft state or field-level form schema
generation.
- Merge when: project.verify owns the same form coverage response contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from mcp.models import JsonObject

type JsonPathPart = str | int

PLACEHOLDERS_OBJECT_KEY: Final = "placeholders"
MISSING_PLACEHOLDER_CODE: Final = "onboarding.placeholder_missing"
EXTRA_PLACEHOLDER_CODE: Final = "onboarding.placeholder_extra"
DUPLICATE_PLACEHOLDER_CODE: Final = "onboarding.placeholder_duplicate"


class OnboardingPlaceholderEntry(NamedTuple):
    """One placeholder field supplied in an onboarding payload."""

    raw_name: str
    canonical_name: str | None
    path: tuple[JsonPathPart, ...]
    has_value: bool


def build_onboarding_project_coverage(
    *,
    onboarding_payload: Mapping[str, object],
    verification_payload: Mapping[str, object],
) -> JsonObject:
    """Return project-aware runtime placeholder coverage for one onboarding.

    payload.
    """
    if verification_payload.get("error_code"):
        return _blocked_project_payload(verification_payload)

    required = _required_placeholders(verification_payload)
    aliases = _placeholder_aliases(required)
    entries = _placeholder_entries(onboarding_payload, aliases=aliases)
    provided = tuple(
        entry for entry in entries if entry.canonical_name is not None
    )
    provided_names = {
        entry.canonical_name for entry in provided if entry.has_value
    }
    missing = tuple(name for name in required if name not in provided_names)
    extra = tuple(entry for entry in entries if entry.canonical_name is None)
    duplicates = _duplicate_placeholders(provided)
    findings = (
        *_missing_findings(missing),
        *_extra_findings(extra),
        *_duplicate_findings(duplicates),
    )
    status = "pass" if not findings else "fail"
    return {
        "project_placeholder_validation_status": status,
        "project_placeholder_required_count": len(required),
        "project_placeholder_provided_count": len(provided_names),
        "project_placeholder_entry_count": len(entries),
        "project_placeholder_missing_count": len(missing),
        "project_placeholder_extra_count": len(extra),
        "project_placeholder_duplicate_count": len(duplicates),
        "required_placeholders": required,
        "missing_placeholders": missing,
        "extra_placeholders": tuple(entry.raw_name for entry in extra),
        "duplicate_placeholders": duplicates,
        "project_placeholder_findings": findings,
        "project_placeholder_next_actions": _next_actions(
            missing=missing,
            extra=extra,
            duplicates=duplicates,
        ),
    }


def _blocked_project_payload(
    verification_payload: Mapping[str, object],
) -> JsonObject:
    return {
        "project_placeholder_validation_status": "blocked",
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
        "project_placeholder_findings": (
            {
                "code": "onboarding.project_unavailable ",
                "severity": "error ",
                "message": (
                    "Project placeholder requirements could not be loaded."
                ),
                "project_status": verification_payload.get("status", "blocked"),
                "project_error_code": verification_payload.get(
                    "error_code", "project_blocked"
                ),
            },
        ),
        "project_placeholder_next_actions": (
            {
                "action": "create_or_select_project",
                "tool": verification_payload.get(
                    "next_action", "project.create"
                ),
                "message": (
                    "Create or select the local project before collecting "
                    "onboarding values."
                ),
            },
        ),
    }


def _required_placeholders(
    verification_payload: Mapping[str, object],
) -> tuple[str, ...]:
    groups: object = verification_payload.get("runtime_setup_groups")
    runtime = verification_payload.get("runtime")
    if isinstance(runtime, Mapping):
        runtime_mapping = cast("Mapping[str, object]", runtime)
        groups = runtime_mapping.get("groups")
    if not isinstance(groups, list | tuple):
        return ()
    required: set[str] = set()
    for group in cast("Iterable[object]", groups):
        if not isinstance(group, dict):
            continue
        group_mapping = cast("Mapping[str, object]", group)
        source = group_mapping.get("source")
        if not isinstance(source, str):
            continue
        placeholder = _strip_placeholder_braces(source)
        if placeholder:
            required.add(placeholder)
    return tuple(sorted(required))


def _placeholder_aliases(required: Iterable[str]) -> Mapping[str, str]:
    aliases: dict[str, str] = {}
    for placeholder in required:
        for alias in (
            placeholder,
            f"{{{{{placeholder}}}}}",
            placeholder.replace(".", "_"),
        ):
            aliases[_normalize_placeholder_name(alias)] = placeholder
    return aliases


def _placeholder_entries(
    value: object,
    *,
    aliases: Mapping[str, str],
    path: tuple[JsonPathPart, ...] = (),
) -> tuple[OnboardingPlaceholderEntry, ...]:
    entries: list[OnboardingPlaceholderEntry] = []
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            key_text = str(key)
            item_path = (*path, key_text)
            if key_text == PLACEHOLDERS_OBJECT_KEY and isinstance(
                item, Mapping
            ):
                for placeholder_key, placeholder_value in cast(
                    "Mapping[object, object]",
                    item,
                ).items():
                    placeholder_name = str(placeholder_key)
                    entries.append(
                        _entry(
                            raw_name=placeholder_name,
                            value=placeholder_value,
                            path=(*item_path, placeholder_name),
                            aliases=aliases,
                        )
                    )
                    entries.extend(
                        _placeholder_entries(
                            placeholder_value,
                            aliases=aliases,
                            path=(*item_path, placeholder_name),
                        )
                    )
                continue
            if _placeholder_like_key(key_text, aliases=aliases):
                entries.append(
                    _entry(
                        raw_name=key_text,
                        value=item,
                        path=item_path,
                        aliases=aliases,
                    )
                )
            entries.extend(
                _placeholder_entries(item, aliases=aliases, path=item_path)
            )
        return tuple(entries)
    if isinstance(value, list | tuple):
        for index, item in enumerate(cast("Iterable[object]", value)):
            entries.extend(
                _placeholder_entries(item, aliases=aliases, path=(*path, index))
            )
    return tuple(entries)


def _entry(
    *,
    raw_name: str,
    value: object,
    path: tuple[JsonPathPart, ...],
    aliases: Mapping[str, str],
) -> OnboardingPlaceholderEntry:
    canonical_name = aliases.get(_normalize_placeholder_name(raw_name))
    return OnboardingPlaceholderEntry(
        raw_name=raw_name,
        canonical_name=canonical_name,
        path=path,
        has_value=_has_nonempty_value(value),
    )


def _placeholder_like_key(value: str, *, aliases: Mapping[str, str]) -> bool:
    normalized = _normalize_placeholder_name(value)
    return normalized in aliases or normalized.startswith("runtime.")


def _duplicate_placeholders(
    entries: Iterable[OnboardingPlaceholderEntry],
) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for entry in entries:
        if not entry.has_value or entry.canonical_name is None:
            continue
        if entry.canonical_name in seen:
            duplicates.add(entry.canonical_name)
        seen.add(entry.canonical_name)
    return tuple(sorted(duplicates))


def _missing_findings(missing: Iterable[str]) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "code": MISSING_PLACEHOLDER_CODE,
            "severity": "error",
            "placeholder": placeholder,
            "message": (
                "Required project runtime placeholder is missing from "
                "onboarding input."
            ),
        }
        for placeholder in missing
    )


def _extra_findings(
    entries: Iterable[OnboardingPlaceholderEntry],
) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "code": EXTRA_PLACEHOLDER_CODE,
            "severity": "warning",
            "placeholder": entry.raw_name,
            "json_path": _json_path(entry.path),
            "message": (
                "Onboarding input contains a placeholder not required "
                "by this project."
            ),
        }
        for entry in entries
    )


def _duplicate_findings(duplicates: Iterable[str]) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "code": DUPLICATE_PLACEHOLDER_CODE,
            "severity": "error",
            "placeholder": placeholder,
            "message": (
                "Onboarding input supplies the same project placeholder "
                "more than once."
            ),
        }
        for placeholder in duplicates
    )


def _next_actions(
    *,
    missing: tuple[str, ...],
    extra: tuple[OnboardingPlaceholderEntry, ...],
    duplicates: tuple[str, ...],
) -> tuple[JsonObject, ...]:
    actions: list[JsonObject] = []
    if missing:
        actions.append(
            {
                "action": "provide_missing_placeholders",
                "placeholders": missing,
                "message": (
                    "Collect values for every required runtime setup "
                    "placeholder."
                ),
            }
        )
    if extra:
        actions.append(
            {
                "action": "remove_extra_placeholders",
                "placeholders": tuple(entry.raw_name for entry in extra),
                "message": (
                    "Remove onboarding fields that are not required by "
                    "this project."
                ),
            }
        )
    if duplicates:
        actions.append(
            {
                "action": "deduplicate_placeholders",
                "placeholders": duplicates,
                "message": (
                    "Keep exactly one onboarding value for each runtime "
                    "placeholder."
                ),
            }
        )
    if not actions:
        actions.append(
            {
                "action": "ready_for_customer_form ",
                "message": (
                    "All required project placeholders are represented once."
                ),
            }
        )
    return tuple(actions)


def _has_nonempty_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _strip_placeholder_braces(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        return stripped[2:-2].strip()
    return stripped


def _normalize_placeholder_name(value: str) -> str:
    return _strip_placeholder_braces(value).strip()


def _json_path(path: tuple[JsonPathPart, ...]) -> str:
    if not path:
        return "$"
    result = "$"
    for part in path:
        if isinstance(part, int):
            result = f"{result}[{part}]"
        elif part.isidentifier():
            result = f"{result}.{part}"
        else:
            result = f"{result}[{part!r}]"
    return result
