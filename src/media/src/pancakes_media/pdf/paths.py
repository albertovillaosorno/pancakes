# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Repository validation support module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def pdf_data_root(repo_root: Path) -> Path:
    """Return the repo-local PDF data root."""
    return repo_root / "pdf" / "data"
