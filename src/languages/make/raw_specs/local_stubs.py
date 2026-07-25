# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.operator-approved-local-stubs
# - 001042#repo.make-catalog.raw-specs-and-catalog-authority
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Operator-approved local raw-spec stubs.

Boundary contract:
- Owns: typed parsing and matching for local operator-approved raw-spec stubs.
- Must not: compile catalog modules, fetch Make data, write files, or
  validate blueprints.
- Allows: provenance field validation and deterministic module-token matching.
- Split when: stub persistence or knowledge-store promotion becomes
  separate workflow.
- Merge when: another raw-spec module owns the same local stub contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.tokens import (
    module_token_parts,
    module_token_resolution_key,
)

if TYPE_CHECKING:
    from languages.make.raw_specs.models import JsonObject

OPERATOR_APPROVED_LOCAL_STUB_SOURCE: Final = "operator-approved-local-stub"


class OperatorApprovedRawSpecStub(NamedTuple):
    """One operator-approved local raw-spec evidence placeholder."""

    module_token: str
    source: str
    approval_timestamp: str
    operator_note: str
    unsupported_fields: tuple[str, ...]
    operator_approved: bool


def operator_approved_raw_spec_stub_from_json(
    payload: JsonObject,
) -> OperatorApprovedRawSpecStub:
    """Return one validated operator-approved local raw-spec stub.

    Returns:
        The validated local raw-spec stub.

    Raises:
        PermissionError: If the stub is not explicitly operator-approved.
        ValueError: If a required provenance member is missing or invalid.
    """
    module_token = _required_text(payload, "module_token")
    _ = module_token_parts(module_token)
    source = _required_text(payload, "source")
    required_source = OPERATOR_APPROVED_LOCAL_STUB_SOURCE
    if source != required_source:
        message = f"Local raw-spec stubs must use source {required_source!r}."
        raise ValueError(message)
    approval_timestamp = _required_text(payload, "approval_timestamp")
    _require_timezone_timestamp(approval_timestamp)
    operator_note = _required_text(payload, "operator_note")
    unsupported_fields = _required_text_tuple(payload, "unsupported_fields")
    operator_approved = _required_bool(payload, "operator_approved")
    if operator_approved is not True:
        message = "Local raw-spec stubs require operator_approved=true."
        raise PermissionError(message)
    return OperatorApprovedRawSpecStub(
        module_token=module_token,
        source=source,
        approval_timestamp=approval_timestamp,
        operator_note=operator_note,
        unsupported_fields=unsupported_fields,
        operator_approved=operator_approved,
    )


def find_operator_approved_raw_spec_stub(
    *,
    module_token: str,
    stubs: tuple[OperatorApprovedRawSpecStub, ...],
) -> OperatorApprovedRawSpecStub | None:
    """Return a matching operator-approved local stub, if one exists."""
    try:
        expected = _stub_key(module_token)
    except ValueError:
        return None
    candidates = tuple(
        stub
        for stub in stubs
        if stub.operator_approved and _stub_key(stub.module_token) == expected
    )
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda stub: (
            stub.source,
            stub.approval_timestamp,
            stub.module_token.casefold(),
        ),
    )


def _stub_key(module_token: str) -> tuple[str, str]:
    app_slug, internal_name = module_token_parts(module_token)
    return (
        app_slug.casefold(),
        module_token_resolution_key(internal_name),
    )


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Local raw-spec stub member {key!r} must be non-empty text."
        raise ValueError(message)
    return value.strip()


def _required_text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    if key not in payload:
        message = _non_empty_string_list_message(key)
        raise ValueError(message)
    value = payload.get(key)
    if not isinstance(value, list):
        message = _non_empty_string_list_message(key)
        raise TypeError(message)
    items: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str) or not item.strip():
            message = _non_empty_string_list_message(key)
            raise ValueError(message)
        items.append(item.strip())
    if not items:
        message = _non_empty_string_list_message(key)
        raise ValueError(message)
    return tuple(sorted(dict.fromkeys(items)))


def _required_bool(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        message = f"Local raw-spec stub member {key!r} must be a boolean."
        raise TypeError(message)
    return value


def _require_timezone_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        message = (
            "Local raw-spec stub approval_timestamp must include a timezone."
        )
        raise ValueError(message)


def _non_empty_string_list_message(key: str) -> str:
    prefix = f"Local raw-spec stub member {key!r}"
    return f"{prefix} must be a non-empty string list."
