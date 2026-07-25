# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
"""PDF rendering entry points for Pancakes media reports."""

from pancakes_media.pdf.pancakes_report import document_from_pancakes_report
from pancakes_media.pdf.pipeline import write_pancakes_report_pdf

__all__ = ["document_from_pancakes_report", "write_pancakes_report_pdf"]
