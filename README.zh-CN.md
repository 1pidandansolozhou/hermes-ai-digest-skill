# Hermes AI 情报日报 Skill

[English](./README.md)

这是一个面向生产的 Hermes Skill，用于生成严格 48 小时窗口的海外 AI 情报日报，支持多源检索、交叉验证、模块化输出、自学习反馈，以及 watchdog 级别的超时保护。

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
- 稳定性与成本控制：
  - 运行时预算保护（超预算自动跳过低优先级阶段）
  - watchdog 包装脚本超时重试
  - 输出字段压缩，降低下游提示词 token 消耗

## 仓库结构

- `SKILL.md`：skill 定义与触发说明
- `scripts/x_ai_tavily_digest.py`：主流程脚本
- `scripts/x_ai_tavily_digest_guarded.py`：超时+重试 watchdog 包装脚本
- `README.md`：英文文档
- `README.zh-CN.md`：中文文档

## 快速开始

```bash
python3 scripts/x_ai_tavily_digest.py > digest.json
```

```bash
python3 scripts/x_ai_tavily_digest_guarded.py > digest.json
```

## 建议环境变量

- `TAVILY_API_KEY`（推荐）
- `GITHUB_TOKEN`（可选）
- `TWIKIT_*` / `TWSC_*`（可选，用于增强 X 信源）

## Hermes 定时任务接入

建议将 `x_ai_tavily_digest_guarded.py` 作为 cron 注入脚本，再在提示词中基于以下字段生成日报：

- `modules`
- `items`
- `collection_stats`
- `learning`

## 运行时 / Token 调优参数

常用环境变量：

- `X_AI_DIGEST_MAX_RUNTIME_SECONDS`（默认 `70`）
- `X_AI_DIGEST_MAX_ITEMS`（默认 `24`）
- `X_AI_DIGEST_MAX_CONTENT_CHARS`（默认 `220`）
- `X_AI_DIGEST_MAX_TAVILY_QUERIES`（默认 `8`）
- `X_AI_DIGEST_MAX_DDGS_NEWS_QUERIES`（默认 `4`）
- `X_AI_DIGEST_MAX_DDGS_TEXT_QUERIES`（默认 `3`）

## License

MIT
