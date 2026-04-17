# Hermes Skills 组合仓库

当前仓库包含两个可复用 Skill：

1. `hermes-ai-digest`：用于生成严格 48 小时窗口的海外 AI 情报日报。
2. `omx-cli-default`：用于 Codex 调用 OMX 时的任务分群、回传判定与闭环收口（低冗余、低 token）。

Hermes 情报日报仍是主能力，新增 OMX skill 用于统一执行标准和反馈闭环。

## 功能特点

- 多源检索：X、Tavily、DDGS、GitHub、arXiv、Hacker News、Reddit、RSS
- 严格时效：仅保留 48 小时内事件
- 交叉验证：可信源时间戳 + 反向检索兜底
- 模块化输出：
  1. 热点信息
  2. 高管/科学家/大厂发言
  3. 高管与技术人员（国内外大厂）监测
  4. 创业公司动态
  5. 大厂动态
  6. 优质论文（arXiv）
- 自学习机制：
  - 持久化保存运行指标
  - 对比近 7 次均值
  - 输出进步信号与下一步优化动作

## 仓库结构

- `SKILL.md`：Hermes 日报 skill 定义与触发说明
- `scripts/x_ai_tavily_digest.py`：Hermes 日报主流程脚本
- `skills/omx-cli-default/`：Codex-OMX 闭环执行 skill
- `README.md`：英文文档
- `README.zh-CN.md`：中文文档

## 快速开始

```bash
python3 scripts/x_ai_tavily_digest.py > digest.json
```

## 建议环境变量

- `TAVILY_API_KEY`（推荐）
- `GITHUB_TOKEN`（可选）
- `TWIKIT_*` / `TWSC_*`（可选，用于增强 X 信源）

## Hermes 定时任务接入

将本脚本作为 cron 注入脚本，然后在提示词中基于以下字段生成日报：

- `modules`
- `items`
- `collection_stats`
- `learning`

## License

MIT
