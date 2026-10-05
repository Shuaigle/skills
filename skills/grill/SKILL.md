---
name: grill
description: Grill the user relentlessly about a plan or decision. Use when the user asks to be grilled; the `docs` branch also maintains vocabulary and decision records.
argument-hint: "[docs] <plan or decision>"
---

# Grill

Interview me relentlessly about every aspect of the plan until we reach a shared understanding. Keep the decision tree in conversation context: settled decisions, open decisions, and their prerequisites. Bare grill requires no new artifact.

The **frontier** contains the open decisions whose prerequisites are settled. Ask one frontier question at a time, provide your recommended answer, and wait for my answer before continuing. Questions that depend on an unsettled decision wait; do not guess that answer.

Phrase each question in everyday language: state the concrete choice, its effect, and your recommendation. Define a technical term in one sentence when the decision depends on it.

After each answer, update the tree and frontier. If an earlier answer changes, reopen the downstream decisions it invalidates and confirm them again.

If a *fact* can be found by exploring the environment (filesystem, tools, etc.), look it up rather than asking me. Pending factual exploration is an unsettled prerequisite; ask another ready question while it runs. An empty frontier with blocked branches is a waiting state, not completion. The *decisions*, though, are mine — put each one to me and wait for my answer.

When a decision needs runnable evidence, suggest `prototype-logic` and bring its findings back into the decision tree.

Finish when every known branch is settled and no assumptions remain silently accepted. Summarize the decisions and ask me to confirm our shared understanding. Do not act on the plan until I confirm.

## Question UI

Use an available, permitted question tool for each question. When the decision has clear alternatives, offer 2–3 distinct options, put your recommendation first, and explain each option's effect briefly. Keep free-text input available; do not invent options for an open-ended question.

- **Codex:** Use `request_user_input` when the current mode permits it; it may be limited to Plan mode. Otherwise use `request_user_input_async` when available. After an async question, wait for the user's actual answer before asking the next question or acting on that decision. A preselected option, a timeout, or an empty response is not an answer.
- **Claude Code:** Use `AskUserQuestion` when available.
- **Fallback:** Ask in chat only when no question tool supports the question in the current environment and mode. Listing options in chat does not create a choice UI.

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
