# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint validation test package.

Boundary contract:
- Owns: package identity for blueprint validation and mapping tests.
- Must not: own rendering, repair, or scraper behavior checks.
- Allows: stable imports for validation-focused test modules.
- Split when: validation subdomains need dedicated support packages.
- Merge when: another marker duplicates validation test identity.
"""

from __future__ import annotations
