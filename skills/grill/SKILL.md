---
name: grill
description: Grill the user relentlessly about a plan or decision. Use when the user asks to be grilled; the `docs` branch also maintains vocabulary and decision records.
argument-hint: "[docs] <plan or decision>"
---

# Grill

Interview me relentlessly about every aspect of the plan until we reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Phrase each question in everyday language: state the concrete choice, its effect, and your recommendation. Define a technical term in one sentence when the decision depends on it.

Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering.

If a *fact* can be found by exploring the environment (filesystem, tools, etc.), look it up rather than asking me. The *decisions*, though, are mine — put each one to me and wait for my answer.

Do not act on the plan until I confirm we have reached a shared understanding.

## Variants

- Bare — invoking `grill` with no argument runs the interview alone.
- `docs` — the `docs` argument adds domain modeling, below.

## The `docs` variant

Maintain the project's vocabulary and decision records as the session runs. Resolve each role with [DOCUMENTATION-LOCATIONS.md](references/DOCUMENTATION-LOCATIONS.md). Create files lazily, only when there is something to write.

During the session:

- **Challenge against the record.** When a term conflicts with the vocabulary record, call it out immediately: "Your vocabulary record defines 'cancellation' as X, but you seem to mean Y — which is it?"
- **Sharpen fuzzy language.** When a term is vague or overloaded, propose a precise canonical one: "You're saying 'account' — do you mean the Customer or the User?"
- **Stress-test with scenarios.** Invent edge-case scenarios that force me to be precise about the boundaries between concepts.
- **Cross-reference the code.** When I state how something works, check whether the code agrees. Surface contradictions: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"
- **Update the vocabulary record inline.** Capture each resolved term the moment it lands, in the format that record already uses. On the default layout it is `CONTEXT.md` and [references/CONTEXT-FORMAT.md](references/CONTEXT-FORMAT.md). The record holds terms: no implementation details, no spec, no scratch pad.
- **Offer ADRs sparingly.** Only when the decision is hard to reverse AND surprising without context AND the result of a real trade-off. All three, or skip. Write it where the repo keeps its decisions; [references/ADR-FORMAT.md](references/ADR-FORMAT.md) covers the default.
