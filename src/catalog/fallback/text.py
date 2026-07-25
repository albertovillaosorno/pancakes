# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog fallback text normalization.

Boundary contract:
- Owns: small deterministic tokenization helpers for catalog fallback text.
- Must not: score candidates, inspect catalog entities, plan goals, or
  perform IO.
- Allows: regex-backed normalization and token flattening for local strings.
- Split when: tokenization needs locale policy, stemming, or external
  vocabulary.
- Merge when: another fallback text module exposes the same token helpers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

TOKEN_PATTERN: Final = re.compile(r"[a-z0-9]+")


def normalize_text(value: str) -> str:
    """Return normalized lookup text."""
    return " ".join(TOKEN_PATTERN.findall(value.lower()))


def tokenize(value: str) -> tuple[str, ...]:
    """Return normalized tokens."""
    return tuple(TOKEN_PATTERN.findall(value.lower()))


def flatten_tokens(values: Iterable[str]) -> frozenset[str]:
    """Return normalized tokens from many text values."""
    tokens: set[str] = set()
    for value in values:
        tokens.update(tokenize(value))
    return frozenset(tokens)
