# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Repository validation support module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from schoenwald_pdf import RenderedPdf, write_handoff_pdf

from pancakes_media.pdf.pancakes_report import document_from_pancakes_report

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def write_pancakes_report_pdf(
    *,
    report: Mapping[str, object],
    output_root: Path,
    relative_path: str,
) -> RenderedPdf:
    """Return the computed result for the caller."""
    document = document_from_pancakes_report(report)
    return write_handoff_pdf(
        document=document,
        output_root=output_root,
        relative_path=relative_path,
    )
