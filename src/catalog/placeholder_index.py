# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Canonical technical placeholder index for catalog lookup surfaces.

Boundary contract:
- Owns: reusable placeholder names and deterministic example-text matching.
- Must not: mutate catalog rows, author semantic answers, or inspect provider
state.
- Allows: read-only prompt/search guidance for replacing example people and
sample PII.
- Split when: placeholder definitions move into a SQLite-backed catalog table.
- Merge when: another catalog module owns the same canonical placeholder names.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple


class CatalogPlaceholderDefinition(NamedTuple):
    """One canonical technical placeholder definition."""

    placeholder: str
    canonical_kind: str
    canonical_use: str
    replaces: str
    examples: tuple[str, ...]
    aliases: tuple[str, ...]
    detection_pattern: str


class CatalogPlaceholderReplacement(NamedTuple):
    """One deterministic placeholder replacement span."""

    placeholder: str
    canonical_kind: str
    matched_text: str
    start: int
    end: int


CATALOG_PLACEHOLDER_INDEX: Final[tuple[CatalogPlaceholderDefinition, ...]] = (
    CatalogPlaceholderDefinition(
        placeholder="[PERSON_FULL_NAME_FORMAT_1]",
        canonical_kind="person_full_name",
        canonical_use="Human full-name examples.",
        replaces=(
            "Full names such as John Doe or Jane Smith when they are examples."
        ),
        examples=("John Doe", "Jane Smith"),
        aliases=("full name", "person full name", "john doe", "jane smith"),
        detection_pattern=r"\b(?:john\s+doe|jane\s+smith)\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[PERSON_FIRST_NAME_FORMAT_1]",
        canonical_kind="person_first_name",
        canonical_use="Human first-name examples.",
        replaces="First names such as John or Jane when they are examples.",
        examples=("John", "Jane"),
        aliases=("first name", "given name", "john", "jane"),
        detection_pattern=r"\b(?:john|jane)\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[PERSON_LAST_NAME_FORMAT_1]",
        canonical_kind="person_last_name",
        canonical_use="Human last-name examples.",
        replaces="Last names such as Doe or Smith when they are examples.",
        examples=("Doe", "Smith"),
        aliases=("last name", "family name", "surname", "doe", "smith"),
        detection_pattern=r"\b(?:doe|smith)\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[EMAIL_ADDRESS_FORMAT_1]",
        canonical_kind="email_address",
        canonical_use="Email-address examples.",
        replaces="Example personal or business email addresses.",
        examples=("jdoe@example.com", "user@example.com"),
        aliases=(
            "email address",
            "jdoe@example.com",
            "jdoe@email.com",
            "user@example.com",
        ),
        detection_pattern=r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[URL_FORMAT_1]",
        canonical_kind="url",
        canonical_use="URL examples.",
        replaces="Example web URLs that are not evidence URLs.",
        examples=("https://example.com", "https://example.org"),
        aliases=("https://example.com", "http://example.com", "example.com"),
        detection_pattern=r"\bhttps?://(?:www\.)?example\.(?:com|org|net)\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[POSTAL_ADDRESS_FORMAT_1]",
        canonical_kind="postal_address",
        canonical_use="Postal-address examples.",
        replaces="Example street addresses.",
        examples=("123 Main St", "123 Main Street"),
        aliases=("postal address", "123 main st", "123 main street"),
        detection_pattern=(
            r"\b\d{1,6}\s+[a-z0-9 .'-]+\s+"
            r"(st|street|ave|avenue|road|rd|boulevard|blvd)\b"
        ),
    ),
    CatalogPlaceholderDefinition(
        placeholder="[PHONE_NUMBER_FORMAT_1]",
        canonical_kind="phone_number",
        canonical_use="Phone-number examples.",
        replaces="Example telephone numbers such as +55 55555.",
        examples=("+55 55555", "+1 555 123 4567", "555-123-4567"),
        aliases=(
            "phone number",
            "telephone number",
            "+55 55555",
            "+1 555 123 4567",
            "555-123-4567",
        ),
        detection_pattern=(
            r"(?<!\w)(?:"
            r"(?:\+1[- .]?)?(?:\(\d{3}\)|\d{3})[- .]\d{3}[- .]\d{4}"
            r"|\+\d{1,3}[- .]?\d{4,14}(?:[- .]?\d{2,14})?"
            r")(?!\w)"
        ),
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATETIME_ISO_UTC_FORMAT_1]",
        canonical_kind="datetime_iso_utc",
        canonical_use="ISO-8601 UTC datetime examples.",
        replaces="Example timestamps shaped like YYYY-MM-DDTHH:MM:SSZ.",
        examples=("2026-01-31T10:30:00Z",),
        aliases=("2026-01-31t10:30:00z", "datetime iso utc"),
        detection_pattern=r"\b20\d{2}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}z\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATETIME_YYYY_MM_DD_HH_MM_SS_FORMAT_1]",
        canonical_kind="datetime_yyyy_mm_dd_hh_mm_ss",
        canonical_use=(
            "Datetime examples with a four-digit year and second precision."
        ),
        replaces="Example timestamps shaped like YYYY-MM-DD HH:MM:SS.",
        examples=("2026-01-31 10:30:00",),
        aliases=("2026-01-31 10:30:00", "datetime yyyy-mm-dd hh:mm:ss"),
        detection_pattern=r"\b20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATETIME_MM_DD_YY_HH_MM_FORMAT_1]",
        canonical_kind="datetime_mm_dd_yy_hh_mm",
        canonical_use="Datetime examples with a two-digit year.",
        replaces="Example timestamps shaped like MM/DD/YY HH:MM.",
        examples=("01/31/26 10:30",),
        aliases=("01/31/26 10:30", "datetime mm/dd/yy hh:mm"),
        detection_pattern=r"\b\d{1,2}/\d{1,2}/\d{2}\s+\d{1,2}:\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATETIME_MM_DD_YYYY_HH_MM_FORMAT_1]",
        canonical_kind="datetime_mm_dd_yyyy_hh_mm",
        canonical_use="Datetime examples with a four-digit year.",
        replaces="Example timestamps shaped like MM/DD/YYYY HH:MM.",
        examples=("01/31/2026 10:30",),
        aliases=("01/31/2026 10:30", "datetime mm/dd/yyyy hh:mm"),
        detection_pattern=r"\b\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATE_YYYY_MM_DD_FORMAT_1]",
        canonical_kind="date_yyyy_mm_dd",
        canonical_use="Date examples with a four-digit year first.",
        replaces="Example calendar dates shaped like YYYY-MM-DD.",
        examples=("2026-01-31",),
        aliases=("2026-01-31", "date yyyy-mm-dd"),
        detection_pattern=r"\b20\d{2}-\d{2}-\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATE_MM_DD_YY_FORMAT_1]",
        canonical_kind="date_mm_dd_yy",
        canonical_use="Date examples with a two-digit year.",
        replaces="Example calendar dates shaped like MM/DD/YY.",
        examples=("01/31/26",),
        aliases=("01/31/26", "date mm/dd/yy"),
        detection_pattern=r"\b\d{1,2}/\d{1,2}/\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[DATE_MM_DD_YYYY_FORMAT_1]",
        canonical_kind="date_mm_dd_yyyy",
        canonical_use="Date examples with a four-digit year.",
        replaces="Example calendar dates shaped like MM/DD/YYYY.",
        examples=("01/31/2026",),
        aliases=("01/31/2026", "date mm/dd/yyyy"),
        detection_pattern=r"\b\d{1,2}/\d{1,2}/20\d{2}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[UUID_FORMAT_1]",
        canonical_kind="uuid",
        canonical_use="UUID examples.",
        replaces="Example UUID values.",
        examples=("00000000-0000-4000-8000-000000000000",),
        aliases=("00000000-0000-4000-8000-000000000000",),
        detection_pattern=(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
        ),
    ),
    CatalogPlaceholderDefinition(
        placeholder="[IP_ADDRESS_FORMAT_1]",
        canonical_kind="ip_address",
        canonical_use="IP-address examples.",
        replaces="Example IPv4 addresses.",
        examples=("192.0.2.1", "203.0.113.10"),
        aliases=("192.0.2.1", "127.0.0.1"),
        detection_pattern=r"\b(?:192\.0\.2|198\.51\.100|203\.0\.113|127\.0\.0)\.\d{1,3}\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[CURRENCY_AMOUNT_FORMAT_1]",
        canonical_kind="currency_amount",
        canonical_use="Currency amount examples.",
        replaces="Example monetary amounts.",
        examples=("$12.34", "USD 12.34"),
        aliases=("$12.34", "usd 12.34"),
        detection_pattern=r"\b(?:usd|eur|gbp)\s?\d+(?:\.\d{2})?\b|\$\d+(?:\.\d{2})?\b",
    ),
    CatalogPlaceholderDefinition(
        placeholder="[SECRET_VALUE_FORMAT_1]",
        canonical_kind="secret_value",
        canonical_use="Secret, token, password, and API-key examples.",
        replaces="Example secrets and credential-bearing values.",
        examples=("api key", "access token", "password"),
        aliases=(
            "api key",
            "access token",
            "bearer token",
            "password",
            "secret",
        ),
        detection_pattern=(
            r"\b(?:api key|access[_ -]?token|auth[_ -]?token|bearer[_ -]?token|"
            r"refresh[_ -]?token|password|secret)\b"
        ),
    ),
    CatalogPlaceholderDefinition(
        placeholder="[CREDIT_CARD_FORMAT_1]",
        canonical_kind="payment_card_number",
        canonical_use="Payment-card examples.",
        replaces="Example credit or debit card numbers.",
        examples=("4242 4242 4242 4242", "4111 1111 1111 1111"),
        aliases=("4242 4242 4242 4242", "4111 1111 1111 1111"),
        detection_pattern=(
            r"\b(?:4242[ -]?4242[ -]?4242[ -]?4242|"
            r"4111[ -]?1111[ -]?1111[ -]?1111)\b"
        ),
    ),
    CatalogPlaceholderDefinition(
        placeholder="[ORGANIZATION_NAME_FORMAT_1]",
        canonical_kind="organization_name",
        canonical_use="Organization-name examples.",
        replaces="Generic company or institution names used only as examples.",
        examples=("Acme", "Contoso", "Example Inc"),
        aliases=("acme", "contoso", "example inc"),
        detection_pattern=r"\b(acme|contoso|example inc)\b",
    ),
)
_CATALOG_PLACEHOLDER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(definition.detection_pattern, re.IGNORECASE)
    for definition in CATALOG_PLACEHOLDER_INDEX
)


def catalog_placeholder_index_payload() -> list[dict[str, object]]:
    """Return the canonical placeholder index as JSON-compatible rows."""
    return [
        {
            "placeholder": definition.placeholder,
            "canonical_kind": definition.canonical_kind,
            "canonical_use": definition.canonical_use,
            "replaces": definition.replaces,
            "examples": list(definition.examples),
            "aliases": list(definition.aliases),
        }
        for definition in CATALOG_PLACEHOLDER_INDEX
    ]


def catalog_placeholder_matches(
    text: str,
    *,
    include_alias_only: bool = False,
) -> list[dict[str, object]]:
    """Return canonical placeholders matched by example text.

    Returns:
        JSON-compatible match rows ordered by the canonical placeholder index.
    """
    replacements = _catalog_placeholder_replacements(text)
    selected_placeholders = {
        replacement.placeholder for replacement in replacements
    }
    normalized_text = text.casefold()
    matches: list[dict[str, object]] = []
    for definition in CATALOG_PLACEHOLDER_INDEX:
        matched_examples = [
            example
            for example in definition.examples
            if example.casefold() in normalized_text
        ]
        matched_aliases = [
            alias
            for alias in definition.aliases
            if alias.casefold() in normalized_text
        ]
        selected_by_alias = include_alias_only and _has_uncovered_lookup_term(
            text=text,
            terms=(*definition.examples, *definition.aliases),
            replacements=replacements,
        )
        if (
            definition.placeholder not in selected_placeholders
            and not selected_by_alias
        ):
            continue
        matches.append(
            {
                "placeholder": definition.placeholder,
                "canonical_kind": definition.canonical_kind,
                "canonical_use": definition.canonical_use,
                "replaces": definition.replaces,
                "matched_examples": matched_examples,
                "matched_aliases": matched_aliases,
            }
        )
    return matches


def catalog_placeholder_replacement_plan(text: str) -> list[dict[str, object]]:
    """Return non-overlapping sample-value replacement spans ordered by source.

    position.
    """
    return [
        {
            "placeholder": replacement.placeholder,
            "canonical_kind": replacement.canonical_kind,
            "matched_text": replacement.matched_text,
            "start": replacement.start,
            "end": replacement.end,
            "replacement": replacement.placeholder,
        }
        for replacement in _catalog_placeholder_replacements(text)
    ]


def catalog_placeholder_normalized_text(text: str) -> str:
    """Return text with detected sample values replaced by canonical.

    placeholders.
    """
    normalized = text
    for replacement in reversed(_catalog_placeholder_replacements(text)):
        normalized = (
            f"{normalized[: replacement.start]}"
            f"{replacement.placeholder}"
            f"{normalized[replacement.end :]}"
        )
    return normalized


def _has_uncovered_lookup_term(
    *,
    text: str,
    terms: tuple[str, ...],
    replacements: list[CatalogPlaceholderReplacement],
) -> bool:
    """Return if an alias/example term is outside selected replacement spans."""
    if not text:
        return False
    for term in terms:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(text):
            if not any(
                match.start() < replacement.end
                and match.end() > replacement.start
                for replacement in replacements
            ):
                return True
    return False


def _catalog_placeholder_replacements(
    text: str,
) -> list[CatalogPlaceholderReplacement]:
    """Return the computed result for the caller."""
    candidates: list[CatalogPlaceholderReplacement] = []
    for definition, pattern in zip(
        CATALOG_PLACEHOLDER_INDEX,
        _CATALOG_PLACEHOLDER_PATTERNS,
        strict=True,
    ):
        candidates.extend(
            CatalogPlaceholderReplacement(
                placeholder=definition.placeholder,
                canonical_kind=definition.canonical_kind,
                matched_text=match.group(0),
                start=match.start(),
                end=match.end(),
            )
            for match in pattern.finditer(text)
        )
    selected: list[CatalogPlaceholderReplacement] = []
    current_end = -1
    for candidate in sorted(candidates, key=_replacement_sort_key):
        if candidate.start < current_end:
            continue
        selected.append(candidate)
        current_end = candidate.end
    return selected


def _replacement_sort_key(
    replacement: CatalogPlaceholderReplacement,
) -> tuple[int, int]:
    """Sort by position, then prefer wider spans when detectors overlap.

    Returns:
        Tuple key for deterministic replacement ordering.
    """
    return (replacement.start, replacement.start - replacement.end)
