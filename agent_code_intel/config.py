"""config — user configuration and the child environment.

Owns loading ``defaults.toml`` (via :mod:`tomllib`) and executing the legacy
``defaults.env`` as real bash, deciding which applies, and turning the result
into an immutable ``Config`` plus an immutable ``ChildEnvironment`` that every
subprocess inherits (issue #48, decisions 14–28, 36).

This module sits at the bottom of the dependency graph — it imports nothing
from :mod:`agent_code_intel` above it (decision 34).

Not converted yet: the loader lands in issue #51. Importing this module still
does no I/O and reads no file (decision 43).
"""

from __future__ import annotations
