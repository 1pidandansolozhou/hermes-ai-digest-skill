# OMX CLI Default - Adaptive Closed Loop (CN + EN)

## 中文

### 现在怎么工作

`omx-cli-default` 已改为“任务群路由 + 去重闭环”：

- `tiny`：Codex 直接做，不走 OMX。
- `standard`：先 OMX 执行，再检查 OMX 是否已回传闭环产物。
- `complex`：必须闭环，但优先复用 OMX 已生成的闭环结果。

核心目标是减少冗余提示词和重复脚本调用，省 token。

### OMX 回传判定

若以下两个文件在本次运行开始后被更新，视为 OMX 已完成闭环，Codex 不再重复执行：

- `.omx/state/skill-feedback/latest-feedback.json`
- `.omx/plans/omx-next-run-brief.md`

### 推荐一键命令

```bash
~/.codex/skills/omx-cli-default/scripts/omx_run_with_feedback.sh \
  --goal "<当前目标>" \
  --cluster auto \
  --omx "omx exec \"<任务>\"" \
  --report "<报告JSON路径>"
```

### 兼容旧调用

```bash
~/.codex/skills/omx-cli-default/scripts/omx_run_with_feedback.sh \
  "<omx命令>" "<报告JSON路径>" "<目标>"
```

---

## English

### New behavior

`omx-cli-default` now uses task-cluster routing with idempotent closed-loop handling:

- `tiny`: direct Codex execution, no OMX loop.
- `standard`: OMX run first, then handoff check.
- `complex`: closed-loop required, but reuse OMX artifacts if already produced.

This avoids prompt bloat and duplicate loop work.

### OMX handoff check

If both files are fresher than this run start time, OMX is treated as loop owner and Codex skips re-running close-loop:

- `.omx/state/skill-feedback/latest-feedback.json`
- `.omx/plans/omx-next-run-brief.md`

### Recommended one-liner

```bash
~/.codex/skills/omx-cli-default/scripts/omx_run_with_feedback.sh \
  --goal "<current-goal>" \
  --cluster auto \
  --omx "omx exec \"<task>\"" \
  --report "<report-json-path>"
```
