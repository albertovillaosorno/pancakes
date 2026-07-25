# Languages

This directory owns source automation platform language boundaries.

Each active child directory represents an original automation platform language,
not a generated implementation target. `src/languages/make/` owns Make.com
source material, Make raw specifications, Make-owned data, Make JSON
interpretation, and Make-to-Pancakes translation behavior. Make is one language
adapter and the only executable source adapter today; it is not the product
core. Future Zapier, n8n, or other source-language layers must become peer
adapters only after evidence, translation ownership, and validation contracts
are accepted.

Python is not a source automation language in this repository. Python is the
implementation language for Pancakes and may later become an output or
translation target through a separate accepted boundary.

Language layers may translate into and out of `src/ir/**` and the current
blueprint compatibility runtime, but they must not own generic IR graph
semantics, AST validation, repair, optimization, or MCP delivery policy.
