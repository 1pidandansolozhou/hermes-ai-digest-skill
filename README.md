# Hermes AI Digest Skill

[简体中文](./README.zh-CN.md)

Production-oriented Hermes skill for generating strict 48-hour overseas AI intelligence digests with multi-source retrieval, cross-verification, modular reporting, and self-learning feedback.

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

## Repository Structure

- `SKILL.md`: skill trigger and instructions
- `scripts/x_ai_tavily_digest.py`: main pipeline
- `README.md`: English documentation
- `README.zh-CN.md`: Chinese documentation

## Quick Start

```bash
python3 scripts/x_ai_tavily_digest.py > digest.json
```

## Recommended Environment Variables

- `TAVILY_API_KEY` (recommended)
- `GITHUB_TOKEN` (optional)
- `TWIKIT_*` / `TWSC_*` (optional, for richer X coverage)

## Hermes Cron Integration

Use this script as a cron data injector, then generate markdown digest from:

- `modules`
- `items`
- `collection_stats`
- `learning`

## License

MIT
