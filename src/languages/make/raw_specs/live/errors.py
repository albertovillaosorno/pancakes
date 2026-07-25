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

"""Make API client exceptions for the scraper boundary.

Boundary contract:
- Owns: scraper-local exception types for live Make API failures.
- Must not: perform transport, parse responses, retry, or inspect credentials.
- Allows: stable error taxonomy for configuration, rate limits, and failures.
- Split when: errors need structured payload fields or retry classifications.
- Merge when: another live error module defines the same exception taxonomy.
"""

from __future__ import annotations


class MakeApiError(RuntimeError):
    """Base exception for Make API adapter failures."""


class MakeApiConfigurationError(MakeApiError):
    """Raised when live Make API configuration is incomplete."""


class MakeApiRateLimitError(MakeApiError):
    """Raised when Make API rate limiting is not recoverable."""


class MakeApiRemoteError(MakeApiError):
    """Raised when Make API transport or response handling fails."""
