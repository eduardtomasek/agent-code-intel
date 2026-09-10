"""agent_code_intel — the Python port of the agent-code-intel CLI (issue #48).

This package is the single behavioural unit the two thin launchers hand control
to. It is still being built one slice at a time against the frozen Bash
reference ``9406cce``; only the pieces a converted slice has landed are wired
up. Everything else raises a deliberate error rather than pretending to work
(issue #48, decision 70).

Module layout (issue #48, decision 33) — these seven, no ``utils``:

    cli           argv → Options, early exit, dispatch; the one launcher entry
    config        defaults.toml / defaults.env loading, ChildEnvironment
    project       .code-intel / registry identity, status probes, Finding
    integrations  grepai / gitnexus / qdrant / ollama / container adapters
    commands      preview / apply / refresh / status / remove orchestration
    hooks         repo-local Claude and Codex SessionStart hook lifecycle
    install       self-install, upgrade, the launcher templates

Dependency direction is one-way (decision 34): cli → commands/install,
commands → project/integrations/hooks, install → config, config/hooks → nothing
above them.

Importing any module must do no I/O, read no config, print nothing and start
nothing (decision 43).
"""

# The single source of the product version (issue #48, decision 73). The CLI
# banner and the JSON status both read it from here. The active entrypoint
# switch in issue #58 makes this the 5.0.0 product version.
__version__ = "5.0.0"
