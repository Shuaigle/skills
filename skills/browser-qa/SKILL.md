---
name: browser-qa
description: Browser acceptance checks for a running local app. Use to verify an agreed browser workflow or smoke-test a UI change against stated acceptance criteria.
---

# Browser QA

Verify the running app, not a mockup or the source diff. Use `diagnosing-bugs` instead when the request is to reproduce or diagnose a reported bug rather than check an agreed outcome. Use the repository's existing browser tests and fixtures before opening a manual browser session. Do not add a test framework, install tools, or change global agent configuration.

1. **Pin the scenario.** Read the relevant ticket, acceptance criteria, and dev/test instructions. Record the revision or build, local URL, fixture, expected visible result, and the action that proves it. If the repo has a test that exercises the same flow and assertion, run its focused command first.
2. **Isolate the run.** Use the repo's local start command, an isolated browser context, and synthetic data. Confirm the active origin and test backend before any write; stop if a scenario can touch production, a live integration, or a personal account. If the local app, fixture, or browser isn't available, say what is blocked. Do not substitute someone's signed-in browser, a public app, or a credential file.
3. **Exercise the flow.** Observe the initial state, perform the actions as a user, and assert the visible outcome or persistent state after reload when relevant. Test edge cases only when the acceptance criteria or the user include them. Check the relevant console or network event only when it answers an assertion or explains a failure. An HTTP 200 or a screenshot alone does not prove that the workflow worked.
4. **Attach minimal evidence.** For each case, report `pass | fail | blocked | not run`, steps or test command, expected and observed outcomes, and the smallest useful evidence. Keep artifacts local unless the user authorizes sharing; remove identities, tokens, request fields and other sensitive data before saving or quoting evidence. If something failed, capture the shortest reliable reproduction and whether it reproduced on another run. Say what remains unverified; browser QA does not cover native-app behavior.

If existing tests cannot produce the required evidence, see [optional runtime tools](references/runtime-tools.md) for isolated Chrome DevTools MCP or for trimming an already-safe recording. Skip these tools when the focused test or existing browser harness is sufficient.
