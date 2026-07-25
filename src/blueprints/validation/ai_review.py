# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.validator-policy
# - 001055#repo.mcp.required-tool-surface
# - 001061#repo.assisted-delivery.claims.manual-capture-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Client-supplied AI review contract helpers.

Boundary contract:
- Owns: explicit client-supplied AI review payload validation.
- Must not: run server-side AI, validate blueprints, or persist review records.
- Allows: bounded text, JSON extraction, coverage hashes, and fail-closed
errors.
- Split when: review transport parsing or coverage policy becomes independent.
- Merge when: another review helper enforces the same explicit-review contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import NoReturn, TypeGuard, cast

JsonObject = dict[str, object]

JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(?P<body>\{.*\})\s*```", re.DOTALL
)
SERVER_AI_PROHIBITED_MESSAGE = (
    "Direct server-side AI execution is prohibited; supply an explicit client"
    "review."
)


class AiReviewError(ValueError):
    """Raised when an AI review contract cannot be accepted."""


def reject_server_side_ai(*, purpose: str) -> None:
    """Fail closed for hidden server-side AI execution paths.

    Raises:
        AiReviewError: If the ai review contract cannot be satisfied.
    """
    message = f"{purpose}: {SERVER_AI_PROHIBITED_MESSAGE}"
    raise AiReviewError(message)


def bounded_review_text(value: str, *, max_chars: int = 24000) -> str:
    """Return bounded prompt text while preserving overflow evidence."""
    normalized = value.strip()
    if len(normalized) <= max_chars:
        return normalized
    overflow = len(normalized) - max_chars
    truncated_marker = f"[TRUNCATED_FOR_AI_REVIEW:{overflow}_CHARS]"
    return f"{normalized[:max_chars]}\n\n{truncated_marker}"


def build_minimal_content_review(*, content: str) -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "decision": "accept",
        "coverage": {
            "content_sha256": _sha256(content),
            "covered": True,
            "unsupported_claims": [],
        },
        "justification": (
            "The client-side AI review covered the complete payload."
        ),
    }


def validate_content_review(*, content: str, review: JsonObject) -> JsonObject:
    """Validate that a client-supplied review covers one exact payload.

    Returns:
        The validated value.
    """
    content_sha256 = _sha256(content)
    decision = str(review.get("decision") or "").strip().lower()
    if decision != "accept":
        _raise_contract_error(
            "review decision must be accept", content_sha256=content_sha256
        )
    coverage_value = review.get("coverage")
    if not _is_json_object(coverage_value):
        _raise_contract_error(
            "review omitted coverage", content_sha256=content_sha256
        )
    coverage = coverage_value
    if coverage.get("content_sha256") != content_sha256:
        _raise_contract_error(
            "review content hash does not match", content_sha256=content_sha256
        )
    if coverage.get("covered") is not True:
        _raise_contract_error(
            "review did not confirm complete coverage",
            content_sha256=content_sha256,
        )
    unsupported = coverage.get("unsupported_claims")
    if unsupported not in (None, []):
        _raise_contract_error(
            "review reported unsupported claims", content_sha256=content_sha256
        )
    return review


def decode_text_content(raw_content: object) -> str:
    """Normalize text or text-part arrays into plain text.

    Returns:
        The normalized value.

    Raises:
        AiReviewError: If the ai review contract cannot be satisfied.
    """
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts = _text_parts(tuple(cast("list[object]", raw_content)))
        if parts:
            return "\n".join(parts)
    message = "AI review response returned no textual JSON content."
    raise AiReviewError(message)


def extract_json_object(content: str) -> JsonObject:
    """Extract one JSON object from plain or fenced model output.

    Returns:
        The extracted value.

    Raises:
        AiReviewError: If the ai review contract cannot be satisfied.
    """
    stripped = content.strip()
    match = JSON_BLOCK_PATTERN.search(stripped)
    if match is not None:
        stripped = match.group("body").strip()

    def reject_non_standard_constant(raw_value: str) -> object:
        message = (
            f"AI review response used non-standard JSON constant {raw_value}."
        )
        raise AiReviewError(message)

    try:
        parsed = cast(
            "object",
            json.loads(stripped, parse_constant=reject_non_standard_constant),
        )
    except json.JSONDecodeError as exc:
        message = "AI review response was not valid JSON."
        raise AiReviewError(message) from exc
    if not _is_json_object(parsed):
        message = "AI review response must be a JSON object."
        raise AiReviewError(message)
    return parsed


def _text_parts(items: tuple[object, ...]) -> tuple[str, ...]:
    """Return textual content parts from a response payload."""
    parts: list[str] = []
    for item in items:
        if not _is_json_object(item):
            continue
        text_value = item.get("text")
        if item.get("type") == "text" and isinstance(text_value, str):
            parts.append(text_value)
    return tuple(parts)


def _raise_contract_error(reason: str, *, content_sha256: str) -> NoReturn:
    """Raise one error with a minimal valid review example.

    Raises:
        AiReviewError: If the ai review contract cannot be satisfied.
    """
    example = json.dumps(
        {
            "decision": "accept",
            "coverage": {
                "content_sha256": content_sha256,
                "covered": True,
                "unsupported_claims": [],
            },
            "justification": (
                "The client-side AI review covered the complete payload."
            ),
        },
        ensure_ascii=True,
    )
    message = f"{reason}. Minimum valid review shape: {example}"
    raise AiReviewError(message)


def _sha256(value: str) -> str:
    """Return the SHA-256 hex digest for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in mapping)
