---
name: hermes-ai-digest
description: Build a strict 48-hour, multi-source overseas AI intelligence digest for Hermes with cross-verification, modular output, WeChat/email delivery, and self-learning trend feedback.
version: 1.1.0
author: Apple + Codex
license: MIT
metadata:
  hermes:
    tags: [ai, digest, hermes, weixin, email, arxiv, github, tavily, ddgs]
    related_skills: [duckduckgo-search, arxiv, blogwatcher, domain-intel, scrapling]
---

# Hermes AI Digest Skill

Use this skill when user asks to run a daily/periodic AI intelligence digest with strict recency filtering, cross-source checks, and stable delivery under network/time-limit pressure.

## What this skill provides

1. Multi-source collection:
- X (twikit/twscrape)
- Tavily search
- DDGS (free web/news)
- GitHub trending repositories
- arXiv latest papers
- Hacker News, Reddit, RSS media feeds

2. Strict quality constraints:
- 48-hour hard time window
- timestamp normalization to ISO (+08:00)
- trusted-source timestamp pass or reverse-verification pass
- relevance filtering for AI topics

3. Structured output modules:
- 热点信息
- 高管/科学家/大厂发言
- 高管与技术人员（国内外大厂）监测
- 创业公司动态
- 大厂动态
- 优质论文（arXiv）

4. Self-learning feedback:
- persist recent run metrics
- compare current run vs 7-run baseline
- output progress signals and next optimization actions

5. Runtime guard + token optimization:
- watchdog wrapper retries when timeout/failure happens
- runtime budget guard avoids long stalls
- compact output payload reduces downstream generation cost

## Files

- `scripts/x_ai_tavily_digest.py`: main collector and ranker
- `scripts/x_ai_tavily_digest_guarded.py`: watchdog wrapper with timeout/retry

## Usage

Run script directly:

```bash
python3 scripts/x_ai_tavily_digest.py > digest.json
```

Recommended for cron:

```bash
python3 scripts/x_ai_tavily_digest_guarded.py > digest.json
```

Use in Hermes cron job:

- set `script: x_ai_tavily_digest_guarded.py`
- render markdown digest from injected JSON fields: `modules`, `items`, `learning`, `collection_stats`

## Required environment

Recommended:
- `TAVILY_API_KEY`

Optional (for richer X data):
- `TWIKIT_USERNAME`
- `TWIKIT_EMAIL`
- `TWIKIT_PASSWORD`
- `TWSC_USERNAME`
- `TWSC_PASSWORD`
- `TWSC_EMAIL`
- `TWSC_EMAIL_PASSWORD`

Optional:
- `GITHUB_TOKEN`

Runtime tuning (optional):
- `X_AI_DIGEST_MAX_RUNTIME_SECONDS`
- `X_AI_DIGEST_MAX_ITEMS`
- `X_AI_DIGEST_MAX_CONTENT_CHARS`
- `X_AI_DIGEST_MAX_TAVILY_QUERIES`
- `X_AI_DIGEST_MAX_DDGS_NEWS_QUERIES`
- `X_AI_DIGEST_MAX_DDGS_TEXT_QUERIES`

## Delivery recommendation

- WeChat and Email parallel jobs at same schedule
- Email enabled with HTML rendering (markdown -> html)
- Fallback strategy for WeChat delivery failures (email backup)

## Notes

- Keep query pack and source lists updated weekly.
- If noisy results increase, tighten AI relevance keywords and trusted domains.
