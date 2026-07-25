# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Commercial asset boundary test package.

Boundary contract:
- Owns: package identity for commercial asset data boundary tests.
- Must not: own course evidence or runtime catalog data checks.
- Allows: stable imports for commercial asset test modules.
- Split when: asset categories need dedicated test support.
- Merge when: another marker duplicates commercial asset test identity.
"""

from __future__ import annotations
