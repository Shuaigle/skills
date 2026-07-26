# Advanced Feedback Loops

1. **Replay a captured trace.** Save a real request, payload, or event log; replay it through the code path in isolation.
2. **Throwaway harness.** Run the smallest system subset that reaches the bug with one call.
3. **Property or fuzz loop.** Drive many generated inputs through an intermittent wrong-output path.
4. **Bisection harness.** Automate boot-and-check across commits, datasets, or versions so `git bisect run` can consume it.
5. **Differential loop.** Run one input through two versions or configurations and diff the outputs.
6. **HITL bash script.** When a human must click, drive the session with `../scripts/hitl-loop.template.sh` and feed captured output back into the loop.
