---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

## Rules

1. Drift-check first: compare the spec/ticket's recorded commit against `HEAD`. If the code it cites has changed underneath it, stop and report — do not improvise around a stale plan.
2. Touch only what the spec/ticket puts in scope. No drive-by fixes; note them for a future ticket.
3. A ticket's STOP condition fires → stop and report.

## Loop

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Done = every acceptance criterion verified by running its command, not by judgement.

Once done, run whichever code-review skill is available and address its findings; with none installed, review the diff yourself against the spec before committing.

Commit to the current branch only when the user or the repo's policy has authorized commits; otherwise stop after verification and report the diff.
