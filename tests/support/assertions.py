# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Shared assertion helpers for repository tests.

Boundary contract:
- Owns: reusable assertion-only helpers for test control-flow failures.
- Must not: hide behavior-specific expectations or replace direct assertions.
- Allows: unreachable-path assertion helpers for callbacks and search helpers.
- Split when: domain-specific helpers need their own support module.
- Merge when: another support module owns the same generic assertion behavior.
"""

from __future__ import annotations

from typing import Never


def assert_unexpected_success(message: str) -> Never:
    """Assert that a test path expected to fail was unexpectedly reached.

    Raises:
        AssertionError: Always when the path is reached.
    """
    unexpected_success = False
    assert unexpected_success, message
    raise AssertionError(message)
