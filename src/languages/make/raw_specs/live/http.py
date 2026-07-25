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

"""HTTP protocols for injectable Make API transport.

Boundary contract:
- Owns: minimal transport protocols and default retry sleep hook.
- Must not: build API URLs, parse JSON, own credentials, or write artifacts.
- Allows: injectable response protocol and one standard-library sleep wrapper.
- Split when: transport abstractions need streaming, tracing, or async support.
- Merge when: another HTTP helper exposes the same live transport protocol.
"""

from __future__ import annotations

import time
from typing import Protocol, Self

type JsonQuery = dict[str, str | int | float | bool]


class HttpResponseLike(Protocol):
    """Minimal response protocol used by MakeApiClient."""

    status: int
    headers: dict[str, str]

    def read(self, amount: int = -1) -> bytes:
        """Read bytes from the response body."""
        ...

    def __enter__(self) -> Self:
        """Enter response context."""
        ...

    def __exit__(
        self, exc_type: object, exc: object, tb: object
    ) -> bool | None:
        """Exit response context."""
        ...


def default_sleep(seconds: float) -> None:
    """Sleep between live retry attempts."""
    time.sleep(seconds)
