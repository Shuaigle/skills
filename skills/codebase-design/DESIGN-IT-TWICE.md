# Design It Twice

When the user wants to explore alternative interfaces for a chosen deepening candidate, use this parallel sub-agent pattern. Based on "Design It Twice" (Ousterhout) — your first idea is unlikely to be the best.

Uses the vocabulary in [SKILL.md](SKILL.md) — **module**, **interface**, **seam**, **adapter**, **leverage**.

## Process

### 1. Frame the problem space

Before spawning sub-agents, write a user-facing explanation of the problem space for the chosen candidate:

- The constraints any new interface would need to satisfy
- The dependencies it would rely on, and which category they fall into (see [DEEPENING.md](DEEPENING.md))
- A rough illustrative code sketch to ground the constraints — not a proposal, just a way to make the constraints concrete

Use plain labels in that explanation: current problem, constraints, dependencies, and example.

Show this to the user, then immediately proceed to Step 2. The user reads and thinks while the sub-agents work in parallel.

### 2. Spawn sub-agents

Start with two sub-agents using the harness's sub-agent mechanism. No sub-agent support? Work through the same briefs yourself, one design at a time. Both designs must satisfy the same confirmed requirements; add another only to resolve a specific trade-off.

Prompt each sub-agent with a separate technical brief (file paths, coupling details, dependency category from [DEEPENING.md](DEEPENING.md), what sits behind the seam). The brief is independent of the user-facing problem-space explanation in Step 1. Give each agent a different design constraint:

- Agent 1: "Give the direct baseline using the existing structure and interfaces where possible."
- Agent 2: "Explore a different interface for the same requirements; name the concrete limitation of the direct approach it addresses."

Include [SKILL.md](SKILL.md)'s design criteria and vocabulary, plus the relevant vocabulary record, in each brief.

Each sub-agent outputs:

1. Interface (types, methods, params — plus invariants, ordering, error modes)
2. Usage example showing how callers use it
3. What the implementation hides behind the seam
4. Dependency strategy and adapters (see [DEEPENING.md](DEEPENING.md))
5. Trade-offs — where leverage is high, where it's thin

### 3. Present and compare

Present designs sequentially so the user can absorb each one, then compare them in prose. Contrast by **depth** (leverage at the interface), **locality** (where change concentrates), and **seam placement**.

For the user, explain these as the public surface, hidden behaviour, change location, and where the module interface lives.

Recommend one design using [SKILL.md](SKILL.md#design-criteria)'s criteria. A hybrid needs a concrete shortcoming that neither design alone addresses.
