---
name: to-docs
description: Distil finished work into the documentation that outlives it, and prune records that no longer point at live code. Writes to CONTEXT.md and docs/adr/.
disable-model-invocation: true
---

# To Docs

Decide what from a finished piece of work deserves to outlive it, and shrink what is already there. Run this after the implementation is committed, or on its own when the docs have drifted from the code.

Two things live in the repo long term: `CONTEXT.md` (the glossary) and `docs/adr/` (one decision per file). Both formats belong to the `grill` skill: [CONTEXT-FORMAT](../grill/references/CONTEXT-FORMAT.md) and [ADR-FORMAT](../grill/references/ADR-FORMAT.md). Specs and tickets under `.scratch/` are scaffolding and stay disposable.

## The keep test

A record stays only while all three hold. Apply it to what you are about to write and to everything already on disk.

1. **It passes the ADR gates.** Hard to reverse, surprising without context, the result of a real trade-off. All three, or skip.
2. **It names live code.** You can point at the module or seam it governs. Anchor the record in `CONTEXT.md` vocabulary and the module and seam language of `codebase-design`, not in file paths. A rename breaks a path; it does not break a module's name.
3. **It stops a future reader from filing a false finding.** Someone auditing this area reads the record and sees a deliberate trade-off where they would otherwise see a defect. If no audit would ever open it, it is not earning its place.

Fail any one and the record goes, whoever wrote it.

## Process

### 1. Prune first

Read `CONTEXT.md` and every file under `docs/adr/`. Run the keep test on each. Check the anchor by looking: does that module still exist, does that glossary term still appear in the code?

**Propose deletions and wait for the user.** List what fails and why, one line each. These files are the user's, and a stale record costs less than a lost one.

### 2. Distil what is new

Work from the spec's Implementation Decisions, or from the conversation when no spec exists. Find the decisions that pass the keep test. **Most runs find none, and that is the expected result.** Say so and move on rather than inventing something to record.

### 3. Fold before adding

Fold each survivor into a record that already covers the area, or supersede that record outright. Add a new file only when nothing existing can absorb it. In `CONTEXT.md`, replace a term instead of stacking a near-synonym beside it. Records that a newer one makes redundant are waste, the way old unit tests become waste once tests at the deepened interface exist.

A run that merges two ADRs into one has done more than a run that adds a third.

### 4. Commit alone

Documentation gets its own commit, citing the implementation commit it came from. Keeping it out of the implementation commit gives the glossary and the ADRs a history you can read without wading through code diffs, and that is what keeps later pruning cheap.

## STOP if

- `CONTEXT.md` or an ADR contradicts the code and you cannot tell which one is wrong. Report the contradiction and let the user settle it.
- The work you are documenting has no commit yet. Nothing anchors a record to a commit that does not exist.
