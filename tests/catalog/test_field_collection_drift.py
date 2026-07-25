# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Drift tests for Make raw-spec field collection ownership.

Boundary contract:
- Owns: shared field collection identity checks for catalog compiler and
storage.
- Must not: compile catalogs, build SQLite databases, or refresh raw specs.
- Allows: import-surface assertions that prevent collection drift.
- Split when: field collection policy gains versioned migration behavior.
- Merge when: catalog compiler/storage tests assert this shared source directly.
"""

from __future__ import annotations

from catalog.compiler import FIELD_COLLECTIONS as COMPILER_FIELD_COLLECTIONS
from catalog.field_collections import (
    FIELD_COLLECTIONS as SHARED_FIELD_COLLECTIONS,
)
from catalog.knowledge import storage as knowledge_storage

EXPECTED_FIELD_COLLECTIONS = (
    ("parameters", "parameter"),
    ("expect", "expect"),
    ("interface", "interface"),
)


def test_catalog_field_collections_do_not_babaf5e3() -> None:
    """Compiler and storage must share one Make field collection contract."""
    assert SHARED_FIELD_COLLECTIONS == EXPECTED_FIELD_COLLECTIONS, (
        f"Unexpected Make field collections: {SHARED_FIELD_COLLECTIONS}"
    )
    assert not (COMPILER_FIELD_COLLECTIONS is not SHARED_FIELD_COLLECTIONS), (
        "Catalog compiler must re-export the shared FIELD_COLLECTIONS constant."
    )
    assert not (
        knowledge_storage.FIELD_COLLECTIONS is not SHARED_FIELD_COLLECTIONS
    ), "Knowledge storage must import the shared FIELD_COLLECTIONS constant."
