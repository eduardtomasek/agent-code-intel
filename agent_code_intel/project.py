"""project — project identity and health probes.

Resolves the project a run acts on — explicit workspace, a valid ``.code-intel``,
a pristine legacy identity on first migration, or the sanitized basename
(issue #48, decision 30) — into an immutable ``ProjectContext``, never
executing ``.code-intel`` as shell (decision 31). Also owns the shared status
probes and the single rule that turns a probe's domain value into an immutable
``Finding`` the calling mode classifies as fatal / drift / warning / normal
(decision 39).

Not converted yet: identity lands in issue #51, the status table in #53.
"""

from __future__ import annotations
