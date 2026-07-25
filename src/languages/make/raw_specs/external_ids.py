# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.external-id-normalization
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Lossless normalization for Make external identifiers.

Boundary contract:
- Owns: lossless validation of positive external identifier text.
- Must not: fetch data, parse raw specs, build paths, or perform IO.
- Allows: preserving decimal identifiers without numeric narrowing.
- Split when: identifier policy becomes endpoint or payload specific.
- Merge when: another helper validates the same external identifier shape.
"""

from __future__ import annotations


def normalize_make_external_id(value: object, *, field_name: str) -> str:
    """Return one positive decimal Make identifier as text.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    if isinstance(value, bool):
        message = f"{field_name} must not be boolean."
        raise TypeError(message)
    if isinstance(value, int):
        return _positive_decimal(str(value), field_name=field_name)
    if isinstance(value, str):
        return _positive_decimal(value.strip(), field_name=field_name)
    message = f"{field_name} must be a positive integer or decimal string."
    raise TypeError(message)


def normalize_optional_make_external_id(
    value: object | None,
    *,
    field_name: str,
) -> str | None:
    """Return an optional Make external identifier as text."""
    if value is None:
        return None
    return normalize_make_external_id(value, field_name=field_name)


def _positive_decimal(value: str, *, field_name: str) -> str:
    """Validate one positive decimal identifier without numeric narrowing.

    Returns:
        The validated value.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if not value:
        message = f"{field_name} must not be empty."
        raise ValueError(message)
    if not value.isdigit():
        message = f"{field_name} must contain decimal digits only."
        raise ValueError(message)
    if int(value) <= 0:
        message = f"{field_name} must be positive."
        raise ValueError(message)
    return value
