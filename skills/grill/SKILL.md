---
name: grill
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, says "grill me" or 「拷問我」, or uses any 'grill' trigger phrase. The `docs` variant also maintains the project's domain glossary (CONTEXT.md) and ADRs during the session.
---

# Grill

Interview me relentlessly about every aspect of the plan until we reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering.

If a *fact* can be found by exploring the environment (filesystem, tools, etc.), look it up rather than asking me. The *decisions*, though, are mine — put each one to me and wait for my answer.

Do not act on the plan until I confirm we have reached a shared understanding.

## Variants

- Bare (`/grill`) — the interview alone.
- `docs` (`/grill docs`) — the interview plus domain modeling, below.

## The `docs` variant

Maintain the project's shared language and decision records as the session runs. File layout — create files lazily, only when there is something to write:

```
/
├── CONTEXT.md        ← glossary, nothing else
└── docs/adr/         ← one decision per file
```

A root `CONTEXT-MAP.md` means the repo has multiple contexts; it points to each context's own `CONTEXT.md` and `docs/adr/`.

During the session:

- **Challenge against the glossary.** When a term conflicts with `CONTEXT.md`, call it out immediately: "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"
- **Sharpen fuzzy language.** When a term is vague or overloaded, propose a precise canonical one: "You're saying 'account' — do you mean the Customer or the User?"
- **Stress-test with scenarios.** Invent edge-case scenarios that force the user to be precise about the boundaries between concepts.
- **Cross-reference the code.** When the user states how something works, check whether the code agrees. Surface contradictions: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"
- **Update `CONTEXT.md` inline.** Capture each resolved term the moment it lands, using [references/CONTEXT-FORMAT.md](references/CONTEXT-FORMAT.md). `CONTEXT.md` stays free of implementation details: a glossary, not a spec or scratch pad.
- **Offer ADRs sparingly.** Only when the decision is hard to reverse AND surprising without context AND the result of a real trade-off. All three, or skip. Format: [references/ADR-FORMAT.md](references/ADR-FORMAT.md).
