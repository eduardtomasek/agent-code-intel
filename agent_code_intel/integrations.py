"""integrations — adapters for the external stack.

One place per external tool — grepai, gitnexus, qdrant, ollama, the container
runtime — that knows how to call it and how to parse its human-readable output
into domain values (issue #48, decision 38). The parsing lives here, not in
``CommandRunner`` and not in the mode orchestration.

Qdrant counts as healthy only with both HTTP health and an open gRPC port
(decision 47); a GrepAI project name mapped elsewhere is ``CONFLICT``
(decision 48); generated GrepAI config is edited only within owned regions
(decision 49).

Not converted yet: the adapters land with the modes that use them (issues
#53–#56).
"""

from __future__ import annotations
