# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make expression palette facts loaded from private browser evidence.

Boundary contract:
- Owns: offline Make expression palette token lookup from retained screenclip
evidence.
- Must not: call Make.com, infer function arity, evaluate expressions, or expose
screenshots.
- Allows: token family lookup for parsers, linters, planners, and documentation.
- Split when: a full Make expression grammar owns parse trees or evaluator
semantics.
- Merge when: another Make module loads the same palette facts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

JsonObject = dict[str, object]
MakeExpressionTokenKind = Literal[
    "function ",
    "keyword ",
    "operator ",
    "system_variable_label ",
    "variable",
]

PALETTE_ASSET: Final = "make_expression_palette_observations"
PALETTE_PATH: Final = (
    Path(__file__).with_name("data") / "expression_palette.json"
)
PALETTE_OBSERVED_SOURCE: Final = "observed:make-expression-palette"
PALETTE_OBSERVED_ARITY_STATUS: Final = "palette_observed_unverified_arity"


class MakeExpressionTokenFact(NamedTuple):
    """One expression token fact observed in a Make editor palette."""

    token: str
    kind: MakeExpressionTokenKind
    palette_id: str
    palette_title: str
    source: str
    arity_status: str | None = None


def load_make_expression_palette_payload() -> JsonObject:
    """Return the private Make expression palette JSON payload.

    Raises:
        ValueError: If the palette file does not contain the expected object
        shape.
    """
    payload = cast(
        "object", json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    )
    if not _is_json_object(payload):
        message = (
            f"Expected Make expression palette JSON object: {PALETTE_PATH}"
        )
        raise ValueError(message)
    if payload.get("asset") != PALETTE_ASSET:
        message = (
            f"Unexpected Make expression palette asset:{payload.get('asset')!r}"
        )
        raise ValueError(message)
    return payload


def iter_make_expression_token_facts() -> tuple[MakeExpressionTokenFact, ...]:
    """Return all observed expression token facts in stable palette order."""
    payload = load_make_expression_palette_payload()
    palettes = _json_object_list(
        payload.get("palettes"), member_name="palettes"
    )
    facts: list[MakeExpressionTokenFact] = []
    for palette in palettes:
        palette_id = _required_text(palette, "palette_id")
        title = _required_text(palette, "title")
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="variable",
                field_name="variables",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="function",
                field_name="functions",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="operator",
                field_name="operators",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="keyword",
                field_name="keywords",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="system_variable_label",
                field_name="scenario_variables",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="system_variable_label",
                field_name="team_variables",
            )
        )
        facts.extend(
            _token_facts(
                palette=palette,
                palette_id=palette_id,
                title=title,
                kind="system_variable_label",
                field_name="organization_variables",
            )
        )
    return tuple(facts)


def make_expression_token_facts(
    token: str,
    *,
    kind: MakeExpressionTokenKind | None = None,
) -> tuple[MakeExpressionTokenFact, ...]:
    """Return observed facts for one token and optional token kind."""
    normalized = _token_key(token)
    return tuple(
        fact
        for fact in iter_make_expression_token_facts()
        if _token_key(fact.token) == normalized
        and (kind is None or fact.kind == kind)
    )


def make_expression_function_facts(
    function_name: str,
) -> tuple[MakeExpressionTokenFact, ...]:
    """Return observed palette facts for one Make expression function name."""
    return make_expression_token_facts(function_name, kind="function")


def make_expression_function_family_ids(function_name: str) -> tuple[str, ...]:
    """Return observed palette family IDs for one function name."""
    return _dedupe(
        fact.palette_id
        for fact in make_expression_function_facts(function_name)
    )


def known_make_expression_function_names() -> tuple[str, ...]:
    """Return all observed Make expression function names."""
    return _dedupe(
        fact.token
        for fact in iter_make_expression_token_facts()
        if fact.kind == "function"
    )


def _token_facts(
    *,
    palette: JsonObject,
    palette_id: str,
    title: str,
    kind: MakeExpressionTokenKind,
    field_name: str,
) -> tuple[MakeExpressionTokenFact, ...]:
    return tuple(
        MakeExpressionTokenFact(
            token=token,
            kind=kind,
            palette_id=palette_id,
            palette_title=title,
            source=PALETTE_OBSERVED_SOURCE,
            arity_status=(
                PALETTE_OBSERVED_ARITY_STATUS if kind == "function" else None
            ),
        )
        for token in _optional_text_list(palette, field_name)
    )


def _optional_text_list(payload: JsonObject, key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        message = f"Expected list at Make expression palette field {key!r}."
        raise TypeError(message)
    values: list[str] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, str):
            message = (
                f"Expected string token at Make expression palette field"
                f"{key!r}."
            )
            raise TypeError(message)
        text = item.strip()
        if text:
            values.append(text)
    return tuple(values)


def _json_object_list(
    value: object, *, member_name: str
) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        message = (
            f"Expected list at Make expression palette member {member_name!r}."
        )
        raise TypeError(message)
    items: list[JsonObject] = []
    for item in cast("list[object]", value):
        if not _is_json_object(item):
            message = (
                f"Expected JSON object in Make expression palette"
                f"{member_name!r}."
            )
            raise ValueError(message)
        items.append(item)
    return tuple(items)


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Missing Make expression palette text field {key!r}."
        raise ValueError(message)
    return value.strip()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = _token_key(value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return tuple(deduped)


def _token_key(value: str) -> str:
    normalized = value.strip().casefold()
    alphanumeric_key = "".join(
        character for character in normalized if character.isalnum()
    )
    return alphanumeric_key or normalized


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("Mapping[object, object]", value)
    return all(isinstance(key, str) for key in raw)
