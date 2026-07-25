# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Shared JSON payload type contracts for tests.

Boundary contract:
- Owns: named JSON payload aliases for repository tests.
- Must not: parse files, validate domain schemas, or own fixture content.
- Allows: type aliases that make payload boundaries explicit in tests.
- Split when: runtime JSON validators or fixture loaders become shared behavior.
- Merge when: another test support file defines these exact aliases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from catalog.json_payloads import normalize_json_value

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

type JsonObject = dict[str, object]


def json_object_from_text(text: str, label: str) -> JsonObject:
    """Parse one JSON object fixture from text.

    Returns:
        The parsed JSON object with normalized JSON values.

    Raises:
        TypeError: If the parsed JSON value is not an object.
    """
    raw = cast("object", json.loads(text))
    if not isinstance(raw, dict):
        message = f"{label} must be a JSON object."
        raise TypeError(message)
    mapping = cast("Mapping[object, object]", raw)
    return {
        str(key): normalize_json_value(value) for key, value in mapping.items()
    }


def json_object_from_path(path: Path, label: str | None = None) -> JsonObject:
    """Load one JSON object fixture from a UTF-8 path.

    Returns:
        The parsed JSON object with normalized JSON values.
    """
    return json_object_from_text(
        text=path.read_text(encoding="utf-8"),
        label=label or path.as_posix(),
    )
