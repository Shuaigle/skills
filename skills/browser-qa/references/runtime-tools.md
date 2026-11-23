# Optional runtime tools

## Chrome DevTools MCP

Use only when the host already provides it and the test needs interactive DOM, network or console evidence the repo's tests do not supply. Use a separate temporary Chrome profile (`--isolated`), disable usage statistics and CrUX URL lookups, and verify the local origin before performing the scenario. Do not auto-connect to daily Chrome or attach to its debugging port. If isolation is unknown, use the repo's own browser runner or mark interactive verification blocked. The [upstream configuration](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/configuration.md) lists the flags for the installed version.

Prefer an assertion or a small before/after screenshot over a full trace, raw HAR, or request body. Do not export a trace containing personal data or credentials.

## Short recording

Use a recording only when the bug or assertion depends on timing or order (e.g. a double-submit or a stale screen returning after navigation). Use the existing browser recorder or an authorized simulator recording. If FFmpeg is already available, trim an already-sanitized local copy to a new file. Never use trimming as redaction. This example emits 8 seconds starting at second 2, no audio, and refuses to overwrite:

```bash
ffmpeg -nostdin -n -ss 2 -i ./qa-recording.mp4 -t 8 -an \
  -c:v libx264 -pix_fmt yuv420p ./qa-evidence.mp4
```

Check the resulting clip before sharing. If FFmpeg or the encoder is unavailable, leave the source alone and report the missing step. Do not run a bulk installer or load external presets. See the [FFmpeg CLI reference](https://ffmpeg.org/ffmpeg.html).
