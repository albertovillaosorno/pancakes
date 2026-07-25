# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Raw spec refresh test package.

Boundary contract:
- Owns: package identity for raw-spec scraper and refresh tests.
- Must not: own compiled catalog schema assertions.
- Allows: stable imports for raw-spec test modules.
- Split when: live and offline raw-spec tests need separate support packages.
- Merge when: another marker duplicates raw-spec test identity.
"""

from __future__ import annotations
