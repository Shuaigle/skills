---
name: to-docs
description: Distil finished work into the documentation that outlives it, and prune records that no longer point at live code. Writes into the repo's own vocabulary and decision records, CONTEXT.md and docs/adr/ by default.
disable-model-invocation: true
---

# To Docs

Decide what from a finished piece of work deserves to outlive it, and shrink what is already there. Run this after the implementation is committed, or on its own when the docs have drifted from the code.

Three things outlive a feature: the vocabulary record (`CONTEXT.md` by default), the decision records (`docs/adr/` by default, one decision per file), and the tests. The tests look after themselves, since `tdd` writes them and the suite fails once they stop matching the code. This skill governs the other two. Specs and tickets under `.scratch/` are scaffolding and stay disposable.

In user messages, translate the internal labels into plain language: vocabulary record means the project terms file; decision record means a design-decision document; prune means remove outdated documentation; distil means save useful terms and decisions; fold means add a decision to an existing record; supersede means write its replacement; scaffolding means temporary spec and ticket files.

The default formats belong to the `grill` skill: [CONTEXT-FORMAT](../grill/references/CONTEXT-FORMAT.md) and [ADR-FORMAT](../grill/references/ADR-FORMAT.md). A repo with its own documentation system keeps its own formats. Match what is there instead of reshaping it.

## Find the documentation first

Resolve the vocabulary and decision roles with [DOCUMENTATION-LOCATIONS.md](../grill/references/DOCUMENTATION-LOCATIONS.md). Where a role is filled, run its keep test against those files. Opening a home for an empty role is a change like any other: propose it and wait.

Start by naming which files you took for each role and what format each uses, one line per role. Where you landed anywhere but the defaults, or where a role has no home at all, stop there and let the user confirm the reading before you prune. Read the wrong files and every proposal after it is wrong too.

## The keep tests

Terms and decision records earn their place on different grounds. Never judge one by the other's test.

**A term** stays while it names something specific to this project's domain and still shows up in the code and in how the team talks. General programming vocabulary never belonged there to begin with (see CONTEXT-FORMAT). A term nobody uses any more, or one whose concept has left the codebase, is dead weight.

**A decision record** stays while all three hold:

1. **It passes the ADR gates.** Hard to reverse, surprising without context, the result of a real trade-off. All three, or it never earned a file.
2. **It names live code.** You can point at the module or seam it governs. Anchor the record in the project's own vocabulary and the module and seam language of `codebase-design`, not in file paths. A rename breaks a path; it does not break a module's name.
3. **It stops a future reader from filing a false finding.** Someone auditing this area reads the record and sees a deliberate trade-off where they would otherwise see a defect. If no audit would ever open it, it is not earning its place.

## Approval before any change

Every file under this skill's care was written by a person or approved by one. **Never delete, rewrite, merge, or supersede an existing record until the user has approved that specific change.** This covers the quiet forms of deletion: folding two decision records into one removes a file, and replacing a defined term removes a definition.

**Raise one proposal at a time.** Say how many you found, then put the first one up: the record, the test it fails, and the choice it needs. Wait for the answer before the next. Hold the rest back until then, including the ones that look obvious.

A wall of five proposals gets one hurried yes covering all five, which is not approval of any of them. Where a proposal needs the user to settle a contradiction rather than approve a change, that one goes first and goes alone.

**Keep each one small.** Ten lines is the ceiling: what the record says, what the code says, the choice you need settled. Anchor it with one file and line. Leave out the evidence tables, the measurements, the records that passed the test, and the findings you noticed on the way. The user asks for the rest when they want it.

**Offer a choice and name your pick.** Two or three ways to settle it, a line each, then the one you would take and the reason. "Shall I change it?" hands back the judgement you were asked to make.

**A run that changes nothing is a complete run.** Docs that are already tight are the goal, not a failure to find work.

## Process

**Find the work first.** Look for the newest `.scratch/<feature-slug>/` carrying a marked `spec.md`, and the commits landed since the last documentation commit. Pick the way in from what turns up, and scope step 1 to it. Several candidates, ask which one. Nothing recent, say there is nothing to distil before you sweep anything.

Two ways in, and they cover different ground. **Distilling a finished piece of work** runs all five steps, with step 1 narrowed to the records that work touched. **A standalone pruning run** sweeps every record in step 1 and stops there. Take the first when you found work, the second when the user asked for a sweep.

Deliver the one you were asked for. "Write up what I just built" asks for step 2, and questions about records that work never touched bury the answer to it. Offer the sweep as a separate run.

### 1. Prune

In a standalone run, apply the matching keep test to every term and every decision record, in every context. In a distil run, apply it to the records that work touched: the ones you are about to write into, and the ones governing the same modules.

Check the anchors by looking: does that module still exist, does that term still appear in the code?

Count what fails and say the number. Then work through them one at a time.

A contradiction you spot outside that scope is worth a line at the end of the run, naming the file and what looks wrong. It stays a note. Turning it into a proposal drags the user into a decision they did not ask for.

### 2. Distil

Work from the marked `spec.md` and the implementation commits. The spec records intent; the landed code records what survived contact with implementation. Two kinds of thing can come out, and each takes its own test.

**Domain terms.** `grill docs` captures vocabulary the moment it lands, so most terms are written down long before you get here. What you are looking for is the term that surfaced during implementation and never made it back: a concept the code now names that the vocabulary record still misses. Apply the term test.

**Decisions.** Read the spec's Implementation Decisions, compare them with the landed code, and apply the decision-record test.

**Most runs find none of either, and that is the expected result.** Say so and move on rather than inventing something to record.

Decisions never go in the vocabulary record, and terms never become decision records.

### 3. Fold before adding

**Terms.** Write each surviving term into the vocabulary record, in the format that record already uses. A term with no counterpart there costs nothing to add. Replacing or merging an existing definition removes one, so propose that and wait. Prefer replacing a term over stacking a near-synonym beside it.

**Decisions.** Take the surviving decisions one at a time. For each, ask the user whether to fold it into a record that already covers the area or to supersede that record outright. Adding a new file destroys nothing, so it needs no approval past the decision to write it, but reach for it only when nothing existing can absorb the decision.

A run that merges two decision records into one has done more than a run that adds a third.

### 4. Commit alone

Documentation gets its own commit, and only where the user or the repo's policy has authorized commits. Otherwise stop after the writes and report the diff.

When the records came out of an implementation, cite that commit in the message. A standalone pruning run has no such commit and cites nothing.

Keeping documentation out of the implementation commit gives these records a history you can read without wading through code diffs, and that is what keeps later pruning cheap.

### 5. Offer to take the scaffolding down

A distil run only, and only after step 4 committed. Where commits were not authorized and you stopped at the diff, the spec still holds decisions that live nowhere else, so say nothing about deleting it. A standalone pruning run has no feature directory in view and skips the step.

Once the documentation commit lands, the spec and its tickets have done their job, and the next reader who opens them takes a finished plan for the current one. The whole `.scratch/<feature-slug>/` is one disposable unit, so what it holds does not need auditing. What matters is deleting the right directory, and only once the work in it is done.

Check the target is exactly one `.scratch/<feature-slug>/`, the slug a single path segment. Never `.scratch/` itself, never a path climbing out of it.

Then check the work is finished. Every acceptance criterion across the tickets is ticked, or the user says so outright. A criterion still `[ ]` means that check never passed: name the ticket and offer nothing. Tickets written before the tick-on-pass rule read as unfinished here, and the user clears those directories by hand.

Then one offer: the path spelled out, that deleting cannot be undone, and keep or delete with keeping as the default. One confirmation covers one directory. Other directories under `.scratch/` are out of scope however stale they look; sweeping them is a request the user has not made.

## STOP if

- A record in scope contradicts the code and you cannot tell which one is wrong. Report the contradiction and let the user settle it. Outside the scope of this run, the same contradiction is a note at the end and stops nothing.
- You are distilling from work that has no commit yet. Nothing anchors a record to a commit that does not exist. Pruning on its own carries no such requirement.
