# Documentation Locations

Resolve two roles separately: the **vocabulary record** that defines domain terms, and the **decision records** that explain durable trade-offs. An answer for one role says nothing about the other.

For each role, stop at the first answer:

1. Read `CLAUDE.md` and `AGENTS.md` for an explicit location or precedence rule.
2. Read a root `CONTEXT-MAP.md`. It locates each context's vocabulary record, not its decision records.
3. Inspect the repo's existing documentation. Judge a file by what it does, not its name.
4. Fall back to a root `CONTEXT.md` and `docs/adr/`. Under a context map, `docs/adr/` sits beside each mapped `CONTEXT.md`.

Either role may be empty, and one file may fill both. Keep one source of truth per role: reuse the repo's record and format instead of creating a parallel one.
