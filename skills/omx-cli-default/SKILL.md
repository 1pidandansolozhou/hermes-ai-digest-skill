---
name: omx-cli-default
description: Run Codex tasks with OMX using adaptive task-cluster routing and an idempotent return close-loop. Keeps prompts concise and avoids duplicate loop work.
---

# OMX CLI Default

## Objective

Align Codex and OMX with a low-token closed loop:

`route -> execute -> handoff-check -> close-loop(if missing)`

## Hard Rules

1. Use task-cluster routing instead of always forcing full OMX flow.
2. Never duplicate close-loop when OMX already returned fresh artifacts.
3. If OMX did not return feedback artifacts, Codex must patch the gap and finish the loop.
4. Keep user-facing reporting short: command, owner, evidence, next action.

## Task Cluster Routing

- `tiny`: one-step lookup/command, no edits, no verification.
  - Run directly in Codex.
  - Skip OMX and skip feedback loop.
- `standard`: light multi-step work, small edits, basic checks.
  - Run `omx exec` (or `omx resume --last`).
  - Use handoff-check; only补闭环 when OMX didn't return artifacts.
- `complex`: debugging/refactor/review/parallel work.
  - Run `omx team` / `omx exec`.
  - Closed-loop required (OMX returns or Codex补齐).

Auto routing uses lightweight keyword heuristics to reduce token overhead.

## OMX Return Handoff Contract

Fresh artifacts mean OMX already closed the loop for this run:

- `.omx/state/skill-feedback/latest-feedback.json`
- `.omx/plans/omx-next-run-brief.md`

If both are newer than run start timestamp, Codex should only summarize and continue the main task. Do not re-run evaluation/close-loop.

## Bootstrap Gate (when needed)

For new projects before substantive execution:

```bash
cd <project-root>
omx init
```

If `omx init` is unavailable:

```bash
cd <project-root>
omx deepinit .
```

If `deepinit` is unavailable:

```bash
cd <project-root>
omx agents-init .
```

## One-Shot Wrapper (recommended)

```bash
~/.codex/skills/omx-cli-default/scripts/omx_run_with_feedback.sh \
  --goal "<current-goal>" \
  --cluster auto \
  --omx "omx exec \"<task>\"" \
  --report "<report_json_path>"
```

Legacy mode is still supported:

```bash
~/.codex/skills/omx-cli-default/scripts/omx_run_with_feedback.sh \
  "<omx_cmd>" "<report_json_path>" "<goal>"
```

## Required Artifacts (for standard/complex loop)

- `.omx/state/skill-feedback/latest-feedback.json`
- `.omx/state/skill-feedback/omx-cli-default.json`
- `.omx/plans/omx-next-run-brief.md`

## Setup Policy

For one-time global install/config injection:

```bash
omx setup --scope user
```

Use project-only scope only on explicit request:

```bash
omx setup --scope project
```

## Recovery Policy

When OMX behavior is unexpected:

```bash
omx doctor
```

If wiring is stale or partially broken:

```bash
omx setup --scope user --force
```

## Execution Behavior

- Codex remains the owner of final delivery quality.
- OMX executes routed tasks; Codex checks return artifacts and only补缺失闭环.
- If OMX already produced closed-loop artifacts, Codex should not redo them.
- If blocked, still persist blocker feedback and next-run brief.

## Output Contract

Always report:

1. OMX commands executed.
2. Loop owner for this run (`omx` or `codex`).
3. Verification evidence and/or blocker.
4. Feedback grade (if loop ran) and next-run brief path.
