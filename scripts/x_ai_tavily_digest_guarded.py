#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BJT = "+08:00"
SCRIPT = Path.home() / ".hermes" / "scripts" / "x_ai_tavily_digest.py"
ATTEMPT_TIMEOUTS = [70, 55]

ATTEMPT_ENVS = [
    {},
    {
        "X_AI_DIGEST_MAX_RUNTIME_SECONDS": "55",
        "X_AI_DIGEST_MAX_TAVILY_QUERIES": "5",
        "X_AI_DIGEST_MAX_DDGS_NEWS_QUERIES": "3",
        "X_AI_DIGEST_MAX_DDGS_TEXT_QUERIES": "2",
        "X_AI_DIGEST_MAX_RSS_FEEDS": "4",
        "X_AI_DIGEST_MAX_HN_QUERIES": "3",
        "X_AI_DIGEST_MAX_REDDIT_SUBREDDITS": "2",
        "X_AI_DIGEST_MAX_ITEMS": "16",
        "X_AI_DIGEST_MAX_CONTENT_CHARS": "140",
    },
]


def _fallback_payload(reason: str, traces: list[dict[str, str]]) -> dict:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ok": False,
        "generated_at_bj": ts,
        "generated_at_iso": datetime.now().isoformat(),
        "source": "multi_source_ai_digest_guarded",
        "runtime_guard": {
            "watchdog": True,
            "reason": reason,
            "attempt_traces": traces,
        },
        "collection_stats": {
            "raw_collected": 0,
            "after_filter": 0,
            "returned": 0,
            "tavily_used": False,
            "ddgs_used": False,
            "query_count": 0,
        },
        "errors": [{"query_label": "watchdog", "error": reason}],
        "learning": {
            "enabled": False,
            "progress_signals": [],
            "next_actions": ["请检查网络/API 可用性，watchdog 已执行重试。"],
        },
        "modules": {
            "hot_info": [],
            "exec_scientist_bigtech_voice": [],
            "exec_tech_bigtech_watch": [],
            "startup_updates": [],
            "bigtech_updates": [],
            "quality_papers_arxiv": [],
        },
        "items": [],
    }


def main() -> int:
    if not SCRIPT.exists():
        print(json.dumps(_fallback_payload("digest_script_missing", [{"script": str(SCRIPT)}]), ensure_ascii=False, indent=2))
        return 0

    traces: list[dict[str, str]] = []
    for idx, timeout_sec in enumerate(ATTEMPT_TIMEOUTS):
        env = os.environ.copy()
        env.update(ATTEMPT_ENVS[idx])
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT)],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
            )
        except subprocess.TimeoutExpired:
            traces.append({"attempt": str(idx + 1), "result": "timeout", "timeout_sec": str(timeout_sec)})
            continue

        if proc.returncode != 0:
            traces.append(
                {
                    "attempt": str(idx + 1),
                    "result": f"exit_{proc.returncode}",
                    "stderr": (proc.stderr or proc.stdout or "")[:220],
                }
            )
            continue

        try:
            payload = json.loads(proc.stdout)
        except Exception:
            traces.append({"attempt": str(idx + 1), "result": "invalid_json"})
            continue

        count = int((payload.get("collection_stats") or {}).get("returned") or len(payload.get("items") or []))
        traces.append({"attempt": str(idx + 1), "result": "ok", "returned": str(count)})

        if count > 0:
            rg = payload.get("runtime_guard") if isinstance(payload.get("runtime_guard"), dict) else {}
            rg["watchdog"] = True
            rg["attempt_traces"] = traces
            payload["runtime_guard"] = rg
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

    print(json.dumps(_fallback_payload("all_attempts_failed_or_empty", traces), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
