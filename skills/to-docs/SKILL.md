---
name: to-docs
description: Distil finished work into the documentation that outlives it, and prune records that no longer point at live code. Writes to CONTEXT.md and docs/adr/.
disable-model-invocation: true
---

# To Docs

Decide what from a finished piece of work deserves to outlive it, and shrink what is already there. Run this after the implementation is committed, or on its own when the docs have drifted from the code.

Three things outlive a feature: `CONTEXT.md` (the glossary), `docs/adr/` (one decision per file), and the tests. The tests look after themselves, since `tdd` writes them and the suite fails once they stop matching the code. This skill governs the other two. Specs and tickets under `.scratch/` are scaffolding and stay disposable.

Both formats belong to the `grill` skill: [CONTEXT-FORMAT](../grill/references/CONTEXT-FORMAT.md) and [ADR-FORMAT](../grill/references/ADR-FORMAT.md).

## Find the documentation first

Read `CONTEXT-MAP.md` at the repo root. When it exists, the repo carries several contexts, each with its own `CONTEXT.md` and `docs/adr/` at the path the map names, and all of them are in scope. When no map exists, the root `CONTEXT.md` and `docs/adr/` are the whole territory.

## The keep tests

Glossary terms and decision records earn their place on different grounds. Never judge one by the other's test.

**A glossary term** in `CONTEXT.md` stays while it names something specific to this project's domain and still shows up in the code and in how the team talks. General programming vocabulary never belonged there to begin with (see CONTEXT-FORMAT). A term nobody uses any more, or one whose concept has left the codebase, is dead weight.

**A decision record** in `docs/adr/` stays while all three hold:

1. **It passes the ADR gates.** Hard to reverse, surprising without context, the result of a real trade-off. All three, or it never earned a file.
2. **It names live code.** You can point at the module or seam it governs. Anchor the record in `CONTEXT.md` vocabulary and the module and seam language of `codebase-design`, not in file paths. A rename breaks a path; it does not break a module's name.
3. **It stops a future reader from filing a false finding.** Someone auditing this area reads the record and sees a deliberate trade-off where they would otherwise see a defect. If no audit would ever open it, it is not earning its place.

## Approval before any change

Every file under this skill's care was written by a person or approved by one. **Never delete, rewrite, merge, or supersede an existing record until the user has approved that specific change.** This covers the quiet forms of deletion: folding two ADRs into one removes a file, and replacing a glossary term removes a definition.

Present each proposal as one line, naming the record, the test it fails, and what you would do about it. Then wait.

**A run that changes nothing is a complete run.** Docs that are already tight are the goal, not a failure to find work.

## Process

### 1. Prune

Run the matching keep test over every glossary term and every ADR, in every context. Check the anchors by looking: does that module still exist, does that term still appear in the code?

List what fails. Wait for the user.

### 2. Distil

Work from the spec's Implementation Decisions, or from the conversation when no spec exists. Find the decisions that pass the ADR test. **Most runs find none, and that is the expected result.** Say so and move on rather than inventing something to record.

### 3. Fold before adding

For each decision that survives, ask the user whether to fold it into a record that already covers the area or to supersede that record outright. Adding a new file destroys nothing, so it needs no approval past the decision to write it, but reach for it only when nothing existing can absorb the decision. In `CONTEXT.md`, prefer replacing a term over stacking a near-synonym beside it.

A run that merges two ADRs into one has done more than a run that adds a third.

### 4. Commit alone

Documentation gets its own commit, and only where the user or the repo's policy has authorized commits. Otherwise stop after the writes and report the diff.

When the records came out of an implementation, cite that commit in the message. A standalone pruning run has no such commit and cites nothing.

Keeping documentation out of the implementation commit gives the glossary and the ADRs a history you can read without wading through code diffs, and that is what keeps later pruning cheap.

## STOP if

- `CONTEXT.md` or an ADR contradicts the code and you cannot tell which one is wrong. Report the contradiction and let the user settle it.
- You are distilling from work that has no commit yet. Nothing anchors a record to a commit that does not exist. Pruning on its own carries no such requirement.
