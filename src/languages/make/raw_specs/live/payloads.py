# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""JSON payload helpers for Make API responses.

Boundary contract:
- Owns: JSON object decoding helpers for live Make API responses.
- Must not: execute HTTP, choose endpoints, write manifests, or parse raw specs.
- Allows: fail-closed response shape checks and string-key normalization.
- Split when: payload handling needs endpoint-specific schemas.
- Merge when: another payload module enforces the same response object contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from languages.make.raw_specs.live.errors import MakeApiRemoteError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from languages.make.raw_specs.models import JsonObject


def ensure_json_object(payload_bytes: bytes, *, label: str) -> JsonObject:
    """Decode bytes and require a JSON object.

    Returns:
        The decoded value.

    Raises:
        MakeApiRemoteError: If the make api remote contract cannot be satisfied.
    """
    if not payload_bytes:
        return {}
    decoded = cast("object", json.loads(payload_bytes.decode("utf-8")))
    if not isinstance(decoded, dict):
        message = f"Make API {label} returned a non-object JSON payload."
        raise MakeApiRemoteError(message)
    return json_object_from_mapping(cast("Mapping[object, object]", decoded))


def json_object_from_mapping(mapping: Mapping[object, object]) -> JsonObject:
    """Return a string-keyed JSON object without widening to Any."""
    return {str(key): value for key, value in mapping.items()}
