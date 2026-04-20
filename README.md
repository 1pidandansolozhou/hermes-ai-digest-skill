# Hermes AI Digest Skill

[简体中文](./README.zh-CN.md)

Production-oriented Hermes skill for generating strict 48-hour overseas AI intelligence digests with multi-source retrieval, cross-verification, modular reporting, self-learning feedback, and watchdog-based runtime protection.

## Features

- Multi-source retrieval: X, Tavily, DDGS, GitHub, arXiv, Hacker News, Reddit, RSS
- Strict recency: hard filter for events within 48 hours
- Cross-verification: trusted-source timestamps + reverse verification fallback
- Structured modules:
  1. Hot signals
  2. Executive / scientist / big-tech statements
  3. Big-tech executive & technical personnel watchlist (CN + global)
  4. Startup dynamics
  5. Big-tech dynamics
  6. High-quality papers (arXiv)
- Self-learning loop:
  - saves run history
  - compares current metrics against 7-run average
  - reports progress signals and next actions
- Reliability & cost controls:
  - runtime budget guard + stage skipping when budget is exhausted
  - watchdog retry wrapper for timeout/failure recovery
  - compact output fields to reduce downstream token consumption

## Repository Structure

- `SKILL.md`: skill trigger and instructions
- `scripts/x_ai_tavily_digest.py`: main pipeline
- `scripts/x_ai_tavily_digest_guarded.py`: timeout + retry watchdog wrapper
- `README.md`: English documentation
- `README.zh-CN.md`: Chinese documentation

## Quick Start

```bash
python3 scripts/x_ai_tavily_digest.py > digest.json
```

```bash
python3 scripts/x_ai_tavily_digest_guarded.py > digest.json
```

## Recommended Environment Variables

- `TAVILY_API_KEY` (recommended)
- `GITHUB_TOKEN` (optional)
- `TWIKIT_*` / `TWSC_*` (optional, for richer X coverage)

## Hermes Cron Integration

Use `x_ai_tavily_digest_guarded.py` as cron injector for better resilience, then generate digest from:

- `modules`
- `items`
- `collection_stats`
- `learning`

## Runtime / Token Tuning

Useful environment knobs:

- `X_AI_DIGEST_MAX_RUNTIME_SECONDS` (default `70`)
- `X_AI_DIGEST_MAX_ITEMS` (default `24`)
- `X_AI_DIGEST_MAX_CONTENT_CHARS` (default `220`)
- `X_AI_DIGEST_MAX_TAVILY_QUERIES` (default `8`)
- `X_AI_DIGEST_MAX_DDGS_NEWS_QUERIES` (default `4`)
- `X_AI_DIGEST_MAX_DDGS_TEXT_QUERIES` (default `3`)

## License

MIT
