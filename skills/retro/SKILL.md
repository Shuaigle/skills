---
name: retro
description: Review a coding session and suggest concrete improvements to the agent's environment.
disable-model-invocation: true
---

# Retro

Review the session the user names, or the current conversation by default. Propose changes that would prevent observed failures or reduce repeated friction. This run produces recommendations; applying them is a separate task.

## Process

1. **Read the evidence.** Use the session's messages, commands, results, and diffs. If another session is named, read its relevant history through the available conversation tools or logs. If that source is unavailable, report the gap. Reference locations and credential types; redact secrets and personal data from excerpts.

2. **Check the environment.** Read the affected repo's instructions, documented standards, task-runner commands, and CI or hooks where relevant. Find existing checks before proposing another one. Distinguish a missing check from one that exists but was skipped, broken, or never connected to the workflow.

3. **Classify each candidate.** Keep only candidates supported by this session:
   - **Mechanical mistakes:** prefer a deterministic check in the repo's existing tooling. Name the observable failure it would catch and where it should run.
   - **Judgement calls:** clarify a documented standard for review when an automated check cannot decide it. Preserve recorded architectural trade-offs.
   - **Navigation:** add a short pointer when finding the right source was the actual bottleneck. Keep facts obtainable from one file or command at their source.
   - **Tool use and information access:** identify repeated searches, noisy outputs, or unavailable logs that materially slowed the work. Propose the smallest change that addresses that evidence.

4. **Rank and report.** Present the most costly or recurring problems first. For each recommendation, give the session evidence, impact, proposed change, effort, trade-off, and how to verify it. Separate confirmed failures from questions needing investigation. An existing check that was not run calls for repairing the workflow, not adding a duplicate check.

## Completion

Every recommendation must trace to an observed event and name a concrete improvement. A short report with no findings is valid; do not manufacture a checklist of generic tooling upgrades.

Report inline. Keep implementation work and permanent vocabulary or decision records with their existing workflows; a retrospective does not create another permanent project journal.
