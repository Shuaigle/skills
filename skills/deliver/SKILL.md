---
name: deliver
description: Run one feature end to end — grill, to-spec, optional to-tickets, implement, review in a fresh session, to-docs — keeping each step's own checkpoints.
argument-hint: "[docs] | <spec issue URL or path to resume>"
disable-model-invocation: true
---

# Deliver

Carry one feature from discussion to documented, reviewed code. This session is the **conductor**: it runs every step except review, and review runs in a session that did not write the code.

Run each step by reading its `SKILL.md` and following it. Keep every checkpoint inside a step: grill's questions, to-spec's seam check, to-tickets' breakdown approval, review's fix selection, to-docs' one-at-a-time proposals. Skip only a step's closing instruction to stop and point the user at the next step; continue to the next step instead.

## Start

| Argument | Run |
|---|---|
| none | New run; step 1 uses `grill` |
| `docs` | New run; step 1 uses `grill docs` |
| spec issue URL or path | Resume (see below) |

Before step 1, or before the first step of a resumed run, ask once whether this run may commit. Use the available question tool.

- **Yes**: commit on the current branch: one implementation commit per ticket (one in total without tickets), review fixes, and documentation in its own commit.
- **No**: at the first commit point, stop and report the diff. The user commits and resumes.

## Steps

1. **Grill** — [grill](../grill/SKILL.md). The user's confirmation of the summary is the gate to step 2.
2. **Spec** — [to-spec](../to-spec/SKILL.md). Keep the spec locator. The commit the spec records is the run's **fixed point**.
3. **Tickets** — decide yourself: skip when the spec is one vertical slice that fits one context; otherwise run [to-tickets](../to-tickets/SKILL.md). State the decision and its reason in one line; do not ask.
4. **Implement** — [implement](../implement/SKILL.md), in this session. With tickets, work them in blocking order. Keep its handoff for steps 5 and 6.
5. **Review** — in a fresh session, once, after all implementation. See below.
6. **Docs** — back in this session, run [to-docs](../to-docs/SKILL.md) with the implementation handoff and the review fix commits since the fixed point.

## Review in a fresh session

The review session receives only:

- The target repo, spec and ticket locators, the fixed point, and the implementation commits.
- The checks that passed, from the implement handoff.
- The commit decision from Start, quoted as the user gave it.
- The instruction: run [review](../review/SKILL.md) against the fixed point, fix what the user selects, then stop without running to-docs.

Give it no conversation context and no account of the design beyond the spec. It shares this checkout, or this session's worktree, so fixes land on the same branch. While it runs, this session writes nothing.

When the harness can start a session, start it with that brief and wait for it to finish. Otherwise stop and give the user one command block to paste into a new session, using this install's invocation syntax for `review`; continue at step 6 when the user returns.

## Resume

Write no state file. Read the spec at the given locator and infer the next step from the artifacts:

| Artifacts | Next step |
|---|---|
| No generated tickets for this spec, no commits after the fixed point | 3 |
| Tickets with unticked acceptance boxes, or implementation unfinished | 4 |
| Implementation complete, review status unknown | Ask whether review finished; then 5 or 6 |
| Documentation commit citing the implementation | Done |

When the artifacts cannot settle whether a step finished, ask the user one question.

## STOP if

- A step stops on its own STOP condition, drift check, or conflict. Report it in plain language; the user resumes later with the spec locator.
- The fixed point does not resolve to a commit.
