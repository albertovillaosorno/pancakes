# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Parse Make expression template delimiters without evaluating expressions.

Boundary contract:
- Owns: delimiter-aware extraction of Make expression template bodies.
- Must not: validate functions, validate output fields, or mutate expressions.
- Allows: quote-aware brace matching shared by validation expression consumers.
- Split when: Make expression tokenization needs a richer AST of its own.
- Merge when: another validation module extracts template bodies identically.
"""

from __future__ import annotations

from typing import Final, NamedTuple

EXPRESSION_START: Final = "{{"
EXPRESSION_END: Final = "}}"


class MakeExpressionTemplate(NamedTuple):
    """One raw Make template with its inner expression body."""

    raw_text: str
    body: str


class MakeExpressionTemplateParseError(ValueError):
    """Raised when Make expression delimiters are not balanced."""


def iter_make_expression_templates(
    text: str,
) -> tuple[MakeExpressionTemplate, ...]:
    """Return Make expression templates while respecting quoted brace text.

    Raises:
        MakeExpressionTemplateParseError: If template parsing cannot be
            satisfied.
    """
    templates: list[MakeExpressionTemplate] = []
    index = 0
    while index < len(text):
        start = text.find(EXPRESSION_START, index)
        close = text.find(EXPRESSION_END, index)
        if close >= 0 and (start < 0 or close < start):
            raise MakeExpressionTemplateParseError
        if start < 0:
            break
        body_start = start + len(EXPRESSION_START)
        body_end = _template_body_end(text, body_start)
        if body_end is None:
            raise MakeExpressionTemplateParseError
        templates.append(
            MakeExpressionTemplate(
                raw_text=text[start : body_end + len(EXPRESSION_END)],
                body=text[body_start:body_end],
            )
        )
        index = body_end + len(EXPRESSION_END)
    return tuple(templates)


def _template_body_end(text: str, body_start: int) -> int | None:
    """Return the close-delimiter index for one template body."""
    index = body_start
    quote: str | None = None
    escaped = False
    while index < len(text) - 1:
        character = text[index]
        if quote is not None:
            escaped, quote = _advance_inside_quote(
                character, quote, escaped=escaped
            )
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "}" and text[index + 1] == "}":
            return index
        index += 1
    return None


def _advance_inside_quote(
    character: str,
    quote: str,
    *,
    escaped: bool,
) -> tuple[bool, str | None]:
    """Return the next escaped and quote state for one quoted character."""
    if escaped:
        return False, quote
    if character == "\\":
        return True, quote
    if character == quote:
        return False, None
    return False, quote
