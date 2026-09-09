# Distribute a managed routing skill per agent target

`agent-code-intel --apply` installs one canonical `agent-code-intel-routing`
skill into `.claude/skills` for Claude and `.agents/skills` for Codex, with
`both` selecting both byte-identical copies. Identical files are untouched,
managed drift is repaired, and a foreign collision requires `--force-docs`;
this preserves user content while keeping normal apply convergent. Status treats
selected-skill drift as unhealthy, while full removal deletes both managed
copies because it also removes the shared project indexes and identity.

## Consequences

The canonical skill must live inside the installed Python package. GitNexus
may still create its own cross-agent documents and Claude skills during
`analyze`; those external artifacts are outside this ownership boundary.
