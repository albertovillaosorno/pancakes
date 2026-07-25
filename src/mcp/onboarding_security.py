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

"""Secret-shaped value detection for local MCP onboarding payloads.

Boundary contract:
- Owns: deterministic, redacted classification of setup values
  submitted to onboarding.validate.
- Must not: store credentials, call providers, inspect environment
  variables, or return raw values.
- Allows: local JSON traversal, placeholder-name allowlisting, and
  structured redacted findings.
- Split when: onboarding validation grows project-aware placeholder
  inventory checks.
- Merge when: a shared zero-trace scanner owns the same MCP onboarding contract.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from mcp.models import JsonObject

type JsonPathPart = str | int

SECRET_LIKE_VALUE_CODE: Final = "secret_like_value_detected"
REDACTED_SECRET_VALUE: Final = "[redacted:secret_like_value]"
MIN_GENERIC_SECRET_VALUE_LENGTH: Final = 8
MIN_MIXED_SECRET_CATEGORY_COUNT: Final = 2
MIN_HIGH_ENTROPY_VALUE_LENGTH: Final = 40
MIN_HIGH_ENTROPY_SCORE: Final = 4.0
MIN_HIGH_ENTROPY_CATEGORY_COUNT: Final = 3
MAX_FINDINGS: Final = 100

PLACEHOLDER_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\A(?:\{\{\s*[^}]+\s*\}\}|__[A-Za-z0-9_.:-]+__|<[A-Za-z0-9_.:-]+>)\Z"
)
ENV_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\A[A-Z][A-Z0-9_]{3,}\Z"
)
LONG_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\A[A-Za-z0-9._~+/=-]{40,}\Z"
)
SLACK_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{20,}\b",
    re.IGNORECASE,
)
GOOGLE_API_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bAIza[0-9A-Za-z_-]{35}\b"
)
ANTHROPIC_API_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
    re.IGNORECASE,
)
OPENAI_API_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
    re.IGNORECASE,
)
JWT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
BEARER_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b",
    re.IGNORECASE,
)
OAUTH_TOKEN_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ya29|1//|0\.A)[A-Za-z0-9._~/-]{16,}\b"
)
PRIVATE_KEY_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
)

SECRET_SHAPE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("slack_token", SLACK_TOKEN_PATTERN),
    ("google_api_key", GOOGLE_API_KEY_PATTERN),
    ("anthropic_api_key", ANTHROPIC_API_KEY_PATTERN),
    ("openai_api_key", OPENAI_API_KEY_PATTERN),
    ("jwt", JWT_PATTERN),
    ("bearer_token", BEARER_TOKEN_PATTERN),
    ("oauth_token", OAUTH_TOKEN_VALUE_PATTERN),
    ("private_key_block", PRIVATE_KEY_BLOCK_PATTERN),
)
SECRET_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "accesstoken",
        "apikey",
        "apitoken",
        "authorization",
        "bearer",
        "clientsecret",
        "credential",
        "oauth",
        "password",
        "refreshtoken",
        "secret",
        "slacktoken",
        "token",
        "webhooksecret",
        "xhookkey",
    )
)
SAFE_PLACEHOLDER_WORDS: Final[frozenset[str]] = frozenset(
    (
        "changeme",
        "dummy",
        "example",
        "placeholder",
        "redacted",
        "sample",
    )
)


class OnboardingTextValue(NamedTuple):
    """One text value with path context for secret classification."""

    path: tuple[JsonPathPart, ...]
    value: str


def onboarding_secret_findings(value: object) -> tuple[JsonObject, ...]:
    """Return redacted secret-like findings for an onboarding payload."""
    findings: list[JsonObject] = []
    for text_value in _text_values(value, path=()):
        classification = _secret_classification(text_value)
        if classification is None:
            continue
        findings.append(
            _finding_payload(
                text_value=text_value, classification=classification
            )
        )
        if len(findings) >= MAX_FINDINGS:
            break
    return tuple(findings)


def onboarding_secret_class_counts(
    findings: Iterable[Mapping[str, object]],
) -> JsonObject:
    """Return deterministic secret classification counts."""
    counts: dict[str, int] = {}
    for finding in findings:
        classification = finding.get("classification")
        if not isinstance(classification, str):
            continue
        counts[classification] = counts.get(classification, 0) + 1
    return cast("JsonObject", dict(sorted(counts.items())))


def _text_values(
    value: object, *, path: tuple[JsonPathPart, ...]
) -> Iterable[OnboardingTextValue]:
    if isinstance(value, str):
        yield OnboardingTextValue(path=path, value=value)
        return
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            key_text = str(key)
            yield from _text_values(item, path=(*path, key_text))
        return
    if isinstance(value, list | tuple):
        sequence = cast("Iterable[object]", value)
        for index, item in enumerate(sequence):
            yield from _text_values(item, path=(*path, index))


def _secret_classification(text_value: OnboardingTextValue) -> str | None:
    value = text_value.value.strip()
    if not value or _safe_placeholder_value(value):
        return None
    for classification, pattern in SECRET_SHAPE_PATTERNS:
        if pattern.search(value) is not None:
            return classification
    if _secret_field_path(text_value.path) and _secret_field_value(value):
        return "secret_field_value"
    if _long_high_entropy_value(value):
        return "high_entropy_value"
    return None


def _finding_payload(
    *, text_value: OnboardingTextValue, classification: str
) -> JsonObject:
    return {
        "code": SECRET_LIKE_VALUE_CODE,
        "severity": "error",
        "classification": classification,
        "json_path": _json_path(text_value.path),
        "message": (
            "Onboarding payload contains a secret-like value; "
            "raw value redacted."
        ),
        "redacted_value": REDACTED_SECRET_VALUE,
    }


def _secret_field_path(path: tuple[JsonPathPart, ...]) -> bool:
    normalized_path = ".".join(_normalize_token(str(part)) for part in path)
    return any(token in normalized_path for token in SECRET_FIELD_TOKENS)


def _secret_field_value(value: str) -> bool:
    if len(value) < MIN_GENERIC_SECRET_VALUE_LENGTH or _safe_placeholder_value(
        value
    ):
        return False
    if any(
        pattern.search(value) is not None
        for _, pattern in SECRET_SHAPE_PATTERNS
    ):
        return True
    if _long_high_entropy_value(value):
        return True
    normalized = _normalize_token(value)
    if any(
        word in normalized
        for word in ("secret", "token", "apikey", "credential")
    ):
        return True
    return _has_mixed_secret_value_characters(value)


def _safe_placeholder_value(value: str) -> bool:
    stripped = value.strip()
    normalized = _normalize_token(stripped)
    if not stripped:
        return True
    if PLACEHOLDER_VALUE_PATTERN.fullmatch(stripped) is not None:
        return True
    if ENV_PLACEHOLDER_PATTERN.fullmatch(stripped) is not None:
        return True
    return any(word in normalized for word in SAFE_PLACEHOLDER_WORDS)


def _long_high_entropy_value(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < MIN_HIGH_ENTROPY_VALUE_LENGTH:
        return False
    if LONG_TOKEN_PATTERN.fullmatch(stripped) is None:
        return False
    if _character_category_count(stripped) < MIN_HIGH_ENTROPY_CATEGORY_COUNT:
        return False
    return _shannon_entropy(stripped) >= MIN_HIGH_ENTROPY_SCORE


def _has_mixed_secret_value_characters(value: str) -> bool:
    return _character_category_count(
        value
    ) >= MIN_MIXED_SECRET_CATEGORY_COUNT and any(
        character.isdigit() for character in value
    )


def _character_category_count(value: str) -> int:
    categories = {
        "lower": any(character.islower() for character in value),
        "upper": any(character.isupper() for character in value),
        "digit": any(character.isdigit() for character in value),
        "symbol": any(not character.isalnum() for character in value),
    }
    return sum(1 for present in categories.values() if present)


def _shannon_entropy(value: str) -> float:
    length = len(value)
    if length == 0:
        return 0.0
    frequencies = {
        character: value.count(character) for character in set(value)
    }
    return -sum(
        (count / length) * math.log2(count / length)
        for count in frequencies.values()
    )


def _json_path(path: tuple[JsonPathPart, ...]) -> str:
    if not path:
        return "$"
    result = "$"
    for part in path:
        if isinstance(part, int):
            result = f"{result}[{part}]"
        elif _simple_json_path_part(part):
            result = f"{result}.{part}"
        else:
            result = f"{result}[{part!r}]"
    return result


def _simple_json_path_part(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))


def _normalize_token(value: str) -> str:
    return "".join(
        character for character in value.casefold() if character.isalnum()
    )
